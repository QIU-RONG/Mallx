# -*- coding: utf-8 -*-
"""
Day 52 手机号验证码登录 / 注册 —— 端到端验收。

覆盖链路：
  发码（TTL / 限流 / 格式校验）→ 错码 → ★未注册（专属业务码 4041）
  → ★验证码「未被消费」→ 用同一个码注册 → token 真的能用
  → 码一次性作废 → 已注册号正常登录 → 身份域隔离未被破坏 → 清理

★★ 本脚本的写法要点（都是本项目踩出来的规矩）

1. **不信接口自报**：每个关键结论都去 Redis / 数据库核对一遍。
   接口说「发码成功」，就去 Redis 查那个 key 在不在、TTL 对不对；
   接口说「注册成功」，就去 users 表查这一行 —— 是不是真的写进去了、写成了什么样。
2. **对照组**：E 段拿匿名请求与「C 端 token 打管理端接口」当对照 ——
   没有它们，「被拒」有可能只是接口整体坏了。
3. **测试手机号固定 + 首尾都清理**：保证脚本可重复跑（幂等），
   也不会在 users 表里留垃圾影响别的回归。

运行：python day52-sms-auth-verify.py
      python day52-sms-auth-verify.py --selfcheck   （AST 核对满额断言常量）
"""

import ast
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import REPO_ROOT  # noqa: E402  （放在 sys.path 之后导入）

