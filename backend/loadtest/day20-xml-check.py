# -*- coding: utf-8 -*-
"""Day 20 骨架自检：mapper XML 的良构性 + statement 齐全性 + SQL 填没填 + TODO 计数。

（沿用 day19-xml-check.py 的配置化结构，只换「本日主角」模块与新增 statement 名单。
  Day 20 与 Day 19 的一个差别：本日主角是【两个 XML】（Coupon / UserCoupon），
  所以 MODULES 里它们是两条独立条目 —— 每个 XML 各自做双向核对。）

检查三类「编译期看不见」的错：

  1. **XML 良构** —— 注释里出现连续两个 ASCII 减号会让解析器抛
     `SAXParseException: 注释中不允许出现字符串 "--"`，
     而 Maven 只是把文件复制过去，编译照样 SUCCESS，**启动才炸**。
     ★ 本日两个 XML 的注释里写了大量 SQL 形状提示（含 `<update>` 说明、§ 引用），
       是本脚本最该盯的地方。
  2. **statement 齐全** —— Java 声明了方法而 XML 里没有同名 id，
     编译不报错、一调用就 `Invalid bound statement (not found)`。
     必须【逐字符一致】。
  3. **SQL 还停在 TODO** —— 骨架期判据。占位 SQL 故意写成以 `TODO` 开头的文本，
     这样本栏能自动反映「实现填没填完」：
     非空 ⇒ 路由到了也必然 500（骨架期正常）；全空 ⇒ 可以进「起应用 + e2e」。

  4. ★ 本日新增：**Java 侧 TODO 计数**（扫 `UnsupportedOperationException`）。
     它与第 3 条一起构成「骨架填完了吗」的完整判据 ——
     光看 XML 会漏掉 Service / Controller 里还没填的方法。
     预期基线：**11 处**（AdminCouponController 3 + CouponController 3 + CouponServiceImpl 5）。

  5. ★★ 本日新增：**XML 语句体「空实现」检测**。
     起因是一个真实事故：把 `TODO: ...` 那行**删掉**、但 SQL 还没写 ——
     语句体只剩空白。此时第 3 条【完全查不到】（没有 `TODO` 文本了），
     本栏会把它当成「已实现」而放行 ⇒ 这是比 TODO 更危险的中间态：
       · 编译过（Maven 只复制 XML）
       · 启动过（MyBatis 解析出一个空 SqlSource，不报错）
       · **被调用才炸**，且报的是 SQL 层错误，看着像业务 bug
     判据：语句体去掉空白后，必须以 SQL 关键字（select / insert / update /
     delete / with）开头。不满足 ⇒ 计入「空实现」并让脚本非 0 退出。

再顺手做一次**双向**核对（Java ↔ XML）：
  · Java 有、XML 无 → 调用必然 Invalid bound statement
  · XML 有、Java 无 → MyBatis 启动**不报错**，静静躺着只能靠人工发现
"""
from _paths import lp
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MK = lp(r"D:\MallX\backend\mallx\mall-marketing\src\main")
PROD = lp(r"D:\MallX\backend\mallx\mall-product\src\main")
ORDER = lp(r"D:\MallX\backend\mallx\mall-order\src\main")
INV = lp(r"D:\MallX\backend\mallx\mall-inventory\src\main")

MODULES = [
    {
        "name": "mall-marketing / CouponMapper（★ Day 20 主角）",
        "java": MK + r"\java\com\mallx\marketing\mapper\CouponMapper.java",
        "xml": MK + r"\resources\mapper\CouponMapper.xml",
        "new": ["increaseReceivedCount", "selectAvailableCoupons"],
    },
    {
        "name": "mall-marketing / UserCouponMapper（★ Day 20 主角）",
        "java": MK + r"\java\com\mallx\marketing\mapper\UserCouponMapper.java",
        "xml": MK + r"\resources\mapper\UserCouponMapper.xml",
        "new": ["insertIgnore", "selectMyCoupons"],
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

# ★ 本日新增：Java 侧骨架占位的扫描范围与预期基线
TODO_SCAN_DIR = MK + r"\java"
TODO_BASELINE = 11

REPORT = lp(r"D:\MallX\backend\loadtest\day20-xml-check-report.txt")

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
    """扫 Java 源码里的 UnsupportedOperationException —— 骨架占位的权威计数。"""
    hits = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, "r", encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if "UnsupportedOperationException" in line:
                        hits.append((fn, i, line.strip()))
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
todos = count_java_todos(TODO_SCAN_DIR)
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
