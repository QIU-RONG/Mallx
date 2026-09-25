# -*- coding: utf-8 -*-
"""L5②（Day 24）品牌 CRUD 权限补发落地 + 幂等验证（backend/sql/14-brand-crud-permissions.sql）。

与 day20-l5-perm-apply.py 同一条通道、同一套判据。本次与 L5①（10 号文件）的**唯一区别**
是期望值从「1 / 1 / 1 / 0」变成「4 / 4 / 4 / 0」—— 而这个变化本身是本脚本最值得看的地方：

  ★★ 10 号文件跑过之后，`permissions` 里已经有 1 条 brand:*（list）。
     若照着「已经处理过品牌了」的判断跳过本文件，现象是
     `POST /api/admin/brands` 对**所有人**稳定 403 —— 包括超管。
     排查会怀疑 @PreAuthorize 拼错、路径不对，**而真因是 role_permissions 里没有行指向新权限**。
     ⇒ 这正是「权限码与授权是两件事」的实证：加了 permissions 行 ≠ 拿到了权限。

  ★ 幂等判据照旧：第二次执行后快照【完全不变】。
  ★ 残留检查：3 条新权限的 path 必须都在 /api/admin/ 下（指向 C 端 = 死权限）。

运行：python day24-perm-apply.py
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
SQL_FILE = lp(r"D:\MallX\backend\sql\14-brand-crud-permissions.sql")
REPORT = lp(r"D:\MallX\backend\loadtest\day24-perm-apply-report.txt")

SNAPSHOT_SQL = """
SELECT 'perm_total',        count(*)::text FROM permissions
UNION ALL SELECT 'perm_brand',      count(*)::text FROM permissions WHERE code LIKE 'brand:%'
UNION ALL SELECT 'rp_total',        count(*)::text FROM role_permissions
UNION ALL SELECT 'rp_brand_role1',  count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 1 AND p.code LIKE 'brand:%'
UNION ALL SELECT 'rp_brand_role2',  count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 2 AND p.code LIKE 'brand:%'
UNION ALL SELECT 'rp_brand_role3',  count(*)::text FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                                     WHERE rp.role_id = 3 AND p.code LIKE 'brand:%'
UNION ALL SELECT 'brand_paths',     COALESCE(string_agg(p.code || '=' || p.path, ' ; ' ORDER BY p.id), 'NULL')
                                     FROM permissions p WHERE p.code LIKE 'brand:%'
UNION ALL SELECT 'perm_max_id',     COALESCE(max(id)::text, 'NULL') FROM permissions
UNION ALL SELECT 'roles_total',     count(*)::text FROM roles
"""

CHECK_SQL = """
SELECT p.id || ' | ' || p.code || ' | ' || p.name || ' | ' || COALESCE(p.path, '') || ' | ' || COALESCE(p.method, '')
  FROM permissions p
 WHERE p.code LIKE 'brand:%'
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
SELECT 'brand_perms_total',                  count(*)::text FROM permissions WHERE code LIKE 'brand:%'
UNION ALL SELECT 'granted_to_super_admin',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 1 AND p.code LIKE 'brand:%'
UNION ALL SELECT 'granted_to_product_admin', count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 2 AND p.code LIKE 'brand:%'
UNION ALL SELECT 'granted_to_order_admin',   count(*)::text FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
       WHERE rp.role_id = 3 AND p.code LIKE 'brand:%'
"""

# ★ 残留检查：brand 权限的 path 一条都不该指向 C 端 /api/brands
STALE_SQL = """
SELECT count(*)::text FROM permissions
 WHERE code LIKE 'brand:%' AND path NOT LIKE '/api/admin/%';
"""

META_SQL = """
SELECT code || '|' || COALESCE(path, '')
  FROM permissions
 WHERE code LIKE 'brand:%'
 ORDER BY id;
