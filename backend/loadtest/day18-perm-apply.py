# -*- coding: utf-8 -*-
"""Day 18 权限补发落地 + 幂等验证（backend/sql/07-admin-permissions.sql）。

做四件事：
  1. 执行前抓「权限快照」（permissions / role_permissions 各角色计数 + product:* 的 path）
  2. 执行 07-admin-permissions.sql
  3. 再抓一次快照并对比：应恰好 +4 条 category 权限、product:* 的 path 被订正
  4. ★ 再执行一次，断言快照【完全不变】—— 这是幂等的判据

本日与 Day 17 的两点不同（脚本层面）：
  · 本日同时含【补发】与【订正】两类动作，所以断言也分两类：
    补发看向「计数」，订正看向「字段值」。
  · ★「期望为 0」也是断言 —— role 3（ORDER_ADMIN）拿到 0 条 category:*。
    只断言「谁拿了」而不锁定「谁没拿」，权限矩阵的区分度就会悄悄退化。

★ 为什么用 docker exec + stdin 传 SQL，而不是把文件挂进容器：
  与既有验收脚本（day13-e2e.py 起）保持同一条通道，少一个「容器里有没有这个文件」的变量。
⚠️ psql 的两个开关是承重的：
  · `-i`          让 docker exec 接住 stdin（不写它，SQL 会被当成空输入，静默什么都不做）
  · `ON_ERROR_STOP=1`  让 SQL 报错时 psql 返回非 0（否则它默认「继续执行后面的语句并返回 0」，
                       于是一次失败的授权会被当成成功 —— 这个坑非常隐蔽）
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
DB_NAME = "mallx"
SQL_FILE = r"D:\MallX\backend\sql\07-admin-permissions.sql"
REPORT = r"D:\MallX\backend\loadtest\day18-perm-apply-report.txt"

SNAPSHOT_SQL = """
SELECT 'perm_total',       count(*)::text FROM permissions
UNION ALL SELECT 'perm_product',    count(*)::text FROM permissions WHERE code LIKE 'product:%'
UNION ALL SELECT 'perm_category',   count(*)::text FROM permissions WHERE code LIKE 'category:%'
UNION ALL SELECT 'rp_total',        count(*)::text FROM role_permissions
UNION ALL SELECT 'rp_role1_super',  count(*)::text FROM role_permissions WHERE role_id = 1
UNION ALL SELECT 'rp_role2_product',count(*)::text FROM role_permissions WHERE role_id = 2
UNION ALL SELECT 'rp_role3_order',  count(*)::text FROM role_permissions WHERE role_id = 3
UNION ALL SELECT 'rp_cat_role1',    count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 1 AND p.code LIKE 'category:%'
UNION ALL SELECT 'rp_cat_role2',    count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 2 AND p.code LIKE 'category:%'
UNION ALL SELECT 'product_paths',   COALESCE(string_agg(p.code || '=' || p.path, ' ; ' ORDER BY p.id), 'NULL')
                                     FROM permissions p WHERE p.code LIKE 'product:%'
UNION ALL SELECT 'perm_max_id',     COALESCE(max(id)::text, 'NULL') FROM permissions
"""

CHECK_SQL = """
SELECT p.id || ' | ' || p.code || ' | ' || p.name || ' | ' || COALESCE(p.path, '') || ' | ' || COALESCE(p.method, '')
  FROM permissions p
 WHERE p.code LIKE 'product:%' OR p.code LIKE 'category:%'
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
SELECT 'category_perms_total',      count(*)::text FROM permissions WHERE code LIKE 'category:%'
UNION ALL SELECT 'granted_to_product_admin', count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 2 AND p.code LIKE 'category:%'
UNION ALL SELECT 'granted_to_super_admin',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 1 AND p.code LIKE 'category:%'
UNION ALL SELECT 'granted_to_order_admin',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 3 AND p.code LIKE 'category:%'
"""

# 5.2 那一段：★ 期望 0 行 —— 不允许任何 product 权限还指向 C 端路径
STALE_SQL = """
SELECT count(*)::text FROM permissions
 WHERE code LIKE 'product:%' AND path LIKE '/api/products%';
