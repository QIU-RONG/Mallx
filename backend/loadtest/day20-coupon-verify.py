# -*- coding: utf-8 -*-
"""
Day 20 优惠券（阶段一）验收：A–K 共 11 条链路。

对应 docs/daily/Day-20-优惠券.md §七 的验收清单。设计原则沿用项目模板：
  1. 不信接口自报 —— 每条业务断言都配一次 psql 对账。
  2. 业务失败 = HTTP 200 + body.code（协议层失败才是真 HTTP 码）。
  3. 满额断言写死常量（EXPECTED / GRANT_LIMIT），防止断言被静默跳过。
  4. 可重复执行 + 高水位线清理（临时数据按 name / username 前缀清理，跑完回基线）。

★ 骨架期护栏（与 day20-skeleton-smoke.py 互为镜像）：
  那个脚本要求「源码里还有 UnsupportedOperationException」才肯跑（否则会真写库）；
  本脚本相反 —— 扫到还有 throw / XML TODO 就【拒绝执行】并提示先填实现。
  理由：拿一个半成品跑验收，只会产出一份满是 FAIL 的噪音报告，
  且失败原因分不清是「实现没写」还是「实现写错了」。

★★ 链路 E 为什么要自造用户：
  库里 C 端用户只有 demo(1) / intruder(2) 两个，而「限量不超发」的判据是
  「N 个人抢 M 张（N > M），成功的恰好 M 个」。两个人抢一个名额也会超发，
  但样本太小、串行执行时「先查后改」也可能碰巧不超发 ⇒ 区分度不足。
  所以脚本临时造 4 个用户（`d20tmp1..4`，密码复用 {noop} 明文前缀）去抢 2 张券。
  ★ 造用户能这么便宜，是因为本项目用 DelegatingPasswordEncoder：
    密码列写 '{noop}d20pw123' 即可登录，不必算 BCrypt。

★ 排期注意：E 段只用临时用户、G 段的 IDOR 用 demo 与 intruder ——
  这样 intruder 的领取记录恒为空，「换个 token 看不到别人的券」才是个干净的判据。

运行：python day20-coupon-verify.py
"""

import atexit
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]
SRC_DIR = r"D:\MallX\backend\mallx\mall-marketing\src\main\java"
XML_DIR = r"D:\MallX\backend\mallx\mall-marketing\src\main\resources\mapper"

CP_PREFIX = "D20-TMP-"             # 临时券名前缀
US_PREFIX = "d20tmp"               # 临时用户名前缀
TMP_PW = "d20pw123"
MAX_PAGE_SIZE = 100                # 与 CouponServiceImpl.MAX_PAGE_SIZE 同一个值
BULK_N = 105                       # 夹紧断言的样本量（必须 > 100 才有区分度）
GRANT_LIMIT = 2                    # E 段：限量 2 张，4 个人抢 —— 写死常量
GRANT_USERS = 4

EXPECTED = 80                      # 满额断言条数（★ 首次跑后按报告 TOTAL 行校准）

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
        # ★ 空串而不是 0 行 —— 本项目的老坑：Docker 引擎自停时 psql 返回空串，
        #   脚本会崩在 int('')，看着像脚本 bug。这里显式翻译成人话。
        raise RuntimeError("psql 返回空输出 —— 多半是 Docker 引擎没起（不是脚本问题）。SQL: %s"
                           % statement)
    return rows[0]


def count(table, where="TRUE"):
    return int(sql1("SELECT count(*) FROM %s WHERE %s" % (table, where)))


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


def records_of(j):
    d = data_of(j)
    return (d.get("records") if isinstance(d, dict) else None) or []


def total_of(j):
    d = data_of(j)
    return (d.get("total") if isinstance(d, dict) else -1)


def qs(params):
    return "&".join("%s=%s" % (k, urllib.parse.quote(str(v), safe=""))
                    for k, v in params.items() if v is not None)


def login(path, username, password):
    st, j, raw = api("POST", path, body={"username": username, "password": password})
    if code_of(j) != 200:
        return None, "HTTP %s / %s" % (st, raw[:120])
    return (data_of(j) or {}).get("token"), "OK"


def wait_ready(deadline=150):
    t0 = time.time()
    while time.time() - t0 < deadline:
        st, j, _ = api("GET", "/api/hello")
        if st != -1:
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------- 时间与造券
def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


NOW = datetime.now()
T_PAST_START = iso(NOW - timedelta(days=365))
T_PAST_END = iso(NOW - timedelta(days=1))
T_FUT_START = iso(NOW + timedelta(days=1))
T_FUT_END = iso(NOW + timedelta(days=365))
T_OK_START = iso(NOW - timedelta(days=1))
T_OK_END = iso(NOW + timedelta(days=30))


