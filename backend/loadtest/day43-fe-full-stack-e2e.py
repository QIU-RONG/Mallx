#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MallX Day 43 · 前端全栈联调 —— 两个 dev server 代理 + 一个后端。

为什么需要一个新脚本
--------------------
FE1–FE3 的验收是**分端**做的（mall-app 单独、admin-app 单独）。这里要证的是另一件事：
**「两个前端 + 一个后端」作为一个整体能不能跑通**，而且链路必须**跨端**
（C 端下单支付 → 管理端发货 → C 端收货评价）。

★ 全部请求都打 **Vite dev server 的代理**（5173 / 5174），不直连 8080。
  这样每条断言同时覆盖三件事：代理配置、接口契约、以及**前端真正会用到的那几个字段名**。
  换句话说：直接打 8080 只能证明后端对，经由代理才能证明「前端接得上」。

判定纪律（沿本项目规矩）
------------------------
· 判定看 `body.code`（业务失败 = HTTP 200 + code != 200），不看 HTTP 状态码；
· 关键值从 `psql` 复算，**不信接口自报**；
· 跑完把订单/支付/评价/库存流水**全部还原**，并复跑 M1 收集器证明 (c) 回基线。

两个本机专属前提（踩过）
------------------------
· ★ **Vite 8 dev 只绑 localhost（IPv6）** ⇒ 必须用 `localhost`，`127.0.0.1` 会拿到 000；
· ★ **系统代理会拦 localhost**（502 假故障）⇒ 必须显式绕过（ProxyHandler({})）。

用法：
    python day43-fe-full-stack-e2e.py
前置：8080 后端在跑；5173 / 5174 两个 dev server 在跑；mallx-postgres 容器在跑。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day43-fe-full-stack-report.txt")

# ★ 用 localhost：Vite 8 dev 只绑 IPv6 的 localhost，127.0.0.1 连不上
PROXY_C = os.environ.get("MALLX_PROXY_C", "http://localhost:5173")   # C 端 mall-app
PROXY_A = os.environ.get("MALLX_PROXY_A", "http://localhost:5174")   # 管理端 admin-app

DOCKER = os.environ.get("MALLX_DOCKER") or \
    r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PG = "mallx-postgres"

USER_NAME, USER_PW = "demo", "demo123"
ADMIN_NAME, ADMIN_PW = "admin", "admin123"
SKU = 4               # MATE80-BLK-512 @ 6999.00
ADDRESS_ID = 2        # demo 的默认收货地址

# 断言总数写死：防止「断言没被创建」导致的假通过。
# 54 = 55 条 chk 调用行 − 3 条「全通过时不会执行」（① 加购/已在车里 二选一
#      ② 清理 OK/FAIL 二选一 ③ 未预期异常那条）+ 2 条在【循环里】各执行两次
#      （两个 dev server 各一条、两个代理各一条）。
# ★ 这个数我是被自己坑过一次的：第一版按「调用行数」直接写了 40，于是 54/0 全过也判 FAIL；
#   第二版静态减 3 又漏了循环乘 2。**数字要对着实跑报告核**，不要对着源码数。
EXPECTED_CHECKS = 54

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                       # noqa: BLE001
    pass

_LINES = []
_CHECKS = [0, 0]      # [passed, failed]


def say(msg=""):
    print(msg)
    _LINES.append(msg)


def chk(name, ok):
    _CHECKS[0 if ok else 1] += 1
    say("  [%s] %s" % ("OK" if ok else "FAIL", name))
    return ok


class _Abort(Exception):
    pass


def need(ok, msg):
    if not ok:
        say("  !! %s" % msg)
        raise _Abort()


# ------------------------------------------------------------------ http
# ★ 每个请求都绕过系统代理：本机 127.0.0.1/localhost 会被代理拦成 502
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(base, method, path, token=None, body=None):
    url = base + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "replace")
            st = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        st = e.code
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = {"code": None, "message": raw[:120], "data": None}
    return st, parsed, raw


