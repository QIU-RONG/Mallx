# -*- coding: utf-8 -*-
"""Day 55 后端单测（ReviewServiceImplTest）的控制组：证明这 9 条断言真的有牙。

跑法：python _d55_review_unit_ctrl.py       （约 2 分钟：3 组 × 一次 mvn test）

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，必须红；
  失败数 = 0 就说明那条断言什么都没守住（假绿）。

三组变异，每组对应一个「真实会犯的错」：

  ① pageAdmin 去掉 size 上限（Math.min(..., MAX_PAGE_SIZE)）
     → sizeIsCappedAt100 必须红
     （size=9999 不被截断 = 一次请求拖走整张评价表；它不报错、不 500）
  ② updateStatus 不再判「影响 0 行」
     → notFoundThrows404 必须红
     （改一个不存在的 id 静默返回成功，运营以为已处理）
  ③ updateStatus 去掉「status 只能是 0/1」判据
     → illegalStatusThrows400 必须红
     （DTO 之外的第二道锁：绕过接口直接调 Service 时，2 会被当成「随便一个值」写进库）

⚠️ 与 Day 48/53/54 同一套实现细节：写完读回校验、收尾必须回基线。
"""
import io
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = os.path.join("D:", os.sep, "MallX", "backend", "mallx")
IMPL = os.path.join(APP, "mall-review", "src", "main", "java", "com", "mallx",
                    "review", "service", "impl", "ReviewServiceImpl.java")

# ★ Windows 上 mvn 是 .cmd —— subprocess 直接 exec 会 WinError 2（不会走 PATHEXT），
#   必须交给 cmd.exe（shell=True）。路径从 PATH 里找，别写死版本号。
MVN = shutil.which("mvn.cmd") or shutil.which("mvn") or "mvn.cmd"

EXPECTED_TOTAL = 9

# (说明, 原文, 改后, 必须红的测试方法名)
CASES = [
    ("① pageAdmin 去掉 size 上限（9999 不再被截断成 100）",
     "        long safePage = Math.max(page, 1);\n"
     "        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);\n"
     "\n"
     "        // ② 三个过滤都可能为 null —— 由 XML 的 <if> 决定是否拼进 WHERE",
     "        long safePage = Math.max(page, 1);\n"
     "        long safeSize = Math.max(size, 1);\n"
     "\n"
     "        // ② 三个过滤都可能为 null —— 由 XML 的 <if> 决定是否拼进 WHERE",
     "sizeIsCappedAt100"),

    ("② updateStatus 不再判「影响 0 行」（不存在的 id 静默成功）",
     "        int rows = reviewMapper.updateReviewStatus(id, status);\n"
     "        if (rows == 0) {\n"
     "            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), \"评价不存在\");\n"
     "        }",
     "        reviewMapper.updateReviewStatus(id, status);",
     "notFoundThrows404"),

    ("③ updateStatus 去掉 status ∈ {0,1} 判据（2 也能写进库）",
     "if (status == null || (status != 0 && status != 1)) {",
     "if (status == null) {",
     "illegalStatusThrows400"),
]

_BASE = None


def read(path):
    return io.open(path, encoding="utf-8", newline="").read()


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    return read(path) == text  # ★ 写完读回校验（本项目踩过「write 成功但没落盘」）


def patch(old, new):
    global _BASE
    if _BASE is None:
        _BASE = read(IMPL)
    crlf = "\r\n" in _BASE
    o = old.replace("\n", "\r\n") if crlf else old
    n = new.replace("\n", "\r\n") if crlf else new
    assert o in _BASE, "变异模式在 ReviewServiceImpl.java 里找不到（CRLF=%s）：\n%s" % (crlf, o[:200])
    assert write(IMPL, _BASE.replace(o, n, 1)), "写回后内容不一致"


def revert():
    assert write(IMPL, _BASE), "还原后内容不一致"


def run_tests():
    cmd = ('"%s" -o -pl mall-review -am test -Dtest=ReviewServiceImplTest'
           ' -Dsurefire.failIfNoSpecifiedTests=false' % MVN)
    p = subprocess.run(cmd, cwd=APP, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1200)
    out = (p.stdout or "") + (p.stderr or "")
    runs = re.findall(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)", out)
    if not runs:
        return p.returncode, -1, -1, out
    # ★ 输出里有多处 "Tests run"：每个 @Nested 类一段、parent 类一段、最后 "Results:" 一段。
    #   要的是最后那段（整体汇总）；累加会把同一个测试数成两遍（首跑实测 9 → 18）。
    total, failed, errors = (int(x) for x in runs[-1])
    return p.returncode, total, failed + errors, out


def main():
    print("=" * 78)
    print("Day 55 · ReviewServiceImplTest 控制组：%d 组变异" % len(CASES))
    print("=" * 78)

    rc, total, failed, out = run_tests()
    print("\n[基线] rc=%s tests=%s failed=%s" % (rc, total, failed))
    if rc != 0 or failed != 0 or total != EXPECTED_TOTAL:
        print("★ 基线不绿（或条数不是 %d）⇒ 先修测试，别做变异" % EXPECTED_TOTAL)
        print(out[-2500:])
        return 2
    print("  ⇒ 基线全绿，可以做变异\n")

    bad = 0
    for i, (desc, old, new, must) in enumerate(CASES, 1):
        print("-" * 78)
        print("第 %d 组 · %s" % (i, desc))
        patch(old, new)
        rc, total, failed, out = run_tests()
        revert()

        hit = must in out
        print("  红掉 %s 条，命中「%s」：%s" % (failed, must, "✅" if hit else "★ 没命中"))
        if not hit:
            print("  ★★ 这条断言【什么都没守住】（假绿）—— 变异后测试仍然全绿")
            print(out[-2000:])
            bad += 1

    print("-" * 78)
    print("  ReviewServiceImpl.java 还原%s" % ("干净" if read(IMPL) == _BASE else "★ 不干净"))
    rc, total, failed, out = run_tests()
    print("\n[收尾] rc=%s tests=%s failed=%s %s"
          % (rc, total, failed, "✅" if (rc == 0 and failed == 0) else "★"))

    if bad or read(IMPL) != _BASE or rc != 0:
        print("\nVERDICT: FAIL —— %d 组不符预期" % bad)
        return 1
    print("\nVERDICT: PASS —— %d 组变异全部命中，且还原干净" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
