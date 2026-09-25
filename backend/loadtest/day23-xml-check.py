# -*- coding: utf-8 -*-
"""Day 23 骨架自检：mapper XML 良构 + statement 齐全 + SQL 填没填 + Java 占位计数。

（沿用 day19 / day20 / day22-xml-check.py 的配置化结构。Day 23 与 Day 22 的两处差别：
  1. ★ 主角模块换成 **mall-admin / AdminRbacMapper**（本日唯一新建的 XML，
     11 条语句 —— 两条关联表不建实体所以手写）；
  2. ★ Java 占位基线从 7 改成 **13** —— Day 22 那 7 处已全部填完（提交 ba675cc），
     本日新增 13 处（AdminAccountManageServiceImpl 6 + RoleManageServiceImpl 6
     + PermissionQueryServiceImpl 1）。
  ※ 同时把 AdminMapper.xml 保留在列表里做【回归】：本日对它做了那条
     `AND r.status = 1` 修复，虽然语句数量没变，但良构与双向核对仍要过。

检查五类「编译期看不见」的错（判据同 day20/day22，不再赘述）：
  1. XML 良构（注释里连续两个 ASCII 减号 → 启动才炸 SAXParseException）
  2. statement 齐全（Java 有、XML 无 → 调用必 Invalid bound statement，逐字符一致）
  3. SQL 还停在 TODO（骨架期判据）
  4. ★ 语句体「空实现」（删了 TODO 文本、SQL 还没写 —— 比 TODO 更隐蔽：
     编译过、启动过、被调用才炸）
  5. Java 侧 UnsupportedOperationException 计数

运行：python day23-xml-check.py
"""
from _paths import lp
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = lp(r"D:\MallX\backend\mallx")
ADMIN = ROOT + r"\mall-admin\src\main"
MK = ROOT + r"\mall-marketing\src\main"
PROD = ROOT + r"\mall-product\src\main"
ORDER = ROOT + r"\mall-order\src\main"
INV = ROOT + r"\mall-inventory\src\main"

MODULES = [
    {
        "name": "mall-admin / AdminRbacMapper（★ Day 23 主角）",
        "java": ADMIN + r"\java\com\mallx\admin\mapper\AdminRbacMapper.java",
        "xml": ADMIN + r"\resources\mapper\AdminRbacMapper.xml",
        # 11 条：两条关联表（不建实体）+ 建档（ON CONFLICT RETURNING）+ 预校验 count
        "new": ["selectRoleIdsByAdminId", "selectPermissionIdsByRoleId",
                "deleteAdminRolesByAdminId", "deleteAdminRolesByRoleId",
                "deleteRolePermissionsByRoleId",
                "insertAdminRoles", "insertRolePermissions",
                "countRolesByIds", "countPermissionsByIds",
                "insertAdminIfAbsent", "insertRoleIfAbsent"],
    },
    {
        "name": "mall-admin / AdminMapper（Day 07 起 + ★ 本日那条修复）",
        "java": ADMIN + r"\java\com\mallx\admin\mapper\AdminMapper.java",
        "xml": ADMIN + r"\resources\mapper\AdminMapper.xml",
        "new": [],
    },
    {
        "name": "mall-admin / DashboardMapper（Day 22 回归）",
        "java": ADMIN + r"\java\com\mallx\admin\mapper\DashboardMapper.java",
        "xml": ADMIN + r"\resources\mapper\DashboardMapper.xml",
        "new": [],
    },
    {
        "name": "mall-marketing / CouponMapper（Day 20 回归）",
        "java": MK + r"\java\com\mallx\marketing\mapper\CouponMapper.java",
        "xml": MK + r"\resources\mapper\CouponMapper.xml",
        "new": [],
    },
    {
        "name": "mall-marketing / UserCouponMapper（Day 21 回归）",
        "java": MK + r"\java\com\mallx\marketing\mapper\UserCouponMapper.java",
        "xml": MK + r"\resources\mapper\UserCouponMapper.xml",
        "new": [],
    },
    {
        "name": "mall-product（Day 19 回归）",
        "java": PROD + r"\java\com\mallx\product\mapper\ProductMapper.java",
        "xml": PROD + r"\resources\mapper\ProductMapper.xml",
        "new": [],
    },
    {
        "name": "mall-order（Day 17 回归）",
        "java": ORDER + r"\java\com\mallx\order\mapper\OrderMapper.java",
        "xml": ORDER + r"\resources\mapper\OrderMapper.xml",
        "new": [],
    },
    {
        "name": "mall-inventory（Day 17 回归）",
        "java": INV + r"\java\com\mallx\inventory\mapper\InventoryMapper.java",
        "xml": INV + r"\resources\mapper\InventoryMapper.xml",
        "new": [],
    },
]

# ★ Day 23：扫全部模块（跳过后端 target 目录），基线 = 本日新增的 13 处
#   （AdminAccountManageServiceImpl 6 + RoleManageServiceImpl 6 + PermissionQueryServiceImpl 1）
TODO_SCAN_ROOT = ROOT
TODO_BASELINE = 13

REPORT = lp(r"D:\MallX\backend\loadtest\day23-xml-check-report.txt")

# 方法声明：行首 4 空格 + 返回类型开头，跨行到 ');'
DECL_RE = re.compile(r"^ {4}\S[^;{}]*?(\w+)\s*\([^;{}]*\)\s*;", re.M)

# ★ 语句体合法性：去空白后必须以 SQL 关键字开头（否则视为「空实现」）
SPEC_SQL_RE = re.compile(r"(?i)^(select|insert|update|delete|with)\b")

