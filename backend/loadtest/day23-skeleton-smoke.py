#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Day 23 骨架 smoke：权限落地 + 13 端点三态 + roles.status 修复证明 + 参数层。

★ 本脚本是【骨架期一次性】的验收。它要回答四个问题：

  [A] **13 条新权限码真的落库了吗，且真的只发给超管吗** —— 后半句是本日最重要的一条：
      admin:create + admin:assign-role 合起来 = 造一个新超管账号；
      role:assign-permission = 给自己所属角色补满任意权限。
      ⇒ 用 op_product / op_order 两个夹具账号做反向对照（只用全权 admin 测 = 什么都证明不了）。
  [B] 13 个端点是否【被路由到】（骨架期正确长相 = HTTP 200 + body.code 500）。
      三态判据（本项目定型）：**404 = 路由没生效 / 401·403 = 权限把门 / 200+code=500 = 骨架 OK**。
  [C] 参数层是否在工作 —— 特别是「null 与 [] 的语义分离」（AssignRolesDTO 的 @NotNull）。
  [D] ★★ 本日最值钱的一组：**AdminMapper.xml 那条修复**（selectPermissionCodesByAdminId
      补 AND r.status = 1）。做法是把 role 2 停用再恢复，然后看 op_product 的权限是否消失；
      同时用【旧 token】打同一端点作为对照 —— 这一对断言同时证明了两件事：
        · 停用角色的权限真的不再下发（修复生效）
        · 已签发的 token 里的权限快照不变（路线① 的正面证据，窗口最长 = token TTL 120min）
  [E] 老链路没被带坏（Day 22 的端点、C 端基础接口）。
  [F] 协议层三态（404 / 405）仍然正确。

⚠️⚠️ **本脚本只在骨架期跑**：实现填完后 B/C 组的 500 会变成 200（断言失效），
    且带写操作的载荷会**真的写库**。实现完成后请改用 `day23-rbac-verify.py`（A–G 组）。

★★ 一个必须分清的分类（首跑就栽在这）：本日验收里混着【两类】端点，正确长相不同 ——
    · **本日新建的 13 个**（Service 全是 TODO）⇒ `200 + code 500`
    · **Day 22 已实现的几个**（dashboard/overview、/api/users/me、/api/admin/users）
      ⇒ `200 + code 200`（它们真的跑完了）
   ⇒ 用 `skeleton()` 判前者、`ok200()` 判后者。混用会产出一堆**假 FAIL**
     （首跑 5 条 FAIL 全部如此，无一真缺陷）。

运行：python day23-skeleton-smoke.py
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

# 满额断言条数（★ 首次跑后按报告 TOTAL 行校准 —— 这道护栏已多次报出「总数不符」）
# 静态清点：A13 + B13 + C4 + D7 + E5 + F2 = 44
# ★ 2026-09-24 首跑 39/44：5 条 FAIL 全是【假 FAIL】，根因同一个 ——
#   D5/D7/E1/E2/E5 打的全是 **Day 22 已实现**的端点（dashboard/overview、
#   /api/users/me、/api/admin/users），它们的正确长相是 **200 + code 200**
#   （真的跑完了），而脚本拿「骨架占位 = 200 + code 500」去判 ⇒ 全部误判。
#   修法：加 ok200() 与 skeleton() 并列，按「本日新建 / 既有已实现」分类断言。
#   ★ 教训与 Day 22 那次（拿 AdminOrderVO 断言 OrderVO）同族：
#     **断言前先确认这个端点/出口是哪一个形态**，别按「同类」猜。
EXPECTED = 44

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


def sql_exec(statement):
    """执行一条写 SQL（不取结果）。"""
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stderr or "").strip()


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


