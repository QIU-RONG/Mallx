# -*- coding: utf-8 -*-
"""
Day 19 验收：C 端商品搜索  GET /api/products/search

设计原则（沿用 Day 17/18 的模板）：
  1. 只读零写入 —— 全部 GET + 只读 psql；可重复执行，不留痕迹。
  2. 不信接口自报 —— 每条业务断言都配一次 psql 对账。
  3. 业务失败 = HTTP 200 + body.code（协议层失败才是真 HTTP 码）。
  4. 满额断言写死常量（EXPECTED），防止断言被静默跳过。

覆盖链路 A–H（见 docs/daily/Day-19-商品搜索.md §七）：
  A 路由与字段映射 / B+ 大小写对照 / B2 纯全文证据 / C 相关性排序
  D JSONB 属性筛选 / E 中文边界 / F 健壮性 / G 索引可达性 / H 零写入校验

运行：python day19-search-verify.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]

EXPECTED = 48                     # 满额断言条数（写死）

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LINES = []

PASS = 0
FAIL = 0
FAILS = []


def say(line=""):
    print(line)
    LINES.append(line)


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        say("  [PASS] %s" % name)
    else:
        FAIL += 1
        FAILS.append(name)
        say("  [FAIL] %s   %s" % (name, extra))


def sql(statement):
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("psql rc=%s: %s" % (r.returncode, (r.stderr or "").strip()[:300]))
    return [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]


def sql1(statement):
    rows = sql(statement)
    return rows[0] if rows else ""


def _get(path):
    req = urllib.request.Request(APP + path, method="GET")
    try:
        with _opener.open(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _qs(params):
    return "&".join("%s=%s" % (k, urllib.parse.quote(str(v), safe=""))
                    for k, v in params.items() if v is not None)


def search(path="/api/products/search", **params):
    """返回 (http_status, json_or_None, raw_text)"""
    q = _qs(params)
    st, body = _get(path + ("?" + q if q else ""))
    try:
        return st, json.loads(body), body
    except Exception:
        return st, None, body


def ids_of(j):
    return [r["id"] for r in j["data"]["records"]]


def wait_ready():
    for _ in range(60):
        try:
            st, j, _b = search(size=1)
            if st == 200 and j and j.get("code") == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


ALIVE = "p.is_deleted=0 AND p.status=1"

# ---------------------------------------------------------------- 开场
say("=" * 74)
say("Day 19 验收：C 端商品搜索（GET /api/products/search）")
say("=" * 74)

say()
say("[等待应用就绪] 127.0.0.1:8080 ...")
if not wait_ready():
    say("  [FATAL] 应用 60 秒内未就绪，终止。")
    sys.exit(2)
say("  应用已就绪。")

# 冻结基线（后续 H 组会再查一次做零写入校验）
BASE_PRODUCTS = int(sql1("SELECT count(*) FROM products"))
BASE_SKUS = int(sql1("SELECT count(*) FROM product_skus"))
BASE_CATS = int(sql1("SELECT count(*) FROM categories"))
say("  库基线：products=%d  product_skus=%d  categories=%d"
    % (BASE_PRODUCTS, BASE_SKUS, BASE_CATS))

# ---------------------------------------------------------------- A 路由与字段
say()
say("-" * 74)
say("A 路由与字段映射（{id} vs search 谁优先 + 下划线别名是否真映射上）")
say("-" * 74)

st, j, raw = search()
check("A1 HTTP 200", st == 200, "实际 %s" % st)
check("A2 body.code == 200 （★ 若是 400 说明路由落到了 /{id}）",
      bool(j) and j.get("code") == 200, "实际 %s" % (j.get("code") if j else raw[:120]))

alive_n = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE))
db_rows = sql("SELECT p.id, p.name, coalesce(p.main_image,''), coalesce(c.name,''), "
              "coalesce((SELECT MIN(s.price)::text FROM product_skus s "
              "WHERE s.product_id=p.id AND s.is_deleted=0 AND s.status=1),'') "
              "FROM products p LEFT JOIN categories c ON c.id=p.category_id "
              "WHERE " + ALIVE + " ORDER BY p.id")

db_ids = [int(r.split("|")[0]) for r in db_rows]
recs = j["data"]["records"] if (j and j.get("data")) else []

check("A3 total == DB 存活商品数 (%d)" % alive_n,
      bool(j) and j["data"]["total"] == alive_n,
      "接口 total=%s" % (j["data"]["total"] if j and j.get("data") else "?"))
check("A4 records 条数 == %d" % alive_n, len(recs) == alive_n, "实际 %d" % len(recs))
check("A5 id 列表与 DB 一致 %s" % db_ids, ids_of(j) == db_ids if j else False,
      "接口 %s" % (ids_of(j) if j else "?"))

db_cat = {int(r.split("|")[0]): r.split("|")[3] for r in db_rows}
db_img = {int(r.split("|")[0]): r.split("|")[2] for r in db_rows}
db_min = {int(r.split("|")[0]): r.split("|")[4] for r in db_rows}

cat_ok = all((r.get("categoryName") or "") == db_cat.get(r["id"], "") for r in recs)
img_ok = all((r.get("mainImage") or "") == db_img.get(r["id"], "") for r in recs)
min_ok = all(abs(float(r["minPrice"]) - float(db_min[r["id"]])) < 1e-6
             for r in recs if r.get("minPrice") is not None and db_min.get(r["id"]))

check("A6 categoryName 逐条 == DB（LEFT JOIN categories 生效）", bool(recs) and cat_ok)
check("A7 mainImage 逐条 == DB（★ 下划线别名确实映射上了，没静默 null）",
      bool(recs) and img_ok)
check("A8 minPrice 逐条 == DB（标量子查询生效）", bool(recs) and min_ok)

# ---------------------------------------------------------------- B 大小写
say()
say("-" * 74)
say("B ★核心对照：同一关键词 iphone，新路 vs 旧路（大小写铁证）")
say("-" * 74)

st, jn, _ = search(keyword="iphone")
check("B1 新路 ?keyword=iphone → total == 1",
      bool(jn) and jn["data"]["total"] == 1,
      "实际 %s" % (jn["data"]["total"] if jn and jn.get("data") else "?"))
check("B2 新路命中 id == 1", bool(jn) and ids_of(jn) == [1],
      "实际 %s" % (ids_of(jn) if jn else "?"))

st, jo, _ = search(path="/api/products", keyword="iphone")
check("B3 旧路 GET /api/products?keyword=iphone → total == 0（LIKE 大小写敏感）",
      bool(jo) and jo["data"]["total"] == 0,
      "实际 %s" % (jo["data"]["total"] if jo and jo.get("data") else "?"))

st, jo2, _ = search(path="/api/products", keyword="iPhone")
check("B4 旧路 ?keyword=iPhone → total == 1（证明只差大小写，不是没数据）",
      bool(jo2) and jo2["data"]["total"] == 1,
      "实际 %s" % (jo2["data"]["total"] if jo2 and jo2.get("data") else "?"))

n_like = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                  + " AND p.name LIKE '%iphone%'"))
n_ilike = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                   + " AND p.name ILIKE '%iphone%'"))
check("B5 DB 对账 LIKE '%iphone%' == 0", n_like == 0, "实际 %d" % n_like)
check("B6 DB 对账 ILIKE '%iphone%' == 1", n_ilike == 1, "实际 %d" % n_ilike)

# ---------------------------------------------------------------- B2 纯全文
say()
say("-" * 74)
say("B2 ★纯全文证据：promotion 只存在于 description（ILIKE 两条兜底都命不中）")
say("-" * 74)

st, jp, _ = search(keyword="promotion")
check("B7 ?keyword=promotion → total == 1",
      bool(jp) and jp["data"]["total"] == 1,
      "实际 %s" % (jp["data"]["total"] if jp and jp.get("data") else "?"))
check("B8 promotion 命中 id == 1", bool(jp) and ids_of(jp) == [1],
      "实际 %s" % (ids_of(jp) if jp else "?"))
check("B9 promotion 的 searchRank > 0（说明走的是 ts_rank，不是恒 0）",
      bool(jp) and jp["data"]["records"][0].get("searchRank", 0) > 0,
      "实际 %s" % (jp["data"]["records"][0].get("searchRank") if jp else "?"))

p_fts = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                 + " AND p.search_vector @@ plainto_tsquery('simple','promotion')"))
p_nm = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                + " AND p.name ILIKE '%promotion%'"))
p_sub = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                 + " AND p.subtitle ILIKE '%promotion%'"))
check("B10 DB 对账 promotion：fts=1 且 name ILIKE=0 且 subtitle ILIKE=0 "
      "⇒ 全文是唯一解释", (p_fts, p_nm, p_sub) == (1, 0, 0),
      "实际 fts=%d nm=%d sub=%d" % (p_fts, p_nm, p_sub))

# ---------------------------------------------------------------- C 相关性
say()
say("-" * 74)
say("C 相关性排序：pro 在两件商品里的 ts_rank 有真实高低差")
say("-" * 74)

st, jr, _ = search(keyword="pro")
ranks = [r.get("searchRank") for r in jr["data"]["records"]] if (jr and jr.get("data")) else []
check("C1 ?keyword=pro → total == 2",
      bool(jr) and jr["data"]["total"] == 2,
      "实际 %s" % (jr["data"]["total"] if jr and jr.get("data") else "?"))
check("C2 顺序 == [1, 2]（id=1 含 pro 两处：name(A) + subtitle(B)）",
      bool(jr) and ids_of(jr) == [1, 2], "实际 %s" % (ids_of(jr) if jr else "?"))
check("C3 searchRank 严格降序（rank[0] > rank[1]）",
      len(ranks) == 2 and ranks[0] > ranks[1], "实际 %s" % ranks)

db_r1 = float(sql1("SELECT round(ts_rank(p.search_vector, "
                   "plainto_tsquery('simple','pro'))::numeric, 6)::text FROM products p "
                   "WHERE p.id=1"))
db_r2 = float(sql1("SELECT round(ts_rank(p.search_vector, "
                   "plainto_tsquery('simple','pro'))::numeric, 6)::text FROM products p "
                   "WHERE p.id=2"))
check("C4 rank(商品1) ≈ 0.668720（DB 对账）",
      len(ranks) == 2 and abs(round(ranks[0], 6) - db_r1) < 1e-4,
      "接口 %.6f / DB %.6f" % (ranks[0] if len(ranks) == 2 else -1, db_r1))
check("C5 rank(商品2) ≈ 0.607927（DB 对账）",
      len(ranks) == 2 and abs(round(ranks[1], 6) - db_r2) < 1e-4,
      "接口 %.6f / DB %.6f" % (ranks[1] if len(ranks) == 2 else -1, db_r2))

# ---------------------------------------------------------------- D JSONB
say()
say("-" * 74)
say("D JSONB 属性筛选（EXISTS + jsonb_build_object）")
say("-" * 74)

st, jd1, _ = search(attrKey="color", attrValue="黑色")
check("D1 attrKey=color&attrValue=黑色 → total == 1 且 id == 1",
      bool(jd1) and jd1["data"]["total"] == 1 and ids_of(jd1) == [1],
      "实际 %s" % (ids_of(jd1) if jd1 else "?"))

st, jd2, _ = search(attrKey="color", attrValue="原色钛金属")
check("D2 attrKey=color&attrValue=原色钛金属 → total == 1 且 id == 1（sku 3）",
      bool(jd2) and jd2["data"]["total"] == 1 and ids_of(jd2) == [1],
      "实际 %s" % (ids_of(jd2) if jd2 else "?"))

st, jd3, _ = search(attrKey="color", attrValue="白色")
check("D3 attrKey=color&attrValue=白色 → total == 1 且 id == 3（sku 5）",
      bool(jd3) and jd3["data"]["total"] == 1 and ids_of(jd3) == [3],
      "实际 %s" % (ids_of(jd3) if jd3 else "?"))

st, jd4, _ = search(keyword="iphone", attrKey="color", attrValue="原色钛金属")
check("D4 keyword=iphone + color=原色钛金属 → total == 1（关键词与属性 AND 叠加）",
      bool(jd4) and jd4["data"]["total"] == 1,
      "实际 %s" % (jd4["data"]["total"] if jd4 and jd4.get("data") else "?"))

st, jd5, _ = search(keyword="iphone", attrKey="color", attrValue="曜金黑")
check("D5 keyword=iphone + color=曜金黑 → total == 0（曜金黑属于商品 2）",
      bool(jd5) and jd5["data"]["total"] == 0,
      "实际 %s" % (jd5["data"]["total"] if jd5 and jd5.get("data") else "?"))

d_db = sql1("SELECT coalesce(string_agg(DISTINCT p.id::text, ','),'') FROM products p "
            "WHERE " + ALIVE + " AND EXISTS (SELECT 1 FROM product_skus s "
            "WHERE s.product_id=p.id AND s.is_deleted=0 AND s.status=1 "
            "AND s.attributes @> jsonb_build_object('color','黑色'))")
check("D6 DB 对账 color=黑色 → {1}", d_db == "1", "实际 {%s}" % d_db)

# ---------------------------------------------------------------- E 中文边界
say()
say("-" * 74)
say("E 中文边界：simple 字典不切词 ⇒ 中文只能靠 ILIKE 兜底（如实打表）")
say("-" * 74)

st, je1, _ = search(keyword="轻薄")
check("E1 ?keyword=轻薄 → total == 1（fts=0，靠 ILIKE subtitle 兜底）",
      bool(je1) and je1["data"]["total"] == 1,
      "实际 %s" % (je1["data"]["total"] if je1 and je1.get("data") else "?"))
check("E2 轻薄命中 id == 4（subtitle『商务轻薄本 2.2K 屏』）",
      bool(je1) and ids_of(je1) == [4], "实际 %s" % (ids_of(je1) if je1 else "?"))

st, je2, _ = search(keyword="笔记本")
check("E3 ?keyword=笔记本 → total == 0 ★已知限制（只在 description，两条 ILIKE 都不覆盖）",
      bool(je2) and je2["data"]["total"] == 0,
      "实际 %s" % (je2["data"]["total"] if je2 and je2.get("data") else "?"))

st, je3, _ = search(keyword="徕卡")
check("E4 ?keyword=徕卡 → total == 2（fts=0，ILIKE subtitle 命中 2 条）",
      bool(je3) and je3["data"]["total"] == 2,
      "实际 %s" % (je3["data"]["total"] if je3 and je3.get("data") else "?"))
check("E5 徕卡命中 ids == [2, 3]", bool(je3) and ids_of(je3) == [2, 3],
      "实际 %s" % (ids_of(je3) if je3 else "?"))

e_fts = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                 + " AND p.search_vector @@ plainto_tsquery('simple','轻薄')"))
e_sub = int(sql1("SELECT count(*) FROM products p WHERE " + ALIVE
                 + " AND p.subtitle ILIKE '%轻薄%'"))
check("E6 DB 对账 轻薄：fts=0 且 subtitle ILIKE=1",
      (e_fts, e_sub) == (0, 1), "实际 fts=%d sub=%d" % (e_fts, e_sub))

# ---------------------------------------------------------------- F 健壮性
say()
say("-" * 74)
say("F 健壮性：成对校验 / tsquery 特殊字符 / 分页夹紧")
say("-" * 74)

st, jf1, raw = search(attrKey="color")
check("F1 只给 attrKey → HTTP 200 + code=400（成对校验）",
      st == 200 and bool(jf1) and jf1.get("code") == 400,
      "HTTP %s code=%s" % (st, jf1.get("code") if jf1 else raw[:100]))

st, jf2, raw = search(attrValue="黑色")
check("F2 只给 attrValue → HTTP 200 + code=400（成对校验）",
      st == 200 and bool(jf2) and jf2.get("code") == 400,
      "HTTP %s code=%s" % (st, jf2.get("code") if jf2 else raw[:100]))

st, jf3, raw = search(keyword="iphone & | !")
check("F3 keyword='iphone & | !' → code=200 且不 500（plainto_tsquery 把它当纯文本）",
      bool(jf3) and jf3.get("code") == 200,
      "HTTP %s code=%s" % (st, jf3.get("code") if jf3 else raw[:100]))

st, jf4, _ = search(size=999)
check("F4 size=999 → data.size 夹到 100",
      bool(jf4) and jf4["data"]["size"] == 100,
      "实际 %s" % (jf4["data"]["size"] if jf4 and jf4.get("data") else "?"))

st, jf5, _ = search(size=0)
check("F5 size=0 → data.size 夹到 1",
      bool(jf5) and jf5["data"]["size"] == 1,
      "实际 %s" % (jf5["data"]["size"] if jf5 and jf5.get("data") else "?"))

st, jf6, _ = search(size=-1)
check("F6 size=-1 → data.size 夹到 1",
      bool(jf6) and jf6["data"]["size"] == 1,
      "实际 %s" % (jf6["data"]["size"] if jf6 and jf6.get("data") else "?"))

st, jf7, _ = search(current=0)
check("F7 current=0 → data.current 夹到 1",
      bool(jf7) and jf7["data"]["current"] == 1,
      "实际 %s" % (jf7["data"]["current"] if jf7 and jf7.get("data") else "?"))

st, jf8, _ = search(attrKey="", attrValue="")
check("F8 attrKey=&attrValue=（都给但都空）→ total == 5（视为不筛选，不报错）",
      bool(jf8) and jf8["data"]["total"] == alive_n,
      "实际 %s" % (jf8["data"]["total"] if jf8 and jf8.get("data") else "?"))

# ---------------------------------------------------------------- G 索引
say()
say("-" * 74)
say("G 索引可达性（★ 小表陷阱：必须把查询剥到只剩 fts 谓词，否则会被 btree 索引截走）")
say("-" * 74)

plan_fts = "\n".join(sql("BEGIN; SET LOCAL enable_seqscan = off; "
                         "EXPLAIN SELECT id FROM products "
                         "WHERE search_vector @@ plainto_tsquery('simple','iphone'); COMMIT;"))
check("G1 GIN 索引 idx_products_search 被选中（出现 Bitmap Index Scan on idx_products_search）",
      "Bitmap Index Scan on idx_products_search" in plan_fts,
      "计划：%s" % plan_fts.replace("\n", " / ")[:160])

plan_trgm = "\n".join(sql("BEGIN; SET LOCAL enable_seqscan = off; "
                          "EXPLAIN SELECT id FROM products "
                          "WHERE name % 'iphone'; COMMIT;"))
check("G2 trgm 索引 idx_products_name_trgm 被选中（pg_trgm 这条路也通）",
      "Bitmap Index Scan on idx_products_name_trgm" in plan_trgm,
      "计划：%s" % plan_trgm.replace("\n", " / ")[:160])

plan_raw = "\n".join(sql("EXPLAIN SELECT p.id FROM products p WHERE p.is_deleted=0 "
                         "AND p.status=1 AND p.search_vector @@ "
                         "plainto_tsquery('simple','iphone')"))
say("  [记录] 完整生产 SQL 在 5 行小表上规划器选的是：%s"
    % (plan_raw.splitlines()[0].strip() if plan_raw else "?"))

# ---------------------------------------------------------------- H 零写入
say()
say("-" * 74)
say("H 零写入校验（验收全程不得改动数据）")
say("-" * 74)

now_p = int(sql1("SELECT count(*) FROM products"))
now_s = int(sql1("SELECT count(*) FROM product_skus"))
now_c = int(sql1("SELECT count(*) FROM categories"))
check("H1 products 行数未变 == %d" % BASE_PRODUCTS, now_p == BASE_PRODUCTS, "实际 %d" % now_p)
check("H2 product_skus 行数未变 == %d" % BASE_SKUS, now_s == BASE_SKUS, "实际 %d" % now_s)
check("H3 categories 行数未变 == %d" % BASE_CATS, now_c == BASE_CATS, "实际 %d" % now_c)

# ---------------------------------------------------------------- 收尾
say()
say("=" * 74)
say("TOTAL: PASS=%d  FAIL=%d   （期望断言数 %d）" % (PASS, FAIL, EXPECTED))
if PASS + FAIL != EXPECTED:
    say("  [WARN] 实际断言数 %d != 期望 %d —— 脚本被改动过？" % (PASS + FAIL, EXPECTED))
if FAILS:
    say("失败清单：")
    for f in FAILS:
        say("  - " + f)
say("VERDICT: %s" % ("OK 全绿" if FAIL == 0 else ("FAIL %d 条" % FAIL)))
say("=" * 74)

report = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "day19-search-verify-report.txt")
with open(report, "w", encoding="utf-8") as fp:
    fp.write("\n".join(LINES) + "\n")
print("\n报告已写入：%s" % report)

sys.exit(0 if FAIL == 0 else 1)