BASE = os.environ.get("MALLX_BASE") or "http://127.0.0.1:8080"
DOCKER = (os.environ.get("MALLX_DOCKER")
          or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe")

# ★ 固定的测试手机号：便于复跑时清理，也不会撞上真实数据
PHONE = "13900009999"
CODE_KEY = "mallx:sms:code:" + PHONE
LIMIT_KEY = "mallx:sms:limit:" + PHONE

EXPECTED_CHECKS = 29

_fails = []


def chk(name, ok, detail=""):
    print("[%s] %s%s" % ("OK  " if ok else "FAIL", name, ("   " + detail) if detail else ""))
    if not ok:
        _fails.append(name)
    return ok


# ---------------------------------------------------------------- 基础设施

def http(method, path, body=None, token=None, timeout=10):
    """★ 显式禁用代理：本机系统代理会把 localhost 也拦了（报 502/10061，看着像服务挂了）。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:200]}


def psql(sql):
    p = subprocess.run([DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx", "-tAc", sql],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    return (p.stdout or "").strip()


def redis(*args):
    p = subprocess.run([DOCKER, "exec", "mallx-redis", "redis-cli"] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    return (p.stdout or "").strip()


def cleanup():
    """幂等清理：把测试手机号留下的东西全删掉（首尾各跑一次）。"""
    psql("DELETE FROM users WHERE phone = '%s'" % PHONE)
    redis("DEL", CODE_KEY)
    redis("DEL", LIMIT_KEY)


# ---------------------------------------------------------------- 主流程

def main():
    # ── 前提护栏：应用没起就别说断言失败（那是环境问题，rc=2） ──
    try:
        st, _ = http("GET", "/api/hello", timeout=5)
    except Exception as e:
        print("★ 前提不成立：后端未就绪（%s）—— 这是环境问题，不是断言失败" % e)
        return 2
    if st != 200:
        print("★ 前提不成立：/api/hello 返回 %s" % st)
        return 2

    cleanup()

    print("=" * 74)
    print("A 段 · 发码")
    print("=" * 74)

    st, r = http("POST", "/api/auth/sms/send", {"phone": PHONE})
    chk("A1 合法手机号发码成功", st == 200 and r.get("code") == 200,
        "http=%s code=%s msg=%s" % (st, r.get("code"), r.get("message")))
    dev = (r.get("data") or {}).get("devCode") or ""
    # ★ 没有短信服务商 ⇒ 非 prod 把明文码放进响应，前端才能弹给用户、脚本才能闭环
    chk("A2 非 prod 返回 devCode（6 位数字）", bool(re.fullmatch(r"\d{6}", dev)), "devCode=%r" % dev)

    saved = redis("GET", CODE_KEY)
    # ★ 不看接口自报：直接问 Redis 那个 key 在不在、值对不对
    chk("A3 ★ Redis 里确实存了这个码（与响应一致）", saved == dev and dev != "",
        "redis=%r resp=%r" % (saved, dev))

    ttl = redis("TTL", CODE_KEY)
    chk("A4 ★ 验证码 TTL 在 (0,300] 秒内", ttl.isdigit() and 0 < int(ttl) <= 300, "ttl=%s" % ttl)

    st, r = http("POST", "/api/auth/sms/send", {"phone": PHONE})
    chk("A5 60 秒内重复发码被限流", r.get("code") == 400,
        "code=%s msg=%s" % (r.get("code"), r.get("message")))

    st, r = http("POST", "/api/auth/sms/send", {"phone": "123"})
    chk("A6 手机号格式非法被拒", r.get("code") == 400,
        "code=%s msg=%s" % (r.get("code"), r.get("message")))

    print()
    print("=" * 74)
    print("B 段 · 用未注册手机号登录")
    print("=" * 74)

    st, r = http("POST", "/api/auth/sms/login", {"phone": PHONE, "code": "000000"})
    chk("B1 错误验证码登录被拒", r.get("code") == 400,
        "code=%s msg=%s" % (r.get("code"), r.get("message")))

    still = redis("GET", CODE_KEY)
    # ★ 校验失败【不消费】—— 否则用户在手机上打错一位，就得重新获取一次
    chk("B2 ★ 错码之后验证码仍在（失败不消费）", still == dev and dev != "", "redis=%r" % still)

    st, r = http("POST", "/api/auth/sms/login", {"phone": PHONE, "code": dev})
    # ★★ 专属业务码 4041：前端靠它决定「跳注册页」。用 message 匹配是脆的（改文案就断）
    chk("B3 ★★ 未注册手机号 → 返回专属业务码 4041", r.get("code") == 4041,
        "code=%s msg=%s" % (r.get("code"), r.get("message")))

    still2 = redis("GET", CODE_KEY)
    # ★★ 这是本功能最容易做错的一步：若在这里就把码消费掉，
    #    用户被引导到注册页后会发现码已作废、又要等 60 秒重发。
    chk("B4 ★★ 未注册时验证码【未被消费】（注册还要用它）", still2 == dev and dev != "",
        "redis=%r" % still2)

    print()
    print("=" * 74)
    print("C 段 · 用同一个码注册")
    print("=" * 74)

    st, r = http("POST", "/api/auth/sms/register",
                 {"phone": PHONE, "code": dev, "nickname": "短信注册用户"})
    chk("C1 注册成功", r.get("code") == 200,
        "code=%s msg=%s" % (r.get("code"), r.get("message")))
    data = r.get("data") or {}
    token = data.get("token") or ""
    uid = data.get("userId")
    chk("C2 注册直接返回 token（注册即登录）", bool(token), "token_len=%d" % len(token))
    chk("C3 返回的 userId 有效", isinstance(uid, int) and uid > 0, "userId=%s" % uid)

    st, me = http("GET", "/api/users/me", token=token)
    chk("C4 ★ 注册返回的 token 真的能用（打 /api/users/me）",
        st == 200 and me.get("code") == 200, "http=%s code=%s" % (st, me.get("code")))
    # ★ 不信自报：拿 me 的 id 与注册返回的 userId 对上
    chk("C5 ★ /users/me 的 id 与注册返回的 userId 一致",
        (me.get("data") or {}).get("id") == uid, "me=%s reg=%s" % ((me.get("data") or {}).get("id"), uid))

    row = psql("SELECT id || '|' || username || '|' || coalesce(phone,'') || '|' || coalesce(nickname,'') "
               "FROM users WHERE phone = '%s'" % PHONE)
    parts = row.split("|") if row else []
    chk("C6 ★ 数据库里确实写入了这一行", len(parts) == 4 and parts[0] == str(uid), "row=%r" % row)
    chk("C7 ★ username == phone（手机号注册不需要另起用户名）",
        len(parts) == 4 and parts[1] == PHONE, "username=%s" % (parts[1] if len(parts) > 1 else "?"))
    chk("C8 昵称落库正确", len(parts) == 4 and parts[3] == "短信注册用户",
        "nickname=%s" % (parts[3] if len(parts) > 3 else "?"))

    pwd = psql("SELECT password FROM users WHERE phone = '%s'" % PHONE)
    # ★ 占位密码也必须过哈希：明文/固定默认密码是最经典的被撞库入口。
    # ⚠️⚠️ 落库形状是 `{bcrypt}$2a$…` ——【带 {id} 算法前缀】，不是裸 `$2a$…`。
    #    bean 是 PasswordEncoderFactories.createDelegatingPasswordEncoder()，
    #    encode() 会自动补上算法前缀（seed 行的 {noop} 属同一前缀体系）。
    #    第一版断言写死 startswith("$2") 因此恒假 —— 那是照【注释】而非照【实现】写的。
    #    判据与 day23-rbac-verify.py 的 B2 保持一致：同一事实用同一判据。
    chk("C9 ★ password 是 bcrypt 哈希（{bcrypt} 前缀）而非明文",
        pwd.startswith("{bcrypt}") and not pwd.startswith("{noop}"),
        "prefix=%s" % pwd[:11])
    # ★★ C9b 的真正判据只能是【拿手机号当密码去登录，必须失败】。
    #   ⚠️ 第一版写的是「哈希串里不含手机号」—— 那是【恒真】的：bcrypt 的输出里
    #   永远不可能出现明文手机号，所以它一条也没守住。控制组第 ④ 组
    #   （把占位密码改成 encode(phone)）实测 0 红，才把这个假绿暴露出来。
    st_c9b, r_c9b = http("POST", "/api/auth/login", {"username": PHONE, "password": PHONE})
    chk("C9b ★ 该账号不能用手机号当密码登录（占位密码不是可猜值）",
        r_c9b.get("code") != 200,
        "code=%s msg=%s" % (r_c9b.get("code"), r_c9b.get("message")))

    gone = redis("EXISTS", CODE_KEY)
    chk("C10 ★ 注册后验证码已作废（一次性）", gone == "0", "exists=%s" % gone)

    print()
    print("=" * 74)
    print("D 段 · 已注册号的正常登录")
    print("=" * 74)

    st, r = http("POST", "/api/auth/sms/login", {"phone": PHONE, "code": dev})
    chk("D1 已消费的验证码不能再登录（一次性）", r.get("code") == 400,
        "code=%s msg=%s" % (r.get("code"), r.get("message")))

    # ★ 60 秒发送限流还在，直接删掉限流 key —— 否则这一步要干等一分钟。
    #   这是测试对 Redis 的【显式干预】，不是绕过被测逻辑：限流本身已在 A5 验过。
    redis("DEL", LIMIT_KEY)
    st, r = http("POST", "/api/auth/sms/send", {"phone": PHONE})
    code2 = (r.get("data") or {}).get("devCode") or ""
    chk("D2 已注册号再次发码成功", r.get("code") == 200 and bool(code2), "code=%s" % r.get("code"))

    st, r = http("POST", "/api/auth/sms/login", {"phone": PHONE, "code": code2})
    chk("D3 ★ 已注册号用验证码登录成功（不再返回 4041）",
        r.get("code") == 200 and (r.get("data") or {}).get("token"),
        "code=%s" % r.get("code"))
    token2 = (r.get("data") or {}).get("token") or ""
    st, me2 = http("GET", "/api/users/me", token=token2)
    chk("D4 ★ 登录拿到的 token 可用且指向同一个用户",
        st == 200 and (me2.get("data") or {}).get("id") == uid,
        "me_id=%s uid=%s" % ((me2.get("data") or {}).get("id"), uid))

    exists2 = redis("EXISTS", CODE_KEY)
    chk("D5 ★ 登录成功后验证码同样被作废", exists2 == "0", "exists=%s" % exists2)

    print()
    print("=" * 74)
    print("E 段 · 安全边界（对照组：证明「被拒」不是接口整体坏了）")
    print("=" * 74)

    st, _ = http("GET", "/api/users/me")
    chk("E1 匿名访问 /api/users/me → 401（白名单只放行 auth，没放行 users）", st == 401, "http=%s" % st)

    st, _ = http("GET", "/api/admin/users", token=token2)
    # ★ 身份域隔离（Day 44）：C 端 token 打管理端必须是真 403，而不是「碰巧能过」
    chk("E2 ★ C 端 token 打管理端接口 → 403（跨域隔离未被破坏）", st == 403, "http=%s" % st)

    print()
    cleanup()
    left = psql("SELECT count(*) FROM users WHERE phone = '%s'" % PHONE)
    chk("E3 清理完成（测试用户已删除，脚本可重复跑）", left == "0", "count=%s" % left)

    print()
    print("=" * 74)
    print("断言 %d 条，失败 %d 条 ⇒ %s"
          % (EXPECTED_CHECKS, len(_fails), "VERDICT: PASS" if not _fails else "VERDICT: FAIL"))
    if _fails:
        for f in _fails:
            print("  - " + f)
    return 0 if not _fails else 1


def selfcheck():
    """AST 数出 chk( 调用点，与 EXPECTED_CHECKS 比对（纯静态、秒级、进 CI）。"""
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
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    sys.exit(main())
