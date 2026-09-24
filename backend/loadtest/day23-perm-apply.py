# -*- coding: utf-8 -*-
"""Day 23 权限补发落地 + 幂等验证（backend/sql/13-day23-permissions.sql）。

与 day18 / day20-l5 / day22 的 perm-apply 是同一条通道、同一套判据。
本次按改动调整了四处：

  1. 快照字段换成 admin:* / role:* / permission:* 相关的计数；
  2. ★ 交叉核对表有【六列】：三个前缀的条数 + 三个角色分别拿到多少。
     其中 role2 / role3 的期望值【都是 0】—— 这是本日最重要的一条安排：
     13 条码一条都不给非超管（理由见 SQL 文件第二节的推理）。
     ★ 只用全权 admin 测 = 什么都证明不了，所以「期望 0」这两格必须存在。
  3. ★ 本次没有「元数据订正」动作（Day 22 那次订正了 user:list 的 path），
     所以 EXPECT_META 只覆盖本日新增的 13 条，逐条核对 path 指向 /api/admin/**。
  4. 幂等判据照旧：第二次执行后快照【完全不变】。

★ 为什么用 docker exec + stdin 传 SQL（理由与 day18/day20/day22 相同）：
  · 少一个「容器里有没有这个文件」的变量；
  · `-i` 让 docker exec 接住 stdin（不写它，SQL 被当成空输入，静默什么都不做）；
  · `ON_ERROR_STOP=1` 让 psql 报错时返回非 0（否则默认「继续执行并返回 0」，
    一次失败的授权会被当成成功 —— 这个坑非常隐蔽）。

运行：python day23-perm-apply.py
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
DB_NAME = "mallx"
SQL_FILE = r"D:\MallX\backend\sql\13-day23-permissions.sql"
REPORT = r"D:\MallX\backend\loadtest\day23-perm-apply-report.txt"

SNAPSHOT_SQL = """
SELECT 'perm_total',     count(*)::text FROM permissions
UNION ALL SELECT 'perm_admin',    count(*)::text FROM permissions WHERE code LIKE 'admin:%'
UNION ALL SELECT 'perm_role',     count(*)::text FROM permissions WHERE code LIKE 'role:%'
UNION ALL SELECT 'perm_perm',     count(*)::text FROM permissions WHERE code LIKE 'permission:%'
UNION ALL SELECT 'rp_total',      count(*)::text FROM role_permissions
UNION ALL SELECT 'rp_rbac_role1', count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                   WHERE rp.role_id = 1
                                     AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
UNION ALL SELECT 'rp_rbac_role2', count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                   WHERE rp.role_id = 2
                                     AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
UNION ALL SELECT 'rp_rbac_role3', count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                   WHERE rp.role_id = 3
                                     AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
UNION ALL SELECT 'rbac_paths',    COALESCE(string_agg(p.code || '=' || p.path, ' ; ' ORDER BY p.id), 'NULL')
                                   FROM permissions p
                                  WHERE p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%'
UNION ALL SELECT 'perm_max_id',   COALESCE(max(id)::text, 'NULL') FROM permissions
"""

CHECK_SQL = """
SELECT p.id || ' | ' || p.code || ' | ' || p.name || ' | ' || COALESCE(p.path, '') || ' | ' || COALESCE(p.method, '')
  FROM permissions p
 WHERE p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%'
 ORDER BY p.id;
"""

GRANT_SQL = """
SELECT r.code || ' | ' || count(*)::text || ' | ' || string_agg(p.code, ', ' ORDER BY p.code)
  FROM role_permissions rp
  JOIN roles r       ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 WHERE p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%'
 GROUP BY r.code ORDER BY r.code;
"""

CROSSCHECK_SQL = """
SELECT 'admin_perms_total',   count(*)::text FROM permissions WHERE code LIKE 'admin:%'
UNION ALL SELECT 'role_perms_total',   count(*)::text FROM permissions WHERE code LIKE 'role:%'
UNION ALL SELECT 'perm_perms_total',   count(*)::text FROM permissions WHERE code LIKE 'permission:%'
UNION ALL SELECT 'role1_rbac',         count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 1 AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
UNION ALL SELECT 'role2_rbac',         count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 2 AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
UNION ALL SELECT 'role3_rbac',         count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 3 AND (p.code LIKE 'admin:%' OR p.code LIKE 'role:%' OR p.code LIKE 'permission:%')
"""

# ★ 残留检查：RBAC 权限的 path 一条都不该指向 /api/admin/ 之外的地方。
#   ⚠️ 若为 0 之外的值 ⇒ 权限表在说谎（下一个人照着 path 去猜端点会猜错）。
STALE_SQL = """
SELECT count(*)::text FROM permissions
 WHERE (code LIKE 'admin:%' OR code LIKE 'role:%' OR code LIKE 'permission:%')
   AND path NOT LIKE '/api/admin/%';
