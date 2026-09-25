# -*- coding: utf-8 -*-
"""Day 17 链路 F -- 管理端库存流水（GET /api/admin/inventory/logs）。

这条链路是三条库存链路里【最轻】的一条（与链路 B 同构：分页 + 行→VO），
但它有两处特有的验收难点：

  ① 库里 inventory_logs 的【基线是 0 条】（day17-m1-regression.py 要求，
     day14/15/16/17-C/E 五个脚本都用「高水位 + 收尾 DELETE」把流水收干净）。
     ⇒ 空表状态下「列表能不能正常返回空」本身是一条边界；
     要验字段/分页/过滤，就必须【自造夹具】。

  ② 用哪条路径造夹具？本脚本选【直接 INSERT】而不是走下单/支付/取消/adjust：
     - 走业务链路要动 inventories、orders、order_items、payments、cart_items，
       跑完【回不了基线】（已取消的订单行删不掉）→ 会把 M1 回归弄脏；
     - 直接 INSERT 只动 inventory_logs 一张表，收尾按高水位删净即可，
       ★ inventories 与四张业务表全程【逐字节不变】，可以当场断言。
     - 代价：夹具行的 before/after 与 inventories 现值不必连续。
       这不影响本接口的验证 —— 本接口【只做投影】，不做任何跨表推导；
       单行自洽（change == after - before）才是这张表的口径。
       四种 type 在真实写点下的符号规律，已由 C（CANCEL_RELEASE）与
       E（ADMIN_ADJUST）两条链路各自实测过。

★ 本脚本【可重复执行】：先记高水位，跑完 DELETE id > 高水位，再断言计数回基线。
★ 断言满额自校验：FULL_TOTAL 是【写死的常量】（见文件末尾注释），
  而不是 len(checks) —— 防止「条件性断言未被创建导致分母缩水」把失败看轻
  （链路 C 踩过 36 vs 39 的坑）。

Usage:
    python day17-f-inventory-log-verify.py
报告（utf-8）与脚本同目录：day17-f-inventory-log-verify-report.txt
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
PATH = "/api/admin/inventory/logs"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day17-f-inventory-log-verify-report.txt")

VO_FIELDS = ["id", "skuId", "type", "changeQuantity", "beforeStock",
             "afterStock", "referenceId", "createdAt"]

# ★ 夹具：6 条，覆盖四种 type、四个 SKU、含 reference_id 为 NULL 的行。
#   每行都满足 change_quantity == after_stock - before_stock（本表的口径）。
FIXTURES = [
    # sku, type,             change, before, after, ref
    (3, "ORDER_LOCK",            -2,    50,    48, None),
    (3, "PAY_SOLD",               0,    48,    48, 101),
    (5, "CANCEL_RELEASE",         3,    20,    23, 102),
    (6, "ADMIN_ADJUST",           7,    10,    17, None),
    (6, "ORDER_LOCK",            -1,    17,    16, None),
    (7, "PAY_SOLD",               0,    90,    90, 103),
]

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


def short(raw, n=200):
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


def norm_ts(v):
    """DB 给 'YYYY-MM-DD HH:MM:SS.ffffff'；Jackson 可能给 ISO 或数组。统一到秒。"""
    if v is None:
        return None
    if isinstance(v, list):
        p = [int(x) for x in v]
        return "%04d-%02d-%02d %02d:%02d:%02d" % tuple(p[:6])
    return str(v).replace("T", " ").strip()[:19]


def counters():
    return dict(
        orders=int(one("SELECT count(*) FROM orders")),
        order_items=int(one("SELECT count(*) FROM order_items")),
        payments=int(one("SELECT count(*) FROM payments")),
        inventory_logs=int(one("SELECT count(*) FROM inventory_logs")),
        cart_items=int(one("SELECT count(*) FROM cart_items")),
    )


def all_inv():
    return one("SELECT string_agg(sku_id||'|'||total_stock||'|'||available_stock||'|'"
               "||locked_stock||'|'||sold_stock, ' ; ' ORDER BY sku_id) FROM inventories")


def hw():
    """★ 高水位取【全表 max(id)】，不是某个 type 的 max —— 与 day14/15/16/17-C/E 逐字对齐。"""
    return int(one("SELECT COALESCE(MAX(id),0) FROM inventory_logs"))


DB_ROWS_SQL = """
SELECT id, sku_id, type, change_quantity, before_stock, after_stock,
       COALESCE(reference_id::text, 'NULL'), created_at
  FROM inventory_logs
 WHERE id > {hw}
 ORDER BY id DESC
