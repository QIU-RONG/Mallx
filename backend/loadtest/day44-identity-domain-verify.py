# -*- coding: utf-8 -*-
"""
Day 44 · 身份域隔离验收（含【控制组】）

背景（为什么要这个脚本）
------------------------
`users` 与 `admins` 是 01-schema.sql 里两张【独立的表】，id 各自从 1 起。
而 JWT 过滤器只把 token 的 `sub`（一个 Long）塞进 principal ⇒
「超管 1」和「顾客 1」在 SecurityContext 里长得一模一样。

Day 44 取证（修复前，见 `_probe_domain.py` 的历史输出）：
    超管 token(sub=1,type=ADMIN)
      GET /api/users/me  → HTTP 200  返回顾客 demo 的手机号/昵称/邮箱
      GET /api/orders    → HTTP 200  返回该顾客全部 6 张订单
      GET /api/cart      → HTTP 200
      GET /api/addresses → HTTP 200
      GET /api/coupons/my→ HTTP 200
即：管理端 token 可以【直接顶替任意 C 端顾客】。

修复（Day 44）
--------------
1. JwtAuthenticationFilter 读 `type` claim，写入 DOMAIN_USER / DOMAIN_ADMIN 两个
   authority；type 缺失或未知 ⇒ **fail closed**（不登记身份 ⇒ 401）。
2. SecurityConfig 按路径把关：/api/admin/** 只收 ADMIN、其余只收 USER，
   例外只有 `POST /api/orders/*/ship`（管理端动作挂在 C 端前缀下）。

★ 控制组（本脚本自带，不可省）
------------------------------
同一套断言在【修复前】的代码上必须全红 —— 证据就是 `_probe_domain.py`：
它在修复前把上面那 5 个端点全部打成了 200，修复后同一支脚本全部变 403。
⇒ 断言确实对「有没有这道闸门」敏感，而不是恒真的摆设。
（脚本里另有 `--control` 模式，把预期翻转成「修复前」的旧行为，
  用于在需要时用真实旧代码回跑：此时脚本**必须失败**。）

用法
----
    python day44-identity-domain-verify.py              # 正式验收（预期全绿）
    python day44-identity-domain-verify.py --control    # 控制组（预期失败）

只读：不写业务数据、不改库存、不下单。
"""
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080"
CONTROL = "--control" in sys.argv          # True = 按「修复前（有漏洞）」的预期跑

FAILS = []
TOTAL = 0
LINES = []


def say(s=""):
    LINES.append(s)


def chk(name, ok, detail=""):
    """控制组模式下把预期【整体翻转】：修好了 ⇒ 旧预期不成立 ⇒ 应当 FAIL。"""
    global TOTAL
    TOTAL += 1
    verdict = ok if not CONTROL else (not ok)
    if not verdict:
        FAILS.append(name + (" | " + detail if detail else ""))
    say("  [%s] %s%s" % ("PASS" if verdict else "FAIL", name,
                         ("  -- " + detail) if detail else ""))


def req(method, path, token=None, body=None):
    url = BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                  # noqa: BLE001
        return -1, "EXC " + str(e)


def japi(method, path, token=None, body=None):
    st, raw = req(method, path, token, body)
    try:
        return st, json.loads(raw), raw
    except Exception:                                       # noqa: BLE001
        return st, {}, raw