lines = []
say = lines.append


def strip_java_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def java_methods(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    return DECL_RE.findall(strip_java_comments(raw))


def xml_statements(path):
    root = ET.parse(path).getroot()
    out = []
    for child in root:
        out.append((child.tag, child.get("id"), (child.text or "").strip()))
    return root, out


def count_java_todos(root_dir):
    """扫 Java 源码里的 UnsupportedOperationException —— 骨架占位的权威计数。

    ★ 跳过 target/ 避免扫到编译产物。★ 本日基线 = 13（见文件头说明）。
    """
    hits = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d != "target"]
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, "r", encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if "UnsupportedOperationException" in line:
                        hits.append((fp.replace(root_dir + "\\", ""), i, line.strip()))
    return hits


total_new = 0
still_todo = []
empty_sql = []
not_wellformed = 0
missing_stmt = []
java_only = []
xml_only = []

for mod in MODULES:
    say("=" * 74)
    say("模块 %s" % mod["name"])
    say("=" * 74)

    # ---- 1. XML 良构 + statement 列表 -------------------------------------
    try:
        root, stmts = xml_statements(mod["xml"])
    except Exception as e:                                   # noqa: BLE001
        not_wellformed += 1
        say("  ❌ XML 不良构：%s: %s" % (type(e).__name__, e))
        continue

    say("  ✅ WELL_FORMED   namespace=%s" % root.get("namespace"))
    ids = set()
    for tag, sid, sql in stmts:
        ids.add(sid)
        if sql.upper().startswith("TODO"):
            flag = "★ TODO"
        elif not SPEC_SQL_RE.match(sql):
            flag = "❌ 空实现"
        else:
            flag = "       "
        say("     %s <%s id=%s>" % (flag, tag, sid))
        if sql.upper().startswith("TODO"):
            still_todo.append("%s#%s" % (mod["name"], sid))
        elif not SPEC_SQL_RE.match(sql):
            empty_sql.append("%s#%s  ← 语句体=%s"
                             % (mod["name"], sid,
                                "空（只剩空白）" if not sql else repr(sql[:40])))

    # ---- 2. 本日新增的 statement 是否都在 --------------------------------
    say("")
    if mod["new"]:
        say("  本日新增 statement：")
        for sid in mod["new"]:
            total_new += 1
            ok = sid in ids
            if not ok:
                missing_stmt.append("%s#%s" % (mod["name"], sid))
            say("     %s %s" % ("✅" if ok else "❌ MISSING", sid))
    else:
        say("  本日新增 statement：无（回归模块，只做良构与双向核对）")

    # ---- 3. Java ↔ XML 双向差集 ------------------------------------------
    jm = java_methods(mod["java"])
    jset = set(jm)
    only_j = sorted(jset - ids)
    only_x = sorted(ids - jset)
    say("")
    say("  Java 声明 %d 个 / XML statement %d 个" % (len(jset), len(ids)))
    if only_j:
        java_only.extend("%s#%s" % (mod["name"], s) for s in only_j)
        say("     ⚠️ Java 有、XML 无（调用必 Invalid bound statement）：%s" % ", ".join(only_j))
    if only_x:
        xml_only.extend("%s#%s" % (mod["name"], s) for s in only_x)
        say("     ⚠️ XML 有、Java 无（启动不报错，静静躺着）：%s" % ", ".join(only_x))
    if not only_j and not only_x:
        say("     ✅ 双向一致")
    say("")

say("=" * 74)
say("小结")
say("=" * 74)
say("  XML 良构              : %d / %d" % (len(MODULES) - not_wellformed, len(MODULES)))
say("  本日新增 statement    : %d 个，缺失 %d 个" % (total_new, len(missing_stmt)))
say("  XML SQL 仍停在 TODO   : %d 条" % len(still_todo))
for s in still_todo:
    say("      · %s" % s)
say("  XML SQL 空实现        : %d 条" % len(empty_sql))
for s in empty_sql:
    say("      · %s" % s)

# ---- 4. Java 侧骨架占位计数 -----------------------------------------------
todos = count_java_todos(TODO_SCAN_ROOT)
say("  Java 骨架占位         : %d 处（骨架交付时 %d 处 → 已填 %d 处）"
    % (len(todos), TODO_BASELINE, max(0, TODO_BASELINE - len(todos))))
for fn, ln, _txt in todos:
    say("      · %s:%d" % (fn, ln))

say("")
if still_todo or todos or empty_sql:
    say("  → 骨架期正常。XML %d 条 TODO + %d 条空实现 + Java %d 处 都填完后，本栏合计应为 0，"
        % (len(still_todo), len(empty_sql), len(todos)))
    say("    那时才能进「起应用 + 跑 e2e」。只要非 0，被路由到的端点必然 500。")
    if empty_sql:
        say("    ⚠️ 「空实现」是比 TODO 更隐蔽的中间态：删了 TODO 文本、SQL 还没写。")
        say("       编译过、启动过，被调用才炸 —— 靠人工看注释是发现不了的。")
else:
    say("  → ✅ XML 与 Java 两侧占位都已清零，可以进入「起应用 + 跑 e2e」阶段。")
say("  Java 有 / XML 无      : %d 个 %s" % (len(java_only), java_only if java_only else ""))
say("  XML 有 / Java 无      : %d 个 %s" % (len(xml_only), xml_only if xml_only else ""))

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")

ok = (not_wellformed == 0 and not missing_stmt and not java_only and not empty_sql)
raise SystemExit(0 if ok else 1)