def code_of(b):
    return b.get("code") if isinstance(b, dict) else None


def dec(x):
    """numeric 字段的比较用 Decimal：psql 回的是 '6999.00'，int() 会直接炸。"""
    return Decimal(str(x))


def data_of(b):
    return (b or {}).get("data")


def get_html(base):
    """dev server 根路径是否返回 HTML（证明 dev server 真的在跑）。"""
    try:
        with _OPENER.open(base + "/", timeout=10) as r:
            head = r.read(400).decode("utf-8", "replace")
            return r.status, head
    except Exception as e:                                              # noqa: BLE001
        return None, str(e)


# ------------------------------------------------------------------ db
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


def inv(sku):
    row = one("SELECT available_stock||'|'||locked_stock||'|'||sold_stock"
              " FROM inventories WHERE sku_id=%d" % sku)
    a, l, s = row.split("|")
    return {"available": int(a), "locked": int(l), "sold": int(s)}


def order_row(oid):
    row = one("SELECT status||'|'||total_amount||'|'||COALESCE(discount_amount,0)||'|'||pay_amount"
              "||'|'||COALESCE(paid_at::text,'')||'|'||COALESCE(shipped_at::text,'')"
              "||'|'||COALESCE(completed_at::text,'')||'|'||user_id"
              " FROM orders WHERE id=%d" % oid)
    f = row.split("|")
    return {"status": f[0], "total": f[1], "discount": f[2], "pay": f[3],
            "paid_at": f[4], "shipped_at": f[5], "completed_at": f[6], "user_id": int(f[7])}


def order_items_of(oid):
    out = one("SELECT id||'|'||product_id||'|'||sku_id FROM order_items"
              " WHERE order_id=%d ORDER BY id" % oid)
    rows = [r for r in out.splitlines() if r.strip()]
    return [tuple(int(x) for x in r.split("|")) for r in rows]