def coupon_body(name, type_="FIXED", amount=10.0, rate=None, min_amount=0.0,
                total=100, start=None, end=None):
    """造一张券的请求体。★ discountAmount / discountRate 按类型只给一个，另一个不出现。"""
    b = {"name": name, "type": type_, "totalCount": total,
         "startTime": start or T_OK_START, "endTime": end or T_OK_END}
    if amount is not None:
        b["discountAmount"] = amount
    if rate is not None:
        b["discountRate"] = rate
    if min_amount is not None:
        b["minAmount"] = min_amount
    return b


def create_coupon(**kw):
    """经管理端接口建券，返回 (新 id, 原始响应文本, body.code)。"""
    st, j, raw = api("POST", "/api/admin/coupons", token=ADMIN_TOKEN, body=coupon_body(**kw))
    return (data_of(j) if code_of(j) == 200 else None), raw, code_of(j)


def mk_users(n, prefix=US_PREFIX):
    """临时 C 端用户。★ 返回 [(username, token, id)]，密码列写 {noop} 明文前缀。"""
    out = []
    for i in range(1, n + 1):
        uname = "%s%d" % (prefix, i)
        sql("INSERT INTO users (username, password, nickname, status) "
            "VALUES ('%s', '{noop}%s', 'Day20 temp %d', 1)" % (uname, TMP_PW, i))
        uid = int(sql1("SELECT id FROM users WHERE username = '%s'" % uname))
        tk, msg = login("/api/auth/login", uname, TMP_PW)
        out.append((uname, tk, uid, msg))
    return out


def parallel_receive(coupon_id, tokens):
    """★ Barrier 齐射：所有线程就位后才同时发请求，否则测得是串行。"""
    n = len(tokens)
    res = [None] * n
    bar = threading.Barrier(n)

    def worker(i):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            bar.wait(timeout=25)
        except Exception:                                         # noqa: BLE001
            pass
        st, j, _raw = api_raw(opener, "POST", "/api/coupons/%d/receive" % coupon_id,
                              token=tokens[i])
        res[i] = (st, code_of(j))

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=40)
    return res


def cleanup():
    """★ 清理必须按 FK 引用顺序：先子表（user_coupons），再 coupons / users。
       直接删 coupons 会撞 fk_user_coupon_coupon（FK 全是 NO ACTION）。"""
    sql("DELETE FROM user_coupons "
        " WHERE coupon_id IN (SELECT id FROM coupons WHERE name LIKE '%s%%') "
        "    OR user_id    IN (SELECT id FROM users   WHERE username LIKE '%s%%')"
        % (CP_PREFIX, US_PREFIX))
    sql("DELETE FROM coupons WHERE name LIKE '%s%%'" % CP_PREFIX)
    sql("DELETE FROM users   WHERE username LIKE '%s%%'" % US_PREFIX)


def _safe_cleanup():
    """★ 无论脚本怎么退出（含断言崩溃、psql 异常）都尝试清一次 ——
       否则残留的临时券/临时用户会污染下一次跑（尤其 users 的基线计数会漂）。"""
    try:
        cleanup()
    except Exception:                                             # noqa: BLE001
        pass


atexit.register(_safe_cleanup)


# ================================================================ 骨架期护栏
def impl_pending():
    """返回 (java_throw_count, xml_todo_count)。非零 = 实现还没填完。"""
    jn = 0
    for root, _d, files in os.walk(SRC_DIR):
        for fn in files:
            if fn.endswith(".java"):
                try:
                    with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as f:
                        jn += f.read().count("UnsupportedOperationException")
                except OSError:
                    pass
    xn = 0
    for root, _d, files in os.walk(XML_DIR):
        for fn in files:
            if fn.endswith(".xml"):
                try:
                    with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as f:
                        xn += f.read().count("TODO: ")
                except OSError:
                    pass
    return jn, xn


say("=" * 74)
say("Day 20 优惠券（阶段一）验收：A 白名单 / B 接通 / C 发券 / D 领券 / E 限量")
say("                        F 时间窗 / G 我的券(IDOR) / H 权限矩阵 / I 健壮性 / J 清理")
say("=" * 74)

_jt, _xt = impl_pending()
if _jt or _xt:
    say()
    say("⛔ 已拒绝执行：mall-marketing 实现尚未填完。")
    say("   Java 里还有 %d 处 UnsupportedOperationException，XML 里还有 %d 处 TODO。" % (_jt, _xt))
    say("   ⇒ 半成品跑验收只会产出一份无法定性的噪音报告（分不清『没写』还是『写错』）。")
    say("   先填完 15 处 TODO，再回来跑本脚本。")
    say("=" * 74)
    raise SystemExit(0)

