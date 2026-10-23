# -*- coding: utf-8 -*-
"""Day 54 新增单测的【控制组】：证明这 26 条断言真的有牙。

跑法：python _d54_admin_unit_ctrl.py     （约 3 分钟：5 组 × 一次 vitest，无需构建）

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，必须红；
  失败数 = 0 就说明那条断言什么都没守住（假绿）。

五组变异，每组都对应一个「真实会犯的错」：

  ① menu.ts   去掉权限码过滤          → 「没有 perms → 只剩 3 个底座入口」必须红
     （入口对所有人可见，运营点进去才发现 403 —— 管理端 403 还不会告警）
  ② coupon.ts FIXED 也下发 discountRate → 「FIXED → 绝不带 discountRate」必须红
     （后端关系校验 400，报错却叫「不能同时填写」，用户会说「我明明没填」）
  ③ coupon.ts 去掉折扣率上限 1        → 「折扣率边界」必须红
     （0.88 被当成 88% 还是 8.8% 的经典口径事故，见 Day 21 的 D21-A）
  ④ confirm.ts 取消也返回 true        → 「取消 → false」必须红
     （★ 已经发生过：点「再想想」照样执行退款）
  ⑤ tree.ts   去掉全角空格缩进        → 「子级按深度前缀」必须红
     （两级分类在下拉里看起来是平级，选错父分类）

⚠️ 与 Day 53 同一套实现细节：直接 node 跑 vitest.mjs（npm run test 会 V8 堆溢出）、
   输出剥 ANSI、写完读回校验、收尾必须回基线。
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = os.path.join("D:", os.sep, "MallX", "frontend", "admin-app")
VITEST = os.path.join(APP, "node_modules", "vitest", "vitest.mjs")

MENU = os.path.join(APP, "src", "utils", "menu.ts")
COUPON = os.path.join(APP, "src", "utils", "coupon.ts")
CONFIRM = os.path.join(APP, "src", "utils", "confirm.ts")
TREE = os.path.join(APP, "src", "utils", "tree.ts")

# ★ 全库测试总数（Day 53 的 21 + Day 54 的 26 + Day 55 的 menu 新用例 1 = 48）；改动测试时必须同步这里
EXPECTED_TOTAL = 48

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# (说明, 文件, 原文, 改后, 必须红的测试名片段)
CASES = [
    ("① menu.ts：去掉权限码过滤（所有人看见全部入口）",
     MENU,
     "  return ADMIN_MENUS.filter((m) => !m.perm || perms.includes(m.perm))",
     "  return [...ADMIN_MENUS]",
     "没有 perms"),

    ("② coupon.ts：FIXED 也下发 discountRate（后端关系校验 400）",
     COUPON,
     "return { ok: true, payload: { ...base, discountAmount: form.discountAmount } }",
     "return { ok: true, payload: { ...base, discountAmount: form.discountAmount, discountRate: form.discountRate ?? undefined } }",
     "FIXED → 带 discountAmount"),

    ("③ coupon.ts：去掉折扣率上限 1（1.01 也能建出来）",
     COUPON,
     "if (form.discountRate == null || form.discountRate <= 0 || form.discountRate > 1) {",
     "if (form.discountRate == null || form.discountRate <= 0) {",
     "折扣率边界"),

    ("④ confirm.ts：取消也返回 true（★ 点「再想想」照样执行退款）",
     CONFIRM,
     "  } catch {\n    // 取消、点 X、按 ESC 都走这里 —— 一律视为「不做」\n    return false\n  }",
     "  } catch {\n    return true\n  }",
     "用户点「取消」"),

    ("⑤ tree.ts：去掉全角空格缩进（两级分类看起来是平级）",
     TREE,
     "out.push({ ...c, name: `${'　'.repeat(depth)}${c.name}` })",
     "out.push({ ...c, name: c.name })",
     "子级按深度前缀"),
]

_BASE = {}


def read(path):
    return io.open(path, encoding="utf-8", newline="").read()


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    return read(path) == text  # ★ 写完读回校验（本项目踩过「write 成功但没落盘」）


def patch(path, old, new):
    if path not in _BASE:
        _BASE[path] = read(path)
    s = _BASE[path]
    crlf = "\r\n" in s
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    assert o in s, "变异模式在 %s 里找不到（CRLF=%s）：\n%s" % (os.path.basename(path), crlf, o[:160])
    assert write(path, s.replace(o, n, 1)), "写回后内容不一致：%s" % path


def revert(path):
    assert write(path, _BASE[path]), "还原后内容不一致：%s" % path


def run_tests():
    p = subprocess.run(["node", VITEST, "run"], cwd=APP, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=900)
    out = ANSI.sub("", (p.stdout or "") + (p.stderr or ""))
    m = re.search(r"Tests\s+(?:(\d+)\s+failed\s*\|\s*)?(\d+)\s+passed", out)
    failed = int(m.group(1)) if (m and m.group(1)) else 0
    passed = int(m.group(2)) if m else -1
    names = set()
    for mm in re.finditer(r"^\s*(?:FAIL|×|✕)\s+(.+?)\s*$", out, re.M):
        txt = mm.group(1)
        if ">" in txt:
            txt = txt.split(">")[-1]
        names.add(txt.strip())
    return p.returncode, passed, failed, names, out


def main():
    print("=" * 78)
    print("Day 54 单测控制组：%d 组变异（每组 = 改坏一处 → 回跑 → 必须红）" % len(CASES))
    print("=" * 78)

    if not os.path.exists(VITEST):
        print("★ 前提不成立：没找到 %s ⇒ 先 npm install（环境问题，rc=2）" % VITEST)
        return 2

    rc, passed, failed, names, out = run_tests()
    print("\n[基线] rc=%s passed=%s failed=%s" % (rc, passed, failed))
    if rc != 0 or failed or passed != EXPECTED_TOTAL:
        print("★ 基线不绿（或条数不是 %d）⇒ 先修测试，别做变异" % EXPECTED_TOTAL)
        for n in sorted(names):
            print("   ×", n)
        print(out[-1500:])
        return 2
    print("  ⇒ 基线全绿，可以做变异\n")

    bad = 0
    for i, (desc, path, old, new, must) in enumerate(CASES, 1):
        print("-" * 78)
        print("第 %d 组 · %s" % (i, desc))
        patch(path, old, new)
        rc, passed, failed, names, _ = run_tests()
        revert(path)

        hit = [n for n in names if must in n]
        print("  红掉 %d 条，命中「%s」：%s" % (failed, must, "✅" if hit else "★ 没命中"))
        if not hit:
            print("  ★★ 一条都没红 ⇒ 这条断言【什么都没守住】（假绿）")
            for n in sorted(names):
                print("     实际红：", n)
            bad += 1
        else:
            for n in hit:
                print("     ×", n)

    print("-" * 78)
    dirty = [p for p in _BASE if read(p) != _BASE[p]]
    for p in _BASE:
        print("  %-14s 还原%s" % (os.path.basename(p), "干净" if p not in dirty else "★ 不干净"))
    rc, passed, failed, names, _ = run_tests()
    print("\n[收尾] rc=%s passed=%s failed=%s %s"
          % (rc, passed, failed, "✅" if (rc == 0 and failed == 0) else "★"))

    if bad or dirty or rc != 0:
        print("\nVERDICT: FAIL —— %d 组不符预期，%d 个文件还原不干净" % (bad, len(dirty)))
        return 1
    print("\nVERDICT: PASS —— %d 组变异全部命中，且还原干净" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
