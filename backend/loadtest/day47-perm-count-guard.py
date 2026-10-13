# -*- coding: utf-8 -*-
"""Day 47（D46-A）· 权限总数【单一来源】护栏。

=============================================================================
为什么需要它（这是 Day 46 真实踩的一次事故）
=============================================================================
Day 46 新增 5 条退款权限（id 42–46），权限总数 41 → 46。
但「权限总数 = 41」这份事实被**硬编码钉在 5 个地方**，改的时候只想起来一处
⇒ CI 第 7 步「Wait for initdb（判据 permissions=41）」永远等不到 46
⇒ **整条 pipeline 红**，而红的位置离真因（SQL 里多了 5 行）有十万八千里。

  .github/workflows/ci.yml             initdb 就绪判据（漏改 ⇒ 整条 pipeline 红）
  backend/loadtest/day24-perm-apply.py         EXPECT_PERM_MAX_ID / EXPECT_PERM_TOTAL
  backend/loadtest/day25-sql-strict-check.py   EXPECT_PERM_TOTAL（+ EXPECTED_FILES）
  backend/loadtest/day25-compose-verify.py     B2 断言 n_perm == N
  backend/loadtest/day43-run-full-stack.ps1    本机整栈入口（**不进 CI** ⇒ 漏了只静默等满 90s）

=============================================================================
本脚本怎么解决：「一处定义，其余必须跟从」
=============================================================================
★ **本文件不硬编码 46**。真值从 `backend/sql/*.sql` 的 `INSERT INTO permissions`
  静态推导出来（那才是唯一的事实来源），然后去核对上面每一处常量是否等于它。

  ⇒ 加权限时你只需要改【SQL】；其余 4 处忘了改，本脚本会**精确地点名是哪一处**。
  ⇒ 反过来：改了常量却没改 SQL，同样会红（常量不再是 SQL 推出来的值）。

[A] 段验的是**不变式**（与具体数字无关，所以永远不会因为加权限而需要改）：
    id 不重复、1..max 连续、显式 id 必须配序列校准。
[B] 段逐处核对常量；★ 「一处都没命中」判 FAIL（正则悄悄失配 ⇒ 假绿，这是最坏的结果）。
[C] 段是**漏网检测**：全库扫一遍带 perm 又带数字的代码行，凡是没登记在本脚本
    声明点清单里的 ⇒ FAIL。这样第 6 处、第 7 处硬编码出现时会自动被抓出来。

=============================================================================
控制组（本脚本自带，证明它有牙；没有控制组 = 什么都没守住）
=============================================================================
  ① 把 `day25-compose-verify.py` 的 46 改回 41            ⇒ B6 红（1 条，零误伤）
  ② 新建 `loadtest/_perm-drift-probe.py` 写 `EXPECT_PERM_TOTAL = 99`
                                                          ⇒ C2 红（抓到未登记声明点）
  ③ 在 SQL 里再加一条权限（id 47）而常量不动               ⇒ B 段 8 条全红
     （这正是 Day 46 的真实场景 —— 也是本脚本唯一存在的理由）
  ④ 把 ci.yml 判据改成 `>= 46`                             ⇒ C1 红（半截初始化会蒙混过关）

运行：python day47-perm-count-guard.py    （纯静态，秒级，不需要 DB / 应用 / Docker）

⚠️ 为什么本脚本**不提供** `--selfcheck`（AST 静态核对满额常量）：
   B 段的 chk( 落在 `for ... in DECL_SITES` 循环里（一处调用点执行 N 次），
   静态数必然小于运行时数 ⇒ 拿它比对只会制造假红（D43-B 的教训）。
   ⇒ 满额判据由**运行时**承担：报告末尾 `ASSERTIONS: x / y (EXPECTED=17)`，
     y != 17 即判 FAIL（删掉一条断言会立刻现形）。CI 直接看退出码。
"""
from _paths import REPO_ROOT
import glob
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT = os.path.join(REPO_ROOT, "backend", "loadtest", "day47-perm-count-guard-report.txt")
SQL_DIR = os.path.join(REPO_ROOT, "backend", "sql")
LOADTEST_DIR = os.path.join(REPO_ROOT, "backend", "loadtest")
CI_DIR = os.path.join(REPO_ROOT, ".github", "workflows")

