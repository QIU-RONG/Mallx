# -*- coding: utf-8 -*-
"""
Day 46 -- 退款 / 售后链路：仅退款 + 退货退款 + 负向支付流水。

为什么这一块要单独验收
----------------------
此前项目只有【正向】链路：下单 -> 支付 -> 发货 -> 收货 -> 评价。
付过钱之后想把钱要回来，系统里没有任何路径 —— 这是业务闭环上最后一个洞。
本脚本把两条逆向路径一次跑完：

    REFUND_ONLY   订单未发货   APPLIED -> APPROVED -------------------> SUCCESS
    RETURN_REFUND 订单已发货   APPLIED -> APPROVED -> RETURNING -> REFUNDING -> SUCCESS

★ 两条路径的差别不是「多两个状态」，而是【有没有实物要从买家手里回到仓库】。
  没有实物要寄回时，中间那两段根本无从发生 —— 所以类型与订单状态的匹配
  是本模块最重要的一条业务规则，[2][3] 两节各断言一次「选错类型 = 400」。

★★「执行退款」是全项目唯一会动钱的动作，一次性写五张表：
    refunds  -> SUCCESS   （CAS 抢资格，★ 必须是第一步）
    orders   -> REFUNDED  （CAS；REFUNDED 不在它的起点集合里 ⇒ 退不了第二次）
    inventories            sold -> available（第五个库存写点，写 REFUND_RETURN 流水）
    user_coupons           退这一单用掉的券（0 行 = 没用券，正常）
    payments               写一笔【负数】流水（对账退化成 SUM(amount)）

对账式（本脚本的核心判据）
--------------------------
  · 库存守恒：total = available + locked + sold，退款后【逐格】回到下单前
  · 资金守恒：同一 order_id 的 SUM(payments.amount) == 0（收一笔 + 退一笔）
  · 流水类型：回补走的是 REFUND_RETURN 而不是 CANCEL_RELEASE（分岔点 = 付没付过钱）

★ 反向断言（本脚本的区分度全靠这些「不该成功」的用例）：
  · 未发货选退货退款 / 已发货选仅退款        -> 400
  · 退货退款【没收货】就执行退款              -> 400（堵在 SQL 的 WHERE 里）
  · 同一订单重复申请 / 重复退款               -> 400
  · C 端 token 打管理端接口                   -> 真 HTTP 403
  · 商品管理员（role 2）打审核接口             -> 真 HTTP 403（★ 反向对照：不给 role 2）
  · 别人的售后单                              -> 404（与「不存在」不可区分）

可重跑 + 自清理
---------------
只操作自己新建的行（id > 高水位线），跑完在 finally 里删干净，
最后逐格比对库存指纹与开头完全一致。

Usage:
    python day46-refund-verify.py
Report: day46-refund-verify-report.txt
"""
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080"
# ★ 可移植性（CI 跑在 Linux）：MALLX_DOCKER 覆盖本机路径
DOCKER = os.environ.get("MALLX_DOCKER") or \
    r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
TARGET_SKU = 4          # MATE80-BLK-512 @ 6999.00
ADDRESS_ID = 2          # demo 的默认地址
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day46-refund-verify-report.txt")

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=60):
    """★ 必须禁代理：系统代理会把 127.0.0.1 也拦下（报 502，看着像服务挂了）。"""
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
    except Exception as e:                                            # noqa: BLE001
        return -1, '{"transport_error": "%s"}' % repr(e)


def japi(method, path, token=None, body=None):
    st, raw = api(method, path, token, body)
    try:
        return st, json.loads(raw), raw
    except ValueError:
        return st, {"raw": raw}, raw


def code_of(raw):
    """★ 业务失败是「HTTP 200 + body.code」，判成功必须看 code。"""
    try:
        return json.loads(raw).get("code")
    except ValueError:
        return None


# ---------------------------------------------------------------- db helpers
def psql(sql):
    """★ stderr 必须暴露：只看 stdout 时 SQL 错误会伪装成「没数据」。"""
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed (rc=%d)\nSQL: %s\nstderr: %s"
                           % (p.returncode, sql, err))
    return out


def one(sql):
    """⚠️ docker exec 回传的行尾带 \\r —— 不 strip 会比对为假。"""
    return psql(sql).strip()


def psql_try(sql):
    """★【预期会失败】的 SQL：不抛异常，返回 (ok, stderr)。

    ★★ 为什么必须有这个函数：唯一索引那层防线在【并发】下才起作用，
       而并发是否真的撞上是概率性的（本机 8 线程跑下来全是 SELECT 拦的）。
       ⇒ 概率性路径不能当唯一证据，必须有一条【确定性】的 SQL 层断言。
    """
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    err = p.stderr.decode("utf-8", "replace")
    return (p.returncode == 0 and "ERROR" not in err), err