def ok200(st, j, label):
    """【已实现】端点的正确长相：HTTP 200 + body.code = 200。返回 (ok, 人话描述)。

    ★ 为什么要与 skeleton() 分开（本脚本第一版就栽在这——5 条假 FAIL）：
      本日验收里混着【两类】端点 ——
        · 本日新建的 13 个（Service 全是 TODO ⇒ 正确长相 200 + code 500）
        · Day 22 已实现的几个（dashboard/overview、/api/users/me、/api/admin/users
          ⇒ 正确长相 200 + code 200，因为它们真的跑完了）
      第一版拿 skeleton() 去判后者，实测全是 200+200，被打成 5 条 FAIL ——
      而 200+200 恰恰说明那些端点工作正常。
    ⇒ 教训：**写骨架期断言前，先确认这个端点是「本日新建」还是「既有已实现」**。
      两者的正确长相不同，混用只会产出一堆假 FAIL（与 Day 22 那次
      「拿 AdminOrderVO 去断言 OrderVO」是同一种错：断言前没确认出口/形态）。
    """
    if st == 200 and code_of(j) == 200:
        return True, "HTTP 200 + code 200（已实现）"
    return False, "HTTP %s + code %s" % (st, code_of(j))


say("=" * 78)
say("Day 23 骨架 smoke：权限落地 + 13 端点三态 + roles.status 修复证明 + 参数层")
say("=" * 78)

say("\n[0] 等待应用就绪")
if not wait_ready():
    say("  [FATAL] 应用 150s 内未就绪")
    raise SystemExit(2)
say("  [OK] 应用已就绪")

DEMO_TOKEN, m0 = login("/api/auth/login", "demo", "demo123")
ADMIN_TOKEN, m1 = login("/api/auth/admin/login", "admin", "admin123")
ORDER_TOKEN, m2 = login("/api/auth/admin/login", "op_order", "op123456")
PROD_TOKEN, m3 = login("/api/auth/admin/login", "op_product", "prod123456")
for nm, tk, msg in (("demo(C端)", DEMO_TOKEN, m0), ("admin(超管)", ADMIN_TOKEN, m1),
                    ("op_order", ORDER_TOKEN, m2), ("op_product", PROD_TOKEN, m3)):
    say("    login %-14s -> %s" % (nm, "OK" if tk else msg))
if not (DEMO_TOKEN and ADMIN_TOKEN and ORDER_TOKEN and PROD_TOKEN):
    say("  [FATAL] 四个账号必须都能登录（夹具缺失？跑过 06-day17-fixtures.sql 吗）")
    raise SystemExit(2)

# ---------------------------------------------------------------- A
say("\n[A] ★ 13 条 RBAC 权限：落库 + path + 只发超管（反向对照用 op_* 夹具）")

RBAC_WHERE = "(p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')"
a1 = sql1("SELECT count(*) FROM permissions WHERE code LIKE 'admin:%'")
check("A1 DB: admin:* 权限条数 = 6", a1 == "6", "实测 %s" % a1)
a2 = sql1("SELECT count(*) FROM permissions WHERE code LIKE 'role:%'")
check("A2 DB: role:* 权限条数 = 6", a2 == "6", "实测 %s" % a2)
a3 = sql1("SELECT count(*) FROM permissions WHERE code LIKE 'permission:%'")
check("A3 DB: permission:* 权限条数 = 1", a3 == "1", "实测 %s" % a3)
a4 = sql1("SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
          "WHERE rp.role_id = 1 AND %s" % RBAC_WHERE)
check("A4 DB: 超管(role1) 拿到 13 条（复算 6+6+1）", a4 == "13", "实测 %s" % a4)
a5 = sql1("SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
          "WHERE rp.role_id = 2 AND %s" % RBAC_WHERE)
check("A5 ★★ DB: 商品管理员(role2) 拿到 0 条（反向对照 —— 多一条就是越权通道）",
      a5 == "0", "实测 %s" % a5)
a6 = sql1("SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
          "WHERE rp.role_id = 3 AND %s" % RBAC_WHERE)
check("A6 ★★ DB: 订单管理员(role3) 拿到 0 条（反向对照）", a6 == "0", "实测 %s" % a6)
a7 = sql1("SELECT count(*) FROM permissions WHERE (code LIKE 'admin:%' OR code LIKE 'role:%' "
          "OR code LIKE 'permission:%') AND path NOT LIKE '/api/admin/%'")