"""

META_SQL = """
SELECT code || '|' || COALESCE(path, '')
  FROM permissions
 WHERE code LIKE 'admin:%' OR code LIKE 'role:%' OR code LIKE 'permission:%'
 ORDER BY id;
"""

# ★ 期望值表 —— 「对着设计断言」：path 必须与真实的 Controller 端点逐字一致
#   （AdminAccountController / AdminRoleController / AdminPermissionController）。
EXPECT_META = {
    "admin:list": "/api/admin/admins",
    "admin:detail": "/api/admin/admins/*",
    "admin:create": "/api/admin/admins",
    "admin:update": "/api/admin/admins/*",
    "admin:delete": "/api/admin/admins/*",
    "admin:assign-role": "/api/admin/admins/*/roles",
    "role:list": "/api/admin/roles",
    "role:detail": "/api/admin/roles/*",
    "role:create": "/api/admin/roles",
    "role:update": "/api/admin/roles/*",
    "role:delete": "/api/admin/roles/*",
    "role:assign-permission": "/api/admin/roles/*/permissions",
    "permission:list": "/api/admin/permissions",
}

# ★ 交叉核对期望值（六列）。
#   ★★ role2_rbac / role3_rbac 期望【都是 0】—— 反向对照，本日最要紧的两格。
#   ★ 复算：role1_rbac = admin_perms_total + role_perms_total + perm_perms_total = 6+6+1 = 13
#     （凡「合计」类期望值都要能从别的格子复算出来，别凭印象填 —— 本纪律已第 3 次被引用。）
EXPECT_CROSS = {
    "admin_perms_total": 6,
    "role_perms_total": 6,
    "perm_perms_total": 1,
    "role1_rbac": 13,
    "role2_rbac": 0,
    "role3_rbac": 0,
}

lines = []
say = lines.append


def psql(sql_text):
    """跑一段 SQL。★ 注意：SQL 用 stdin 传，不走命令行 —— 命令行会撞 PS 的 % 展开坑。"""
    args = [DOCKER, "exec", "-i",
            "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql",
            "-U", DB_USER, "-d", DB_NAME,
            "-v", "ON_ERROR_STOP=1",
            "-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def snapshot(label):
    rc, out, err = psql(SNAPSHOT_SQL)
    if rc != 0:
        say("❌ 快照失败（%s）rc=%d err=%s" % (label, rc, err[:400]))
        return None
    d = {}
    for line in out.splitlines():
        if "|" in line:
            k, v = line.split("|", 1)
            d[k] = v
    return d


def kv_rows(sql_text):
    rc, out, err = psql(sql_text)
    d = {}
    for line in out.splitlines():
        if "|" in line:
            k, v = line.split("|", 1)
            d[k] = v
    return rc, d, err


def diff(a, b):
    keys = sorted(set(a) | set(b))
    return [(k, a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)]


def bail(code):
    report = "\n".join(lines)
    print(report)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    raise SystemExit(code)


say("=" * 74)
say("Day 23 权限补发（RBAC：管理员 / 角色 / 权限）—— %s" % SQL_FILE)
say("=" * 74)

with open(SQL_FILE, "r", encoding="utf-8") as fh:
    sql_body = fh.read()
say("SQL 文件 %d 字符 / %d 行" % (len(sql_body), sql_body.count("\n") + 1))
say("")

# ---------- 1. 执行前快照 ----------
before = snapshot("before")
if before is None:
    bail(1)

say("[1] 执行前快照")
for k, v in before.items():
    say("      %-18s = %s" % (k, v))
say("")

# ---------- 2. 第一次执行 ----------
rc, out, err = psql(sql_body)
say("[2] 第一次执行  rc=%d" % rc)
if err:
    say("      stderr: %s" % err[:1500])
if rc != 0:
    say("      ❌ 执行失败，终止")
    bail(1)
say("      ✅ 执行成功（含文件末尾四段自检 SELECT，输出见下）")
say("")
for ln in out.splitlines():
    say("      %s" % ln)
say("")

after1 = snapshot("after1")
say("[3] 第一次执行后的变化（before -> after1）")
changes = diff(before, after1 or {})
if not changes:
    say("      ⚠️ 没有任何变化 —— 可能权限早就补过了，或 SQL 里的 WHERE NOT EXISTS 判错了")
for k, a, b in changes:
    say("      %-18s %s -> %s" % (k, a, b))
say("")

# ---------- 3. 第二次执行（幂等判据） ----------
rc2, out2, err2 = psql(sql_body)
say("[4] 第二次执行（幂等验证）  rc=%d" % rc2)
if err2:
    say("      stderr: %s" % err2[:800])
after2 = snapshot("after2")
say("")
say("[5] 第二次执行后的变化（after1 -> after2）—— ★ 必须为空")
changes2 = diff(after1 or {}, after2 or {})
if changes2:
    say("      ❌ 不幂等！以下字段被第二次执行改动了：")
    for k, a, b in changes2:
        say("         %-18s %s -> %s" % (k, a, b))
else:
    say("      ✅ 无任何变化 —— SQL 是幂等的")

# ---------- 4. 自检 ----------
say("")
say("[6] 权限清单（admin:* / role:* / permission:*）")
rc6, out, err = psql(CHECK_SQL)
rows6 = [ln for ln in out.splitlines() if ln.strip()]
for ln in rows6:
    say("      %s" % ln)
say("      （共 %d 行，期望 13）" % len(rows6))

say("")
say("[7] 每个角色拿到了多少 RBAC 权限（★ 期望只有 SUPER_ADMIN 一行）")
rc7, out, err = psql(GRANT_SQL)
rows7 = [ln for ln in out.splitlines() if ln.strip()]
for ln in rows7:
    say("      %s" % ln)
say("      （共 %d 行，期望 1 —— 多出来的行 = 越权通道已开）" % len(rows7))

say("")
say("[8] ★ 交叉核对（对着 EXPECT_CROSS 断言；role2/role3 期望为 0）")
cross_ok = True
rc8, rows8, err8 = kv_rows(CROSSCHECK_SQL)
for k, v in rows8.items():
    exp = EXPECT_CROSS.get(k)
    good = (str(v) == str(exp))
    cross_ok = cross_ok and good
    say("      [%s] %-26s 实际=%-3s 期望=%s" % ("PASS" if good else "FAIL", k, v, exp))

say("")
say("[9] ★ 元数据核对（13 条 path 必须逐字指向 /api/admin/**）")
meta_ok = (rc6 == 0) and (len(rows6) == 13)
rc9, rows9, err9 = kv_rows(META_SQL)
got_total = len(rows9)
for c, ep in sorted(EXPECT_META.items()):
    got = rows9.get(c)
    good = (got == ep)
    meta_ok = meta_ok and good
    say("      [%s] %-24s path=%s" % ("PASS" if good else "FAIL", c, got))

say("")
say("[10] ★ 残留检查：RBAC 权限里 path 不指向 /api/admin/ 的条数（期望 0）")
rc10, out, err = psql(STALE_SQL)
stale = out.strip() if out else "?"
stale_ok = (stale == "0")
say("      [%s] 实际=%s 期望=0" % ("PASS" if stale_ok else "FAIL", stale))

# ---------- 小结尾 ----------
say("")
say("=" * 74)
ok = (rc == 0) and (rc2 == 0) and not changes2 and cross_ok and meta_ok and stale_ok \
    and got_total == len(EXPECT_META) and len(rows7) == 1
if got_total != len(EXPECT_META):
    say("⚠️ 权限行数不一致：实际 %d 行，期望 %d 行" % (got_total, len(EXPECT_META)))
if len(rows7) != 1:
    say("⚠️ 拿到 RBAC 权限的角色有 %d 个，期望 1 个（只有 SUPER_ADMIN）" % len(rows7))
say("VERDICT: %s" % ("OK —— 13 条 RBAC 权限已补发 + 只发超管 + path 对齐 + 幂等"
                     if ok else "FAIL —— 见上文"))
say("=" * 74)

bail(0 if ok else 1)