say("实现已填完（无骨架占位）—— 继续。")
say()
say("[等待应用就绪] 127.0.0.1:8080 ...")
if not wait_ready():
    say("  [FATAL] 应用 150 秒内未就绪，终止（先去看应用日志）。")
    raise SystemExit(2)
say("  应用已就绪。")

# 清残留 → 记基线（可重复执行的前提）
try:
    cleanup()
except RuntimeError as e:
    say("  [FATAL] 清理残留失败：%s" % e)
    raise SystemExit(2)

BASE_CP = count("coupons")
BASE_UC = count("user_coupons")
BASE_US = count("users")

# ---------------------------------------------------------------- 登录
say()
say("[-] 登录五身份")
DEMO_TOKEN, m1 = login("/api/auth/login", "demo", "demo123")
INTRUDER_TOKEN, m2 = login("/api/auth/login", "intruder", "intruder")
ADMIN_TOKEN, m3 = login("/api/auth/admin/login", "admin", "admin123")
ORDER_TOKEN, m4 = login("/api/auth/admin/login", "op_order", "op123456")
PRODUCT_TOKEN, m5 = login("/api/auth/admin/login", "op_product", "prod123456")
for label, tk, msg in [("demo(C端)", DEMO_TOKEN, m1), ("intruder(C端)", INTRUDER_TOKEN, m2),
                       ("admin(超管)", ADMIN_TOKEN, m3), ("op_order", ORDER_TOKEN, m4),
                       ("op_product", PRODUCT_TOKEN, m5)]:
    say("      %-14s : %s" % (label, msg))
say("  库基线：coupons=%d  user_coupons=%d  users=%d" % (BASE_CP, BASE_UC, BASE_US))
if not ADMIN_TOKEN:
    say("  [FATAL] admin 登录失败，终止。")
    raise SystemExit(2)

# ================================================================ A 白名单
say()
say("-" * 74)
say("A 路由与白名单粒度（★ 精确路径 /api/coupons 而非 /api/coupons/**）")
say("-" * 74)

st, j, raw = api("GET", "/api/coupons")
check("A1 匿名 GET /api/coupons → HTTP 200（精确白名单放行）", st == 200,
      "实际 HTTP %s" % st)

st, j, raw = api("GET", "/api/coupons/my")
check("A2 ★★ 匿名 GET /api/coupons/my → HTTP 401（没被通配白名单误伤；"
      "写成 /** 时这里会是 200 = 任何人能看任何人的券）", st == 401,
      "实际 HTTP %s" % st)

st, j, raw = api("GET", "/api/admin/coupons")
check("A3 匿名 GET /api/admin/coupons → HTTP 401", st == 401, "实际 HTTP %s" % st)

st, j, raw = api("POST", "/api/coupons/1/receive")
check("A4 匿名 POST /api/coupons/1/receive → HTTP 401（领券不在白名单）", st == 401,
      "实际 HTTP %s" % st)

# ================================================================ B 已接通
say()
say("-" * 74)
say("B 实现已接通：三个端点都不再是骨架长相（HTTP 200 + code=500）")
say("-" * 74)

st, j, raw = api("GET", "/api/coupons", token=DEMO_TOKEN)
check("B1 demo GET /api/coupons → code=200（不再是 500）",
      st == 200 and code_of(j) == 200, "HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/coupons/my", token=DEMO_TOKEN)
check("B2 demo GET /api/coupons/my → code=200",
      st == 200 and code_of(j) == 200, "HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/coupons", token=ADMIN_TOKEN)
check("B3 admin GET /api/admin/coupons → code=200",
      st == 200 and code_of(j) == 200, "HTTP %s code %s" % (st, code_of(j)))

# ================================================================ C 发券
say()
say("-" * 74)
say("C 管理端发券：落库字段对账 + 关系校验 + 券名不唯一")
say("-" * 74)

cid, craw, ccode = create_coupon(name=CP_PREFIX + "FIXED", type_="FIXED", amount=20.0,
                                 min_amount=100.0, total=50)
check("C1 POST /api/admin/coupons（合法 FIXED 载荷）→ code=200", ccode == 200,
      "实际 code=%s / %s" % (ccode, craw[:160]))
check("C2 返回新券 id 且 > 0", isinstance(cid, int) and cid > 0, "实际 data=%r" % cid)