check("A7 DB: RBAC 权限里 path 未指向 /api/admin/ 的条数 = 0（权限表不说谎）",
      a7 == "0", "实测 %s" % a7)

st, j, raw = api("GET", "/api/admin/roles")
check("A8 匿名 GET /api/admin/roles -> HTTP 401", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:80]))

st, j, raw = api("GET", "/api/admin/roles", token=PROD_TOKEN)
check("A9 ★★ op_product(PRODUCT_ADMIN) 打 /api/admin/roles -> HTTP 403（反向对照）",
      st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/admins", token=ORDER_TOKEN)
check("A10 ★★ op_order(ORDER_ADMIN) 打 /api/admin/admins -> HTTP 403（反向对照）",
      st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/permissions", token=PROD_TOKEN)
check("A11 op_product 打 /api/admin/permissions -> HTTP 403", st == 403,
      "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("PUT", "/api/admin/roles/2/permissions", token=ORDER_TOKEN,
                 body={"permissionIds": [1]})
check("A12 ★ op_order 打 PUT /api/admin/roles/{id}/permissions -> HTTP 403（自我提权通道已关）",
      st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/admins", token=DEMO_TOKEN)
check("A13 ★ C 端 token 打管理端 -> HTTP 403（C 端 token 无 perms，hasAuthority 必失败）",
      st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))

# ---------------------------------------------------------------- B
say("\n[B] ★ 13 个端点是否被路由（超管 token + 合法载荷；骨架期正确长相 200+code=500）")
# ★ 载荷必须【合法】：@Valid 跑在 @PreAuthorize 之前（Day 07 定型的坑）——
#   非法载荷永远先撞 400，与有没有权限无关。
B_CASES = [
    ("B1  GET    /api/admin/admins",               "GET",    "/api/admin/admins",               None),
    ("B2  GET    /api/admin/admins/1",             "GET",    "/api/admin/admins/1",             None),
    ("B3  POST   /api/admin/admins",               "POST",   "/api/admin/admins",
     {"username": "d23probe", "password": "d23pass123", "nickname": "骨架探针"}),
    ("B4  PUT    /api/admin/admins/1",             "PUT",    "/api/admin/admins/1",
     {"nickname": "骨架探针"}),
    ("B5  DELETE /api/admin/admins/1",             "DELETE", "/api/admin/admins/1",             None),
    ("B6  PUT    /api/admin/admins/1/roles",       "PUT",    "/api/admin/admins/1/roles",
     {"roleIds": [1]}),
    ("B7  GET    /api/admin/roles",                "GET",    "/api/admin/roles",                None),
    ("B8  GET    /api/admin/roles/1",              "GET",    "/api/admin/roles/1",              None),
    ("B9  POST   /api/admin/roles",                "POST",   "/api/admin/roles",
     {"name": "骨架探针角色", "code": "D23_PROBE", "description": "骨架期探针"}),
    ("B10 PUT    /api/admin/roles/1",              "PUT",    "/api/admin/roles/1",
     {"name": "骨架探针"}),
    ("B11 DELETE /api/admin/roles/1",              "DELETE", "/api/admin/roles/1",              None),
    ("B12 PUT    /api/admin/roles/1/permissions",  "PUT",    "/api/admin/roles/1/permissions",
     {"permissionIds": [1]}),
    ("B13 GET    /api/admin/permissions",          "GET",    "/api/admin/permissions",          None),
]
for label, method, path, body in B_CASES:
    st, j, raw = api(method, path, token=ADMIN_TOKEN, body=body)
    ok, desc = skeleton(st, j, label)
    check("%s -> %s" % (label, desc), ok, "%s / %s" % (desc, raw[:100]))

# ---------------------------------------------------------------- C
say("\n[C] 参数层：@Valid 在入口就把非法载荷挡成 400（★ 尤其是 null 与 [] 的语义分离）")
st, j, raw = api("POST", "/api/admin/admins", token=ADMIN_TOKEN, body={})
check("C1 POST /api/admin/admins 空载荷 {} -> 200 + code 400（@NotBlank）",
      st == 200 and code_of(j) == 400, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:90]))

