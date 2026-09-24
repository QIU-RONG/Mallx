#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Day 22 骨架 smoke（起应用后的第一道门）：安全收口 + 权限矩阵 + 骨架三态 + L7。

★ 本脚本的性质：**骨架期一次性**的验收，实现填完后它的 B/C 组断言会全部失效
  （500 → 200）。它要回答的是四个问题：

  [A] **漏洞入口真的拆掉了吗** —— 旧端点 GET /api/users、GET /api/users/{id}、
      PUT /api/users/{id}/nickname 现在必须是 **404**（从前是 200，见 day22-sec-probe.py）。
      ★ 这一组是 Day 22 最值钱的断言：它把「收口」变成可证伪的事实，
        而不是「我改过代码了」。
  [B] 管理端用户接口的**权限矩阵**是否按设计的非对称形状生效
      （user:list/detail 给超管+订单；user:status 只给超管）。
  [C] 仪表盘两个端点的权限与骨架三态。
  [D] L7（订单 VO 补 discountAmount）是否真的落到了两个出口上。

★ 骨架期的「正确长相」是 **200 + body.code = 500**（Service 抛
  UnsupportedOperationException，被 GlobalExceptionHandler 的 Exception 兜底）。
  三态判据（本项目定型）：404 = 路由没生效 / 401·403 = 权限把门 / 200+code=500 = 骨架 OK。

运行：python day22-skeleton-smoke.py
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]

# 满额断言条数（★ 首次跑后按报告 TOTAL 行校准）
# 2026-09-24：初版写 30，实测 28/30（D 组 3 条里 2 条 FAIL）——
#   根因是 D 组拿【管理端订单列表】断言 OrderVO，而那个接口用的是另一个 VO
#   （AdminOrderVO）⇒ 假 FAIL；同时发现 buildDetail 缺一行 setter（并发 Edit 丢写）。
#   改完 D 组 3 条 → 5 条（补「C 端接口」与「恒等式」两条），总数 30 → 32。
EXPECTED = 32

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


def sql1(statement):
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("psql rc=%s: %s" % (r.returncode, (r.stderr or "").strip()[:300]))
    rows = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]
    if not rows:
        raise RuntimeError("psql 返回空输出 —— 多半是 Docker 引擎没起（不是脚本问题）")
    return rows[0]


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


def skeleton(st, j, label):
    """骨架期正确长相：HTTP 200 + body.code = 500。返回 (ok, 人话描述)。"""
    if st == 200 and code_of(j) == 500:
        return True, "HTTP 200 + code 500（骨架占位）"
    return False, "HTTP %s + code %s" % (st, code_of(j))


say("=" * 78)
say("Day 22 骨架 smoke：安全收口 + 权限矩阵 + 骨架三态 + L7")
say("=" * 78)

say("\n[0] 等待应用就绪")
if not wait_ready():
    say("  [FATAL] 应用 150s 内未就绪")
    raise SystemExit(2)
say("  [OK] 应用已就绪")

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

ORDER_ID = int(sql1("SELECT coalesce(min(id), 0) FROM orders"))
DB_DISCOUNT = sql1("SELECT discount_amount FROM orders WHERE id = %d" % ORDER_ID) if ORDER_ID else "N/A"
say("    DB: min(orders.id)=%d  discount_amount=%s" % (ORDER_ID, DB_DISCOUNT))

# ---------------------------------------------------------------- A
say("\n[A] ★ 安全收口：旧端点必须【从 200 变成 404】（漏洞入口被拆掉）")
st, j, raw = api("GET", "/api/users")
check("A1 匿名 GET /api/users -> HTTP 401（仍然要登录，不是公开）", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:80]))

st, j, raw = api("GET", "/api/users", token=DEMO_TOKEN)
check("A2 demo token GET /api/users -> HTTP 404（★ 从前是 200 + 全站口令哈希）",
      st == 404, "实测 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("GET", "/api/users/2", token=DEMO_TOKEN)
check("A3 demo token GET /api/users/{别人} -> HTTP 404（从前 200）",
      st == 404, "实测 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("PUT", "/api/users/2/nickname", token=DEMO_TOKEN, body={"nickname": "x"})
check("A4 demo token PUT /api/users/{别人}/nickname -> HTTP 404（从前 200，能改任何人）",
      st == 404, "实测 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("GET", "/api/users/me", token=DEMO_TOKEN)
ok, desc = skeleton(st, j, "GET /api/users/me")
check("A5 demo token GET /api/users/me -> %s" % desc, ok, desc)

st, j, raw = api("GET", "/api/users/me")
check("A6 匿名 GET /api/users/me -> HTTP 401", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:80]))

st, j, raw = api("PUT", "/api/users/me/nickname", token=DEMO_TOKEN, body={"nickname": "hello"})
ok, desc = skeleton(st, j, "PUT /api/users/me/nickname")
check("A7 demo token PUT /api/users/me/nickname（合法载荷）-> %s" % desc, ok, desc)

# ---------------------------------------------------------------- B
say("\n[B] 管理端用户接口：权限矩阵（非对称形状）+ 骨架三态")
st, j, raw = api("GET", "/api/admin/users")
check("B1 匿名 GET /api/admin/users -> HTTP 401", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:80]))

