# -*- coding: utf-8 -*-
"""Day 27 · 性能基线：索引到底有没有被用上（EXPLAIN ANALYZE 复盘）。

为什么需要它
------------
`docs/perf-report.md` §五 已经写了「本项目用了三件索引」，但**没有一条 EXPLAIN 证据**。
而且那里还写着一句自我安慰式的话：「小表上看不到索引不是做错了」——
`products` 只有 5 行，`EXPLAIN` 一定选 `Seq Scan`。

★ 问题在于：**这句话让「索引没被用上」永远无法被证伪。**
  5 行时是「正常」，30 万行时也可能被同一句话糊过去。
  ⇒ 判据（与 backlog 里 L1 的「样本量陷阱」同源）：
    **要验「索引有没有被用上」，样本必须大到、且分布必须让索引有胜算。**

★★ 第一版脚本自己就踩了这个坑（2026-09-26 实跑记录）：
  第一版把 `category_id` 只分布在 5 个分类上、`status` 二值、`iphone` 写进了
  **每一个**商品名 —— 于是每条谓词的命中率都是 20%~100%，计划器**拒绝使用任何索引**，
  12 条查询里 10 条「未命中」。
  **那是计划器对，不是索引错。** 低选择性列上走索引只会更慢。
  ⇒ 所以本版**先造出有选择性的分布**，并把「选择性」本身做成断言（见 [4b]）。

做法（★ 零副作用）
------------------
临时库 `mallx_perf_probe`（与 `day25-sql-strict-check.py` 同一套路）→ 灌 01→14
→ 造数到有区分度的量级 → `ANALYZE` → 13 条查询逐条 `EXPLAIN (ANALYZE, BUFFERS)`
→ DROP DATABASE。**不碰开发库的任何数据。**

★ 断言对着「设计」写，分两类：
  · **正向** `INDEX:<名>`     —— 该索引就是为这条查询建的 ⇒ 计划里必须出现它；
  · **反向对照** `NOT_INDEX:<名>` —— 这条查询设计上就**不该**用某个索引
    （前导 `%` 废掉 B-tree、`OR` 挡住索引、低选择性列）⇒ 计划里**必须不出现**它。
    没有这一类，就无法区分「索引没用」与「**索引被查询写法挡住了**」。

运行：python day27-explain-audit.py
前置：容器 mallx-postgres 在运行（**不需要**应用在跑）。
"""
from _paths import lp
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
ADMIN_DB = "mallx"
PROBE_DB = "mallx_perf_probe"          # ★ 临时库，跑完就删
SQL_DIR = lp(r"D:\MallX\backend\sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day27-explain-audit-report.txt")

FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

# ---- 规模与【选择性】（★ 不是「越大越好」，是「必须让索引有胜算」）----
N_CATEGORIES = 300       # 3 万商品 / 300 分类 ≈ 100 行/分类 ⇒ category_id 有选择性
N_USERS = 5000           # 3 万订单 / 5000 用户 = 6 行/用户   ⇒ user_id 有选择性
N_PRODUCTS = 30000
N_ORDERS = 30000
N_LOGS = 60000
N_REVIEWS = 20000
RARE_PCT = 1000          # 每 1000 个里 1 个 ⇒ 约 0.1%
# ★★ 选择性是【造出来的】，不是随手写的 —— 这里有一段实测：
#    第一版用 1%（30000 行里 300 行），13 条查询里 10 条「未命中」——
#    因为每条谓词都命中 20%~100%，**计划器拒绝使用任何索引**（它是对的）。
#    ⇒ 判据①：**审计脚本自己必须先让样本落在判据的取值域里**，
#      否则断言只是在测自己的造数，不是在测索引。
#    改成 0.1% 之后大部分查询命中。
#
# ★★ 另一段更值钱的实测：前几轮 Q4/R2/Q8b 的计划在 GIN 与 Seq Scan 之间来回翻转，
#    当时归因为「计划器临界区 + 统计噪声」。**那个解释是错的。**
#    真正原因：批量灌数后 GIN 索引的 fastupdate【待处理列表】没清 ——
#    GIN 扫 32 行要 13.3ms / 298 次 buffer 命中；`VACUUM` 之后同一条查询降到 0.9ms / 19 次。
#    ⇒ 判据②：**现象不稳定时，先怀疑「被测对象处于未整理状态」，
#      再怀疑「它本来就不确定」** —— 后者更省事，但通常是把测量误差当成了系统性质。

