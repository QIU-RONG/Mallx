#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Day 22 开工前安全探针：C 端 `/api/users` 家族是否越权 / 泄露口令哈希。

【代码级三条证据】（先看代码，再实测 —— 避免误报）
  ① `SecurityConfig:49-62` 白名单【不含】`/api/users` ⇒ 它只需登录，不是公开；
  ② `UserController` 三个方法都【没有】`@PreAuthorize`。★ 这本身合理：
     C 端 token 不带 perms，挂了必 403（Day 06 铁律）。但「不挂」之后
     就【必须】自己做「只能看自己」的归属过滤 —— 而这里一行都没有；
  ③ `User.java:16` 有 `private String password;` 且【无 @JsonIgnore】，
     三个方法直接返回 `Result<User>` / `Result<PageResult<User>>`。

⇒ 三条推论，本脚本逐条实测：
   (a) 任何登录用户能拉到【全站用户分页列表】；
   (b) 列表 / 详情响应体里带【口令哈希】；
   (c) 能改【任何人】的昵称（无归属校验）。

★ 只读为主。唯一一次写操作（D 组改昵称）写回原值，并做二次校验 + 兜底恢复。
★ 断言对着【设计】写：本项目设计上「私有资源非本人一律伪装 404」（`requireOwn`），
  所以 (a)(b)(c) 全部应为「否」—— 本脚本期望**全绿**（即漏洞被证实）。
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP = "http://127.0.0.1:8080"
DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]

EXPECTED = 16
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LINES = []
PASS = 0
FAIL = 0
FAILS = []


def say(line=""):
    print(line)
    LINES.append(line)


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        say("  [PASS] %s" % name)
    else:
        FAIL += 1
        FAILS.append(name)
        say("  [FAIL] %s   %s" % (name, extra))


# ---------------------------------------------------------------- DB
def sql(statement):
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("psql rc=%s: %s" % (r.returncode, (r.stderr or "").strip()[:300]))
    return [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]


def sql1(statement):
    rows = sql(statement)
    if not rows:
        raise RuntimeError("psql 返回空输出 —— 多半是 Docker 引擎没起（不是脚本问题）。SQL: %s"
                           % statement)
    return rows[0]


# ---------------------------------------------------------------- HTTP
def api(method, path, token=None, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(APP + path, method=method, data=data, headers=headers)
    try:
        with _opener.open(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
            st = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        st = e.code
    except Exception as e:                                        # noqa: BLE001
        return -1, None, "%s: %s" % (type(e).__name__, e)
    try:
        return st, json.loads(raw), raw
    except Exception:                                             # noqa: BLE001
        return st, None, raw


def code_of(j):
    return j.get("code") if isinstance(j, dict) else None


def data_of(j):
    return (j.get("data") if isinstance(j, dict) else None)


def records_of(j):
    d = data_of(j)
    return (d.get("records") if isinstance(d, dict) else None) or []


def login(path, username, password):
    st, j, raw = api("POST", path, body={"username": username, "password": password})
    if code_of(j) != 200:
        return None, "HTTP %s / %s" % (st, raw[:120])
    return (data_of(j) or {}).get("token"), "OK"


def wait_ready(deadline=150):
    t0 = time.time()
    while time.time() - t0 < deadline:
        st, _, _ = api("GET", "/api/hello")
        if st != -1:
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------- main
say("=" * 78)
say("Day 22 安全探针：C 端 /api/users 家族越权 + 口令哈希外泄")
say("=" * 78)

say("\n[0] 等待应用就绪")
if not wait_ready():
    say("  [FATAL] 应用 150s 内未就绪")
    raise SystemExit(2)
say("  [OK] 应用已就绪")

DEMO_TOKEN, m1 = login("/api/auth/login", "demo", "demo123")
ADMIN_TOKEN, m2 = login("/api/auth/admin/login", "admin", "admin123")
ORDER_TOKEN, m3 = login("/api/auth/admin/login", "op_order", "op123456")
for nm, tk, msg in (("demo(C端)", DEMO_TOKEN, m1), ("admin(超管)", ADMIN_TOKEN, m2),
                    ("op_order(订单管理员)", ORDER_TOKEN, m3)):
    say("    login %-20s -> %s" % (nm, "OK" if tk else msg))
if not (DEMO_TOKEN and ADMIN_TOKEN and ORDER_TOKEN):
    say("  [FATAL] 三个账号必须都能登录")
    raise SystemExit(2)

DB_USER_N = int(sql1("SELECT count(*) FROM users"))
DEMO_PW = sql1("SELECT password FROM users WHERE username='demo'")
INTRUDER_PW = sql1("SELECT password FROM users WHERE username='intruder'")
INTRUDER_NICK = sql1("SELECT nickname FROM users WHERE username='intruder'")
INTRUDER_ID = int(sql1("SELECT id FROM users WHERE username='intruder'"))
say("    DB: users=%d 条；intruder.id=%d nickname=%s" % (DB_USER_N, INTRUDER_ID, INTRUDER_NICK))

# ---------------------------------------------------------------- A 组
say("\n[A] 匿名访问 —— 期望【真 HTTP 401】（过滤器层拦下，不是 200+code）")
st, j, raw = api("GET", "/api/users")
check("A1 匿名 GET /api/users -> HTTP 401（Security 层真实状态码）", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:100]))

