"""从 mapper XML 里抽出指定 statement 的 SQL，把 #{param} 换成测试值，直连 PG 跑一遍。

用途：证明「你写在 XML 里的那段文本」本身在库里能跑出预期结果 ——
      而不是相信一份等价的手抄版本（手抄版对了，不代表文件里那份也对）。

顺带能抓到两类静默错误：
  · #{参数名} 拼错 → 替换不上，原样带着 #{} 进 PG → 语法错误
  · 别名写错     → 列头不对，与 Java 字段对不上（本脚本会把列头原样打印出来）

用法：
  python day16-xml-sql-probe.py                 # 跑内置清单里的全部条目
  python day16-xml-sql-probe.py selectBuyContext # 只跑某一条
"""
import re
import subprocess
import sys
from pathlib import Path

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
MALLX = Path(r"D:\MallX\backend\mallx")
PG = ["exec", "-i", "-e", "PGCLIENTENCODING=UTF8", "mallx-postgres",
      "psql", "-U", "mallx", "-d", "mallx"]

# statement id -> (xml 路径, 参数替换表)
# ★ 参数值按「库里真实存在的数据」填，见 day16-buycontext-probe.sql 的 A 组。
CASES = {
    "selectBuyContext": (
        MALLX / "mall-order/src/main/resources/mapper/OrderItemMapper.xml",
        {"orderItemId": "1", "userId": "1"},
    ),
}


def extract(xml_path: Path, sid: str):
    text = xml_path.read_text(encoding="utf-8")
    m = re.search(r'<(select|insert|update|delete)\s+id="%s"[^>]*>(.*?)</\1>' % re.escape(sid),
                  text, re.S)
    if not m:
        return None
    return m.group(2).strip()


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    total = bad = 0
    for sid, (xml_path, params) in CASES.items():
        if want and sid != want:
            continue
        total += 1
        print("=" * 66)
        print(f"statement : {sid}")
        print(f"source    : {xml_path}")

        sql = extract(xml_path, sid)
        if sql is None:
            print("RESULT    : !!! <statement> not found in XML")
            bad += 1
            continue

        missing = [k for k in params if f"#{{{k}}}" not in sql]
        if missing:
            print(f"WARN      : params declared but not used in SQL: {missing}")
        sql_filled = sql
        for k, v in params.items():
            sql_filled = sql_filled.replace(f"#{{{k}}}", v)

        leftover = re.findall(r"#\{\w+\}", sql_filled)
        if leftover:
            print(f"RESULT    : !!! unresolved placeholders {leftover} "
                  f"-> param name typo in XML")
            bad += 1
            continue

        print(f"params    : {params}")
        print("-" * 66)
        r = subprocess.run([DOCKER] + PG, input="\\pset border 2\n" + sql_filled,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        print(out.rstrip())
        if "ERROR" in out.upper():
            bad += 1

    print("=" * 66)
    print(f"CHECKED: {total}   PROBLEMS: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
