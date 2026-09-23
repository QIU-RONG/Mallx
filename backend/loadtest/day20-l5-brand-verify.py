# -*- coding: utf-8 -*-
"""L5①（Day 20 补漏）品牌字典接口验收：GET /api/brands（公开）+ GET /api/admin/brands（brand:list）。

设计原则沿用项目模板：
  1. 不信接口自报 —— 每条业务断言都配一次 psql 对账。
  2. 业务失败 = HTTP 200 + body.code；协议层失败（401/403/404）是真 HTTP 码。
  3. 满额断言写死常量（EXPECTED），防止断言被静默跳过。
  4. 可重复执行 + 高水位线清理（临时品牌按 id > 基线 max 清理，跑完回基线）。

★ 本脚本的核心是【反向对照】，不是「接口能返回数据」：
  · C 端 / 管理端必须给出【不同】答案 —— 差异恰好是那 1 个停用品牌。
    脚本临时插一条 status = 0 的品牌来制造这个差异。库里 7 条品牌全是 status = 1，
    不造数据的话「C 端只看 status=1」这条断言【恒真】，等于什么都没验
    （同 L1 的教训：样本量不够时，夹紧前后的结果一样，用现有数据区分不出来）。
  · 这正是 L2 拆 getDetail / getAdminDetail 的同构证据：
    「停用的东西 C 端看不见、管理端必须看得见（管理员要重新启用它）」。
  · 权限矩阵同理：op_order（ORDER_ADMIN，无 brand:list）必须真 403 ——
    「谁没有」才是区分度所在，只验 admin 200 什么都证明不了。

★ 白名单粒度也用三态钉住（Day 20 的实测坑）：
    匿名 GET  /api/brands      → 200   （精确路径放行）
    匿名 GET  /api/brands/999  → 401   （★ 若白名单写成 /api/brands/** 这里会是 404 甚至 200）
    匿名 POST /api/brands      → 401   （白名单是「路径 + 方法」，GET 才放行）

运行：python day20-l5-brand-verify.py
"""
import atexit
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

TMP_BRAND_NAME = "L5-TEMP-DISABLED"     # 临时停用品牌（brands.name 有 UNIQUE，必须固定名字）
EXPECTED = 24                            # 满额断言条数（写死）

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


# ---------------------------------------------------------------- DB
def sql(statement):
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("psql rc=%s: %s" % (r.returncode, (r.stderr or "").strip()[:300]))
    return [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]


def sql1(statement):
    rows = sql(statement)
    if not rows:
        # ★ 空串而不是 0 行 —— 老坑：Docker 引擎自停时 psql 返回空串，
        #   脚本会崩在 int('')，看着像脚本 bug。这里显式翻译成人话。
        raise RuntimeError("psql 返回空输出 —— 多半是 Docker 引擎没起（不是脚本问题）")
    return rows[0]


