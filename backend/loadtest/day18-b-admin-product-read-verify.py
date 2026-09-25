# -*- coding: utf-8 -*-
"""Day 18 链路 B -- 管理端商品读（GET /api/admin/products 与 /{id}）。

这条链路要验的【核心命题】只有一句：
    「管理端能把【下架商品】也读出来，而 C 端读不到」——
    这正是「同一个 Service、两个相反的过滤口径」（规划 §6.1）的可观测证据。

为此必须先造一条 status=0 的商品：库里原来的 5 个种子商品【全部上架】
（基线断言 #3 会当场证明这一点），没有样本就验不出「含下架」。

造样本的方式：**直接 INSERT 一行 products**，不走 POST 接口 ——
因为本期管理端写接口（链路 C）此刻可能还是骨架，用它造夹具会把 B 的
结论绑在 C 的实现上（两条链路就不独立了）。收尾按 id 物理删净即可。

★ 本脚本【可重复执行】：先记高水位（全表 max(id)），跑完 DELETE 夹具行，
  并断言 products 活行数回基线、5 条种子逐字节不变。

★ 满额自校验：FULL_TOTAL 是【写死的常量】，而不是 len(checks) ——
  防止「条件性断言未被创建导致分母缩水」把失败看轻（Day 17 链路 C 踩过 36 vs 39）。

Usage:
    python day18-b-admin-product-read-verify.py
报告（utf-8）与脚本同目录：day18-b-admin-product-read-verify-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
ADMIN = "/api/admin/products"
CEND = "/api/products"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day18-b-admin-product-read-verify-report.txt")

# ProductVO 的 9 个字段（顺序无所谓，比对前会 sorted）
VO_FIELDS = ["brandId", "brandName", "categoryId", "categoryName", "id",
             "mainImage", "name", "status", "subtitle"]

# ★ 夹具：一条【下架】商品。category 11 = 二级分类「智能手机」，其父是 1「手机通讯」；
#   brand 1 = Apple。放二级分类是为了顺带验证「categoryId 过滤会展开到子分类」。
FX_NAME = "FX-OFFLINE-PRODUCT"
FX_CATEGORY = 11
FX_BRAND = 1

SEED_ALIVE = 5          # 基线：5 个种子商品全部 is_deleted=0 / status=1

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


def short(raw, n=190):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ---------------------------------------------------------------- db helpers
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip(), p.returncode


def one(sql):
    """单值。⚠️ docker exec 回传行尾带 \\r —— 不 strip 会让比对恒为假。"""
    return psql(sql)[0].strip()


TABLES = ["products", "product_skus", "product_images", "categories", "brands",
          "orders", "order_items", "payments", "cart_items", "inventory_logs"]


def counters():
    return {t: int(one("SELECT count(*) FROM %s" % t)) for t in TABLES}


def alive_products():
    return int(one("SELECT count(*) FROM products WHERE is_deleted=0"))


def seed_snapshot():
    """5 个种子商品的逐字节快照（id:status:name），用于收尾比对。"""
    return one("SELECT string_agg(id||':'||status||':'||name, ' ; ' ORDER BY id) "
               "FROM products WHERE id <= %d" % SEED_ALIVE)


def hw():
    """★ 高水位取【全表 max(id)】。"""
    return int(one("SELECT COALESCE(MAX(id),0) FROM products"))


DB_ROWS_SQL = """
SELECT p.id::text
     || '|' || p.category_id::text
     || '|' || COALESCE(c.name, 'NULL')
     || '|' || COALESCE(p.brand_id::text, 'NULL')
     || '|' || COALESCE(b.name, 'NULL')
     || '|' || p.name
     || '|' || COALESCE(p.subtitle, 'NULL')
     || '|' || COALESCE(p.main_image, 'NULL')
     || '|' || p.status::text
  FROM products p
  LEFT JOIN categories c ON c.id = p.category_id
  LEFT JOIN brands     b ON b.id = p.brand_id
 WHERE p.is_deleted = 0 {extra}
 ORDER BY p.id DESC
