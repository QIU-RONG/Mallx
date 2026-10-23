# -*- coding: utf-8 -*-
"""Day 56 本机端到端验证 —— 不依赖 Docker（用一个临时 PostgreSQL 实例 + 新构建的 jar）。

背景：本机没有 Docker 引擎，而既有验收脚本（day14/15/16）全部通过
`docker exec mallx-postgres psql` 读库 ⇒ 无法在本机复跑。本脚本改用：
  · 应用：`java -jar mall-server.jar --server.port=8081`（本机 8080 被别的项目占用）
  · 数据库：临时 PG 集群（127.0.0.1:5434，01→19 已初始化）
  · 读库：本地 psql（`MALLX_PSQL` 覆盖路径）

它覆盖三件事：
  [A] 管理端 10 个页面背后的接口全部可用（Day 54 五域 + 仪表盘）
  [B] C 端主链路：地址 → 加购 → 下单 → 支付 → 发货 → 收货 → 评价（真实业务路径）
  [C] Day 55 评价审核：隐藏 → C 端列表/平均分/计数同步回退 → 恢复 → 全部回来

用法：
    set MALLX_BASE=http://127.0.0.1:8081
    set MALLX_PSQL=D:\\PSQL\\bin\\psql.exe
    python day56-local-e2e.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.environ.get("MALLX_BASE", "http://127.0.0.1:8081")
PSQL = os.environ.get("MALLX_PSQL", "psql")
PGHOST = os.environ.get("MALLX_PGHOST", "127.0.0.1")
PGPORT = os.environ.get("MALLX_PGPORT", "5434")

n_pass = n_fail = 0
records = []


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        line = "[OK]   %s%s" % (name, ("   " + detail) if detail else "")
    else:
        n_fail += 1
        line = "[FAIL] %s   %s" % (name, detail)
    print(line)
    records.append(line)
    return ok


def http(method, path, token=None, body=None, expect_http=200):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status = r.getcode()
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {"_raw": raw[:200]}
    if status != expect_http:
        print("  ★ HTTP %s on %s %s -> %s" % (status, method, path, raw[:300]))
    return status, payload


def body_code(payload):
    return payload.get("code")


def sql_one(query):
    p = subprocess.run(
        [PSQL, "-h", PGHOST, "-p", PGPORT, "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-c", query],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("psql failed: %s\n%s" % (query, p.stderr))
    return p.stdout.strip()


def login(user, pwd, admin=False):
    path = "/api/auth/admin/login" if admin else "/api/auth/login"
    st, j = http("POST", path, body={"username": user, "password": pwd})
    return j.get("data", {}).get("token")


def main():
    print("=" * 78)
    print("Day 56 本机端到端验证 · BASE=%s · PG=%s:%s" % (BASE, PGHOST, PGPORT))
    print("=" * 78)

    # ---------------- [0] 启动与登录 ----------------
    print("\n[0] 健康与登录")
    st, j = http("GET", "/actuator/health")
    chk("0.1 /actuator/health = UP", j.get("status") == "UP", str(j.get("status")))

    admin = login("admin", "admin123", admin=True)
    demo = login("demo", "demo123")
    chk("0.2 管理员 admin/admin123 能登录（token 非空）", bool(admin), "tokenLen=%d" % (len(admin or "")))
    chk("0.3 买家 demo/demo123 能登录", bool(demo), "tokenLen=%d" % (len(demo or "")))
    if not admin or not demo:
        print("\n★ 登录失败，后续无法继续")
        return 1

    # ---------------- [A] 管理端接口面 ----------------
    print("\n[A] 管理端接口（Day 54 五域 + 仪表盘）")
    admin_gets = [
        ("商品列表", "/api/admin/products?current=1&size=5"),
        ("分类树", "/api/admin/categories/tree"),
        ("品牌字典", "/api/admin/brands"),
        ("券列表", "/api/admin/coupons?page=1&size=5"),
        ("用户列表", "/api/admin/users?current=1&size=5"),
        ("角色列表", "/api/admin/roles?current=1&size=5"),
        ("权限字典", "/api/admin/permissions"),
        ("评价列表", "/api/admin/reviews?current=1&size=5"),
        ("仪表盘概览", "/api/admin/dashboard/overview"),
    ]
    for label, path in admin_gets:
        st, j = http("GET", path, token=admin)
        chk("A.%s %s 200" % (label, path.split("?")[0]), st == 200 and body_code(j) == 200,
            "http=%s code=%s" % (st, body_code(j)))

    st, j = http("GET", "/api/admin/permissions", token=admin)
    perms = j.get("data") or []
    chk("A.10 权限字典共 51 条（Day 55 评价 2 条 + Day 64 店铺 3 条）", len(perms) == 51, "n=%d" % len(perms))
    codes = {p.get("code") for p in perms}
    chk("A.11 review:list / review:status 都在字典里",
        {"review:list", "review:status"} <= codes, "missing=%s" %
        ({"review:list", "review:status"} - codes))

    # ---------------- [B] C 端主链路 ----------------
    print("\n[B] C 端主链路（地址 → 加购 → 下单 → 支付 → 发货 → 收货 → 评价）")
    st, j = http("POST", "/api/addresses", token=demo, body={
        "receiverName": "E2E 测试", "receiverPhone": "13900000000",
        "province": "上海市", "city": "上海市", "district": "浦东新区",
        "detailAddress": "测试路 1 号", "isDefault": True})
    # ★ Result<Long>：data 直接是新地址 id（不是对象）
    address_id = j.get("data")
    chk("B.1 新增收货地址", st == 200 and body_code(j) == 200 and isinstance(address_id, int),
        "id=%s" % address_id)

    sku_id = sql_one(
        "SELECT s.id FROM product_skus s JOIN inventories i ON i.sku_id = s.id "
        "WHERE s.product_id = 1 AND s.status = 1 AND i.available_stock > 0 ORDER BY s.id LIMIT 1")
    chk("B.2 商品 1 有可售 SKU", bool(sku_id), "skuId=%s" % sku_id)

    st, j = http("POST", "/api/cart", token=demo, body={"skuId": int(sku_id), "quantity": 1})
    chk("B.3 加入购物车", st == 200 and body_code(j) == 200, "http=%s code=%s" % (st, body_code(j)))

    st, j = http("POST", "/api/orders", token=demo, body={"addressId": address_id})
    order_id = j.get("data")
    chk("B.4 从购物车下单（PENDING_PAYMENT）", st == 200 and body_code(j) == 200 and order_id,
        "orderId=%s code=%s" % (order_id, body_code(j)))

    st, j = http("POST", "/api/payments", token=demo, body={"orderId": order_id, "method": "ALIPAY"})
    chk("B.5 支付成功（order → PAID）", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    st, j = http("POST", "/api/orders/%s/ship" % order_id, token=admin)
    chk("B.6 管理员发货", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    st, j = http("POST", "/api/orders/%s/confirm" % order_id, token=demo)
    chk("B.7 买家确认收货（order → COMPLETED）", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    st, j = http("GET", "/api/orders/%s" % order_id, token=demo)
    detail = j.get("data") or {}
    items = detail.get("items") or []
    order_item_id = items[0].get("id") if items else None
    chk("B.8 订单详情含明细（可评价）", bool(order_item_id),
        "status=%s items=%d" % (detail.get("status"), len(items)))

    st, j = http("POST", "/api/reviews", token=demo,
                 body={"orderItemId": order_item_id, "rating": 5, "content": "E2E 测试评价，稍后会隐藏"})
    review_id = j.get("data", {}).get("id") if isinstance(j.get("data"), dict) else None
    chk("B.9 发表评价（5 星）", st == 200 and body_code(j) == 200 and review_id, "reviewId=%s" % review_id)

    # ---------------- [C] 评价审核（Day 55） ----------------
    print("\n[C] 评价审核：隐藏 → 三处同步 → 恢复 → 全部回来")
    st, j = http("GET", "/api/products/1/reviews?page=1&size=100")
    page = j.get("data") or {}
    before_count = page.get("reviewCount")
    chk("C.1 隐藏前：C 端评价数 ≥1 且平均分 5.0",
        before_count and before_count >= 1 and float(page.get("avgRating") or 0) == 5.0,
        "count=%s avg=%s" % (before_count, page.get("avgRating")))

    st, j = http("PUT", "/api/admin/reviews/%s/status" % review_id, token=admin, body={"status": 0})
    chk("C.2 管理员隐藏该评价", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    st, j = http("GET", "/api/products/1/reviews?page=1&size=100")
    page2 = j.get("data") or {}
    ids = {r.get("id") for r in (page2.get("records") or [])}
    chk("C.3 隐藏后：C 端评价数 -1 且记录消失",
        page2.get("reviewCount") == before_count - 1 and review_id not in ids,
        "count=%s (before=%s)" % (page2.get("reviewCount"), before_count))
    chk("C.4 隐藏后：平均分随实时聚合回退（无评价时 0）",
        float(page2.get("avgRating") or 0) == (5.0 if page2.get("reviewCount") else 0.0),
        "avg=%s" % page2.get("avgRating"))

    st, j = http("GET", "/api/admin/reviews?current=1&size=50&status=0", token=admin)
    hidden_ids = {r.get("id") for r in (j.get("data", {}).get("records") or [])}
    chk("C.5 管理端 status=0 能看到它（不是单向失明）", review_id in hidden_ids,
        "hidden=%s" % sorted(hidden_ids)[:5])

    st, j = http("PUT", "/api/admin/reviews/%s/status" % review_id, token=admin, body={"status": 1})
    st2, j2 = http("GET", "/api/products/1/reviews?page=1&size=100")
    page3 = j2.get("data") or {}
    ids3 = {r.get("id") for r in (page3.get("records") or [])}
    chk("C.6 恢复后：评价数回到原值且记录重新出现",
        j.get("code") == 200 and page3.get("reviewCount") == before_count and review_id in ids3,
        "count=%s avg=%s" % (page3.get("reviewCount"), page3.get("avgRating")))

    # ---------------- [D] Day 54 写接口冒烟 ----------------
    print("\n[D] Day 54 写接口冒烟（分类 / 品牌 / 券）")
    st, j = http("POST", "/api/admin/categories", token=admin,
                 body={"parentId": 1, "name": "E2E 子分类", "sortOrder": 99})
    cat_id = j.get("data")
    chk("D.1 新建二级分类", st == 200 and body_code(j) == 200 and cat_id, "id=%s" % cat_id)
    st, j = http("PUT", "/api/admin/categories/%s" % cat_id, token=admin,
                 body={"name": "E2E 子分类（改名）"})
    chk("D.2 改分类名（局部更新）", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))
    st, j = http("DELETE", "/api/admin/categories/%s" % cat_id, token=admin)
    chk("D.3 删分类（无引用可物理删）", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    st, j = http("POST", "/api/admin/brands", token=admin, body={"name": "E2E 品牌"})
    brand_id = j.get("data")
    chk("D.4 新建品牌", st == 200 and body_code(j) == 200 and brand_id, "id=%s" % brand_id)
    st, j = http("POST", "/api/admin/brands", token=admin, body={"name": "E2E 品牌"})
    chk("D.5 重名品牌 → 400（UNIQUE 被翻译成人话，不是 500）",
        st == 200 and body_code(j) == 400, "code=%s" % body_code(j))
    st, j = http("DELETE", "/api/admin/brands/%s" % brand_id, token=admin)
    chk("D.6 删品牌（无商品引用）", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    st, j = http("POST", "/api/admin/coupons", token=admin, body={
        "name": "E2E 满减券", "type": "FIXED", "discountAmount": 10, "minAmount": 0,
        "totalCount": 10, "startTime": "2026-10-01T00:00:00", "endTime": "2026-12-31T23:59:59"})
    coupon_id = j.get("data")
    chk("D.7 新建满减券（FIXED）", st == 200 and body_code(j) == 200 and coupon_id, "id=%s" % coupon_id)
    st, j = http("POST", "/api/admin/coupons", token=admin, body={
        "name": "E2E 非法券", "type": "FIXED", "discountAmount": 10, "discountRate": 0.8,
        "totalCount": 10, "startTime": "2026-10-01T00:00:00", "endTime": "2026-12-31T23:59:59"})
    chk("D.8 两个面额字段同时出现 → 400（后端关系校验）",
        st == 200 and body_code(j) == 400, "code=%s" % body_code(j))
    st, j = http("DELETE", "/api/admin/coupons/%s" % coupon_id, token=admin)
    chk("D.9 删券（未被领取）", st == 200 and body_code(j) == 200, "code=%s" % body_code(j))

    # ---------------- [E] 越权面 ----------------
    print("\n[E] 越权面（前端显隐不是边界，后端才是）")
    # ★ 401 与 403 的分工（项目判据）：匿名 = 401（过滤器层不知道你是谁）；
    #   合法 C 端 token = 已认证、但没有管理端权限码 ⇒ 403。
    #   E.1 的第一版断言写的是 401 —— 实测 403 才是对的，改的是断言不是代码。
    st, j = http("GET", "/api/admin/reviews?current=1&size=1", token=demo, expect_http=403)
    chk("E.1 C 端 token 打管理端接口 → 403（已认证但无权限码）", st == 403, "http=%s" % st)
    st, j = http("GET", "/api/admin/reviews?current=1&size=1")
    chk("E.2 匿名打管理端接口 → 401", st == 401, "http=%s" % st)

    # ---------------- 汇总 ----------------
    print("\n" + "=" * 78)
    print("ASSERTIONS: %d / %d passed" % (n_pass, n_pass + n_fail))
    print("VERDICT: %s" % ("OK —— 管理端接口面 / C 端主链路 / 评价审核 全部通过"
                          if n_fail == 0 else "FAIL —— %d 条未过" % n_fail))
    print("=" * 78)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "day56-local-e2e-report.txt"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write("\n".join(records) + "\n\nASSERTIONS: %d / %d passed\nVERDICT: %s\n"
                % (n_pass, n_pass + n_fail, "OK" if n_fail == 0 else "FAIL"))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
