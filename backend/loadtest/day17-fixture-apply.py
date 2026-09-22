# -*- coding: utf-8 -*-
"""Day 17 · 夹具落库（`06-day17-fixtures.sql`）—— 幂等实证 + 判别力前置检查

为什么单独一个脚本：
    规划 §夹具 要求「op_order（ORDER_ADMIN）」，而它的 id 必须 ≠ admin 的 1，
    否则「管理端详情不过滤归属」那条断言会因为 1 = 1 变成永远为真（测不出降级）。
    所以落库之后必须【实测】把 id 打出来，不能靠"插进去了"就当数。

★ 幂等判据：连跑两次，第二次的 admins / admin_roles 快照必须与第一次完全相同。
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SQL_FILE = r"D:\MallX\backend\sql\06-day17-fixtures.sql"
REPORT = r"D:\MallX\backend\loadtest\day17-fixture-apply-report.txt"

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"

lines = []
say = lines.append
checks = []


def ck(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    say("  %s %-56s %s" % ("✅" if ok else "❌", name, detail))


def psql(sql):
    p = subprocess.run([DOCKER, "exec", "-i", CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("psql 失败: %s" % (p.stderr or "")[:400])
    return [r for r in (p.stdout or "").strip().splitlines() if r.strip()]


def psql_file(text):
    p = subprocess.run([DOCKER, "exec", "-i", CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("执行 SQL 文件失败: %s" % (p.stderr or "")[:400])
    return (p.stdout or "").strip()


def snapshot():
    admins = psql("SELECT id, username, password, nickname, status FROM admins ORDER BY id;")
    links = psql("SELECT admin_id, role_id FROM admin_roles ORDER BY admin_id, role_id;")
    return admins, links


say("=" * 78)
say("Day 17 · 夹具落库 —— backend/sql/06-day17-fixtures.sql")
say("=" * 78)

with open(SQL_FILE, encoding="utf-8") as f:
    sql_text = f.read()

# ---------- 0. 前置：现有管理员（判"危险巧合"是否成立） ----------
a0, l0 = snapshot()
say("[0] 执行前 admins = %d 行 / admin_roles = %d 行" % (len(a0), len(l0)))
for r in a0:
    say("      " + r)
say("")

# ---------- 1. 第一次执行 ----------
say("[1] 第一次执行 SQL 文件")
out1 = psql_file(sql_text)
for r in out1.splitlines():
    say("      " + r)
a1, l1 = snapshot()
say("      → admins = %d 行 / admin_roles = %d 行" % (len(a1), len(l1)))
say("")

# ---------- 2. 第二次执行（幂等实证） ----------
say("[2] 第二次执行（幂等实证）")
out2 = psql_file(sql_text)
a2, l2 = snapshot()
say("      → admins = %d 行 / admin_roles = %d 行" % (len(a2), len(l2)))
ck("第二次执行后 admins 快照与第一次【逐字节相同】", a1 == a2,
   "变化 %s" % (set(a2) ^ set(a1) if a1 != a2 else "无"))
ck("第二次执行后 admin_roles 快照与第一次【逐字节相同】", l1 == l2,
   "变化 %s" % (set(l2) ^ set(l1) if l1 != l2 else "无"))
ck("admins 表无重复 username（幂等没产生副本）",
   len({r.split("|")[1] for r in a1}) == len(a1), "%d 行 / %d 个唯一 username" % (len(a1), len({r.split("|")[1] for r in a1})))
ck("admin_roles 无重复授予（同一 admin+role 只出现一次）",
   len(l1) == len(set(l1)), str(l1))
# ★ 不能用「净新增 == 1」当判据 —— 那只在【首次执行】成立；
#   重复执行时 +0 才是幂等的正确表现（本行就是为了兼容两种情形）
ck("admin_roles 净新增 ≤ 1（首次 +1 / 重复 +0 都算对）",
   len(l1) - len(l0) <= 1, "%d→%d" % (len(l0), len(l1)))
say("")

# ---------- 3. ★ 判别力前置检查：op_order.id 必须 ≠ 1 ----------
say("[3] ★ 判别力前置检查（这条不过，链路 B 的核心断言就是假的）")
op = [r for r in a1 if r.split("|")[1] == "op_order"]
ck("op_order 已存在", len(op) == 1, str(op)[:80])

op_id = int(op[0].split("|")[0]) if op else -1
ords = psql("SELECT DISTINCT user_id FROM orders ORDER BY user_id;")
order_owners = [int(x) for x in ords]
say("      op_order.id = %s ；orders.user_id 取值集合 = %s" % (op_id, order_owners))
ck("op_order.id ≠ 任一订单的 user_id（★ 否则降级实现也返回 200，断言失效）",
   op_id not in order_owners, "op_order.id=%s / order owners=%s" % (op_id, order_owners))
say("")

# ---------- 4. 权限矩阵（op_order 该有什么、不该有什么） ----------
say("[4] op_order 的实际权限码（角色 3 = ORDER_ADMIN）")
perms = psql(
    "SELECT DISTINCT p.code FROM admins a "
    "JOIN admin_roles ar ON ar.admin_id = a.id "
    "JOIN role_permissions rp ON rp.role_id = ar.role_id "
    "JOIN permissions p ON p.id = rp.permission_id "
    "WHERE a.username = 'op_order' ORDER BY p.code;")
say("      %s" % perms)
has_order = sorted(c for c in perms if c.startswith("order:"))
has_inv = sorted(c for c in perms if c.startswith("inventory:"))
ck("有 order:*（4 条：list / ship / detail / cancel）", has_order ==
   ["order:cancel", "order:detail", "order:list", "order:ship"], str(has_order))
ck("★ 没有 inventory:*（权限矩阵区分度的来源）", has_inv == [], str(has_inv))
say("")

# ---------- 汇总 ----------
bad = [c for c in checks if not c[1]]
say("=" * 78)
if bad:
    say("VERDICT: FAIL —— %d / %d 项不符" % (len(bad), len(checks)))
    for n, _, d in bad:
        say("   · %s   %s" % (n, d))
else:
    say("VERDICT: OK —— %d / %d 项全过（夹具就绪 + 幂等成立 + 判别力成立）" % (len(checks), len(checks)))
    say("   op_order.id = %s，用它取 user_id=1 的订单：正确实现 200 / 降级实现 404。" % op_id)
say("=" * 78)

report = "\n".join(lines)
print(report)
open(REPORT, "w", encoding="utf-8").write(report + "\n")
raise SystemExit(0 if not bad else 1)
