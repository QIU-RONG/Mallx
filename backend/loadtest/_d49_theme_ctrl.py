# -*- coding: utf-8 -*-
"""
Day 49 主题护栏的控制组 —— 拿【故意改坏】的代码回跑 day49-theme-guard.py，
每一组都必须让它红，且红的必须是【预计的那一条】。

★ 为什么必须做：
  按项目铁律，新护栏不配套控制组等于没写。而且这里有个特别容易骗过自己的场景：
  「变异后确实有断言红了」≠「守住了」—— 红的可能是别的断言（或干脆是脚本崩了）。
  所以每一组都断言【命中的断言名】。

★ 另外两条来自既往教训的做法：
  ① 用【内存备份】还原，不用 git checkout —— 本轮新增的文件还没提交，checkout 回不来；
  ② 每次写盘后【立刻读回校验】—— 本项目栽过三次「write() 返回成功但内容没变」，
     后果是变异残留、后面几组的失败数累计，看起来像「护栏不灵敏」。

运行：python _d49_theme_ctrl.py
"""

import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOADTEST = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(LOADTEST))
GUARD = os.path.join(LOADTEST, "day49-theme-guard.py")

MALL_THEME = "frontend/mall-app/src/styles/theme.css"
MALL_MAIN = "frontend/mall-app/src/main.ts"
MALL_CART = "frontend/mall-app/src/views/Cart.vue"
ADMIN_THEME = "frontend/admin-app/src/styles/theme.css"


def path(rel):
    return os.path.join(REPO, rel.replace("/", os.sep))


_BACKUP = {}


def backup(rel):
    if rel not in _BACKUP:
        _BACKUP[rel] = io.open(path(rel), encoding="utf-8", newline="").read()
    return _BACKUP[rel]


def apply_variant(rel, old, new):
    """写入变异并【读回校验】—— 落盘失败必须当场发现，否则会污染后面的组。"""
    base = backup(rel)
    if old not in base:
        raise AssertionError("变异模式没命中：%s 中找不到 %r" % (rel, old[:60]))
    mutated = base.replace(old, new, 1)
    io.open(path(rel), "w", encoding="utf-8", newline="").write(mutated)
    back = io.open(path(rel), encoding="utf-8", newline="").read()
    if back != mutated:
        raise AssertionError("★ 落盘校验失败：%s 写进去的内容与预期不一致" % rel)


def reset_all():
    """把每个被改过的文件还原成备份内容，并逐字校验。"""
    for rel, content in _BACKUP.items():
        io.open(path(rel), "w", encoding="utf-8", newline="").write(content)
        back = io.open(path(rel), encoding="utf-8", newline="").read()
        if back != content:
            raise AssertionError("★ 还原失败：%s" % rel)


def run_guard():
    p = subprocess.run([sys.executable, GUARD], cwd=LOADTEST, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)
    out = (p.stdout or "") + (p.stderr or "")
    fails = re.findall(r"^\[FAIL\]\s+(\S+)", out, re.M)
    return p.returncode, fails, out