# 满额护栏（★ 别再手工数：--selfcheck 用 AST 静态度量本文件的 chk( 调用点并与本常量比对）
EXPECTED_CHECKS = 17

# -----------------------------------------------------------------------------
# 声明点清单：每一处「权限总数的硬编码副本」都必须登记在这里。
#   (显示名, 相对路径, 取值正则, 语义, 最少命中数)
#     语义 "total" = 权限总条数；"max" = 最大 id
# ★ 新增第 6 处时：① 在这里加一行；② 若忘了加，[C2] 段会替你抓出来。
# -----------------------------------------------------------------------------
DECL_SITES = [
    ("B1 ci.yml · initdb 数据判据", ".github/workflows/ci.yml",
     r'\[ "\$n" (?:!=|=) "(\d+)" \]', "total", 2),
    ("B2 ci.yml · 步骤名/日志文案", ".github/workflows/ci.yml",
     r'permissions=(\d+)', "total", 1),
    ("B3 ci.yml · 报错文案「期望 N」", ".github/workflows/ci.yml",
     r'期望 (\d+)', "total", 1),
    ("B4 day24-perm-apply · MAX_ID", "backend/loadtest/day24-perm-apply.py",
     r'EXPECT_PERM_MAX_ID\s*=\s*(\d+)', "max", 1),
    ("B5 day24-perm-apply · TOTAL", "backend/loadtest/day24-perm-apply.py",
     r'EXPECT_PERM_TOTAL\s*=\s*(\d+)', "total", 1),
    ("B6 day25-sql-strict · TOTAL", "backend/loadtest/day25-sql-strict-check.py",
     r'EXPECT_PERM_TOTAL\s*=\s*(\d+)', "total", 1),
    ("B7 day25-compose · B2 断言", "backend/loadtest/day25-compose-verify.py",
     r'n_perm\s*==\s*(\d+)', "total", 1),
    ("B8 day43-run-full-stack · 等待判据", "backend/loadtest/day43-run-full-stack.ps1",
     r'\$pg"\.Trim\(\) -eq "(\d+)"', "total", 1),
    ("B9 day43-run-full-stack · 期望文案", "backend/loadtest/day43-run-full-stack.ps1",
     r'期望 (\d+)', "total", 1),
]

# [C2] 的「疑似声明点」形态 —— 比 DECL_SITES 更宽，用来抓【还没登记】的第 6/7 处。
# ★ 每条都要求「标识符里带 PERM / permissions」+「两位以上数字」，
#   否则会把 `total=10`、`st == 403`、`permissionIds` 这类无关行一网打尽（假红也是失控）。
#   (可疑形态, 同行上下文要求) —— 上下文为 None 表示形态本身足够特异。
#   ★「期望 N」「-eq "N"」单独出现毫无意义（满库都是「期望 401」），必须**同一行**还带
#     perm/permissions/$pg 才算可疑 —— 这条是踩出来的：第一版没加上下文，一屏假红。
SUSPECT_RXS = [
    (r"[A-Za-z_]*PERM[A-Za-z_]*\s*=\s*\d{2,}", None),
    (r"permissions\s*[=＝]\s*\d{2,}", None),
    (r"n_perm\s*==\s*\d{2,}", None),
    (r'"\$n"\s*(?:!=|=)\s*"\d{2,}"', None),
    (r'\$pg"\.Trim\(\) -eq "\d{2,}"', None),
    (r"期望\s*\d{2,}", r"(?i)permissions|\$pg"),
    (r'-eq\s*"\d{2,}"', r"(?i)permissions|\$pg"),
]

