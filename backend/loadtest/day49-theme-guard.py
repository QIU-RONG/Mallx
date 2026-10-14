# -*- coding: utf-8 -*-
"""
Day 49 主题一致性护栏（纯静态，秒级，不需要 build / DB / 应用）。

★★ 为什么需要它

  「主色」这件事被钉在【五处】：
    ① mall-app/src/styles/theme.css 的 --el-color-primary 与六个色阶
    ② admin-app/src/styles/theme.css 的同一组
    ③ 两个 main.ts 里 theme.css 与 element-plus/index.css 的【加载顺序】
       （顺序反了 → 覆盖失效，但 lint / build 全绿）
    ④ 两个应用的品牌色 / 价格色是否一致
    ⑤ 源码里残留的硬编码色值

  这五处任何一处漂了，症状都只是「页面看着不对劲」，而
  eslint / vue-tsc / vite build **全都不报错** —— 与后端「权限总数钉在 5 处」
  完全同类（见 day47-perm-count-guard.py）。

★★ 最硬的一条是 A2

  它【不比对「我写的值」】，而是按 Element Plus 的混色规律从主色<b>推导</b>出
  六个色阶再比对：
      light-N = 主色 + (255-主色) × N/10
      dark-2  = 主色 × 0.8
  ⇒ 只手改 --el-color-primary 会被它当场抓住。症状是「按钮 hover 时跳回蓝色」，
     因为 hover 取的是 light-3 —— 这种错只改一个值、静态截图还看不出来，
     不写公式就测不到。

★ 前提护栏（rc=2）

  两个 theme.css / main.ts 必须存在。**读不到时判「前提不成立」而不是「断言失败」**：
  护栏第一版就把路径前缀写漏了（少了 frontend/），于是 5 条断言全报「缺失」，
  看起来像「主题全面漂移」—— 把环境错误伪装成业务错误，是最误导的一种红。

运行：python day49-theme-guard.py             （纯静态）
      python day49-theme-guard.py --selfcheck （AST 核对满额断言常量）
"""

import ast
import io
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(SCRIPT_DIR))

APPS = ("mall-app", "admin-app")
THEME_REL = "src/styles/theme.css"
MAIN_REL = "src/main.ts"

EXPECTED_CHECKS = 6

# 旧主题（橙色系）与 EP 默认蓝 —— 出现即代表「换色没换干净」
STALE_VALUES = (
    "#ff6a00", "#ff8c33", "#e65f00", "#fff7f0",   # 上一版橙色主题
    "#409eff", "#79bbff",                          # Element Plus 默认蓝
    "255, 106, 0",                                 # 旧橙的 rgba 写法
)

LEVELS = ("light-3", "light-5", "light-7", "light-8", "light-9")
DARK = "dark-2"

_fails = []


def chk(name, ok, detail=""):
    print("[%s] %s%s" % ("OK  " if ok else "FAIL", name, ("   " + detail) if detail else ""))
    if not ok:
        _fails.append(name)
    return ok


# ---------------------------------------------------------------- 基础工具

def app_path(app, rel):
    return os.path.join(REPO, "frontend", app, rel.replace("/", os.sep))


def read_rel(rel):
    """相对仓库根读文件（给源码扫描用）。"""
    p = os.path.join(REPO, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return None
    return io.open(p, encoding="utf-8", errors="replace").read()


def parse_css_vars(text):
    """抓 `--name: value` 的【最后一个】定义（后者覆盖前者，与浏览器一致）。"""
    d = {}
    for m in re.finditer(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;}]+)", text):
        d[m.group(1).strip()] = m.group(2).strip()
    return d


def hex2rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb2hex(r, g, b):
    return "#%02x%02x%02x" % (r, g, b)


def lighten(base, n):
    """EP 规律：light-N = 主色与白按 N/10 混合。"""
    r, g, b = hex2rgb(base)
    f = n / 10.0
    return rgb2hex(round(r + (255 - r) * f), round(g + (255 - g) * f), round(b + (255 - b) * f))


