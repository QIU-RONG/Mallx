# -*- coding: utf-8 -*-
"""Day 20 骨架门禁：新模块是否被路由、白名单粒度、权限矩阵前三层、补丁是否已应用。

骨架期这几个问题必须分开答，因为失败长相完全不同：

  404        → **路由没生效**。要么 Controller 不在扫描范围，要么路径写错 ——
               本项目「新模块漏改 mall-server/pom.xml」的坑就是这个症状
               （编译通过、启动成功、接口 404）。★ Day 20 是第 9 个模块第一次真的写代码，
               虽然 pom 早就配好，仍要打一发证明它真的被扫到了。
  401        → 路由生效，被 Security 的认证层拦下（匿名）。★ 正常情况下这是我们想要的。
  403        → 路由生效，认证过了但权限不够。★ 也是我们想要的。
  HTTP 200 + body.code = 500
             → 路由与授权**都过了**，进了方法体 —— 骨架期方法体是 TODO 的
               `throw new UnsupportedOperationException`（或 XML 里的 TODO 占位 SQL），
               所以它恰恰是**骨架正确的证据**。填完逻辑后应变成 200 / 400。

★★ 判据必须区分「真 HTTP 状态码」与「HTTP 200 + body.code」：
   401 / 403 由 Security 过滤器层给出，**不经过** @RestControllerAdvice；
   业务错误（含骨架期的 UnsupportedOperationException）才是 HTTP 200 + body.code。
   拿 body.code 去比状态码会全线误判 —— 这个坑从 Day 13 踩到 Day 17。

★★ 本日独有的一条断言（Day 16 的反面）：**白名单粒度的证据**
   SecurityConfig 里新增的是精确路径  GET /api/coupons  →  匿名应 200
   而不是通配        GET /api/coupons/** →  会把「我的券」也公开
   所以本脚本第 2 节必须成对断言：
       匿名 GET /api/coupons      → HTTP 200
       匿名 GET /api/coupons/my   → HTTP 401   ★ 没被误伤
   这一对就是「精确路径 vs 通配路径」的实测差别。写错成 /** 时，第二条会变成 200 ——
   而那意味着**任何人可以看任何人的券**，且服务端不报任何错。
"""
from _paths import lp

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = lp(r"D:\MallX\backend\loadtest\day20-skeleton-smoke-report.txt")
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
SKELETON_SCAN_DIR = lp(r"D:\MallX\backend\mallx\mall-marketing\src\main\java")
TODO_BASELINE = 11

# ★ 必须显式清空代理：本机系统代理会把 127.0.0.1 也拦下，
#   表现是 502 upstream connect failed (os error 10061) —— 不是服务挂了。
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 管理端新建券的【合法载荷】—— 必须能过 @Valid + 过 Service 的关系校验，
# 否则 400 会出现在校验层，看起来像「路由工作正常」，实际没进方法体。
COUPON_BODY = {
    "name": "smoke-tmp",
    "type": "FIXED",
    "discountAmount": 10.00,
    "minAmount": 100.00,
    "totalCount": 100,
    "startTime": "2020-01-01T00:00:00",
    "endTime": "2030-01-01T00:00:00",
}

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


def body_code(resp):
    """取 body.code；解析不了返回 None。★ 骨架期判 500 靠它，不靠 HTTP 码。"""
    try:
        return json.loads(resp).get("code")
    except Exception:                                             # noqa: BLE001
        return None


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


def psql(sql):
    """★ stderr 必须浮出来：只读 stdout 会把 SQL 错误伪装成『没数据』。"""
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed (rc=%d)\nSQL: %s\nstderr: %s"
                           % (p.returncode, sql, err))
    return out


def one(sql):
    return psql(sql).strip()


# ---------------------------------------------------------------- 骨架期护栏
# ★★ 护栏的理由（Day 18 真事故）：骨架门禁的前提是「方法体还是 throw」。
#    实现填完之后再跑它，那些 POST/DELETE 就不再撞 throw 而是真的写库
#    （2026-09-23：新建商品 id=31、分类 36/37，并软删了商品 1）。
#    ⇒ 开跑前先数一遍源码里还有没有 UnsupportedOperationException：
#      一个都没有 = 骨架期已过 = 立刻停。
def skeleton_remaining():
    n = 0
    for root, _dirs, files in os.walk(SKELETON_SCAN_DIR):
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
say("Day 20 骨架门禁 —— 路由 + 白名单粒度 + 权限矩阵 + 补丁状态")
say("=" * 74)

