# -*- coding: utf-8 -*-
"""Day 25 · M3-2：README「快速开始」里写下的每一件事，逐条实测。

为什么值得单独写一个脚本？
------------------------------------------------------------------
README 是本项目**唯一面向外部读者**的文档，而它上一版（停在 Day 10）里的
命令已经**有两条过期且没人发现**：
  · `bash mvnw.sh package`  —— 与后来实测的离线构建命令不是一回事；
  · `GET /api/db-check` 作为「无需登录的验证接口」—— Day 06 加了 Security 之后
    它**不在白名单里**，匿名访问是 **401**，照 README 敲会以为服务坏了。
⇒ 判据：**文档里的命令与「能跑通」之间没有自动联系**，必须有个脚本替读者先跑一遍。
   （与 Day 24「改了接口没同步 docs/api/」是同一类错误的两个出口。）

本脚本只做**只读**探测（登录、查列表、故意越权），不写库、不改数据。

断言分组：
  A 依赖服务（PG / 应用）
  B 文档站（api-docs / swagger-ui）
  C 种子账号登录（demo / admin）+ 各自能过的接口
  D 鉴权三档（公开 / 登录 / 权限码）—— README 里那条「状态码约定」的实证
  E 白名单是【方法粒度】的（匿名 POST 打白名单里的 GET → 401 而非 405）

运行：python day25-readme-quickstart-check.py
"""
from _paths import lp
import json
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
import os
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
# ★ 护栏：断言条数写死。分解 = A 2 + B 3 + C 4 + D 5 + E 2 = 16
#   （首跑时这里写的是 17 —— 立刻被护栏抓出来，见 Day-25 文档 §坑。
#    这正是它存在的理由：断言条数算错的两次，症状与「断言没被创建」一模一样。）
EXPECTED = 16

# ★ 不走系统代理：本机 curl/urllib 都会把 127.0.0.1 交给代理，得到 502 假故障
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

lines_out = []
n_pass = 0
n_fail = 0