def darken(base, n):
    """EP 规律：dark-2 = 主色与黑按 n/10 混合。"""
    r, g, b = hex2rgb(base)
    f = 1 - n / 10.0
    return rgb2hex(round(r * f), round(g * f), round(b * f))


def near(a, b, tol=1):
    """逐通道容差比较 —— 手工取整会有 ±1 的差，但差一个色阶（十几）必须判失败。"""
    try:
        ra, ga, ba = hex2rgb(a)
        rb, gb, bb = hex2rgb(b)
    except Exception:
        return False
    return abs(ra - rb) <= tol and abs(ga - gb) <= tol and abs(ba - bb) <= tol


def blank_out(m):
    """把匹配到的内容替换成等长空白 —— 保留换行与行号，便于按行报告。"""
    return re.sub(r"[^\n]", " ", m.group(0))


def strip_comments(text):
    """去掉 /* */、<!-- -->、// 注释，但【保持行号不变】。"""
    text = re.sub(r"/\*.*?\*/", blank_out, text, flags=re.S)
    text = re.sub(r"<!--.*?-->", blank_out, text, flags=re.S)
    text = re.sub(r"^[ \t]*//.*$", blank_out, text, flags=re.M)
    return text


# ---------------------------------------------------------------- 断言主体

def main():
    # ── 前提护栏：文件必须存在。不存在 = 前提不成立（rc=2），不是「断言失败」 ──
    required = [app_path(a, r) for a in APPS for r in (THEME_REL, MAIN_REL)]
    missing = [os.path.relpath(p, REPO).replace("\\", "/") for p in required
               if not os.path.exists(p)]
    if missing:
        print("★ 前提不成立：读不到以下文件 —— 这是路径/环境问题，不是「主题漂移」")
        for m in missing:
            print("   -", m)
        print("   (REPO=%s)" % REPO)
        return 2

    themes = {a: parse_css_vars(io.open(app_path(a, THEME_REL), encoding="utf-8").read())
              for a in APPS}
    mains = {a: io.open(app_path(a, MAIN_REL), encoding="utf-8").read() for a in APPS}

    # ── A1 主色存在，且两个应用【同值】（两套主色是「看着乱」的第一来源） ──
    primaries = {a: themes[a].get("--el-color-primary", "") for a in APPS}
    same = len({v.lower() for v in primaries.values() if v}) == 1 and all(primaries.values())
    chk("A1 两个应用的 --el-color-primary 都存在且同值",
        same, " | ".join("%s=%s" % (a, primaries[a] or "缺失") for a in APPS))

    base = primaries.get("mall-app") or "#000000"

    # ── A2 六个色阶成套，且【按公式从主色推导】得到（最硬的一条） ──
    bad = []
    for app in APPS:
        v = themes[app]
        for lv in LEVELS:
            key = "--el-color-primary-%s" % lv
            want = lighten(base, int(lv.split("-")[1]))
            got = v.get(key)
            if got is None:
                bad.append("%s %s 缺失" % (app, key))
            elif not near(got, want):
                bad.append("%s %s=%s 应为 %s" % (app, key, got, want))
        key = "--el-color-primary-%s" % DARK
        want = darken(base, 2)
        got = v.get(key)
        if got is None:
            bad.append("%s %s 缺失" % (app, key))
        elif not near(got, want):
            bad.append("%s %s=%s 应为 %s" % (app, key, got, want))
    chk("A2 ★六个色阶成套，且与主色按 EP 混色规律同源（只手改 primary 会在此现形）",
        not bad, "; ".join(bad) if bad else "由 %s 推导出的 6 个值全部吻合" % base)

    # ── A3 品牌色 = EP 主色（防止又分叉成「品牌一套、组件一套」） ──
    bad = []
    for app in APPS:
        bc = themes[app].get("--brand-color", "")
        if not bc:
            bad.append("%s --brand-color 缺失" % app)
        elif not near(bc, base):
            bad.append("%s --brand-color=%s 与 primary=%s 不一致" % (app, bc, base))
    chk("A3 --brand-color 与 --el-color-primary 同值（组件与品牌不会各说各话）",
        not bad, "; ".join(bad) if bad else "两应用均为 %s" % base)

    # ── A4 import 顺序：theme.css 必须排在 element-plus/dist/index.css【之后】 ──
    #    同选择器（:root）下 CSS 变量看先后，反了就是「改了没效果」
    bad = []
    for app in APPS:
        t = mains[app]
        i_ep = t.find("element-plus/dist/index.css")
        i_theme = t.find("./styles/theme.css")
        if i_ep < 0:
            bad.append("%s 未引入 element-plus 样式" % app)
        elif i_theme < 0:
            bad.append("%s 未引入 theme.css" % app)
        elif i_theme < i_ep:
            bad.append("%s theme.css 在 EP 之前（覆盖会失效）" % app)
    chk("A4 theme.css 的 import 排在 Element Plus 样式之后（否则覆盖静默失效）",
        not bad, "; ".join(bad) if bad else "两应用顺序正确")

    # ── B1 源码里没有残留的旧主题色 / EP 默认蓝（排除注释） ──
    hits = []
    for app in APPS:
        src = os.path.join(REPO, "frontend", app, "src")
        for dirpath, _dirs, files in os.walk(src):
            for fn in files:
                if not fn.endswith((".vue", ".css", ".ts")):
                    continue
                p = os.path.join(dirpath, fn)
                stripped = strip_comments(io.open(p, encoding="utf-8", errors="replace").read())
                for i, line in enumerate(stripped.splitlines(), 1):
                    for v in STALE_VALUES:
                        if v in line:
                            hits.append("%s:%d %s" % (
                                os.path.relpath(p, REPO).replace("\\", "/"), i, v))
    chk("B1 源码非注释区没有残留的旧橙色 / EP 默认蓝",
        not hits, "; ".join(hits[:6]) + (" …" if len(hits) > 6 else "") if hits else "干净")

    # ── B2 价格色两个应用同值（金额长不一样会像两个产品） ──
    prices = {a: themes[a].get("--brand-price", "") for a in APPS}
    ok = all(prices.values()) and len({v.lower() for v in prices.values()}) == 1
    chk("B2 两个应用的 --brand-price 都存在且同值",
        ok, " | ".join("%s=%s" % (a, prices[a] or "缺失") for a in APPS))

    print("")
    print("断言 %d 条，失败 %d 条 ⇒ %s"
          % (EXPECTED_CHECKS, len(_fails), "VERDICT: PASS" if not _fails else "VERDICT: FAIL"))
    return 0 if not _fails else 1


def selfcheck():
    """AST 静态数本文件里 chk( 的调用点，与 EXPECTED_CHECKS 比对。

    ★ 只适用【顺序执行】的脚本；有 chk 落在循环体内时拒绝出结论（rc=2）。
    """
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        tree = ast.parse(f.read())

    def calls(node):
        return [n for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "chk"]

    sites = len(calls(tree))
    loops = sum(len(calls(n)) for n in ast.walk(tree)
                if isinstance(n, (ast.For, ast.While, ast.comprehension)))
    if loops:
        print("★ 有 %d 处 chk( 落在循环体内 ⇒ 静态核对不适用（拒绝出结论）" % loops)
        return 2
    ok = (sites == EXPECTED_CHECKS)
    print("chk( call sites = %d   EXPECTED_CHECKS = %d   %s"
          % (sites, EXPECTED_CHECKS, "OK" if ok else "★ MISMATCH -- 有断言被增删却没同步常量"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    sys.exit(main())