"""

# ★ 期望值表 —— 「对着设计断言」：path 必须与 AdminBrandController 的真实端点逐字一致。
#   前三条是本日新增（Day 24），brand:list 是 Day 20 的（保持不变，顺带回归）。
EXPECT_META = {
    "brand:list": "/api/admin/brands",
    "brand:create": "/api/admin/brands",
    "brand:update": "/api/admin/brands/*",
    "brand:delete": "/api/admin/brands/*",
}

# ★ 交叉核对期望值 —— 4 / 4 / 4 / 0，全部从「10 号文件已发 1 条」复算：
#     1（list，Day 20）+ 3（本日） = 4
EXPECT_CROSS = {
    "brand_perms_total": 4,
    "granted_to_super_admin": 4,
    "granted_to_product_admin": 4,
    "granted_to_order_admin": 0,
}

EXPECT_PERM_MAX_ID = 41
EXPECT_PERM_TOTAL = 41

lines = []
say = lines.append


def psql(sql_text):
    """跑一段 SQL。★ SQL 用 stdin 传，不走命令行 —— 命令行会撞 PS 的 % 展开坑。"""
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
say("L5② 品牌 CRUD 权限补发 —— %s" % SQL_FILE)
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
say("[6] 权限清单（brand:*）—— ★ 期望 4 行：21 / 39 / 40 / 41")
rc6, out, err = psql(CHECK_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[7] 每个角色拿到了多少权限（整体）")
rc7, out, err = psql(GRANT_SQL)
for ln in out.splitlines():
    say("      %s" % ln)

say("")
say("[8] ★ 交叉核对（对着 EXPECT_CROSS 断言；最后一列期望为 0）")
cross_ok = True
rc8, rows8, err8 = kv_rows(CROSSCHECK_SQL)
for k, v in rows8.items():
    exp = EXPECT_CROSS.get(k)
    good = (str(v) == str(exp))
    cross_ok = cross_ok and good
    say("      [%s] %-26s 实际=%-3s 期望=%s" % ("PASS" if good else "FAIL", k, v, exp))

say("")
say("[9] ★ 元数据核对 —— 四条 brand:* 的 path 必须与端点逐字一致")
meta_ok = (rc6 == 0)
rc9, rows9, err9 = kv_rows(META_SQL)
got_total = len(rows9)
for c, ep in sorted(EXPECT_META.items()):
    got = rows9.get(c)
    good = (got == ep)
    meta_ok = meta_ok and good
    say("      [%s] %-14s path=%s" % ("PASS" if good else "FAIL", c, got))

say("")
say("[10] ★ 残留检查：brand 权限里 path 不指向 /api/admin/ 的条数（期望 0）")
rc10, out, err = psql(STALE_SQL)
stale = out.strip() if out else "?"
stale_ok = (stale == "0")
say("      [%s] 实际=%s 期望=0" % ("PASS" if stale_ok else "FAIL", stale))

say("")
say("[11] ★ 序列与总数校准（显式 id 种子的必备一步）")
final = aft = after2 or {}
max_id = final.get("perm_max_id")
perm_total = final.get("perm_total")
seq_ok = (max_id == str(EXPECT_PERM_MAX_ID)) and (perm_total == str(EXPECT_PERM_TOTAL))
say("      [%s] max(id)=%s  期望=%d" % ("PASS" if max_id == str(EXPECT_PERM_MAX_ID) else "FAIL",
                                        max_id, EXPECT_PERM_MAX_ID))
say("      [%s] count(*) =%s  期望=%d" % ("PASS" if perm_total == str(EXPECT_PERM_TOTAL) else "FAIL",
                                          perm_total, EXPECT_PERM_TOTAL))
say("      ⚠️ max(id) 与 count(*) 必须同值 —— 显式 id 插入后若忘了 setval 序列，" )
say("         下一次业务 INSERT 会拿到 nextval=26 撞上已存在的行（23505）。")

# ---------- 小结尾 ----------
say("")
say("=" * 74)
ok = (rc == 0) and (rc2 == 0) and not changes2 and cross_ok and meta_ok and stale_ok \
    and seq_ok and (got_total == len(EXPECT_META))
if got_total != len(EXPECT_META):
    say("⚠️ 权限行数不一致：实际 %d 行，期望 %d 行" % (got_total, len(EXPECT_META)))
say("VERDICT: %s" % ("OK —— 品牌 CRUD 权限已补发 + 幂等（4/4/4/0）" if ok else "FAIL —— 见上文"))
say("=" * 74)

bail(0 if ok else 1)