# 另一对同源常量：backend/sql 的文件数 vs day25-sql-strict-check 的 EXPECTED_FILES
FILES_SITE = ("day25-sql-strict · EXPECTED_FILES", "backend/loadtest/day25-sql-strict-check.py",
              r'EXPECTED_FILES\s*=\s*(\d+)')

lines_out = []
n_pass = n_fail = 0


def say(s=""):
    lines_out.append(s)
    print(s)


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def read(rel):
    p = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return None
    return io.open(p, encoding="utf-8").read()


# -----------------------------------------------------------------------------
# [A] 真值：从 SQL 静态推导
# -----------------------------------------------------------------------------
def parse_permissions():
    """解析 `INSERT INTO permissions (id, ...) ... FROM (VALUES (1, ...), ...)`。

    返回 (per_file, ids)；per_file = [(文件名, [id...]), ...]
    """
    per_file = []
    for path in sorted(glob.glob(os.path.join(SQL_DIR, "*.sql"))):
        src = io.open(path, encoding="utf-8").read()
        src = re.sub(r"--[^\n]*", "", src)          # 去掉行注释，免得注释里的数字混进来
        got = []
        for m in re.finditer(r"INSERT INTO permissions\s*\(", src):
            seg = src[m.end():]
            end = seg.find(";")
            if end > 0:
                seg = seg[:end]
            v = seg.find("VALUES")
            if v < 0:
                continue
            got += [int(x) for x in re.findall(r"\(\s*(\d+)\s*,", seg[v:])]
        if got:
            per_file.append((os.path.basename(path), got))
    ids = [i for _f, g in per_file for i in g]
    return per_file, ids


