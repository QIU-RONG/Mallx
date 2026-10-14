# -*- coding: utf-8 -*-
"""Day 48 · 前端 ESLint 的控制组（证明那 4 条规则真的有牙）。

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，
  脚本必须失败；失败数 = 0 就说明什么都没守住。

探针一次带 4 种违规，对应 eslint.config.mjs 里的 4 条规则：
  ① console.log          → no-console（warn 级，靠 --max-warnings 0 升级成失败）
  ② : any                → @typescript-eslint/no-explicit-any（error）
  ③ debugger             → no-debugger（error）
  ④ v-html               → vue/no-v-html（error）

⚠️ 探针文件名【不能】以 `.` 或 `_` 开头 —— ESLint 默认忽略点文件，
   而后端那次控制组就栽在「探针名落在自己的豁免规则里」（Day 47 的教训）。
   这里用 `__lint_probe__.ts`，双下划线开头，ESLint 不忽略它。
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = os.path.join("D:", os.sep, "MallX", "frontend", "mall-app")
NPM = r"C:\Program Files\nodejs\npm.cmd"
PROBE = os.path.join(APP, "src", "__lint_probe__.ts")

PROBE_SRC = """// 临时探针：4 种违规各一处（控制组用，跑完即删）
// ⚠️ 第一版在这里加了 `// eslint-disable-next-line no-debugger` —— 等于自己把要测的规则关掉，
//   控制组因此漏报 no-debugger。★ 探针必须是【干净地违规】，不能带任何豁免注释。
export function probe(): any {
  debugger
  console.log('probe')
  return 1
}
"""

PROBE_VUE = os.path.join(APP, "src", "__lint_probe__.vue")
# ⚠️ 同样不能带 eslint-disable 注释 —— 第一版在 v-html 上加了一行
#   `<!-- eslint-disable-next-line vue/no-v-html -->`，把要测的规则又关掉了。
PROBE_VUE_SRC = """<template>
  <div v-html="'<b>x</b>'" />
</template>

<script setup lang="ts">
console.log('x')
</script>
"""


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    return io.open(path, encoding="utf-8").read() == text


def run_lint():
    p = subprocess.run([NPM, "run", "lint"], cwd=APP, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    # 实际输出形如：  1:26  error    Unexpected any. ...    @typescript-eslint/no-explicit-any
    # message 与 rule 之间是【多个空格】，所以用 \s{2,} 切；rule 一定在行尾。
    problems = re.findall(r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.*?)\s{2,}(\S+)\s*$",
                          out, re.M)
    return p.returncode, problems, out


def main():
    print("=" * 74)
    print("Day 48 · mall-app ESLint 控制组")
    print("=" * 74)

    # ① 基线：干净代码必须 pass
    rc, problems, _ = run_lint()
    print("\n[基线] rc=%s problems=%d %s" % (rc, len(problems), "OK" if rc == 0 else "★"))
    if rc != 0:
        print("★ 基线就不干净 ⇒ 先修存量，再谈控制组")
        return 1

    # ② 探针：4 种违规必须被抓到
    assert write(PROBE, PROBE_SRC), "probe write failed"
    assert write(PROBE_VUE, PROBE_VUE_SRC), "probe vue write failed"
    rc, problems, out = run_lint()
    os.remove(PROBE)
    os.remove(PROBE_VUE)

    rules_hit = sorted({p[4] for p in problems})
    print("\n[探针] rc=%s problems=%d" % (rc, len(problems)))
    for line, col, sev, msg, rule in problems:
        print("      %s:%s %-7s %s" % (line, col, sev, rule))

    # ★ 规则名要写 ESLint 实际输出的全名 —— 第一版写 "no-explicit-any"，
    #   而实际输出是 "@typescript-eslint/no-explicit-any"（带 scope），
    #   于是明明命中了却被判成「缺」。探针命中的是 rule，判据也要用同一个字符串。
    want = ["no-console", "no-debugger", "@typescript-eslint/no-explicit-any", "vue/no-v-html"]
    missing = [r for r in want if r not in rules_hit]
    ok = (rc != 0) and not missing
    print("\n四条规则命中：%s" % ("全部 ✅" if not missing else "★ 缺 %s" % missing))
    print("退出码非 0（CI 会红）：%s" % ("✅" if rc != 0 else "★ 没红 ⇒ --max-warnings 0 没生效？"))

    # ③ 收尾：删掉探针后必须恢复干净
    rc2, problems2, _ = run_lint()
    print("\n[收尾] 探针已删，rc=%s problems=%d %s"
          % (rc2, len(problems2), "✅" if rc2 == 0 else "★ 还有残留"))
    ok = ok and rc2 == 0

    print("\n" + "=" * 74)
    print("VERDICT: %s" % ("OK —— 4 条规则都有牙，且探针清理后恢复干净"
                           if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
