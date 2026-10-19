# -*- coding: utf-8 -*-
"""前端 ESLint 的控制组（参数化版：两个应用都能跑）。

跑法：
    python _d53_admin_fe_ctrl.py            # 默认 admin-app
    python _d53_admin_fe_ctrl.py mall-app   # 也可回跑 C 端

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，
  脚本必须失败；失败数 = 0 就说明什么都没守住。

探针一次带 4 种违规，对应 eslint.config.mjs 里的 4 条规则：
  ① console.log          → no-console（warn 级，靠 --max-warnings 0 升级成失败）
  ② : any                → @typescript-eslint/no-explicit-any（error）
  ③ debugger             → no-debugger（error）
  ④ v-html               → vue/no-v-html（error）

⚠️ 探针文件名【不能】以 `.` 开头（ESLint 默认忽略点文件），也不能落在任何豁免里
   —— Day 47 就栽在「探针名正好命中自己的豁免规则」上。
⚠️ 探针里【不能】带 `eslint-disable` 注释 —— 那等于自己把要测的规则关掉
   （Day 48 第一版在 no-debugger 与 v-html 上都犯过）。
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP_NAME = sys.argv[1] if len(sys.argv) > 1 else "admin-app"
APP = os.path.join("D:", os.sep, "MallX", "frontend", APP_NAME)
NPM = r"C:\Program Files\nodejs\npm.cmd"
PROBE_TS = os.path.join(APP, "src", "__lint_probe__.ts")
PROBE_VUE = os.path.join(APP, "src", "__lint_probe__.vue")

PROBE_TS_SRC = """// 临时探针：违规各一处（控制组用，跑完即删）—— 刻意不带任何豁免注释
export function probe(): any {
  debugger
  console.log('probe')
  return 1
}
"""

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
    print("ESLint 控制组 · %s" % APP_NAME)
    print("=" * 74)

    # ① 基线：干净代码必须 pass
    rc, problems, _ = run_lint()
    print("\n[基线] rc=%s problems=%d %s" % (rc, len(problems), "OK" if rc == 0 else "★"))
    if rc != 0:
        print("★ 基线就不干净 ⇒ 先修存量，再谈控制组")
        for line, col, sev, msg, rule in problems:
            print("      %s:%s %-7s %s" % (line, col, sev, rule))
        return 1

    # ② 探针：4 种违规必须被抓到
    assert write(PROBE_TS, PROBE_TS_SRC), "probe ts write failed"
    assert write(PROBE_VUE, PROBE_VUE_SRC), "probe vue write failed"
    rc, problems, _ = run_lint()
    for p in (PROBE_TS, PROBE_VUE):
        if os.path.exists(p):
            os.remove(p)

    rules_hit = sorted({p[4] for p in problems})
    print("\n[探针] rc=%s problems=%d" % (rc, len(problems)))
    for line, col, sev, msg, rule in problems:
        print("      %s:%s %-7s %s" % (line, col, sev, rule))

    # ★ 规则名要用 ESLint 实际输出的全名（带 scope）—— Day 48 第一版写 "no-explicit-any"
    #   而实际是 "@typescript-eslint/no-explicit-any"，于是明明命中却判成「缺」。
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
