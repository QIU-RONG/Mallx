# -*- coding: utf-8 -*-
"""Day 17 链路 D -- 管理端库存分页（GET /api/admin/inventory/skus）。

这条链路是三条库存链路里唯一【纯读】的一条，所以验收的重点不是「有没有写坏数据」，
而是三件事：

  ① 权限矩阵的【区分度】—— 必须用 op_order（ORDER_ADMIN，没有 inventory:*）
     打进来拿到 403。admin（SUPER_ADMIN）全是 200，它【证明不了】权限码写对了没；
  ② SQL 的 JOIN 语义 —— 9 个字段逐行与 DB 对账，其中 skuName / productName
     来自两个 LEFT JOIN。★ 别名写成驼峰会静默为 null 而不报错（PG 折小写），
     所以「9 个字段全部 non-null」本身就是对别名写法的检验；
  ③ 分页与夹紧 —— size=0 / size<0 是 MP 的两个经典静默坑
     （0 → 返空列表但 total 正常；<0 → 不执行分页、查全表）。
     夹紧写在 new Page<>() 之前才治得住。

★ 本端点是【只读】的，所以不需要清理；但仍要证实「跑完 DB 一个字节都没动」——
  这是留给 day17-m1-regression.py 的前提。

Usage:
    python day17-d-inventory-list-verify.py
报告（utf-8）与脚本同目录：day17-d-inventory-list-verify-report.txt
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
PATH = "/api/admin/inventory/skus"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day17-d-inventory-list-verify-report.txt")

VO_FIELDS = ["skuId", "skuName", "productId", "productName",
             "totalStock", "availableStock", "lockedStock", "soldStock", "updatedAt"]

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
    return p.stdout.decode("utf-8", "replace").strip()


def one(sql):
    """单值。⚠️ docker exec 回传行尾带 \\r —— 不 strip 会让比对恒为假。"""
    return psql(sql).strip()


def norm_ts(v):
    """DB 给 'YYYY-MM-DD HH:MM:SS.ffffff'；Jackson 可能给 ISO 或数组。统一到秒。"""
    if v is None:
        return None
    if isinstance(v, list):
        p = [int(x) for x in v]
        return "%04d-%02d-%02d %02d:%02d:%02d" % tuple(p[:6])
    return str(v).replace("T", " ").strip()[:19]


DB_ROWS_SQL = """
SELECT i.sku_id, COALESCE(s.name, '(规格已删除)'), s.product_id,
       COALESCE(p.name, '(商品已删除)'),
       i.total_stock, i.available_stock, i.locked_stock, i.sold_stock, i.updated_at
  FROM inventories i
  LEFT JOIN product_skus s ON s.id = i.sku_id
  LEFT JOIN products     p ON p.id = s.product_id
 ORDER BY i.sku_id