def git_dirty():
    """已跟踪文件的改动清单（未跟踪的 ?? 不算）。

    ★ 不能直接判「工作区必须干净」：本控制组通常在【改动还没提交】时跑，
      那时工作区本来就是脏的。真正该问的是「有没有【多出来】的改动」——
      即变异残留。所以先取一次基线，最后做集合差。
      （第一版就是直接判 dirty 非空 ⇒ 把本轮真实改动误报成「还原不干净」。）
    """
    g = subprocess.run(["git", "status", "--short"], cwd=REPO, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return sorted(l for l in (g.stdout or "").splitlines()
                  if l.strip() and not l.startswith("??"))


CASES = [
    # ⚠️ 这里的 old 字符串是【真实文件内容】，换主色后必须同步（day50 换小米橙时改过一次）。
    #    下面 main() 里有一道「变异模式预检」——失配会立刻报错，而不是跑到那一组才莫名失败。
    ("① 删掉 mall-app 的 --el-color-primary 覆盖（＝上一版的状态：只定义品牌色、不管组件）",
     MALL_THEME,
     "  --el-color-primary: #ff6700;\n", "",
     ["A1", "A2", "A3"]),

    ("② 只把 light-3 改回 EP 的 #79bbff（＝「只手改 primary 不改色阶」的反面）",
     MALL_THEME,
     "  --el-color-primary-light-3: #ff954c;",
     "  --el-color-primary-light-3: #79bbff;",
     ["A2"]),

    ("③ 把 admin 的品牌色改成另一个值（两应用主色分叉）",
     ADMIN_THEME,
     "  --brand-color: #ff6700;",
     "  --brand-color: #112233;",
     ["A3"]),

    ("④ 调换 mall-app 的 import 顺序（theme.css 排到 EP 之前 ⇒ 覆盖静默失效）",
     MALL_MAIN,
     "import 'element-plus/dist/index.css'\nimport './style.css'\nimport './styles/theme.css'",
     "import './styles/theme.css'\nimport 'element-plus/dist/index.css'\nimport './style.css'",
     ["A4"]),

    ("⑤ 在 Cart.vue 里留一个硬编码的 EP 蓝（换色没换干净）",
     MALL_CART,
     "  color: #909399;",
     "  color: #409eff;",
     ["B1"]),

    ("⑥ 把 admin 的价格色改成别的（两个应用的金额色分叉）",
     ADMIN_THEME,
     "  --brand-price: #e1251b;",
     "  --brand-price: #ff0000;",
     ["B2"]),
]


def main():
    dirty0 = git_dirty()

    # ── 基线：未变异时必须全绿。基线不绿说明护栏本身有问题，先修它。 ──
    rc, fails, out = run_guard()
    print("=" * 78)
    print("基线：rc=%s 失败=%s" % (rc, fails or "无"))
    if rc != 0 or fails:
        print(out[-1200:])
        print("★ 基线不绿 ⇒ 控制组无意义，先修护栏")
        return 2
    print("  ⇒ 基线全绿，可以做变异\n")

    # ── 前置：所有变异模式必须能在目标文件里【命中】 ──
    #    ★ 换主题色 / 改文案之后，控制组里的 old 字符串会失配。
    #      预检让它【立刻】报出该更新哪一条，而不是跑到那一组才抛 AssertionError ——
    #      这是 D47「变异必须落在真实文件形态上」那条规矩的机器化版本。
    miss = [title for title, rel, old, _n, _w in CASES if old not in backup(rel)]
    if miss:
        print("★ 变异模式未命中（多半是被测文件改了、控制组没跟上）：")
        for m in miss:
            print("   -", m)
        return 2

    bad = 0
    for title, rel, old, new, want in CASES:
        try:
            backup(rel)
            apply_variant(rel, old, new)
            rc, fails, out = run_guard()
            hit = set(fails)
            missing = [w for w in want if w not in hit]
            ok = (rc != 0) and not missing
            print("[%s] %s" % ("OK  " if ok else "BAD ", title))
            print("       期望命中 %s | 实际命中 %s" % (want, sorted(hit) or "无"))
            if not ok:
                print("       rc=%s 缺失=%s" % (rc, missing or "无"))
                bad += 1
        finally:
            reset_all()

    # ── 收尾：还原后必须与基线完全一致（防止变异残留污染仓库） ──
    rc2, fails2, _out2 = run_guard()
    clean = (rc2 == 0 and not fails2)

    # ★ 判据是「有没有【多出来】的改动」，不是「工作区干不干净」——
    #   本控制组常在工作区本来就有改动时跑（本轮的真实改动还没提交）。
    dirty1 = git_dirty()
    extra = sorted(set(dirty1) - set(dirty0))
    gone = sorted(set(dirty0) - set(dirty1))

    print("=" * 78)
    print("还原后重跑护栏：rc=%s 失败=%s  ⇒ %s" % (rc2, fails2 or "无", "干净" if clean else "★ 不干净"))
    print("启动时工作区已有 %d 处改动（本轮真实改动，不算残留）" % len(dirty0))
    print("多出来的改动（＝变异残留）：%s" % (extra or "无"))
    print("意外消失的改动：%s" % (gone or "无"))
    print("")
    if bad:
        print("VERDICT: FAIL —— 有 %d 组变异不符预期" % bad)
        return 1
    if not clean:
        print("VERDICT: FAIL —— 还原后护栏仍不绿，有变异残留")
        return 1
    if extra or gone:
        print("VERDICT: FAIL —— 工作区改动集合与启动时不一致")
        return 1
    print("VERDICT: PASS —— %d 组变异全部按预期命中，且还原干净" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