_throws = skeleton_remaining()
if _throws == 0:
    say("")
    say("⛔ 已拒绝执行：mall-marketing 源码里已无 UnsupportedOperationException（骨架期已过）。")
    say("   本脚本会真的调用 POST /api/admin/coupons —— 实现填完后跑它就是在写库。")
    say("   （Day 18 真写过：新建商品 id=31、分类 36/37。护栏就是这么加上的。）")
    say("   ⇒ 请改跑 day20 的验收脚本与 day17-m1-regression.py。")
    say("=" * 74)
    print("\n".join(lines))
    with open(REPORT, "w", encoding="utf-8") as _f:
        _f.write("\n".join(lines) + "\n")
    raise SystemExit(0)

say("骨架期确认：mall-marketing 源码中仍有 %d 处 UnsupportedOperationException"
    "（预期基线 %d；写端点不会真写库）" % (_throws, TODO_BASELINE))

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

# ---------- [2] C 端：白名单粒度的证据 ----------
say("[2] ★★ C 端三个端点 —— 白名单粒度（本日最重要的一组）")
say("      判据：匿名能到 Controller ⇒ HTTP 200 且 body.code=500（骨架占位）")
say("            匿名被拦         ⇒ HTTP 401")
C_ENDPOINTS = [
    ("GET",  "/api/coupons",            None, "PUBLIC",
     "★ 精确白名单应放行（HTTP 200）"),
    ("GET",  "/api/coupons/my",         None, "PRIVATE",
     "★★ 必须 401 —— 通配白名单会误伤它"),
    ("POST", "/api/coupons/1/receive",  None, "PRIVATE",
     "需登录，不在白名单"),
]
for method, path, body, kind, note in C_ENDPOINTS:
    code, resp = req(method, path, body=body)
    bc = body_code(resp)
    if kind == "PUBLIC":
        good = (code == 200 and bc == 500)
        detail = "HTTP %s / body.code=%s 期望 HTTP 200 + code=500" % (code, bc)
    else:
        good = (code == 401)
        detail = "HTTP %s 期望 401" % code
    if not good:
        failures.append("匿名 %s %s：%s" % (method, path, detail))
    say("      %s 匿名 %-6s %-30s %s" % ("✅" if good else "❌", method, path, detail))
    say("           %s" % note)
    # 带 C 端 token：应过认证、进方法体 → HTTP 200 + code=500
    if kind == "PRIVATE" or path == "/api/coupons":
        code2, resp2 = req(method, path, token=demo_token, body=body)
        bc2 = body_code(resp2)
        good2 = (code2 == 200 and bc2 == 500)
        if not good2:
            failures.append("demo %s %s：HTTP %s / body.code=%s 期望 HTTP 200 + code=500"
                            % (method, path, code2, bc2))
        say("      %s demo   %-6s %-30s HTTP %s / body.code=%s" %
            ("✅" if good2 else "❌", method, path, code2, bc2))
say("")

# ---------- [3] 管理端：权限矩阵 ----------
say("[3] 管理端三个端点 × 五种身份（★ 期望 coupon:* 只发给超管）")
say("      demo(C端)   → 403（C 端 token 的 perms 是空集）")
say("      op_order    → 403（★ 反向对照：有 order:*，没有 coupon:*）")
say("      op_product  → 403（★ 反向对照：营销不是商品岗位的活）")
say("      admin(超管) → 过权限，落 HTTP 200 + code=500（骨架占位）")
ADMIN_ENDPOINTS = [
    ("GET",    "/api/admin/coupons",   None,        "coupon:list"),
    ("POST",   "/api/admin/coupons",   COUPON_BODY, "coupon:create"),
    ("DELETE", "/api/admin/coupons/1", None,        "coupon:delete"),
]
IDENTITIES = [
    ("匿名",       None,          "401"),
    ("demo(C端)",  demo_token,    "403"),
    ("op_order",   order_token,   "403"),
    ("op_product", product_token, "403"),
    ("admin(超管)", admin_token,  "SKELETON"),
]
for method, path, body, perm in ADMIN_ENDPOINTS:
    say("")
    say("  %-6s %-24s  [%s]" % (method, path, perm))
    for label, token, expect in IDENTITIES:
        code, resp = req(method, path, token=token, body=body)
        bc = body_code(resp)
        if expect == "SKELETON":
            good = (code == 200 and bc == 500)
            detail = "HTTP %s / body.code=%s 期望 200+500" % (code, bc)
        else:
            good = (code == int(expect))
            detail = "HTTP %s 期望 %s" % (code, expect)
        if not good:
            failures.append("%s %s [%s]：%s" % (method, path, label, detail))
        say("      %s %-12s %s" % ("✅" if good else "❌", label, detail))
say("")