# ---------------------------------------------------------------- HTTP
def api_raw(opener, method, path, token=None, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(APP + path, method=method, data=data, headers=headers)
    try:
        with opener.open(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
            st = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        st = e.code
    except Exception as e:                                        # noqa: BLE001
        return -1, None, "%s: %s" % (type(e).__name__, e)
    try:
        return st, json.loads(raw), raw
    except Exception:                                             # noqa: BLE001
        return st, None, raw


def api(method, path, token=None, body=None):
    return api_raw(_opener, method, path, token=token, body=body)


def code_of(j):
    return j.get("code") if isinstance(j, dict) else None


def data_of(j):
    return (j.get("data") if isinstance(j, dict) else None)


def ids_of_list(j):
    d = data_of(j)
    return [r.get("id") for r in d] if isinstance(d, list) else None


def login(path, username, password):
    st, j, raw = api("POST", path, body={"username": username, "password": password})
    if code_of(j) != 200:
        return None, "HTTP %s / %s" % (st, raw[:120])
    return (data_of(j) or {}).get("token"), "OK"


def wait_ready(deadline=150):
    t0 = time.time()
    while time.time() - t0 < deadline:
        st, _j, _r = api("GET", "/api/hello")
        if st != -1:
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------- 临时品牌
def drop_tmp_brand():
    """★ 按主键删。临时品牌不挂商品（products.brand_id 没有指向它），
       所以不会撞 fk_product_brand；真撞了说明造数写错了，让它炸出来。"""
    sql("DELETE FROM brands WHERE name = '%s'" % TMP_BRAND_NAME)


def cleanup():
    drop_tmp_brand()


def _safe_cleanup():
    """★ 无论脚本怎么退出（含断言崩溃、psql 异常）都尝试清一次 ——
       否则残留的临时品牌会污染下一次跑（brands 行数基线会漂）。"""
    try:
        cleanup()
    except Exception:                                             # noqa: BLE001
        pass


atexit.register(_safe_cleanup)


# ================================================================ 开场
say("=" * 74)
say("L5① 验收：品牌字典（GET /api/brands + GET /api/admin/brands）")
say("=" * 74)

say()
say("[等待应用就绪] 127.0.0.1:8080 ...")
if not wait_ready():
    say("  [FATAL] 应用 150 秒内未就绪，终止。")
    sys.exit(2)
say("  应用已就绪。")

# 防御性清理：上一轮若残留同名品牌，INSERT 会撞 UNIQUE(name)
drop_tmp_brand()

BASE_ALL = int(sql1("SELECT count(*) FROM brands"))
BASE_ENABLED = int(sql1("SELECT count(*) FROM brands WHERE status = 1"))
BASE_MAX_ID = int(sql1("SELECT COALESCE(max(id), 0) FROM brands"))
say("  库基线：brands 全部=%d  status=1 的=%d  max(id)=%d"
    % (BASE_ALL, BASE_ENABLED, BASE_MAX_ID))

# 造一条【停用】品牌 —— 差异点全靠它，没有它本脚本大部分断言恒真
sql("INSERT INTO brands (name, logo, description, status) "
    "VALUES ('%s', 'https://oss.mallx.local/brand/tmp.png', 'L5 反向对照用，脚本跑完自动删除', 0)"
    % TMP_BRAND_NAME)
TMP_ID = int(sql1("SELECT id FROM brands WHERE name = '%s'" % TMP_BRAND_NAME))
say("  ★ 已插入临时【停用】品牌 id=%d（它只应出现在管理端，不应出现在 C 端）" % TMP_ID)

# 登录三个账号
say()
say("[登录] admin(SUPER_ADMIN) / op_product(PRODUCT_ADMIN) / op_order(ORDER_ADMIN)")
t_admin, m1 = login("/api/auth/admin/login", "admin", "admin123")
t_prod, m2 = login("/api/auth/admin/login", "op_product", "prod123456")
t_order, m3 = login("/api/auth/admin/login", "op_order", "op123456")
say("  admin:%s  op_product:%s  op_order:%s" % (m1, m2, m3))
if not (t_admin and t_prod and t_order):
    say("  [FATAL] 夹具账号登录失败 —— 请先跑 day17-fixture-apply.py（06-day17-fixtures.sql）")
    say("          op_product 尤其重要：它验的是「brand:list 有没有补发给商品管理员」")
    sys.exit(2)

# ---------------------------------------------------------------- A C 端公开字典
say()
say("-" * 74)
say("A C 端 /api/brands（匿名，白名单精确路径）")
say("-" * 74)

st, jc, raw = api("GET", "/api/brands")
check("A1 匿名 GET /api/brands → HTTP 200", st == 200, "实际 %s" % st)
check("A2 body.code == 200", code_of(jc) == 200,
      "实际 %s" % (code_of(jc) if jc else raw[:120]))
check("A3 data 是【数组】（Result<List<BrandVO>>，不是分页对象）",
      isinstance(data_of(jc), list),
      "实际类型 %s" % type(data_of(jc)).__name__)

c_ids = ids_of_list(jc) or []
db_enabled_rows = sql("SELECT id, name, COALESCE(logo, ''), COALESCE(description, '') "
                      "FROM brands WHERE status = 1 ORDER BY id")
db_enabled_ids = [int(r.split("|")[0]) for r in db_enabled_rows]

check("A4 条数 == DB 中 status=1 的品牌数 (%d)" % BASE_ENABLED,
      len(c_ids) == BASE_ENABLED, "实际 %d" % len(c_ids))
check("A5 id 序列与 DB(status=1, order by id) 完全一致 %s" % db_enabled_ids,
      c_ids == db_enabled_ids, "实际 %s" % c_ids)
check("A6 ★ 停用品牌（id=%d）不在 C 端结果里" % TMP_ID,
      TMP_ID not in c_ids, "实际 %s" % c_ids)

db_txt = {int(r.split("|")[0]): r.split("|")[1:] for r in db_enabled_rows}
field_ok = True
bad = ""
for r in (data_of(jc) or []):
    exp = db_txt.get(r.get("id"))
    got = [r.get("name"), r.get("logo") or "", r.get("description") or ""]
    if exp is None or got != exp:
        field_ok = False
        bad = "id=%s 接口=%s DB=%s" % (r.get("id"), got, exp)
        break
check("A7 name/logo/description 逐条 == DB（BeanUtils 拷字段没漏）",
      bool(data_of(jc)) and field_ok, bad)

# ---------------------------------------------------------------- B 白名单粒度
say()
say("-" * 74)
say("B ★白名单粒度三态：/api/brands 放行，/api/brands/999 与 POST 都必须被挡")
say("-" * 74)

st, _j, _r = api("GET", "/api/admin/brands")
check("B1 匿名 GET /api/admin/brands → 真 HTTP 401（未被白名单放行）", st == 401,
      "实际 %s" % st)

st, _j, _r = api("POST", "/api/brands", body={"name": "x"})
check("B2 匿名 POST /api/brands → 真 HTTP 401（白名单只放行 GET，是「路径+方法」粒度）",
      st == 401, "实际 %s" % st)

st, _j, _r = api("GET", "/api/brands/999")
check("B3 ★ 匿名 GET /api/brands/999 → 真 HTTP 401 —— 若白名单写成 /api/brands/** 这里不会 401",
      st == 401, "实际 %s" % st)

st999, _j, _r = api("GET", "/api/brands/999", token=t_admin)
check("B4 带 admin token 再打 /api/brands/999 → 404（证明这条路径确实没路由，B3 的 401 出自 Security）",
      st999 == 404, "实际 %s" % st999)

# ---------------------------------------------------------------- C 权限矩阵
say()
say("-" * 74)
say("C 管理端权限矩阵（★ 区分度靠「谁没有」）")
say("-" * 74)

st, ja, raw = api("GET", "/api/admin/brands", token=t_admin)
check("C1 admin(SUPER_ADMIN) → HTTP 200 + code 200",
      st == 200 and code_of(ja) == 200,
      "HTTP %s code=%s" % (st, code_of(ja) if ja else raw[:120]))

a_ids = ids_of_list(ja) or []
db_all_rows = sql("SELECT id, name, COALESCE(logo, ''), COALESCE(description, '') "
                  "FROM brands ORDER BY id")
db_all_ids = [int(r.split("|")[0]) for r in db_all_rows]

check("C2 admin 条数 == DB 全部品牌数 (%d)（含停用）" % (BASE_ALL + 1),
      len(a_ids) == BASE_ALL + 1, "实际 %d" % len(a_ids))
check("C3 ★ admin 结果【包含】停用品牌 id=%d（管理员要能看见它才能重新启用）" % TMP_ID,
      TMP_ID in a_ids, "实际 %s" % a_ids)

st, jp, raw = api("GET", "/api/admin/brands", token=t_prod)
check("C4 op_product(PRODUCT_ADMIN，brand:list 已补发) → HTTP 200 + code 200",
      st == 200 and code_of(jp) == 200,
      "HTTP %s code=%s" % (st, code_of(jp) if jp else raw[:120]))

st, jo, raw = api("GET", "/api/admin/brands", token=t_order)
check("C5 ★ op_order(ORDER_ADMIN，无 brand:list) → 真 HTTP 403（不是 200+code）",
      st == 403, "HTTP %s body=%s" % (st, (raw or "")[:100]))
check("C6 ★ admin 与 op_product 的响应体【逐字节相同】（结果与调用者无关）",
      bool(ja) and bool(jp) and
      json.dumps(ja, sort_keys=True, ensure_ascii=False) ==
      json.dumps(jp, sort_keys=True, ensure_ascii=False))

st, _j, _r = api("GET", "/api/admin/brands/999", token=t_admin)
check("C7 /api/admin/brands/999 带 admin → 404（管理端目前只有 list 一个口子，没有漏出的端点）",
      st == 404, "实际 %s" % st)

# ---------------------------------------------------------------- D 两端口径差异
say()
say("-" * 74)
say("D ★两端口径差异 —— 与 L2 拆 getDetail/getAdminDetail 同构的证据")
say("-" * 74)

check("D1 管理端条数 - C 端条数 == 1（差值恰好是那一个停用品牌）",
      len(a_ids) - len(c_ids) == 1, "管理端 %d / C 端 %d" % (len(a_ids), len(c_ids)))
check("D2 管理端 id 集合 - C 端 id 集合 == {%d}" % TMP_ID,
      set(a_ids) - set(c_ids) == {TMP_ID}, "实际 %s" % sorted(set(a_ids) - set(c_ids)))
check("D3 C 端 id 集合 ⊂ 管理端 id 集合（C 端是管理端的子集，不是另一份数据）",
      set(c_ids).issubset(set(a_ids)))

# ---------------------------------------------------------------- E 清理与零写入
say()
say("-" * 74)
say("E 清理（临时品牌删掉，库回基线）")
say("-" * 74)

cleanup()
now_all = int(sql1("SELECT count(*) FROM brands"))
now_max = int(sql1("SELECT COALESCE(max(id), 0) FROM brands"))
st, jc2, _r = api("GET", "/api/brands")
c_ids2 = ids_of_list(jc2) or []

check("E1 清理后 brands 行数 == 基线 %d" % BASE_ALL, now_all == BASE_ALL, "实际 %d" % now_all)
check("E2 ★ 高水位线：不存在 id > 基线 max(id)=%d 的品牌" % BASE_MAX_ID,
      now_max == BASE_MAX_ID, "实际 max(id)=%d" % now_max)
check("E3 清理后 C 端条数 == 基线 %d（接口回到原状）" % BASE_ENABLED,
      len(c_ids2) == BASE_ENABLED, "实际 %d" % len(c_ids2))

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
                      "day20-l5-brand-verify-report.txt")
with open(report, "w", encoding="utf-8") as fp:
    fp.write("\n".join(LINES) + "\n")
print("\n报告已写入：%s" % report)

sys.exit(0 if FAIL == 0 else 1)
