# -*- coding: utf-8 -*-
"""Day 16 skeleton: check the two mapper XMLs are well-formed.

Why this matters here: an XML *comment* may not contain a double hyphen, and that
mistake compiles fine (Maven just copies the file) and only blows up when MyBatis
parses it at startup - `SAXParseException: 注释中不允许出现字符串 "--"`.
Day 13 hit exactly that. A plain well-formedness parse catches it in milliseconds.
"""
import xml.etree.ElementTree as ET

FILES = [
    r"D:\MallX\backend\mallx\mall-order\src\main\resources\mapper\OrderItemMapper.xml",
    r"D:\MallX\backend\mallx\mall-review\src\main\resources\mapper\ReviewMapper.xml",
]

bad = 0
for path in FILES:
    try:
        root = ET.parse(path).getroot()
        stmts = [(c.tag, c.get("id")) for c in root]
        print("OK   %s" % path)
        print("     root=%s namespace=%s" % (root.tag, root.get("namespace")))
        for tag, sid in stmts:
            print("     +- <%s id=%s>" % (tag, sid))
    except Exception as e:                                     # noqa: BLE001
        bad += 1
        print("FAIL %s" % path)
        print("     %s: %s" % (type(e).__name__, e))

print("\nWELL_FORMED: %d / %d" % (len(FILES) - bad, len(FILES)))
