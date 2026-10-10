# -*- coding: utf-8 -*-
"""身份域隔离 —— 影响面探针（Day 44）

要证的命题
----------
`JwtAuthenticationFilter` 只把 token 的 `sub` 转成 `Long` 当 principal，
**不看** `JwtUtil` 签进去的 `type`（`USER` / `ADMIN`）claim；
而 `users` 与 `admins` 是 01-schema.sql 里**两张独立的表**，id 各自从 1 起。
两者相乘 ⇒ 管理端 token（`sub` = `admins.id`）打 C 端接口时，
会被当作 `users.id = admins.id` 那位顾客来执行。

本脚本**只做取证，不做判定**（不写断言、不改任何数据）：
   ① 解出两个 token 的 sub / type（base64，不需要密钥）—— 证明两者数值可能相同
   ② 用管理端 token 打 C 端各只读端点，记录返回
   ③ 把返回的数据拿去 DB 里查真实归属 —— 看它是不是「同号顾客」的
   ④ 反向：C 端 token 打管理端端点

用法：
    python _probe_domain.py                 # 打 127.0.0.1:8080
    MALLX_BASE=http://127.0.0.1:8081 python _probe_domain.py
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.environ.get("MALLX_BASE", "http://127.0.0.1:8080")
DOCKER = os.environ.get("MALLX_DOCKER") or \
    r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PG = "mallx-postgres"

USER_NAME, USER_PW = "demo", "demo123"
ADMIN_NAME, ADMIN_PW = "admin", "admin123"

OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


# ---------------------------------------------------------------- HTTP
def api(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        code = e.code
    except Exception as e:                       # noqa: BLE001
        return 0, {"_err": str(e)}, ""
    try:
        return code, json.loads(raw), raw
    except Exception:                            # noqa: BLE001
        return code, {"_raw": raw[:300]}, raw


def jwt_claims(token):
    """只解 payload（base64url），不验签 —— 用于做「sub / type 是什么」的取证。"""
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p).decode("utf-8"))
    except Exception as e:                       # noqa: BLE001
        return {"_err": str(e)}


# ---------------------------------------------------------------- DB
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         PG, "psql", "-U", "mallx", "-d", "mallx", "-X", "-t", "-A", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed (rc=%d)\nSQL: %s\nstderr: %s" % (p.returncode, sql, err))
    return out


def one(sql):
    return psql(sql).strip()


def brief(obj, limit=200):
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + " …"


# ---------------------------------------------------------------- main
def main():
    say("=" * 78)
    say("身份域隔离 · 影响面取证   BASE=%s" % BASE)
    say("=" * 78)

    # ---- ① 登录，解 token
    st, b, _ = api("POST", "/api/auth/login", body={"username": USER_NAME, "password": USER_PW})
    ctoken = (b.get("data") or {}).get("token") if isinstance(b, dict) else None
    st2, b2, _ = api("POST", "/api/auth/admin/login", body={"username": ADMIN_NAME, "password": ADMIN_PW})
    atoken = (b2.get("data") or {}).get("token") if isinstance(b2, dict) else None

    say()
    say("[0] 登录与 token 身份")
    say("    C 端登录   HTTP %s  token=%s" % (st, "有" if ctoken else "★无"))
    say("    管理端登录 HTTP %s  token=%s" % (st2, "有" if atoken else "★无"))
    if not ctoken or not atoken:
        say("    ★ 登录失败，后续无法取证：")
        say("      C=%s" % brief(b))
        say("      A=%s" % brief(b2))
        return 2

    cc, ac = jwt_claims(ctoken), jwt_claims(atoken)
    say("    C 端 token payload: sub=%r  type=%r  username=%r"
        % (cc.get("sub"), cc.get("type"), cc.get("username")))
    say("    管理端 token payload: sub=%r  type=%r  username=%r"
        % (ac.get("sub"), ac.get("type"), ac.get("username")))
    same = cc.get("sub") == ac.get("sub")
    say("    ★ 两个 token 的 sub %s（%r vs %r）"
        % ("**数值相同** —— 过滤器只看 sub 就分不出来" if same else "不同", cc.get("sub"), ac.get("sub")))

    asub, csub = ac.get("sub"), cc.get("sub")

    # ---- ② 两张表的实际数据：找出 id 交集
    say()
    say("[1] 两张表的 id 空间（01-schema.sql：users 与 admins 各自独立）")
    say("    users  : %s" % one("SELECT string_agg(id||'='||username, ', ' ORDER BY id) FROM users"))
    say("    admins : %s" % one("SELECT string_agg(id||'='||username, ', ' ORDER BY id) FROM admins"))
    overlap = one("SELECT COALESCE(string_agg(u.id::text, ',' ORDER BY u.id), '(空)')"
                  " FROM users u JOIN admins a ON a.id = u.id")
    say("    id 交集: %s  ← 交集里的每个号，管理端 token 都能『顶替』那位顾客"
        % overlap)
    say("    管理端 sub=%s 在 users 表里存在: %s"
        % (asub, one("SELECT EXISTS(SELECT 1 FROM users WHERE id=%s)" % asub)))
    say("    该号顾客: %s"
        % one("SELECT COALESCE((SELECT username||' / '||COALESCE(nickname,'(无昵称)')||' / '"
              "||COALESCE(phone,'(无手机号)') FROM users WHERE id=%s), '(不存在)')" % asub))

    # ---- ③ 管理端 token 打 C 端只读端点
    say()
    say("[2] 用【管理端 token】打 C 端只读端点（正常应为 401/403 而不是数据）")
    probes = [
        ("GET", "/api/users/me",        "我的资料"),
        ("GET", "/api/orders",          "我的订单列表"),
        ("GET", "/api/cart",            "我的购物车"),
        ("GET", "/api/addresses",       "我的收货地址"),
        ("GET", "/api/coupons/my",      "我的优惠券"),
    ]
    for method, path, label in probes:
        code, body, _ = api(method, path, token=atoken)
        data = body.get("data") if isinstance(body, dict) else None
        say()
        say("    %-22s %-6s → HTTP %s  code=%s" % (path, label, code,
                                                  body.get("code") if isinstance(body, dict) else "?"))
        say("        返回: %s" % brief(data))

        # 逐条对账：返回的东西在 DB 里属于谁
        cid = data.get("id") if isinstance(data, dict) else None
        if path == "/api/users/me" and cid is not None:
            who = one("SELECT COALESCE(username,'(无)') FROM users WHERE id=%s" % cid)
            say("        ★ DB 核对：该记录 id=%s 属于 users.username=%s  ← %s"
                % (cid, who, "就是同号顾客本人" if str(cid) == str(asub) else "非同号，需另查"))
        if path == "/api/orders" and isinstance(data, dict):
            recs = data.get("records") or []
            ids = [r.get("id") for r in recs]
            say("        订单数=%d  ids=%s" % (len(ids), ids[:12]))
            if ids:
                owner = one("SELECT string_agg(DISTINCT user_id::text, ',') FROM orders WHERE id IN (%s)"
                            % ",".join(str(int(i)) for i in ids))
                say("        ★ DB 核对：这些订单的 user_id = %s   （管理端 sub=%s ⇒ %s）"
                    % (owner, asub, "同一人 —— 管理端 token 读到了顾客的订单" if owner == str(asub) else "需人工判"))

    # ---- ④ 反向：C 端 token 打管理端端点
    say()
    say("[3] 反向：用【C 端 token】打管理端端点（应被 403 挡住）")
    for path in ["/api/admin/orders", "/api/admin/users", "/api/admin/dashboard/overview"]:
        code, body, _ = api("GET", path, token=ctoken)
        say("    %-38s → HTTP %s  code=%s  %s"
            % (path, code, body.get("code") if isinstance(body, dict) else "?", brief(body, 90)))

    say()
    say("=" * 78)
    say("取证完成（本脚本不判定、不写库）")
    say("=" * 78)
    return 0


if __name__ == "__main__":
    rc = main()
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "_probe_domain-report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")
    sys.exit(rc)