st, j, raw = api("POST", "/api/admin/roles", token=ADMIN_TOKEN,
                 body={"name": "x", "code": "lower_case"})
check("C2 POST /api/admin/roles 小写 code -> 200 + code 400（@Pattern，防拼出坏 ROLE_ 前缀）",
      st == 200 and code_of(j) == 400, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:90]))

st, j, raw = api("PUT", "/api/admin/admins/1/roles", token=ADMIN_TOKEN, body={})
check("C3 ★★ PUT /{id}/roles 省略 roleIds（null）-> 200 + code 400 —— "
      "★ 挡住「前端漏传 = 静默清空角色」",
      st == 200 and code_of(j) == 400, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:90]))

st, j, raw = api("PUT", "/api/admin/roles/1/permissions", token=ADMIN_TOKEN, body={})
check("C4 ★★ PUT /{id}/permissions 省略 permissionIds（null）-> 200 + code 400（同上）",
      st == 200 and code_of(j) == 400, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:90]))

# ---------------------------------------------------------------- D
say("\n[D] ★★ roles.status 修复证明（停用 role 2 → 权限码应消失）+ 路线① 证据（旧 token 不变）")
say("    ★ 为什么这组能证明修复：修复前 selectPermissionCodesByAdminId 只判 p.status，")
say("      停用角色【不挡权限码】⇒ 新 token 也会有 dashboard:overview ⇒ 会是 200+500 而非 403。")

ROLE2_STATUS_BEFORE = sql1("SELECT status FROM roles WHERE id = 2")
check("D1 DB: role 2(商品管理员) 初始 status = 1（停用前基线）",
      ROLE2_STATUS_BEFORE == "1", "实测 %s" % ROLE2_STATUS_BEFORE)

try:
    rc, err = sql_exec("UPDATE roles SET status = 0 WHERE id = 2")
    check("D2 DB: 把 role 2 停用（status 0）执行成功", rc == 0, "rc=%s err=%s" % (rc, err[:200]))
    if rc != 0:
        raise RuntimeError("停用失败，跳过 D 组剩余断言")

    NEW_PROD_TOKEN, msg = login("/api/auth/admin/login", "op_product", "prod123456")
    check("D3 停用角色后，op_product 仍能登录（账号 status 未被改，只有角色被停用）",
          bool(NEW_PROD_TOKEN), "登录失败：%s" % msg)

    if NEW_PROD_TOKEN:
        st, j, raw = api("GET", "/api/admin/dashboard/overview", token=NEW_PROD_TOKEN)
        check("D4 ★★ 【新 token】打 dashboard/overview -> HTTP 403 —— "
              "停用角色的权限码真的不再下发（这就是那条修复生效的证据）",
              st == 403, "实测 HTTP %s code %s / %s（若为 200+500 ⇒ 修复没生效！）"
              % (st, code_of(j), raw[:90]))
    else:
        check("D4 ★★ 【新 token】打 dashboard/overview -> HTTP 403", False, "无法登录，跳过")

    # ★ 为什么用 dashboard/overview 来验「旧 token 权限不变」：
    #   op_product 只持有 product:*（Day 07）+ dashboard:*（Day 22），本日这 13 条
    #   它一条都没有（A5 已证）⇒ 想验「旧 token 里的权限快照还在」，只能用它确实
    #   持有的权限。dashboard/overview 最直接，且它是【Day 22 已实现】的端点
    #   ⇒ 正确长相 200 + code 200（真的跑完了 —— 比 200+500 更强）。
    st, j, raw = api("GET", "/api/admin/dashboard/overview", token=PROD_TOKEN)
    ok, desc = ok200(st, j, "旧 token")
    check("D5 ★★ 【旧 token】打同一端点 -> %s —— 已签发的 token 里权限快照【不变】，"
          "且因该端点已实现，它还能真的跑完" % desc,
          ok, "实测 %s（路线①：窗口最长 = token TTL 120min）" % desc)