st, j, raw = api("GET", "/api/admin/users", token=DEMO_TOKEN)
check("B2 ★ C 端 token 打管理端 -> HTTP 403（C 端 token 无 perms，hasAuthority 必失败）",
      st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/users", token=PROD_TOKEN)
check("B3 ★ op_product（无 user:*）-> HTTP 403（★ 反向对照）", st == 403,
      "实测 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("GET", "/api/admin/users", token=ORDER_TOKEN)
ok, desc = skeleton(st, j, "op_order GET /api/admin/users")
check("B4 ★ op_order（有 user:list）-> %s" % desc, ok, desc)

st, j, raw = api("GET", "/api/admin/users", token=ADMIN_TOKEN)
ok, desc = skeleton(st, j, "admin GET /api/admin/users")
check("B5 admin（超管）-> %s" % desc, ok, desc)

st, j, raw = api("GET", "/api/admin/users/1", token=ORDER_TOKEN)
ok, desc = skeleton(st, j, "op_order GET /api/admin/users/{id}")
check("B6 ★ op_order（有 user:detail）-> %s" % desc, ok, desc)

st, j, raw = api("GET", "/api/admin/users/1", token=PROD_TOKEN)
check("B7 op_product GET /api/admin/users/{id} -> HTTP 403（反向对照）", st == 403,
      "实测 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("PUT", "/api/admin/users/1/status", token=ORDER_TOKEN, body={"status": 1})
check("B8 ★★ op_order PUT /{id}/status -> HTTP 403（user:status 只给超管，反向对照）",
      st == 403, "实测 HTTP %s / %s" % (st, raw[:120]))

st, j, raw = api("PUT", "/api/admin/users/1/status", token=ADMIN_TOKEN, body={"status": 1})
ok, desc = skeleton(st, j, "admin PUT /{id}/status")
check("B9 admin PUT /api/admin/users/{id}/status（合法载荷）-> %s" % desc, ok, desc)

st, j, raw = api("PUT", "/api/admin/users/1/status", token=ADMIN_TOKEN, body={"status": 9})
check("B10 ★ 越界状态值 {status:9} -> HTTP 200 + code 400（@Valid 的 @Max 挡下，不是 200+500）",
      st == 200 and code_of(j) == 400, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:100]))

st, j, raw = api("PUT", "/api/admin/users/1/status", token=ADMIN_TOKEN, body={})
check("B11 空载荷 {} -> HTTP 200 + code 400（@NotNull 挡下）",
      st == 200 and code_of(j) == 400, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:100]))

# ---------------------------------------------------------------- C
say("\n[C] 仪表盘：权限（三角色全给）+ 骨架三态")
st, j, raw = api("GET", "/api/admin/dashboard/overview")
check("C1 匿名 GET /api/admin/dashboard/overview -> HTTP 401", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:80]))

for nm, tk in (("admin", ADMIN_TOKEN), ("op_order", ORDER_TOKEN), ("op_product", PROD_TOKEN)):
    st, j, raw = api("GET", "/api/admin/dashboard/overview", token=tk)
    ok, desc = skeleton(st, j, "%s overview" % nm)
    check("C%d %s GET /api/admin/dashboard/overview -> %s"
          % (2 + ["admin", "op_order", "op_product"].index(nm), nm, desc), ok, desc)

st, j, raw = api("GET", "/api/admin/dashboard/overview", token=DEMO_TOKEN)
check("C5 ★ C 端 token 打仪表盘 -> HTTP 403", st == 403,
      "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/dashboard/trend?days=7", token=ADMIN_TOKEN)
ok, desc = skeleton(st, j, "admin trend")
check("C6 admin GET /api/admin/dashboard/trend?days=7 -> %s" % desc, ok, desc)