"""


def db_rows(extra=""):
    """返回 [dict] —— 形状与 ProductVO 的 9 个字段一一对应（id 降序，与接口排序一致）。"""
    out = psql(DB_ROWS_SQL.format(extra=extra))[0]
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        p = line.split("|")
        rows.append(dict(
            id=int(p[0]), categoryId=int(p[1]),
            categoryName=None if p[2] == "NULL" else p[2],
            brandId=None if p[3] == "NULL" else int(p[3]),
            brandName=None if p[4] == "NULL" else p[4],
            name=p[5],
            subtitle=None if p[6] == "NULL" else p[6],
            mainImage=None if p[7] == "NULL" else p[7],
            status=int(p[8])))
    return rows


def rec_norm(r):
    """把接口返回的一条 record 归一化到与 db_rows() 相同的形状（只取 9 个字段）。"""
    return {k: r.get(k) for k in VO_FIELDS}


def insert_fixture():
    """★ 夹具 SQL 一律纯 ASCII（本机 PS 管道会吃 CJK 字节）。"""
    sql = ("INSERT INTO products "
           "(category_id, brand_id, name, subtitle, main_image, status, "
           " created_at, updated_at) VALUES "
           "(%d, %d, '%s', 'fx-subtitle', '/img/fx.png', 0, "
           " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id" % (FX_CATEGORY, FX_BRAND, FX_NAME))
    out, rc = psql(sql)
    fid = None
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            fid = int(line)
    return fid, rc, out


# ================================================================ main
def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 18 链路 B -- 管理端商品读（分页含下架 / status 可选过滤 / 详情 / 权限矩阵）")
    say("target : %s%s  与  %s/{id}" % (BASE, ADMIN, ADMIN))
    say("accounts: demo(C端) / op_order(ORDER_ADMIN) / op_product(PRODUCT_ADMIN) / admin(SUPER_ADMIN)")
    say("fixture : 1 条 status=0 商品（直接 INSERT，不走写接口 —— 保持 B 与 C 相互独立）")
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base_counts = counters()
    base_alive = alive_products()
    base_seed = seed_snapshot()
    base_hw = hw()
    say("  products 活行 = %d ；全表 %d 行 ；高水位 = %d"
        % (base_alive, base_counts["products"], base_hw))
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base_counts.items())))
    chk("#1 基线：products 活行 == %d" % SEED_ALIVE, base_alive == SEED_ALIVE,
        "实得 %d" % base_alive)
    chk("#2 基线：categories == 7（3 个顶级 + 4 个二级）",
        base_counts["categories"] == 7, "实得 %d" % base_counts["categories"])
    seed_off = int(one("SELECT count(*) FROM products WHERE status <> 1"))
    chk("#3 ★ 基线：5 条种子商品 status 全为 1 —— 『下架商品』这条边界原先不存在，夹具必须自造",
        seed_off == 0, "实得 %d 条非上架" % seed_off)
    tops = one("SELECT string_agg(id::text, ',' ORDER BY id) FROM categories WHERE parent_id IS NULL")
    subs = one("SELECT string_agg(id::text, ',' ORDER BY id) FROM categories WHERE parent_id IS NOT NULL")
    say("  分类拓扑：顶级 [%s] ；二级 [%s]" % (tops, subs))
    chk("#4 基线：顶级 == 1,2,3 ；二级 == 11,12,21,31（categoryId 展开断言的依据）",
        tops == "1,2,3" and subs == "11,12,21,31", "top=%s sub=%s" % (tops, subs))

    # ---------------------------------------------------------- [1] anonymous
    say("\n[1] 匿名（★ Security 层写响应 ⇒ 真 HTTP 401，不是 body.code）")
    st, raw = api("GET", ADMIN)
    say("  匿名 GET %s        -> http=%s %s" % (ADMIN, st, short(raw, 100)))
    chk("#5 匿名分页被拒：真 HTTP 401", st == 401, "http=%s" % st)
    st, raw = api("GET", "%s/1" % ADMIN)
    say("  匿名 GET %s/1      -> http=%s %s" % (ADMIN, st, short(raw, 100)))
    chk("#6 匿名详情被拒：真 HTTP 401", st == 401, "http=%s" % st)

    # ---------------------------------------------------------- [2] login
    say("\n[2] 登录四个身份（token 只在内存里，不落盘）")

    def login(path, u, p):
        st_, b_, _ = japi("POST", path, body={"username": u, "password": p})
        return (b_.get("data") or {}).get("token"), b_.get("code")

    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_o_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    op_p_t, c3 = login("/api/auth/admin/login", "op_product", "prod123456")
    adm_t, c4 = login("/api/auth/admin/login", "admin", "admin123")
    for nm, tk, cd in (("demo", demo_t, c1), ("op_order", op_o_t, c2),
                       ("op_product", op_p_t, c3), ("admin", adm_t, c4)):
        say("  %-11s code=%s token_len=%d" % (nm, cd, len(tk or "")))
    chk("#7 四个身份全部登录成功", all([demo_t, op_o_t, op_p_t, adm_t]),
        "op_product 缺失请先跑 day17-fixture-apply.py")
    if not all([demo_t, op_o_t, op_p_t, adm_t]):
        say("\nABORT: 缺 token")
        flush()
        return 1

    # ---------------------------------------------------------- [3] 权限矩阵
    say("\n[3] ★ 权限矩阵（关掉白名单后，管理端【读也要权限】—— 与 C 端 GET 公开正好相反）")
    st, raw = api("GET", ADMIN, token=demo_t)
    say("  demo(C 端 token，perms 空集)  http=%s code=%s %s" % (st, body_code(raw), short(raw, 90)))
    chk("#8 C 端 token 被拒：真 HTTP 403", st == 403, "http=%s" % st)

    st, raw = api("GET", ADMIN, token=op_o_t)
    say("  op_order(ORDER_ADMIN)        http=%s code=%s %s" % (st, body_code(raw), short(raw, 90)))
    say("     ★ 它有 order:* 但【故意没有】product:* ⇒ 应该是 403")
    chk("#9 ★ op_order（有 order:* 无 product:list）被拒：真 HTTP 403", st == 403, "http=%s" % st)

    st, raw = api("GET", "%s/1" % ADMIN, token=op_o_t)
    say("  op_order 打详情              http=%s code=%s %s" % (st, body_code(raw), short(raw, 90)))
    chk("#10 ★ 详情端点同样按权限把关（product:detail）：真 HTTP 403", st == 403, "http=%s" % st)

    st_p, b_p, raw_p = japi("GET", ADMIN, token=op_p_t)
    say("  op_product(PRODUCT_ADMIN)    http=%s code=%s" % (st_p, b_p.get("code")))
    chk("#11 op_product（有 product:*）通过：HTTP 200 + code 200",
        st_p == 200 and b_p.get("code") == 200, "http=%s code=%s" % (st_p, b_p.get("code")))

    st_a, b_a, raw_a = japi("GET", ADMIN, token=adm_t)
    say("  admin(SUPER_ADMIN)           http=%s code=%s" % (st_a, b_a.get("code")))
    chk("#12 admin（超管）通过：HTTP 200 + code 200",
        st_a == 200 and b_a.get("code") == 200, "http=%s code=%s" % (st_a, b_a.get("code")))
    chk("#13 ★★ 两种身份的响应体【逐字节相同】—— 管理端不做归属过滤（数据权限反转的正向证据）",
        json.dumps(b_p, sort_keys=True, ensure_ascii=False)
        == json.dumps(b_a, sort_keys=True, ensure_ascii=False))

    # ---------------------------------------------------------- [4] 分页口径（造夹具前）
    say("\n[4] 分页口径（造夹具【之前】：此刻库里全是上架，两个端应该看到同样多）")

    def apage(p=None, s=None, extra="", token=None, path=ADMIN):
        qs = []
        if p is not None:
            qs.append("current=%s" % p)
        if s is not None:
            qs.append("size=%s" % s)
        if extra:
            qs.append(extra)
        q = ("?" + "&".join(qs)) if qs else ""
        st_, b_, raw_ = japi("GET", path + q, token=token)
        return st_, (b_.get("data") or {}), b_, raw_

    _, d, b, _ = apage(token=op_p_t)
    say("  管理端(不筛选) records=%d total=%s current=%s size=%s"
        % (len(d.get("records") or []), d.get("total"), d.get("current"), d.get("size")))
    chk("#14 管理端不筛选时 total == 库里活商品数 %d" % SEED_ALIVE,
        d.get("total") == SEED_ALIVE, "实得 %s" % d.get("total"))
    _, dc, bc, _ = apage(token=None, path=CEND)
    say("  C 端(匿名)     total=%s" % dc.get("total"))
    chk("#15 C 端匿名分页 total == %d（此刻两端一致 —— 差异要等夹具进来才显形）" % SEED_ALIVE,
        dc.get("total") == SEED_ALIVE, "实得 %s" % dc.get("total"))
    recs = d.get("records") or []
    chk("#16 ★ 每条 record 的 key 集合 == ProductVO 的 9 个字段（无多无少、null 也照回）",
        bool(recs) and all(sorted(r.keys()) == sorted(VO_FIELDS) for r in recs),
        "首条 keys=%s" % (sorted(recs[0].keys()) if recs else "[]"))
    _, d_np, _, _ = apage(token=op_p_t, p=None, s=None)
    chk("#17 不传 page/size 时走 defaultValue：current=1 / size=10",
        d_np.get("current") == 1 and d_np.get("size") == 10,
        "current=%s size=%s" % (d_np.get("current"), d_np.get("size")))

    # ---------------------------------------------------------- [5] 造下架夹具
    say("\n[5] ★★ 造夹具：INSERT 1 条 status=0 商品（库里原有 5 条全是上架）")
    fx_id, rc, raw_fx = insert_fixture()
    say("  INSERT rc=%s returncode=%s ；新 id = %s" % (rc, rc, fx_id))
    chk("#18 夹具落库：products 活行 %d -> %d，且该行 status=0" % (SEED_ALIVE, SEED_ALIVE + 1),
        fx_id is not None
        and alive_products() == SEED_ALIVE + 1
        and int(one("SELECT status FROM products WHERE id=%d" % fx_id)) == 0,
        "fx_id=%s alive=%d" % (fx_id, alive_products()))
    if fx_id is None:
        say("\nABORT: 夹具未落库\n%s" % raw_fx)
        flush()
        return 1

    _, d5, _, _ = apage(s=100, token=op_p_t)
    _, d5c, _, _ = apage(s=100, token=None, path=CEND)
    ids_admin = [r["id"] for r in (d5.get("records") or [])]
    ids_cend = [r["id"] for r in (d5c.get("records") or [])]
    say("  管理端总览 total=%s ids=%s" % (d5.get("total"), ids_admin))
    say("  C 端总览   total=%s ids=%s" % (d5c.get("total"), ids_cend))
    chk("#19 ★★ 管理端 total == %d（含下架那条）" % (SEED_ALIVE + 1),
        d5.get("total") == SEED_ALIVE + 1, "实得 %s" % d5.get("total"))
    chk("#20 ★★ C 端 total 仍 == %d（下架对 C 端不可见）" % SEED_ALIVE,
        d5c.get("total") == SEED_ALIVE, "实得 %s" % d5c.get("total"))
    chk("#21 ★★ 管理端 records 里能取到夹具 id（含下架的直接证据）",
        fx_id in ids_admin, "ids=%s fx=%s" % (ids_admin, fx_id))
    chk("#22 ★★ C 端 records 里取不到夹具 id（反向对照，缺了这条「含下架」就没被证明）",
        fx_id not in ids_cend, "ids=%s fx=%s" % (ids_cend, fx_id))

    # ---------------------------------------------------------- [6] status 可选过滤
    say("\n[6] ★★ status 可选过滤：eq(status != null, 列, 值) 的 condition 必须写对")
    say("     写错成 .eq(Product::getStatus, 1) 写死 → 不传时也会少掉下架（#25 会当场抓住）")

    _, d0, _, _ = apage(s=100, extra="status=0", token=op_p_t)
    ids0 = [r["id"] for r in (d0.get("records") or [])]
    say("  status=0 -> total=%s ids=%s" % (d0.get("total"), ids0))
    chk("#23 status=0 只命中夹具那一条", d0.get("total") == 1 and ids0 == [fx_id],
        "total=%s ids=%s" % (d0.get("total"), ids0))

    _, d1, _, _ = apage(s=100, extra="status=1", token=op_p_t)
    ids1 = [r["id"] for r in (d1.get("records") or [])]
    say("  status=1 -> total=%s ids=%s" % (d1.get("total"), ids1))
    chk("#24 status=1 命中 %d 条且不含夹具" % SEED_ALIVE,
        d1.get("total") == SEED_ALIVE and fx_id not in ids1,
        "total=%s ids=%s" % (d1.get("total"), ids1))

    chk("#25 ★★ 不传 status == 两者都要（total %d）—— 若被写成写死 status=1 这里会掉到 %d"
        % (SEED_ALIVE + 1, SEED_ALIVE),
        d5.get("total") == SEED_ALIVE + 1, "实得 %s" % d5.get("total"))

    # ---------------------------------------------------------- [7] 详情（下架也能看）
    say("\n[7] 详情：管理端必须能看【下架】商品（C 端 getDetail 不判 status，恰好复用）")
    st_fx, b_fx, raw_fx2 = japi("GET", "%s/%d" % (ADMIN, fx_id), token=op_p_t)
    say("  管理端 GET /%d -> http=%s code=%s status=%s name=%s"
        % (fx_id, st_fx, b_fx.get("code"), (b_fx.get("data") or {}).get("status"),
           (b_fx.get("data") or {}).get("name")))
    chk("#26 ★★ 下架商品的详情可读：HTTP 200 + code 200 + status==0",
        st_fx == 200 and b_fx.get("code") == 200
        and (b_fx.get("data") or {}).get("status") == 0,
        "http=%s code=%s data=%s" % (st_fx, b_fx.get("code"), short(raw_fx2, 120)))

    st_1, b_1, _ = japi("GET", "%s/1" % ADMIN, token=op_p_t)
    d1d = b_1.get("data") or {}
    say("  管理端 GET /1  -> http=%s code=%s id=%s skus=%s images=%s"
        % (st_1, b_1.get("code"), d1d.get("id"),
           len(d1d.get("skus") or []), len(d1d.get("images") or [])))
    chk("#27 种子商品详情：id 正确且含 skus / images 两个子结构（复用 getDetail）",
        st_1 == 200 and b_1.get("code") == 200 and d1d.get("id") == 1
        and isinstance(d1d.get("skus"), list) and isinstance(d1d.get("images"), list),
        "http=%s code=%s id=%s" % (st_1, b_1.get("code"), d1d.get("id")))

    st_nf, raw_nf = api("GET", "%s/99999999" % ADMIN, token=op_p_t)
    say("  管理端 GET /99999999 -> http=%s code=%s %s"
        % (st_nf, body_code(raw_nf), short(raw_nf, 110)))
    chk("#28 不存在的商品 -> code 404（本项目业务异常走 HTTP 200 + body.code）",
        body_code(raw_nf) == 404, "http=%s code=%s" % (st_nf, body_code(raw_nf)))

    st_bad, raw_bad = api("GET", "%s/abc" % ADMIN, token=op_p_t)
    say("  管理端 GET /abc -> http=%s code=%s %s"
        % (st_bad, body_code(raw_bad), short(raw_bad, 110)))
    chk("#29 路径参数类型不匹配 -> HTTP 200 + code 400",
        st_bad == 200 and body_code(raw_bad) == 400,
        "http=%s code=%s" % (st_bad, body_code(raw_bad)))

    # ---------------------------------------------------------- [8] categoryId 展开
    say("\n[8] ★ categoryId 过滤：沿用「自己 + 直接子分类」的展开口径（expandCategoryIds）")
    say("     种子分布：商品 1/2/3 属分类 11（父 1）；商品 4/5 属分类 21（父 2）；夹具属 11")

    def cat(cid, expect, note):
        _, dd, _, _ = apage(s=100, extra="categoryId=%s" % cid, token=op_p_t)
        n = len(dd.get("records") or [])
        say("  categoryId=%-8s -> total=%-3s records=%-2d   (%s)" % (cid, dd.get("total"), n, note))
        return dd

    dd11 = cat(11, 4, "二级分类本身：3 种子 + 夹具")
    chk("#30 categoryId=11（子分类）命中 4 条", dd11.get("total") == 4, "实得 %s" % dd11.get("total"))
    dd1 = cat(1, 4, "★ 顶级 1 必须【展开】到子分类 11 ⇒ 与上一条同结果")
    chk("#31 ★ categoryId=1（顶级）也命中 4 条 == categoryId=11 —— 父子展开生效",
        dd1.get("total") == 4, "实得 %s" % dd1.get("total"))
    dd2 = cat(2, 2, "顶级 2 + 子分类 21：种子 4/5 两条")
    chk("#32 categoryId=2 命中 2 条（2 与 21）", dd2.get("total") == 2, "实得 %s" % dd2.get("total"))
    dd9 = cat(999999, 0, "★ 不存在的分类 → 空列表，不 500")
    chk("#33 categoryId=999999 -> 0 条且 HTTP 200（IN (空集) 不报错）",
        dd9.get("total") == 0, "实得 %s" % dd9.get("total"))

    # ---------------------------------------------------------- [9] keyword
    say("\n[9] keyword 模糊匹配")
    _, dk1, _, _ = apage(s=100, extra="keyword=iPhone", token=op_p_t)
    say("  keyword=iPhone      -> total=%s names=%s"
        % (dk1.get("total"), [r.get("name") for r in (dk1.get("records") or [])]))
    chk("#34 keyword=iPhone 命中 1 条", dk1.get("total") == 1, "实得 %s" % dk1.get("total"))
    _, dk2, _, _ = apage(s=100, extra="keyword=NOSUCHKEYWORD", token=op_p_t)
    say("  keyword=NOSUCH...   -> total=%s" % dk2.get("total"))
    chk("#35 keyword 无命中 -> 0 条且不 500", dk2.get("total") == 0, "实得 %s" % dk2.get("total"))

    # ---------------------------------------------------------- [10] 夹紧
    say("\n[10] ★★ 夹紧四态（MP 的两个静默坑：size=0 返空列表、size<0 查全表）")
    say("     本方法的夹紧写在 Service（pageAdminProducts）里，与 Day 17 的 listSkus 同层")
    clamp_cases = [
        (0, 1, "size=0 夹到 1（不夹时 MP 返回空列表）"),
        (-5, 1, "size=-5 夹到 1（不夹时 MP 不执行分页、查全表）"),
        (99999, 100, "size>100 夹到 MAX_PAGE_SIZE=100"),
        (1, 1, "原样"),
        (6, 6, "原样"),
    ]
    sizes_after = {}
    for s_in, s_expect, note in clamp_cases:
        _, dd, _, _ = apage(s=s_in, token=op_p_t)
        sizes_after[s_in] = dd.get("size")
        say("  size=%-6s -> 回传 size=%-4s records=%-2d total=%-3s   (%s)"
            % (s_in, dd.get("size"), len(dd.get("records") or []), dd.get("total"), note))
    chk("#36 size=0 回传 size==1 且【仍有 1 条记录】（不夹则 0 条）",
        sizes_after.get(0) == 1
        and len((apage(s=0, token=op_p_t)[1].get("records") or [])) == 1,
        "size=%s" % sizes_after.get(0))
    chk("#37 size=-5 回传 size==1 且【只有 1 条】（不夹则查全表）",
        sizes_after.get(-5) == 1
        and len((apage(s=-5, token=op_p_t)[1].get("records") or [])) == 1,
        "size=%s" % sizes_after.get(-5))
    chk("#38 size=99999 回传 size==100", sizes_after.get(99999) == 100,
        "实得 %s" % sizes_after.get(99999))
    _, dcur, _, _ = apage(p=0, s=10, token=op_p_t)
    say("  current=0 -> 回传 current=%s" % dcur.get("current"))
    chk("#39 current=0 回传 current==1（page<1 归一到 1）",
        dcur.get("current") == 1, "实得 %s" % dcur.get("current"))
    totals = [apage(s=s_in, token=op_p_t)[1].get("total") for s_in in (0, -5, 99999, 1, 6)]
    say("  四种边界下的 total：%s" % totals)
    chk("#40 ★ 夹紧只影响页大小、不改总数：四种边界的 total 恒为 %d" % (SEED_ALIVE + 1),
        all(t == SEED_ALIVE + 1 for t in totals), str(totals))
    chk("#41 size=1 / size=6 原样回传（夹紧不是无脑钳到两端）",
        sizes_after.get(1) == 1 and sizes_after.get(6) == 6,
        "size=1 -> %s ; size=6 -> %s" % (sizes_after.get(1), sizes_after.get(6)))

    # ---------------------------------------------------------- [11] 9 字段对账
    say("\n[11] ★★ 9 字段逐行与 DB 对账（不信接口自报）")
    _, d_all, _, _ = apage(s=100, token=op_p_t)
    api_rows = [rec_norm(r) for r in (d_all.get("records") or [])]
    db_all = db_rows()
    say("  API 条数 = %d ；DB 活行 = %d" % (len(api_rows), len(db_all)))
    chk("#42 管理端全量条数 == 6（5 种子 + 夹具）",
        len(api_rows) == SEED_ALIVE + 1, "实得 %d" % len(api_rows))
    chk("#43 ★★ 6 条 × 9 字段【逐字段】与 DB 相同（含 categoryName / brandName 的补齐）",
        api_rows == db_all,
        "首条不符: %s" % next((("api=%s vs db=%s" % (a, d)) for a, d in zip(api_rows, db_all) if a != d),
                              "无"))
    ids_all = [r["id"] for r in api_rows]
    chk("#44 按 id 严格降序（orderByDesc(Product::getId) 生效）",
        ids_all == sorted(ids_all, reverse=True) and len(set(ids_all)) == len(ids_all), str(ids_all))
    chk("#45 ★ 每条 categoryName 都非空（fillNames 批量补齐生效，不是 N+1 也不是漏补）",
        all(r["categoryName"] for r in api_rows),
        str([r["id"] for r in api_rows if not r["categoryName"]]))
    _, dc_all, _, _ = apage(s=100, token=None, path=CEND)
    api_c = [rec_norm(r) for r in (dc_all.get("records") or [])]
    db_c = db_rows(extra="AND p.status = 1")
    say("  C 端 9 字段对账：api=%d 行 / db(status=1)=%d 行" % (len(api_c), len(db_c)))
    chk("#46 ★ C 端列表 9 字段同样与 DB 一致（证明【没顺手改坏】C 端口径）",
        api_c == db_c,
        "首条不符: %s" % next((("api=%s vs db=%s" % (a, d)) for a, d in zip(api_c, db_c) if a != d),
                              "无"))

    # ---------------------------------------------------------- [12] 只读性 + CLEANUP
    say("\n[12] 只读性 + CLEANUP（本链路不得改动任何业务行）")
    same_seed = seed_snapshot() == base_seed
    say("  5 条种子快照：%s" % ("逐字节相同" if same_seed else "★ 与基线不同"))
    chk("#47 ★ 5 条种子商品逐字节未变（本脚本只 INSERT 自己的夹具）", same_seed)

    now_counts = counters()
    diff = {k: (base_counts[k], now_counts[k]) for k in TABLES if base_counts[k] != now_counts[k]}
    say("  计数差异（清理前）：%s" % (diff or "无"))
    chk("#48 除 products 多出夹具 1 行外，其余 9 张表计数全未变",
        diff == {"products": (SEED_ALIVE, SEED_ALIVE + 1)}, str(diff))

    _, drc = psql("DELETE FROM products WHERE id = %d" % fx_id)
    left = int(one("SELECT count(*) FROM products WHERE id = %d" % fx_id))
    fin_counts = counters()
    say("  DELETE rc=%s ；夹具残留 = %d 行 ；products %d -> %d"
        % (drc, left, now_counts["products"], fin_counts["products"]))
    chk("#49 ★ 夹具物理删净：按 id 查 0 行，且活行回 %d" % SEED_ALIVE,
        left == 0 and alive_products() == SEED_ALIVE,
        "left=%d alive=%d" % (left, alive_products()))
    chk("#50 ★ 十张表计数全部回基线（M1 回归 198/198 的前提）",
        fin_counts == base_counts,
        str({k: (base_counts[k], fin_counts[k]) for k in TABLES if base_counts[k] != fin_counts[k]}))
    _, d_end, _, _ = apage(s=100, token=op_p_t)
    _, d_endc, _, _ = apage(s=100, token=None, path=CEND)
    say("  收尾：管理端 total=%s ；C 端 total=%s" % (d_end.get("total"), d_endc.get("total")))
    chk("#51 ★ 收尾后两端 total 都回 5（管理端「含下架」的能力仍在，只是库里已无下架样本）",
        d_end.get("total") == SEED_ALIVE and d_endc.get("total") == SEED_ALIVE,
        "admin=%s cend=%s" % (d_end.get("total"), d_endc.get("total")))

    # ---------------------------------------------------------- verdict
    say("\n" + "=" * 78)
    say("ASSERTIONS：实得 %d 条" % len(checks))
    say("=" * 78)
    passed = 0
    for name, good, detail in checks:
        say("  [%s] %s%s" % ("PASS" if good else "FAIL", name,
                            ("   <- " + detail) if (detail and not good) else ""))
        passed += 1 if good else 0
    say("\nRESULT: %d/%d passed" % (passed, len(checks)))
    say("★ 满额自校验：FULL_TOTAL = %d ；实得 %d ；%s"
        % (FULL_TOTAL, len(checks),
           "一致" if len(checks) == FULL_TOTAL else "★ 不一致 —— 有断言未被创建（分母缩水）"))
    say("VERDICT: %s" % ("ADMIN-PRODUCT-READ OK -- 权限矩阵有区分度、"
                         "含下架口径与 C 端形成对照、status 可选过滤成立、"
                         "父子分类展开生效、9 字段与 DB 逐字段一致"
                         if (passed == len(checks) and len(checks) == FULL_TOTAL)
                         else "NOT CLEAN -- 见上面 FAIL 行"))
    flush()
    print("report -> %s   %d/%d passed (FULL_TOTAL=%d)" % (OUT, passed, len(checks), FULL_TOTAL))
    return 0 if (passed == len(checks) and len(checks) == FULL_TOTAL) else 1


# ★★ 满额常量：新增/删除任何一条断言时必须同步改这里。
#    它存在的唯一理由是防止「条件性断言未被创建」把失败看轻（Day 17 链路 C 踩过 36 vs 39）。
#    51 = 设计值（[0]4 + [1]2 + [2]1 + [3]6 + [4]4 + [5]5 + [6]3 + [7]4 + [8]4 + [9]2
#                + [10]6 + [11]5 + [12]5）。
FULL_TOTAL = 51

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                           # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
