#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Day 22 验收（A–E 五组）：用户管理 + 仪表盘 + 安全收口回归 + L7。

★ 与 day22-skeleton-smoke.py 的分工：
    smoke   = 骨架期门禁（期望 200 + code 500，实现填完后它必然失效）
    本脚本  = **实现期验收**（期望真数据），是「安全收口」的长期回归断言。
  ⇒ 两个脚本的期望值【方向相反】，别把 smoke 的断言搬到这儿（见文档 §二末段）。

五组：
  [A] 安全回归 —— 把 day22-sec-probe.py 的断言【反过来写】：
      旧三个端点必须 404；/me 只能看自己；出口【不含 password 键】；user:list 的 path 已订正。
  [B] 用户管理 —— 分页夹紧（size 字段 + 记录数双判）、keyword 跨三列、
      ★ 括号正确性（唯一的判据是「已禁用但昵称命中」的行不许漏进来）、状态条件更新 + 幂等 + 404。
  [C] 权限矩阵 —— 非对称形状（读给业务角色、写给超管）必须有【反向对照】才算验过。
  [D] 仪表盘 —— 4 标量逐值对账；★ 销售额的【支付口径】用一条 FAILED 支付来证伪；
      ★ 补 0 用「零点个数 == 天数 - DB 里有单的天数」来证（不靠「今天恰好没单」这种运气）。
  [E] L7 + 老链路 —— 恒等式三数一起断；不用券时 discount 是 0.00 而不是 null。

★★ 三条纪律（本项目反复踩过）：
  ① 断言对着【设计】写，不对着库的默认行为写；脚本与设计打架时改脚本。
  ② 造的数据必须【高水位线清理】，且跑完断言【基线还原】——否则 M1 的计数断言必红。
  ③ 清理写在 finally 里：断言中途炸了也要清干净（否则下一次跑从脏状态开始）。

运行：python day22-admin-verify.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 满额断言条数（★ 首次跑后按报告 TOTAL 行校准）
# 2026-09-24 静态清点：A 10 + B 19 + C 8 + D 21（含 D3 三角色 3 条）+ E 7 + F 2 = 67
EXPECTED = 67

# ---- 夹具标记（清理一律按它，不依赖 username 内容）----
EMAIL_MARK = "d22cw"
ORD_MARK = "D22CW"
FAIL_AMOUNT = "777.77"          # 故意失败的支付，必须【不计入】销售额
OK_ADD_AMOUNT = "123.45"        # 故意成功的支付，销售额必须【恰好增加】这么多

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


# ============================================================ psql 通道
def _psql(statement, allow_empty=False):
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("psql rc=%s: %s" % (r.returncode, (r.stderr or "").strip()[:300]))
    rows = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]
    if not rows and not allow_empty:
        raise RuntimeError("psql 返回空输出 —— 多半是 Docker 引擎没起（不是脚本问题）")
    return rows


def sql1(stmt):
    return _psql(stmt)[0]


def sql_int(stmt):
    return int(sql1(stmt))


def sql_exec(stmt):
    return _psql(stmt, allow_empty=True)


def sql_many(stmt):
    return _psql(stmt)