# ------------------------------------------------------------------ main
def main():
    say("=" * 78)
    say("MallX  Day 43 · 前端全栈联调（两个 dev server 代理 / 跨端链路 / 基线还原）")
    say("=" * 78)
    say("run at : %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    say("C 端代理 : %s   ·   管理端代理 : %s" % (PROXY_C, PROXY_A))

    high_water = int(one("SELECT COALESCE(max(id),0) FROM inventory_logs"))
    base_inv = inv(SKU)
    base_counts = one("SELECT (SELECT count(*) FROM orders)||'/'||"
                      "(SELECT count(*) FROM payments)||'/'||"
                      "(SELECT count(*) FROM order_items)||'/'||"
                      "(SELECT count(*) FROM reviews)||'/'||"
                      "(SELECT count(*) FROM inventory_logs)")
    created = []
    touched = set()
    say("baseline: sku%d avail/locked/sold = %s   rows o/p/oi/rv/il = %s"
        % (SKU, base_inv, base_counts))

    try:
        # ============================================================ [1] 两个 dev server
        say("\n[1] 两个 dev server 是否都在跑（★ 用 localhost，Vite 8 只绑 IPv6）")
        for tag, base in (("mall-app", PROXY_C), ("admin-app", PROXY_A)):
            st, head = get_html(base)
            ok = st == 200 and "<div id=\"app\"" in head
            say("  GET %s/  -> http=%s  html_has_app_div=%s" % (base, st, "<div id=\"app\"" in head))
            chk("%s dev server 返回可挂载的 HTML" % tag, ok)

        say("\n[2] 后端是否经【两个代理】都可达（代理规则本身）")
        for tag, base in (("5173", PROXY_C), ("5174", PROXY_A)):
            st, b, _ = api(base, "GET", "/api/hello")
            chk("%s 代理 /api -> 8080 可达（code=200）" % tag, st == 200 and code_of(b) == 200)

        # ============================================================ [3] C 端登录
        say("\n[3] C 端经 5173 登录")
        st, b, raw = api(PROXY_C, "POST", "/api/auth/login",
                         body={"username": USER_NAME, "password": USER_PW})
        utok = data_of(b).get("token") if isinstance(data_of(b), dict) else None
        chk("demo 登录成功并拿到 token", st == 200 and code_of(b) == 200 and bool(utok))

        st, b, _ = api(PROXY_C, "POST", "/api/auth/login",
                       body={"username": USER_NAME, "password": "wrong-password"})
        chk("错误密码被拒（code != 200）", code_of(b) != 200)

        # ============================================================ [4] C 端商品浏览
        say("\n[4] C 端商品列表 / 详情（前端真实用到的字段）")
        st, b, _ = api(PROXY_C, "GET", "/api/products?page=1&size=10")
        d = data_of(b) or {}
        records = d.get("records") or []
        chk("商品列表可读且非空（records=%d）" % len(records), code_of(b) == 200 and len(records) > 0)
        # ★ 字段名以【前端自己的类型定义】为准（frontend/mall-app/src/types/api.d.ts 的 ProductVO）。
        #   列表 VO 里【没有 price】—— 价格挂在 SKU 上，列表页并不显示价格。
        #   第一版脚本按「我以为的」写了 price ⇒ 直接 FAIL。这正是经代理跑一遍的价值：
        #   直接打 8080 只会验后端对不对，验不出「前端拿到的字段名对不对」。
        chk("列表项带前端 ProductVO 必需的 id/name/status",
            all(k in records[0] for k in ("id", "name", "status")) if records else False)

        pid = records[0]["id"] if records else 0
        st, b, _ = api(PROXY_C, "GET", "/api/products/%d" % pid)
        pd = data_of(b) or {}
        skus = pd.get("skus") or []
        chk("商品详情可读且带 SKU 列表（skus=%d）" % len(skus), code_of(b) == 200 and len(skus) > 0)
        chk("详情 id 与列表 id 一致", pd.get("id") == pid)
        # 详情页要选 SKU 下单 ⇒ sku 上必须有 id 与 price（价格在前端 SkuVO 里）
        chk("SKU 带前端选规格/显示价格必需的 id/price",
            all(k in skus[0] for k in ("id", "price")) if skus else False)

        # ============================================================ [5] C 端购物车 → 下单 → 支付
        say("\n[5] C 端购物车 → 下单 → 支付（经 5173）")
        st, b, _ = api(PROXY_C, "GET", "/api/cart", token=utok)
        items = (data_of(b) or {}).get("items") or []
        found = next((it for it in items if it.get("skuId") == SKU), None)
        if not found:
            st, b, _ = api(PROXY_C, "POST", "/api/cart", token=utok,
                           body={"skuId": SKU, "quantity": 1})
            chk("加购成功（SKU %d 不在车里 → POST /api/cart）" % SKU, code_of(b) == 200)
            st, b, _ = api(PROXY_C, "GET", "/api/cart", token=utok)
            items = (data_of(b) or {}).get("items") or []
            found = next((it for it in items if it.get("skuId") == SKU), None)
        else:
            chk("购物车可读（SKU %d 已在车里）" % SKU, True)
        need(found, "购物车里找不到 SKU %d" % SKU)

        st, b, _ = api(PROXY_C, "PUT", "/api/cart/%s" % found["id"], token=utok,
                       body={"quantity": 1})
        chk("改数量成功（PUT /api/cart/{id}）", code_of(b) == 200)
        st, b, _ = api(PROXY_C, "PUT", "/api/cart/%s/selected" % found["id"], token=utok,
                       body={"selected": True})
        chk("勾选成功（PUT /api/cart/{id}/selected）", code_of(b) == 200)

        touched.add(SKU)
        st, b, raw = api(PROXY_C, "POST", "/api/orders", token=utok,
                         body={"addressId": ADDRESS_ID})
        oid = data_of(b)
        oid = oid.get("id") if isinstance(oid, dict) else oid
        chk("下单成功（POST /api/orders）", code_of(b) == 200 and bool(oid))
        need(oid, "下单没有拿到 orderId")
        created.append(int(oid))
        say("  orderId = %s" % oid)

        row = order_row(int(oid))
        chk("新订单状态 PENDING_PAYMENT（DB）", row["status"] == "PENDING_PAYMENT")
        # ★ 金额是 numeric ⇒ psql 回的是 '6999.00'，不能用 int()（第一版就崩在这）
        chk("★ 金额恒等式（DB）：total - discount = pay",
            dec(row["total"]) - dec(row["discount"]) == dec(row["pay"]))
        chk("下单锁定库存（DB available 减 1）",
            inv(SKU)["available"] == base_inv["available"] - 1)

        st, b, _ = api(PROXY_C, "POST", "/api/payments", token=utok,
                       body={"orderId": int(oid), "method": "ALIPAY"})
        chk("支付成功（POST /api/payments，入参没有 amount）", code_of(b) == 200)
        row = order_row(int(oid))
        chk("支付后状态 PAID（DB）", row["status"] == "PAID")
        chk("paid_at 已写入（DB）", bool(row["paid_at"]))
        # ★ 列名以 01-schema.sql 为准：payments 的金额列叫 amount（**不是** pay_amount，
        #   那个是 orders 表上的）。第一版按「两表同义就该同名」猜了列名 ⇒ SQL 直接报错。
        chk("★ 支付流水金额 = orders.pay_amount（跨表对账，前端金额恒等式的后端基础）",
            dec(one("SELECT amount FROM payments WHERE order_id=%d" % int(oid))) == dec(row["pay"]))

        st, b, _ = api(PROXY_C, "GET", "/api/orders", token=utok)
        chk("订单列表可读且能看到本单",
            code_of(b) == 200 and any(str(o.get("id")) == str(oid)
                                      for o in ((data_of(b) or {}).get("records") or [])))
        st, b, _ = api(PROXY_C, "GET", "/api/orders/%s" % oid, token=utok)
        chk("订单详情可读（GET /api/orders/{id}）", code_of(b) == 200)
        st, b, _ = api(PROXY_C, "GET", "/api/orders/%s" % oid)
        chk("他人/匿名读该订单被拒（不是 200）", code_of(b) != 200)

        # ============================================================ [6] 管理端
        say("\n[6] 管理端经 5174 —— 看到 C 端刚下的单并发货")
        st, b, raw = api(PROXY_A, "POST", "/api/auth/admin/login",
                         body={"username": ADMIN_NAME, "password": ADMIN_PW})
        atok = data_of(b).get("token") if isinstance(data_of(b), dict) else None
        chk("admin 登录成功（经 5174）", st == 200 and code_of(b) == 200 and bool(atok))

        st, b, _ = api(PROXY_A, "GET", "/api/admin/orders?page=1&size=10", token=atok)
        recs = (data_of(b) or {}).get("records") or []
        chk("管理端订单列表可读且能看到这张单（GET /api/admin/orders）",
            code_of(b) == 200 and any(str(o.get("id")) == str(oid) for o in recs))

        st, b, _ = api(PROXY_A, "GET", "/api/admin/orders/%s" % oid, token=atok)
        chk("管理端能读到该单详情（GET /api/admin/orders/{id}）", code_of(b) == 200)

        # ★ 记录但不判定：管理端 token 打 C 端订单接口属于设计外用法（C 端接口按 requireOwn
        #   把 principal 当 userId，管理端的 principal 是 adminId），不预设结论。
        st, b, _ = api(PROXY_C, "GET", "/api/orders/%s" % oid, token=atok)
        say("  （记录，不判定）管理端 token -> C 端 /api/orders/{id} : http=%s code=%s"
            % (st, code_of(b)))

        st, b, _ = api(PROXY_A, "POST", "/api/orders/%s/ship" % oid, token=atok)
        chk("发货成功（POST /api/orders/{id}/ship）", code_of(b) == 200)
        row = order_row(int(oid))
        chk("发货后状态 SHIPPED（DB）", row["status"] == "SHIPPED")
        chk("shipped_at 已写入（DB）", bool(row["shipped_at"]))

        st, b, _ = api(PROXY_A, "POST", "/api/orders/%s/ship" % oid, token=atok)
        chk("重复发货被拒（状态机：不是 200）", code_of(b) != 200)

        st, b, _ = api(PROXY_A, "POST", "/api/orders/%s/cancel" % oid, token=utok)
        chk("已发货订单不可取消（不是 200）", code_of(b) != 200)

        # ============================================================ [7] C 端收货 + 评价
        say("\n[7] C 端经 5173 —— 确认收货 + 评价")
        st, b, _ = api(PROXY_C, "POST", "/api/orders/%s/confirm" % oid, token=utok)
        chk("确认收货成功（POST /api/orders/{id}/confirm）", code_of(b) == 200)
        row = order_row(int(oid))
        chk("收货后状态 COMPLETED（DB）", row["status"] == "COMPLETED")
        chk("completed_at 已写入（DB）", bool(row["completed_at"]))

        items_db = order_items_of(int(oid))
        need(items_db, "order_items 里查不到本单的行")
        item_id, prod_id, _sku = items_db[0]
        before_rv = int(one("SELECT count(*) FROM reviews"))
        st, b, _ = api(PROXY_C, "POST", "/api/reviews", token=utok,
                       body={"orderItemId": item_id, "rating": 5, "content": "Day43 全栈联调"})
        chk("评价成功（POST /api/reviews，只传 orderItemId）", code_of(b) == 200)
        chk("reviews 表多了一行（DB 复算）",
            int(one("SELECT count(*) FROM reviews")) == before_rv + 1)
        chk("★ 评价的 order_id / product_id 由后端从 order_items 反查（DB 校验）",
            one("SELECT order_id||'|'||product_id FROM reviews WHERE order_item_id=%d"
                % item_id) == "%d|%d" % (int(oid), prod_id))

        st, b, raw = api(PROXY_C, "POST", "/api/reviews", token=utok,
                         body={"orderItemId": item_id, "rating": 5, "content": "再来一次"})
        chk("同一 orderItemId 重复评价被拒（不是 200）", code_of(b) != 200)

        st, b, _ = api(PROXY_C, "GET", "/api/products/%d/reviews?page=1&size=10" % prod_id)
        chk("公开读评价（无 token，C 端商品详情页要用）", code_of(b) == 200)

        # ============================================================ [8] 跨端权限对照
        say("\n[8] 跨端权限对照（白名单/权限码按【端】分开）")
        st, b, _ = api(PROXY_A, "GET", "/api/admin/roles", token=utok)
        say("  C 端 token -> 管理端 /api/admin/roles : http=%s code=%s" % (st, code_of(b)))
        chk("C 端 token 打管理端接口被拒", code_of(b) != 200)
        st, b, _ = api(PROXY_A, "GET", "/api/admin/roles")
        chk("匿名打管理端接口被拒", code_of(b) != 200)
        st, b, _ = api(PROXY_A, "GET", "/api/admin/roles", token=atok)
        chk("★ 正向对照：管理端 token 打同一接口可以（200）", code_of(b) == 200)
        st, b, _ = api(PROXY_C, "GET", "/api/cart")
        chk("匿名打 C 端私有接口被拒", code_of(b) != 200)
        # 记录但不判定：管理端 token 打 C 端私有接口属于设计外用法，不预设结论
        st, b, _ = api(PROXY_C, "GET", "/api/cart", token=atok)
        say("  （记录，不判定）管理端 token -> C 端 /api/cart : http=%s code=%s" % (st, code_of(b)))

        # ============================================================ [9] 端到端账目
        say("\n[9] 账目对账（DB）")
        chk("支付流水正好 1 行", one("SELECT count(*) FROM payments WHERE order_id=%d"
                                    % int(oid)) == "1")
        chk("订单行数 = 1（本单只买了一个 SKU）", len(items_db) == 1)
        inv_after = inv(SKU)
        chk("★ 已收货订单：sold 比基线 +1", inv_after["sold"] == base_inv["sold"] + 1)
        chk("★ 已收货订单：available 比基线 -1",
            inv_after["available"] == base_inv["available"] - 1)
        chk("locked 回到基线（无挂起锁定）", inv_after["locked"] == base_inv["locked"])
        chk("评价数 +1（相对基线）",
            int(one("SELECT count(*) FROM reviews")) == int(base_counts.split("/")[3]) + 1)

    except _Abort:
        say("\n(提前中止 —— 下面的清理照常执行)")
    except Exception as e:                                              # noqa: BLE001
        # ★ 兜住一切异常。第一版就是栽在这：finally 清完场后异常直接冒出去，
        #   脚本崩掉 ⇒ 已经跑过的 40 多条断言连同整份报告一起丢了。
        #   清场很重要，但「把发生过什么留下证据」同样重要。
        import traceback
        say("\n!! 未预期异常（已记录；清理照常执行）: %s: %s" % (type(e).__name__, e))
        say(traceback.format_exc())
        chk("脚本未抛未预期异常", False)

    finally:
        # ============================================================ [10] 清理
        say("\n" + "=" * 78)
        say("[10] CLEANUP —— 抹掉本次痕迹，回到基线")
        say("=" * 78)
        say("  orders to delete : %s" % (created or "(none)"))
        say("  ledger rows      : id > %d" % high_water)
        try:
            if created:
                ids = ",".join(str(o) for o in created)
                psql("DELETE FROM reviews WHERE order_id IN (%s);"
                     " DELETE FROM payments WHERE order_id IN (%s);"
                     " DELETE FROM order_items WHERE order_id IN (%s);"
                     " DELETE FROM orders WHERE id IN (%s);" % (ids, ids, ids, ids))
            psql("DELETE FROM inventory_logs WHERE id > %d;" % high_water)
            for sku in sorted(touched):
                psql("UPDATE inventories SET available_stock=%d, locked_stock=%d,"
                     " sold_stock=%d, updated_at=CURRENT_TIMESTAMP WHERE sku_id=%d;"
                     % (base_inv["available"], base_inv["locked"], base_inv["sold"], sku))
            chk("清理未报 SQL 错误", True)
        except Exception as e:                                          # noqa: BLE001
            say("  CLEANUP FAILED: %s" % e)
            chk("清理未报 SQL 错误", False)

        after_inv = inv(SKU)
        chk("库存逐字段回到基线", after_inv == base_inv)
        after_counts = one("SELECT (SELECT count(*) FROM orders)||'/'||"
                           "(SELECT count(*) FROM payments)||'/'||"
                           "(SELECT count(*) FROM order_items)||'/'||"
                           "(SELECT count(*) FROM reviews)||'/'||"
                           "(SELECT count(*) FROM inventory_logs)")
        say("  rows before/after = %s / %s" % (base_counts, after_counts))
        chk("表计数回到基线（orders/payments/order_items/reviews/inventory_logs）",
            after_counts == base_counts)

    say("\n" + "=" * 78)
    total = _CHECKS[0] + _CHECKS[1]
    say("结果：%d 通过 / %d 失败   （期望断言数 %d）" % (_CHECKS[0], _CHECKS[1], EXPECTED_CHECKS))
    ok = _CHECKS[1] == 0 and total == EXPECTED_CHECKS
    say("VERDICT: %s" % ("PASS —— 两个前端 + 后端作为一个整体跑通了" if ok else "FAIL"))
    say("=" * 78)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_LINES) + "\n")
    say("report -> %s" % OUT)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