def say(s=""):
    lines_out.append(s)
    print(s)


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def http(method, path, body=None, token=None, timeout=25):
    """返回 (status, parsed_body_or_None, raw_text)"""
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Accept", "application/json")
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with OPENER.open(req, data=data, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, _parse(raw), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, _parse(raw), raw
    except Exception as e:                       # 连接被拒 / 超时
        return 0, None, "%s: %s" % (type(e).__name__, e)


def _parse(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def code_of(b):
    return b.get("code") if isinstance(b, dict) else None


def main():
    say("=" * 78)
    say("MallX README「快速开始」逐条实测")
    say("=" * 78)

    say("")
    say("[A] 依赖服务")
    p = subprocess.run([DOCKER, "exec", CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-t", "-A", "-c", "SELECT 1"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120)
    chk("A1 PostgreSQL 可连（docker exec psql -> 1）", p.returncode == 0 and p.stdout.strip() == "1",
        "rc=%d out=%r err=%r" % (p.returncode, p.stdout.strip(), p.stderr.strip()[:120]))
    st, b, raw = http("GET", "/api/hello")
    chk("A2 GET /api/hello -> 200 + data=\"Hello MallX\"",
        st == 200 and code_of(b) == 200 and b.get("data") == "Hello MallX",
        "http=%s code=%s data=%r" % (st, code_of(b), (b or {}).get("data")))

    say("")
    say("[B] 文档站")
    st, b, raw = http("GET", "/v3/api-docs")
    chk("B1 GET /v3/api-docs -> 200 且 JSON 里的 paths 非空",
        st == 200 and isinstance(b, dict) and len(b.get("paths", {})) > 0,
        "http=%s paths=%s" % (st, len(b.get("paths", {})) if isinstance(b, dict) else "-"))
    chk("B2 文档里含 securityScheme bearerAuth（Authorize 按钮据此渲染）",
        isinstance(b, dict) and "bearerAuth" in b.get("components", {}).get("securitySchemes", {}),
        "")
    st, b, raw = http("GET", "/swagger-ui/index.html")
    chk("B3 GET /swagger-ui/index.html -> 200", st == 200, "http=%s" % st)

    say("")
    say("[C] 种子账号（03-data.sql）")
    st, b, raw = http("POST", "/api/auth/login", {"username": "demo", "password": "demo123"})
    t_user = (b or {}).get("data", {}).get("token") if code_of(b) == 200 else None
    chk("C1 C 端登录 demo/demo123 -> 200 + 有 token + tokenType=Bearer",
        code_of(b) == 200 and bool(t_user)
        and (b.get("data") or {}).get("tokenType") == "Bearer",
        "code=%s tokenType=%s" % (code_of(b), (b or {}).get("data", {}).get("tokenType")))
    st, b, raw = http("POST", "/api/auth/admin/login", {"username": "admin", "password": "admin123"})
    t_admin = (b or {}).get("data", {}).get("token") if code_of(b) == 200 else None
    chk("C2 管理端登录 admin/admin123 -> 200 + 有 token", code_of(b) == 200 and bool(t_admin),
        "code=%s" % code_of(b))
    st, b, raw = http("GET", "/api/users/me", token=t_user)
    chk("C3 demo token -> GET /api/users/me 200，且出参【不含 password】",
        code_of(b) == 200 and isinstance(b.get("data"), dict) and "password" not in b["data"],
        "code=%s keys=%s" % (code_of(b), sorted(b["data"].keys()) if code_of(b) == 200 else "-"))
    st, b, raw = http("GET", "/api/admin/dashboard/overview", token=t_admin)
    chk("C4 admin token -> GET /api/admin/dashboard/overview 200",
        code_of(b) == 200, "code=%s" % code_of(b))

    say("")
    say("[D] 鉴权三档（README「状态码约定」的实证）")
    st, b, raw = http("GET", "/api/brands")
    chk("D1 匿名 GET /api/brands -> HTTP 200（公开档，白名单）", st == 200 and code_of(b) == 200,
        "http=%s code=%s" % (st, code_of(b)))
    st, b, raw = http("GET", "/api/db-check")
    chk("D2 匿名 GET /api/db-check -> HTTP 401（★ 不在白名单；README 旧版把它写成公开验证接口）",
        st == 401, "http=%s body=%s" % (st, raw[:80]))
    st, b, raw = http("GET", "/api/coupons/my")
    chk("D3 匿名 GET /api/coupons/my -> HTTP 401（私有，白名单只放行精确的 /api/coupons）",
        st == 401, "http=%s" % st)
    st, b, raw = http("GET", "/api/admin/dashboard/overview", token=t_user)
    chk("D4 C 端 token 打管理端 -> HTTP 403（★ 真状态码，不是 200+code）", st == 403,
        "http=%s" % st)
    st, b, raw = http("GET", "/api/admin/categories/tree",
                      token=_login("op_order", "op123456"))
    chk("D5 op_order（ORDER_ADMIN）打商品域管理端 -> 403（反向对照，证明 403 不是『没登录』）",
        st == 403, "http=%s" % st)

    say("")
    say("[E] 白名单是【方法粒度】的")
    st, b, raw = http("POST", "/api/coupons", {})
    chk("E1 匿名 POST /api/coupons -> HTTP 401（★ 不是 405：过滤器链先于 MVC 路由）",
        st == 401, "http=%s" % st)
    st, b, raw = http("POST", "/api/coupons", {}, token=t_user)
    chk("E2 带 token 的 POST /api/coupons -> HTTP 405（这才走到 MVC，发现没有 POST handler）",
        st == 405, "http=%s" % st)

    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, n_pass + n_fail, EXPECTED))
    if n_pass + n_fail != EXPECTED:
        say("★ 护栏未过：实得 %d 条，期望 %d 条 —— 有断言没被创建（分母缩水）"
            % (n_pass + n_fail, EXPECTED))
    say("VERDICT: %s" % ("OK" if n_fail == 0 and n_pass + n_fail == EXPECTED else "FAIL"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines_out) + "\n")
    return 0 if (n_fail == 0 and n_pass + n_fail == EXPECTED) else 1


def _login(u, pw):
    st, b, _raw = http("POST", "/api/auth/admin/login", {"username": u, "password": pw})
    return (b or {}).get("data", {}).get("token") if code_of(b) == 200 else None


REPORT = lp(r"D:\MallX\backend\loadtest\day25-readme-quickstart-check-report.txt")

if __name__ == "__main__":
    sys.exit(main())
