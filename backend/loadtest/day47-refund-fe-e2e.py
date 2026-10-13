#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Day 47 · 退款/售后的【前端联调】—— 两个 dev server 代理 + 跨端链路。

为什么还要一个新脚本（day46-refund-verify.py 已经 82 条了）
----------------------------------------------------------
day46 直连 8080，验的是**后端对不对**。
本脚本全部请求走 **Vite dev server 的代理**（5173 / 5174），因此每条断言同时覆盖三件事：
  ① 代理配置（前端真正在用的那条路）
  ② 接口契约
  ③ **前端类型定义里声明的字段名**（frontend/*/src/types/api.d.ts 的 RefundVO / AdminRefundVO）
第 ③ 条是直连后端永远验不出来的：字段名写错在前端只会**静默显示空白**，不报错。

★ 跨端是这里的重点（与 day43 同构）：
  C 端申请 → 管理端审核/打款 → C 端看到 SUCCESS，
  并且**商品管理员（op_product）全程 403** —— 售后是订单域的延续（18 号补丁第二节③）。

判定纪律（沿本项目规矩）
------------------------
· 业务失败 = **HTTP 200 + body.code != 200** ⇒ 判定看 code，不看 HTTP 状态码；
· 真 401/403 由 Security 层给，这是少数【必须看 HTTP 状态码】的地方；
· 金额/状态去 `psql` 复算，不信接口自报；
· 清库按 §9.2 的教训：**先确认已退款回补，再删单**，否则 sold/available 会永久漂移。

两个本机专属前提（踩过）
------------------------
· Vite 8 dev 只绑 localhost（IPv6）⇒ 用 `localhost`，`127.0.0.1` 会拿到 000；
· 系统代理会拦 localhost（502 假故障）⇒ 必须 ProxyHandler({}) 绕过。

用法：python day47-refund-fe-e2e.py
前置：8080 后端在跑；5173/5174 两个 dev server 在跑；mallx-postgres 容器在跑。
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day47-refund-fe-e2e-report.txt")

PROXY_C = os.environ.get("MALLX_PROXY_C", "http://localhost:5173")   # C 端 mall-app
PROXY_A = os.environ.get("MALLX_PROXY_A", "http://localhost:5174")   # 管理端 admin-app

DOCKER = os.environ.get("MALLX_DOCKER") or \
    r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PG = "mallx-postgres"

USER_NAME, USER_PW = "demo", "demo123"
SKU = 4               # MATE80-BLK-512 @ 6999.00
ADDRESS_ID = 2        # demo 的默认收货地址

# ★ 售后权限的【反向对照】账号（18 号补丁第二节③：商品管理员故意不发 refund:*）
OP_ORDER, OP_ORDER_PW = "op_order", "op123456"        # role 3 · 订单管理员 —— 有 refund:*
OP_PRODUCT, OP_PRODUCT_PW = "op_product", "prod123456"  # role 2 · 商品管理员 —— 无 refund:*

# 满额护栏：实跑报告里的 ASSERTIONS 必须等于它，否则判 FAIL（防止「断言没被创建」冒充通过）
EXPECTED_CHECKS = 27

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

_LINES = []
_CHECKS = [0, 0]


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
            raw, st = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, st = e.read().decode("utf-8", "replace"), e.code
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = {"code": None, "message": raw[:120], "data": None}
    return st, parsed, raw


def code_of(b):
    """★ 业务码：本项目业务失败是 HTTP 200 + body.code != 200"""
    return b.get("code") if isinstance(b, dict) else None


def data_of(b):
    return b.get("data") if isinstance(b, dict) else None


def msg_of(b):
    return (b.get("message") or "") if isinstance(b, dict) else ""


def login(base, path, user, pwd):
    st, b, _raw = api(base, "POST", path, body={"username": user, "password": pwd})
    return (data_of(b) or {}).get("token") if st == 200 and code_of(b) == 200 else None


# ------------------------------------------------------------------ DB
def psql(sql):
    p = subprocess.run([DOCKER, "exec", PG, "psql", "-U", "mallx", "-d", "mallx", "-tAc", sql],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "").strip()


def one(sql):
    return psql(sql)


def dec(x):
    return Decimal(str(x or "0"))


def inv(sku_id):
    r = psql("SELECT available, locked, sold FROM inventories WHERE sku_id=%d" % sku_id)
    parts = (r or "0|0|0").split("|")
    return {"available": int(parts[0] or 0), "locked": int(parts[1] or 0),
            "sold": int(parts[2] or 0)}


def order_row(oid):
    r = psql("SELECT status, total_amount, discount_amount, pay_amount "
             "FROM orders WHERE id=%d" % oid)
    parts = (r or "|||").split("|")
    return {"status": parts[0], "total": parts[1], "discount": parts[2], "pay": parts[3]}


# ------------------------------------------------------------------ main
def main():
    say("=" * 78)
    say("Day 47 · 退款/售后【前端联调】（C 端 5173 ↔ 管理端 5174，全部经 Vite 代理）")
    say("=" * 78)

    created = []
    base_inv = inv(SKU)

    try:
        # ================================================== [A] C 端：下单 → 支付 → 申请售后
        say("\n[A] C 端（经 5173）—— 前端 MyRefunds.vue / OrderDetail.vue 实际用的字段")
        utok = login(PROXY_C, "/api/auth/login", USER_NAME, USER_PW)
        chk("demo 登录成功（经 5173）", bool(utok))
        need(utok, "C 端登录失败")

        # --- 造一张【已支付未发货】的单（售后只可能发生在付过钱的单上）
        st, b, _ = api(PROXY_C, "GET", "/api/cart", token=utok)
        items = (data_of(b) or {}).get("items") or []
        found = next((it for it in items if it.get("skuId") == SKU), None)
        if not found:
            api(PROXY_C, "POST", "/api/cart", token=utok, body={"skuId": SKU, "quantity": 1})
            st, b, _ = api(PROXY_C, "GET", "/api/cart", token=utok)
            items = (data_of(b) or {}).get("items") or []
            found = next((it for it in items if it.get("skuId") == SKU), None)
            chk("加购成功（POST /api/cart）", bool(found))
        else:
            chk("购物车可读（SKU 已在车里）", True)
        need(found, "购物车里找不到 SKU %d" % SKU)
        api(PROXY_C, "PUT", "/api/cart/%s/selected" % found["id"], token=utok,
            body={"selected": True})

        st, b, _ = api(PROXY_C, "POST", "/api/orders", token=utok, body={"addressId": ADDRESS_ID})
        oid = data_of(b)
        oid = oid.get("id") if isinstance(oid, dict) else oid
        chk("下单成功（POST /api/orders）", bool(oid))
        need(oid, "没有拿到 orderId")
        oid = int(oid)
        created.append(oid)

        st, b, _ = api(PROXY_C, "POST", "/api/payments", token=utok,
                       body={"orderId": oid, "method": "ALIPAY"})
        chk("支付成功（POST /api/payments）", code_of(b) == 200)
        chk("DB：订单状态 PAID（未发货 ⇒ 只可能是【仅退款】）",
            order_row(oid)["status"] == "PAID")

        # --- ★ 类型 ↔ 订单状态 的匹配（前端把它锁成只读选项，后端仍要挡）
        st, b, _ = api(PROXY_C, "POST", "/api/refunds", token=utok,
                       body={"orderId": oid, "type": "RETURN_REFUND", "reason": "选错类型"})
        chk("★ 未发货却选【退货退款】→ code 400", code_of(b) == 400)
        chk("  报错指明该选【仅退款】（前端不必猜）", "仅退款" in msg_of(b))

        st, b, _ = api(PROXY_C, "POST", "/api/refunds", token=utok,
                       body={"orderId": oid, "type": "REFUND_ONLY", "reason": "前端联调：不想要了"})
        rid = data_of(b)
        chk("★ 正确类型申请成功（POST /api/refunds）", code_of(b) == 200 and bool(rid))
        need(rid, "没有拿到 refundId")

        st, b, _ = api(PROXY_C, "POST", "/api/refunds", token=utok,
                       body={"orderId": oid, "type": "REFUND_ONLY", "reason": "重复申请"})
        chk("★ 重复申请被挡（同一订单只能有一张进行中的售后单）→ 400", code_of(b) == 400)

        st, b, _ = api(PROXY_C, "GET", "/api/refunds/my?page=1&size=10", token=utok)
        recs = ((data_of(b) or {}).get("records") or [])
        mine = next((r for r in recs if str(r.get("id")) == str(rid)), None)
        chk("我的售后列表能看到这张单（GET /api/refunds/my）", bool(mine))
        # ★★ 字段名以 frontend/mall-app/src/types/api.d.ts 的 RefundVO 为准
        chk("★ 行内含前端 RefundVO 必需的 refundNo/type/status/amount/reason",
            bool(mine) and all(k in mine for k in ("refundNo", "type", "status", "amount", "reason")))

        st, _b, _ = api(PROXY_C, "GET", "/api/refunds/my?page=1&size=10")
        chk("匿名读「我的售后」→ 真 HTTP 401（不是 200）", st == 401)

        # ================================================== [B] 管理端：权限矩阵 + 审核 + 打款
        say("\n[B] 管理端（经 5174）—— 前端 RefundList.vue 实际用的字段")

        ptok = login(PROXY_A, "/api/auth/admin/login", OP_PRODUCT, OP_PRODUCT_PW)
        chk("op_product（商品管理员）登录成功", bool(ptok))
        st, _b, _ = api(PROXY_A, "GET", "/api/admin/refunds?page=1&size=10", token=ptok)
        # ★★ 反向对照：售后是订单域，商品管理员连【看】都不该看
        chk("★★ op_product 读售后列表 → 真 HTTP 403（18 号补丁第二节③）", st == 403)

        otok = login(PROXY_A, "/api/auth/admin/login", OP_ORDER, OP_ORDER_PW)
        chk("op_order（订单管理员）登录成功", bool(otok))
        need(otok, "op_order 登录失败")

        st, b, _ = api(PROXY_A, "GET", "/api/admin/refunds?page=1&size=10", token=otok)
        recs = ((data_of(b) or {}).get("records") or [])
        hit = next((r for r in recs if str(r.get("id")) == str(rid)), None)
        chk("op_order 能看到这张售后单（GET /api/admin/refunds）", bool(hit))
        # ★★ 字段名以 frontend/admin-app/src/types/api.d.ts 的 AdminRefundVO 为准
        #    （比 C 端 VO 多 orderNo / userNickname —— 运营要拿订单号去查、要联系买家）
        chk("★ 行内含前端 AdminRefundVO 必需的 refundNo/orderNo/type/status/amount",
            bool(hit) and all(k in hit for k in ("refundNo", "orderNo", "type", "status", "amount")))

        st, b, _ = api(PROXY_A, "POST", "/api/admin/refunds/%s/approve" % rid, token=otok)
        chk("审核通过（op_order 持 refund:approve）→ 200", code_of(b) == 200)

        st, b, _ = api(PROXY_A, "POST", "/api/admin/refunds/%s/approve" % rid, token=otok)
        chk("★ 重复审核通过被 CAS 挡 → 400（状态机不允许回退）", code_of(b) == 400)

        st, _b, _ = api(PROXY_A, "POST", "/api/admin/refunds/%s/approve" % rid, token=ptok)
        chk("★★ op_product 打【审核通过】→ 真 HTTP 403（动钱端点必须挡住）", st == 403)

        st, b, _ = api(PROXY_A, "POST", "/api/admin/refunds/%s/refund" % rid, token=otok)
        chk("★★★ 执行退款（全项目唯一动钱的售后端点）→ 200", code_of(b) == 200)

        st, b, _ = api(PROXY_A, "POST", "/api/admin/refunds/%s/refund" % rid, token=otok)
        chk("★ 重复打款被挡 → 400（同一张单不可能退两次）", code_of(b) == 400)

        # ================================================== [C] 跨端结果 + 对账
        say("\n[C] 跨端结果 + DB 对账（不信接口自报）")
        st, b, _ = api(PROXY_C, "GET", "/api/refunds/%s" % rid, token=utok)
        chk("C 端再查该售后单 → status=SUCCESS", (data_of(b) or {}).get("status") == "SUCCESS")
        chk("DB：orders 状态 = REFUNDED", order_row(oid)["status"] == "REFUNDED")
        # ★ 负向流水的价值：资金对账退化成「该单支付流水求和 = 0」
        chk("★ DB：该单 payments 求和 = 0（正向收款 + 负向退款）",
            dec(one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE order_id=%d" % oid)) == 0)
        chk("★ DB：库存已回补（available 回到下单前 %d）" % base_inv["available"],
            inv(SKU)["available"] == base_inv["available"])

        # ================================================== [D] 清理
        say("\n[D] 清理（★ 先确认已退款回补，再删单 —— 见 REF §9.2）")
        psql("DELETE FROM refunds WHERE id=%s" % rid)
        psql("DELETE FROM payments WHERE order_id=%d" % oid)
        psql("DELETE FROM order_items WHERE order_id=%d" % oid)
        psql("DELETE FROM orders WHERE id=%d" % oid)
        created.remove(oid)
        chk("清理完成（refunds/payments/order_items/orders 均已删）",
            one("SELECT count(*) FROM orders WHERE id=%d" % oid) == "0")

    except _Abort:
        pass
    finally:
        if created:
            say("  ⚠ 残留订单：%s（请手工核对库存基线）" % created)

    total = _CHECKS[0] + _CHECKS[1]
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (_CHECKS[0], total, EXPECTED_CHECKS))
    if total != EXPECTED_CHECKS:
        say("★ 护栏未过：实得 %d 条，期望 %d 条" % (total, EXPECTED_CHECKS))
    ok = _CHECKS[1] == 0 and total == EXPECTED_CHECKS
    say("VERDICT: %s" % ("OK" if ok else "FAIL"))
    say("=" * 78)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(_LINES) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