"""

META_SQL = """
SELECT code || '|' || COALESCE(path, '')
  FROM permissions
 WHERE code LIKE 'product:%' OR code LIKE 'category:%'
 ORDER BY id;
"""

# ★ 期望值表 —— 「对着设计断言」，不是「对着库的现状断言」。
#   product:* 五条的旧 path 全部指向 C 端（03-data.sql 的原值），本日订正到管理端。
#   category:* 四条是本日新增，path 必须与 AdminCategoryController 的真实端点逐字一致。
EXPECT_META = {
    "product:list":     "/api/admin/products",
    "product:detail":   "/api/admin/products/*",
    "product:create":   "/api/admin/products",
    "product:update":   "/api/admin/products/*",
    "product:delete":   "/api/admin/products/*",
    "category:list":    "/api/admin/categories/tree",
    "category:create":  "/api/admin/categories",
    "category:update":  "/api/admin/categories/*",
    "category:delete":  "/api/admin/categories/*",
}

# ★ 交叉核对期望值（含「期望 0」）
EXPECT_CROSS = {
    "category_perms_total": 4,
    "granted_to_product_admin": 4,
    "granted_to_super_admin": 4,
    "granted_to_order_admin": 0,
}

lines = []
say = lines.append


def psql(sql_text):
    """跑一段 SQL，返回 (rc, stdout, stderr)。全部走 docker exec，stdin 传语句。"""
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
    """把 k|v 形式的查询结果读成 dict"""
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


say("=" * 74)
say("Day 18 权限补发 —— %s" % SQL_FILE)
say("=" * 74)

with open(SQL_FILE, "r", encoding="utf-8") as fh:
    sql_body = fh.read()
say("SQL 文件 %d 字符 / %d 行" % (len(sql_body), sql_body.count("\n") + 1))
say("")

# ---------- 1. 执行前快照 ----------
before = snapshot("before")
if before is None:
    print("\n".join(lines))
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    raise SystemExit(1)

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
    print("\n".join(lines))
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    raise SystemExit(1)
say("      ✅ 执行成功（含文件末尾的四段自检 SELECT，输出见下）")
say("")
for ln in out.splitlines():
    say("      %s" % ln)
say("")

after1 = snapshot("after1")
say("[3] 第一次执行后的变化（before -> after）")
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
say("[6] 权限清单（product:* + category:*）")
rc6, out, err = psql(CHECK_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[7] 每个角色拿到了多少权限")
rc7, out, err = psql(GRANT_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[8] ★ 交叉核对（对着 EXPECT_CROSS 断言；注意最后一列期望为 0）")
cross_ok = True
rc8, rows8, err8 = kv_rows(CROSSCHECK_SQL)
for k, v in rows8.items():
    exp = EXPECT_CROSS.get(k)
    good = (v == str(exp))
    cross_ok = cross_ok and good
    say("      [%s] %-26s 实际=%-3s 期望=%s" % ("PASS" if good else "FAIL", k, v, exp))

say("")
say("[9] ★ 元数据核对 —— product 的五条 path 必须已订正，category 四条必须与端点一致")
meta_ok = (rc6 == 0)
rc9, rows9, err9 = kv_rows(META_SQL)
got_total = len(rows9)
for c, ep in sorted(EXPECT_META.items()):
    got = rows9.get(c)
    good = (got == ep)
    meta_ok = meta_ok and good
    say("      [%s] %-16s path=%s" % ("PASS" if good else "FAIL", c, got))

say("")
say("[10] ★ 残留检查：还指向 C 端路径的 product 权限条数（期望 0）")
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
say("VERDICT: %s" % ("OK —— 权限已补发 + 订正 + 幂等" if ok else "FAIL —— 见上文"))
say("=" * 74)

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
raise SystemExit(0 if ok else 1)
