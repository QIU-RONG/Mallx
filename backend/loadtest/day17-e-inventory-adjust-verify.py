# -*- coding: utf-8 -*-
"""Day 17 链路 E -- 管理端库存调整（POST /api/admin/inventory/skus/{skuId}/adjust）。

这是【第四个库存写点】，也是四条里【唯一会改 total_stock 的一条】。
所以验收的重点不是"接口通不通"，而是四条互相独立的判据：

  ① 权限矩阵的区分度 —— 必须用 op_order（ORDER_ADMIN，没有 inventory:adjust）
     打进来拿到 403。admin（SUPER_ADMIN）全是 200，它【证明不了】权限码写对了没。
  ② ★ 动量守恒 —— 成功的调整必须让 total 与 available【同向同量】移动，
     而 locked / sold【一格都不许动】。这是本链路的核心不变量。
  ③ ★ 400 与 500 的分界 —— delta=0 / 调整后为负 / SKU 不存在，三者都是
     【用户可理解的业务结果】(400)，而不是 moveLockedToSold 那类"账目不一致"(500)。
  ④ ★ 流水的自洽 —— 本次新增的 ADMIN_ADJUST 流水逐条满足
     change == after - before，且 Σ(change) == Δtotal（这对账式只有本类型成立）。

★ 本链路的用例【会真的改库存】，所以脚本必须自带「还原 + 回收」两件事：
  · 库存：+5 → -3 → 再 -2 归位，净变化 0，Σ(change) 也恰好为 0；
  · 流水：DELETE FROM inventory_logs WHERE id > 水位线。
    （⚠️ 生产里流水表只增不改不删；但验收脚本必须把库放回基线，
      与 day14/15/16/17-C 四个脚本同一句话、同一约定。）
  两件都做完，day17-m1-regression.py 才可能给出 BASELINE RESTORED: YES。

Usage:
    python day17-e-inventory-adjust-verify.py
报告（utf-8）与脚本同目录：day17-e-inventory-adjust-verify-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
SKU = 1
ADJUST = "/api/admin/inventory/skus/%d/adjust" % SKU
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day17-e-inventory-adjust-verify-report.txt")

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=60):
    """★ 显式禁用代理：会话注入的 HTTP_PROXY 会把 127.0.0.1 也拦下（502 os error 10061）。"""
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                                      # noqa: BLE001
        return -1, '{"transport_error": "%s"}' % repr(e)


def japi(method, path, token=None, body=None):
    st, raw = api(method, path, token, body)
    try:
        return st, json.loads(raw), raw
    except ValueError:
        return st, {"raw": raw}, raw


def body_code(raw):
    try:
        return json.loads(raw).get("code")
    except ValueError:
        return None


def body_msg(raw):
    try:
        return json.loads(raw).get("message")
    except ValueError:
        return None


def short(raw, n=190):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ---------------------------------------------------------------- db helpers
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


def one(sql):
    """单值。⚠️ docker exec 回传行尾带 \\r —— 不 strip 会让比对恒为假。"""
    return psql(sql).strip()


def inv(sku=SKU):
    row = one("SELECT total_stock||'|'||available_stock||'|'||locked_stock||'|'||sold_stock"
              " FROM inventories WHERE sku_id = %d" % sku)
    if not row:
        return None
    p = row.split("|")
    return dict(total=int(p[0]), available=int(p[1]), locked=int(p[2]), sold=int(p[3]))


def fmt(d):
    return "total=%-4d avail=%-4d locked=%-3d sold=%-3d" % (
        d["total"], d["available"], d["locked"], d["sold"])


def identity(sku=SKU):
    return one("SELECT (total_stock = available_stock + locked_stock + sold_stock)"
               " FROM inventories WHERE sku_id = %d" % sku) == "t"


def all_inv():
    return one("SELECT string_agg(sku_id||'|'||total_stock||'|'||available_stock||'|'"
               "||locked_stock||'|'||sold_stock, ' ; ' ORDER BY sku_id) FROM inventories")


def counters():
    return dict(
        orders=int(one("SELECT count(*) FROM orders")),
        order_items=int(one("SELECT count(*) FROM order_items")),
        payments=int(one("SELECT count(*) FROM payments")),
        inventory_logs=int(one("SELECT count(*) FROM inventory_logs")),
        cart_items=int(one("SELECT count(*) FROM cart_items")),
    )


def adjust(tok, delta, reason="Day17 链路 E 验收"):
    st, b, raw = japi("POST", ADJUST, token=tok, body={"delta": delta, "reason": reason})
    return st, b.get("code"), b.get("message"), raw


def raw_adjust(tok, body):
    st, b, raw = japi("POST", ADJUST, token=tok, body=body)
    return st, b.get("code"), b.get("message"), raw


# ================================================================ main
def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 17 链路 E -- 管理端库存调整（★ 第四个写点 / 唯一改 total_stock 的一条）")
    say("target : %s%s" % (BASE, ADJUST))
    say("accounts: demo(C端) / op_order(ORDER_ADMIN) / op_product(PRODUCT_ADMIN) / admin(SUPER_ADMIN)")
    say("体例   : sku_id=%d ，用例 +5 → -3 → -2 归位，净变化 0" % SKU)
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base_inv = all_inv()
    b = inv()
    base_counts = counters()
    base_water = int(one("SELECT COALESCE(MAX(id),0) FROM inventory_logs"))
    say("  sku%d  %s" % (SKU, fmt(b)))
    say("  恒等式 = %s ；inventory_logs 水位线 = id>%d" % (identity(), base_water))
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base_counts.items())))
    chk("基线：库存四格可读", b is not None, "")
    chk("基线：恒等式成立", identity(), "")
    baseline = dict(b)
    say("  ★ 基线快照 = %s" % fmt(baseline))

    # ---------------------------------------------------------- [1] anonymous
    say("\n[1] 匿名 POST %s" % ADJUST)
    st, b_, raw = japi("POST", ADJUST, body={"delta": 1, "reason": "匿名"})
    say("  http=%s code=%s %s" % (st, b_.get("code"), short(raw, 120)))
    say("  ★ Security 层（过滤器）写响应 ⇒ 真 HTTP 401，不是 body.code")
    chk("匿名被拒，且是真 HTTP 401", st == 401, "http=%s" % st)

    # ---------------------------------------------------------- [2] login
    say("\n[2] 登录四个身份（token 只在内存里，不落盘）")

    def login(path, u, p):
        st_, b2, _ = japi("POST", path, body={"username": u, "password": p})
        return (b2.get("data") or {}).get("token"), b2.get("code")

    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_o_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    op_p_t, c3 = login("/api/auth/admin/login", "op_product", "prod123456")
    adm_t, c4 = login("/api/auth/admin/login", "admin", "admin123")
    for nm, c, t in (("demo", c1, demo_t), ("op_order", c2, op_o_t),
                     ("op_product", c3, op_p_t), ("admin", c4, adm_t)):
        say("  %-11s code=%s token_len=%d" % (nm, c, len(t or "")))
    chk("四个身份全部登录成功", all([demo_t, op_o_t, op_p_t, adm_t]),
        "op_product 缺失请先跑 day17-fixture-apply.py")
    if not all([demo_t, op_o_t, op_p_t, adm_t]):
        say("\nABORT: 缺 token")
        flush()
        return 1

    # ---------------------------------------------------------- [3] 权限矩阵
    say("\n[3] ★ 权限矩阵（先做被拒的两个 —— 顺便证明「被拒 = 零副作用」）")
    before_403 = all_inv()

    st, raw = api("POST", ADJUST, token=demo_t, body={"delta": 1, "reason": "越权"})
    say("  demo(C 端 token)      http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    chk("C 端 token 被拒，且是真 HTTP 403", st == 403, "http=%s" % st)

    st, raw = api("POST", ADJUST, token=op_o_t, body={"delta": 1, "reason": "越权"})
    say("  op_order(ORDER_ADMIN) http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    say("     ★ 它有 order:* 但【故意没有】inventory:adjust ⇒ 应该 403")
    chk("★ op_order（无 inventory:adjust）被拒：真 HTTP 403", st == 403, "http=%s" % st)

    chk("★ 两次被拒【零副作用】：库存逐字节未动", all_inv() == before_403,
        "变了 → 说明校验发生在写库之后")

    # ---------------------------------------------------------- [4] delta = 0
    say("\n[4] delta = 0 → 业务规则拒绝（Service 手工判，不在 DTO 上）")
    st, code, msg, raw = adjust(op_p_t, 0)
    say("  http=%s code=%s message=%s" % (st, code, msg))
    chk("delta=0 → body.code=400「调整量不能为 0」", code == 400 and "调整量不能为 0" in (msg or ""),
        "code=%s msg=%s" % (code, msg))

    # ---------------------------------------------------------- [5] DTO 校验
    say("\n[5] DTO 格式校验（@NotNull / @NotBlank / @Size）")
    st, code, msg, raw = raw_adjust(op_p_t, {"reason": "缺 delta"})
    say("  delta 缺失          http=%s code=%s message=%s" % (st, code, msg))
    chk("delta=null → 400", code == 400, "code=%s" % code)

    st, code, msg, raw = raw_adjust(op_p_t, {"delta": 1, "reason": ""})
    say("  reason 空串         http=%s code=%s message=%s" % (st, code, msg))
    chk("reason 空白 → 400", code == 400, "code=%s" % code)

    st, code, msg, raw = raw_adjust(op_p_t, {"delta": 1})
    say("  reason 缺失         http=%s code=%s message=%s" % (st, code, msg))
    chk("reason=null → 400", code == 400, "code=%s" % code)

    st, code, msg, raw = raw_adjust(op_p_t, {"delta": 1, "reason": "x" * 201})
    say("  reason 201 字       http=%s code=%s %s" % (st, code, short(msg or "", 80)))
    chk("reason 超 200 字 → 400", code == 400, "code=%s" % code)

    # ---------------------------------------------------------- [6] 不存在的 SKU
    say("\n[6] SKU 不存在（999999）→ 同样是 400，不是 404 / 500")
    st, b2, raw = japi("POST", "/api/admin/inventory/skus/999999/adjust",
                       token=op_p_t, body={"delta": 1, "reason": "不存在"})
    say("  http=%s code=%s message=%s" % (st, b2.get("code"), b2.get("message")))
    say("  ★ 守卫在 WHERE 里 ⇒ 影响 0 行 ⇒ RETURNING 空手 ⇒ null ⇒ 400")
    say("    本接口【不区分】「SKU 不存在」与「调成负的」—— 两者都只是「这个调整不成立」")
    chk("SKU 不存在 → body.code=400（不是 404 / 500）", b2.get("code") == 400,
        "code=%s" % b2.get("code"))

    # ---------------------------------------------------------- [7] 正补货 +5
    say("\n[7] ★ 正补货 delta=+5（op_product）")
    before = inv()
    st, code, msg, raw = adjust(op_p_t, 5)
    after = inv()
    say("  http=%s code=%s message=%s" % (st, code, msg))
    say("  %s  →  %s" % (fmt(before), fmt(after)))
    chk("+5 → 200 + code 200", code == 200, "code=%s" % code)
    chk("★ total  +5（100→105）", after["total"] == before["total"] + 5,
        "%d→%d" % (before["total"], after["total"]))
    chk("★ available +5（同向同量）", after["available"] == before["available"] + 5,
        "%d→%d" % (before["available"], after["available"]))
    chk("★ locked 一格未动", after["locked"] == before["locked"], "")
    chk("★ sold   一格未动", after["sold"] == before["sold"], "")
    chk("恒等式仍成立", identity(), "")

    # ---------------------------------------------------------- [8] 正报损 -3
    say("\n[8] ★ 正报损 delta=-3")
    before = inv()
    st, code, msg, raw = adjust(op_p_t, -3)
    after = inv()
    say("  http=%s code=%s message=%s" % (st, code, msg))
    say("  %s  →  %s" % (fmt(before), fmt(after)))
    chk("-3 → 200 + code 200", code == 200, "code=%s" % code)
    chk("★ total  -3", after["total"] == before["total"] - 3, "")
    chk("★ available -3（同向同量）", after["available"] == before["available"] - 3, "")
    chk("★ locked / sold 一格未动",
        after["locked"] == before["locked"] and after["sold"] == before["sold"], "")

    # ---------------------------------------------------------- [9] 守卫挡下
    say("\n[9] ★ 守卫挡下：delta = -(available+1) → 调整后为负")
    cur = inv()
    bad = -(cur["available"] + 1)
    st, code, msg, raw = adjust(op_p_t, bad)
    say("  当前 avail=%d ，提交 delta=%d" % (cur["available"], bad))
    say("  http=%s code=%s message=%s" % (st, code, msg))
    chk("★ 调整后为负 → 400（用户可理解的业务结果，不是 500）",
        code == 400 and "不能为负" in (msg or ""), "code=%s msg=%s" % (code, msg))
    chk("★ 被守卫挡下【零副作用】：库存逐字节未动", inv() == cur, "%s → %s" % (fmt(cur), fmt(inv())))
    say("  对照：moveLockedToSold / releaseLocked 的 0 行是【账目不一致】→ 500；")
    say("        这里的 0 行是【管理员填了个太大的负数】→ 400。同为 0 行，语义不同。")

    # ---------------------------------------------------------- [10] 流水
    say("\n[10] ★ 流水核对（id > %d 的 ADMIN_ADJUST；此刻【还没做还原】）" % base_water)
    raw_logs = psql("SELECT id||'|'||type||'|'||change_quantity||'|'||before_stock||'|'"
                    "||after_stock||'|'||COALESCE(reference_id::text,'NULL')||'|'||sku_id"
                    " FROM inventory_logs WHERE id > %d AND type='ADMIN_ADJUST' ORDER BY id" % base_water)
    rows = []
    for line in raw_logs.splitlines():
        if not line.strip():
            continue
        p = line.split("|")
        rows.append(dict(id=int(p[0]), type=p[1], change=int(p[2]), before=int(p[3]),
                         after=int(p[4]), ref=p[5], sku=int(p[6])))
    say("  本次新增 %d 条：" % len(rows))
    for r in rows:
        say("    id=%-4d type=%-13s change=%-5d before=%-4d after=%-4d ref=%-4s sku=%d"
            % (r["id"], r["type"], r["change"], r["before"], r["after"], r["ref"], r["sku"]))
    chk("★ 已成功的两次调整各落一条流水 ⇒ 此刻恰好 2 条（还原那次还没发生）",
        len(rows) == 2, "实得 %d" % len(rows))
    chk("★ 每条 change == after - before（恒等式由 writeLog 构造保证，不可能写歪）",
        all(r["change"] == r["after"] - r["before"] for r in rows),
        "" if all(r["change"] == r["after"] - r["before"] for r in rows) else "有反例")
    chk("★ change 序列 == [+5, -3]", [r["change"] for r in rows] == [5, -3],
        "实得 %s" % [r["change"] for r in rows])
    chk("★ 全部 type=ADMIN_ADJUST", all(r["type"] == "ADMIN_ADJUST" for r in rows), "")
    chk("★ 全部 reference_id IS NULL（管理端调整【本来就没有】关联订单，不是「拿不到」）",
        all(r["ref"] == "NULL" for r in rows),
        "实得 %s" % [r["ref"] for r in rows])
    chk("★ 全部 sku_id=%d" % SKU, all(r["sku"] == SKU for r in rows), "")
    chk("★ Σ(change) == Δtotal（这对账式只有本类型成立，其余三条改的是「货归哪一格」）",
        sum(r["change"] for r in rows) == inv()["total"] - baseline["total"],
        "Σ=%d Δtotal=%d" % (sum(r["change"] for r in rows), inv()["total"] - baseline["total"]))

    # ---------------------------------------------------------- [11] 还原
    say("\n[11] ★ 还原到基线（+5 → -3 的净额是 +2，所以补一次 -2）")
    st, code, msg, raw = adjust(op_p_t, -2, "Day17 验收还原")
    say("  http=%s code=%s message=%s" % (st, code, msg))
    chk("还原调用成功", code == 200, "code=%s" % code)

    # ---------------------------------------------------------- [12] 终局对账
    say("\n[12] ★ 终局对账（库存四格）")
    fin = inv()
    say("  基线 %s" % fmt(baseline))
    say("  终局 %s" % fmt(fin))
    chk("★ sku%d 四格【逐字段】回基线" % SKU, fin == baseline, "%s vs %s" % (fmt(fin), fmt(baseline)))
    chk("★ 7 个 SKU 库存整体逐字节回基线", all_inv() == base_inv, "")
    chk("恒等式成立", identity(), "")

    # ---------------------------------------------------------- [13] 清理
    say("\n[13] ★ CLEANUP —— 回收本次产生的流水")
    say("  DELETE FROM inventory_logs WHERE id > %d" % base_water)
    say("  ★ 生产里流水表是【只增不改不删】的；但验收脚本必须把数据库放回基线 ——")
    say("    这与 day14 / day15 / day16 / day17-C 四个脚本的收尾完全一致：")
    say("    同一句话、同一「全表 max(id) 水位线」约定。不收，M1 回归就报 BASELINE RESTORED: NO。")
    psql("DELETE FROM inventory_logs WHERE id > %d" % base_water)
    say("  清理后 inventory_logs = %d （基线 %d）"
        % (int(one("SELECT count(*) FROM inventory_logs")), base_counts["inventory_logs"]))

    fin_counts = counters()
    say("\n  五项 counters 终局 vs 基线：")
    for k in sorted(base_counts):
        say("    %-14s %d → %d  (Δ=%+d)"
            % (k, base_counts[k], fin_counts[k], fin_counts[k] - base_counts[k]))
    chk("★ 五项 counters 全部回基线（含 inventory_logs）",
        all(fin_counts[k] == base_counts[k] for k in base_counts),
        "; ".join("%s Δ%+d" % (k, fin_counts[k] - base_counts[k])
                  for k in sorted(base_counts) if fin_counts[k] != base_counts[k]))
    say("  ★ 这是 day17-m1-regression.py 能给出 BASELINE RESTORED: YES 的前提")

    # ---------------------------------------------------------- 汇总
    passed = sum(1 for _, ok, _ in checks if ok)
    say("\n" + "=" * 78)
    bad = [(n, d) for n, ok, d in checks if not ok]
    if bad:
        say("FAILED %d 项：" % len(bad))
        for n, d in bad:
            say("  [FAIL] %s   %s" % (n, d))
    say("RESULT: %d/%d PASS" % (passed, len(checks)))
    say("VERDICT: %s" % ("ALL GREEN" if passed == len(checks) else "HAS FAILURES"))
    say("=" * 78)
    flush()
    print("\n".join(_lines))
    return 0 if passed == len(checks) else 2


if __name__ == "__main__":
    sys.exit(main())