row = sql1("SELECT name || '|' || type || '|' || discount_amount || '|' || "
           "COALESCE(discount_rate::text,'-') || '|' || min_amount || '|' || "
           "total_count || '|' || received_count || '|' || status || '|' || "
           "to_char(start_time,'YYYY-MM-DD HH24:MI:SS') || '|' || "
           "to_char(end_time,'YYYY-MM-DD HH24:MI:SS') || '|' || "
           "COALESCE(created_at::text,'-') || '|' || COALESCE(updated_at::text,'-') "
           "FROM coupons WHERE id = %s" % cid) if cid else ""
parts = row.split("|") if row else []
check("C3 ★ DB 逐字段对账（name/type/discount_amount/discount_rate/min_amount/"
      "total_count/received_count/status/start_time/end_time/created_at/updated_at）",
      len(parts) == 12 and parts[0] == CP_PREFIX + "FIXED" and parts[1] == "FIXED"
      and parts[2] == "20.00" and parts[3] == "-" and parts[4] == "100.00"
      and parts[5] == "50" and parts[6] == "0" and parts[7] == "1"
      and parts[10] != "-" and parts[11] != "-",
      "实际行=%r" % row)

cid2, craw2, ccode2 = create_coupon(name=CP_PREFIX + "FIXED", type_="FIXED", amount=20.0,
                                    min_amount=100.0, total=50)
check("C4 重复建【同名】券 → code=200（券名无 UNIQUE，同名券合法）", ccode2 == 200,
      "实际 code=%s / %s" % (ccode2, craw2[:160]))
check("C5 同名两张券的 id 不同（真的是两行，不是覆盖）",
      isinstance(cid2, int) and cid2 != cid,
      "cid=%s cid2=%s" % (cid, cid2))

n_before = count("coupons")
cid3, craw3, ccode3 = create_coupon(name=CP_PREFIX + "BADTIME", type_="FIXED", amount=5.0,
                                    start=T_FUT_START, end=T_PAST_END)
check("C6 ★ endTime 早于 startTime → code=400（否则券会『永远领不到』且不报错）",
      ccode3 == 400, "实际 code=%s / %s" % (ccode3, craw3[:160]))
check("C7 DB 核对：被拒的券没落库（coupons 计数不变，%d → %d）"
      % (n_before, count("coupons")), count("coupons") == n_before,
      "实际 %d" % count("coupons"))

# ================================================================ D 领券
say()
say("-" * 74)
say("D ★★ 领券核心：占名额 → 发到手（同一事务）+ 重复领回滚")
say("-" * 74)

d_id, draw, dcode = create_coupon(name=CP_PREFIX + "MAIN", type_="FIXED", amount=30.0,
                                  total=100)
check("D0 造一张 total_count=100 的主券 → code=200", dcode == 200,
      "实际 code=%s" % dcode)

rc0 = int(sql1("SELECT received_count FROM coupons WHERE id=%s" % d_id))
uc0 = count("user_coupons")