def all_inv():
    out = one("SELECT sku_id||'|'||total_stock||'|'||available_stock||'|'"
              "||locked_stock||'|'||sold_stock FROM inventories ORDER BY sku_id")
    rows = {}
    for line in out.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) == 5:
            rows[int(p[0])] = dict(total=int(p[1]), available=int(p[2]),
                                   locked=int(p[3]), sold=int(p[4]))
    return rows


def inv(sku):
    return all_inv()[sku]


def inv_line(tag, sku, r):
    return "  %-22s sku%d  total=%3d  available=%3d  locked=%3d  sold=%3d  identity=%s" % (
        tag, sku, r["total"], r["available"], r["locked"], r["sold"],
        "OK" if r["total"] == r["available"] + r["locked"] + r["sold"] else "BROKEN")


def stock_delta(a, b):
    return "available %+d  locked %+d  sold %+d" % (
        b["available"] - a["available"], b["locked"] - a["locked"], b["sold"] - a["sold"])


def status_of(order_id):
    return one("SELECT status FROM orders WHERE id=%d" % order_id) or "(missing)"


def pay_amount_of(order_id):
    return one("SELECT pay_amount FROM orders WHERE id=%d" % order_id).strip()


def refund_row(rid):
    out = one("SELECT status||'|'||type||'|'||coalesce(amount::text,'-')||'|'"
              "||coalesce(tracking_no,'-')||'|'"
              "||coalesce(to_char(applied_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(audited_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(shipped_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(received_at,'HH24:MI:SS'),'-')||'|'"
              "||coalesce(to_char(refunded_at,'HH24:MI:SS'),'-')"
              " FROM refunds WHERE id=%d" % rid)
    p = [x.strip() for x in out.split("|")]
    if len(p) != 9:
        return None
    return dict(status=p[0], type=p[1], amount=p[2], tracking_no=p[3],
                applied_at=p[4], audited_at=p[5], shipped_at=p[6],
                received_at=p[7], refunded_at=p[8])


def short(raw, n=150):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


class _Abort(Exception):
    """提前退出但仍跑 finally 的清理、仍写报告。"""


