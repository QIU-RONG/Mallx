# -*- coding: utf-8 -*-
"""Day 19 骨架门禁：搜索端点是否被路由到、字面量路径是否优先于 {id}、
   白名单是否只管 GET、以及基线是否未破。

★★ 与 Day 18 门禁最大的区别：**本脚本零写入**。
   Day 18 的门禁会真的打 POST/PUT/DELETE（实现填完后就成了破坏性脚本，出过事故），
   所以它必须带「骨架期护栏」。
   Day 19 新增的只有一条 GET —— 只读，无副作用。护栏仍然保留，但意义不同：
   它防的不是「写库」，而是把「实现已填完」误判成故障（那时 code 会是 200 而不是 500）。

本脚本回答四个问题，失败长相完全不同：

  `/api/products/search` 返回 code=500 → ★ **这就是要的答案**：
        路由命中了 search 方法（方法体是 TODO 的 throw），
        证明【字面量路径优先于 {id} 变量模式】。
  `/api/products/search` 返回 code=400 → ❌ **路由落到了 `{id}`**：
        "search" 转 Long 失败，被 MethodArgumentTypeMismatchException 接走。
        ⇒ 路径冲突没按预期解决，要改路径或改映射。
  `/api/products/search` 返回 404      → ❌ 路由根本没生效。

★★ 层级判据（本节是 Day 19 现场实测补上的）：
    **Security 过滤器链跑在 MVC 路由之前**。所以「匿名 POST /api/products/search」
    拿到的是 **401**，而不是 405 —— 它根本走不到「方法不被支持」那一步。
    只有【通过了认证】的请求才会抵达 MVC，那时才可能给出真实 405。
    ⇒ 白名单 `GET /api/products/**` 是【方法粒度】的：只放 GET，POST 仍要认证。
    实测证据（本脚本 [3] 节）：匿名 GET → 500（进方法体）、匿名 POST → 401（被 Security 拒）、
    带 token 的 POST → 405（到 MVC 才发现方法不支持，顺带回归 Day 18 补的 handler）。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = r"D:\MallX\backend\loadtest\day19-skeleton-smoke-report.txt"

# ★ 必须显式清空代理：本机系统代理会把 127.0.0.1 也拦下，
#   表现是 502 upstream connect failed (os error 10061) —— 不是服务挂了。
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 白名单红线（回归）：这几条必须【匿名可读】，且语义不许变。
WHITELIST_REDLINE = [
    ("GET", "/api/hello", "探活"),
    ("GET", "/api/products?current=1&size=1", "C 端商品列表（Day 09 口径）"),
    ("GET", "/api/products/1", "C 端商品详情"),
    ("GET", "/api/categories/tree", "C 端分类树"),
]

# ★ 层级断言表：(方法, 路径, 用哪个 token, 期望, 说明)
#   期望用 {"http": x} 或 {"http": x, "code": y}（body.code 只在 HTTP 200 时有意义）
LAYER_PROBES = [
    ("GET", "/api/products/search", "anon", {"http": 200, "code": 500},
     "匿名 GET 在白名单内 ⇒ 直通 MVC ⇒ 命中骨架 throw（这就是链路 A 的断言）"),
    ("POST", "/api/products/search", "anon", {"http": 401},
     "★ 匿名 POST 不在白名单 ⇒ Security 先拒，永远到不了 MVC —— 白名单是【方法粒度】"),
    ("GET", "/api/products/search", "demo", {"http": 200, "code": 500},
     "带 C 端 token 结果相同：白名单与是否带 token 无关"),
    ("POST", "/api/products/search", "demo", {"http": 405},
     "★ 认证通过后才抵达 MVC ⇒ 真实 405（顺带回归 Day 18 补的 handler）"),
]

# 信息性探测（不作断言）
MISC_PROBES = [
    ("GET", "/api/products?keyword=iphone",
     "★ 旧路（LIKE）对照：大小写敏感 ⇒ 现在就该是 total=0；验收期新路必须是 ≥1"),
]

lines = []
say = lines.append
failures = []


def req(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with opener.open(r, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                        # noqa: BLE001
        return -1, "%s: %s" % (type(e).__name__, e)


def show(method, path, token=None):
    """返回 (http, body.code, body.message, body.data, 原始响应)"""
    http, resp = req(method, path, token=token)
    try:
        j = json.loads(resp)
        return http, j.get("code"), j.get("message"), j.get("data"), resp
    except Exception:                                             # noqa: BLE001
        return http, None, resp[:100], None, resp


def brief(data, n=90):
    s = json.dumps(data, ensure_ascii=False) if data is not None else "null"
    return s if len(s) <= n else s[:n] + "..."


def login(path, username, password):
    code, body = req("POST", path, body={"username": username, "password": password})
    try:
        j = json.loads(body)
    except Exception:                                             # noqa: BLE001
        return None, "HTTP %s / 非 JSON: %s" % (code, body[:160])
    if j.get("code") != 200:
        return None, "登录失败: %s" % body[:160]
    return j["data"]["token"], "OK"


def wait_app(deadline=180):
    t0 = time.time()
    while time.time() - t0 < deadline:
        code, _ = req("GET", "/api/hello")
        if code != -1:
            return True, time.time() - t0
        time.sleep(2)
    return False, time.time() - t0


# ---------------------------------------------------------------- 骨架期护栏
# ★ 2026-09-23（Day 18）事故：实现填完后误跑骨架门禁，它真的写了库
#   （新建商品 31 / 分类 36·37，软删商品 1，改分类 1 的 sort_order）。
#   教训：**靠「占位/异常」保持无害的脚本，必须把「前提是否还成立」写成可执行检查。**
#   ⚠️ 本脚本自身只读，护栏的作用是「别把已实现当成故障」——
#      护栏为 0 时仍会走完，但会明确提示「500 断言已过期」。
SKELETON_SCAN_DIRS = [
    r"D:\MallX\backend\mallx\mall-product\src\main\java",
]


def skeleton_remaining():
    n = 0
    for d in SKELETON_SCAN_DIRS:
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.endswith(".java"):
                    continue
                try:
                    with open(os.path.join(root, fn), encoding="utf-8",
                              errors="replace") as f:
                        n += f.read().count("UnsupportedOperationException")
                except OSError:
                    pass
    return n


say("=" * 74)
say("Day 19 骨架门禁 —— 路由 / 路径优先级 / 白名单方法粒度 / 基线回归（零写入）")
say("=" * 74)
_throws = skeleton_remaining()
say("骨架期扫描：mall-product 源码中仍有 %d 处 UnsupportedOperationException" % _throws)
if _throws == 0:
    say("  ⚠️ 已无占位 —— 骨架期已过。下面的 code=500 断言不再适用：")
    say("     实现填完后 /api/products/search 的 code 应为 200（成功）或 400（业务校验失败）。")
    say("     ⇒ 这一趟只当基线回归（第 [2] 节）看，别把 200 当失败。")
say("")

ok, secs = wait_app()
say("应用可达: %s（等待 %.1fs，探测 /api/hello）" % ("是" if ok else "否", secs))
if not ok:
    say("❌ 应用没起来 —— 下面全部跳过（先去看应用日志）")
    report = "\n".join(lines)
    print(report)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    raise SystemExit(1)
say("")

demo_token, demo_msg = login("/api/auth/login", "demo", "demo123")
say("登录 demo(C端) : %s" % demo_msg)
say("")
TOKENS = {"anon": None, "demo": demo_token}

# ------------------------------------------------ [1] ★ 核心：路径优先级
say("=" * 74)
say("[1] ★ 核心：/api/products/search 命中谁？（字面量 vs {id} 变量模式）")
say("=" * 74)
http, bcode, msg, data, raw = show("GET", "/api/products/search")
say("      GET /api/products/search")
say("        HTTP %s   body.code=%s   message=%s   data=%s" % (http, bcode, msg, brief(data)))
say("")
if http == 200 and bcode == 500:
    say("      ✅ 命中 search 方法（方法体是骨架期 TODO 的 throw）")
    say("      ⇒ 结论：PathPattern 的【字面量优先于变量】在本应用成立，")
    say("         /search 没有被当成 id=\"search\"。")
elif http == 200 and bcode == 400:
    say("      ❌ 路由落到了 /api/products/{id}：\"search\" 转 Long 失败")
    say("         ⇒ 路径冲突没按预期解决 —— 需要改路径（如 /api/products/search/list）")
    failures.append("GET /api/products/search 落到了 {id}（code=400，期望 500）")
elif http == 404:
    say("      ❌ 404 —— 路由根本没生效（Controller 是否被扫到？@GetMapping 写了吗？）")
    failures.append("GET /api/products/search 返回 404（路由未生效）")
else:
    say("      ❌ 意外结果：HTTP %s / body.code=%s" % (http, bcode))
    failures.append("GET /api/products/search 返回 HTTP %s / code=%s" % (http, bcode))
say("")

# ------------------------------------------------ [2] 基线回归：白名单红线
say("=" * 74)
say("[2] ★ 白名单红线回归（匿名可读，语义不许变）")
say("=" * 74)
for method, path, desc in WHITELIST_REDLINE:
    http, bcode, msg, data, raw = show(method, path)
    good = (http == 200 and bcode == 200)
    if not good:
        failures.append("%s %s 期望 200/200，实得 %s/%s" % (method, path, http, bcode))
    say("      %s %-34s HTTP %-4s code=%-4s %s" % ("✅" if good else "❌", path, http, bcode, desc))
say("")

# ------------------------------------------------ [3] 白名单的方法粒度
say("=" * 74)
say("[3] ★ 层级断言：Security 先于 MVC，白名单只管 GET")
say("=" * 74)
for method, path, who, expect, desc in LAYER_PROBES:
    http, bcode, msg, data, raw = show(method, path, TOKENS[who])
    good = True
    if expect.get("http") is not None:
        good = good and (http == expect["http"])
    if expect.get("code") is not None:
        good = good and (bcode == expect["code"])
    if not good:
        failures.append("%s %s [%s] 期望 http=%s code=%s，实得 http=%s code=%s"
                        % (method, path, who, expect.get("http"), expect.get("code"), http, bcode))
    say("      %s %-5s %-30s [%-4s] HTTP %-4s code=%-5s 期望 http=%s code=%s"
        % ("✅" if good else "❌", method, path, who, http, bcode,
           expect.get("http"), expect.get("code")))
    say("             %s" % desc)
say("")

# ------------------------------------------------ [4] 信息性探测
say("=" * 74)
say("[4] 信息性探测（不作断言）")
say("=" * 74)
for method, path, desc in MISC_PROBES:
    http, bcode, msg, data, raw = show(method, path)
    total = data.get("total") if isinstance(data, dict) else None
    say("      %-5s %-38s HTTP %-4s code=%-5s total=%s" % (method, path, http, bcode, total))
    say("             %s" % desc)
say("")

say("=" * 74)
if failures:
    say("VERDICT: FAIL —— %d 项不符" % len(failures))
    for f in failures:
        say("   · %s" % f)
else:
    say("VERDICT: OK")
    say("  ① /api/products/search 命中 search 方法（code=500 = 骨架期正确长相）")
    say("  ② 白名单红线 %d 条全部匿名 200/200" % len(WHITELIST_REDLINE))
    say("  ③ 层级判据 %d 条成立：匿名 GET 直通 MVC，匿名 POST 被 Security 拦（401），"
        % len(LAYER_PROBES))
    say("     带 token 的 POST 才到 MVC（405）—— 白名单是方法粒度的。")
    say("  ④ 零写入（全部请求只读；那一条 POST 打的是不存在的写映射，且未过认证）。")
say("=" * 74)

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
raise SystemExit(0 if not failures else 1)
