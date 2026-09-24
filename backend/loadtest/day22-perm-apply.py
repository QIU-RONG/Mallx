# -*- coding: utf-8 -*-
"""Day 22 权限补发落地 + 幂等验证（backend/sql/12-day22-permissions.sql）。

与 day18-perm-apply.py / day20-l5-perm-apply.py 同一条通道、同一套判据，
本次按改动调整了四处：

  1. 快照字段换成 user:* / dashboard:* 相关的计数；
  2. ★ 交叉核对表有【七列】（不是四列）—— 因为本次同时动了两个权限族，
     且用户的分配是「list/detail 给超管+订单、status 只给超管」的非对称形状；
  3. ★★ 本次多一类判据：【元数据订正】。user:list 这条权限的 path
     从 C 端 /api/users 订正为 /api/admin/users（它从 Day 06 起就没有主人）。
     ⇒ EXPECT_META 里也必须把 user:list 写进去 —— 否则「订正生效了没」无人验证，
     而这正是本项目反复踩的「改了却没有断言覆盖」。
  4. 幂等判据照旧：第二次执行后快照【完全不变】。

★ 为什么用 docker exec + stdin 传 SQL（理由与 day18/day20 相同）：
  · 少一个「容器里有没有这个文件」的变量；
  · `-i` 让 docker exec 接住 stdin（不写它，SQL 被当成空输入，静默什么都不做）；
  · `ON_ERROR_STOP=1` 让 psql 报错时返回非 0（否则默认「继续执行并返回 0」，
    一次失败的授权会被当成成功 —— 这个坑非常隐蔽）。

运行：python day22-perm-apply.py
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
DB_NAME = "mallx"
SQL_FILE = r"D:\MallX\backend\sql\12-day22-permissions.sql"
REPORT = r"D:\MallX\backend\loadtest\day22-perm-apply-report.txt"

SNAPSHOT_SQL = """
SELECT 'perm_total',        count(*)::text FROM permissions
UNION ALL SELECT 'perm_user',       count(*)::text FROM permissions WHERE code LIKE 'user:%'
UNION ALL SELECT 'perm_dash',       count(*)::text FROM permissions WHERE code LIKE 'dashboard:%'
UNION ALL SELECT 'rp_total',        count(*)::text FROM role_permissions
UNION ALL SELECT 'rp_ud_role1',     count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 1 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%')
UNION ALL SELECT 'rp_ud_role2',     count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 2 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%')
UNION ALL SELECT 'rp_ud_role3',     count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 3 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%')
UNION ALL SELECT 'ud_paths',        COALESCE(string_agg(p.code || '=' || p.path, ' ; ' ORDER BY p.id), 'NULL')
                                     FROM permissions p
                                    WHERE p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%'
UNION ALL SELECT 'perm_max_id',     COALESCE(max(id)::text, 'NULL') FROM permissions
"""

CHECK_SQL = """
SELECT p.id || ' | ' || p.code || ' | ' || p.name || ' | ' || COALESCE(p.path, '') || ' | ' || COALESCE(p.method, '')
  FROM permissions p
 WHERE p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%'
 ORDER BY p.id;
"""

GRANT_SQL = """
SELECT r.code || ' | ' || count(*)::text || ' | ' || string_agg(p.code, ', ' ORDER BY p.code)
  FROM role_permissions rp
  JOIN roles r       ON r.id = rp.role_id
  JOIN permissions p ON p.id = rp.permission_id
 GROUP BY r.code ORDER BY r.code;