# ================================================================ main
def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))
        return bool(good)

    say("=" * 78)
    say("Day 46 -- 退款 / 售后链路（仅退款 + 退货退款 + 负向支付流水）")
    say("target : %s   accounts: demo(1) / admin(1) / op_order(2) / op_product(3) / intruder(2)"
        % BASE)
    say("sku under test: %d" % TARGET_SKU)
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE")
    base_all = all_inv()
    base = base_all[TARGET_SKU]
    hw_logs = int(one("SELECT coalesce(max(id),0) FROM inventory_logs"))
    hw_refunds = int(one("SELECT coalesce(max(id),0) FROM refunds"))
    hw_pay = int(one("SELECT coalesce(max(id),0) FROM payments"))
    hw_orders = int(one("SELECT coalesce(max(id),0) FROM orders"))
    say(inv_line("baseline", TARGET_SKU, base))
    say("  high-water: inventory_logs=%d refunds=%d payments=%d orders=%d"
        % (hw_logs, hw_refunds, hw_pay, hw_orders))
    chk("baseline: every SKU satisfies total = available + locked + sold",
        all(r["total"] == r["available"] + r["locked"] + r["sold"] for r in base_all.values()))

    # ---------------------------------------------------------- [1] logins
    say("\n[1] logins (tokens in memory only)")
    toks = {}

    def login(path, user, pwd):
        st, b, raw = japi("POST", path, body={"username": user, "password": pwd})
        t = (b.get("data") or {}).get("token")
        say("  %-10s http=%s code=%s token_len=%d" % (user, st, b.get("code"), len(t or "")))
        return t

    toks["demo"] = login("/api/auth/login", "demo", "demo123")
    toks["intruder"] = login("/api/auth/login", "intruder", "intruder")
    toks["admin"] = login("/api/auth/admin/login", "admin", "admin123")
    toks["op_order"] = login("/api/auth/admin/login", "op_order", "op123456")
    toks["op_product"] = login("/api/auth/admin/login", "op_product", "prod123456")

    for k in ("demo", "admin", "op_order", "op_product", "intruder"):
        chk("login %s succeeded" % k, bool(toks[k]))
    if not toks["demo"] or not toks["admin"]:
        say("\nABORT: demo / admin token required")
        flush()
        return 1

    created_orders = []
    created_refunds = []

    try:
        # ------------------------------------------------ helpers
        def cart_all():
            _, b, _ = japi("GET", "/api/cart", token=toks["demo"])
            return (b.get("data") or {}).get("items") or []

        def cart_find(sku):
            for it in cart_all():
                if it.get("skuId") == sku:
                    return it
            return None

        def select_only(item_id):
            for it in cart_all():
                want = (it["id"] == item_id)
                if bool(it.get("selected")) != want:
                    japi("PUT", "/api/cart/%s/selected" % it["id"], token=toks["demo"],
                         body={"selected": want})

        def place_order(qty=1):
            it = cart_find(TARGET_SKU)
            if it is None:
                japi("POST", "/api/cart", token=toks["demo"],
                     body={"skuId": TARGET_SKU, "quantity": qty})
                it = cart_find(TARGET_SKU)
            japi("PUT", "/api/cart/%s" % it["id"], token=toks["demo"], body={"quantity": qty})
            select_only(it["id"])
            st, b, raw = japi("POST", "/api/orders", token=toks["demo"],
                              body={"addressId": ADDRESS_ID})
            oid = b.get("data") if isinstance(b.get("data"), int) else None
            return oid, b.get("code"), raw

        def pay(oid):
            return japi("POST", "/api/payments", token=toks["demo"],
                        body={"orderId": oid, "method": "ALIPAY"})

        def ship(oid):
            return japi("POST", "/api/orders/%d/ship" % oid, token=toks["admin"])

        def apply_refund(oid, rtype, reason="不想要了"):
            return japi("POST", "/api/refunds", token=toks["demo"],
                        body={"orderId": oid, "type": rtype, "reason": reason})

        def admin_post(path, who="admin", body=None):
            return japi("POST", path, token=toks[who], body=body)

        # ================================================================
        say("\n" + "-" * 78)
        say("ORDER A -- 仅退款（REFUND_ONLY）：付了钱、还没发货")
        say("-" * 78)

        oid_a, c, raw = place_order()
        say("\n[A1] place + pay order A -> id=%s code=%s" % (oid_a, c))
        chk("A: order created", isinstance(oid_a, int))
        if not isinstance(oid_a, int):
            say("ABORT: " + short(raw))
            raise _Abort()
        created_orders.append(oid_a)
        stp, bp, _ = pay(oid_a)
        say("     pay -> http=%s code=%s status=%s" % (stp, bp.get("code"), status_of(oid_a)))
        chk("A: order paid -> PAID", status_of(oid_a) == "PAID")
        amt_a = pay_amount_of(oid_a)
        say("     pay_amount = %s" % amt_a)

        say("\n[A2] 选错类型：订单未发货却申请【退货退款】 -> 期望 400")
        st, b, raw = apply_refund(oid_a, "RETURN_REFUND")
        say("     http=%s code=%s %s" % (st, b.get("code"), short(raw, 110)))
        chk("A2: 未发货选退货退款 -> code 400", code_of(raw) == 400)
        chk("A2: 消息指明该选【仅退款】", "仅退款" in (b.get("msg") or raw))

        say("\n[A3] 正确类型：申请【仅退款】")
        st, b, raw = apply_refund(oid_a, "REFUND_ONLY")
        rid_a = b.get("data") if isinstance(b.get("data"), int) else None
        say("     http=%s code=%s refundId=%s" % (st, b.get("code"), rid_a))
        chk("A3: 仅退款申请成功", isinstance(rid_a, int))
        created_refunds.append(rid_a)
        r = refund_row(rid_a)
        say("     db: status=%s type=%s amount=%s applied_at=%s"
            % (r["status"], r["type"], r["amount"], r["applied_at"]))
        chk("A3: 落库 status=APPLIED", r["status"] == "APPLIED")
        chk("A3: amount = 订单实付快照 %s" % amt_a, r["amount"].rstrip("0").rstrip(".") ==
            amt_a.rstrip("0").rstrip(".") or float(r["amount"]) == float(amt_a))
        chk("A3: applied_at 已写（业务时间戳不挂 fill）", r["applied_at"] != "-")

        say("\n[A4] 重复申请 -> 期望 400（同一订单只能有一张进行中的售后单）")
        st, b, raw = apply_refund(oid_a, "REFUND_ONLY")
        say("     http=%s code=%s %s" % (st, b.get("code"), short(raw, 110)))
        chk("A4: 重复申请 -> code 400", code_of(raw) == 400)

        say("\n[A5] IDOR：intruder 看 demo 的售后单 -> 404（与「不存在」不可区分）")
        st, b, raw = japi("GET", "/api/refunds/%d" % rid_a, token=toks["intruder"])
        say("     http=%s code=%s" % (st, b.get("code")))
        chk("A5: 非本人 -> code 404", code_of(raw) == 404)
        st2, b2, raw2 = japi("GET", "/api/refunds/999999", token=toks["demo"])
        chk("A5: 不存在同样是 404（两条响应不可区分）",
            code_of(raw2) == 404 and (b2.get("msg") == b.get("msg")))

        say("\n[A6] 管理端审核通过（op_order = 订单管理员，role 3）")
        st, b, raw = admin_post("/api/admin/refunds/%d/approve" % rid_a, "op_order")
        say("     http=%s code=%s" % (st, b.get("code")))
        chk("A6: op_order 审核通过 -> 200/code 200", code_of(raw) == 200)
        r = refund_row(rid_a)
        say("     db: status=%s audited_at=%s" % (r["status"], r["audited_at"]))
        chk("A6: APPLIED -> APPROVED", r["status"] == "APPROVED")
        chk("A6: audited_at 已写", r["audited_at"] != "-")

        say("\n[A7] ★★ 执行退款（唯一会动钱的那一步）")
        before = inv(TARGET_SKU)
        say(inv_line("  before refund", TARGET_SKU, before))
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_a, "op_order")
        say("     http=%s code=%s" % (st, b.get("code")))
        chk("A7: 执行退款成功", code_of(raw) == 200)
        after = inv(TARGET_SKU)
        say(inv_line("  after  refund", TARGET_SKU, after))
        say("     delta: %s" % stock_delta(before, after))

        r = refund_row(rid_a)
        say("     db refunds: status=%s refunded_at=%s" % (r["status"], r["refunded_at"]))
        chk("A7: refunds -> SUCCESS", r["status"] == "SUCCESS")
        chk("A7: refunded_at 已写", r["refunded_at"] != "-")
        chk("A7: orders -> REFUNDED", status_of(oid_a) == "REFUNDED")
        chk("A7: orders.refunded_at 已写",
            one("SELECT coalesce(to_char(refunded_at,'HH24:MI:SS'),'-') FROM orders WHERE id=%d"
                % oid_a) != "-")
        chk("A7: 库存 sold -1（★ 不是 locked：付过钱了）", after["sold"] == before["sold"] - 1)
        chk("A7: 库存 available +1", after["available"] == before["available"] + 1)
        chk("A7: 库存 total 不变（守恒式没破）", after["total"] == before["total"])

        say("\n[A8] 库存流水：回补必须记 REFUND_RETURN，不是 CANCEL_RELEASE")
        lg = one("SELECT type||'|'||change_quantity||'|'||coalesce(reference_id::text,'-')"
                 " FROM inventory_logs WHERE id > %d AND sku_id=%d ORDER BY id"
                 % (hw_logs, TARGET_SKU))
        say("     new logs: %s" % (lg or "(none)"))
        chk("A8: 有一条 REFUND_RETURN 流水，change=+1", "REFUND_RETURN|1" in lg)
        chk("A8: 流水 reference_id = 订单 %d" % oid_a, ("|%d" % oid_a) in lg)
        chk("A8: 没有误记成 CANCEL_RELEASE", "CANCEL_RELEASE" not in lg)

        say("\n[A9] 资金对账：payments 里有一笔【负数】流水，净额归零")
        pays = one("SELECT amount::text||'|'||method||'|'||status FROM payments"
                   " WHERE id > %d AND order_id=%d ORDER BY id" % (hw_pay, oid_a))
        net = one("SELECT coalesce(sum(amount),0) FROM payments WHERE order_id=%d" % oid_a)
        say("     new payments: %s" % (pays or "(none)"))
        say("     SUM(amount) for order A = %s" % net)
        chk("A9: 新增一笔 REFUND/REFUNDED 流水", "REFUND|REFUNDED" in (pays or ""))
        chk("A9: 金额为负（-%s）" % amt_a, ("-%s" % amt_a) in (pays or ""))
        chk("A9: 该单资金净额 = 0（收一笔 + 退一笔）", float(net) == 0.0)

        say("\n[A10] 重复执行退款 -> 400（同一张单不可能退两次钱）")
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_a, "admin")
        say("     http=%s code=%s" % (st, b.get("code")))
        chk("A10: 重复退款 -> code 400", code_of(raw) == 400)

        # ================================================================
        say("\n" + "-" * 78)
        say("ORDER B -- 退货退款（RETURN_REFUND）：已发货，货要真的寄回来")
        say("-" * 78)

        oid_b, c, raw = place_order()
        say("\n[B1] place + pay + ship order B -> id=%s" % oid_b)
        chk("B: order created", isinstance(oid_b, int))
        if not isinstance(oid_b, int):
            say("ABORT: " + short(raw))
            raise _Abort()
        created_orders.append(oid_b)
        pay(oid_b)
        ship(oid_b)
        say("     status=%s" % status_of(oid_b))
        chk("B: order shipped -> SHIPPED", status_of(oid_b) == "SHIPPED")

        say("\n[B2] 选错类型：已发货却申请【仅退款】 -> 期望 400")
        st, b, raw = apply_refund(oid_b, "REFUND_ONLY")
        say("     http=%s code=%s %s" % (st, b.get("code"), short(raw, 110)))
        chk("B2: 已发货选仅退款 -> code 400", code_of(raw) == 400)
        chk("B2: 消息指明该选【退货退款】", "退货退款" in (b.get("msg") or raw))

        say("\n[B3] 申请【退货退款】-> APPLIED")
        st, b, raw = apply_refund(oid_b, "RETURN_REFUND", reason="尺码不合适")
        rid_b = b.get("data") if isinstance(b.get("data"), int) else None
        chk("B3: 退货退款申请成功", isinstance(rid_b, int))
        created_refunds.append(rid_b)
        say("     refundId=%s status=%s" % (rid_b, refund_row(rid_b)["status"]))

        say("\n[B4] 审核通过 -> APPROVED（此时还不能退钱：货还没寄回）")
        admin_post("/api/admin/refunds/%d/approve" % rid_b, "admin")
        chk("B4: -> APPROVED", refund_row(rid_b)["status"] == "APPROVED")

        say("\n[B5] ★★ 没收到货就执行退款 -> 期望 400（堵在 SQL 的 WHERE 里）")
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_b, "admin")
        say("     http=%s code=%s %s" % (st, b.get("code"), short(raw, 110)))
        chk("B5: 未收货执行退款 -> code 400", code_of(raw) == 400)

        say("\n[B6] 买家寄出（填物流单号）-> RETURNING")
        st, b, raw = japi("POST", "/api/refunds/%d/ship" % rid_b, token=toks["demo"],
                          body={"trackingNo": "SF1234567890"})
        say("     http=%s code=%s" % (st, b.get("code")))
        r = refund_row(rid_b)
        say("     db: status=%s tracking_no=%s shipped_at=%s"
            % (r["status"], r["tracking_no"], r["shipped_at"]))
        chk("B6: -> RETURNING", r["status"] == "RETURNING")
        chk("B6: tracking_no 落库", r["tracking_no"] == "SF1234567890")
        chk("B6: shipped_at 已写", r["shipped_at"] != "-")

        say("\n[B7] 执行退款仍应失败（已寄出但卖家没收货）-> 400")
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_b, "admin")
        chk("B7: 未收货 -> 仍然 code 400", code_of(raw) == 400)

        say("\n[B8] 卖家确认收货 -> REFUNDING")
        st, b, raw = admin_post("/api/admin/refunds/%d/receive" % rid_b, "admin")
        r = refund_row(rid_b)
        say("     http=%s code=%s status=%s received_at=%s"
            % (st, b.get("code"), r["status"], r["received_at"]))
        chk("B8: -> REFUNDING", r["status"] == "REFUNDING")
        chk("B8: received_at 已写", r["received_at"] != "-")

        say("\n[B9] ★★ 执行退款 -> SUCCESS + 五个写点")
        before_b = inv(TARGET_SKU)
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_b, "admin")
        after_b = inv(TARGET_SKU)
        say("     http=%s code=%s  delta: %s"
            % (st, b.get("code"), stock_delta(before_b, after_b)))
        chk("B9: 执行退款成功", code_of(raw) == 200)
        chk("B9: refunds -> SUCCESS", refund_row(rid_b)["status"] == "SUCCESS")
        chk("B9: orders -> REFUNDED", status_of(oid_b) == "REFUNDED")
        chk("B9: 库存 sold -1 / available +1 / total 不变",
            after_b["sold"] == before_b["sold"] - 1
            and after_b["available"] == before_b["available"] + 1
            and after_b["total"] == before_b["total"])
        net_b = one("SELECT coalesce(sum(amount),0) FROM payments WHERE order_id=%d" % oid_b)
        say("     SUM(amount) for order B = %s" % net_b)
        chk("B9: 资金净额 = 0", float(net_b) == 0.0)

        # ================================================================
        say("\n" + "-" * 78)
        say("ORDER C -- 撤销与拒绝：两条【不动钱】的终态")
        say("-" * 78)

        oid_c, c, raw = place_order()
        created_orders.append(oid_c)
        pay(oid_c)
        say("\n[C1] order C -> %s" % status_of(oid_c))
        st, b, raw = apply_refund(oid_c, "REFUND_ONLY")
        rid_c = b.get("data")
        created_refunds.append(rid_c)
        say("     apply -> refundId=%s" % rid_c)

        st, b, raw = japi("POST", "/api/refunds/%d/cancel" % rid_c, token=toks["demo"])
        say("     cancel -> http=%s code=%s status=%s"
            % (st, b.get("code"), refund_row(rid_c)["status"]))
        chk("C1: 撤销 -> CANCELLED", refund_row(rid_c)["status"] == "CANCELLED")

        say("\n[C2] 撤销后重新申请（终态不受部分唯一索引约束）")
        st, b, raw = apply_refund(oid_c, "REFUND_ONLY")
        rid_c2 = b.get("data") if isinstance(b.get("data"), int) else None
        created_refunds.append(rid_c2)
        say("     re-apply -> refundId=%s code=%s" % (rid_c2, b.get("code")))
        chk("C2: 撤销后可以重新申请", isinstance(rid_c2, int))

        say("\n[C3] 审核拒绝 -> REJECTED，且一分钱没动")
        before_c = inv(TARGET_SKU)
        # ★ 只调一次，且带上 remark —— 拒绝原因必须落库（买家要看得见为什么被拒）
        st, b, raw = japi("POST",
                          "/api/admin/refunds/%d/reject?remark=%s"
                          % (rid_c2, urllib.parse.quote("不支持7天无理由")),
                          token=toks["admin"])
        r = refund_row(rid_c2)
        remark_db = one("SELECT coalesce(remark,'-') FROM refunds WHERE id=%d" % rid_c2)
        say("     reject -> http=%s code=%s status=%s remark=%s"
            % (st, b.get("code"), r["status"], remark_db))
        chk("C3: -> REJECTED", r["status"] == "REJECTED")
        chk("C3: 拒绝原因落库（买家要看得见）", remark_db == "不支持7天无理由")
        chk("C3: 库存一格没动（拒绝不该动货）", inv(TARGET_SKU) == before_c)
        chk("C3: 订单状态没变（拒绝不该动订单）", status_of(oid_c) == "PAID")
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_c2, "admin")
        say("     rejected 后执行退款 -> http=%s code=%s" % (st, b.get("code")))
        chk("C3: 已拒绝的单执行退款 -> 400", code_of(raw) == 400)

        say("\n[C4] ★ 被拒之后还能重新申请（终态不受部分唯一索引约束）→ 最终还是退成了")
        st, b, raw = apply_refund(oid_c, "REFUND_ONLY", reason="重新申请：确实是质量问题")
        rid_c3 = b.get("data") if isinstance(b.get("data"), int) else None
        created_refunds.append(rid_c3)
        say("     re-apply after reject -> refundId=%s code=%s" % (rid_c3, b.get("code")))
        chk("C4: 被拒后可重新申请", isinstance(rid_c3, int))
        admin_post("/api/admin/refunds/%d/approve" % rid_c3, "admin")
        st, b, raw = admin_post("/api/admin/refunds/%d/refund" % rid_c3, "admin")
        say("     refund -> http=%s code=%s status=%s"
            % (st, b.get("code"), refund_row(rid_c3)["status"] if rid_c3 else "-"))
        chk("C4: 重新申请后能正常退款", code_of(raw) == 200)
        chk("C4: orders -> REFUNDED", status_of(oid_c) == "REFUNDED")
        net_c = one("SELECT coalesce(sum(amount),0) FROM payments WHERE order_id=%d" % oid_c)
        say("     SUM(amount) for order C = %s" % net_c)
        chk("C4: 资金净额 = 0", float(net_c) == 0.0)
        # ★ 到这里三张单全部 REFUNDED ⇒ 库存应当【逐格】回到下单前（无需人工补偿）

        # ================================================================
        say("\n" + "-" * 78)
        say("ORDER D -- ★ 并发申请：SELECT 那层防线在并发下必然失效，只能靠唯一索引")
        say("-" * 78)

        oid_d, c, raw = place_order()
        say("\n[D1] place + pay order D -> id=%s code=%s" % (oid_d, c))
        chk("D1: order created", isinstance(oid_d, int))
        if not isinstance(oid_d, int):
            say("ABORT: " + short(raw))
            raise _Abort()
        created_orders.append(oid_d)
        pay(oid_d)
        say("     status=%s" % status_of(oid_d))

        N = 8
        res = [None] * N
        gate = threading.Barrier(N)

        def worker(i):
            gate.wait()                       # ★ 尽量同时发起，别串行撞
            res[i] = apply_refund(oid_d, "REFUND_ONLY", reason="并发%d" % i)

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        codes = [code_of(r[2]) if r else None for r in res]
        ids = []
        for r in res:
            d = (r[1] or {}).get("data")
            if isinstance(d, int):
                ids.append(d)
        created_refunds.extend(ids)
        winners = sum(1 for x in codes if x == 200)
        say("     并发 %d 次 -> code 分布 = %s" % (N, sorted(str(x) for x in codes)))
        say("     拿到的 refundId = %s" % ids)
        active = int(one("SELECT count(*) FROM refunds WHERE order_id=%d "
                         "AND status IN ('APPLIED','APPROVED','RETURNING','REFUNDING')"
                         % oid_d))
        say("     DB 里该单进行中售后单数 = %d" % active)
        chk("F: 并发申请只有 1 张成功", winners == 1)
        chk("F: 其余全部业务失败 400（★ 不是 500：唯一冲突必须被翻译成业务失败）",
            all(x == 400 for x in codes if x != 200))
        chk("F: ★ DB 里该单只有 1 张进行中售后单（唯一索引那层防线真在干活）",
            active == 1)

        # 收尾：把这张赢下来的单退掉，库存才能回到基线
        if ids:
            admin_post("/api/admin/refunds/%d/approve" % ids[0], "admin")
            admin_post("/api/admin/refunds/%d/refund" % ids[0], "admin")
            say("     收尾退款 -> status=%s orders=%s"
                % (refund_row(ids[0])["status"], status_of(oid_d)))
            chk("F: 收尾后订单 -> REFUNDED", status_of(oid_d) == "REFUNDED")

        # ================================================================
        say("\n[G] ★ 部分唯一索引：直接对着数据库验（确定性，不靠并发撞运气）")
        say("    并发那条 F 只能证明「没炸」，证明不了「是谁拦的」；这一节才是硬证据。")

        def ins(status, tag):
            return psql_try(
                "INSERT INTO refunds (refund_no, order_id, user_id, type, status, amount,"
                " applied_at) VALUES ('RF-G-%s', %d, 1, 'REFUND_ONLY', '%s', 1.00,"
                " CURRENT_TIMESTAMP)" % (tag, oid_d, status))

        ok1, _ = ins("APPLIED", "g1")
        ok2, err2 = ins("APPLIED", "g2")
        ok3, err3 = ins("CANCELLED", "g3")
        say("     APPLIED#1=%s  APPLIED#2=%s  CANCELLED=%s" % (ok1, ok2, ok3))
        if not ok2:
            say("     g2 报错摘要: %s" % (err2 or "").strip().splitlines()[0:1])
        chk("G: 第一张「进行中」售后单可插入", ok1)
        chk("G: ★ 第二张「进行中」被唯一索引挡住（并发不变式由数据库守）", not ok2)
        chk("G: 报错点名 uk_refunds_active_order（不是别的约束误伤）",
            "uk_refunds_active_order" in (err2 or ""))
        chk("G: ★ 已终结的（CANCELLED）照样能插 —— 证明它是【部分】索引", ok3)

        # ================================================================
        say("\n" + "-" * 78)
        say("[D] 权限矩阵：谁不能碰售后（★ 区分度全靠「谁没有」）")
        say("-" * 78)
        st, b, raw = japi("GET", "/api/admin/refunds", token=toks["demo"])
        say("  D1 C 端 token -> GET /api/admin/refunds  http=%s" % st)
        chk("D1: C 端 token 打管理端 -> 真 HTTP 403", st == 403)

        st, b, raw = japi("GET", "/api/admin/refunds", token=toks["op_order"])
        say("  D2 op_order(role3) -> http=%s code=%s" % (st, b.get("code")))
        chk("D2: 订单管理员能看售后列表", st == 200 and code_of(raw) == 200)

        target = rid_c2 if refund_row(rid_c2)["status"] != "APPLIED" else rid_c
        st, b, raw = japi("POST", "/api/admin/refunds/%d/approve" % target,
                          token=toks["op_product"])
        say("  D3 op_product(role2) -> approve http=%s" % st)
        chk("D3: 商品管理员打审核 -> 真 HTTP 403（★ 反向对照：不给 role 2）", st == 403)

        st, b, raw = japi("GET", "/api/refunds/my", token=toks["demo"])
        mine = (b.get("data") or {}).get("records") or (b.get("data") or {}).get("list") or []
        say("  D4 demo 我的售后单数 = %d" % len(mine))
        chk("D4: 我的售后单列表非空", len(mine) >= 3)
        st, b, raw = japi("GET", "/api/refunds/my", token=toks["intruder"])
        others = (b.get("data") or {}).get("records") or (b.get("data") or {}).get("list") or []
        say("  D5 intruder 我的售后单数 = %d" % len(others))
        chk("D5: 别人的售后单不出现在我的列表里", len(others) == 0)

    except _Abort:
        pass
    except Exception as e:                                            # noqa: BLE001
        say("\n!! EXCEPTION: %r" % (e,))
        chk("脚本未抛异常", False)

    finally:
        # ---------------------------------------------------------- cleanup
        say("\n" + "-" * 78)
        say("[E] CLEANUP + baseline re-check")
        say("-" * 78)
        try:
            if created_refunds:
                ids = ",".join(str(x) for x in created_refunds if x)
                psql("DELETE FROM refunds WHERE id IN (%s)" % ids)
            if created_orders:
                oids = ",".join(str(x) for x in created_orders if x)
                # ★★ 自愈：还停在「货已售出」状态的单必须先退货再删
                #     —— 直接 DELETE FROM orders 会把 sold 那格永久留在库里
                #       （Day 46 首跑踩过：订单 C 走到 REJECTED 没退款，
                #        cleanup 却把订单删了 ⇒ sku4 sold 永远多 1，
                #        day15 / day16 的「sold == PAID+SHIPPED+COMPLETED」守恒式各红 2 条）。
                #     ★ 脚本中途 abort 时这一步是唯一能挡住污染的东西。
                for oid in [x for x in created_orders if x]:
                    stt = one("SELECT coalesce(max(status),'-') FROM orders "
                              "WHERE id=%d" % oid)
                    if stt not in ("PAID", "SHIPPED", "COMPLETED"):
                        continue
                    say("  !! order %s 仍处于 %s —— 删除前先把货退回去" % (oid, stt))
                    for row in psql("SELECT sku_id||'|'||quantity FROM order_items "
                                    "WHERE order_id=%d" % oid).splitlines():
                        sku, qty = [int(v) for v in row.split("|")[:2]]
                        psql("UPDATE inventories SET sold_stock = sold_stock - %d, "
                             "available_stock = available_stock + %d, "
                             "updated_at = CURRENT_TIMESTAMP WHERE sku_id = %d"
                             % (qty, qty, sku))
                # ★ 并发那节可能造出「返回了 500 但库里已插入」的孤儿单，
                #   只按 id 删会漏 —— 再按 order_id 兜一遍
                psql("DELETE FROM refunds WHERE order_id IN (%s)" % oids)
                psql("DELETE FROM payments WHERE order_id IN (%s)" % oids)
                psql("DELETE FROM order_items WHERE order_id IN (%s)" % oids)
                psql("DELETE FROM orders WHERE id IN (%s)" % oids)
            psql("DELETE FROM inventory_logs WHERE id > %d" % hw_logs)
            psql("DELETE FROM payments WHERE id > %d" % hw_pay)
            say("  deleted refunds=%s orders=%s" % (created_refunds, created_orders))
        except Exception as e:                                        # noqa: BLE001
            say("  !! cleanup failed: %r" % (e,))

        final = all_inv()
        say(inv_line("final", TARGET_SKU, final[TARGET_SKU]))
        say("  delta vs baseline: %s" % stock_delta(base, final[TARGET_SKU]))
        same = all(final[k] == base_all[k] for k in base_all)
        chk("★ 库存逐格回到基线（退款是支付+下单的严格逆操作）", same)
        chk("清理后 refunds 无残留",
            int(one("SELECT count(*) FROM refunds WHERE id > %d" % hw_refunds)) == 0)
        chk("清理后 orders 无残留",
            int(one("SELECT count(*) FROM orders WHERE id > %d" % hw_orders)) == 0)
        chk("清理后 payments 无残留",
            int(one("SELECT count(*) FROM payments WHERE id > %d" % hw_pay)) == 0)

        # ---------------------------------------------------------- verdict
        failed = [n for n, ok in checks if not ok]
        say("\n" + "=" * 78)
        for n, ok in checks:
            say("  [%s] %s" % ("PASS" if ok else "FAIL", n))
        say("=" * 78)
        say("TOTAL: %d / %d passed, %d failed" % (len(checks) - len(failed), len(checks), len(failed)))
        say("VERDICT: %s" % ("PASS" if not failed else "FAIL"))
        flush()
        print("ASSERTIONS: %d / %d passed (EXPECTED=%d)"
              % (len(checks) - len(failed), len(checks), EXPECTED_CHECKS))
        print("VERDICT: %s" % ("OK" if not failed else "FAIL"))
        return 0 if not failed else 1


# ★ 常量必须与运行时断言数一致（对着实跑报告核，别对着源码数）
EXPECTED_CHECKS = 82


if __name__ == "__main__":
    sys.exit(main())