st, j, raw = api("GET", "/api/users/%d" % INTRUDER_ID)
check("A2 匿名 GET /api/users/{id} -> HTTP 401", st == 401,
      "实测 HTTP %s / %s" % (st, raw[:100]))

# ---------------------------------------------------------------- B 组
say("\n[B] C 端 token 拉全站用户列表 —— 期望【只能看到自己】")
st, j, raw = api("GET", "/api/users", token=DEMO_TOKEN)
check("B1 demo token GET /api/users -> HTTP 200 + code 200（能进）",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

recs = records_of(j)
check("B2 ★ 返回【全站 %d 个用户】而非只有自己（越权·水平）" % DB_USER_N,
      len(recs) == DB_USER_N,
      "实测 %d 条；total=%s" % (len(recs), (data_of(j) or {}).get("total")))

names = [r.get("username") for r in recs]
check("B3 ★ 列表里出现别人的账号 intruder（不是只有 demo）",
      "intruder" in names, "实际 usernames=%s" % names)

has_pw_key = any("password" in r for r in recs)
check("B4 ★★ 列表每条都带 password 字段（敏感列外泄）", has_pw_key,
      "第一条的键=%s" % (sorted(recs[0].keys()) if recs else "N/A"))

leaked = [r.get("password") for r in recs if r.get("username") == "intruder"]
check("B5 ★★ 泄露的 password 值与 DB 哈希【逐字节相同】",
      leaked == [INTRUDER_PW], "接口=%r  DB=%r" % (leaked, INTRUDER_PW))

# ---------------------------------------------------------------- C 组
say("\n[C] C 端 token 看【别人】的详情 —— 项目设计：非本人应伪装 404")
st, j, raw = api("GET", "/api/users/%d" % INTRUDER_ID, token=DEMO_TOKEN)
check("C1 demo token GET /api/users/{intruder} -> 拿到 200（设计应为 404）",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

d = data_of(j) or {}
check("C2 ★★ 该响应体含 password 且等于 DB 里 intruder 的哈希",
      d.get("password") == INTRUDER_PW,
      "接口=%r  DB=%r" % (d.get("password"), INTRUDER_PW))

st, j2, raw2 = api("GET", "/api/users/1", token=DEMO_TOKEN)
d2 = data_of(j2) or {}
check("C3 ★ 「看自己」与「看别人」响应【结构同构】（都含 password，无任何区分）",
      set(d2.keys()) == set(d.keys()) and "password" in d2,
      "自己键=%s / 别人键=%s" % (sorted(d2.keys()), sorted(d.keys())))

# ---------------------------------------------------------------- D 组
say("\n[D] C 端 token 改【别人】的昵称 —— 写回原值，DB 无痕")
st, j, raw = api("PUT", "/api/users/%d/nickname" % INTRUDER_ID,
                 token=DEMO_TOKEN, body=INTRUDER_NICK)
check("D1 demo token PUT /api/users/{intruder}/nickname -> 200（能写别人的行）",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s / %s" % (st, code_of(j), raw[:100]))

now_nick = sql1("SELECT nickname FROM users WHERE username='intruder'")
if now_nick != INTRUDER_NICK:
    # 兜底恢复：万一 @RequestBody String 的引号处理与预期不同，立刻还原
    sql("UPDATE users SET nickname='%s' WHERE username='intruder'" % INTRUDER_NICK.replace("'", "''"))
    now_nick = sql1("SELECT nickname FROM users WHERE username='intruder'")
check("D2 DB 值未被改坏（写入的是原值，已还原校验）", now_nick == INTRUDER_NICK,
      "现在=%r 期望=%r" % (now_nick, INTRUDER_NICK))

# ---------------------------------------------------------------- E 组
say("\n[E] 口径对照 —— 这个接口【不是】管理端专属，也没被权限把住")
st, j, raw = api("GET", "/api/users", token=ORDER_TOKEN)
check("E1 ★ op_order（只有 order:list/detail/cancel/ship 四个权限）也能拉全站用户",
      st == 200 and code_of(j) == 200 and len(records_of(j)) == DB_USER_N,
      "实测 HTTP %s code %s 条数=%d" % (st, code_of(j), len(records_of(j))))

st, j, raw = api("GET", "/api/users", token=ADMIN_TOKEN)
check("E2 超管 token 同样 200（说明与权限无关，只与「有没有登录」有关）",
      st == 200 and code_of(j) == 200, "实测 HTTP %s code %s" % (st, code_of(j)))

st, j, raw = api("GET", "/api/admin/users", token=ADMIN_TOKEN)
check("E3 GET /api/admin/users 目前 -> 真 HTTP 404（Day 22 要建的正是它）",
      st == 404, "实测 HTTP %s / %s" % (st, raw[:100]))

# 权限种子里的 path 口径（历史遗留：user:list 指向 C 端路径）
perm_path = sql1("SELECT path FROM permissions WHERE code='user:list'")
perm_roles = sql1("SELECT string_agg(role_id::text, ',' ORDER BY role_id) "
                  "FROM role_permissions rp JOIN permissions p ON p.id=rp.permission_id "
                  "WHERE p.code='user:list'")
check("E4 ★ 权限种子里 user:list 的 path = '/api/users'（C 端路径，需与新建的 /api/admin/users 对齐）",
      perm_path == "/api/users", "实测 path=%r 发给了 role=%s" % (perm_path, perm_roles))

say("\n" + "-" * 78)
say("TOTAL: %d / %d 通过，%d 失败" % (PASS, PASS + FAIL, FAIL))
if FAILS:
    say("FAILED:")
    for f in FAILS:
        say("  - %s" % f)
say("VERDICT: %s" % ("OK —— 三条推论全部实测成立，C 端 /api/users 确认越权 + 泄口令哈希"
                     if FAIL == 0 else "MISMATCH —— 与代码级推论不符，需重新定性"))
say("-" * 78)

if PASS + FAIL != EXPECTED:
    say("!! 护栏：断言总数 %d != EXPECTED %d —— 有断言被跳过，或 EXPECTED 需校准"
        % (PASS + FAIL, EXPECTED))

with open("day22-sec-probe-report.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(LINES) + "\n")
say("(报告已写入 day22-sec-probe-report.txt)")