"""


def db_rows():
    """返回 [dict(...)] —— 与 InventoryVO 同序。"""
    out = psql(DB_ROWS_SQL)
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        p = line.split("|")
        rows.append(dict(skuId=int(p[0]), skuName=p[1], productId=int(p[2]) if p[2] else None,
                         productName=p[3], totalStock=int(p[4]), availableStock=int(p[5]),
                         lockedStock=int(p[6]), soldStock=int(p[7]), updatedAt=norm_ts(p[8])))
    return rows


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


def rec_norm(r):
    """把接口返回的一条 record 归一化到与 db_rows() 同样的形状。"""
    return dict(skuId=r.get("skuId"), skuName=r.get("skuName"), productId=r.get("productId"),
                productName=r.get("productName"), totalStock=r.get("totalStock"),
                availableStock=r.get("availableStock"), lockedStock=r.get("lockedStock"),
                soldStock=r.get("soldStock"), updatedAt=norm_ts(r.get("updatedAt")))


# ================================================================ main
def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 17 链路 D -- 管理端库存分页（LEFT JOIN ×2 + 分页夹紧）")
    say("target : %s%s" % (BASE, PATH))
    say("accounts: demo(C端) / op_order(ORDER_ADMIN) / op_product(PRODUCT_ADMIN) / admin(SUPER_ADMIN)")
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    db = db_rows()
    base_inv = all_inv()
    base_counts = counters()
    say("  inventories 行数 = %d ；恒等式 = %s" % (
        len(db), one("SELECT bool_and(total_stock = available_stock + locked_stock + sold_stock)"
                     " FROM inventories")))
    for r in db:
        say("    sku%-2d %-16s %-26s total=%-4d avail=%-4d locked=%-3d sold=%-3d"
            % (r["skuId"], r["skuName"], r["productName"], r["totalStock"],
               r["availableStock"], r["lockedStock"], r["soldStock"]))
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base_counts.items())))
    chk("基线：inventories 有 7 行（7 个 SKU）", len(db) == 7, "实得 %d" % len(db))

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

    st, raw = api("GET", PATH, token=demo_t)
    say("  demo(C 端 token)      http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    chk("C 端 token 被拒，且是真 HTTP 403", st == 403, "http=%s" % st)

    st, raw = api("GET", PATH, token=op_o_t)
    say("  op_order(ORDER_ADMIN) http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    say("     ★ 它有 order:* 但【故意没有】inventory:* ⇒ 应该是 403；")
    say("       如果这里给 200，说明库存权限被误发给了 ORDER_ADMIN（或权限码写错）")
    chk("★ op_order（无 inventory:list）被拒：真 HTTP 403", st == 403, "http=%s" % st)

    st, b, raw = japi("GET", PATH, token=op_p_t)
    say("  op_product(PRODUCT_ADMIN) http=%s code=%s" % (st, b.get("code")))
    chk("op_product（有 inventory:list）通过：HTTP 200 + code 200",
        st == 200 and b.get("code") == 200, "http=%s code=%s" % (st, b.get("code")))

    st_a, b_a, _ = japi("GET", PATH, token=adm_t)
    say("  admin(SUPER_ADMIN)    http=%s code=%s" % (st_a, b_a.get("code")))
    chk("admin（超管）通过：HTTP 200 + code 200",
        st_a == 200 and b_a.get("code") == 200, "http=%s code=%s" % (st_a, b_a.get("code")))
    chk("★ op_product 与 admin 的响应体【逐字节相同】（结果与调用者无关）",
        json.dumps(b, sort_keys=True, ensure_ascii=False)
        == json.dumps(b_a, sort_keys=True, ensure_ascii=False))

    # ---------------------------------------------------------- [4] 字段对账
    say("\n[4] ★★ 9 字段逐行与 DB 对账（不信接口自报）")
    data = b.get("data") or {}
    recs = data.get("records") or []
    say("  records 条数 = %d ；total = %s ；current = %s ；size = %s"
        % (len(recs), data.get("total"), data.get("current"), data.get("size")))
    chk("records 条数 == DB 的 7 行（默认 size=10）", len(recs) == 7, "实得 %d" % len(recs))
    chk("total == 7", data.get("total") == 7, "实得 %s" % data.get("total"))

    if recs:
        chk("★ 每条 record 的 key 集合 == InventoryVO 的 9 个字段（无多无少）",
            all(sorted(r.keys()) == sorted(VO_FIELDS) for r in recs),
            "首条 keys=%s" % sorted(recs[0].keys()))

    got = [rec_norm(r) for r in recs]
    chk("★ 7 条 × 9 字段【逐字段】与 DB 相同（含两个 JOIN 出来的名称）",
        got == db, "首条不符: %s" % next((("api=%s vs db=%s" % (g, d))
                                        for g, d in zip(got, db) if g != d), "无"))

    bad_null = [(r["skuId"], k) for r in got for k in ("skuName", "productName") if not r.get(k)]
    chk("★ skuName / productName 全部非空（别名写法的直接检验）", not bad_null, str(bad_null))

    # ---------------------------------------------------------- [5] 排序 + 恒等式
    say("\n[5] 排序与恒等式")
    ids = [r["skuId"] for r in got]
    say("  skuId 顺序：%s" % ids)
    chk("按 sku_id 严格升序（对账视图要的是顺序稳定）", ids == sorted(ids) and len(set(ids)) == len(ids), str(ids))
    identity = [(r["skuId"], r["totalStock"], r["availableStock"] + r["lockedStock"] + r["soldStock"])
                for r in got
                if r["totalStock"] != r["availableStock"] + r["lockedStock"] + r["soldStock"]]
    chk("★ 每行 total == available + locked + sold（四格恒等式）", not identity, str(identity))

    # ---------------------------------------------------------- [6] 分页
    say("\n[6] 分页：size=3 取三页，并集必须 == 全量且无交集")

    def page(p, s, token=op_p_t):
        st_, b_, _ = japi("GET", "%s?page=%s&size=%s" % (PATH, p, s), token=token)
        return st_, (b_.get("data") or {}), b_

    seen = []
    for p in (1, 2, 3):
        st_, d_, _ = page(p, 3)
        cur = [r["skuId"] for r in (d_.get("records") or [])]
        say("  page=%d size=3 -> current=%s size=%s total=%s records=%s"
            % (p, d_.get("current"), d_.get("size"), d_.get("total"), cur))
        chk("page=%d 的 current == %d" % (p, p), d_.get("current") == p, "实得 %s" % d_.get("current"))
        seen += cur
    st_, d4, _ = page(4, 3)
    say("  page=4 size=3 -> records=%s （超出范围）" % (d4.get("records") or []))
    chk("三页并集大小 == 7（不重）", len(seen) == 7, "实得 %d: %s" % (len(seen), seen))
    chk("三页并集 == 全量 skuId 集合（不漏）", sorted(seen) == sorted(r["skuId"] for r in db),
        "并集=%s / 全量=%s" % (sorted(seen), sorted(r["skuId"] for r in db)))
    chk("page=4（超出）返回空 records，但 total 仍为 7",
        (d4.get("records") or []) == [] and d4.get("total") == 7,
        "records=%s total=%s" % (d4.get("records"), d4.get("total")))

    # ---------------------------------------------------------- [7] 夹紧
    say("\n[7] ★ 夹紧四态（MP 的两个静默坑：size=0 返空列表、size<0 查全表）")
    cases = [
        ("size=0", 0, 1, "夹到 1（不夹时 MP 返回空列表）"),
        ("size=-5", -5, 1, "夹到 1（不夹时 MP 不执行分页、查全表）"),
        ("size=99999", 99999, 100, "夹到 MAX_PAGE_SIZE=100"),
        ("size=1", 1, 1, "原样"),
        ("size=7", 7, 7, "原样"),
    ]
    for label, s, expect_size, note in cases:
        st_, d_, _ = page(1, s)
        n = len(d_.get("records") or [])
        say("  %-11s -> 回传 size=%-4s records=%-2d total=%s   (%s)"
            % (label, d_.get("size"), n, d_.get("total"), note))
        chk("%s 回传的 size == %d" % (label, expect_size), d_.get("size") == expect_size,
            "实得 %s" % d_.get("size"))
        chk("%s 的 total 恒为 7（夹紧不影响总数）" % label, d_.get("total") == 7,
            "实得 %s" % d_.get("total"))

    st_, dp, _ = page(0, 10)
    say("  page=0    -> current=%s size=%s records=%d" % (dp.get("current"), dp.get("size"),
                                                         len(dp.get("records") or [])))
    chk("page=0 被夹到 current == 1", dp.get("current") == 1, "实得 %s" % dp.get("current"))

    st, b_np, _ = japi("GET", PATH, token=op_p_t)
    d_np = b_np.get("data") or {}
    say("  不传参      -> current=%s size=%s records=%d（defaultValue 生效）"
        % (d_np.get("current"), d_np.get("size"), len(d_np.get("records") or [])))
    chk("不传 page/size 时走 defaultValue：current=1 / size=10",
        d_np.get("current") == 1 and d_np.get("size") == 10,
        "current=%s size=%s" % (d_np.get("current"), d_np.get("size")))

    # ---------------------------------------------------------- [8] 非数字参数
    say("\n[8] 边界：非数字 / 负数 page 的原始报错")
    st, raw = api("GET", "%s?page=abc&size=10" % PATH, token=op_p_t)
    say("  ?page=abc -> http=%s code=%s %s" % (st, body_code(raw), short(raw, 110)))
    chk("?page=abc -> HTTP 200 + code 400（参数类型不匹配）",
        st == 200 and body_code(raw) == 400, "http=%s code=%s" % (st, body_code(raw)))

    # ---------------------------------------------------------- [9] 只读性
    say("\n[9] 只读性：跑完 DB 必须一个字节都没动")
    now_counts = counters()
    now_inv = all_inv()
    for k in sorted(base_counts):
        same = now_counts[k] == base_counts[k]
        say("  %-16s = %-5d %s" % (k, now_counts[k], "unchanged" if same else
                                   "★ CHANGED from %d" % base_counts[k]))
        chk("%s 未被本次读操作改动" % k, same, "%d -> %d" % (base_counts[k], now_counts[k]))
    inv_same = now_inv == base_inv
    say("  inventories     : %s" % ("逐字节相同" if inv_same else "★ 与基线不同"))
    if not inv_same:
        say("    now     : %s" % now_inv)
        say("    baseline: %s" % base_inv)
    chk("7 个 SKU 库存逐字节不变", inv_same)

    # ---------------------------------------------------------- verdict
    say("\n" + "=" * 78)
    say("ASSERTIONS（满额 %d 条）" % len(checks))
    say("=" * 78)
    passed = 0
    for name, good, detail in checks:
        say("  [%s] %s%s" % ("PASS" if good else "FAIL", name,
                            ("   <- " + detail) if (detail and not good) else ""))
        passed += 1 if good else 0
    say("\nRESULT: %d/%d passed" % (passed, len(checks)))
    say("VERDICT: %s" % ("INVENTORY-LIST OK -- 权限矩阵有区分度、9 字段与 DB 一致、"
                         "分页不重不漏、夹紧四态正确"
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