# ============================================================ HTTP 通道
def api(method, path, token=None, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(APP + path, method=method, data=data, headers=headers)
    try:
        with _opener.open(req, timeout=25) as resp:
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


def code_of(j):
    return j.get("code") if isinstance(j, dict) else None


def data_of(j):
    return (j.get("data") if isinstance(j, dict) else None)


def records_of(j):
    d = data_of(j)
    return (d.get("records") if isinstance(d, dict) else None) or []


def login(path, username, password):
    st, j, raw = api("POST", path, body={"username": username, "password": password})
    if code_of(j) != 200:
        return None, "HTTP %s / %s" % (st, raw[:120])
    return (data_of(j) or {}).get("token"), "OK"


def wait_ready(deadline=150):
    t0 = time.time()
    while time.time() - t0 < deadline:
        st, _, _ = api("GET", "/api/hello")
        if st != -1:
            return True
        time.sleep(2)
    return False


def dec(x):
    from decimal import Decimal
    return Decimal(str(x))


def dec_eq(a, b):
    try:
        return dec(a) == dec(b)
    except Exception:                                             # noqa: BLE001
        return False


# ============================================================ 护栏：实现是否真的填了
def guard_implemented():
    files = [
        os.path.join(ROOT, "mallx/mall-user/src/main/java/com/mallx/user/service/impl/AdminUserServiceImpl.java"),
        os.path.join(ROOT, "mallx/mall-user/src/main/java/com/mallx/user/service/impl/UserServiceImpl.java"),
        os.path.join(ROOT, "mallx/mall-admin/src/main/java/com/mallx/admin/service/impl/DashboardServiceImpl.java"),
        os.path.join(ROOT, "mallx/mall-admin/src/main/resources/mapper/DashboardMapper.xml"),
    ]
    bad = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            txt = fh.read()
        if "UnsupportedOperationException" in txt:
            bad.append("Java 占位仍在: " + os.path.basename(f))
    xml = files[3]
    with open(xml, encoding="utf-8") as fh:
        for m in re.finditer(r"<select\b[^>]*\bid=\"(\w+)\"[^>]*>(.*?)</select>", fh.read(), re.S):
            body = m.group(2).strip()
            if not re.match(r"(?is)^(select|with|insert|update|delete)\b", body):
                bad.append("XML 语句体为空/非法: %s" % m.group(1))
    return bad


# ============================================================ 清理（高水位线）
def cleanup():
    # 顺序即语义：payments → orders（外键方向）；users 最后（它是两者的父）
    sql_exec("DELETE FROM payments WHERE payment_no LIKE '%s-%%'" % ORD_MARK)
    sql_exec("DELETE FROM orders   WHERE order_no   LIKE '%s-%%'" % ORD_MARK)
    sql_exec("DELETE FROM users    WHERE email      LIKE '%s%%'" % EMAIL_MARK)


def baseline():
    return {
        "users": sql_int("SELECT count(*) FROM users"),
        "products": sql_int("SELECT count(*) FROM products WHERE is_deleted = 0"),
        "orders": sql_int("SELECT count(*) FROM orders"),
        "payments": sql_int("SELECT count(*) FROM payments"),
        "coupons": sql_int("SELECT count(*) FROM coupons"),
        "user_coupons": sql_int("SELECT count(*) FROM user_coupons"),
    }


# ============================================================ 主流程
say("=" * 78)
say("Day 22 验收：用户管理 + 仪表盘 + 安全收口回归 + L7（A–E）")
say("=" * 78)

say("\n[0] 护栏与准备")
bad = guard_implemented()
if bad:
    say("  [FATAL] 实现没填完，拒绝执行（拿半成品跑验收，报告里分不清「没写」还是「写错」）：")
    for b in bad:
        say("      - %s" % b)
    raise SystemExit(3)
say("  [OK] 7 处实现与 5 条 SQL 均已落地（无 UnsupportedOperationException / 无空语句体）")

if not wait_ready():
    say("  [FATAL] 应用 150s 内未就绪")
    raise SystemExit(2)
say("  [OK] 应用已就绪")

cleanup()
BASE = baseline()
say("  基线: %s" % BASE)

DEMO_TOKEN, m1 = login("/api/auth/login", "demo", "demo123")
ADMIN_TOKEN, m2 = login("/api/auth/admin/login", "admin", "admin123")
ORDER_TOKEN, m3 = login("/api/auth/admin/login", "op_order", "op123456")
PROD_TOKEN, m4 = login("/api/auth/admin/login", "op_product", "prod123456")
for nm, tk, msg in (("demo(C端)", DEMO_TOKEN, m1), ("admin(超管)", ADMIN_TOKEN, m2),
                    ("op_order", ORDER_TOKEN, m3), ("op_product", PROD_TOKEN, m4)):
    say("    login %-14s -> %s" % (nm, "OK" if tk else msg))
if not (DEMO_TOKEN and ADMIN_TOKEN and ORDER_TOKEN and PROD_TOKEN):
    say("  [FATAL] 四个账号必须都能登录")
    raise SystemExit(2)

DEMO_ID = sql_int("SELECT id FROM users WHERE username = 'demo'")
PUBLIC_KEYS = {"id", "username", "nickname", "phone", "email", "status", "createdAt"}
say("    demo.id=%d  公开字段白名单=%s" % (DEMO_ID, sorted(PUBLIC_KEYS)))

# 造夹具用户：alpha=启用且昵称命中 / beta=禁用且昵称命中（★ 括号判据的靶子）/ gamma=用户名命中
ALPHA_ID = int(sql1(
    "INSERT INTO users (username, password, nickname, phone, email, status) VALUES "
    "('d22tmp_alpha', '{noop}D22CW', 'D22CW_ALPHA', '13900001001', 'd22cw+alpha@t.local', 1) "
    "RETURNING id"))
BETA_ID = int(sql1(
    "INSERT INTO users (username, password, nickname, phone, email, status) VALUES "
    "('d22tmp_beta', '{noop}D22CW', 'D22CW_BETA', '13900001002', 'd22cw+beta@t.local', 0) "
    "RETURNING id"))
GAMMA_ID = int(sql1(
    "INSERT INTO users (username, password, nickname, phone, email, status) VALUES "
    "('D22CW_GAMMA_USER', '{noop}D22CW', 'd22tmp_gamma', '13900001003', 'd22cw+gamma@t.local', 1) "
    "RETURNING id"))
say("    夹具用户 alpha=%d(启用) beta=%d(禁用) gamma=%d(用户名命中)"
    % (ALPHA_ID, BETA_ID, GAMMA_ID))

# 仪表盘夹具：一单 + 两条支付（4 天前）
FIX_ORDER_ID = int(sql1(
    "INSERT INTO orders (order_no, user_id, total_amount, pay_amount, status, "
    " receiver_name, receiver_phone, receiver_address, created_at) VALUES "
    "('%s-ORD-1', %d, 10.00, 10.00, 'PENDING', 'D22CW', '13900001000', 'D22CW addr', "
    " now() - interval '4 days') RETURNING id" % (ORD_MARK, DEMO_ID)))
say("    夹具订单 id=%d（created_at = 4 天前）" % FIX_ORDER_ID)

try:
    # ======================================================== A 安全回归
    say("\n[A] ★ 安全回归：漏洞入口必须【全部 404】，出口必须【不再有 password】")
    st, j, raw = api("GET", "/api/users")
    check("A1 匿名 GET /api/users -> HTTP 401（仍要登录，不是公开）", st == 401,
          "实测 HTTP %s / %s" % (st, raw[:80]))

    st, j, raw = api("GET", "/api/users", token=DEMO_TOKEN)
    check("A2 demo GET /api/users -> HTTP 404（★ 从前 200 + 全站口令哈希）", st == 404,
          "实测 HTTP %s / %s" % (st, raw[:100]))

    st, j, raw = api("GET", "/api/users/2", token=DEMO_TOKEN)
    check("A3 demo GET /api/users/{别人} -> HTTP 404（从前 200）", st == 404,
          "实测 HTTP %s / %s" % (st, raw[:100]))

    st, j, raw = api("PUT", "/api/users/2/nickname", token=DEMO_TOKEN, body={"nickname": "x"})
    check("A4 demo PUT /api/users/{别人}/nickname -> HTTP 404（从前 200，能改任何人）",
          st == 404, "实测 HTTP %s / %s" % (st, raw[:100]))

    st, j, raw = api("GET", "/api/users/me", token=DEMO_TOKEN)
    me = data_of(j) or {}
    check("A5 demo GET /api/users/me -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:100]))
    check("A6 ★ /me 返回的就是【自己】（data.id == demo 的 DB id）",
          me.get("id") == DEMO_ID, "接口 id=%r  DB demo id=%r" % (me.get("id"), DEMO_ID))
    check("A7 ★★ /me 响应体【不含 password 键】（外泄根因已除）",
          "password" not in me, "键=%s" % sorted(me.keys()))
    check("A8 ★ /me 响应键 ⊆ 公开字段白名单（多出任何一列都算泄露）",
          set(me.keys()) <= PUBLIC_KEYS,
          "多出=%s" % sorted(set(me.keys()) - PUBLIC_KEYS))

    st, j, raw = api("GET", "/api/admin/users", token=ADMIN_TOKEN)
    recs = records_of(j)
    leak = [r.get("id") for r in recs if not (set(r.keys()) <= PUBLIC_KEYS)]
    check("A9 ★ 管理端用户列表每条的键 ⊆ 公开白名单（全站列表也不漏 password）",
          bool(recs) and not leak, "越界行 id=%s 首行键=%s"
          % (leak, sorted(recs[0].keys()) if recs else "N/A"))

    p1 = sql1("SELECT path FROM permissions WHERE code = 'user:list'")
    check("A10 ★ DB：user:list 的 path 已从 /api/users 订正为 /api/admin/users",
          p1 == "/api/admin/users", "实测 path=%r" % p1)

    # ======================================================== B 用户管理
    say("\n[B] 用户管理：分页夹紧 / keyword 三列 / ★ 括号 / 状态条件更新")
    st, j, raw = api("GET", "/api/admin/users?current=1&size=-1", token=ADMIN_TOKEN)
    d = data_of(j) or {}
    check("B1 size=-1 夹到【下限 1】（size 字段=1 且只回 1 条）",
          d.get("size") == 1 and len(records_of(j)) == 1,
          "size=%r 条数=%d" % (d.get("size"), len(records_of(j))))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=0", token=ADMIN_TOKEN)
    d = data_of(j) or {}
    check("B2 size=0 夹到【下限 1】（不夹的话 MP 会 LIMIT 0 ⇒ 0 条）",
          d.get("size") == 1 and len(records_of(j)) == 1,
          "size=%r 条数=%d" % (d.get("size"), len(records_of(j))))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=1000", token=ADMIN_TOKEN)
    d = data_of(j) or {}
    check("B3 size=1000 夹到【上限 100】（★ 用 size 字段判，不靠记录数——库里没 100 条）",
          d.get("size") == 100, "size=%r" % d.get("size"))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=100&keyword=D22CW", token=ADMIN_TOKEN)
    d = data_of(j) or {}
    ids = {r.get("id") for r in records_of(j)}
    check("B4 keyword=D22CW 跨三列任一命中 -> 3 条（alpha/beta 走昵称，gamma 走用户名）",
          d.get("total") == 3 and ids == {ALPHA_ID, BETA_ID, GAMMA_ID},
          "total=%r ids=%s" % (d.get("total"), sorted(ids)))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=100&keyword=D22CW&status=1",
                     token=ADMIN_TOKEN)
    d = data_of(j) or {}
    ids = {r.get("id") for r in records_of(j)}
    check("B5 ★★ 括号正确性：keyword=D22CW + status=1 -> 恰好 2 条，【已禁用的 beta 不许漏进来】",
          d.get("total") == 2 and ids == {ALPHA_ID, GAMMA_ID} and BETA_ID not in ids,
          "total=%r ids=%s（beta=%d 出现=漏括号）" % (d.get("total"), sorted(ids), BETA_ID))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=100&keyword=D22CW&status=0",
                     token=ADMIN_TOKEN)
    d = data_of(j) or {}
    ids = {r.get("id") for r in records_of(j)}
    check("B6 keyword=D22CW + status=0 -> 恰好 beta 一条",
          d.get("total") == 1 and ids == {BETA_ID}, "total=%r ids=%s" % (d.get("total"), sorted(ids)))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=100&keyword=1390000100",
                     token=ADMIN_TOKEN)
    d = data_of(j) or {}
    check("B7 keyword 命中【phone】列 -> 3 条（证明 phone 参与 OR）",
          d.get("total") == 3, "total=%r" % d.get("total"))

    st, j, raw = api("GET", "/api/admin/users?current=1&size=100&keyword=D22CW_GAMMA",
                     token=ADMIN_TOKEN)
    d = data_of(j) or {}
    ids = {r.get("id") for r in records_of(j)}
    check("B8 keyword 命中【username】列 -> 恰好 gamma",
          d.get("total") == 1 and ids == {GAMMA_ID}, "total=%r ids=%s" % (d.get("total"), sorted(ids)))

    t_all = (data_of(api("GET", "/api/admin/users?current=1&size=100", token=ADMIN_TOKEN)[1]) or {}).get("total")
    t_1 = (data_of(api("GET", "/api/admin/users?current=1&size=100&status=1", token=ADMIN_TOKEN)[1]) or {}).get("total")
    t_0 = (data_of(api("GET", "/api/admin/users?current=1&size=100&status=0", token=ADMIN_TOKEN)[1]) or {}).get("total")
    check("B9 ★ status 不传 = 两者都要（total 无过滤 == status=1 + status=0）",
          t_all == t_1 + t_0 and t_0 >= 1,
          "全部=%r 启用=%r 禁用=%r" % (t_all, t_1, t_0))

    st, j, raw = api("GET", "/api/admin/users/%d" % ALPHA_ID, token=ADMIN_TOKEN)
    d = data_of(j) or {}
    check("B10 管理端详情 -> HTTP 200 + code 200 + 用户名对得上",
          st == 200 and code_of(j) == 200 and d.get("username") == "d22tmp_alpha",
          "HTTP %s code %s username=%r" % (st, code_of(j), d.get("username")))
    check("B11 ★ 详情响应也不含 password 键", "password" not in d, "键=%s" % sorted(d.keys()))

    st, j, raw = api("GET", "/api/admin/users/999999999", token=ADMIN_TOKEN)
    check("B12 详情 id 不存在 -> code 404（真 404 语义，不伪装）", code_of(j) == 404,
          "HTTP %s code %s / %s" % (st, code_of(j), raw[:100]))

    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=ADMIN_TOKEN,
                     body={"status": 0})
    db_status = sql_int("SELECT status FROM users WHERE id = %d" % ALPHA_ID)
    check("B13 改状态 1->0 -> 200 且 DB 落到 0",
          st == 200 and code_of(j) == 200 and db_status == 0,
          "HTTP %s code %s DB status=%d" % (st, code_of(j), db_status))

    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=ADMIN_TOKEN,
                     body={"status": 0})
    db_status = sql_int("SELECT status FROM users WHERE id = %d" % ALPHA_ID)
    check("B14 ★ 幂等：重复禁用 -> 200（不是 404/409），DB 仍是 0",
          st == 200 and code_of(j) == 200 and db_status == 0,
          "HTTP %s code %s DB status=%d" % (st, code_of(j), db_status))

    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=ADMIN_TOKEN,
                     body={"status": 1})
    db_status = sql_int("SELECT status FROM users WHERE id = %d" % ALPHA_ID)
    check("B15 改回启用 -> DB 落到 1（状态可双向改）",
          db_status == 1, "HTTP %s DB status=%d" % (st, db_status))

    st, j, raw = api("PUT", "/api/admin/users/999999999/status", token=ADMIN_TOKEN,
                     body={"status": 1})
    check("B16 ★ 改不存在的 id -> code 404（影响行数 0 == 不存在，没有先查后改）",
          code_of(j) == 404, "HTTP %s code %s / %s" % (st, code_of(j), raw[:100]))

    bump = sql1("SELECT (updated_at > created_at)::text FROM users WHERE id = %d" % ALPHA_ID)
    check("B17 ★ updates 走了显式 updated_at（手写 UpdateWrapper 不走自动填充 ⇒ 我们显式补了）",
          bump == "true", "updated_at > created_at = %r" % bump)

    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=ADMIN_TOKEN,
                     body={"status": 9})
    check("B18 越界 status=9 -> code 400（@Max 挡下，不是 200+500）", code_of(j) == 400,
          "HTTP %s code %s" % (st, code_of(j)))

    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=ADMIN_TOKEN, body={})
    check("B19 空载荷 {} -> code 400（@NotNull 挡下）", code_of(j) == 400,
          "HTTP %s code %s" % (st, code_of(j)))

    # ======================================================== C 权限矩阵
    say("\n[C] 权限矩阵：读给业务角色、写给超管（★ 每一条「给」都要配一条「不给」）")
    st, j, raw = api("GET", "/api/admin/users")
    check("C1 匿名 GET /api/admin/users -> HTTP 401", st == 401,
          "实测 HTTP %s / %s" % (st, raw[:80]))

    st, j, raw = api("GET", "/api/admin/users", token=DEMO_TOKEN)
    check("C2 ★ C 端 token 打管理端 -> HTTP 403（C 端 token 无 perms）", st == 403,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, raw = api("GET", "/api/admin/users", token=PROD_TOKEN)
    check("C3 ★ op_product（无 user:*）-> HTTP 403（反向对照）", st == 403,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, raw = api("GET", "/api/admin/users", token=ORDER_TOKEN)
    check("C4 ★ op_order（有 user:list）-> HTTP 200 + code 200（读是必要的）",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, raw = api("GET", "/api/admin/users/%d" % ALPHA_ID, token=ORDER_TOKEN)
    check("C5 ★ op_order（有 user:detail）-> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    before = sql_int("SELECT status FROM users WHERE id = %d" % ALPHA_ID)
    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=ORDER_TOKEN,
                     body={"status": 0})
    after = sql_int("SELECT status FROM users WHERE id = %d" % ALPHA_ID)
    check("C6 ★★ op_order PUT /{id}/status -> HTTP 403（user:status 只给超管）",
          st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))
    check("C7 ★★ 被拒的写【一行都没落库】（403 不只是个状态码）",
          before == after == 1, "改前=%d 改后=%d" % (before, after))

    st, j, raw = api("PUT", "/api/admin/users/%d/status" % ALPHA_ID, token=PROD_TOKEN,
                     body={"status": 0})
    check("C8 op_product PUT /{id}/status -> HTTP 403（连 user:list 都没有）", st == 403,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    # ======================================================== D 仪表盘
    say("\n[D] 仪表盘：4 标量对账 + ★ 销售额支付口径 + ★ 补 0")
    st, j, raw = api("GET", "/api/admin/dashboard/overview")
    check("D1 匿名 overview -> HTTP 401", st == 401, "实测 HTTP %s / %s" % (st, raw[:80]))

    st, j, raw = api("GET", "/api/admin/dashboard/overview", token=DEMO_TOKEN)
    check("D2 ★ C 端 token 打仪表盘 -> HTTP 403", st == 403,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    for nm, tk in (("admin", ADMIN_TOKEN), ("op_order", ORDER_TOKEN), ("op_product", PROD_TOKEN)):
        st, j, raw = api("GET", "/api/admin/dashboard/overview", token=tk)
        check("D3-%s 三角色全给：%s overview -> HTTP 200 + code 200" % (nm, nm),
              st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, raw = api("GET", "/api/admin/dashboard/overview", token=ADMIN_TOKEN)
    ov = data_of(j) or {}
    check("D4 userCount 与 DB 一致（全表，含已禁用）",
          ov.get("userCount") == sql_int("SELECT count(*) FROM users"),
          "接口=%r DB=%r" % (ov.get("userCount"), sql_int("SELECT count(*) FROM users")))
    check("D5 productCount 与 DB 一致（★ 口径 is_deleted=0）",
          ov.get("productCount") == sql_int("SELECT count(*) FROM products WHERE is_deleted = 0"),
          "接口=%r DB=%r" % (ov.get("productCount"),
                             sql_int("SELECT count(*) FROM products WHERE is_deleted = 0")))
    check("D6 orderCount 与 DB 一致（全表，含已取消）",
          ov.get("orderCount") == sql_int("SELECT count(*) FROM orders"),
          "接口=%r DB=%r" % (ov.get("orderCount"), sql_int("SELECT count(*) FROM orders")))

    db_sales = sql1("SELECT coalesce(sum(amount), 0) FROM payments WHERE status = 'SUCCESS'")
    check("D7 salesAmount 与 DB 支付口径一致（coalesce(sum) WHERE SUCCESS）",
          dec_eq(ov.get("salesAmount"), db_sales),
          "接口=%r DB=%r" % (ov.get("salesAmount"), db_sales))

    sql_exec("INSERT INTO payments (payment_no, order_id, amount, method, status, paid_at) "
             "VALUES ('%s-PAY-FAIL', %d, %s, 'ALIPAY', 'FAILED', now() - interval '4 days')"
             % (ORD_MARK, FIX_ORDER_ID, FAIL_AMOUNT))
    st, j, raw = api("GET", "/api/admin/dashboard/overview", token=ADMIN_TOKEN)
    ov2 = data_of(j) or {}
    check("D8 ★★ 失败支付【不计入】销售额（支付口径的证据，不是订单口径）",
          dec_eq(ov2.get("salesAmount"), db_sales),
          "插 FAILED %s 后接口=%r（应为 %r 不变）" % (FAIL_AMOUNT, ov2.get("salesAmount"), db_sales))

    sql_exec("INSERT INTO payments (payment_no, order_id, amount, method, status, paid_at) "
             "VALUES ('%s-PAY-OK', %d, %s, 'ALIPAY', 'SUCCESS', now() - interval '4 days')"
             % (ORD_MARK, FIX_ORDER_ID, OK_ADD_AMOUNT))
    st, j, raw = api("GET", "/api/admin/dashboard/overview", token=ADMIN_TOKEN)
    ov3 = data_of(j) or {}
    check("D9 ★★ 成功支付【恰好加】%s（销售额真的在算，不是恒 0）" % OK_ADD_AMOUNT,
          dec_eq(ov3.get("salesAmount"), dec(db_sales) + dec(OK_ADD_AMOUNT)),
          "插 SUCCESS %s 后接口=%r（应为 %r）"
          % (OK_ADD_AMOUNT, ov3.get("salesAmount"), dec(db_sales) + dec(OK_ADD_AMOUNT)))

    # ---- 趋势 + 补 0 ----
    today = date.today()
    start7 = (today - timedelta(days=6)).isoformat()
    st, j, raw = api("GET", "/api/admin/dashboard/trend?days=7", token=ADMIN_TOKEN)
    pts = data_of(j) or []
    check("D10 trend days=7 -> 恰好 7 个点（★ 直觉写法只会有「有单的那几天」）",
          len(pts) == 7, "实测 %d 个点" % len(pts))

    expect_dates = [(today - timedelta(days=6 - i)).isoformat() for i in range(7)]
    got_dates = [p.get("date") for p in pts]
    check("D11 日期序列 = 连续 7 天、升序、最后一天=今天",
          got_dates == expect_dates, "实测=%s 期望=%s" % (got_dates[:3], expect_dates[:3]))

    db_in_window = sql_int("SELECT count(*) FROM orders WHERE created_at >= '%s'::date" % start7)
    api_sum = sum(int(p.get("orderCount") or 0) for p in pts)
    check("D12 趋势里的 orderCount 之和 == DB 窗口内订单数",
          api_sum == db_in_window, "接口和=%d DB=%d" % (api_sum, db_in_window))

    db_days = sql_int("SELECT count(DISTINCT to_char(created_at, 'YYYY-MM-DD')) FROM orders "
                      "WHERE created_at >= '%s'::date" % start7)
    zeros = len([p for p in pts if int(p.get("orderCount") or 0) == 0])
    check("D13 ★★ 补 0 的证明：零点个数 == 天数 - DB 里有单的天数（%d - %d = %d）"
          % (7, db_days, 7 - db_days),
          zeros == 7 - db_days, "实测零点=%d 期望=%d" % (zeros, 7 - db_days))

    fix_day = (today - timedelta(days=4)).isoformat()
    fix_pt = [p for p in pts if p.get("date") == fix_day]
    check("D14 我造的「4 天前那一单」落在正确的点上（orderCount >= 1）",
          bool(fix_pt) and int(fix_pt[0].get("orderCount") or 0) >= 1,
          "%s 的点=%r" % (fix_day, fix_pt[0] if fix_pt else None))

    check("D15 ★ 补 0 补的是 0 而不是 null（salesAmount 全非 null）",
          all(p.get("salesAmount") is not None for p in pts),
          "含 null 的点数=%d" % len([p for p in pts if p.get("salesAmount") is None]))

    st, j, raw = api("GET", "/api/admin/dashboard/trend?days=-1", token=ADMIN_TOKEN)
    check("D16 ★ days=-1 夹到【下限 1】-> 1 个点（不夹的话 generate_series 回空集，看着像「没生意」）",
          len(data_of(j) or []) == 1, "实测 %d 个点" % len(data_of(j) or []))

    st, j, raw = api("GET", "/api/admin/dashboard/trend?days=100000", token=ADMIN_TOKEN)
    check("D17 ★ days=100000 夹到【上限 90】-> 90 个点",
          len(data_of(j) or []) == 90, "实测 %d 个点" % len(data_of(j) or []))

    st, j, raw = api("GET", "/api/admin/dashboard/trend", token=ADMIN_TOKEN)
    check("D18 days 不传 -> 默认 7（靠 @RequestParam 的 defaultValue）",
          len(data_of(j) or []) == 7, "实测 %d 个点" % len(data_of(j) or []))

    st, j, raw = api("GET", "/api/admin/dashboard/trend?days=7")
    check("D19 匿名 trend -> HTTP 401", st == 401, "实测 HTTP %s / %s" % (st, raw[:80]))

    # ======================================================== E L7 + 老链路
    say("\n[E] L7（订单 VO 带 discountAmount）+ 老链路存活")
    MY_ORDER_ID = sql_int("SELECT coalesce(min(id), 0) FROM orders WHERE user_id = %d" % DEMO_ID)
    if MY_ORDER_ID:
        st, j, raw = api("GET", "/api/orders/%d" % MY_ORDER_ID, token=DEMO_TOKEN)
        od = data_of(j) or {}
        check("E1 C 端订单详情含 discountAmount 键", "discountAmount" in od,
              "键=%s" % sorted(od.keys()))
        check("E2 ★ 恒等式 pay = total - discount（三个数一起断）",
              dec_eq(od.get("payAmount"),
                     dec(od.get("totalAmount")) - dec(od.get("discountAmount"))),
              "total=%r pay=%r discount=%r"
              % (od.get("totalAmount"), od.get("payAmount"), od.get("discountAmount")))
        check("E3 ★ 不用券时 discountAmount = 0 而不是 null",
              od.get("discountAmount") is not None and dec_eq(od.get("discountAmount"), 0),
              "discountAmount=%r" % od.get("discountAmount"))

        st, j, raw = api("GET", "/api/orders", token=DEMO_TOKEN)
        recs = records_of(j)
        check("E4 C 端订单列表 records[0] 也含 discountAmount（两个出口都要有）",
              bool(recs) and "discountAmount" in recs[0],
              "首行键=%s" % (sorted(recs[0].keys()) if recs else "N/A"))
    else:
        for nm in ("E1 C 端订单详情含 discountAmount 键",
                   "E2 恒等式 pay = total - discount",
                   "E3 不用券时 discountAmount = 0",
                   "E4 C 端订单列表含 discountAmount"):
            check(nm, False, "demo 名下没有订单，无法验")

    st, j, raw = api("GET", "/api/products")
    check("E5 GET /api/products（公开）-> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))
    st, j, raw = api("GET", "/api/orders", token=DEMO_TOKEN)
    check("E6 demo GET /api/orders -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))
    st, j, raw = api("GET", "/api/cart", token=DEMO_TOKEN)
    check("E7 demo GET /api/cart -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

finally:
    # ======================================================== 清理 + 基线还原
    say("\n[F] 清理夹具 + 基线还原")
    cleanup()
    NOW = baseline()
    same = all(NOW[k] == BASE[k] for k in BASE)
    check("F1 ★ 基线还原：清理后六张表的计数与开工前【逐一相等】",
          same, "开工前=%s 清理后=%s" % (BASE, NOW))
    left = sql_int("SELECT count(*) FROM users WHERE email LIKE '%s%%'" % EMAIL_MARK)
    check("F2 夹具用户已清空（email LIKE '%s%%' 剩 %d 行）" % (EMAIL_MARK, left), left == 0,
          "残留 %d 行" % left)

# ---------------------------------------------------------------- 收尾
say("\n" + "-" * 78)
say("TOTAL: %d / %d 通过，%d 失败" % (PASS, PASS + FAIL, FAIL))
if FAILS:
    say("FAILED:")
    for f in FAILS:
        say("  - %s" % f)
say("VERDICT: %s" % ("OK —— 安全收口 + 用户管理 + 仪表盘 + L7 全部成立"
                     if FAIL == 0 else "有失败项，见上"))
say("-" * 78)

if PASS + FAIL != EXPECTED:
    say("!! 护栏：断言总数 %d != EXPECTED %d —— 有断言被跳过，或 EXPECTED 需校准"
        % (PASS + FAIL, EXPECTED))

with open(os.path.join(HERE, "day22-admin-verify-report.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(LINES) + "\n")
say("(报告已写入 day22-admin-verify-report.txt)")

raise SystemExit(1 if FAIL else 0)