"""

CROSSCHECK_SQL = """
SELECT 'user_perms_total',           count(*)::text FROM permissions WHERE code LIKE 'user:%'
UNION ALL SELECT 'dashboard_perms_total', count(*)::text FROM permissions WHERE code LIKE 'dashboard:%'
UNION ALL SELECT 'role1_user_and_dash',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 1 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%')
UNION ALL SELECT 'role2_user_and_dash',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 2 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%')
UNION ALL SELECT 'role3_user_and_dash',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 3 AND (p.code LIKE 'user:%' OR p.code LIKE 'dashboard:%')
UNION ALL SELECT 'role3_user_detail',     count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 3 AND p.code = 'user:detail'
UNION ALL SELECT 'role3_user_status',     count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 3 AND p.code = 'user:status'
"""

# ★ 残留检查：user/dashboard 权限的 path 一条都不该指向 C 端前缀
STALE_SQL = """
SELECT count(*)::text FROM permissions
 WHERE (code LIKE 'user:%' OR code LIKE 'dashboard:%')
   AND path NOT LIKE '/api/admin/%';
"""

META_SQL = """
SELECT code || '|' || COALESCE(path, '')
  FROM permissions
 WHERE code LIKE 'user:%' OR code LIKE 'dashboard:%'
 ORDER BY id;
"""

# ★ 期望值表 —— 「对着设计断言」：path 必须与真实的 Controller 端点逐字一致。
#   ★★ user:list 是【订正】来的（原本是 /api/users），它出现在这张表里本身就是新判据。
EXPECT_META = {
    "user:list": "/api/admin/users",
    "user:detail": "/api/admin/users/*",
    "user:status": "/api/admin/users/*/status",
    "dashboard:overview": "/api/admin/dashboard/overview",
    "dashboard:trend": "/api/admin/dashboard/trend",
}

# ★ 交叉核对期望值（七列；其中 role3_user_status 期望【0】，是反向对照）
EXPECT_CROSS = {
    "user_perms_total": 3,
    "dashboard_perms_total": 2,
    "role1_user_and_dash": 5,
    "role2_user_and_dash": 2,
    "role3_user_and_dash": 4,
    "role3_user_detail": 1,
    "role3_user_status": 0,
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
say("Day 22 权限补发（用户管理 + 仪表盘）—— %s" % SQL_FILE)
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
say("[6] 权限清单（user:* / dashboard:*）")
rc6, out, err = psql(CHECK_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[7] 每个角色拿到了多少权限（整体）")
rc7, out, err = psql(GRANT_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[8] ★ 交叉核对（对着 EXPECT_CROSS 断言；role3_user_status 期望为 0）")
cross_ok = True
rc8, rows8, err8 = kv_rows(CROSSCHECK_SQL)
for k, v in rows8.items():
    exp = EXPECT_CROSS.get(k)
    good = (str(v) == str(exp))
    cross_ok = cross_ok and good
    say("      [%s] %-26s 实际=%-3s 期望=%s" % ("PASS" if good else "FAIL", k, v, exp))

say("")
say("[9] ★ 元数据核对（含 user:list 的 path 订正）")
meta_ok = (rc6 == 0)
rc9, rows9, err9 = kv_rows(META_SQL)
got_total = len(rows9)
for c, ep in sorted(EXPECT_META.items()):
    got = rows9.get(c)
    good = (got == ep)
    meta_ok = meta_ok and good
    say("      [%s] %-20s path=%s" % ("PASS" if good else "FAIL", c, got))

say("")
say("[10] ★ 残留检查：user/dashboard 权限里 path 不指向 /api/admin/ 的条数（期望 0）")
rc10, out, err = psql(STALE_SQL)
stale = out.strip() if out else "?"
stale_ok = (stale == "0")
say("      [%s] 实际=%s 期望=0" % ("PASS" if stale_ok else "FAIL", stale))

# ---------- 小结尾 ----------
say("")
say("=" * 74)
ok = (rc == 0) and (rc2 == 0) and not changes2 and cross_ok and meta_ok and stale_ok \
    and got_total == len(EXPECT_META)
if got_total != len(EXPECT_META):
    say("⚠️ 权限行数不一致：实际 %d 行，期望 %d 行" % (got_total, len(EXPECT_META)))
say("VERDICT: %s" % ("OK —— 用户/仪表盘权限已补发 + user:list path 已订正 + 幂等"
                     if ok else "FAIL —— 见上文"))
say("=" * 74)

bail(0 if ok else 1)
