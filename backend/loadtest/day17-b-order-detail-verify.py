# -*- coding: utf-8 -*-
"""Day 17 · 链路 B 验收 —— `GET /api/admin/orders/{id}`（管理端订单详情 · 复用 buildDetail）

本脚本的**核心**是一组对照实验，而不是"返回 200 就算过"：

    同一个订单 id（它属于 users.id = 1 = demo），四个身份 × 两个端点：

      调用者                                端点                      期望
      demo（属主）                          GET /api/orders/{id}      200 + code 200
      intruder（user_id=2，非属主）          GET /api/orders/{id}      200 + code **404**  ← C 端【伪装】
      op_order（admins.id=2，非属主管理员）  GET /api/admin/orders/{id} 200 + code **200**  ← 管理端【不筛】
      admin（超管）                          GET /api/admin/orders/{id} 200 + code 200

★★ 为什么必须用 op_order 而不是 admin：
   实测 admins.id = 1，而所有订单的 user_id 也全是 1 —— 两个数字【撞在一起】。
   若 detailByAdmin 被错写成 requireOwn(当前登录管理员id, orderId)，
   用 admin 测会因 1 = 1 照样返回 200，**永远发现不了这个降级**。
   op_order 的 id = 2 ≠ 1，用它取 user_id=1 的订单：
       正确实现 → 200
       降级实现 → 404
   所以「op_order 拿到 200」这一条，才是「管理端详情不做归属过滤」真正的判别力所在。

其他的三层判据（与本项目其余验收脚本一致）：
    ① 真 HTTP 状态码 vs HTTP 200 + body.code 分开判；
    ② 14 个字段（+ items 的 9 个字段）逐个与 DB 比，不采信接口自报；
    ③ 完整性与边界：VO 不含 userId；不存在 id → 业务 404；/abc → 业务 400。
"""
from _paths import lp
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = lp(r"D:\MallX\backend\loadtest\day17-b-order-detail-verify-report.txt")

import os
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# OrderDetailVO 的 15 个字段（= 出参白名单，★ 刻意不含 userId）
# ★ 2026-09-24（Day 22 · L7）：14 → 15，新增 discountAmount。
#   这里修掉的是一处【回归盲区】：本脚本不在 day17-m1-regression.py 的名单里
#   （M1 只跑 day14/15/16 三个 E2E），所以给 OrderDetailVO 加字段时，
#   **没有任何自动回归会因为我漏改这个常量而报警**。
#   ⇒ 通用教训：改动出参 VO 的字段集后，必须 grep 全项目找「键集合相等」式断言
#     （`set(...keys()) ==`）并逐个同步。这类断言是【双向】的 ——
#     少一个字段 FAIL，多一个字段同样 FAIL（它验的是「白名单」而不是「至少包含」）。
DETAIL_FIELDS = ["id", "orderNo", "totalAmount", "payAmount", "discountAmount", "status",
                 "receiverName", "receiverPhone", "receiverAddress",
                 "createdAt", "paidAt", "shippedAt", "completedAt", "cancelledAt", "items"]
# 订单头里【允许为 null】的字段（未流转的节点；不做假默认值）
NULLABLE_HEAD = {"paidAt", "shippedAt", "completedAt", "cancelledAt"}

# OrderItemVO 的 9 个字段
ITEM_FIELDS = ["id", "productId", "skuId", "productName", "skuName",
               "price", "quantity", "totalAmount", "image"]
NULLABLE_ITEM = {"image"}

lines = []
say = lines.append
checks = []


