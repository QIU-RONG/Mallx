# -*- coding: utf-8 -*-
"""
Day 17 链路 C -- 管理端取消订单（POST /api/admin/orders/{id}/cancel）。

本链路只有 2 行业务代码，但它是本日【唯一复用回补链路】的一条：

    cancel(userId, orderId)    : requireOwn(404) -> CAS -> 回补库存 + 写流水
    cancelByAdmin(orderId)     : selectById(404) -> CAS -> 回补库存 + 写流水
                                  ^^^^^^^^^^^^^^^ 换成存在性检查（不做归属校验）

所以验收的重点不是「能不能取消」，而是：

  ① 回补是否与 C 端【完全同源】—— 库存三格 + 流水口径（CANCEL_RELEASE / change=+n /
     reference_id=orderId），任何一处不一致都会在 Day 14 的全链路对账上表现为「账目漂移」；
  ② 「跳过归属」有没有被写成别的形态 —— 比如 requireOwn(null, id)、从 token 取一个
     userId 传进去、或者自己再写一份 CAS + releaseLocked。

★★ 本脚本是【写操作】—— 自带清理（水位线 + 库存 SET 回基线 + finally 兜底），
   可重复执行；跑完 orders / order_items / payments / inventory_logs / cart_items /
   inventories 全部回到基线，好让 day17-m1-regression.py 的 BASELINE RESTORED 保持 YES。

断言层次（与项目其余验收一致）：
  ① 真 HTTP 状态码（Security 层的 401/403）与 HTTP 200 + body.code 分开判；
  ② 写入效果【必须去 DB 核】—— 状态码什么也证明不了；
  ③ 权限矩阵用 op_order（ORDER_ADMIN）而不是 admin（SUPER_ADMIN）——
     超管权限全有，区分不出「权限码写对了没」。

Usage:
    python day17-c-order-cancel-verify.py
报告（utf-8）与脚本同目录：day17-c-order-cancel-verify-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
TARGET_SKU = 4          # MATE80-BLK-512 @ 6999.00
ADDRESS_ID = 2          # demo 的默认地址
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day17-c-order-cancel-verify-report.txt")

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=60):
    """返回 (http_status, raw_text)。★ 显式禁用代理：会话注入的 HTTP_PROXY 会把
    127.0.0.1 也拦下，报 502 os error 10061 —— 看起来像服务挂了。"""
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
    """★ 业务码藏在 body.code 里（HTTP 仍是 200）。真实 HTTP 状态码只出现在 Security 层。"""
    try:
        return json.loads(raw).get("code")
    except ValueError:
        return None


def body_msg(raw):
    try:
        return json.loads(raw).get("message")
    except ValueError:
        return None


# ---------------------------------------------------------------- db helpers
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip()


def one(sql):
    """单值。⚠️ docker exec 回传行尾带 \\r —— 不 strip 会让比对恒为假。"""
    return psql(sql).strip()


def inv(sku):
    out = one("SELECT total_stock||','||available_stock||','||locked_stock||','||sold_stock"
              "||','||(total_stock=available_stock+locked_stock+sold_stock)"
              " FROM inventories WHERE sku_id=%d" % sku)
    p = [x.strip() for x in out.split(",")]
    return dict(total=int(p[0]), available=int(p[1]), locked=int(p[2]),
                sold=int(p[3]), id_ok=p[4].lower() in ("t", "true"))


def inv_line(tag, sku, r):
    return "  %-14s sku%d  total=%3d  available=%3d  locked=%3d  sold=%3d  identity=%s" % (
        tag, sku, r["total"], r["available"], r["locked"], r["sold"],
        "OK" if r["id_ok"] else "BROKEN")


def all_inv():
    return one("SELECT string_agg(sku_id||'|'||total_stock||'|'||available_stock||'|'"
               "||locked_stock||'|'||sold_stock, ' ; ' ORDER BY sku_id) FROM inventories")


def order_state(oid):
    out = one("SELECT status||','||coalesce(cancelled_at::text,'NULL')||','"
              "||coalesce(paid_at::text,'NULL') FROM orders WHERE id=%d" % oid)
    if not out:
        return None
    p = [x.strip() for x in out.split(",")]
    return dict(status=p[0], cancelled_at=p[1], paid_at=p[2])


def logs_since(high):
    return one("SELECT coalesce(string_agg(id||'|'||sku_id||'|'||type||'|'"
               "||change_quantity||'|'||before_stock||'|'||after_stock||'|'"
               "||coalesce(reference_id::text,'NULL'), '  ;  ' ORDER BY id), '-')"
               " FROM inventory_logs WHERE id > %d" % high)


def log_sum_since(high):
    return one("SELECT coalesce(sum(change_quantity),0)::text"
               " FROM inventory_logs WHERE id > %d" % high)


def log_count_since(high):
    return int(one("SELECT count(*) FROM inventory_logs WHERE id > %d" % high) or 0)


def short(raw, n=220):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ================================================================ main
def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 17 链路 C -- 管理端取消订单（复用回补链路）")
    say("target : %s   account: demo(C端) / op_order(ORDER_ADMIN) / admin(SUPER_ADMIN)" % BASE)
    say("=" * 78)

    created = []                 # 本次造的 order id -> 清理目标
    high_water = None            # inventory_logs 水位线

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base = inv(TARGET_SKU)
    base_all_inv = all_inv()
    base_counts = dict(
        orders=int(one("SELECT count(*) FROM orders")),
        order_items=int(one("SELECT count(*) FROM order_items")),
        payments=int(one("SELECT count(*) FROM payments")),
        inventory_logs=int(one("SELECT count(*) FROM inventory_logs")),
        cart_items=int(one("SELECT count(*) FROM cart_items")),
    )
    high_water = int(one("SELECT coalesce(max(id),0) FROM inventory_logs"))
    paid_owned = one("SELECT id FROM orders WHERE status='PAID' ORDER BY id LIMIT 1")
    say(inv_line("stock", TARGET_SKU, base))
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base_counts.items())))
    say("  inventory_logs 水位线 = %d ；找一个 PAID 单做对照 = %s" % (high_water, paid_owned))
    chk("baseline identity holds for sku%d" % TARGET_SKU, base["id_ok"])

    # ---------------------------------------------------------- [1] anonymous
    say("\n[1] 匿名 POST /api/admin/orders/1/cancel")
    st, raw = api("POST", "/api/admin/orders/1/cancel")
    say("  http=%s code=%s %s" % (st, body_code(raw), short(raw, 120)))
    say("  ★ 这是 Security 层（过滤器）写的响应，所以是【真 HTTP 401】")
    chk("匿名被拒，且是真 HTTP 401（不是 body.code）", st == 401, "http=%s" % st)

    # ---------------------------------------------------------- [2] login
    say("\n[2] 登录三个身份（token 只在内存里，不落盘）")

    def login(path, u, p):
        st_, b_, _ = japi("POST", path, body={"username": u, "password": p})
        return (b_.get("data") or {}).get("token"), b_.get("code")

    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    adm_t, c3 = login("/api/auth/admin/login", "admin", "admin123")
    say("  demo     code=%s token_len=%d" % (c1, len(demo_t or "")))
    say("  op_order code=%s token_len=%d" % (c2, len(op_t or "")))
    say("  admin    code=%s token_len=%d" % (c3, len(adm_t or "")))
    chk("三个身份全部登录成功", all([demo_t, op_t, adm_t]),
        "op_order 缺失请先跑 day17-fixture-apply.py")
    if not all([demo_t, op_t, adm_t]):
        say("\nABORT: 缺 token")
        flush()
        return 1

    op_id = int(one("SELECT id FROM admins WHERE username='op_order'"))

    # ---------------------------------------------------------- [3] C 端 403
    say("\n[3] C 端 token 打管理端端点（demo 权限集为空 -> 403）")
    st, raw = api("POST", "/api/admin/orders/1/cancel", token=demo_t)
    say("  http=%s code=%s %s" % (st, body_code(raw), short(raw, 120)))
    say("  ★ 同样是 Security 层的真 403 —— @PreAuthorize('order:cancel') 在方法前就把门关了")
    chk("C 端 token 被拒，且是真 HTTP 403", st == 403, "http=%s" % st)

    # ---------------------------------------------------------------- helpers
    def place_order():
        """把 sku4 x1 放进购物车、选中、下单。返回 order id 或 None。"""
        st_, b_, _ = japi("GET", "/api/cart", token=demo_t)
        target = None
        for it in ((b_.get("data") or {}).get("items") or []):
            if it.get("skuId") == TARGET_SKU:
                target = it
        if target is None:
            say("    购物车里没有 sku%d -> POST /api/cart" % TARGET_SKU)
            japi("POST", "/api/cart", token=demo_t, body={"skuId": TARGET_SKU, "quantity": 1})
            st_, b_, _ = japi("GET", "/api/cart", token=demo_t)
            for it in ((b_.get("data") or {}).get("items") or []):
                if it.get("skuId") == TARGET_SKU:
                    target = it
        if target is None:
            return None
        japi("PUT", "/api/cart/%s/selected" % target["id"], token=demo_t, body={"selected": True})
        st_, b_, _ = japi("POST", "/api/orders", token=demo_t, body={"addressId": ADDRESS_ID})
        return b_.get("data") if st_ == 200 and isinstance(b_.get("data"), int) else None

    try:
        # ------------------------------------------------------ [4] 造单 A
        say("\n[4] 造一张待支付单 A（demo 下单：available -1 / locked +1）")
        order_a = place_order()
        say("  新订单 id = %s" % order_a)
        chk("订单 A 创建成功", isinstance(order_a, int))
        if not isinstance(order_a, int):
            raise SystemExit
        created.append(order_a)
        sa = order_state(order_a)
        say("  psql: %s" % sa)
        chk("订单 A 是 PENDING_PAYMENT", sa and sa["status"] == "PENDING_PAYMENT")
        after_order = inv(TARGET_SKU)
        say(inv_line("下单后", TARGET_SKU, after_order))
        chk("下单把货锁住了：available -1 / locked +1 / sold 不动",
            after_order["available"] == base["available"] - 1
            and after_order["locked"] == base["locked"] + 1
            and after_order["sold"] == base["sold"])
        say("  流水：%s" % logs_since(high_water))

        # ------------------------------------------------------ [5] 取消 A
        say("\n[5] ★ op_order(ORDER_ADMIN, id=%d) 取消订单 A" % op_id)
        say("    注意 op_order.id=%d 与订单属主 demo.userId=1 【不相等】——"
            % op_id)
        say("    所以「停用归属检查」这件事在这里是【可判别的】")
        st, b, raw = japi("POST", "/api/admin/orders/%d/cancel" % order_a, token=op_t)
        say("  http=%s code=%s message=%s data=%s" % (
            st, b.get("code"), b.get("message"), json.dumps(b.get("data"))))
        chk("取消成功：HTTP 200 + code 200", st == 200 and b.get("code") == 200,
            "实际 http=%s code=%s msg=%s" % (st, b.get("code"), b.get("message")))
        chk("返回 Result<Void>（data 为 null）", b.get("data") is None)

        # ------------------------------------------------------ [6] DB 对账
        say("\n[6] DB 对账：订单状态（不信接口自报）")
        sb = order_state(order_a)
        say("  psql: %s" % sb)
        chk("status 变成 CANCELLED", sb and sb["status"] == "CANCELLED",
            "实际 %s" % (sb or {}).get("status"))
        chk("cancelled_at 已写入（业务事实时间）", sb and sb["cancelled_at"] != "NULL")
        chk("paid_at 仍为 NULL（取消不碰支付时间）", sb and sb["paid_at"] == "NULL")

        # ------------------------------------------------------ [7] 库存回补
        say("\n[7] ★★ 库存回补：releaseLocked 与 deductStock 严格互逆")
        after_cancel = inv(TARGET_SKU)
        say(inv_line("取消后", TARGET_SKU, after_cancel))
        say("  vs 基线：available %+d  locked %+d  sold %+d" % (
            after_cancel["available"] - base["available"],
            after_cancel["locked"] - base["locked"],
            after_cancel["sold"] - base["sold"]))
        chk("locked 回到基线", after_cancel["locked"] == base["locked"])
        chk("available 回到基线", after_cancel["available"] == base["available"])
        chk("sold 完全没被碰", after_cancel["sold"] == base["sold"])
        chk("三格恒等式仍成立", after_cancel["id_ok"])

        # ------------------------------------------------------ [8] 流水
        say("\n[8] ★★ 流水口径：CANCEL_RELEASE / change=+n / reference_id=orderId")
        rows = logs_since(high_water)
        say("  本次新增流水：%s" % rows)
        cr = [r for r in rows.split("  ;  ") if r.split("|")[2:3] == ["CANCEL_RELEASE"]]
        chk("新增 CANCEL_RELEASE 恰好 1 条", len(cr) == 1, "实得 %d 条" % len(cr))
        if cr:
            f = cr[0].split("|")
            say("  该条：sku=%s change=%s before=%s after=%s ref=%s"
                % (f[1], f[3], f[4], f[5], f[6]))
            chk("change_quantity = +1（available 增加的方向）", f[3] == "1")
            chk("reference_id = 订单 id（能反查是哪张单退回的）", f[6] == str(order_a))
            chk("before/after 接续：after = before + 1", int(f[5]) == int(f[4]) + 1)
        say("  ★ 账本自洽：本次 Σ(change) = %s   （下单 -1 与取消 +1 相抵）"
            % log_sum_since(high_water))
        chk("Σ(change) over 本次流水 == 0", log_sum_since(high_water) == "0")

        # ------------------------------------------------------ [9] 重复取消
        say("\n[9] ★ 重复取消同一单（这就是端点用 POST 不用 PUT 的原因）")
        st, b, _ = japi("POST", "/api/admin/orders/%d/cancel" % order_a, token=op_t)
        say("  http=%s code=%s message=%s" % (st, b.get("code"), b.get("message")))
        chk("重复取消被拒：HTTP 200 + code 400", st == 200 and b.get("code") == 400,
            "实际 http=%s code=%s" % (st, b.get("code")))
        chk("...且措辞是「不允许取消」", "不允许取消" in (b.get("message") or ""),
            "message=%s" % b.get("message"))
        chk("库存没有被再动一次", inv(TARGET_SKU) == after_cancel)
        chk("流水没有新增第 2 条", log_count_since(high_water) == len(
            [r for r in rows.split("  ;  ") if r.strip()]))

        # ------------------------------------------------------ [10] 造单 B + admin 取消
        say("\n[10] 造单 B，改由 admin(SUPER_ADMIN) 取消 —— 两个管理身份都必须能取消")
        order_b = place_order()
        say("  新订单 id = %s" % order_b)
        chk("订单 B 创建成功且为 PENDING_PAYMENT",
            isinstance(order_b, int) and order_state(order_b)["status"] == "PENDING_PAYMENT")
        if isinstance(order_b, int):
            created.append(order_b)
            st, b, _ = japi("POST", "/api/admin/orders/%d/cancel" % order_b, token=adm_t)
            say("  admin 取消 http=%s code=%s -> status=%s"
                % (st, b.get("code"), (order_state(order_b) or {}).get("status")))
            chk("admin 也能取消（不是只有 op_order 能）",
                st == 200 and b.get("code") == 200
                and order_state(order_b)["status"] == "CANCELLED")
            chk("库存再次回到基线", inv(TARGET_SKU) == base)

        # ------------------------------------------------------ [11] PAID 单
        if paid_owned:
            say("\n[11] ★ 取消已支付单 #%s —— 本日边界的显式声明（不做退款）" % paid_owned)
            before_paid = order_state(int(paid_owned))
            st, b, _ = japi("POST", "/api/admin/orders/%s/cancel" % paid_owned, token=op_t)
            say("  http=%s code=%s message=%s" % (st, b.get("code"), b.get("message")))
            chk("PAID 单被 CAS 挡成 400", st == 200 and b.get("code") == 400,
                "实际 http=%s code=%s msg=%s" % (st, b.get("code"), b.get("message")))
            after_paid = order_state(int(paid_owned))
            say("  该单前后：%s -> %s" % (before_paid, after_paid))
            chk("PAID 单原封不动（状态与时间戳都没变）", before_paid == after_paid)
            chk("库存未因此变化", inv(TARGET_SKU) == base)
        else:
            say("\n[11] (库里没有 PAID 单 —— 跳过)")

        # ------------------------------------------------------ [12] 边界
        say("\n[12] ★ 边界：不存在的 id / 非数字 id（设计已定案 —— 本栏现在是【断言】，不再只报实测）")
        st, b, raw = japi("POST", "/api/admin/orders/99999999/cancel", token=op_t)
        say("  POST /api/admin/orders/99999999/cancel -> http=%s code=%s message=%s"
            % (st, b.get("code"), b.get("message")))
        say("     ★ 这里曾经是 500「订单明细缺失」：C 端的 requireOwn 顺手把「不存在」挡成了 404，")
        say("       管理端跳过归属之后，连存在性检查也一并丢了，于是走到 cancelOne 里查明细为空。")
        say("       但 500 的语义是「服务端错了」，而「你要取消的单不存在」是客户端错误。")
        say("       现已补回：selectById -> null -> 404（与 detailByAdmin 同款）。")
        chk("★ 不存在的 id -> code=404「订单不存在」（不是 500、也不是 400）",
            st == 200 and b.get("code") == 404 and b.get("message") == "订单不存在",
            "实际 http=%s code=%s message=%s" % (st, b.get("code"), b.get("message")))
        chk("★ 不是 400 —— 证明存在性检查排在 CAS【之前】（顺序写反就会先被 CAS 挡成 400，"
            "把「找不到」说成「状态不对」）",
            b.get("code") != 400, "实际 code=%s" % b.get("code"))

        # 同一 id 走【详情】端点，作为同源对照：
        # 两个端点面对「同一个不存在的资源」必须给出同一个答案。
        st_d, b_d, _ = japi("GET", "/api/admin/orders/99999999", token=op_t)
        say("  GET  /api/admin/orders/99999999 (详情)   -> http=%s code=%s message=%s"
            % (st_d, b_d.get("code"), b_d.get("message")))
        chk("★ 同 id 的【详情】端点同为 404 —— 取消与详情对「不存在」的口径一致",
            st_d == 200 and b_d.get("code") == 404 and b_d.get("message") == "订单不存在",
            "实际 http=%s code=%s message=%s" % (st_d, b_d.get("code"), b_d.get("message")))

        st, b, _ = japi("POST", "/api/admin/orders/abc/cancel", token=op_t)
        say("  POST /api/admin/orders/abc/cancel        -> http=%s code=%s message=%s"
            % (st, b.get("code"), b.get("message")))
        chk("/abc -> code=400（路径变量类型不匹配）", st == 200 and b.get("code") == 400,
            "实际 http=%s code=%s" % (st, b.get("code")))

    except SystemExit:
        say("\n(提前中止 —— 下面的清理仍会执行)")

    finally:
        # ------------------------------------------------------ [13] 清理
        say("\n" + "=" * 78)
        say("[13] CLEANUP —— 删掉本次造的单据与流水，库存 SET 回基线")
        say("=" * 78)
        say("  要删的订单：%s" % (created or "(无)"))
        say("  要删的流水：id > %d" % high_water)
        try:
            if created:
                ids = ",".join(str(o) for o in created)
                psql("DELETE FROM payments WHERE order_id IN (%s);"
                     " DELETE FROM order_items WHERE order_id IN (%s);"
                     " DELETE FROM orders WHERE id IN (%s);" % (ids, ids, ids))
            psql("DELETE FROM inventory_logs WHERE id > %d;" % high_water)
            psql("DELETE FROM cart_items WHERE user_id=1 AND sku_id=%d;" % TARGET_SKU)
            psql("UPDATE inventories SET locked_stock=%d, sold_stock=%d,"
                 " available_stock=total_stock-%d-%d, updated_at=CURRENT_TIMESTAMP"
                 " WHERE sku_id=%d;"
                 % (base["locked"], base["sold"], base["sold"], base["locked"], TARGET_SKU))
            chk("清理执行无 SQL 错误", True)
        except Exception as e:                                                  # noqa: BLE001
            say("  CLEANUP FAILED: %s" % e)
            chk("清理执行无 SQL 错误", False)

        # ------------------------------------------------------ [14] 核对基线
        say("\n[14] VERIFY —— 回到基线（这是留给 day17-m1-regression.py 的前提）")
        counts_now = dict(
            orders=int(one("SELECT count(*) FROM orders")),
            order_items=int(one("SELECT count(*) FROM order_items")),
            payments=int(one("SELECT count(*) FROM payments")),
            inventory_logs=int(one("SELECT count(*) FROM inventory_logs")),
            cart_items=int(one("SELECT count(*) FROM cart_items")),
        )
        for k in sorted(base_counts):
            same = counts_now[k] == base_counts[k]
            say("  %-16s = %-5d %s" % (k, counts_now[k],
                                       "unchanged" if same else "★ CHANGED from %d" % base_counts[k]))
            chk("%s 回到基线" % k, same,
                "%d -> %d" % (base_counts[k], counts_now[k]))
        inv_ok = (all_inv() == base_all_inv)
        say("  inventories     : %s" % ("逐字节相同" if inv_ok else "★ 与基线不同"))
        if not inv_ok:
            say("    now     : %s" % all_inv())
            say("    baseline: %s" % base_all_inv)
        chk("7 个 SKU 库存逐字节回到基线", inv_ok)

    # ---------------------------------------------------------- verdict
    say("\n" + "=" * 78)
    say("ASSERTIONS")
    say("=" * 78)
    passed = 0
    for name, good, detail in checks:
        say("  [%s] %s%s" % ("PASS" if good else "FAIL", name,
                            ("   <- " + detail) if (detail and not good) else ""))
        passed += 1 if good else 0
    say("\nRESULT: %d/%d passed" % (passed, len(checks)))
    say("VERDICT: %s" % ("CANCEL-BY-ADMIN OK -- 回补同源、流水口径正确、权限矩阵成立"
                         if passed == len(checks) else "NOT CLEAN -- 见上面 FAIL 行"))
    flush()
    print("report -> %s   %d/%d passed" % (OUT, passed, len(checks)))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                           # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