finally:
    rc, err = sql_exec("UPDATE roles SET status = %s WHERE id = 2" % ROLE2_STATUS_BEFORE)
    RESTORED = sql1("SELECT status FROM roles WHERE id = 2")
    check("D6 DB: role 2 的 status 已被恢复成 %s（高水位线清理）" % ROLE2_STATUS_BEFORE,
          rc == 0 and RESTORED == ROLE2_STATUS_BEFORE,
          "rc=%s 现值=%s err=%s" % (rc, RESTORED, err[:150]))

    RESTOKEN, msg = login("/api/auth/admin/login", "op_product", "prod123456")
    if RESTOKEN:
        st, j, raw = api("GET", "/api/admin/dashboard/overview", token=RESTOKEN)
        ok, desc = ok200(st, j, "恢复后重新登录")
        check("D7 恢复角色后再登录 -> %s（权限回来了）" % desc, ok, desc)
    else:
        check("D7 恢复角色后再登录 -> 已实现", False, "登录失败：%s" % msg)

# ---------------------------------------------------------------- E
say("\n[E] 老链路没被带坏")
# ★ E 组的端点【全部是已实现的】（Day 22 或更早）⇒ 正确长相一律 200 + code 200。
#   ⚠️ 这里用 ok200() 而不是 skeleton()：第一版用错，白挨了 3 条假 FAIL。
st, j, raw = api("GET", "/api/admin/users", token=ADMIN_TOKEN)
ok, desc = ok200(st, j, "admin GET /api/admin/users（Day 22 端点）")
check("E1 Day 22 的 /api/admin/users -> %s" % desc, ok, desc)

st, j, raw = api("GET", "/api/admin/dashboard/overview", token=ADMIN_TOKEN)
ok, desc = ok200(st, j, "admin overview（Day 22 端点）")
check("E2 Day 22 的 /api/admin/dashboard/overview -> %s" % desc, ok, desc)

st, j, raw = api("GET", "/api/products")
check("E3 GET /api/products（公开）-> HTTP 200 + code 200",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/orders", token=DEMO_TOKEN)
check("E4 demo GET /api/orders（我的订单）-> HTTP 200 + code 200",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/users/me", token=DEMO_TOKEN)
ok, desc = ok200(st, j, "demo GET /api/users/me（Day 22 收口后的端点）")
check("E5 Day 22 收口后的 /api/users/me -> %s" % desc, ok, desc)

# ---------------------------------------------------------------- F
say("\n[F] 协议层三态（404 / 405）仍然正确")
st, j, raw = api("GET", "/api/admin/no-such-thing", token=ADMIN_TOKEN)
check("F1 带 token 打不存在的路径 -> HTTP 404（不是 200+500）", st == 404,
      "实测 HTTP %s / %s" % (st, raw[:90]))

st, j, raw = api("POST", "/api/admin/permissions", token=ADMIN_TOKEN, body={"x": 1})
check("F2 ★ POST /api/admin/permissions（只读端点）-> HTTP 405 —— "
      "「路径在、方法不支持」才是「只读」的准确表达",
      st == 405, "实测 HTTP %s / %s" % (st, raw[:90]))

# ---------------------------------------------------------------- 收尾
say("\n" + "-" * 78)
say("TOTAL: %d / %d 通过，%d 失败" % (PASS, PASS + FAIL, FAIL))
if FAILS:
    say("FAILED:")
    for f in FAILS:
        say("  - %s" % f)
say("VERDICT: %s" % ("OK —— 13 条权限只发超管 + 13 端点已路由 + 参数层生效 + roles.status 修复生效"
                     if FAIL == 0 else "有失败项，见上"))
say("-" * 78)

if PASS + FAIL != EXPECTED:
    say("!! 护栏：断言总数 %d != EXPECTED %d —— 有断言被跳过，或 EXPECTED 需校准"
        % (PASS + FAIL, EXPECTED))

with open("day23-skeleton-smoke-report.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(LINES) + "\n")
say("(报告已写入 day23-skeleton-smoke-report.txt)")
