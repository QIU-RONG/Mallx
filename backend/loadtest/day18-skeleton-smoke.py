# -*- coding: utf-8 -*-
"""Day 18 骨架门禁：9 个新端点是否被路由到、权限矩阵的前三层是否成立。

骨架期这三个问题必须分开答，因为失败长相完全不同：

  端点 404   → **路由没生效**。要么 Controller 不在扫描范围，
               要么路径写错 —— Day 16 那个「新模块漏改 mall-server/pom.xml」
               的坑，症状就是「编译通过、启动成功、接口 404」。
  端点 401   → 路由生效，被 Security 的认证层拦下（匿名）。★ 这是我们想要的。
  端点 403   → 路由生效，认证过了但权限不够。★ 这也是我们想要的。
  端点 500   → 路由与授权**都过了**，进了方法体 —— 骨架期方法体是 TODO 的
               `throw new UnsupportedOperationException`，所以 500 恰恰是
               **骨架正确的证据**。填完逻辑后，它应该变成 200 / 400。

★★ 判据必须区分「真 HTTP 状态码」与「HTTP 200 + body.code」：
   401 / 403 由 Security 过滤器层给出，**不经过** @RestControllerAdvice；
   业务错误才是 HTTP 200 + body.code（本项目约定）。
   拿 body.code 去比状态码会全线误判 —— 这个坑从 Day 13 踩到 Day 17。

★ 本日比 Day 17 多一层身份（4 种 → 5 种），因为本日新增了「商品管理员」这个对角：
    demo(C端)       → 403（C 端 token 的 perms 是空集）
    op_order        → 403（有 order:*，**没有** product:* / category:*）
    op_product      → 非 401/403（有 product:* + category:*）
    admin(超管)     → 非 401/403（全量）
  ⚠️ 「谁没有权限」与「谁有权限」同等重要 —— 只测有权限的账号，
     权限矩阵退化成「一次登录测试」。

★ 关于请求体：POST/PUT 必须带【能通过 @Valid 的】body。
   否则 400 会出现在 @Valid 那一层，看起来像「路由工作正常」，
   实际根本没进方法体 —— 骨架期真正想看到的是 500。
   ★ 骨架期这些请求【零写入】：Controller 方法体是 throw，不会走到 Service。

★★ 但第 4 节「迁移探测」是唯一的例外，它必须用【故意非法】的 body ——
   因为探测目标 POST /api/products 是【可能仍然活着的写接口】：
   它在 Day 09-11 就已完整实现，管理员又确实带着 product:create 权限。
   用合法载荷探测 → 它真的会写库（Day 18 实测踩到：写进了一行 id=22，
   事后靠 day18-cleanup-probe.py 清掉）。
   ⇒ 探测一个「可能还活着的写接口」，要让它死在更早的一层：
        迁移前：过认证 + 过权限 + @Valid 失败 → 400（零写入）
        迁移后：方法映射不存在              → 405
     两者依旧可区分（400 vs 405），且都不会写库。
"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = r"D:\MallX\backend\loadtest\day18-skeleton-smoke-report.txt"

# ★ 必须显式清空代理：本机系统代理会把 127.0.0.1 也拦下，
#   表现是 502 upstream connect failed (os error 10061) —— 不是服务挂了。
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# (方法, 路径, body)  —— body 必须是能过 @Valid 的最小合法载荷
ENDPOINTS = [
    ("GET",    "/api/admin/products",              None),
    ("GET",    "/api/admin/products/1",            None),
    ("POST",   "/api/admin/products",              {"categoryId": 1, "name": "smoke-tmp",
                                                    "skus": [{"skuCode": "SMOKE-TMP-001", "price": 1.00}]}),
    ("PUT",    "/api/admin/products/1",            {"subtitle": "smoke-tmp"}),
    ("DELETE", "/api/admin/products/1",            None),
    ("GET",    "/api/admin/categories/tree",       None),
    ("POST",   "/api/admin/categories",            {"name": "smoke-tmp"}),
    ("PUT",    "/api/admin/categories/1",          {"sortOrder": 99}),
    ("DELETE", "/api/admin/categories/1",          None),
]

# 白名单红线：这两条 C 端 GET 必须【匿名可读】。若它们变成 401，
# 说明有人把管理端 Controller 挂到了 /api/products/** 或 /api/categories/** 上
# —— 那会反过来把管理端接口静默公开（先匹配先赢），是本日的头号红线。
WHITELIST_REDLINE = [
    ("GET", "/api/products?current=1&size=1"),
    ("GET", "/api/categories/tree"),
]

# 迁移探测（信息性，不作断言）：C 端写接口是否已被迁走。
# ★★ 载荷【故意非法】（只给 categoryId，缺 name）—— 见文件头第 4 节说明。
#    迁移前 → 过认证 + 过权限 + @Valid 失败 = 400（零写入）
#    迁移后 → 方法映射不存在 = 405
MIGRATION_PROBES = [
    ("POST", "/api/products", {"categoryId": 1}),
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


def wait_app(deadline=150):
    t0 = time.time()
    while time.time() - t0 < deadline:
        code, _ = req("GET", "/api/hello")
        if code != -1:
            return True, time.time() - t0
        time.sleep(2)
    return False, time.time() - t0


def login(path, username, password):
    code, body = req("POST", path, body={"username": username, "password": password})
    try:
        j = json.loads(body)
    except Exception:                                             # noqa: BLE001
        return None, "HTTP %s / 非 JSON: %s" % (code, body[:200])
    if j.get("code") != 200:
        return None, "登录失败: %s" % body[:200]
    return j["data"]["token"], "OK"


# ---------------------------------------------------------------- 骨架期护栏
# ★★ 2026-09-23 事故：实现填完之后又跑了一次本脚本，第 2 节的 POST/PUT/DELETE
#    不再撞 throw，而是真的写进了库（新建商品 id=31、分类 36/37；把商品 1 软删、
#    把分类 1 的 sort_order 改成 99）。骨架门禁的前提是「方法体还是 throw」，
#    前提不成立却照跑，它就从只读探测变成破坏性脚本。
#    ⇒ 开跑前先数一遍源码里还有没有 UnsupportedOperationException：
#      一个都没有 = 骨架期已过 = 立刻停（写端点一个都不许打）。
SKELETON_SCAN_DIRS = [
    r"D:\MallX\backend\mallx\mall-product\src\main\java",
    r"D:\MallX\backend\mallx\mall-admin\src\main\java",
    r"D:\MallX\backend\mallx\mall-order\src\main\java",
    r"D:\MallX\backend\mallx\mall-inventory\src\main\java",
]


def skeleton_remaining():
    n = 0
    import os
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
say("Day 18 骨架门禁 —— 路由 + 权限矩阵前三层")
say("=" * 74)

_throws = skeleton_remaining()
if _throws == 0:
    say("")
    say("⛔ 已拒绝执行：源码里已无 UnsupportedOperationException（骨架期已过）。")
    say("   本脚本第 2 节会真的调用 POST/PUT/DELETE —— 实现填完后跑它就是在写库。")
    say("   （2026-09-23 真写过：新建商品 id=31、分类 36/37，并软删了商品 1。）")
    say("   ⇒ 请改跑 day18-b/c/d/e-*-verify.py 与 day17-m1-regression.py。")
    say("=" * 74)
    print("\n".join(lines))
    with open(REPORT, "w", encoding="utf-8") as _f:
        _f.write("\n".join(lines) + "\n")
    raise SystemExit(0)
say("骨架期确认：源码中仍有 %d 处 UnsupportedOperationException（写端点不会真写库）"
    % _throws)

ok, secs = wait_app()
say("应用可达: %s（等待 %.1fs，探测 /api/hello）" % ("是" if ok else "否", secs))
if not ok:
    say("❌ 应用没起来 —— 下面全部跳过（先去看应用日志）")
    print("\n".join(lines))
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    raise SystemExit(1)
say("")

# ---------- 登录五种身份 ----------
say("[1] 登录")
demo_token, demo_msg = login("/api/auth/login", "demo", "demo123")
say("      demo(C端)   : %s" % demo_msg)
admin_token, admin_msg = login("/api/auth/admin/login", "admin", "admin123")
say("      admin(超管) : %s" % admin_msg)
order_token, order_msg = login("/api/auth/admin/login", "op_order", "op123456")
say("      op_order    : %s" % order_msg)
product_token, product_msg = login("/api/auth/admin/login", "op_product", "prod123456")
say("      op_product  : %s" % product_msg)
say("")

IDENTITIES = [
    ("匿名", None, "401"),
    ("demo(C端)", demo_token, "403"),
    ("op_order", order_token, "403"),
    ("op_product", product_token, "NOT-401/403"),
    ("admin(超管)", admin_token, "NOT-401/403"),
]

say("[2] %d 端点 × %d 身份" % (len(ENDPOINTS), len(IDENTITIES)))
say("")
for method, path, body in ENDPOINTS:
    say("  %-6s %s" % (method, path))
    for label, token, expect in IDENTITIES:
        code, resp = req(method, path, token=token, body=body)
        if expect == "401":
            good = (code == 401)
        elif expect == "403":
            good = (code == 403)
        else:
            good = code not in (401, 403, -1, 404)
        mark = "✅" if good else "❌"
        if not good:
            failures.append("%s %s [%s] 期望 %s，实得 %s" % (method, path, label, expect, code))
        snippet = resp.replace("\n", " ")[:60]
        say("      %s %-12s HTTP %-4s 期望 %-11s %s" % (mark, label, code, expect, snippet))
    say("")

# ---------- 白名单红线 ----------
say("[3] ★ 白名单红线：C 端两条公开 GET 必须匿名可读（回归）")
for method, path in WHITELIST_REDLINE:
    code, resp = req(method, path)
    good = (code == 200)
    if not good:
        failures.append("%s %s 期望匿名 200，实得 %s" % (method, path, code))
    say("      %s %-6s %-34s 匿名 HTTP %s" % ("✅" if good else "❌", method, path, code))
say("")

# ---------- 迁移探测（信息性） ----------
say("[4] 迁移探测（信息性，不作断言）—— C 端写接口是否已迁走")
say("      ★ 载荷故意缺 name：迁移前 admin 落在 400(@Valid)，迁移后应变成 405(方法没了)")
say("      迁移完成后期望：匿名 401 / demo 403 / admin 405")
for method, path, body in MIGRATION_PROBES:
    for label, token in (("匿名", None), ("demo(C端)", demo_token), ("admin(超管)", admin_token)):
        code, resp = req(method, path, token=token, body=body)
        snippet = resp.replace("\n", " ")[:50]
        say("      %-6s %-18s %-12s HTTP %-4s %s" % (method, path, label, code, snippet))
say("")

say("=" * 74)
if failures:
    say("VERDICT: FAIL —— %d 项不符" % len(failures))
    for f in failures:
        say("   · %s" % f)
else:
    say("VERDICT: OK")
    say("  路由 %d/%d 生效；匿名全 401、C 端与 op_order 全 403" % (len(ENDPOINTS), len(ENDPOINTS)))
    say("  —— 权限矩阵前三层成立。")
    say("  op_product / 超管侧落在 500：那是骨架期方法体 TODO 的 throw，属【预期】。")
    say("  填完逻辑后，这两侧应变成 200 / 400（不再是 500）。")
say("=" * 74)

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
raise SystemExit(0 if not failures else 1)
