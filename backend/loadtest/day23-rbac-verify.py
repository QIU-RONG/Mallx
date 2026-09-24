#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Day 23 验收（A–G 七组）：RBAC 权限管理（管理员 / 角色 / 权限）。

★ 与 day23-skeleton-smoke.py 的分工：
    smoke   = 骨架期门禁（期望 200 + code 500；实现填完后它必然失效）
    本脚本  = **实现期验收**（期望真数据），是 RBAC 的长期回归断言。
  ⇒ 两个脚本的期望值【方向相反】，别把 smoke 的断言搬过来。

★★ 本日断言写法的总纲（路线①的直接后果）：
   权限是签进 token 的。所以所有「改了权限之后应该生效」的断言，都必须
   【重新登录】拿一个新 token 再打 —— 用旧 token 打，只会得到「权限还在」的假象。
   E 组把这一对【并行断言】（旧 token 仍有 / 新 token 已无）本身当成验收对象。

七组：
  [A] 权限落地 —— 13 条码 + path/method 逐字对齐 + 只发超管 + op_product/op_order 反向对照 403。
  [B] 管理员 CRUD —— 分页夹紧双判 / keyword 括号（★ 造「昵称命中但 status=0」的靶子）/
      详情【无 password 键】/ ★ create 后【新密码能登录】（证 encoder 生效）/ 撞 UNIQUE → 400。
  [C] 角色 CRUD —— 列表 / 详情含 permissionIds / code 撞 → 400 / 护栏①（停用+删除 SUPER_ADMIN 都 400）。
  [D] 两个分配 —— 全量替换幂等 / 空数组 = 清空 / 不存在的 id → 400（不是 500）/
      护栏②（减超管权限 → 400）/ 护栏③（清空自己的角色 → 400）/ 物理删两张表一起断。
  [E] ★ roles.status 修复证明 —— 停用角色 → 重登录 → 权限码消失；旧 token 不变。
  [F] 权限只读 —— 不分页（条数 == 全表行数）/ type 过滤 / POST·PUT·DELETE 全 405。
  [G] 基线还原 —— 5 张表回基线 + 超管仍有 13 条（清理没伤到超管）。

★★ 三条纪律（本项目反复踩过）：
  ① 断言对着【设计】写，不对着库的默认行为写；脚本与设计打架时改脚本。
  ② 造的数据必须【高水位线清理】，跑完断言【基线还原】——否则 M1 的计数断言必红。
  ③ 清理写在 finally 里：断言中途炸了也要清干净。