EXPECTED_CHECKS = 38     # ★ 满额护栏

lines = []
say = lines.append
n_pass = n_fail = 0
FINDINGS = []
PROBES = []


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def psql(db, sql_text, stop=True, timeout=900):
    """把 SQL 用 stdin 灌给 psql。★ 不走命令行：命令行会撞 PS 的 % 展开坑。"""
    args = [DOCKER, "exec", "-i",
            "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql",
            "-U", DB_USER, "-d", db]
    if stop:
        args += ["-v", "ON_ERROR_STOP=1"]
    args += ["-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    out = (p.stdout or "").replace("\r", "").strip()
    err = (p.stderr or "").replace("\r", "").strip()
    return p.returncode, out, err


def one(sql):
    rc, out, err = psql(PROBE_DB, sql)
    if rc != 0:
        raise RuntimeError("SQL 失败 rc=%d err=%s\n%s" % (rc, err[:400], sql[:200]))
    return out.splitlines()[0] if out else ""


# ------------------------------------------------------------------ 造数
# ⚠️ 下面凡是【不做 %-格式化】的 SQL 片段，% 一律写【单个】；
#    只有被 `% (...)` 格式化过的字符串才需要写 `%%`。混了就是
#    `operator does not exist: bigint %% integer`（本脚本第一版实测踩过）。
SEEDS = [
    ("维表：%d 个分类" % N_CATEGORIES, """
INSERT INTO categories (parent_id, name, sort_order, status)
SELECT NULL, 'PERF-分类-' || g, 0, 1 FROM generate_series(1, %d) g;
""" % N_CATEGORIES),

    ("维表：%d 个用户" % N_USERS, """
INSERT INTO users (username, password, nickname, phone, email, status)
SELECT 'perfuser' || g, 'x', 'PERF', '139' || lpad(g::text, 8, '0'),
       'perf' || g || '@example.com', 1
FROM generate_series(1, %d) g;
""" % N_USERS),

    # ★ 选择性设计：iphone 只进 1% 的名字；笔记本只进 1%；平板只进 1% 的 description；
    #   status=1 占 99%（低选择性，专门用来做反向对照）
    ("商品 %d 行（含 1%% 稀有词）" % N_PRODUCTS, """
INSERT INTO products (category_id, brand_id, name, subtitle, description, main_image, status, is_deleted)
SELECT (SELECT id FROM categories ORDER BY id OFFSET (g %% (SELECT count(*) FROM categories)) LIMIT 1),
       (SELECT id FROM brands     ORDER BY id OFFSET (g %% GREATEST((SELECT count(*) FROM brands),1)) LIMIT 1),
       'PERF-商品-' || g || ' 手机'
         || CASE WHEN g %% %d = 0 THEN ' iphone' ELSE '' END
         || CASE WHEN g %% %d = 1 THEN ' 笔记本' ELSE '' END,
       'PERF-副标题-' || g || ' 轻薄便携',
       'PERF-描述-' || g || ' 高性能办公'
         || CASE WHEN g %% %d = 2 THEN ' 平板' ELSE '' END,
       '/img/perf-' || g || '.jpg',
       CASE WHEN g %% 100 = 3 THEN 0 ELSE 1 END,
       0
FROM generate_series(1, %d) g;
""" % (RARE_PCT, RARE_PCT, RARE_PCT, N_PRODUCTS)),

    ("SKU x2/商品（黑色 0.05%）", """
INSERT INTO product_skus (product_id, sku_code, name, price, original_price, attributes, image, status, is_deleted)
SELECT p.id, 'PERF-SKU-' || p.id || '-' || k, 'PERF-SKU', 100.00 + k, 200.00,
       jsonb_build_object('color',
           CASE WHEN p.id % 2000 = 0 THEN '黑色' ELSE '白色' END),
       '/img/perf-sku.jpg', 1, 0
FROM products p CROSS JOIN generate_series(1, 2) k
WHERE p.name LIKE 'PERF-%';
"""),

    ("库存 x1/SKU", """
INSERT INTO inventories (sku_id, total_stock, available_stock, locked_stock, sold_stock)
SELECT s.id, 100, 100, 0, 0 FROM product_skus s WHERE s.sku_code LIKE 'PERF-%';
"""),

    # ★ PENDING_PAYMENT 只占 1%，否则超时关单扫描无从判断索引有没有被用上
    ("订单 %d 行（PENDING 1%%）" % N_ORDERS, """
INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status,
                    receiver_name, receiver_phone, receiver_address, created_at, updated_at)
SELECT 'PERF-ORD-' || g,
       (SELECT id FROM users ORDER BY id OFFSET (g %% (SELECT count(*) FROM users)) LIMIT 1),
       100.00, 100.00,
       CASE WHEN g %% 100 = 0 THEN 'PENDING_PAYMENT' ELSE 'PAID' END,
       'PERF', '13000000000', 'PERF 地址',
       CURRENT_TIMESTAMP - (g || ' minutes')::interval,
       CURRENT_TIMESTAMP - (g || ' minutes')::interval
FROM generate_series(1, %d) g;
""" % N_ORDERS),

    # ★ 必须按 row_number 对齐再 JOIN。写成 `orders JOIN product_skus ON sku_code LIKE ...`
    #   会先产生 3万 x 6万 = 18 亿行的中间结果（笛卡尔），直接跑死。
    ("明细 x1/订单", """
INSERT INTO order_items (order_id, product_id, sku_id, product_name, sku_name, price, quantity, total_amount, image)
SELECT o.id, s.product_id, s.id, 'PERF-商品', 'PERF-SKU', 100.00, 1, 100.00, '/img/perf.jpg'
FROM (SELECT id, row_number() OVER (ORDER BY id) rn
        FROM orders WHERE order_no LIKE 'PERF-%') o
JOIN (SELECT id, product_id, row_number() OVER (ORDER BY id) rn
        FROM product_skus WHERE sku_code LIKE 'PERF-%') s
  ON s.rn = o.rn;
"""),

    ("库存流水 %d 行（1 条/SKU）" % N_LOGS, """
INSERT INTO inventory_logs (sku_id, change_quantity, before_stock, after_stock, type, reference_id, created_at)
SELECT s.id, -1, 100 - (g %% 50), 99 - (g %% 50), 'ORDER_LOCK', NULL,
       CURRENT_TIMESTAMP - (g || ' minutes')::interval
FROM generate_series(1, %d) g
JOIN (SELECT id, row_number() OVER (ORDER BY id) rn
        FROM product_skus WHERE sku_code LIKE 'PERF-%%') s
  ON s.rn = 1 + (g %% 60000);
""" % N_LOGS),

    ("评价 %d 行" % N_REVIEWS, """
INSERT INTO reviews (user_id, product_id, order_id, order_item_id, rating, content, status)
SELECT o.user_id, oi.product_id, oi.order_id, oi.id, 5, 'PERF 评价', 1
FROM order_items oi JOIN orders o ON o.id = oi.order_id
WHERE o.order_no LIKE 'PERF-%%'
ORDER BY oi.id
LIMIT %d;
""" % N_REVIEWS),
]

CAT1 = "(SELECT id FROM categories ORDER BY id LIMIT 1)"
USER1 = "(SELECT id FROM users ORDER BY id LIMIT 1)"
ORDER1 = "(SELECT id FROM orders ORDER BY id LIMIT 1)"
SKU1 = "(SELECT id FROM product_skus WHERE sku_code LIKE 'PERF-%' ORDER BY id LIMIT 1)"
PROD1 = "(SELECT id FROM products WHERE name LIKE 'PERF-%' ORDER BY id LIMIT 1)"

# ------------------------------------------------------------------ 查询集
# 期望： "INDEX:<名>" 必须出现 / "NOT_INDEX:<名>" 必须不出现
QUERIES = [
    ("Q1", "C 端列表：status = 1（低选择性）",
     "SELECT id, name FROM products WHERE is_deleted = 0 AND status = 1 ORDER BY id DESC LIMIT 10",
     "NOT_INDEX:idx_products_status",
     "status=1 命中 99% 的行 ⇒ 索引无胜算；计划器应当绕开它"),

    ("Q2", "C 端列表：按 category_id（无 LIMIT/ORDER BY）",
     "SELECT id, name FROM products WHERE is_deleted = 0 AND status = 1 AND category_id = %s" % CAT1,
     "INDEX:idx_products_category_id", "该索引就是为它建的"),

    ("Q3", "countByCategoryId（删除分类的引用校验，含软删）",
     "SELECT count(*) FROM products WHERE category_id = %s" % CAT1,
     "INDEX:idx_products_category_id", "删除前的阻塞式校验"),

    # ★ Q4（纯全文）已移到 PROBE_LIST —— 它的计划在多次运行间【不稳定】，不能做硬断言。

    ("Q5", "★★ 真实 searchProducts（全文 **+ OR 兜底**）",
     "SELECT p.id, p.name FROM products p LEFT JOIN categories c ON c.id = p.category_id "
     "WHERE p.is_deleted = 0 AND p.status = 1 "
     "AND (p.search_vector @@ plainto_tsquery('simple','iphone') "
     "     OR p.name ILIKE '%iphone%' OR p.subtitle ILIKE '%iphone%' OR p.description ILIKE '%iphone%') "
     "ORDER BY ts_rank(p.search_vector, plainto_tsquery('simple','iphone')) DESC, p.id ASC LIMIT 10",
     "NOT_INDEX:idx_products_search",
     "★ 这是【生产真实形状】：OR 让 GIN 无法被选中 —— 索引建了，但这条查询用不上"),

    ("Q6", "搜索：中文兜底（ILIKE 三列 + OR）",
     "SELECT p.id FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
     "AND (p.name ILIKE '%笔记本%' OR p.subtitle ILIKE '%笔记本%' OR p.description ILIKE '%笔记本%') LIMIT 10",
     "NOT_INDEX:idx_products_name_trgm", "★ OR + 前导 % ⇒ trgm 索引被挡在门外"),

    ("Q7", "搜索：**单列** ILIKE（去掉 OR）",
     "SELECT p.id FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
     "AND p.name ILIKE '%笔记本%' LIMIT 10",
     "INDEX:idx_products_name_trgm", "★ 与 Q6 成对照：是 OR 挡住的，不是索引不存在"),

    ("Q8a", "搜索：属性筛选（**从 product 侧驱动**的 EXISTS）",
     "SELECT p.id FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
     "AND EXISTS (SELECT 1 FROM product_skus s WHERE s.product_id = p.id "
     "            AND s.is_deleted = 0 AND s.status = 1 "
     "            AND s.attributes @> jsonb_build_object('color', '黑色')) LIMIT 10",
     "INDEX:idx_product_skus_attributes",
     "★ 生产真实形状：计划器会把 EXISTS【反写成从 SKU 侧驱动】—— 先 GIN 扫出黑色 SKU，再按 PK 取商品"),

    ("Q8b", "属性筛选：**直接从 SKU 侧**按属性查（对照）",
     "SELECT s.id FROM product_skus s WHERE s.is_deleted = 0 AND s.status = 1 "
     "AND s.attributes @> jsonb_build_object('color', '黑色') LIMIT 10",
     "INDEX:idx_product_skus_attributes",
     "★ 与 Q8a 成对照：证明 JSONB GIN 索引是好的，只是被 EXISTS 的驱动方向绕开了"),

    ("Q9", "订单列表：按 user_id",
     "SELECT id, order_no, status FROM orders WHERE user_id = %s ORDER BY id DESC LIMIT 10" % USER1,
     "INDEX:idx_orders_user_id", "C 端「我的订单」"),

    ("Q10", "★ 超时关单扫描（每 60 秒自动跑一次）",
     "SELECT id FROM orders WHERE status = 'PENDING_PAYMENT' "
     "AND created_at < CURRENT_TIMESTAMP - interval '2 minutes' LIMIT 100",
     "INDEX:idx_orders_status",
     "★ 全项目唯一一条分钟级自动执行的查询，最该被验证"),

    ("Q11", "订单详情：按 order_id 取明细",
     "SELECT id, sku_id, quantity FROM order_items WHERE order_id = %s" % ORDER1,
     "INDEX:idx_order_items_order_id", "每张订单详情都要走一次"),

    ("Q12", "库存流水：按 sku_id 倒序（管理端流水页）",
     "SELECT id, change_quantity FROM inventory_logs WHERE sku_id = %s ORDER BY id DESC LIMIT 20" % SKU1,
     "INDEX:idx_inventory_logs_sku_id", "流水表增长最快"),

    ("Q13", "商品评价：按 product_id",
     "SELECT id, rating FROM reviews WHERE product_id = %s LIMIT 10" % PROD1,
     "INDEX:idx_reviews_product_id", "商品详情页的评价列表"),
]

# ★ 探针：只记录、不断言。用来解释「为什么某条查询没用索引」。
PROBE_LIST = [
    ("R1", "C 端列表：category_id **+ ORDER BY id DESC LIMIT 10**（生产真实形状）",
     "SELECT id, name FROM products WHERE is_deleted = 0 AND status = 1 "
     "AND category_id = %s ORDER BY id DESC LIMIT 10" % CAT1,
     "与 Q2 对比：加了 ORDER BY + LIMIT 之后，计划器是否改走 PK 反向扫"),

    ("R2", "搜索：**纯**全文（无 OR 兜底）—— 与 Q5 成对照",
     "SELECT p.id, p.name FROM products p WHERE p.is_deleted = 0 AND p.status = 1 "
     "AND p.search_vector @@ plainto_tsquery('simple', 'iphone') "
     "ORDER BY ts_rank(p.search_vector, plainto_tsquery('simple','iphone')) DESC, p.id ASC LIMIT 10",
     "★★ 与 Q5 同一条 SQL 去掉 OR 之后：GIN 被用上（1.3ms）⇒ 证明「挡索引的是 OR，不是索引本身」"),
]


def scan_plan(plan_text):
    """从 EXPLAIN 文本里取出所有索引名 + 所有 Seq Scan 的表。

    ⚠️ 必须带上 `Backward`：`ORDER BY id DESC` 会让计划器输出
    `Index Scan Backward using products_pkey` —— 第一版正则只认 `Index Scan using`，
    于是这类计划被读成「没有用任何索引」，报告的「实际计划」列直接变成 `-`。
    ★ 扫不出东西时，先怀疑自己的解析器，而不是先下结论。
    """
    idx = set()
    for m in re.finditer(r"Index (?:Only )?Scan(?: Backward)? using (\w+)", plan_text):
        idx.add(m.group(1))
    for m in re.finditer(r"Bitmap Index Scan on (\w+)", plan_text):
        idx.add(m.group(1))
    seq = set(re.findall(r"Seq Scan on (\w+)", plan_text))
    return sorted(idx), sorted(seq)


def run_explain(sql):
    rc, out, err = psql(PROBE_DB, "EXPLAIN (ANALYZE, BUFFERS) " + sql)
    if rc != 0:
        return None, None, None, err
    idx, seq = scan_plan(out)
    m = re.search(r"Execution Time: ([\d.]+) ms", out)
    return idx, seq, ("%s ms" % m.group(1) if m else "?"), out


def main():
    say("=" * 78)
    say("Day 27 -- 性能基线：索引有没有被用上（临时库 %s，EXPLAIN ANALYZE）" % PROBE_DB)
    say("=" * 78)

    say("")
    say("[0] 建临时库（★ 只动这一个名字，开发库不碰）")
    rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;\nCREATE DATABASE %s;" % (PROBE_DB, PROBE_DB))
    chk("CREATE DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))
    if rc != 0:
        return bail()

    try:
        say("")
        say("[1] 按序灌 01→14（与 initdb 同序，ON_ERROR_STOP=1）")
        bad = []
        for name in FILES:
            body = open(os.path.join(SQL_DIR, name), encoding="utf-8").read()
            rc, _o, err = psql(PROBE_DB, body)
            say("      [%s] %s" % ("OK  " if rc == 0 else "FAIL", name))
            if rc != 0:
                bad.append(name)
                say("             stderr: %s" % err.replace("\n", " | ")[:300])
        chk("14 份补丁全部 rc == 0", not bad, "bad=%s" % bad)
        if bad:
            return bail()

        say("")
        say("[2] 造数（★ 规模 + **选择性**，否则「看不到索引」永远无法被证伪）")
        for label, sql in SEEDS:
            rc, _o, err = psql(PROBE_DB, sql)
            chk("造数 %s" % label, rc == 0, "rc=%d err=%s" % (rc, err[:200]))

        say("")
        say("[3] VACUUM (ANALYZE) —— ★ 两件事都必须做，少一件结论就是错的")
        say("     · ANALYZE：不做的话 pg_class.reltuples 还是 0，计划器只能瞎猜")
        say("     · VACUUM ：不做的话 GIN 索引的 fastupdate【待处理列表】里还堆着刚灌进去的几万条")
        say("       —— 实测（本脚本第 5~7 轮）：待处理列表未清时，GIN 扫 32 行要 13.3ms / 298 次")
        say("       buffer 命中，计划器于是改用 Seq Scan；清掉之后同一条查询 0.9ms。")
        say("       ★★ 这才是前几轮「计划在 GIN 与 Seq Scan 之间反复翻转」的真正原因 ——")
        say("          不是统计噪声，是**索引自身处于未整理状态**。")
        rc, _o, err = psql(PROBE_DB, "VACUUM (ANALYZE);")
        chk("VACUUM (ANALYZE) 全库", rc == 0, "err=%s" % err[:160])

        say("")
        say("[4] 规模核对（造数真的落库了吗）")
        for tbl, want in [("products", N_PRODUCTS), ("product_skus", N_PRODUCTS * 2),
                          ("orders", N_ORDERS), ("order_items", N_ORDERS),
                          ("inventory_logs", N_LOGS), ("reviews", N_REVIEWS)]:
            got = int(one("SELECT count(*) FROM %s" % tbl))
            est = int(one("SELECT reltuples::bigint FROM pg_class WHERE relname = '%s'" % tbl))
            chk("%s 行数 >= %d（且 ANALYZE 估算同量级）" % (tbl, want),
                got >= want and est > want * 0.5,
                "actual=%d reltuples=%d" % (got, est))

        say("")
        say("[4b] ★ 选择性核对 —— 断言「造数落在判据的取值域里」")
        say("     （第一版脚本就是死在这一步：每条谓词都命中 20%~100%，索引必然不被选中）")
        n_iphone = int(one("SELECT count(*) FROM products WHERE search_vector @@ plainto_tsquery('simple','iphone')"))
        n_pend = int(one("SELECT count(*) FROM orders WHERE status = 'PENDING_PAYMENT'"))
        chk("全文词 'iphone' 命中率 < 5%（有选择性）",
            n_iphone > 0 and n_iphone < N_PRODUCTS * 0.05, "hit=%d / %d" % (n_iphone, N_PRODUCTS))
        chk("PENDING_PAYMENT 占比 < 5%（有选择性）",
            0 < n_pend < N_ORDERS * 0.05, "pending=%d / %d" % (n_pend, N_ORDERS))

        say("")
        say("[5] EXPLAIN (ANALYZE, BUFFERS) —— 逐条查询")
        say("")
        for qid, name, sql, expect, why in QUERIES:
            idx, seq, ms, out = run_explain(sql)
            if idx is None:
                chk("%s %s" % (qid, name), False, "EXPLAIN 失败：%s" % str(seq)[:200])
                continue
            kind, target = expect.split(":", 1)
            ok = (target in idx) if kind == "INDEX" else (target not in idx)
            FINDINGS.append((qid, name, expect, idx, seq, ms, ok, why))
            chk("%s %s" % (qid, name), ok,
                "idx=%s seq=%s %s" % (idx or "-", seq or "-", ms))
            if not ok:
                # ★ 未命中必须留下【完整计划】作为证据，否则解释只能是猜的
                say("")
                say("      ---- %s 完整计划（未命中，附证据）----" % qid)
                for ln in out.splitlines():
                    say("      " + ln)
                say("      ---- %s 计划结束 ----" % qid)
                say("")

        say("")
        say("[5b] 探针（只记录、不断言：用来解释「为什么某条查询没用索引」）")
        for pid, name, sql, why in PROBE_LIST:
            idx, seq, ms, out = run_explain(sql)
            if idx is None:
                say("      [%s] EXPLAIN 失败" % pid)
                continue
            PROBES.append((pid, name, idx, seq, ms))
            say("      [%s] %s" % (pid, name))
            say("            idx=%s seq=%s %s" % (idx or "-", seq or "-", ms))
            say("            %s" % why)

        say("")
        say("[6] 汇总（★ 未命中不等于缺陷：要看是「索引没用」还是「查询写法挡住了索引」）")
        say("")
        say("      %-4s %-40s %-32s %-5s %s" % ("ID", "查询", "设计预期", "结论", "实际计划"))
        for qid, name, expect, idx, seq, ms, ok, why in FINDINGS:
            say("      %-4s %-40s %-32s %-5s %s" % (
                qid, name[:38], expect, ("OK" if ok else "MISS"), (idx or seq or "-")))

        hit = sum(1 for f in FINDINGS if f[6])
        chk("%d 条查询全部符合设计预期（命中 %d）" % (len(QUERIES), hit), hit == len(QUERIES),
            "hit=%d/%d" % (hit, len(QUERIES)))

        d = {f[0]: f for f in FINDINGS}
        chk("★★ 核心结论：生产真实搜索（Q5）用不上 idx_products_search —— OR 兜底把它挡住了",
            "idx_products_search" not in d["Q5"][3], "Q5=%s" % d["Q5"][3])
        chk("★ 反向对照成立：Q7(单列 ILIKE) 用上 trgm，而 Q6(OR) 用不上",
            "idx_products_name_trgm" in d["Q7"][3] and "idx_products_name_trgm" not in d["Q6"][3],
            "Q6=%s / Q7=%s" % (d["Q6"][3], d["Q7"][3]))
        chk("★ Q8a/Q8b 都用上 JSONB GIN（EXISTS 被计划器反写成从 SKU 侧驱动）",
            "idx_product_skus_attributes" in d["Q8a"][3]
            and "idx_product_skus_attributes" in d["Q8b"][3],
            "Q8a=%s / Q8b=%s" % (d["Q8a"][3], d["Q8b"][3]))

    finally:
        say("")
        say("[7] 删临时库")
        rc, _o, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:160]))

    return bail()


def bail(code=None):
    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 索引命中情况与设计一致，反向对照成立" if ok
                         else "FAIL -- 见上面 FAIL 行"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("report -> %s" % REPORT)
    if code is None:
        code = 0 if ok else 1
    return code


if __name__ == "__main__":
    sys.exit(main())
