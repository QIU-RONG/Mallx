# -*- coding: utf-8 -*-
"""Day 19 骨架自检：mapper XML 的良构性 + statement 齐全性 + SQL 填没填。

（沿用 day18-xml-check.py 的配置化结构，只换「本日主角」模块与新增 statement 名单。）

检查三类「编译期看不见」的错：

  1. **XML 良构** —— 注释里出现连续两个 ASCII 减号会让解析器抛
     `SAXParseException: 注释中不允许出现字符串 "--"`，
     而 Maven 只是把文件复制过去，编译照样 SUCCESS，**启动才炸**。
     ★ Day 19 的 searchProducts 注释里写了大量 SQL 片段（含 `||` 拼接、`<if>` 标签），
       是本脚本最该盯的一处。
  2. **statement 齐全** —— Java 声明了方法而 XML 里没有同名 id，
     编译不报错、一调用就 `Invalid bound statement (not found)`。
     必须【逐字符一致】。
  3. **SQL 还停在 TODO** —— 骨架期判据。占位 SQL 故意写成以 `TODO` 开头的文本
     （不是合法 SQL），这样本栏能自动反映「实现填没填完」：
     非空 ⇒ 路由到了也必然 500（骨架期正常）；全空 ⇒ 可以进「起应用 + e2e」。

再顺手做一次**双向**核对（Java ↔ XML）：
  · Java 有、XML 无 → 调用必然 Invalid bound statement
  · XML 有、Java 无 → MyBatis 启动**不报错**，静静躺着只能靠人工发现
"""
from _paths import lp
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODULES = [
    {
        "name": "mall-product（Day 19 主角）",
        "java": lp(r"D:\MallX\backend\mallx\mall-product\src\main\java\com\mallx\product\mapper\ProductMapper.java"),
        "xml": lp(r"D:\MallX\backend\mallx\mall-product\src\main\resources\mapper\ProductMapper.xml"),
        "new": ["searchProducts"],
    },
    {
        "name": "mall-order（Day 17 回归）",
        "java": lp(r"D:\MallX\backend\mallx\mall-order\src\main\java\com\mallx\order\mapper\OrderMapper.java"),
        "xml": lp(r"D:\MallX\backend\mallx\mall-order\src\main\resources\mapper\OrderMapper.xml"),
        "new": [],
    },
    {
        "name": "mall-inventory（Day 17 回归）",
        "java": lp(r"D:\MallX\backend\mallx\mall-inventory\src\main\java\com\mallx\inventory\mapper\InventoryMapper.java"),
        "xml": lp(r"D:\MallX\backend\mallx\mall-inventory\src\main\resources\mapper\InventoryMapper.xml"),
        "new": [],
    },
]

REPORT = lp(r"D:\MallX\backend\loadtest\day19-xml-check-report.txt")

# 方法声明：行首 4 空格 + 返回类型开头，跨行到 ');'
# （searchProducts 的声明跨 5 行，单行正则抓不到）
DECL_RE = re.compile(r"^ {4}\S[^;{}]*?(\w+)\s*\([^;{}]*\)\s*;", re.M)

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


total_new = 0
still_todo = []
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
        flag = "★ TODO" if sql.upper().startswith("TODO") else "       "
        say("     %s <%s id=%s>" % (flag, tag, sid))
        if sql.upper().startswith("TODO"):
            still_todo.append("%s#%s" % (mod["name"], sid))

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
say("  SQL 仍停在 TODO       : %d 条" % len(still_todo))
if still_todo:
    for s in still_todo:
        say("      · %s" % s)
    say("  → 骨架期正常。全部填完后本栏应为 0 —— 只要非 0，那些接口必然 500。")
else:
    say("  → ✅ 所有 SQL 都已填写，可以进入「起应用 + 跑 e2e」阶段。")
say("  Java 有 / XML 无      : %d 个 %s" % (len(java_only), java_only if java_only else ""))
say("  XML 有 / Java 无      : %d 个 %s" % (len(xml_only), xml_only if xml_only else ""))

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")

ok = not_wellformed == 0 and not missing_stmt and not java_only
raise SystemExit(0 if ok else 1)