运行：python day23-rbac-verify.py
"""
import json
import os
import re
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 满额断言条数（★ 首次跑后按报告 TOTAL 行校准 —— 这道护栏已多次报出「总数不符」）
# 静态清点：A 21 + B 18 + C 13 + D 19 + E 7 + F 7 + G 6 = 91
EXPECTED = 91

# ---- 夹具：一律用【无下划线】前缀，免得 LIKE 里的 _ 变成通配符 ----
U_MARK = "d23tmp"        # username LIKE 'd23tmp%'
R_MARK = "D23TMP"        # roles.code LIKE 'D23TMP%'
KW = "D23KW"             # keyword 的靶子关键字
TMP_PWD = "D23Tmp123"    # 临时管理员口令（长度过 6..64 校验）

# ---- 13 条权限的期望字面量（与 13-day23-permissions.sql 逐字一致）----
RBAC_PERMS = [
    ("admin:list",             "/api/admin/admins",              "GET"),
    ("admin:detail",           "/api/admin/admins/*",            "GET"),
    ("admin:create",           "/api/admin/admins",              "POST"),
    ("admin:update",           "/api/admin/admins/*",            "PUT"),
    ("admin:delete",           "/api/admin/admins/*",            "DELETE"),
    ("admin:assign-role",      "/api/admin/admins/*/roles",      "PUT"),
    ("role:list",              "/api/admin/roles",               "GET"),
    ("role:detail",            "/api/admin/roles/*",             "GET"),
    ("role:create",            "/api/admin/roles",               "POST"),
    ("role:update",            "/api/admin/roles/*",             "PUT"),
    ("role:delete",            "/api/admin/roles/*",             "DELETE"),
    ("role:assign-permission", "/api/admin/roles/*/permissions", "PUT"),
    ("permission:list",        "/api/admin/permissions",         "GET"),
]
PERM_ID_LIST = "(" + ",".join(str(26 + i) for i in range(13)) + ")"

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


def sql_many(stmt):
    return _psql(stmt)


def sql_exec(stmt):
    return _psql(stmt, allow_empty=True)


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
    if isinstance(d, dict):
        return d.get("records") or []
    if isinstance(d, list):
        return d
    return []


def total_of(j):
    d = data_of(j)
    return (d.get("total") if isinstance(d, dict) else None)


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


# ============================================================ 护栏
def guard_implemented():
    """★ 骨架期的坑（Day 18 误跑真写库）：不判「占位文本在不在」，判「内容是否合法」。"""
    bad = []
    js = [
        "mall-admin/src/main/java/com/mallx/admin/service/impl/AdminAccountManageServiceImpl.java",
        "mall-admin/src/main/java/com/mallx/admin/service/impl/RoleManageServiceImpl.java",
        "mall-admin/src/main/java/com/mallx/admin/service/impl/PermissionQueryServiceImpl.java",
    ]
    for rel in js:
        with open(os.path.join(ROOT, "mallx", rel), encoding="utf-8") as fh:
            if "UnsupportedOperationException" in fh.read():
                bad.append("Java 占位仍在: " + os.path.basename(rel))
    xml = os.path.join(ROOT, "mallx/mall-admin/src/main/resources/mapper/AdminRbacMapper.xml")
    with open(xml, encoding="utf-8") as fh:
        txt = fh.read()
    n = 0
    for m in re.finditer(r"<(select|insert|delete|update)\b[^>]*\bid=\"(\w+)\"[^>]*>(.*?)</\1>", txt, re.S):
        n += 1
        if not re.match(r"(?is)^(select|with|insert|update|delete)\b", m.group(3).strip()):
            bad.append("XML 语句体为空/非法: %s" % m.group(2))
    if n != 11:
        bad.append("AdminRbacMapper 语句数 %d != 11" % n)
    return bad


# ============================================================ 清理（高水位线）
def cleanup():
    # 顺序即语义：先两张关联表（它们是引用方），再 roles / admins（被引用方）
    sql_exec("DELETE FROM admin_roles WHERE admin_id IN "
             "(SELECT id FROM admins WHERE username LIKE '%s%%')" % U_MARK)
    sql_exec("DELETE FROM admin_roles WHERE role_id IN "
             "(SELECT id FROM roles WHERE code LIKE '%s%%')" % R_MARK)
    sql_exec("DELETE FROM role_permissions WHERE role_id IN "
             "(SELECT id FROM roles WHERE code LIKE '%s%%')" % R_MARK)
    sql_exec("DELETE FROM admins WHERE username LIKE '%s%%'" % U_MARK)
    sql_exec("DELETE FROM roles  WHERE code     LIKE '%s%%'" % R_MARK)


def baseline():
    return {
        "admins": sql_int("SELECT count(*) FROM admins"),
        "roles": sql_int("SELECT count(*) FROM roles"),
        "admin_roles": sql_int("SELECT count(*) FROM admin_roles"),
        "role_permissions": sql_int("SELECT count(*) FROM role_permissions"),
        "permissions": sql_int("SELECT count(*) FROM permissions"),
    }


def rbac_count(role_id):
    return sql_int(
        "SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
        "WHERE rp.role_id = %d AND (p.code LIKE 'admin:%%' OR p.code LIKE 'role:%%' "
        "OR p.code LIKE 'permission:%%')" % role_id)


# ============================================================ 主流程
say("=" * 78)
say("Day 23 验收：RBAC 权限管理（A–G 七组）")
say("=" * 78)

say("\n[0] 护栏与准备")
bad = guard_implemented()
if bad:
    say("  [FATAL] 实现没填完，拒绝执行（拿半成品跑验收，报告里分不清「没写」还是「写错」）：")
    for b in bad:
        say("      - %s" % b)
    raise SystemExit(3)
say("  [OK] 13 处实现与 11 条 SQL 均已落地（无占位 / 无空语句体 / 语句数 11）")

if not wait_ready():
    say("  [FATAL] 应用 150s 内未就绪")
    raise SystemExit(2)
say("  [OK] 应用已就绪")

n_rbac = sql_int("SELECT count(*) FROM permissions WHERE id IN %s" % PERM_ID_LIST)
if n_rbac != 13:
    say("  [FATAL] 权限码只有 %d / 13 条落库 ⇒ 先跑 day23-perm-apply.py，再跑本脚本" % n_rbac)
    raise SystemExit(3)

cleanup()
BASE = baseline()
say("  基线: %s" % BASE)

DEMO_TOKEN, m0 = login("/api/auth/login", "demo", "demo123")
ADMIN_TOKEN, m1 = login("/api/auth/admin/login", "admin", "admin123")
ORDER_TOKEN, m2 = login("/api/auth/admin/login", "op_order", "op123456")
PROD_TOKEN, m3 = login("/api/auth/admin/login", "op_product", "prod123456")
for nm, tk, msg in (("demo(C端)", DEMO_TOKEN, m0), ("admin(超管)", ADMIN_TOKEN, m1),
                    ("op_order", ORDER_TOKEN, m2), ("op_product", PROD_TOKEN, m3)):
    say("    login %-14s -> %s" % (nm, "OK" if tk else msg))
if not (DEMO_TOKEN and ADMIN_TOKEN and ORDER_TOKEN and PROD_TOKEN):
    say("  [FATAL] 四个账号必须都能登录")
    raise SystemExit(2)

ADMIN_ID = sql_int("SELECT id FROM admins WHERE username = 'admin'")
say("    admin.id=%d" % ADMIN_ID)

try:
    # ---------------------------------------------------------- A 权限落地
    say("\n[A] 权限落地（13 条 + 只发超管 + 反向对照）")
    check("A1 13 条新权限码全部落库", n_rbac == 13, "实测 %d" % n_rbac)

    rows = sql_many("SELECT code || '|' || path || '|' || method FROM permissions "
                    "WHERE id IN %s ORDER BY id" % PERM_ID_LIST)
    for i, (code, path, method) in enumerate(RBAC_PERMS):
        got = rows[i] if i < len(rows) else "<缺失>"
        check("A%d %s -> %s %s" % (i + 2, code, method, path),
              got == "%s|%s|%s" % (code, path, method), "实测 %s" % got)

    r1 = rbac_count(1)
    check("A15 SUPER_ADMIN(role 1) 拿到全部 13 条", r1 == 13, "实测 %d" % r1)
    r2 = rbac_count(2)
    check("A16 ★ 反向对照 PRODUCT_ADMIN(role 2) 拿到 0 条", r2 == 0, "实测 %d" % r2)
    r3 = rbac_count(3)
    check("A17 ★ 反向对照 ORDER_ADMIN(role 3) 拿到 0 条", r3 == 0, "实测 %d" % r3)

    st, j, _ = api("GET", "/api/admin/roles", token=PROD_TOKEN)
    check("A18 op_product 打 /api/admin/roles -> HTTP 403", st == 403, "实测 HTTP %s" % st)

    st, j, _ = api("GET", "/api/admin/admins", token=ORDER_TOKEN)
    check("A19 op_order 打 /api/admin/admins -> HTTP 403", st == 403, "实测 HTTP %s" % st)

    st, j, _ = api("GET", "/api/admin/roles", token=ADMIN_TOKEN)
    check("A20 超管打 /api/admin/roles -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("GET", "/api/admin/roles")
    check("A21 匿名打 /api/admin/roles -> HTTP 401", st == 401, "实测 HTTP %s" % st)

    # ---------------------------------------------------------- B 管理员 CRUD
    say("\n[B] 管理员 CRUD")
    st, j, raw = api("POST", "/api/admin/admins", token=ADMIN_TOKEN,
                     body={"username": U_MARK + "a1", "password": TMP_PWD, "nickname": KW + "_a1"})
    A1_ID = data_of(j)
    check("B1 POST 建管理员 -> HTTP 200 + code 200 + 返回 id",
          st == 200 and code_of(j) == 200 and isinstance(A1_ID, int), "实测 HTTP %s code %s data %s"
          % (st, code_of(j), A1_ID))
    if not isinstance(A1_ID, int):
        raise SystemExit("B1 拿不到新管理员 id，后续无法继续")

    # ⚠️ 不能断言「$2 开头」：本项目用的是 DelegatingPasswordEncoder
    #    （SecurityConfig#passwordEncoder → PasswordEncoderFactories.createDelegatingPasswordEncoder()）
    #    ⇒ encode() 产出的形状是【{bcrypt}$2a$10$...】，带 {id} 前缀。
    #    这也正是种子里那句 {noop}admin123 能被 matches 认出来的原因（同一个委托编码器）。
    pwd_stored = sql1("SELECT substr(password, 1, 16) FROM admins WHERE id = %d" % A1_ID)
    check("B2 库里 password 是编码后的（{bcrypt}$2a$…）而不是 {noop} 明文",
          pwd_stored.startswith("{bcrypt}") and not pwd_stored.startswith("{noop}"),
          "实测前缀 %s" % pwd_stored)

    NEW_TOKEN, msg = login("/api/auth/admin/login", U_MARK + "a1", TMP_PWD)
    check("B3 ★ create 后【新密码能登录】（encode/matches 同一套算法的真证明）",
          NEW_TOKEN is not None, "登录失败：%s" % msg)

    st, j, _ = api("POST", "/api/admin/admins", token=ADMIN_TOKEN,
                   body={"username": U_MARK + "a1", "password": TMP_PWD})
    check("B4 重复 username -> code 400（走 ON CONFLICT，不是 500）",
          code_of(j) == 400, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("GET", "/api/admin/admins/%d" % A1_ID, token=ADMIN_TOKEN)
    check("B5 GET 管理员详情 -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    d = data_of(j) or {}
    check("B6 ★★ 详情响应里【没有 password 键】（不是 \"password\": null）",
          "password" not in d, "实测键: %s" % sorted(d.keys()))

    check("B7 详情 roleIds / roleCodes 是空数组（新账号默认无角色）",
          d.get("roleIds") == [] and d.get("roleCodes") == [],
          "实测 roleIds=%s roleCodes=%s" % (d.get("roleIds"), d.get("roleCodes")))

    # ★ 括号判据的靶子：禁用 + 昵称命中（只有 .and() 包括号才能把它挡在外面）
    sql_exec("INSERT INTO admins (username, password, nickname, status, created_at, updated_at) "
             "VALUES ('%sb1', '{noop}%s', '%s_b1', 0, now(), now())" % (U_MARK, TMP_PWD, KW))
    B1_ID = sql_int("SELECT id FROM admins WHERE username = '%sb1'" % U_MARK)
    say("    夹具: %sa1(启用, 昵称命中, id=%d) / %sb1(★禁用, 昵称命中, id=%d) —— 后者是括号判据的靶子"
        % (U_MARK, A1_ID, U_MARK, B1_ID))

    st, j, _ = api("GET", "/api/admin/admins?keyword=%s" % KW, token=ADMIN_TOKEN)
    check("B8 不传 status 的列表：keyword 命中【启用 + 禁用】两行（禁用不是删除）",
          total_of(j) == 2, "实测 total=%s" % total_of(j))

    st, j, _ = api("GET", "/api/admin/admins?keyword=%s&status=0" % KW, token=ADMIN_TOKEN)
    check("B9 status=0 过滤 -> 只剩那行禁用的", total_of(j) == 1, "实测 total=%s" % total_of(j))

    st, j, _ = api("GET", "/api/admin/admins?keyword=%s&status=1" % KW, token=ADMIN_TOKEN)
    recs = records_of(j)
    names = [r.get("username") for r in recs]
    check("B10 ★★ 括号正确性：keyword + status=1 时，「昵称命中但已禁用」的行【不许出现】",
          total_of(j) == 1 and (U_MARK + "b1") not in names, "实测 total=%s names=%s"
          % (total_of(j), names))

    # ⚠️ 这里必须用【username 字符串】而不是 B1_ID：目标是「命中 username 列」
    #    （拿 id 当 keyword 是个陷阱 —— id 是数字，username/nickname 里都不含它，必然 0 行）。
    st, j, _ = api("GET", "/api/admin/admins?keyword=%sb1" % U_MARK, token=ADMIN_TOKEN)
    check("B11 keyword 命中 username 列（keyword=%sb1 -> 1 行）" % U_MARK,
          total_of(j) == 1, "实测 total=%s" % total_of(j))

    st, j, _ = api("GET", "/api/admin/admins?size=1000", token=ADMIN_TOKEN)
    check("B12 夹紧上限：size=1000 -> size 字段被夹到 100",
          (data_of(j) or {}).get("size") == 100, "实测 size=%s" % (data_of(j) or {}).get("size"))

    st, j, _ = api("GET", "/api/admin/admins?size=-1", token=ADMIN_TOKEN)
    check("B13 夹紧下限：size=-1 -> size 字段被夹到 1（不是 100，更不是全表）",
          (data_of(j) or {}).get("size") == 1, "实测 size=%s" % (data_of(j) or {}).get("size"))

    st, j, _ = api("PUT", "/api/admin/admins/%d" % A1_ID, token=ADMIN_TOKEN,
                   body={"nickname": KW + "_a1_new"})
    nk = sql1("SELECT nickname FROM admins WHERE id = %d" % A1_ID)
    check("B14 PUT 改昵称 -> HTTP 200 + 库里已变", st == 200 and code_of(j) == 200
          and nk == KW + "_a1_new", "实测 HTTP %s code %s db=%s" % (st, code_of(j), nk))

    st, j, _ = api("PUT", "/api/admin/admins/%d" % A1_ID, token=ADMIN_TOKEN, body={})
    check("B15 PUT 没有任何字段 -> code 400（不发出空 UPDATE）",
          code_of(j) == 400, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/99999999", token=ADMIN_TOKEN,
                   body={"nickname": "whatever"})
    check("B16 PUT 不存在的 id（合法载荷）-> code 404",
          code_of(j) == 404, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/%d" % ADMIN_ID, token=ADMIN_TOKEN, body={"status": 0})
    st_db = sql1("SELECT status FROM admins WHERE id = %d" % ADMIN_ID)
    check("B17 ★ 护栏③ 停用【自己】-> code 400，且库里 status 未变",
          code_of(j) == 400 and st_db == "1", "实测 code %s db.status=%s" % (code_of(j), st_db))

    st, j, _ = api("DELETE", "/api/admin/admins/99999999", token=ADMIN_TOKEN)
    check("B18 DELETE 不存在的 id -> code 404", code_of(j) == 404,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    # ---------------------------------------------------------- C 角色 CRUD
    say("\n[C] 角色 CRUD + 护栏①")
    st, j, _ = api("POST", "/api/admin/roles", token=ADMIN_TOKEN,
                   body={"name": "D23 临时角色一", "code": R_MARK + "R1", "description": "验收用"})
    R1_ID = data_of(j)
    check("C1 POST 建角色 -> HTTP 200 + 返回 id",
          st == 200 and code_of(j) == 200 and isinstance(R1_ID, int),
          "实测 HTTP %s code %s data %s" % (st, code_of(j), R1_ID))
    if not isinstance(R1_ID, int):
        raise SystemExit("C1 拿不到角色 id，后续无法继续")

    st, j, _ = api("POST", "/api/admin/roles", token=ADMIN_TOKEN,
                   body={"name": "重复", "code": R_MARK + "R1"})
    check("C2 重复 code -> code 400", code_of(j) == 400,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("GET", "/api/admin/roles?keyword=%s" % R_MARK, token=ADMIN_TOKEN)
    check("C3 列表 keyword 命中 name/code -> 至少 1 行", (total_of(j) or 0) >= 1,
          "实测 total=%s" % total_of(j))

    st, j, _ = api("GET", "/api/admin/roles?size=1000", token=ADMIN_TOKEN)
    check("C4 夹紧上限：size=1000 -> size 字段 100",
          (data_of(j) or {}).get("size") == 100, "实测 size=%s" % (data_of(j) or {}).get("size"))

    st, j, _ = api("GET", "/api/admin/roles/%d" % R1_ID, token=ADMIN_TOKEN)
    d = data_of(j) or {}
    check("C5 角色详情含 permissionIds + permissionCodes（新角色为空数组）",
          st == 200 and d.get("permissionIds") == [] and d.get("permissionCodes") == [],
          "实测 HTTP %s permIds=%s permCodes=%s" % (st, d.get("permissionIds"), d.get("permissionCodes")))

    st, j, _ = api("PUT", "/api/admin/roles/%d" % R1_ID, token=ADMIN_TOKEN,
                   body={"name": "D23 临时角色一改名"})
    nm = sql1("SELECT name FROM roles WHERE id = %d" % R1_ID)
    check("C6 PUT 改角色名 -> HTTP 200 + 库里已变",
          st == 200 and code_of(j) == 200 and nm == "D23 临时角色一改名",
          "实测 HTTP %s db.name=%s" % (st, nm))

    st, j, _ = api("PUT", "/api/admin/roles/99999999", token=ADMIN_TOKEN, body={"name": "x"})
    check("C7 PUT 不存在的角色 id -> code 404", code_of(j) == 404,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    SUPER_ID = sql_int("SELECT id FROM roles WHERE code = 'SUPER_ADMIN'")
    st, j, _ = api("PUT", "/api/admin/roles/%d" % SUPER_ID, token=ADMIN_TOKEN, body={"status": 0})
    super_status = sql1("SELECT status FROM roles WHERE id = %d" % SUPER_ID)
    check("C8 ★ 护栏① 停用 SUPER_ADMIN -> code 400，且库里 status 未变",
          code_of(j) == 400 and super_status == "1",
          "实测 code %s db.status=%s" % (code_of(j), super_status))

    st, j, _ = api("DELETE", "/api/admin/roles/%d" % SUPER_ID, token=ADMIN_TOKEN)
    check("C9 ★ 护栏① 删除 SUPER_ADMIN -> code 400", code_of(j) == 400,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("POST", "/api/admin/roles", token=ADMIN_TOKEN,
                   body={"name": "D23 临时角色二", "code": R_MARK + "R2"})
    R2_ID = data_of(j)
    check("C10 POST 建第二个角色 -> HTTP 200 + 返回 id",
          st == 200 and isinstance(R2_ID, int), "实测 HTTP %s data %s" % (st, R2_ID))

    st, j, _ = api("DELETE", "/api/admin/roles/99999999", token=ADMIN_TOKEN)
    check("C11 DELETE 不存在的角色 id -> code 404", code_of(j) == 404,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    check("C12 SUPER_ADMIN 仍在且 status=1（护栏① 两次拒绝都没写坏数据）",
          super_status == "1" and rbac_count(SUPER_ID) == 13,
          "实测 status=%s rbac=%d" % (super_status, rbac_count(SUPER_ID)))

    st, j, _ = api("POST", "/api/admin/roles", token=ADMIN_TOKEN,
                   body={"name": "D23 临时角色E", "code": R_MARK + "RE"})
    RE_ID = data_of(j)
    check("C13 POST 建 E 组用的角色 -> HTTP 200 + 返回 id",
          st == 200 and isinstance(RE_ID, int), "实测 HTTP %s data %s" % (st, RE_ID))

    # ---------------------------------------------------------- D 两个分配
    say("\n[D] 两个分配（全量替换）+ 护栏②③")
    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % A1_ID, token=ADMIN_TOKEN,
                   body={"roleIds": [R1_ID, R2_ID]})
    check("D1 PUT admins/{id}/roles [r1,r2] -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    n = sql_int("SELECT count(*) FROM admin_roles WHERE admin_id = %d" % A1_ID)
    check("D2 库里 admin_roles 该管理员有 2 行", n == 2, "实测 %d 行" % n)

    st, j, _ = api("GET", "/api/admin/admins/%d" % A1_ID, token=ADMIN_TOKEN)
    got_ids = sorted((data_of(j) or {}).get("roleIds") or [])
    check("D3 详情 roleIds 回显 == [r1,r2]", got_ids == sorted([R1_ID, R2_ID]),
          "实测 %s" % got_ids)

    api("PUT", "/api/admin/admins/%d/roles" % A1_ID, token=ADMIN_TOKEN,
        body={"roleIds": [R1_ID, R2_ID]})
    n = sql_int("SELECT count(*) FROM admin_roles WHERE admin_id = %d" % A1_ID)
    check("D4 ★ 幂等：重复提交同一份集合 -> 仍是 2 行（不是 4 行）", n == 2, "实测 %d 行" % n)

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % A1_ID, token=ADMIN_TOKEN,
                   body={"roleIds": [R1_ID, R1_ID]})
    n = sql_int("SELECT count(*) FROM admin_roles WHERE admin_id = %d" % A1_ID)
    check("D5 传重复 id [r1,r1] -> 去重后 1 行（否则撞复合主键变 500）", n == 1, "实测 %d 行" % n)

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % A1_ID, token=ADMIN_TOKEN,
                   body={"roleIds": [R1_ID, 99999999]})
    check("D6 ★ 含不存在的角色 id -> code 400（不是 500 —— 不靠 FK 的 23503 做控制流）",
          code_of(j) == 400, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % A1_ID, token=ADMIN_TOKEN,
                   body={"roleIds": []})
    n = sql_int("SELECT count(*) FROM admin_roles WHERE admin_id = %d" % A1_ID)
    check("D7 空数组 [] = 清空 -> HTTP 200 且库里 0 行",
          st == 200 and code_of(j) == 200 and n == 0, "实测 HTTP %s 行数 %d" % (st, n))

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % A1_ID, token=ADMIN_TOKEN, body={})
    check("D8 roleIds 缺失（{}）-> code 400（@NotNull；否则会被当成 [] 静默清空角色）",
          code_of(j) == 400, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/99999999/roles", token=ADMIN_TOKEN,
                   body={"roleIds": [R1_ID]})
    check("D9 PUT 不存在的管理员 id -> code 404", code_of(j) == 404,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % ADMIN_ID, token=ADMIN_TOKEN,
                   body={"roleIds": []})
    check("D10 ★ 护栏③ 清空【自己】的角色 -> code 400", code_of(j) == 400,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % ADMIN_ID, token=ADMIN_TOKEN,
                   body={"roleIds": [SUPER_ID]})
    own = sql_many("SELECT role_id FROM admin_roles WHERE admin_id = %d" % ADMIN_ID)
    check("D11 ★ 护栏③ 只拦「清空」：给自己换一份【非空】角色 -> 200，且超管身份没丢",
          st == 200 and code_of(j) == 200 and own == [str(SUPER_ID)],
          "实测 HTTP %s code %s 现有角色 %s" % (st, code_of(j), own))

    st, j, _ = api("PUT", "/api/admin/roles/%d/permissions" % R1_ID, token=ADMIN_TOKEN,
                   body={"permissionIds": [26, 27]})
    check("D12 PUT roles/{id}/permissions [26,27] -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    n = sql_int("SELECT count(*) FROM role_permissions WHERE role_id = %d" % R1_ID)
    check("D13 库里 role_permissions 该角色 2 行", n == 2, "实测 %d 行" % n)

    api("PUT", "/api/admin/roles/%d/permissions" % R1_ID, token=ADMIN_TOKEN,
        body={"permissionIds": [26, 27]})
    n = sql_int("SELECT count(*) FROM role_permissions WHERE role_id = %d" % R1_ID)
    check("D14 ★ 幂等：重复提交同一份权限集合 -> 仍是 2 行", n == 2, "实测 %d 行" % n)

    st, j, _ = api("PUT", "/api/admin/roles/%d/permissions" % R1_ID, token=ADMIN_TOKEN,
                   body={"permissionIds": [26, 99999999]})
    check("D15 ★ 含不存在的权限 id -> code 400（不是 500）", code_of(j) == 400,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/roles/%d/permissions" % SUPER_ID, token=ADMIN_TOKEN,
                   body={"permissionIds": [26, 27]})
    check("D16 ★ 护栏② 把 SUPER_ADMIN 的权限改少 -> code 400", code_of(j) == 400,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    cur = sql_many("SELECT permission_id FROM role_permissions WHERE role_id = %d "
                   "ORDER BY permission_id" % SUPER_ID)
    st, j, _ = api("PUT", "/api/admin/roles/%d/permissions" % SUPER_ID, token=ADMIN_TOKEN,
                   body={"permissionIds": [int(x) for x in cur]})
    check("D17 ★ 护栏② 的边界：把【现状原样】提交（不增不减）-> 200（拦的是「减」不是「改」）",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("POST", "/api/admin/admins", token=ADMIN_TOKEN,
                   body={"username": U_MARK + "x1", "password": TMP_PWD, "nickname": "待删"})
    X1_ID = data_of(j)
    api("PUT", "/api/admin/admins/%d/roles" % X1_ID, token=ADMIN_TOKEN, body={"roleIds": [R1_ID]})
    n_before = sql_int("SELECT count(*) FROM admins WHERE id = %d" % X1_ID)
    n_role_before = sql_int("SELECT count(*) FROM admin_roles WHERE admin_id = %d" % X1_ID)
    st, j, _ = api("DELETE", "/api/admin/admins/%d" % X1_ID, token=ADMIN_TOKEN)
    n_after = sql_int("SELECT count(*) FROM admins WHERE id = %d" % X1_ID)
    n_role_after = sql_int("SELECT count(*) FROM admin_roles WHERE admin_id = %d" % X1_ID)
    check("D18 物理删管理员 -> HTTP 200 + admins 该行没了（前置：确实有 1 行 + 1 条角色）",
          st == 200 and n_before == 1 and n_role_before == 1 and n_after == 0,
          "实测 HTTP %s before=%d/%d after=%d" % (st, n_before, n_role_before, n_after))
    check("D19 ★★ 物理删同时清掉 admin_roles（否则留孤儿行：将来同 id 会【凭空继承旧角色】）",
          n_role_after == 0, "实测残留 %d 行" % n_role_after)

    # ---------------------------------------------------------- E roles.status 修复证明
    say("\n[E] ★★ roles.status 修复证明（Day 23 那条 SQL 修复的实证）")
    st, j, _ = api("POST", "/api/admin/admins", token=ADMIN_TOKEN,
                   body={"username": U_MARK + "e", "password": TMP_PWD, "nickname": "E 组"})
    E_ID = data_of(j)
    check("E1 POST 建 E 组管理员 -> HTTP 200 + 返回 id", st == 200 and isinstance(E_ID, int),
          "实测 HTTP %s data %s" % (st, E_ID))

    st, j, _ = api("PUT", "/api/admin/roles/%d/permissions" % RE_ID, token=ADMIN_TOKEN,
                   body={"permissionIds": [38]})
    check("E2 给临时角色 RE 只授 permission:list(38) -> 200", st == 200 and code_of(j) == 200,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/admins/%d/roles" % E_ID, token=ADMIN_TOKEN,
                   body={"roleIds": [RE_ID]})
    check("E3 把 RE 分配给该管理员 -> 200", st == 200 and code_of(j) == 200,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    OLD_TOKEN, msg = login("/api/auth/admin/login", U_MARK + "e", TMP_PWD)
    if not OLD_TOKEN:
        # ⚠️ 这里【不能】补一条 check：那会让断言总数 +1，把 EXPECTED 护栏搅成假报警。
        #    token 为 None 时 api() 不发 Authorization 头 → 下面的断言自然 401 失败。
        say("    [WARN] E 组管理员登录失败：%s" % msg)
    st, j, _ = api("GET", "/api/admin/permissions", token=OLD_TOKEN)
    check("E4 ★ 停用前：新登录的 token 打 /api/admin/permissions -> HTTP 200（有权限）",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("PUT", "/api/admin/roles/%d" % RE_ID, token=ADMIN_TOKEN, body={"status": 0})
    check("E5 停用 RE（status=0）-> HTTP 200", st == 200 and code_of(j) == 200,
          "实测 HTTP %s code %s" % (st, code_of(j)))

    NEW2_TOKEN, msg2 = login("/api/auth/admin/login", U_MARK + "e", TMP_PWD)
    st, j, _ = api("GET", "/api/admin/permissions", token=NEW2_TOKEN)
    check("E6 ★★★ 停用后【重新登录】的 token 打同一端点 -> HTTP 403（权限码真的不再下发 = 修复生效）",
          st == 403, "实测 HTTP %s code %s" % (st, code_of(j)))

    st, j, _ = api("GET", "/api/admin/permissions", token=OLD_TOKEN)
    check("E7 ★★★ 而【停用前的旧 token】打同一端点 -> HTTP 200（快照不变 = 路线① 的正面证据）",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

    # ---------------------------------------------------------- F 权限只读
    say("\n[F] 权限字典只读（不分页 + 无写方法）")
    st, j, _ = api("GET", "/api/admin/permissions", token=ADMIN_TOKEN)
    check("F1 GET /api/admin/permissions -> HTTP 200 + code 200",
          st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))
    lst = data_of(j) or []
    all_n = sql_int("SELECT count(*) FROM permissions")
    check("F2 ★ 不分页：返回条数 == permissions 全表行数",
          isinstance(lst, list) and len(lst) == all_n, "实测 %s vs 全表 %d" % (len(lst), all_n))

    st, j, _ = api("GET", "/api/admin/permissions?type=API", token=ADMIN_TOKEN)
    api_n = sql_int("SELECT count(*) FROM permissions WHERE type = 'API'")
    check("F3 type=API 过滤 -> 条数 == count(type='API')",
          len(data_of(j) or []) == api_n, "实测 %s vs %d" % (len(data_of(j) or []), api_n))

    st, j, _ = api("GET", "/api/admin/permissions?keyword=assign", token=ADMIN_TOKEN)
    codes = [p.get("code") for p in (data_of(j) or [])]
    check("F4 keyword 过滤命中 code（含 assign 的两条）",
          sorted(codes) == ["admin:assign-role", "role:assign-permission"], "实测 %s" % codes)

    for m in ("POST", "PUT", "DELETE"):
        st, j, _ = api(m, "/api/admin/permissions", token=ADMIN_TOKEN)
        check("F5-%s %s /api/admin/permissions -> HTTP 405（路径在、方法不支持）" % (m, m),
              st == 405, "实测 HTTP %s" % st)

    # ---------------------------------------------------------- G 基线还原
    say("\n[G] 基线还原（清理 + 断言没伤到自己）")
    cleanup()
    AFTER = baseline()
    for k in ("admins", "roles", "admin_roles", "role_permissions", "permissions"):
        check("G %s 回到基线（%d -> %d）" % (k, BASE[k], AFTER[k]), AFTER[k] == BASE[k],
              "实测 %d，基线 %d" % (AFTER[k], BASE[k]))
    r1_after = rbac_count(SUPER_ID)
    check("G6 ★ 清完后超管仍持有 13 条 RBAC 码（清理/护栏都没伤到超管）",
          r1_after == 13, "实测 %d" % r1_after)

finally:
    say("\n[清理] 高水位线删除（断言中途炸了也要清干净）")
    try:
        cleanup()
        FINAL = baseline()
        say("  清理后: %s" % FINAL)
    except Exception as e:                                        # noqa: BLE001
        say("  [WARN] 清理失败：%s" % e)

say("\n" + "=" * 78)
TOTAL = PASS + FAIL
say("TOTAL: %d / %d    PASS=%d FAIL=%d" % (TOTAL, EXPECTED, PASS, FAIL))
if TOTAL != EXPECTED:
    say("⚠️ 断言总数与 EXPECTED 不符 —— 有断言被静默跳过或重复计数，请核对静态清点")
if FAILS:
    say("FAILED:")
    for f in FAILS:
        say("  - %s" % f)
say("VERDICT: %s" % ("ALL GREEN" if FAIL == 0 and TOTAL == EXPECTED else "NOT GREEN"))
say("=" * 78)

out = os.path.join(HERE, "day23-rbac-verify-report.txt")
with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(LINES) + "\n")
print("\n报告已写入: %s" % out)
sys.exit(0 if (FAIL == 0 and TOTAL == EXPECTED) else 1)
