# -*- coding: utf-8 -*-
"""D46-A 护栏的【控制组】：四组已知有问题的变体，护栏必须失败，且失败点要精确。

只测「好的那一侧」= 什么都没测。这个脚本存在的全部意义是证明 day47-perm-count-guard.py 有牙。
跑法：python _d46a_ctrl.py   （会临时改动 4 个已提交文件，跑完用 git checkout 还原）
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.abspath(__file__))            # backend/loadtest
REPO = os.path.dirname(os.path.dirname(ROOT))                # D:\MallX
GUARD = os.path.join(ROOT, "day47-perm-count-guard.py")


def run_guard():
    p = subprocess.run([sys.executable, GUARD], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = p.stdout or ""
    fails = [l.strip()[7:].split("   ")[0].strip()
             for l in out.splitlines() if l.strip().startswith("[FAIL]")]
    if p.returncode not in (0, 1):
        print("  !! guard rc=%d  stderr=%s" % (p.returncode, (p.stderr or "")[:500]))
    return p.returncode, fails, out


def patch(rel, old, new):
    p = os.path.join(REPO, rel.replace("/", os.sep))
    s = io.open(p, encoding="utf-8", newline="").read()
    assert old in s, "pattern not found in %s: %r" % (rel, old[:40])
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
    return p


def restore(rel):
    subprocess.run(["git", "checkout", "--", rel], cwd=REPO, capture_output=True)


def git_clean(rel):
    p = subprocess.run(["git", "status", "--short", "--", rel], cwd=REPO,
                       capture_output=True, text=True)
    return not (p.stdout or "").strip()


cases = []


def case(name, mutate, expect_contains, cleanup):
    mutate()
    rc, fails, out = run_guard()
    cleanup()
    hit = [f for f in fails if any(k in f for k in expect_contains)]
    ok = (rc != 0) and hit
    cases.append((name, ok, rc, fails, expect_contains))
    print("[%s] %s   rc=%d  失败 %d 条" % ("OK " if ok else "FAIL", name, rc, len(fails)))
    for f in fails:
        print("        - %s" % f)
    assert git_clean_all(), "!! 残留未还原"


def git_clean_all():
    p = subprocess.run(["git", "status", "--short"], cwd=REPO, capture_output=True, text=True)
    return "backend/loadtest/day99-drift-probe.py" not in (p.stdout or "")


print("=" * 78)
print("D46-A 护栏控制组（4 组；每组都必须 FAIL，且失败点命中预期）")
print("=" * 78)

# 基线：现在必须是绿的
rc, fails, _o = run_guard()
print("[基线] 当前仓库 rc=%d 失败=%d 条（期望 0/0）" % (rc, len(fails)))
assert rc == 0, "基线不绿，控制组无从谈起"
print()

# ① 漏改一处常量（Day 46 的原始事故形态）
case("① day25-compose 的 46 退回 41（漏改一处）",
     lambda: patch("backend/loadtest/day25-compose-verify.py", "n_perm == 46", "n_perm == 41"),
     ["B7"],
     lambda: restore("backend/loadtest/day25-compose-verify.py"))

# ② 冒出一个【未登记】的声明点（第 6 处硬编码）
#    ★ 文件名必须是 dayNN-*.py：`_*.py` 是内部工具约定，被护栏的扫描豁免了
#      （第一版探针叫 day99-drift-probe.py ⇒ 被自己的豁免规则绕过，控制组 0 失败 —— 假绿）
probe = os.path.join(ROOT, "day99-drift-probe.py")


def make_probe():
    io.open(probe, "w", encoding="utf-8", newline="\n").write(
        "# -*- coding: utf-8 -*-\nEXPECT_PERM_TOTAL = 99\n")


case("② 新建 day99-drift-probe.py 写 EXPECT_PERM_TOTAL = 99（未登记声明点）",
     make_probe, ["C2"],
     lambda: os.path.exists(probe) and os.remove(probe))

# ③ SQL 里真加一条权限，常量全不动（★ 本脚本唯一存在的理由）
case("③ SQL 新增一条权限 id=47，5 处常量不动",
     lambda: patch("backend/sql/18-refund-permissions.sql",
                   "    (46, '执行退款',",
                   "    (46, '执行退款',    'refund:refund',  'API', '/api/admin/refunds/*/refund',  'POST'),\n"
                   "    (47, '假权限',"),
     ["B1", "B7"],
     lambda: restore("backend/sql/18-refund-permissions.sql"))

# ④ 把 initdb 判据偷懒写成 >=（会让半截初始化蒙混过关）
case("④ ci.yml 判据写成 >= 46（防半截初始化失效）",
     lambda: patch(".github/workflows/ci.yml", '[ "$n" = "46" ]', '[ "$n" >= "46" ]'),
     ["C1"],
     lambda: restore(".github/workflows/ci.yml"))

print()
print("=" * 78)
bad = [c for c in cases if not c[1]]
print("控制组结果：%d/%d 命中预期（失败数为 0 ⇒ 什么都没守住）" % (len(cases) - len(bad), len(cases)))
print("VERDICT: %s" % ("OK" if not bad else "FAIL"))
print("=" * 78)
sys.exit(0 if not bad else 1)