st, j, raw = api("POST", "/api/coupons/%s/receive" % d_id, token=DEMO_TOKEN)
check("D1 demo 领取 → HTTP 200 + code=200", st == 200 and code_of(j) == 200,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

rc1 = int(sql1("SELECT received_count FROM coupons WHERE id=%s" % d_id))
check("D2 ★ DB 核对：received_count 恰好 +1（%d → %d）" % (rc0, rc1), rc1 == rc0 + 1,
      "实际 %d" % rc1)

uc1 = count("user_coupons")
check("D3 ★ DB 核对：user_coupons 恰好 +1 行（%d → %d）" % (uc0, uc1), uc1 == uc0 + 1,
      "实际 %d" % uc1)

ucrow = sql1("SELECT user_id || '|' || coupon_id || '|' || status || '|' || "
             "CASE WHEN received_at IS NULL THEN '-' ELSE 'set' END "
             "FROM user_coupons WHERE coupon_id=%s ORDER BY id DESC LIMIT 1" % d_id)
check("D4 ★ DB 核对：新行 user_id=1 / coupon_id=%s / status='UNUSED'" % d_id,
      ucrow == "1|%s|UNUSED|set" % d_id, "实际行=%r" % ucrow)

check("D5 ★ DB 核对：received_at 已写入（XML 的 INSERT 不走填充器，"
      "必须在 SQL 里手写 CURRENT_TIMESTAMP）",
      sql1("SELECT CASE WHEN received_at IS NULL THEN 'null' ELSE 'set' END "
           "FROM user_coupons WHERE coupon_id=%s ORDER BY id DESC LIMIT 1" % d_id) == "set")

st, j, raw = api("POST", "/api/coupons/%s/receive" % d_id, token=DEMO_TOKEN)
check("D6 ★ 同一人再领一次 → code=400（一人一券，靠 ON CONFLICT 影响行数判定）",
      code_of(j) == 400, "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

rc2 = int(sql1("SELECT received_count FROM coupons WHERE id=%s" % d_id))
check("D7 ★★ DB 核对：重复领【没能】再加名额（received_count 仍 %d）"
      "—— 这是『INSERT 撞唯一约束→抛异常→整个事务回滚』的直接证据" % rc1,
      rc2 == rc1, "实际 %d" % rc2)

uc2 = count("user_coupons")
check("D8 DB 核对：user_coupons 无新行（仍 %d）" % uc1, uc2 == uc1, "实际 %d" % uc2)

# ================================================================ E 限量并发
say()
say("-" * 74)
say("E ★★ 限量并发：%d 个人抢 %d 张，成功必须恰好 %d 个（不超发）"
    % (GRANT_USERS, GRANT_LIMIT, GRANT_LIMIT))
say("-" * 74)

e_id, eraw, ecode = create_coupon(name=CP_PREFIX + "LIMITED", type_="FIXED", amount=50.0,
                                  total=GRANT_LIMIT)
check("E1 造限量券：total_count=%d → code=200" % GRANT_LIMIT, ecode == 200,
      "实际 code=%s" % ecode)

users = mk_users(GRANT_USERS)
ok_login = all(tk for _u, tk, _i, _m in users)
check("E2 临时造 %d 个 C 端用户且都能登录（{noop} 明文前缀，不必算 BCrypt）" % GRANT_USERS,
      ok_login, "; ".join("%s:%s" % (u, m) for u, _t, _i, m in users))

tokens = [tk for _u, tk, _i, _m in users if tk]
results = parallel_receive(e_id, tokens)
ok_n = sum(1 for st, c in results if c == 200)
bad_n = sum(1 for st, c in results if c == 400)
check("E3 ★ 并发齐射（Barrier）：恰好 %d 个成功（写死常量，非事后数）" % GRANT_LIMIT,
      ok_n == GRANT_LIMIT, "实际 %d 成功 / 明细 %s" % (ok_n, results))
check("E4 另外 %d 个拿到 code=400（成功+失败 == 参赛人数 %d，没人漏判）"
      % (GRANT_USERS - GRANT_LIMIT, GRANT_USERS),
      bad_n == GRANT_USERS - GRANT_LIMIT, "实际 %d 个失败" % bad_n)

rc_e = int(sql1("SELECT received_count FROM coupons WHERE id=%s" % e_id))
check("E5 ★★ DB 核对：received_count 恰好 == %d（★ 超发的话会是 3 或 4）" % GRANT_LIMIT,
      rc_e == GRANT_LIMIT, "实际 %d" % rc_e)
uc_e = count("user_coupons", "coupon_id = %s" % e_id)
check("E6 DB 核对：该券的领取记录恰好 %d 行" % GRANT_LIMIT, uc_e == GRANT_LIMIT,
      "实际 %d" % uc_e)

# ================================================================ F 时间窗/状态
say()
say("-" * 74)
say("F ★ 四条守卫的另外三条（未开始 / 已下架 / 已过期 / 已抢光）")
say("-" * 74)

f1, _r, c = create_coupon(name=CP_PREFIX + "NOTSTART", total=10,
                          start=T_FUT_START, end=T_FUT_END)
check("F0a 造『未开始』券 → code=200", c == 200, "实际 code=%s" % c)
f2, _r, c = create_coupon(name=CP_PREFIX + "OFFLINE", total=10)
check("F0b 造『已下架』券 → code=200", c == 200, "实际 code=%s" % c)
if f2:
    sql("UPDATE coupons SET status = 0 WHERE id = %s" % f2)
f3, _r, c = create_coupon(name=CP_PREFIX + "EXPIRED", total=10,
                          start=T_PAST_START, end=T_PAST_END)
check("F0c 造『已过期』券 → code=200", c == 200, "实际 code=%s" % c)

names_in_list = None
st, j, raw = api("GET", "/api/coupons?%s" % qs({"page": 1, "size": MAX_PAGE_SIZE}))
names_in_list = [r.get("name") for r in records_of(j)]
check("F1 ★ 公开列表不出现『未开始』的券（列表口径 == 领取守卫）",
      (CP_PREFIX + "NOTSTART") not in names_in_list, "列表=%s" % (names_in_list or raw[:160]))
check("F2 ★ 公开列表不出现『已下架』的券", (CP_PREFIX + "OFFLINE") not in names_in_list,
      "列表=%s" % names_in_list)
check("F3 ★ 公开列表不出现『已过期』的券", (CP_PREFIX + "EXPIRED") not in names_in_list,
      "列表=%s" % names_in_list)
check("F4 ★ 公开列表不出现『已抢光』的券（received_count == total_count）",
      (CP_PREFIX + "LIMITED") not in names_in_list, "列表=%s" % names_in_list)

st, j, raw = api("POST", "/api/coupons/%s/receive" % f1, token=DEMO_TOKEN)
check("F5 领『未开始』的券 → code=400", code_of(j) == 400,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))
st, j, raw = api("POST", "/api/coupons/%s/receive" % f2, token=DEMO_TOKEN)
check("F6 领『已下架』的券 → code=400", code_of(j) == 400,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))
st, j, raw = api("POST", "/api/coupons/%s/receive" % f3, token=DEMO_TOKEN)
check("F7 领『已过期』的券 → code=400", code_of(j) == 400,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

bad_rc = int(sql1("SELECT COALESCE(sum(received_count),0) FROM coupons "
                  "WHERE id IN (%s,%s,%s)" % (f1, f2, f3)))
check("F8 ★ DB 核对：三张失败券的 received_count 合计 == 0（一次失败都没改库）",
      bad_rc == 0, "实际 %d" % bad_rc)

# ================================================================ G 我的券/IDOR
say()
say("-" * 74)
say("G ★ 我的券：归属隔离（IDOR）+ 惰性过期（expired 是算出来的）")
say("-" * 74)

check("G0 intruder 登录成功（★★ IDOR 对照的前提 —— 若它拿不到 token，请求会退化成匿名、"
      "G4 的『无交集』会因为两边都空而【假绿】）", bool(INTRUDER_TOKEN),
      "登录失败：%s" % m2)

st, j, raw = api("GET", "/api/coupons/my?%s" % qs({"page": 1, "size": MAX_PAGE_SIZE}),
                 token=DEMO_TOKEN)
check("G1 demo GET /api/coupons/my → code=200", st == 200 and code_of(j) == 200,
      "HTTP %s code %s" % (st, code_of(j)))
mine = records_of(j)
db_mine = count("user_coupons", "user_id = 1")
check("G2 ★ DB 对账：条数 == DB 里 demo 的领取记录数（%d）" % db_mine, len(mine) == db_mine,
      "接口 %d 条" % len(mine))
check("G3 ★ demo 的券里含刚领的那张（couponId=%s）" % d_id,
      any(r.get("couponId") == d_id for r in mine),
      "接口 couponId 集=%s" % [r.get("couponId") for r in mine])

st, j2, raw2 = api("GET", "/api/coupons/my?%s" % qs({"page": 1, "size": MAX_PAGE_SIZE}),
                   token=INTRUDER_TOKEN)
other = records_of(j2)
db_other = count("user_coupons", "user_id = 2")
ids_mine = {r.get("id") for r in mine}
ids_other = {r.get("id") for r in other}
check("G4 ★★ IDOR：intruder 的『我的券』里不含 demo 的任何领取记录（id 集合无交集）",
      not (ids_mine & ids_other), "demo=%s / intruder=%s" % (sorted(ids_mine), sorted(ids_other)))
check("G5 ★ IDOR 对账：intruder 的条数 == DB 里 intruder 的记录数（%d）" % db_other,
      len(other) == db_other, "接口 %d 条" % len(other))

# 惰性过期：造一张已过期但 demo 已领的券
g_id, _r, c = create_coupon(name=CP_PREFIX + "EXPMINE", total=10,
                            start=T_PAST_START, end=T_PAST_END)
sql("INSERT INTO user_coupons (user_id, coupon_id, status) "
    "VALUES (1, %s, 'UNUSED')" % g_id)
st, j, raw = api("GET", "/api/coupons/my?%s" % qs({"page": 1, "size": MAX_PAGE_SIZE}),
                 token=DEMO_TOKEN)
target = [r for r in records_of(j) if r.get("couponId") == g_id]
check("G6 ★ 过期券在『我的券』里 expired == true（由 SQL 现算 c.end_time < CURRENT_TIMESTAMP）",
      bool(target) and target[0].get("expired") is True,
      "找到 %d 条 / %s" % (len(target), target[0] if target else "-"))
check("G7 ★★ 反证：DB 里该行 status 仍是 'UNUSED'（惰性过期不写回 EXPIRED）",
      sql1("SELECT status FROM user_coupons WHERE user_id=1 AND coupon_id=%s" % g_id) == "UNUSED",
      "实际 %s" % sql1("SELECT status FROM user_coupons WHERE user_id=1 AND coupon_id=%s" % g_id))

# ================================================================ H 权限矩阵
say()
say("-" * 74)
say("H ★ 权限矩阵：coupon:* 只发给超管 ⇒ C 端与两个业务管理员全部 403")
say("-" * 74)

h_del, _r, c = create_coupon(name=CP_PREFIX + "PERM", total=10)
check("H0 造一张供删除测试的券（无人领取）→ code=200", c == 200, "实际 code=%s" % c)

PERM_CASES = [
    ("GET", "/api/admin/coupons", None, "coupon:list"),
    ("POST", "/api/admin/coupons", coupon_body(CP_PREFIX + "PERMPROBE"), "coupon:create"),
    ("DELETE", "/api/admin/coupons/%s" % h_del, None, "coupon:delete"),
]
# ★★ 这个矩阵【刻意只放被拒的四类身份，不放超管】：
#    超管打 DELETE 是**真删** —— 把它放进循环，会把下面 H13 的靶子提前删掉
#    （H13 就会因为「券不存在」而假失败，且失败得莫名其妙）。
#    超管的放行分别由 B3（GET）/ C1（POST）/ H13（DELETE）覆盖，不需要在这里重复。
PERM_DENIED = [
    ("匿名", None, 401),
    ("demo(C端)", DEMO_TOKEN, 403),
    ("op_order", ORDER_TOKEN, 403),
    ("op_product", PRODUCT_TOKEN, 403),
]
for method, path, body, perm in PERM_CASES:
    say("    %-6s %-28s [%s]" % (method, path, perm))
    for label, tk, expect in PERM_DENIED:
        st, j, raw = api(method, path, token=tk, body=body)
        check("H %s [%s] %s → HTTP %s" % (method, perm, label, expect),
              st == expect, "实际 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("DELETE", "/api/admin/coupons/%s" % h_del, token=ADMIN_TOKEN)
check("H13 超管删『无人领取』的券 → code=200（守卫不该拦它）",
      code_of(j) == 200, "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))
check("H14 DB 核对：该券已从 coupons 物理删除",
      count("coupons", "id = %s" % h_del) == 0, "实际 %d 行" % count("coupons", "id = %s" % h_del))

st, j, raw = api("DELETE", "/api/admin/coupons/%s" % d_id, token=ADMIN_TOKEN)
check("H15 ★★ 删【已被领取过】的券 → code=400（守卫把外键异常翻译成人话，而不是 500）",
      code_of(j) == 400, "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))
check("H16 DB 核对：被拒删的券仍在（id=%s 还在）" % d_id,
      count("coupons", "id = %s" % d_id) == 1, "实际 %d 行" % count("coupons", "id = %s" % d_id))

# ================================================================ I 健壮性
say()
say("-" * 74)
say("I 健壮性：类型关系校验 / total_count=0 / 分页夹紧")
say("-" * 74)

st, j, raw = api("POST", "/api/admin/coupons", token=ADMIN_TOKEN,
                 body={"name": CP_PREFIX + "NOAMT", "type": "FIXED",
                       "totalCount": 10, "startTime": T_OK_START, "endTime": T_OK_END})
check("I1 ★ FIXED 券缺 discount_amount → code=400（参数层 @Valid 表达不了的关系校验）",
      code_of(j) == 400, "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

st, j, raw = api("POST", "/api/admin/coupons", token=ADMIN_TOKEN,
                 body={"name": CP_PREFIX + "NORATE", "type": "DISCOUNT",
                       "totalCount": 10, "startTime": T_OK_START, "endTime": T_OK_END})
check("I2 ★ DISCOUNT 券缺 discount_rate → code=400", code_of(j) == 400,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

i_ok, _r, c = create_coupon(name=CP_PREFIX + "RATEOK", type_="DISCOUNT", amount=None,
                            rate=88.0, total=10)
check("I3 DISCOUNT 券带 discount_rate → code=200（上一条不是『一律拒绝』）", c == 200,
      "实际 code=%s" % c)

i_zero, _r, c = create_coupon(name=CP_PREFIX + "ZERO", total=0)
check("I4 total_count=0 的券建得出来 → code=200（先占位后放量是合法业务）", c == 200,
      "实际 code=%s" % c)
st, j, raw = api("POST", "/api/coupons/%s/receive" % i_zero, token=DEMO_TOKEN)
check("I5 但谁都领不到 → code=400（守卫 received_count < total_count 即 0 < 0 为假）",
      code_of(j) == 400, "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

st, j, raw = api("POST", "/api/admin/coupons", token=ADMIN_TOKEN,
                 body={"name": "", "type": "FIXED", "discountAmount": 10.0,
                       "totalCount": 10, "startTime": T_OK_START, "endTime": T_OK_END})
check("I6 券名为空 → code=400（@NotBlank 在参数层挡住）", code_of(j) == 400,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

st, j, raw = api("POST", "/api/admin/coupons", token=ADMIN_TOKEN,
                 body={"name": CP_PREFIX + "BADTYPE", "type": "CASH",
                       "discountAmount": 10.0, "totalCount": 10,
                       "startTime": T_OK_START, "endTime": T_OK_END})
check("I7 券类型 CASH（不在 FIXED|DISCOUNT 内）→ code=400（@Pattern；"
      "列没有 CHECK 约束，取值只能靠应用层守）", code_of(j) == 400,
      "HTTP %s code %s / %s" % (st, code_of(j), raw[:160]))

# 分页夹紧：样本量必须 > 上限才有区分度（库里券数远小于 100）
n_now = count("coupons")
sql("INSERT INTO coupons (name, type, discount_amount, min_amount, total_count, "
    "received_count, start_time, end_time, status) "
    "SELECT '%sBULK-' || g, 'FIXED', 5.00, 0.00, 100, 0, "
    "CURRENT_TIMESTAMP - INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '30 day', 1 "
    "FROM generate_series(1, %d) g" % (CP_PREFIX, BULK_N))
mysql = count("coupons")
check("I8 造数生效：coupons 从 %d 增到 %d（样本量 > 上限 %d，夹紧才验得出来）"
      % (n_now, mysql, MAX_PAGE_SIZE), mysql == n_now + BULK_N, "实际 %d" % mysql)

st, j, raw = api("GET", "/api/coupons?%s" % qs({"page": 1, "size": 999}))
n999 = len(records_of(j))
check("I9 ★ size=999 → records 恰好 %d 条（夹紧公式 min(max(size,1),100) 生效；"
      "未夹紧会返回全部 %d 条，一次拖走整张表）" % (MAX_PAGE_SIZE, mysql),
      n999 == MAX_PAGE_SIZE, "实际 %d 条（库里 %d 张）" % (n999, mysql))

st, j, raw = api("GET", "/api/coupons?%s" % qs({"page": 1, "size": 1000}))
check("I10 size=1000 时 total == DB 里可领券的真实张数（夹紧不改过滤口径）",
      total_of(j) == int(sql1("SELECT count(*) FROM coupons WHERE status=1 "
                              "AND start_time <= CURRENT_TIMESTAMP "
                              "AND end_time >= CURRENT_TIMESTAMP "
                              "AND received_count < total_count")),
      "接口 total=%s" % total_of(j))

st, j, raw = api("GET", "/api/coupons?%s" % qs({"page": 1, "size": 0}))
check("I11 size=0 → records 恰好 1 条（负数/零被夹到【下限 1】，"
      "未夹紧时 MP 会返回空列表 —— 不报错但分页器坏了）",
      len(records_of(j)) == 1, "实际 %d 条" % len(records_of(j)))

# ================================================================ J 清理
say()
say("-" * 74)
say("J 高水位线清理（★ 按 FK 引用顺序：先 user_coupons，再 coupons / users）")
say("-" * 74)

cleanup()
end_cp = count("coupons")
end_uc = count("user_coupons")
end_us = count("users")
leftover_cp = count("coupons", "name LIKE '%s%%'" % CP_PREFIX)
leftover_us = count("users", "username LIKE '%s%%'" % US_PREFIX)

check("J1 coupons 回基线 %d" % BASE_CP, end_cp == BASE_CP, "实际 %d" % end_cp)
check("J2 user_coupons 回基线 %d" % BASE_UC, end_uc == BASE_UC, "实际 %d" % end_uc)
check("J3 users 回基线 %d（临时用户已删）" % BASE_US, end_us == BASE_US, "实际 %d" % end_us)
check("J4 无残留临时标识（券 %d 张 / 用户 %d 个）" % (leftover_cp, leftover_us),
      leftover_cp == 0 and leftover_us == 0,
      "残留券=%d 残留用户=%d" % (leftover_cp, leftover_us))

# ================================================================ 汇总
say()
say("=" * 74)
say("TOTAL: PASS=%d  FAIL=%d   （期望断言数 %d）" % (PASS, FAIL, EXPECTED))
if PASS + FAIL != EXPECTED:
    say("[FAIL] 断言总数与 EXPECTED 不符 —— 有断言被静默跳过，或 EXPECTED 需要校准！")
    FAILS.append("ASSERTION COUNT MISMATCH (actual %d, expected %d)" % (PASS + FAIL, EXPECTED))
say("VERDICT: %s" % ("OK 全绿" if FAIL == 0 else ("FAILED -> " + "; ".join(FAILS))))
say("=" * 74)
say("下一步（K 链路）：python day17-m1-regression.py  —— 期望 198/198 + BASELINE RESTORED")

with open("day20-coupon-verify-report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")

sys.exit(0 if FAIL == 0 else 1)
