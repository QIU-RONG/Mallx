# -*- coding: utf-8 -*-
"""admin-app 三个单测文件的【控制组】：证明这 21 条断言真的有牙。

跑法：python _d53_admin_unit_ctrl.py      （约 1 分钟：7 组 × 一次 vitest，无需构建）

★ 项目铁律：新写的护栏必须自带控制组 —— 拿【已知有问题的版本】回跑，必须红；
  失败数 = 0 就说明那条断言什么都没守住。

七组变异，每组都对应一个「真实会犯的错」：

  ① http.ts  403 也走 gotoLogin  → 「HTTP 403」那条必须红
     （管理端 403 是常态：运营点错一个菜单就被踢出后台，且不会报错、不会告警）
  ② http.ts  业务 401 只提示不踢登录 → 「code=401」必须红
  ③ auth.ts  去掉 type==='ADMIN' 判断 → 「type=USER」必须红
     （C 端 token 混进后台，前端会把越权尝试显示成一堆空白按钮）
  ④ auth.ts  logout 漏清 localStorage → 「清内存 + 清 localStorage」必须红
     （刷新后又登进去了）
  ⑤ auth.ts  restore() 变空操作 → 「只有 token 在 localStorage 时」必须红
     （刷新后所有按钮消失）
  ⑥ router  去掉 auth.restore() → 「每次导航都调 restore」必须红
  ⑦ router  未登录也放行 → 「未登录访问受保护页」必须红

⚠️ 两个已知坑（Day 48 踩过，这里预防）：
  · 用 `npm run test` 走 subprocess 会让 vitest **V8 堆溢出** ⇒ 直接用 node 跑 vitest.mjs
  · vitest 的管道输出带 **ANSI 色码**，不剥掉任何正则都匹配不上
  · Java/TS 源码可能是 CRLF，多行变异模式要按实际换行风格转换
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = os.path.join("D:", os.sep, "MallX", "frontend", "admin-app")
VITEST = os.path.join(APP, "node_modules", "vitest", "vitest.mjs")
HTTP = os.path.join(APP, "src", "api", "http.ts")
AUTH = os.path.join(APP, "src", "stores", "auth.ts")
ROUTER = os.path.join(APP, "src", "router", "index.ts")

EXPECTED_TOTAL = 21

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# (说明, 文件, 原文, 改后, 必须红的测试名片段)
CASES = [
    ("① http.ts：403 也走 gotoLogin（把「无权限」当「未登录」）",
     HTTP,
     "      ElMessage.error('权限不足：当前账号没有该操作的权限码')",
     "      gotoLogin('权限不足：当前账号没有该操作的权限码')",
     "HTTP 403"),

    ("② http.ts：业务 401 只提示、不踢登录（登录态过期没人管了）",
     HTTP,
     "        gotoLogin('登录已过期，请重新登录')",
     "        ElMessage.error('登录已过期，请重新登录')",
     "code=401"),

    ("③ auth.ts：去掉 type==='ADMIN' 判断（C 端 token 也能混进后台）",
     AUTH,
     "      if (claims.type !== 'ADMIN') return []",
     "      if (false) return []",
     "type=USER"),

    ("④ auth.ts：logout 漏清 localStorage（刷新后又登进去了）",
     AUTH,
     "    localStorage.removeItem(TOKEN_KEY)\n    localStorage.removeItem(USER_KEY)",
     "    // mutated: 不清 storage",
     "清内存 + 清 localStorage"),

    ("⑤ auth.ts：restore() 变空操作（刷新后所有按钮消失）",
     AUTH,
     "    if (token.value) perms.value = decodePerms(token.value)",
     "    // mutated",
     "只有 token 在 localStorage 时"),

    ("⑥ router：去掉 auth.restore()（perms 永远恢复不了）",
     ROUTER,
     "  auth.restore()\n",
     "",
     "每次导航都调 restore"),

    ("⑦ router：未登录也放行（后台裸奔）",
     ROUTER,
     "  if (to.path !== '/login' && !auth.isLogin) {\n    return '/login'\n  }\n",
     "",
     "未登录访问受保护页"),
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
    assert o in s, "变异模式在 %s 里找不到（CRLF=%s）：\n%s" % (os.path.basename(path), crlf, o[:120])
    assert write(path, s.replace(o, n, 1)), "写回后内容不一致：%s" % path


def revert(path):
    assert write(path, _BASE[path]), "还原后内容不一致：%s" % path


def run_tests():
    p = subprocess.run(["node", VITEST, "run"], cwd=APP, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
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
    print("admin-app 单测控制组：%d 组变异（每组 = 改坏一处 → 回跑 → 必须红）" % len(CASES))
    print("=" * 78)

    if not os.path.exists(VITEST):
        print("★ 前提不成立：没找到 %s ⇒ 先 npm install（这是环境问题，rc=2）" % VITEST)
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
        ok = bool(hit) and rc != 0
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
    # 收尾：全部还原后必须回到基线
    dirty = [p for p in _BASE if read(p) != _BASE[p]]
    for p in _BASE:
        print("  %-18s 还原%s" % (os.path.basename(p), "干净" if p not in dirty else "★ 不干净"))
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
