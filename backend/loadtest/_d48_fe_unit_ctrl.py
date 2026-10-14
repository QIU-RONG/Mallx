# -*- coding: utf-8 -*-
"""Day 48 · 前端单测的控制组（证明 http/auth/router 那 15 条真的有牙）。

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，
  脚本必须失败；失败数 = 0 就说明什么都没守住。

6 组变异，每组对应一类「改一个公共文件弄坏一片页面、而类型检查和构建都看不出来」的事故：

  ① http：协议层 401 不再踢回登录页        → 应红「HTTP 401 → 同样三件事」
  ② http：业务 401 与其它业务失败同一处理   → 应红「code=401 → 三件事」
  ③ auth：logout 不清 localStorage          → 应红「logout 后三项全部移除」
  ④ auth：setAuth 不写 localStorage          → 应红「setAuth 后三项落盘」+「刷新恢复」
  ⑤ router：守卫不带 redirect query          → 应红「redirect 带回原路径」
  ⑥ router：守卫不再检查 requiresAuth        → 应红「未登录被拦截」+「redirect」

⚠️ 前端源文件是 LF（本项目 Write/Edit 工具产物），但为通用起见仍按字节探测换行风格。
⚠️ 变异必须【先备份再写】+【写完读回校验】+【跑完还原再读回校验】——
   上一轮后端控制组就栽在「写成功但内容没变，导致后面几组失败数累积」。
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = os.path.join("D:", os.sep, "MallX", "frontend", "mall-app")
NPM = r"C:\Program Files\nodejs\npm.cmd"

HTTP = "src/api/http.ts"
AUTH = "src/stores/auth.ts"
ROUTER = "src/router/index.ts"

_backup = {}
results = []


def _path(rel):
    return os.path.join(APP, rel.replace("/", os.sep))


def _nl(rel):
    with open(_path(rel), "rb") as f:
        return "\r\n" if b"\r\n" in f.read() else "\n"


def read(rel):
    return io.open(_path(rel), encoding="utf-8").read()


def write(rel, text):
    io.open(_path(rel), "w", encoding="utf-8", newline=_nl(rel)).write(text)
    return io.open(_path(rel), encoding="utf-8").read() == text


def mutate(rel, old, new):
    if rel not in _backup:
        _backup[rel] = read(rel)
    s = _backup[rel]
    assert old in s, "pattern not found in %s:\n%s" % (rel, old[:160])
    assert write(rel, s.replace(old, new, 1)), "WRITE DID NOT LAND: %s" % rel


def restore(rel):
    assert write(rel, _backup[rel]), "RESTORE DID NOT LAND: %s" % rel


def run_tests():
    # ★★ 用 node 直跑 vitest.mjs，不经过 npm：
    #   实测 subprocess 调 `npm run test` 会在 vitest 启动时 V8 堆溢出（rc=134），
    #   而同一命令在 PowerShell 里跑是好的 —— 差别在 npm 多包的那层进程/环境。
    #   ⇒ 自动化脚本一律 `node node_modules/vitest/vitest.mjs run`。
    p = subprocess.run(["node", "node_modules/vitest/vitest.mjs", "run"],
                       cwd=APP, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    # ★★ vitest 即使输出到管道也带 ANSI 颜色码（\x1b[32m…），
    #   「Tests」和「15 passed」之间就夹着颜色码 ⇒ 不先剥掉，任何正则都匹配不上。
    #   第一版就栽在这：基线明明是 15 passed，解析出来却是 -1。
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
    # vitest 汇总行是 `Tests  2 failed | 13 passed (15)` —— 数字在 passed/failed 【前面】
    m = re.search(r"Tests\s+(?:(\d+)\s+failed\s*\|\s*)?(\d+)\s+passed", clean)
    total = int(m.group(2)) if m else -1
    failed_names = re.findall(r"^\s*FAIL\s+(src/\S+)\s*>\s*(.+?)\s*$", clean, re.M)
    return p.returncode, total, sorted({"%s > %s" % (a, b) for a, b in failed_names}), clean


def case(title, rel, old, new, expect):
    mutate(rel, old, new)
    rc, total, failed, out = run_tests()
    restore(rel)
    ok = (rc != 0) and len(failed) >= len(expect)
    results.append((ok, title, rc, total, failed, expect))
    print("\n%s  %s" % ("[OK]  " if ok else "[BAD] ", title))
    print("      rc=%s tests=%s failed=%d" % (rc, total, len(failed)))
    for f in failed[:6]:
        print("        · %s" % f[:90])
    if not ok:
        print("      ★ 期望至少红 %d 条：%s" % (len(expect), expect))


def main():
    print("=" * 74)
    print("Day 48 · mall-app 前端单测控制组（vitest）")
    print("=" * 74)

    rc, total, failed, _ = run_tests()
    print("\n[基线] rc=%s tests=%s failed=%d" % (rc, total, len(failed)))
    if rc != 0:
        print("★ 基线就不绿 ⇒ 先修测试")
        return 1
    if total != 15:
        print("★ 基线 15 条，实得 %s ⇒ 有测试没被创建" % total)
        return 1

    # ① 协议层 401 只提示、不踢回登录页
    case("① http：协议层 401 不再 gotoLogin", HTTP,
         """    const st = err.response?.status
    if (st === 401) {
      gotoLogin('请先登录')
    } else if (st === 403) {""",
         """    const st = err.response?.status
    if (st === 403) {""",
         ["HTTP 401"])

    # ② 业务 401 与其它业务失败同一处理
    case("② http：业务 401 不再特殊处理", HTTP,
         """      if (body.code === 401) {
        gotoLogin('登录已过期，请重新登录')
      } else {
        ElMessage.error(body.message || `操作失败（code=${body.code}）`)
      }""",
         """      ElMessage.error(body.message || `操作失败（code=${body.code}）`)""",
         ["code=401"])

    # ③ logout 不清 localStorage
    case("③ auth：logout 不清 localStorage（刷新后假登录）", AUTH,
         """    localStorage.removeItem('mall_token')
    localStorage.removeItem('mall_username')
    localStorage.removeItem('mall_nickname')""",
         """    // 变异：只清内存，不清持久化""",
         ["logout"])

    # ④ setAuth 不写 localStorage
    case("④ auth：setAuth 不写 localStorage（刷新丢登录态）", AUTH,
         """    localStorage.setItem('mall_token', t)
    localStorage.setItem('mall_username', u)
    localStorage.setItem('mall_nickname', nickname.value)""",
         """    // 变异：只写内存，不持久化""",
         ["setAuth", "恢复"])

    # ⑤ 守卫不带 redirect
    case("⑤ router：守卫不带 redirect query", ROUTER,
         "    return { path: '/login', query: { redirect: to.fullPath } }",
         "    return { path: '/login' }",
         ["redirect"])

    # ⑥ 守卫不再检查 requiresAuth
    case("⑥ router：守卫不再检查 requiresAuth", ROUTER,
         """  if (to.meta.requiresAuth && !auth.token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true""",
         """  return true""",
         ["未登录"])

    dirty = [rel for rel in _backup if read(rel) != _backup[rel]]
    print("\n" + "=" * 74)
    print("还原检查：%s" % ("干净 ✅" if not dirty else "★ 仍有改动 → %s" % dirty))
    bad = [r for r in results if not r[0]]
    print("控制组：%d 组，符合预期 %d 组" % (len(results), len(results) - len(bad)))
    for ok, title, rc, total, failed, expect in results:
        print("  %s 红 %d 条  %s" % ("[OK] " if ok else "[BAD]", len(failed), title[:48]))
    print("VERDICT: %s" % ("OK —— 每一组都按预期响" if not bad and not dirty
                           else "FAIL"))
    return 0 if (not bad and not dirty) else 1


if __name__ == "__main__":
    sys.exit(main())