def ck(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    say("  %s %-58s %s" % ("✅" if ok else "❌", name, detail))


def req(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with opener.open(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                            # noqa: BLE001
        return -1, "%s: %s" % (type(e).__name__, e)


def wait_app(deadline=180):
    t0 = time.time()
    while time.time() - t0 < deadline:
        if req("GET", "/api/hello")[0] != -1:
            return True, time.time() - t0
        time.sleep(2)
    return False, time.time() - t0


def login(path, username, password):
    code, body = req("POST", path, body={"username": username, "password": password})
    try:
        j = json.loads(body)
    except Exception:                                                 # noqa: BLE001
        return None, "HTTP %s / 非 JSON: %s" % (code, body[:160])
    if j.get("code") != 200:
        return None, "登录失败(%s): %s" % (code, body[:160])
    return j["data"]["token"], "OK"


def psql(sql):
    p = subprocess.run([DOCKER, "exec", "-i", CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("psql 失败: %s" % (p.stderr or "")[:300])
    return [r for r in (p.stdout or "").strip().splitlines() if r.strip()]


def call(path, token=None):
    """返回 (http_code, parsed_json_or_raw_text)。"""
    code, body = req("GET", path, token=token)
    try:
        return code, json.loads(body)
    except Exception:                                                 # noqa: BLE001
        return code, body


def biz(j):
    return j.get("code") if isinstance(j, dict) else ("<非JSON:%s>" % str(j)[:60])


def ts(s):
    """时间戳归一：JSON 的 T 与 DB 的空格统一，比到秒。"""
    return str(s or "").replace("T", " ")[:19]


say("=" * 78)
say("Day 17 · 链路 B 验收 —— GET /api/admin/orders/{id}")
say("=" * 78)

# ============ 0. 应用可达 ============
ok, secs = wait_app()
say("应用可达: %s（等待 %.1fs）" % ("是" if ok else "否", secs))
if not ok:
    say("❌ 应用没起来，中止。")
    print("\n".join(lines))
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    raise SystemExit(1)
say("")

# ============ 1. DB 基线 ============
head = {}
for r in psql("SELECT id, order_no, user_id, total_amount, pay_amount, discount_amount, status, "
              "receiver_name, "
              "receiver_phone, receiver_address, created_at, paid_at, shipped_at, completed_at, "
              "cancelled_at FROM orders ORDER BY id;"):
    f = r.split("|")
    head[int(f[0])] = dict(zip(
        ["id", "orderNo", "userId", "totalAmount", "payAmount", "discountAmount", "status",
         "receiverName",
         "receiverPhone", "receiverAddress", "createdAt", "paidAt", "shippedAt",
         "completedAt", "cancelledAt"], f))

items = {}
for r in psql("SELECT id, order_id, product_id, sku_id, product_name, sku_name, price, quantity, "
              "total_amount, COALESCE(image,'') FROM order_items ORDER BY order_id, id;"):
    f = r.split("|")
    items.setdefault(int(f[1]), []).append(dict(zip(
        ["id", "productId", "skuId", "productName", "skuName", "price", "quantity",
         "totalAmount", "image"], [f[0], f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9]])))

say("[1] DB 基线")
say("      orders %d 张；归属 user_id 集合 = %s；明细共 %d 条"
    % (len(head), sorted({v["userId"] for v in head.values()}), sum(len(v) for v in items.values())))
say("      逐单明细条数 = %s" % {k: len(v) for k, v in sorted(items.items())})
say("")

# ============ 2. 登录四个身份 ============
demo_token, m1 = login("/api/auth/login", "demo", "demo123")
intr_token, m2 = login("/api/auth/login", "intruder", "intruder")
admin_token, m3 = login("/api/auth/admin/login", "admin", "admin123")
op_token, m4 = login("/api/auth/admin/login", "op_order", "op123456")
say("[2] 登录  demo:%s  intruder:%s  admin:%s  op_order:%s" % (m1, m2, m3, m4))
ck("四个身份全部登录成功", all([demo_token, intr_token, admin_token, op_token]),
   "op_order token 可用于权限矩阵")
if not op_token:
    say("      ⚠️ op_order 登录失败 —— 请先跑 day17-fixture-apply.py（06-day17-fixtures.sql）")
say("")

op_id = int(psql("SELECT id FROM admins WHERE username='op_order';")[0])
sample_ids = sorted(head.keys(), reverse=True)
probe_id = 9005 if 9005 in head else sample_ids[0]
probe_owner = head[probe_id]["userId"]
say("[3] 判别力前提（实测，不假设）")
say("      op_order 的 admins.id = %d ；订单 %d 的 user_id = %s"
    % (op_id, probe_id, probe_owner))
ck("op_order.id ≠ 该订单的 user_id（降级实现会被这条抓出来）",
   op_id != int(probe_owner), "%d vs %s" % (op_id, probe_owner))
say("")

# ============ 4. 权限三态（真 HTTP 状态码） ============
say("[4] 权限三态 —— /api/admin/orders/%d" % probe_id)
c, _ = req("GET", "/api/admin/orders/%d" % probe_id)
ck("匿名（不带头）-> 真 HTTP 401", c == 401, "实得 %s" % c)
c, _ = req("GET", "/api/admin/orders/%d" % probe_id, token=demo_token)
ck("C 端 demo token -> 真 HTTP 403", c == 403, "实得 %s" % c)
c, _ = req("GET", "/api/admin/orders/%d" % probe_id, token=intr_token)
ck("C 端 intruder token -> 真 HTTP 403", c == 403, "实得 %s" % c)
say("")

# ============ 5. ★★ 数据权限反转：对照实验 ============
say("[5] ★★ 数据权限反转 —— 同一订单 id，四个身份 × 两个端点")
cases = [
    ("demo",     "demo（属主）                C 端", "/api/orders/%d" % probe_id, demo_token, 200, 200),
    ("intruder", "intruder（非属主）          C 端", "/api/orders/%d" % probe_id, intr_token, 200, 404),
    ("op_order", "op_order（非属主管理员）    管理端", "/api/admin/orders/%d" % probe_id, op_token, 200, 200),
    ("admin",    "admin（超管）              管理端", "/api/admin/orders/%d" % probe_id, admin_token, 200, 200),
]
bodies = {}
for key, label, path, tok, exp_http, exp_code in cases:
    http, j = call(path, token=tok)
    bodies[key] = j
    ck("%-32s -> HTTP %s + code %s" % (label, exp_http, exp_code),
       http == exp_http and biz(j) == exp_code, "实得 HTTP %s + code %s" % (http, biz(j)))

say("")
say("      ★ 两条关键推论：")
ck("C 端非属主被伪装成 404（读越权防护）", biz(bodies["intruder"]) == 404,
   "code=%s" % biz(bodies["intruder"]))
ck("★ 管理端【不筛归属】：非属主管理员拿到 200（不是 404）",
   biz(bodies["op_order"]) == 200, "op_order code=%s" % biz(bodies["op_order"]))
ck("管理端两身份返回的详情体逐字节相同（与调用者是谁无关）",
   json.dumps(bodies["op_order"], sort_keys=True, ensure_ascii=False) ==
   json.dumps(bodies["admin"], sort_keys=True, ensure_ascii=False))
say("")

# ============ 6. 防枚举：C 端 404 与「不存在 id」逐字节相同 ============
say("[6] 防枚举 —— C 端「不是你的单」与「不存在的单」必须不可区分")
_, j_other = call("/api/orders/%d" % probe_id, token=intr_token)
_, j_absent = call("/api/orders/99999999", token=demo_token)
ck("两者 HTTP 200 + code 404", biz(j_other) == 404 and biz(j_absent) == 404,
   "%s / %s" % (biz(j_other), biz(j_absent)))
ck("两者响应体逐字节相同（★ 否则可遍历 id 画出「哪些单真实存在」的地图）",
   json.dumps(j_other, sort_keys=True, ensure_ascii=False) ==
   json.dumps(j_absent, sort_keys=True, ensure_ascii=False),
   "%s | %s" % (json.dumps(j_other, ensure_ascii=False)[:70],
                json.dumps(j_absent, ensure_ascii=False)[:70]))
say("")

# ============ 7. 管理端详情逐字段对账（覆盖全部订单） ============
say("[7] ★ 逐单逐字段对账（管理端，14 个字段 + items 9 个字段）")
keyset_bad, null_bad, val_bad, item_bad, seen_data = [], [], [], [], []
for oid in sample_ids:
    http, j = call("/api/admin/orders/%d" % oid, token=admin_token)
    if http != 200 or biz(j) != 200:
        val_bad.append("id=%s HTTP=%s code=%s" % (oid, http, biz(j)))
        continue
    d = j["data"]
    seen_data.append(d)
    if set(d.keys()) != set(DETAIL_FIELDS):
        keyset_bad.append((oid, sorted(set(DETAIL_FIELDS) ^ set(d.keys()))))
    for k in DETAIL_FIELDS:
        if d.get(k) is None and k not in NULLABLE_HEAD:
            null_bad.append("id=%s 字段 %s 为 null" % (oid, k))
    db = head[oid]
    for api_k, db_k in [("id", "id"), ("orderNo", "orderNo"), ("status", "status"),
                        ("receiverName", "receiverName"), ("receiverPhone", "receiverPhone"),
                        ("receiverAddress", "receiverAddress"),
                        ("createdAt", "createdAt"), ("paidAt", "paidAt"),
                        ("shippedAt", "shippedAt"), ("completedAt", "completedAt"),
                        ("cancelledAt", "cancelledAt")]:
        if api_k in ("id",):
            continue
        if ts(d.get(api_k)) != ts(db[db_k]):
            val_bad.append("id=%s %s %r != %r" % (oid, api_k, d.get(api_k), db[db_k]))
    # ★ Day 22 · L7：discountAmount 也纳入逐字段对账 —— 给 VO 加了字段就【必须】加对账，
    #   否则「字段存在但值恒为 null/0」这类错没有任何断言看得见。
    #   本日实测踩过：VO 有字段、setter 漏写（并发 Edit 丢写）⇒ 接口返回
    #   discountAmount=null，而上面那条「键集合相等」断言照样 PASS。
    #   ⇒ 键集合断言证明的是「字段在不在」，数值对账证明的才是「值对不对」。
    for k in ("totalAmount", "payAmount", "discountAmount"):
        try:
            if abs(float(d.get(k)) - float(db[k])) > 0.001:
                val_bad.append("id=%s %s %s != %s" % (oid, k, d.get(k), db[k]))
        except Exception:                                             # noqa: BLE001
            val_bad.append("id=%s %s 无法比较: %r" % (oid, k, d.get(k)))
    if str(d.get("id")) != str(db["id"]):
        val_bad.append("id 不符 %s != %s" % (d.get("id"), db["id"]))

    # ---- items ----
    db_items = items.get(oid, [])
    api_items = d.get("items") or []
    if len(api_items) != len(db_items):
        item_bad.append("id=%s items 条数 %d != DB %d" % (oid, len(api_items), len(db_items)))
        continue
    for ai, di in zip(api_items, db_items):
        if set(ai.keys()) != set(ITEM_FIELDS):
            item_bad.append("id=%s item key 集合不符 %s" % (oid, sorted(ai.keys())))
        for ik in ITEM_FIELDS:
            if ik in NULLABLE_ITEM:
                continue
            if ai.get(ik) is None:
                item_bad.append("id=%s item.%s 为 null" % (oid, ik))
        for api_k, db_k in [("id", "id"), ("productName", "productName"), ("skuName", "skuName"),
                            ("quantity", "quantity"), ("price", "price"),
                            ("totalAmount", "totalAmount")]:
            av, dv = ai.get(api_k), di[db_k]
            if api_k in ("price", "totalAmount"):
                try:
                    if abs(float(av) - float(dv)) > 0.001:
                        item_bad.append("id=%s item.%s %s != %s" % (oid, api_k, av, dv))
                except Exception:                                     # noqa: BLE001
                    item_bad.append("id=%s item.%s 无法比较 %r" % (oid, api_k, av))
            elif str(av) != str(dv):
                item_bad.append("id=%s item.%s %r != %r" % (oid, api_k, av, dv))
        # productId / skuId 与 DB 比
        if str(ai.get("productId")) != str(di["productId"]):
            item_bad.append("id=%s item.productId %r != %r" % (oid, ai.get("productId"), di["productId"]))
        if str(ai.get("skuId")) != str(di["skuId"]):
            item_bad.append("id=%s item.skuId %r != %r" % (oid, ai.get("skuId"), di["skuId"]))

ck("每次返回的 key 集合 == VO 的 14 字段", not keyset_bad, str(keyset_bad[:2]))
ck("★ VO 不含 userId（%d 单全覆盖，key 集合里没有它）" % len(seen_data),
   all("userId" not in d for d in seen_data), "%d 单" % len(seen_data))
ck("无 null 字段（未流转的时间戳除外）", not null_bad, str(null_bad[:3]))
ck("订单头 13 个标量字段逐个与 DB 一致", not val_bad, str(val_bad[:3]))
ck("items 逐条逐字段与 DB 一致（含 9006 的 2 条明细）", not item_bad, str(item_bad[:3]))
say("      覆盖订单 = %s" % sample_ids)
say("")

# ============ 8. 边界：不存在 id / 非数字 id ============
say("[8] 边界（HTTP 200 + body.code，不是真 404/400）")
http, j = call("/api/admin/orders/99999999", token=admin_token)
ck("不存在的 id -> HTTP 200 + code 404", http == 200 and biz(j) == 404,
   "HTTP %s + code %s" % (http, biz(j)))
http, j = call("/api/admin/orders/abc", token=admin_token)
ck("非数字 id /abc -> HTTP 200 + code 400", http == 200 and biz(j) == 400,
   "HTTP %s + code %s" % (http, biz(j)))
say("")

# ============ 汇总 ============
bad = [c for c in checks if not c[1]]
say("=" * 78)
if bad:
    say("VERDICT: FAIL —— %d / %d 项不符" % (len(bad), len(checks)))
    for n, _, d in bad:
        say("   · %s   %s" % (n, d))
else:
    say("VERDICT: OK —— %d / %d 项全过" % (len(checks), len(checks)))
    say("  复用路线成立：detail 与 detailByAdmin 共用 buildDetail；管理端不过滤归属；")
    say("  C 端防枚举不变；14+9 字段全部与 DB 对账通过。")
say("=" * 78)

report = "\n".join(lines)
print(report)
open(REPORT, "w", encoding="utf-8").write(report + "\n")
raise SystemExit(0 if not bad else 1)