def main():
    say("=" * 78)
    say("Day 47（D46-A）· 权限总数【单一来源】护栏")
    say("真值来源：backend/sql/*.sql 的 INSERT INTO permissions（本脚本不硬编码总数）")
    say("=" * 78)

    # ---------- [A] SQL 侧不变式 ----------
    say("")
    say("[A] SQL 侧（真值 + 三条与具体数字无关的不变式）")
    per_file, ids = parse_permissions()
    uniq = sorted(set(ids))
    total, max_id = len(uniq), (max(uniq) if uniq else 0)

    chk("A1 每个含 INSERT INTO permissions 的文件都解析出 ≥1 个显式 id",
        len(per_file) >= 1 and all(len(g) >= 1 for _f, g in per_file),
        "files=%d  ids=%d" % (len(per_file), len(ids)))
    dup = sorted({i for i in ids if ids.count(i) > 1})
    chk("A2 跨文件【无重复 id】", not dup, "dup=%s" % (dup or "无"))
    chk("A3 id 从 1 连续到 max（显式 id 跳号/复用 ⇒ 立刻现形）",
        uniq == list(range(1, max_id + 1)) if uniq else False,
        "max=%d  uniq=%d" % (max_id, len(uniq)))
    chk("A4 max_id == 总条数（等价于 A3，换个角度看同一件事）",
        max_id == total, "max=%d total=%d" % (max_id, total))
    # ★ 显式 id 不会推进 PG 序列 ⇒ 每个写权限的文件都必须校准，否则业务侧 INSERT 撞主键 23505
    miss_setval = []
    for fn, _g in per_file:
        src = read("backend/sql/" + fn) or ""
        if "pg_get_serial_sequence('permissions'" not in src.replace('"', "'"):
            miss_setval.append(fn)
    chk("A5 每个补发权限的文件都配了序列校准 setval(pg_get_serial_sequence('permissions'))",
        not miss_setval, "缺=%s" % (miss_setval or "无"))

    say("")
    say("     ↳ SQL 推导结果：total=%d  max_id=%d  files=%d" % (total, max_id, len(per_file)))

    # ---------- [B] 逐处核对常量 ----------
    say("")
    say("[B] 常量侧（%d 处硬编码副本，必须全部等于 SQL 推导值）" % len(DECL_SITES))
    for name, rel, rx, kind, minimum in DECL_SITES:
        src = read(rel)
        if src is None:
            chk("B %s：文件不存在" % name, False, rel)
            continue
        nums = [int(x) for x in re.findall(rx, src)]
        want = total if kind == "total" else max_id
        # ★ 「一处都没命中」判 FAIL：正则悄悄失配 ⇒ 假绿，这是最坏的结果
        chk("%s == %s(%d)" % (name, kind, want),
            len(nums) >= minimum and all(n == want for n in nums),
            "命中 %d 处，值=%s" % (len(nums), nums or "无"))

    # ---------- [C] 反向：漏网检测 + 两条「别偷懒」 ----------
    say("")
    say("[C] 反向（漏网检测 / 判据不许写成 >=）")

    ci = read(".github/workflows/ci.yml") or ""
    lazy = re.findall(r'\[ "\$n" >= "\d+" \]|permissions>=\d+', ci)
    chk("C1 ci.yml 的 initdb 判据不是 >=（>= 会让「半截初始化」蒙混过关）",
        not lazy, "命中=%s" % (lazy or "无"))

    # 扫全部 .py / .ps1 / workflow yml：凡「形态像权限数字声明」却【没登记】的 ⇒ 漏网。
    # ★ 这就是「第 6 处硬编码」的自动发现器 —— 它比人可靠，因为它不依赖你想得起来。
    unchecked = []
    scan = (glob.glob(os.path.join(LOADTEST_DIR, "*.py")) +
            glob.glob(os.path.join(LOADTEST_DIR, "*.ps1")) +
            glob.glob(os.path.join(CI_DIR, "*.yml")))
    for path in sorted(scan):
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        base = os.path.basename(rel)
        if base == "day47-perm-count-guard.py":
            continue                                   # 本脚本自己不算
        if base.startswith("_"):
            continue                                   # `_*.py` 是内部/临时工具（如本脚本的控制组）
                                                       # ★ 真实漂移只会落在 dayNN-*.py / ci.yml 里
        for i, line in enumerate(io.open(path, encoding="utf-8", errors="replace"), 1):
            s = line.strip()
            if s.startswith(("#", "--", "*", "//")):   # 注释行不参与（文案里出现数字是正常的）
                continue
            if not any(re.search(rx, s) and (ctx is None or re.search(ctx, s))
                       for rx, ctx in SUSPECT_RXS):
                continue
            if any(r == rel and re.search(rx, s) for _n, r, rx, _k, _m in DECL_SITES):
                continue                               # 已登记
            unchecked.append("%s:%d  %s" % (rel, i, s[:70]))
    chk("C2 全库扫：没有【未登记】的权限数字声明点（新增第 6 处会自动被抓）",
        not unchecked, "漏网=%s" % (unchecked or "无"))

    n_sql = len(glob.glob(os.path.join(SQL_DIR, "*.sql")))
    src = read(FILES_SITE[1]) or ""
    m = re.search(FILES_SITE[2], src)
    chk("C3 backend/sql 文件数(%d) == %s（同一类同源常量漂移：16→18 上次也漂过）"
        % (n_sql, FILES_SITE[0]),
        bool(m) and int(m.group(1)) == n_sql,
        "declared=%s" % (m.group(1) if m else "无"))

    return verdict()


def verdict():
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, n_pass + n_fail, EXPECTED_CHECKS))
    if n_pass + n_fail != EXPECTED_CHECKS:
        say("★ 护栏未过：实得 %d 条，期望 %d 条" % (n_pass + n_fail, EXPECTED_CHECKS))
    ok = (n_fail == 0 and n_pass + n_fail == EXPECTED_CHECKS)
    say("VERDICT: %s" % ("OK" if ok else "FAIL"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines_out) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
