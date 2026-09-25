# -*- coding: utf-8 -*-
"""
Day 20 补漏验收：L1（C 端列表分页夹紧）+ L2（C 端详情不判上架）

对应 docs/backlog.md 的 L1 / L2 两条。设计原则沿用项目模板：
  1. 不信接口自报 —— 每条业务断言都配一次 psql 对账。
  2. 业务失败 = HTTP 200 + body.code（协议层失败才是真 HTTP 码）。
  3. 满额断言写死常量（EXPECTED），防止断言被静默跳过。
  4. 可重复执行 + 高水位线清理（临时数据按 name 前缀清理，跑完 products 回基线）。

★ L1 的判据为什么是 size=0 和「造 150 条」两条：
  库里的 5 条商品太少 —— size=-1 夹紧前后都是 5 条，**用现有数据区分不出来**。
  所以①用 size=0（夹紧后 Math.max(0,1)=1 → 1 条；未夹紧 → 0 条，干净区分）；
  ②临时插到 155 条，让「上限」真正暴露：
      · size=-1  → 夹紧公式把负数夹到【下限 1】→ 1 条
                   （★ 未夹紧时 MP 的语义是 size<0 = 不限量 → 会返回全部 155 条，这才是要堵的洞）
      · size=1000 → 夹到【上限 100】→ 100 条
    两个方向分别钉住下限与上限。

★ L2 的判据核心是**反向对照**：下架后 C 端 404、管理端 200，两者必须不同。
  两端都 200 = 没拆开（还是同一个方法）；两端都 404 = 把管理端砸了。

运行：python day20-l1l2-verify.py
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "http://127.0.0.1:8080"
import os
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]

EXPECTED = 33                     # 满额断言条数（写死）
TEMP_N = 150                      # 临时商品条数（高水位线用 name 前缀隔离）
TEMP_PREFIX = "L1-TEMP-"
MAX_PAGE_SIZE = 100               # 与 ProductServiceImpl.MAX_PAGE_SIZE 同一个值

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


def api(method, path, token=None, body=None):
    """返回 (http_status, parsed_json_or_None, raw_text)"""
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(APP + path, method=method, data=data, headers=headers)
    try:
        with _opener.open(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
            st = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        st = e.code
    try:
        return st, json.loads(raw), raw
    except Exception:                                             # noqa: BLE001
        return st, None, raw


def qs(params):
    return "&".join("%s=%s" % (k, urllib.parse.quote(str(v), safe=""))
                    for k, v in params.items() if v is not None)


def page(path, **params):
    q = qs(params)
    return api("GET", path + ("?" + q if q else ""))


def recs(j):
    return (j["data"]["records"] if (j and j.get("data")) else [])


def total(j):
    return (j["data"]["total"] if (j and j.get("data")) else -1)


def login(path, username, password):
    st, j, raw = api("POST", path, body={"username": username, "password": password})
    if not j or j.get("code") != 200:
        return None, "HTTP %s / %s" % (st, raw[:150])
    return j["data"]["token"], "OK"


def wait_ready():
    for _ in range(60):
        try:
            st, j, _raw = page("/api/products", size=1)
            if st == 200 and j and j.get("code") == 200:
                return True
        except Exception:                                         # noqa: BLE001
            pass
        time.sleep(2)
    return False


def cleanup_temp():
    sql("DELETE FROM products WHERE name LIKE '%s%%'" % TEMP_PREFIX)


# ================================================================ 开场
say("=" * 74)
say("Day 20 补漏验收：L1 分页夹紧 + L2 详情判上架")
say("=" * 74)
say()
say("[等待应用就绪] 127.0.0.1:8080 ...")
if not wait_ready():
    say("  [FATAL] 应用 60 秒内未就绪，终止。")
    sys.exit(2)
say("  应用已就绪。")

DEMO_TOKEN, demo_msg = login("/api/auth/login", "demo", "demo123")
ADMIN_TOKEN, admin_msg = login("/api/auth/admin/login", "admin", "admin123")
say("      demo(C端)   : %s" % demo_msg)
say("      admin(超管) : %s" % admin_msg)
if not ADMIN_TOKEN:
    say("  [FATAL] admin 登录失败，无法验证管理端对照，终止。")
    sys.exit(2)

# 先清一次残留（可重复执行的前提）
cleanup_temp()

BASE_PRODUCTS = int(sql1("SELECT count(*) FROM products"))
BASE_SKUS = int(sql1("SELECT count(*) FROM product_skus"))
BASE_ALIVE = int(sql1("SELECT count(*) FROM products WHERE is_deleted=0 AND status=1"))
say("  库基线：products=%d  product_skus=%d  C端存活(status=1,is_deleted=0)=%d"
    % (BASE_PRODUCTS, BASE_SKUS, BASE_ALIVE))

# ================================================================ A 基线
say()
say("-" * 74)
say("A 基线：默认参数下的列表（改动不得影响正常路径）")
say("-" * 74)

st, j, raw = page("/api/products")
check("A1 GET /api/products → HTTP 200", st == 200, "实际 HTTP %s" % st)
check("A2 body.code == 200", bool(j) and j.get("code") == 200,
      "实际 %s" % (j.get("code") if j else raw[:120]))
check("A3 total == DB 存活商品数 (%d)" % BASE_ALIVE, total(j) == BASE_ALIVE,
      "接口 total=%s" % total(j))
check("A4 默认 size=10 时 records 条数 == total（5 条装得下）",
      len(recs(j)) == total(j) and len(recs(j)) == BASE_ALIVE,
      "records=%d total=%d" % (len(recs(j)), total(j)))

# ================================================================ B L1 夹紧
say()
say("-" * 74)
say("B L1 ★ 分页夹紧（size=0 的区分度 / size=-1 的上限语义）")
say("-" * 74)

st, j, raw = page("/api/products", current=1, size=0)
n0 = len(recs(j))
check("B1 ★ size=0 → records 恰好 %d 条（未夹紧会是 0 条；夹紧后 Math.max(0,1)=1）"
      % 1, n0 == 1, "实际 %d 条" % n0)
check("B2 size=0 时 total 仍 == DB 存活数（夹紧没改过滤口径）", total(j) == BASE_ALIVE,
      "接口 total=%s 期望 %d" % (total(j), BASE_ALIVE))

st, j, raw = page("/api/products", current=0, size=10)
check("B3 current=0 → HTTP 200 + code 200（page<1 被夹到 1，不报错）",
      st == 200 and bool(j) and j.get("code") == 200,
      "HTTP %s code %s" % (st, j.get("code") if j else raw[:120]))
check("B4 current=0 → records 非空（确实取的是第 1 页，不是空页）",
      len(recs(j)) == BASE_ALIVE, "实际 %d 条" % len(recs(j)))

# ---- 临时造数据，让「上限」语义真正暴露 ----
cat_id = int(sql1("SELECT MIN(id) FROM categories"))
say("  临时插入 %d 条商品（category_id=%d, name 前缀 %s）..." % (TEMP_N, cat_id, TEMP_PREFIX))
sql("INSERT INTO products (category_id, name, status) "
    "SELECT %d, '%s' || g, 1 FROM generate_series(1, %d) g" % (cat_id, TEMP_PREFIX, TEMP_N))

now_products = int(sql1("SELECT count(*) FROM products"))
now_alive = int(sql1("SELECT count(*) FROM products WHERE is_deleted=0 AND status=1"))
check("B5 造数生效：products == 基线 %d + %d" % (BASE_PRODUCTS, TEMP_N),
      now_products == BASE_PRODUCTS + TEMP_N,
      "实际 %d" % now_products)

st, j, raw = page("/api/products", current=1, size=-1)
nb = len(recs(j))
check("B6 ★ size=-1 → records 恰好 1 条（夹紧公式 min(max(size,1),100) 把负数夹到【下限 1】；"
      "★★ 未夹紧时 MP 的语义是「size<0 = 不限量」→ 会返回全部 %d 条）" % now_alive,
      nb == 1, "实际 %d 条（存活 %d）" % (nb, now_alive))
check("B7 size=-1 时 total == %d（total 不受夹紧影响，仍如实报总数）" % now_alive,
      total(j) == now_alive, "接口 total=%s 期望 %d" % (total(j), now_alive))

st, j, raw = page("/api/products", current=1, size=1000)
check("B8 size=1000 → records 恰好 %d 条（上限两侧都夹得住）" % MAX_PAGE_SIZE,
      len(recs(j)) == MAX_PAGE_SIZE, "实际 %d 条" % len(recs(j)))

db_top = [int(r) for r in sql("SELECT id FROM products WHERE is_deleted=0 AND status=1 "
                              "ORDER BY id DESC LIMIT %d" % MAX_PAGE_SIZE)]
check("B9 size=1000 的 id 列表 == DB 中 id 最大的 %d 个（ORDER BY id DESC 未被破坏）"
      % MAX_PAGE_SIZE, [r["id"] for r in recs(j)] == db_top,
      "接口前 3 个 %s / DB 前 3 个 %s"
      % ([r["id"] for r in recs(j)][:3], db_top[:3]))

# ================================================================ C 口径未被动
say()
say("-" * 74)
say("C L1 ★ 只加夹紧、没动过滤口径（Day 19 链路 B 的对照组前提仍在）")
say("-" * 74)

st, j, raw = page("/api/products", keyword="iphone")
check("C1 keyword=iphone → total == 0（like 仍大小写敏感）", total(j) == 0,
      "实际 total=%s" % total(j))
st, j, raw = page("/api/products", keyword="iPhone")
check("C2 keyword=iPhone → total == 1（对照组的存在理由，未被顺手改掉）", total(j) == 1,
      "实际 total=%s" % total(j))

# ================================================================ D 清理
say()
say("-" * 74)
say("D 高水位线清理（临时数据按 name 前缀删除）")
say("-" * 74)

cleanup_temp()
back_products = int(sql1("SELECT count(*) FROM products"))
leftover = int(sql1("SELECT count(*) FROM products WHERE name LIKE '%s%%'" % TEMP_PREFIX))
check("D1 清理后 products == 基线 %d" % BASE_PRODUCTS, back_products == BASE_PRODUCTS,
      "实际 %d" % back_products)
check("D2 残留临时商品 == 0 条", leftover == 0, "实际 %d" % leftover)

# ================================================================ E L2 详情
say()
say("-" * 74)
say("E L2 ★ C 端详情判上架（下架 vs 上架 / C 端 vs 管理端 反向对照）")
say("-" * 74)

pid = int(sql1("SELECT MIN(id) FROM products WHERE is_deleted=0 AND status=1"))
say("  靶子商品 id=%d" % pid)
db_status = int(sql1("SELECT status FROM products WHERE id=%d" % pid))
check("E1 靶子商品 DB status == 1（前提成立）", db_status == 1, "实际 %s" % db_status)

C_PATH = "/api/products/%d" % pid
A_PATH = "/api/admin/products/%d" % pid

st, cj, craw = api("GET", C_PATH)
check("E2 上架时 C 端 GET /api/products/%d → code 200" % pid,
      st == 200 and bool(cj) and cj.get("code") == 200,
      "HTTP %s code %s" % (st, cj.get("code") if cj else craw[:120]))

st, aj, araw = api("GET", A_PATH, token=ADMIN_TOKEN)
check("E3 上架时管理端 GET /api/admin/products/%d → code 200" % pid,
      st == 200 and bool(aj) and aj.get("code") == 200,
      "HTTP %s code %s" % (st, aj.get("code") if aj else araw[:120]))

db_sku_n = int(sql1("SELECT count(*) FROM product_skus WHERE product_id=%d AND is_deleted=0" % pid))
db_img_n = int(sql1("SELECT count(*) FROM product_images WHERE product_id=%d" % pid))
d = (aj.get("data") or {}) if aj else {}
check("E4 管理端详情字段与 DB 一致（skus=%d / images=%d / name 对齐）" % (db_sku_n, db_img_n),
      len(d.get("skus") or []) == db_sku_n and len(d.get("images") or []) == db_img_n
      and (d.get("name") or "") == sql1("SELECT name FROM products WHERE id=%d" % pid),
      "接口 skus=%s images=%s" % (len(d.get("skus") or []), len(d.get("images") or [])))

# ---- 下架 ----
st, j, raw = api("PUT", A_PATH, token=ADMIN_TOKEN, body={"status": 0})
check("E5 下架：PUT /api/admin/products/%d {\"status\":0} → code 200" % pid,
      st == 200 and bool(j) and j.get("code") == 200,
      "HTTP %s code %s raw %s" % (st, j.get("code") if j else "?", raw[:120]))

now_status = int(sql1("SELECT status FROM products WHERE id=%d" % pid))
check("E6 DB 核对：status == 0（下架真的落库了）", now_status == 0, "实际 %s" % now_status)

st, cj2, craw2 = api("GET", C_PATH)
check("E7 ★ 下架后 C 端详情 → code 404（伪装 404，不是 403）",
      bool(cj2) and cj2.get("code") == 404,
      "实际 code=%s HTTP=%s" % (cj2.get("code") if cj2 else "?", st))

st, aj2, araw2 = api("GET", A_PATH, token=ADMIN_TOKEN)
d2 = (aj2.get("data") or {}) if aj2 else {}
check("E8 ★ 下架后管理端详情 → code 200 且 skus/images 仍完整（管理员还得能改价/重上架）",
      bool(aj2) and aj2.get("code") == 200 and len(d2.get("skus") or []) == db_sku_n
      and len(d2.get("images") or []) == db_img_n,
      "code=%s skus=%s images=%s"
      % (aj2.get("code") if aj2 else "?", len(d2.get("skus") or []), len(d2.get("images") or [])))

check("E9 ★★ 同一 id、同一时刻：两端结果必须【不同】（都 200=没拆开；都 404=砸了管理端）",
      (cj2.get("code") if cj2 else None) != (aj2.get("code") if aj2 else None),
      "C端=%s 管理端=%s" % (cj2.get("code") if cj2 else "?", aj2.get("code") if aj2 else "?"))

# ---- 伪装 404 的一致性：下架商品 vs 不存在的 id ----
st, nj, nraw = api("GET", "/api/products/99999999")
same = (cj2 == nj)
check("E10 ★ 伪装 404 一致性：下架商品与「不存在的 id」的响应逐字段相同",
      same, "下架=%s / 不存在=%s" % (craw2[:140], nraw[:140]))

# ---- 恢复 ----
st, j, raw = api("PUT", A_PATH, token=ADMIN_TOKEN, body={"status": 1})
check("E11 恢复：PUT {\"status\":1} → code 200",
      st == 200 and bool(j) and j.get("code") == 200,
      "HTTP %s code %s" % (st, j.get("code") if j else raw[:120]))

back_status = int(sql1("SELECT status FROM products WHERE id=%d" % pid))
check("E12 DB 核对：status 回到 1", back_status == 1, "实际 %s" % back_status)

st, cj3, craw3 = api("GET", C_PATH)
check("E13 恢复后 C 端详情 → code 200（商品重新可见）",
      bool(cj3) and cj3.get("code") == 200,
      "实际 code=%s" % (cj3.get("code") if cj3 else "?"))

# ================================================================ F 零写入收尾
say()
say("-" * 74)
say("F 零写入收尾（跑完一切回基线）")
say("-" * 74)

end_products = int(sql1("SELECT count(*) FROM products"))
end_skus = int(sql1("SELECT count(*) FROM product_skus"))
end_bad = int(sql1("SELECT count(*) FROM products WHERE is_deleted<>0 OR status<>1"))

check("F1 products == 基线 %d" % BASE_PRODUCTS, end_products == BASE_PRODUCTS,
      "实际 %d" % end_products)
check("F2 product_skus == 基线 %d" % BASE_SKUS, end_skus == BASE_SKUS, "实际 %d" % end_skus)
check("F3 无残留脏状态（is_deleted<>0 或 status<>1 的行 == 0）", end_bad == 0, "实际 %d" % end_bad)

# ================================================================ 汇总
say()
say("=" * 74)
say("TOTAL: PASS=%d  FAIL=%d   （期望断言数 %d）" % (PASS, FAIL, EXPECTED))
if PASS + FAIL != EXPECTED:
    say("[FAIL] 断言总数与 EXPECTED 不符 —— 有断言被静默跳过！")
    FAILS.append("ASSERTION COUNT MISMATCH")
say("VERDICT: %s" % ("OK 全绿" if FAIL == 0 else ("FAILED -> " + "; ".join(FAILS))))
say("=" * 74)

with open("day20-l1l2-verify-report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")

sys.exit(0 if FAIL == 0 else 1)