# ---------------------------------------------------------------- D
say("\n[D] ★ L7：订单详情/列表必须带出 discountAmount（本日已实现，两个出口都要验）")
# ★ L7 的作用域是【C 端两个出口】（OrderDetailVO / OrderVO）。
#   ⚠️ 管理端订单【列表】用的是另一个 VO（AdminOrderVO，由手写 SQL selectAdminOrders 装配），
#      **不在 L7 范围内** —— 本脚本第一版就是拿它断言，得到一条假 FAIL
#      （首行键里根本没有 discountAmount，却有 userId/userNickname ⇒ 一眼看出是别的类）。
#   管理端【详情】则走的是同一个 buildDetail ⇒ 值得顺带验（证明确实共用）。
#   ★ 教训：断言之前先确认「这个接口的出口是哪个 VO」，别按 URL 猜。


def dec_eq(a, b):
    """按 decimal 比较（避开 float 的 0.1 问题与 '0.00' vs '0.0' 的字符串差异）。"""
    try:
        from decimal import Decimal
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:                                             # noqa: BLE001
        return False


if ORDER_ID:
    st, j, raw = api("GET", "/api/orders/%d" % ORDER_ID, token=DEMO_TOKEN)
    d = data_of(j) or {}
    check("D1 C 端订单详情含 discountAmount 键", "discountAmount" in d,
          "键=%s" % sorted(d.keys()))
    check("D2 详情里的 discountAmount 与 DB 逐字节一致（id=%d）" % ORDER_ID,
          dec_eq(d.get("discountAmount"), DB_DISCOUNT),
          "接口=%r  DB=%r" % (d.get("discountAmount"), DB_DISCOUNT))
    check("D3 ★ 恒等式 payAmount = totalAmount - discountAmount（三个数一起断）",
          dec_eq(d.get("payAmount"),
                 (__import__("decimal").Decimal(str(d.get("totalAmount")))
                  - __import__("decimal").Decimal(str(d.get("discountAmount"))))),
          "total=%r pay=%r discount=%r"
          % (d.get("totalAmount"), d.get("payAmount"), d.get("discountAmount")))

    st, j, raw = api("GET", "/api/orders", token=DEMO_TOKEN)
    recs = records_of(j)
    check("D4 C 端订单列表 records[0] 含 discountAmount 键",
          bool(recs) and "discountAmount" in recs[0],
          "首行键=%s" % (sorted(recs[0].keys()) if recs else "N/A"))

    st, j, raw = api("GET", "/api/admin/orders/%d" % ORDER_ID, token=ADMIN_TOKEN)
    check("D5 管理端订单详情（走同一个 buildDetail）也含 discountAmount 键",
          "discountAmount" in (data_of(j) or {}),
          "键=%s" % sorted((data_of(j) or {}).keys()))
else:
    for nm in ("D1 C 端订单详情含 discountAmount 键",
               "D2 详情里的 discountAmount 与 DB 一致",
               "D3 恒等式 pay = total - discount",
               "D4 C 端订单列表 records[0] 含 discountAmount 键",
               "D5 管理端订单详情也含 discountAmount 键"):
        check(nm, False, "库里没有订单，无法验")

# ---------------------------------------------------------------- E
say("\n[E] 老链路没被带坏（C 端基础接口仍活着）")
st, j, raw = api("GET", "/api/products")
check("E1 GET /api/products（公开）-> HTTP 200 + code 200",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/orders", token=DEMO_TOKEN)
check("E2 demo GET /api/orders（我的订单）-> HTTP 200 + code 200",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/cart", token=DEMO_TOKEN)
check("E3 demo GET /api/cart -> HTTP 200 + code 200",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

# ---------------------------------------------------------------- 收尾
say("\n" + "-" * 78)
say("TOTAL: %d / %d 通过，%d 失败" % (PASS, PASS + FAIL, FAIL))
if FAILS:
    say("FAILED:")
    for f in FAILS:
        say("  - %s" % f)
say("VERDICT: %s" % ("OK —— 安全收口生效 + 权限矩阵正确 + 骨架三态正常 + L7 落地"
                     if FAIL == 0 else "有失败项，见上"))
say("-" * 78)

if PASS + FAIL != EXPECTED:
    say("!! 护栏：断言总数 %d != EXPECTED %d —— 有断言被跳过，或 EXPECTED 需校准"
        % (PASS + FAIL, EXPECTED))

with open("day22-skeleton-smoke-report.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(LINES) + "\n")
say("(报告已写入 day22-skeleton-smoke-report.txt)")