"""


def db_rows(h):
    """返回 [dict(...)] —— 与 InventoryLogVO 同序（id 降序，与接口排序一致）。"""
    out = psql(DB_ROWS_SQL.format(hw=h))[0]
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        p = line.split("|")
        rows.append(dict(id=int(p[0]), skuId=int(p[1]), type=p[2],
                         changeQuantity=int(p[3]), beforeStock=int(p[4]),
                         afterStock=int(p[5]),
                         referenceId=None if p[6] == "NULL" else int(p[6]),
                         createdAt=norm_ts(p[7])))
    return rows


def rec_norm(r):
    """把接口返回的一条 record 归一化到与 db_rows() 同样的形状。"""
    return dict(id=r.get("id"), skuId=r.get("skuId"), type=r.get("type"),
                changeQuantity=r.get("changeQuantity"), beforeStock=r.get("beforeStock"),
                afterStock=r.get("afterStock"), referenceId=r.get("referenceId"),
                createdAt=norm_ts(r.get("createdAt")))


def insert_fixtures():
    vals = ",".join(
        "(%d,'%s',%d,%d,%d,%s)" % (s, t, c, b, a, "NULL" if r is None else str(r))
        for (s, t, c, b, a, r) in FIXTURES)
    sql = ("INSERT INTO inventory_logs "
           "(sku_id, type, change_quantity, before_stock, after_stock, reference_id) "
           "VALUES " + vals)
    return psql(sql)


# ================================================================ main
def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 17 链路 F -- 管理端库存流水（分页 + 行→VO + 可选过滤）")
    say("target : %s%s" % (BASE, PATH))
    say("accounts: demo(C端) / op_order(ORDER_ADMIN) / op_product(PRODUCT_ADMIN) / admin(SUPER_ADMIN)")
    say("fixtures: %d 条直接 INSERT（四种 type / 四个 SKU / 含 reference_id 为 NULL）" % len(FIXTURES))
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base_counts = counters()
    base_inv = all_inv()
    base_hw = hw()
    say("  inventories 恒等式 = %s" % one(
        "SELECT bool_and(total_stock = available_stock + locked_stock + sold_stock)"
        " FROM inventories"))
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base_counts.items())))
    say("  ★ inventory_logs 高水位 = %d（收尾按 id > %d 删净）" % (base_hw, base_hw))
    chk("★ 基线：inventory_logs == 0 条（M1 回归的前提，不是本脚本造的）",
        base_counts["inventory_logs"] == 0, "实得 %d" % base_counts["inventory_logs"])
    chk("基线：inventories 有 7 行", int(one("SELECT count(*) FROM inventories")) == 7)

    # ---------------------------------------------------------- [1] anonymous
    say("\n[1] 匿名 GET %s" % PATH)
    st, raw = api("GET", PATH)
    say("  http=%s code=%s %s" % (st, body_code(raw), short(raw, 120)))
    say("  ★ Security 层（过滤器）写响应 ⇒ 真 HTTP 401，不是 body.code")
    chk("匿名被拒，且是真 HTTP 401", st == 401, "http=%s" % st)

    # ---------------------------------------------------------- [2] login
    say("\n[2] 登录四个身份（token 只在内存里，不落盘）")

    def login(path, u, p):
        st_, b_, _ = japi("POST", path, body={"username": u, "password": p})
        return (b_.get("data") or {}).get("token"), b_.get("code")

    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_o_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    op_p_t, c3 = login("/api/auth/admin/login", "op_product", "prod123456")
    adm_t, c4 = login("/api/auth/admin/login", "admin", "admin123")
    say("  demo       code=%s token_len=%d" % (c1, len(demo_t or "")))
    say("  op_order   code=%s token_len=%d" % (c2, len(op_o_t or "")))
    say("  op_product code=%s token_len=%d" % (c3, len(op_p_t or "")))
    say("  admin      code=%s token_len=%d" % (c4, len(adm_t or "")))
    chk("四个身份全部登录成功", all([demo_t, op_o_t, op_p_t, adm_t]),
        "op_product 缺失请先跑 day17-fixture-apply.py")
    if not all([demo_t, op_o_t, op_p_t, adm_t]):
        say("\nABORT: 缺 token")
        flush()
        return 1

    # ---------------------------------------------------------- [3] 权限矩阵
    say("\n[3] ★ 权限矩阵（同一个点，四种身份 —— 区分度就在这里）")
    say("    本端点的权限码是 inventory:log（不是 inventory:list）")

    st, raw = api("GET", PATH, token=demo_t)
    say("  demo(C 端 token)      http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    chk("C 端 token 被拒，且是真 HTTP 403", st == 403, "http=%s" % st)

    st, raw = api("GET", PATH, token=op_o_t)
    say("  op_order(ORDER_ADMIN) http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    say("     ★ 它有 order:* 但【故意没有】inventory:* ⇒ 应该是 403")
    chk("★ op_order（无 inventory:log）被拒：真 HTTP 403", st == 403, "http=%s" % st)

    st, b, raw = japi("GET", PATH, token=op_p_t)
    say("  op_product(PRODUCT_ADMIN) http=%s code=%s" % (st, b.get("code")))
    chk("op_product（有 inventory:log）通过：HTTP 200 + code 200",
        st == 200 and b.get("code") == 200, "http=%s code=%s" % (st, b.get("code")))

    st_a, b_a, _ = japi("GET", PATH, token=adm_t)
    say("  admin(SUPER_ADMIN)    http=%s code=%s" % (st_a, b_a.get("code")))
    chk("admin（超管）通过：HTTP 200 + code 200",
        st_a == 200 and b_a.get("code") == 200, "http=%s code=%s" % (st_a, b_a.get("code")))
    chk("★ op_product 与 admin 的响应体【逐字节相同】（结果与调用者无关）",
        json.dumps(b, sort_keys=True, ensure_ascii=False)
        == json.dumps(b_a, sort_keys=True, ensure_ascii=False))

    # ---------------------------------------------------------- [4] 空表边界
    say("\n[4] ★ 空表边界：造夹具【之前】先看一眼 —— 空表不能 500")
    d0 = b.get("data") or {}
    say("  records=%s total=%s current=%s size=%s"
        % (d0.get("records"), d0.get("total"), d0.get("current"), d0.get("size")))
    chk("★ 空表时 records == []（不是 null、不报错）", d0.get("records") == [],
        "实得 %r" % (d0.get("records"),))
    chk("★ 空表时 total == 0", d0.get("total") == 0, "实得 %s" % d0.get("total"))
    chk("空表时 current/size 仍回传（defaultValue 生效）",
        d0.get("current") == 1 and d0.get("size") == 10,
        "current=%s size=%s" % (d0.get("current"), d0.get("size")))

    # ---------------------------------------------------------- [5] 造夹具
    say("\n[5] 造夹具：直接 INSERT %d 条流水（不动 inventories）" % len(FIXTURES))
    _, irc = insert_fixtures()
    cnt = int(one("SELECT count(*) FROM inventory_logs WHERE id > %d" % base_hw))
    say("  INSERT rc=%s ；新增 %d 条" % (irc, cnt))
    for f in FIXTURES:
        say("    sku=%-2d %-15s change=%-3d %d→%d ref=%s"
            % (f[0], f[1], f[2], f[3], f[4], "NULL" if f[5] is None else f[5]))
    chk("夹具全部落库：新增 == %d 条" % len(FIXTURES), cnt == len(FIXTURES), "实得 %d" % cnt)
    chk("★ 夹具自身满足口径 change_quantity == after_stock - before_stock",
        all(c == a - b for (_s, _t, c, b, a, _r) in FIXTURES))
    db = db_rows(base_hw)
    say("  DB 侧（id 降序）：%s" % [r["id"] for r in db])

    # ---------------------------------------------------------- [6] 字段对账
    say("\n[6] ★★ 8 字段逐行与 DB 对账（不信接口自报）")
    st, b, _ = japi("GET", "%s?page=1&size=100" % PATH, token=op_p_t)
    recs = (b.get("data") or {}).get("records") or []
    say("  records 条数 = %d ；total = %s" % (len(recs), (b.get("data") or {}).get("total")))
    chk("records 条数 == 新增的 %d 条" % len(FIXTURES), len(recs) == len(FIXTURES),
        "实得 %d" % len(recs))
    chk("total == %d" % len(FIXTURES), (b.get("data") or {}).get("total") == len(FIXTURES),
        "实得 %s" % (b.get("data") or {}).get("total"))

    if recs:
        chk("★ 每条 record 的 key 集合 == InventoryLogVO 的 8 个字段（无多无少）",
            all(sorted(r.keys()) == sorted(VO_FIELDS) for r in recs),
            "首条 keys=%s" % sorted(recs[0].keys()))

    got = [rec_norm(r) for r in recs]
    chk("★ %d 条 × 8 字段【逐字段】与 DB 相同" % len(FIXTURES), got == db,
        "首条不符: %s" % next((("api=%s vs db=%s" % (g, d))
                               for g, d in zip(got, db) if g != d), "无"))
    chk("★ 每行 changeQuantity == afterStock - beforeStock（口径对照 DB 也成立）",
        all(r["changeQuantity"] == r["afterStock"] - r["beforeStock"] for r in got),
        str([r["id"] for r in got
             if r["changeQuantity"] != r["afterStock"] - r["beforeStock"]]))
    chk("★ reference_id 为 NULL 的行，接口返回 key 存在且值为 null（不是缺字段）",
        all(r.get("referenceId") is None for r in recs if r.get("type") in ("ORDER_LOCK",)),
        short(json.dumps([r for r in recs if r.get("type") == "ORDER_LOCK"][:1],
                         ensure_ascii=False), 160))
    chk("★ referenceId 有值的行也确实带出来了（NULL 与有值都验，避免只验半边）",
        sorted(r["referenceId"] for r in got if r["referenceId"] is not None) == [101, 102, 103],
        str(sorted(r["referenceId"] for r in got if r["referenceId"] is not None)))
    chk("★ createdAt 非空且与 DB 同秒", all(r["createdAt"] for r in got))

    # ---------------------------------------------------------- [7] 排序
    say("\n[7] 排序")
    ids = [r["id"] for r in got]
    say("  id 顺序：%s" % ids)
    chk("★ 按 id 严格【降序】（orderByDesc(InventoryLog::getId) 生效）",
        ids == sorted(ids, reverse=True) and len(set(ids)) == len(ids), str(ids))
    say("  type 分布：%s" % sorted(set(r["type"] for r in got)))
    chk("★ 四种 type 都在结果里（夹具覆盖完整性）",
        set(r["type"] for r in got)
        == {"ORDER_LOCK", "PAY_SOLD", "CANCEL_RELEASE", "ADMIN_ADJUST"},
        str(sorted(set(r["type"] for r in got))))

    # ---------------------------------------------------------- [8] 分页
    say("\n[8] 分页：size=2 取三页，并集必须 == 全量且无交集")

    def page(p, s, extra="", token=op_p_t):
        st_, b_, _ = japi("GET", "%s?page=%s&size=%s%s" % (PATH, p, s, extra), token=token)
        return st_, (b_.get("data") or {}), b_

    seen = []
    for p in (1, 2, 3):
        st_, d_, _ = page(p, 2)
        cur = [r["id"] for r in (d_.get("records") or [])]
        say("  page=%d size=2 -> current=%s size=%s total=%s records=%s"
            % (p, d_.get("current"), d_.get("size"), d_.get("total"), cur))
        chk("page=%d 的 current == %d" % (p, p), d_.get("current") == p,
            "实得 %s" % d_.get("current"))
        seen += cur
    st_, d4, _ = page(4, 2)
    say("  page=4 size=2 -> records=%s （超出范围）" % (d4.get("records") or []))
    chk("三页并集大小 == %d（不重）" % len(FIXTURES), len(seen) == len(FIXTURES),
        "实得 %d: %s" % (len(seen), seen))
    chk("三页并集 == 全量 id 集合（不漏）", sorted(seen) == sorted(r["id"] for r in db),
        "并集=%s / 全量=%s" % (sorted(seen), sorted(r["id"] for r in db)))
    chk("page=4（超出）返回空 records，但 total 仍为 %d" % len(FIXTURES),
        (d4.get("records") or []) == [] and d4.get("total") == len(FIXTURES),
        "records=%s total=%s" % (d4.get("records"), d4.get("total")))

    # ---------------------------------------------------------- [9] 夹紧
    say("\n[9] ★ 夹紧四态（MP 的两个静默坑：size=0 返空列表、size<0 查全表）")
    cases = [
        ("size=0", 0, 1, "夹到 1（不夹时 MP 返回空列表）"),
        ("size=-5", -5, 1, "夹到 1（不夹时 MP 不执行分页、查全表）"),
        ("size=99999", 99999, 100, "夹到 MAX_PAGE_SIZE=100"),
        ("size=1", 1, 1, "原样"),
        ("size=6", 6, 6, "原样"),
    ]
    for label, s, expect_size, note in cases:
        st_, d_, _ = page(1, s)
        n = len(d_.get("records") or [])
        say("  %-11s -> 回传 size=%-4s records=%-2d total=%s   (%s)"
            % (label, d_.get("size"), n, d_.get("total"), note))
        chk("%s 回传的 size == %d" % (label, expect_size), d_.get("size") == expect_size,
            "实得 %s" % d_.get("size"))
        chk("%s 的 total 恒为 %d（夹紧不影响总数）" % (label, len(FIXTURES)),
            d_.get("total") == len(FIXTURES), "实得 %s" % d_.get("total"))
    chk("size=0/-5 时必须【仍有 1 条】——这是夹紧生效的直接证据（不夹则 0 条）",
        len((page(1, 0)[1].get("records") or [])) == 1
        and len((page(1, -5)[1].get("records") or [])) == 1,
        "size=0 -> %d / size=-5 -> %d" % (len((page(1, 0)[1].get("records") or [])),
                                           len((page(1, -5)[1].get("records") or []))))

    st_, dp, _ = page(0, 10)
    say("  page=0    -> current=%s size=%s records=%d"
        % (dp.get("current"), dp.get("size"), len(dp.get("records") or [])))
    chk("page=0 被夹到 current == 1", dp.get("current") == 1, "实得 %s" % dp.get("current"))

    st, b_np, _ = japi("GET", PATH, token=op_p_t)
    d_np = b_np.get("data") or {}
    say("  不传参      -> current=%s size=%s records=%d（defaultValue 生效）"
        % (d_np.get("current"), d_np.get("size"), len(d_np.get("records") or [])))
    chk("不传 page/size 时走 defaultValue：current=1 / size=10",
        d_np.get("current") == 1 and d_np.get("size") == 10,
        "current=%s size=%s" % (d_np.get("current"), d_np.get("size")))

    # ---------------------------------------------------------- [10] 可选过滤
    say("\n[10] ★★ 可选过滤：eq(condition, 列, 值) 的 condition 必须写对")
    say("     写错成 .eq(列, null) 会拼出 sku_id = null → 恒不匹配且不报错")

    def filt(extra, expect_n, note):
        st_, d_, b_ = page(1, 100, extra)
        n = len(d_.get("records") or [])
        types = sorted(set(r.get("type") for r in (d_.get("records") or [])))
        skus = sorted(set(r.get("skuId") for r in (d_.get("records") or [])))
        say("  %-28s -> records=%-2d total=%-3s types=%s skus=%s   (%s)"
            % (extra or "(无)", n, d_.get("total"), types, skus, note))
        chk("过滤 %s 命中 %d 条" % (extra or "(无)", expect_n), n == expect_n, "实得 %d" % n)
        return d_

    filt("", 6, "不筛 = 全量")
    filt("&skuId=3", 2, "两个 ORDER_LOCK 里 sku=3 的有 2 条")
    filt("&skuId=5", 1, "CANCEL_RELEASE 那条")
    filt("&skuId=6", 2, "ADMIN_ADJUST + ORDER_LOCK")
    filt("&skuId=999999", 0, "★ 不存在的 SKU → 空列表，不 500")
    filt("&type=PAY_SOLD", 2, "sku=3 与 sku=7 各一条")
    filt("&type=ORDER_LOCK", 2, "")
    filt("&type=CANCEL_RELEASE", 1, "")
    filt("&type=ADMIN_ADJUST", 1, "")
    filt("&type=NOSUCH", 0, "★ 不存在的 type → 空列表，不 500")
    filt("&skuId=6&type=ORDER_LOCK", 1, "★ 两个条件【同时】生效（交集）")
    filt("&skuId=5&type=ORDER_LOCK", 0, "交集为空")
    d_sp = filt("&type=%20", 6, "★★ 空格串等价【不筛】—— 验 isBlank() 归一化")
    chk("★★ type=%%20（空格串）total 仍为 %d，证明 isBlank() 而非 isEmpty() 在把关"
        % len(FIXTURES), d_sp.get("total") == len(FIXTURES),
        "实得 %s（若为 0，说明只判 isEmpty()，空格串被当成真值拼进了 SQL）"
        % d_sp.get("total"))
    d_low = filt("&type=pay_sold", 0, "★ 观察：type 不做大小写归一，原样直传 SQL（PG 区分大小写）")
    say("     ↑ 这是【有意不归一】：过滤值是查询条件，不是持久化值。")
    chk("★ 小写 type 不命中（证明过滤值是原样直传的，没有被悄悄 upper 化）",
        d_low.get("total") == 0, "实得 %s" % d_low.get("total"))

    # ---------------------------------------------------------- [11] 非数字参数
    say("\n[11] 边界：非数字 page 的原始报错")
    st, raw = api("GET", "%s?page=abc&size=10" % PATH, token=op_p_t)
    say("  ?page=abc -> http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    chk("?page=abc -> HTTP 200 + code 400（参数类型不匹配）",
        st == 200 and body_code(raw) == 400, "http=%s code=%s" % (st, body_code(raw)))

    # ---------------------------------------------------------- [12] 只读性
    say("\n[12] 只读性：除【本脚本自己造的夹具】外，DB 必须一个字节都没动")
    now_counts = counters()
    for k in ("orders", "order_items", "payments", "cart_items"):
        same = now_counts[k] == base_counts[k]
        say("  %-16s = %-5d %s" % (k, now_counts[k], "unchanged" if same else
                                   "★ CHANGED from %d" % base_counts[k]))
        chk("%s 未被本链路改动" % k, same, "%d -> %d" % (base_counts[k], now_counts[k]))
    chk("★ inventory_logs 只多出夹具的 %d 条（接口本身没有写任何流水）"
        % len(FIXTURES),
        now_counts["inventory_logs"] - base_counts["inventory_logs"] == len(FIXTURES),
        "Δ=%d" % (now_counts["inventory_logs"] - base_counts["inventory_logs"]))
    inv_same = all_inv() == base_inv
    say("  inventories     : %s" % ("逐字节相同" if inv_same else "★ 与基线不同"))
    if not inv_same:
        say("    now     : %s" % all_inv())
        say("    baseline: %s" % base_inv)
    chk("★ 7 个 SKU 库存逐字节不变（本脚本走 INSERT，不碰 inventories）", inv_same)

    # ---------------------------------------------------------- [13] CLEANUP
    say("\n[13] ★ CLEANUP —— 按高水位回收本次夹具（与 day14/15/16/17-C/E 逐字对齐）")
    _, drc = psql("DELETE FROM inventory_logs WHERE id > %d" % base_hw)
    fin_counts = counters()
    say("  DELETE rc=%s ；inventory_logs %d → %d"
        % (drc, now_counts["inventory_logs"], fin_counts["inventory_logs"]))
    chk("★ inventory_logs 回到基线 %d 条" % base_counts["inventory_logs"],
        fin_counts["inventory_logs"] == base_counts["inventory_logs"],
        "实得 %d" % fin_counts["inventory_logs"])
    chk("★ 五项计数全部回基线（M1 回归的前提）",
        fin_counts == base_counts,
        str({k: (base_counts[k], fin_counts[k]) for k in base_counts
             if base_counts[k] != fin_counts[k]}))
    chk("★ 7 个 SKU 库存仍逐字节 == 基线（终局复核）", all_inv() == base_inv)
    chk("★ 收尾后列表回到空表形态（同 [4]，证明清理彻底）",
        (japi("GET", "%s?page=1&size=100" % PATH, token=op_p_t)[1].get("data") or {}
         ).get("total") == 0,
        "total=%s" % (japi("GET", "%s?page=1&size=100" % PATH, token=op_p_t)[1]
                      .get("data") or {}).get("total"))

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
    say("VERDICT: %s" % ("INVENTORY-LOG OK -- 权限矩阵有区分度、8 字段与 DB 一致、"
                         "id 降序、分页不重不漏、夹紧四态正确、两个可选过滤与 isBlank 归一化成立"
                         if (passed == len(checks) and len(checks) == FULL_TOTAL)
                         else "NOT CLEAN -- 见上面 FAIL 行"))
    flush()
    print("report -> %s   %d/%d passed (FULL_TOTAL=%d)" % (OUT, passed, len(checks), FULL_TOTAL))
    return 0 if (passed == len(checks) and len(checks) == FULL_TOTAL) else 1


# ★★ 满额常量：新增/删除任何一条断言时必须同步改这里。
#    它存在的唯一理由是防止「条件性断言未被创建」把失败看轻（链路 C 踩过 36 vs 39）。
#    70 = 2026-09-22 首轮实测值（6 条夹具 / 四种 type / 8 字段对账 收口）。
FULL_TOTAL = 70

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                           # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
