# -*- coding: utf-8 -*-
"""Day 25 · M3-3：Docker Compose 全栈【实机验收】。

验的不是「文件写对了」，而是「一套全新的数据卷从 initdb 一路走到能调通受保护接口」。

历史背景（为什么要写这个脚本）：
  compose 只要少一个 `depends_on: {condition: service_healthy}`，或者
  initdb 里的某个 SQL 补丁失败，现象都是「容器 Up、接口 500」——
  看 `docker compose ps` 全是绿色，看日志才发现表不存在。
  ⇒ 判据：容器 healthy 只证明**进程活着**，不证明**业务可用**。

前置：`docker compose -f deploy/docker-compose.app.yml up -d` 已跑完，APP_PORT 见 deploy/.env。

运行：python day25-compose-verify.py [宿主端口，默认 8081]
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
BASE = "http://127.0.0.1:%d" % PORT
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
COMPOSE_FILE = r"D:\MallX\deploy\docker-compose.app.yml"
PROJECT = "mallx-stack"
PG_CONTAINER = "mallx-stack-postgres-1"
APP_CONTAINER = "mallx-stack-app-1"
EXPECTED = 12

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
lines_out = []
n_pass = n_fail = 0


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


def sh(args, timeout=120):
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def sql(q):
    rc, out, err = sh([DOCKER, "exec", PG_CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                       "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", q])
    return rc, out, err


def http(method, path, body=None, token=None, timeout=25):
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
            return r.status, _p(raw), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, _p(raw), raw
    except Exception as e:
        return 0, None, "%s: %s" % (type(e).__name__, e)


def _p(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def code_of(b):
    return b.get("code") if isinstance(b, dict) else None


def main():
    say("=" * 78)
    say("MallX Docker Compose 全栈验收（宿主端口 %d）" % PORT)
    say("=" * 78)

    say("")
    say("[A] 容器层")
    rc, out, _e = sh([DOCKER, "inspect", "-f", "{{.State.Health.Status}}", APP_CONTAINER])
    chk("A1 app 容器 health 状态 = healthy", rc == 0 and out == "healthy", "out=%r" % out)
    rc, out, _e = sh([DOCKER, "inspect", "-f", "{{.State.Health.Status}}", PG_CONTAINER])
    chk("A2 postgres 容器 health 状态 = healthy", rc == 0 and out == "healthy", "out=%r" % out)
    rc, out, _e = sh([DOCKER, "inspect", "-f", "{{.Config.User}}", APP_CONTAINER])
    chk("A3 app 容器【非 root】运行（User=mallx）", out == "mallx", "User=%r" % out)

    say("")
    say("[B] initdb 链路（01→14 是否真的按序跑完）")
    rc, out, err = sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    n_tab = int(out) if rc == 0 and out.isdigit() else -1
    chk("B1 核心表已建（public schema 表数 >= 22）", n_tab >= 22, "tables=%s" % n_tab)
    rc, out, _e = sql("SELECT count(*) FROM permissions")
    n_perm = int(out) if rc == 0 and out.isdigit() else -1
    chk("B2 权限码全部补发到位（permissions = 41）", n_perm == 41, "permissions=%s" % n_perm)
    rc, out, _e = sql("SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id=rp.permission_id"
                      " WHERE p.code LIKE 'brand:%' AND rp.role_id = 1")
    chk("B3 最后一份补丁（14 号 · brand:*）的授权也在（超管持有 4 条 brand 权限）",
        rc == 0 and out == "4", "rows=%s" % out)
    rc, out, _e = sql("SELECT count(*) FROM information_schema.columns WHERE table_name='orders'"
                      " AND column_name='discount_amount'")
    chk("B4 DDL 补丁 11 号生效（orders.discount_amount 存在）", rc == 0 and out == "1", "cols=%s" % out)

    say("")
    say("[C] 端到端可用性（对外端口 %d）" % PORT)
    st, b, raw = http("GET", "/api/hello")
    chk("C1 GET /api/hello -> 200", st == 200 and code_of(b) == 200, "http=%s" % st)
    st, b, raw = http("GET", "/api/products")
    chk("C2 匿名 GET /api/products -> 200（白名单在容器里同样生效）",
        st == 200 and code_of(b) == 200, "http=%s" % st)
    st, b, raw = http("POST", "/api/auth/admin/login", {"username": "admin", "password": "admin123"})
    t_admin = (b or {}).get("data", {}).get("token") if code_of(b) == 200 else None
    chk("C3 管理员登录 -> 200 + 有 token", code_of(b) == 200 and bool(t_admin),
        "code=%s" % code_of(b))

    say("")
    say("[D] ★ 核心一条：权限码真的经【新库】生效")
    st, b, raw = http("GET", "/api/admin/roles", token=t_admin)
    chk("D1 GET /api/admin/roles 带超管 token -> 200（说明 role_permissions 种子齐）",
        code_of(b) == 200, "code=%s" % code_of(b))
    st, b, raw = http("GET", "/api/admin/roles")
    chk("D2 同一端点匿名 -> HTTP 401（未配错成公开）", st == 401, "http=%s" % st)
    return _verdict()


def _verdict():
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, n_pass + n_fail, EXPECTED))
    if n_pass + n_fail != EXPECTED:
        say("★ 护栏未过：实得 %d 条，期望 %d 条" % (n_pass + n_fail, EXPECTED))
    say("VERDICT: %s" % ("OK" if n_fail == 0 and n_pass + n_fail == EXPECTED else "FAIL"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines_out) + "\n")
    return 0 if (n_fail == 0 and n_pass + n_fail == EXPECTED) else 1


REPORT = r"D:\MallX\backend\loadtest\day25-compose-verify-report.txt"

if __name__ == "__main__":
    sys.exit(main())
