# -*- coding: utf-8 -*-
"""Day 17 骨架门禁：6 个新端点是否被路由到、权限矩阵的前两层是否成立。

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
   拿 body.code 去比状态码会全线误判 —— 这个坑从 Day 13 踩到今天。

三种身份，对应权限矩阵的前两层（第三层 op_order 夹具留给 day17-admin-e2e.py）：
  匿名             → 期望 401
  demo（C 端用户） → 期望 403（C 端 token 的 perms 是空集）
  admin（超管）    → 期望「非 401/403」（骨架期即 500）
"""
from _paths import lp
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = lp(r"D:\MallX\backend\loadtest\day17-skeleton-smoke-report.txt")

# ★ 必须显式清空代理：本机系统代理会把 127.0.0.1 也拦下，
#   表现是 502 upstream connect failed (os error 10061) —— 不是服务挂了。
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ENDPOINTS = [
    ("GET",  "/api/admin/orders",                        None),
    ("GET",  "/api/admin/orders/1",                      None),
    ("POST", "/api/admin/orders/1/cancel",               None),
    ("GET",  "/api/admin/inventory/skus",                None),
    ("GET",  "/api/admin/inventory/logs",                None),
    ("POST", "/api/admin/inventory/skus/1/adjust",       {"delta": 1, "reason": "smoke"}),
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


say("=" * 74)
say("Day 17 骨架门禁 —— 路由 + 权限矩阵前两层")
say("=" * 74)

ok, secs = wait_app()
say("应用可达: %s（等待 %.1fs，探测 /api/hello）" % ("是" if ok else "否", secs))
if not ok:
    say("❌ 应用没起来 —— 下面全部跳过（先去看应用日志）")
    print("\n".join(lines))
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    raise SystemExit(1)
say("")

# ---------- 登录两种身份 ----------
say("[1] 登录")
demo_token, demo_msg = login("/api/auth/login", "demo", "demo123")
say("      demo   : %s" % demo_msg)
admin_token, admin_msg = login("/api/auth/admin/login", "admin", "admin123")
say("      admin  : %s" % admin_msg)
say("")

IDENTITIES = [
    ("匿名", None, "401"),
    ("demo(C端)", demo_token, "403"),
    ("admin(超管)", admin_token, "NOT-401/403"),
]

say("[2] 6 端点 × 3 身份")
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
        snippet = resp.replace("\n", " ")[:68]
        say("      %s %-12s HTTP %-4s 期望 %-11s %s" % (mark, label, code, expect, snippet))
    say("")

say("=" * 74)
if failures:
    say("VERDICT: FAIL —— %d 项不符" % len(failures))
    for f in failures:
        say("   · %s" % f)
else:
    say("VERDICT: OK")
    say("  路由 6/6 生效；匿名全 401、C 端全 403 —— 权限矩阵前两层成立。")
    say("  超管侧落在 500：那是骨架期方法体 TODO 的 throw，属【预期】。")
    say("  填完逻辑后，超管侧应变成 200 / 400（不再是 500）。")
say("=" * 74)

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
raise SystemExit(0 if not failures else 1)