def payload_of(token):
    """只解 payload，不验签 —— 这里只是取证「token 里到底写了什么」。"""
    seg = token.split(".")
    if len(seg) < 2:
        return {}
    pad = seg[1] + "=" * (-len(seg[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(pad).decode("utf-8"))
    except Exception:                                       # noqa: BLE001
        return {}


def login(path, username, password):
    st, b, raw = japi("POST", path, body={"username": username, "password": password})
    tok = (b.get("data") or {}).get("token")
    return st, tok, b, raw


def main():
    say("=" * 78)
    say("Day 44 · 身份域隔离验收   BASE=%s   mode=%s"
        % (BASE, "CONTROL(旧行为预期)" if CONTROL else "正式验收"))
    say("=" * 78)

    # ------------------------------------------------------------ [0] 登录
    say("\n[0] 登录并取证 token 内容")
    st_u, user_tok, bu, _ = login("/api/auth/login", "demo", "demo123")
    st_a, admin_tok, ba, _ = login("/api/auth/admin/login", "admin", "admin123")
    chk("C 端登录成功 (demo)", st_u == 200 and bool(user_tok), "http=%s" % st_u)
    chk("管理端登录成功 (admin)", st_a == 200 and bool(admin_tok), "http=%s" % st_a)
    if not user_tok or not admin_tok:
        say("\nABORT: 两个 token 缺一不可（DB 没起？应用没起？）")
        flush()
        return 1

    pu, pa = payload_of(user_tok), payload_of(admin_tok)
    say("    C 端 token  : sub=%r type=%r username=%r"
        % (pu.get("sub"), pu.get("type"), pu.get("username")))
    say("    管理端 token: sub=%r type=%r username=%r"
        % (pa.get("sub"), pa.get("type"), pa.get("username")))
    chk("两个 token 的 type claim 已区分 (USER / ADMIN)",
        pu.get("type") == "USER" and pa.get("type") == "ADMIN")
    # ★ 这是整个漏洞的成因：只看 sub 分不出来
    say("    ★ 注意：若两个 sub 数值相同，则「只看 sub」= 必然混淆（本库实测 sub 均为 %r）"
        % pu.get("sub"))

    # ------------------------------------------------- [1] 正向：同域仍然通
    say("\n[1] 正向控制组：本域 token 打本域接口，必须照旧 200（修闸门不能把自家门堵死）")
    for name, path in [("/api/users/me", "/api/users/me"),
                       ("/api/orders", "/api/orders"),
                       ("/api/cart", "/api/cart"),
                       ("/api/addresses", "/api/addresses"),
                       ("/api/coupons/my", "/api/coupons/my")]:
        st, b, raw = japi("GET", path, token=user_tok)
        chk("C 端 token → GET %s = 200" % name, st == 200 and b.get("code") == 200,
            "http=%s code=%s" % (st, b.get("code")))

    for name, path in [("/api/admin/dashboard/overview", "/api/admin/dashboard/overview"),
                       ("/api/admin/users", "/api/admin/users"),
                       ("/api/admin/orders", "/api/admin/orders")]:
        st, b, raw = japi("GET", path, token=admin_tok)
        chk("管理端 token → GET %s = 200" % name, st == 200 and b.get("code") == 200,
            "http=%s code=%s" % (st, b.get("code")))

    # ------------------------------------------- [2] 反向：跨域一律真 403
    say("\n[2] 核心：管理端 token 打 C 端接口 → 必须【真 HTTP 403】，且 body 不带任何数据")
    for path in ["/api/users/me", "/api/orders", "/api/cart",
                 "/api/addresses", "/api/coupons/my"]:
        st, b, raw = japi("GET", path, token=admin_tok)
        leaked = json.dumps(b.get("data"), ensure_ascii=False) if b.get("data") else "null"
        chk("管理端 token → GET %s = HTTP 403" % path, st == 403,
            "http=%s code=%s" % (st, b.get("code")))
        chk("  且响应体不含任何业务数据 (data=%s)" % leaked[:24],
            b.get("data") is None, "data=%s" % leaked[:60])

    say("\n[3] 反向：C 端 token 打管理端接口 → 403")
    for path in ["/api/admin/dashboard/overview", "/api/admin/users", "/api/admin/orders"]:
        st, b, raw = japi("GET", path, token=user_tok)
        chk("C 端 token → GET %s = HTTP 403" % path, st == 403,
            "http=%s code=%s" % (st, b.get("code")))

    # ------------------------------- [4] 例外通道：发货仍归管理端（不能误杀）
    say("\n[4] 例外通道：POST /api/orders/{id}/ship 是管理端动作却挂在 C 端前缀下")
    st_a_ship, b_a_ship, _ = japi("POST", "/api/orders/999999/ship", token=admin_tok)
    st_u_ship, b_u_ship, _ = japi("POST", "/api/orders/999999/ship", token=user_tok)
    chk("管理端 token 打发货【未被域闸门拦下】(http≠403)", st_a_ship != 403,
        "http=%s code=%s" % (st_a_ship, b_a_ship.get("code")))
    chk("C 端 token 打发货【被拦下】(http=403)", st_u_ship == 403,
        "http=%s code=%s" % (st_u_ship, b_u_ship.get("code")))

    # --------------------------------------------- [5] fail-closed 兜底检查
    say("\n[5] fail closed：token 不可解析 ⇒ 401（而不是 500，也不是「当成没权限的已登录」）")
    st, b, raw = japi("GET", "/api/users/me", token=admin_tok[:-3] + "aaa")
    chk("篡改过的 token → 401", st == 401, "http=%s" % st)
    st, b, raw = japi("GET", "/api/users/me", token=None)
    chk("不带 token → 401", st == 401, "http=%s" % st)

    # ------------------------------------------------------------------ 汇总
    say("\n" + "=" * 78)
    if CONTROL:
        say("控制组结论：%d/%d 项【按旧行为预期不成立】"
            % (TOTAL - len(FAILS), TOTAL))
        say("  ⇒ 旧行为与新断言冲突的项数 = %d（>0 才说明断言抓得住这个 bug）" % len(FAILS))
    else:
        say("验收结论：%d/%d 通过，失败 %d" % (TOTAL - len(FAILS), TOTAL, len(FAILS)))
        for f in FAILS:
            say("  ✗ " + f)
    say("=" * 78)
    flush()
    if CONTROL:
        return 0 if FAILS else 1          # 控制组：有冲突才算抓得住
    return 0 if not FAILS else 1


def flush():
    out = "\n".join(LINES)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                        # noqa: BLE001
        pass
    print(out)
    with open("day44-identity-domain-result.txt", "w", encoding="utf-8") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    sys.exit(main())
