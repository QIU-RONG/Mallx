# -*- coding: utf-8 -*-
"""Day 17 权限补发落地 + 幂等验证（backend/sql/05-admin-permissions.sql）。

做四件事：
  1. 执行前抓「权限快照」（permissions / role_permissions 各角色计数 + order:list 的 path）
  2. 执行 05-admin-permissions.sql
  3. 再抓一次快照并对比：应恰好 +5 条权限、授权按前缀补齐
  4. ★ 再执行一次，断言快照【完全不变】—— 这是幂等的判据

为什么幂等验证是本脚本的核心而不是附赠：
  这个文件将来必然会被反复执行（地基一改就要重跑，新环境要装）。
  · 不幂等的最坏形态不是报错 —— 报错（23505 撞主键）反而是好的，它当场告诉你。
  · 坏的是「伪幂等」：靠 ON CONFLICT 之类把重复掩住，让人以为重跑无害，
    实际 updated_at 已经被反复刷新，「谁在什么时候改过这一行」这条线索就废了。
  → 所以判据必须落在【快照逐字段不变】，而不是「没报错」。

★ 为什么用 docker exec + stdin 传 SQL，而不是把文件挂进容器：
  与既有验收脚本（day13-e2e.py 起）保持同一条通道，少一个「容器里有没有这个文件」的变量。
⚠️ psql 的两个开关是承重的：
  · `-i`          让 docker exec 接住 stdin（不写它，SQL 会被当成空输入，静默什么都不做）
  · `ON_ERROR_STOP=1`  让 SQL 报错时 psql 返回非 0（否则它默认「继续执行后面的语句并返回 0」，
                       于是一次失败的建表/授权会被当成成功 —— 这个坑非常隐蔽）
"""
from _paths import lp
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
DB_NAME = "mallx"
SQL_FILE = lp(r"D:\MallX\backend\sql\05-admin-permissions.sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day17-perm-apply-report.txt")

SNAPSHOT_SQL = """
SELECT 'perm_total',      count(*)::text FROM permissions
UNION ALL SELECT 'perm_order',      count(*)::text FROM permissions WHERE code LIKE 'order:%'
UNION ALL SELECT 'perm_inventory',  count(*)::text FROM permissions WHERE code LIKE 'inventory:%'
UNION ALL SELECT 'rp_total',        count(*)::text FROM role_permissions
UNION ALL SELECT 'rp_role1_super',  count(*)::text FROM role_permissions WHERE role_id = 1
UNION ALL SELECT 'rp_role2_product',count(*)::text FROM role_permissions WHERE role_id = 2
UNION ALL SELECT 'rp_role3_order',  count(*)::text FROM role_permissions WHERE role_id = 3
UNION ALL SELECT 'order_list_path',   COALESCE((SELECT path FROM permissions WHERE code = 'order:list'), 'NULL')
UNION ALL SELECT 'order_detail_name', COALESCE((SELECT name FROM permissions WHERE code = 'order:detail'), 'NULL')
UNION ALL SELECT 'order_detail_path', COALESCE((SELECT path FROM permissions WHERE code = 'order:detail'), 'NULL')
UNION ALL SELECT 'perm_max_id',       COALESCE(max(id)::text, 'NULL') FROM permissions
"""

CHECK_SQL = """
SELECT p.id || ' | ' || p.code || ' | ' || p.name || ' | ' || COALESCE(p.path, '') || ' | ' || COALESCE(p.method, '')
  FROM permissions p
 WHERE p.code LIKE 'order:%' OR p.code LIKE 'inventory:%'
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
SELECT 'inventory_total=' || (SELECT count(*) FROM permissions WHERE code LIKE 'inventory:%')
    || '  granted_to_product_admin=' || (SELECT count(*) FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
           WHERE rp.role_id = 2 AND p.code LIKE 'inventory:%')
    || '  granted_to_super_admin=' || (SELECT count(*) FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
           WHERE rp.role_id = 1 AND p.code LIKE 'inventory:%')
    || '  order_total=' || (SELECT count(*) FROM permissions WHERE code LIKE 'order:%')
    || '  granted_to_order_admin=' || (SELECT count(*) FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
           WHERE rp.role_id = 3 AND p.code LIKE 'order:%');
"""

META_SQL = """
SELECT code || '|' || name || '|' || COALESCE(path, '')
  FROM permissions
 WHERE code IN ('order:list', 'order:detail')
 ORDER BY code;
"""

# ★ 期望值表 —— 这是「对着设计断言」，不是「对着库的现状断言」。
#   两个条目都是被错过的历史遗留：
#     · order:list   的 path 曾指向 C 端端点 '/api/orders'（03-data.sql 的原值）
#     · order:detail 的 name/path 曾是 order:list 的副本（照抄没改）
#   之所以值得加断言：这类错误的形态是「不报错、不少列、不影响鉴权」
#   （@PreAuthorize 认的是 code），只会让后来者按 path 去找端点时找错地方。
EXPECT_META = {
    "order:detail": ("管理端订单详情", "/api/admin/orders/*"),
    "order:list":   ("订单列表",       "/api/admin/orders"),
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


def diff(a, b):
    keys = sorted(set(a) | set(b))
    return [(k, a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)]


say("=" * 74)
say("Day 17 权限补发 —— %s" % SQL_FILE)
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
say("      ✅ 执行成功（含文件末尾的三段自检 SELECT，输出见下）")
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

# ---------- 4. 三段自检 ----------
say("")
say("[6] 权限清单（order:* + inventory:*）")
rc, out, err = psql(CHECK_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[7] 每个角色拿到了多少权限")
rc, out, err = psql(GRANT_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[8] ★ 交叉核对（左右两侧的计数必须两两相等）")
rc, out, err = psql(CROSSCHECK_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[9] ★ 元数据订正核对 —— name / path 必须与 code 自洽")
say("      （本栏是本轮新加的：错误指向不报错、不少列、不影响鉴权，只误导后来者）")
rc9, out, err = psql(META_SQL)
meta_rows = {}
for ln in out.splitlines():
    if "|" in ln:
        c, n, p = ln.split("|", 2)
        meta_rows[c] = (n, p)
        say("      %-14s name=%-14s path=%s" % (c, n, p))
meta_ok = (rc9 == 0)
for c, (en, ep) in sorted(EXPECT_META.items()):
    got = meta_rows.get(c)
    good = (got == (en, ep))
    meta_ok = meta_ok and good
    say("      [%s] %s  期望 name=%s / path=%s" % ("PASS" if good else "FAIL", c, en, ep))

# ---------- 小结尾 ----------
say("")
say("=" * 74)
ok = (rc == 0) and (rc2 == 0) and not changes2 and meta_ok
say("VERDICT: %s" % ("OK —— 权限已补发且幂等" if ok else "FAIL —— 见上文"))
say("=" * 74)

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
raise SystemExit(0 if ok else 1)