# ---------- [4] 白名单红线（回归 + 本日新增） ----------
say("[4] 白名单红线：以下三条【匿名】可读/应拦，全部不能变")
REDLINE = [
    ("GET", "/api/products?current=1&size=1", 200, "Day 09-11 的 C 端公开 GET（回归）"),
    ("GET", "/api/categories/tree",           200, "C 端分类树（回归）"),
    ("GET", "/api/coupons",                   200, "★ Day 20 新增：可领券列表公开"),
    ("GET", "/api/coupons/my",                401, "★★ Day 20 新增：我的券【不能】被公开"),
]
for method, path, expect, why in REDLINE:
    code, _resp = req(method, path)
    good = (code == expect)
    if not good:
        failures.append("%s %s 期望匿名 %s，实得 %s（%s）" % (method, path, expect, code, why))
    say("      %s 匿名 %-6s %-34s HTTP %-4s 期望 %s" %
        ("✅" if good else "❌", method, path, code, expect))
    say("           %s" % why)
say("")

# ---------- [5] 补丁状态（只读核对） ----------
say("[5] SQL 补丁是否已应用（只读核对）")
PATCH_CHECKS = [
    ("user_coupons 唯一约束",
     "SELECT count(*) FROM pg_constraint WHERE conname = 'uk_user_coupons_user_coupon'",
     1, "09-user-coupons-unique.sql"),
    ("coupon:* 权限条数",
     "SELECT count(*) FROM permissions WHERE code LIKE 'coupon:%'",
     3, "08-marketing-permissions.sql"),
    ("role 1（超管）拿到几条",
     "SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
     "WHERE rp.role_id = 1 AND p.code LIKE 'coupon:%'",
     3, "08-marketing-permissions.sql 第三节①"),
    ("role 2（商品管理员）拿到几条",
     "SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
     "WHERE rp.role_id = 2 AND p.code LIKE 'coupon:%'",
     0, "★ 期望 0 —— 反向对照，不是遗漏"),
    ("role 3（订单管理员）拿到几条",
     "SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
     "WHERE rp.role_id = 3 AND p.code LIKE 'coupon:%'",
     0, "★ 期望 0 —— 反向对照，不是遗漏"),
]
try:
    for name, sql, expect, why in PATCH_CHECKS:
        got = int(one(sql))
        good = (got == expect)
        if not good:
            failures.append("补丁核对「%s」：期望 %s，实得 %s" % (name, expect, got))
        say("      %s %-26s = %-3s 期望 %-3s  [%s]"
            % ("✅" if good else "❌", name, got, expect, why))
except RuntimeError as e:
    failures.append("补丁核对 psql 失败：%s" % e)
    say("      ❌ psql 失败：%s" % e)
say("")

# ---------- [6] 零写入 ----------
say("[6] 零写入核对：门禁全程不应改动任何数据")
ZERO_WRITE = [
    ("coupons", "SELECT count(*) FROM coupons"),
    ("user_coupons", "SELECT count(*) FROM user_coupons"),
]
try:
    for name, sql in ZERO_WRITE:
        n = int(one(sql))
        say("      %-14s = %s" % (name, n))
    # ★ 期望两张表都是 0 —— 本日新增的券与领取记录都由【验收脚本】造并自行清理，
    #   门禁脚本一个字节都不该写。
    c1 = int(one("SELECT count(*) FROM coupons"))
    c2 = int(one("SELECT count(*) FROM user_coupons"))
    good = (c1 == 0 and c2 == 0)
    if not good:
        failures.append("零写入核对：coupons=%s / user_coupons=%s，期望都是 0"
                        "（门禁脚本不该写库）" % (c1, c2))
    say("      %s 两张表都应为 0（门禁零写入）" % ("✅" if good else "❌"))
except RuntimeError as e:
    failures.append("零写入核对 psql 失败：%s" % e)
    say("      ❌ psql 失败：%s" % e)
say("")

say("=" * 74)
if failures:
    say("VERDICT: FAIL —— %d 项不符" % len(failures))
    for f in failures:
        say("   · %s" % f)
else:
    say("VERDICT: OK")
    say("  路由 6/6 生效（mall-marketing 被扫到了，没有一个 404）")
    say("  ★ 白名单粒度：匿名 /api/coupons = 200，匿名 /api/coupons/my = 401 —— 精确路径成立")
    say("  ★ 权限矩阵前三层成立：匿名 401 / C端与两个业务管理员 403 / 超管过权限落骨架 500")
    say("  ★ 两个 SQL 补丁均已应用（唯一约束 1 条；coupon:* 3 条只发给了超管）")
    say("  → 超管侧落在 code=500：那是骨架期方法体 TODO 的 throw / XML 的 TODO 占位，属【预期】。")
    say("    填完逻辑后，它应变成 200 / 400（不再是 500）。")
say("=" * 74)

report = "\n".join(lines)
print(report)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(report + "\n")
raise SystemExit(0 if not failures else 1)
