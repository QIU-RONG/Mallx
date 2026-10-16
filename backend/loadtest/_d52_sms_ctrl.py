# -*- coding: utf-8 -*-
"""
Day 52「手机号验证码登录/注册」验收脚本的【控制组】。

跑法：python _d52_sms_ctrl.py          （约 6-8 分钟，含 4 次 mvn 构建 + 应用重启）

为什么必须做：本项目铁律 —— **新写的护栏必须自带控制组**。
拿「故意改坏的实现」回跑验收脚本，脚本**必须红**；
红 0 条 = 这条断言什么都没守住（Day 48 就抓出过两条这样的假绿）。

四组变异（每组都对应一个「真实世界里会犯的错」）：

  ① 去掉发码限流          → A5 必须红
     （忘了限流 = 任何人可以拿验证码接口刷短信费 / 撞码）
  ② 未注册返回普通 400    → B3 必须红
     （丢掉专属业务码 4041 ⇒ 前端再也没法区分「未注册」与「验证码错」，
       只能去匹配文案，后端改一个字就静默失效）
  ③ 登录时把码消费掉      → B4 必须红（+ 下游级联）
     （`verify` 写成 `verifyAndConsume` ⇒ 用户被送去注册页时码已作废，
       又得等 60 秒重发 —— 这是本功能最容易犯的错）
  ④ 占位密码改成 encode(手机号) → C9b 必须红
     （占位密码可猜 = 关掉的密码登录其实没关）

⚠️ 每一组改完必须**立刻还原并读回校验**：控制组自己的改动残留会污染
   后面几组的结果，让「失败数」变成前面几组的叠加（Day 47 踩过）。
"""

import io
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\MallX"
LOADTEST = os.path.join(REPO, "backend", "loadtest")
USER_SRC = os.path.join(REPO, "backend", "mallx", "mall-user", "src", "main", "java", "com", "mallx", "user")
CTRL = os.path.join(USER_SRC, "controller", "AuthController.java")
SMS_IMPL = os.path.join(USER_SRC, "service", "impl", "SmsCodeServiceImpl.java")
USER_IMPL = os.path.join(USER_SRC, "service", "impl", "UserServiceImpl.java")

MVN = r"D:\Maven\apache-maven-3.9.15\bin\mvn.cmd"
JAVA = r"D:\java\bin\java.exe"
DOCKER = (os.environ.get("MALLX_DOCKER")
          or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe")
TARGET = os.path.join(REPO, "backend", "mallx", "mall-server", "target")
JAR = "mall-server-0.0.1-SNAPSHOT.jar"
SCRIPT = os.path.join(LOADTEST, "day52-sms-auth-verify.py")
APP_LOG = os.path.join(REPO, "_ctrl52-app.log")

# ---------------------------------------------------------------- 变异定义
# (说明, 文件, 原文, 改后, 必须红掉的断言名, 是否要求「没有多余的红」)
CASES = [
    # ★ strict=False 的理由（首跑实测）：去掉限流后 A5 的「第二次发码」会被真正执行
    #   ⇒ Redis 里的码被覆盖 ⇒ 后面所有「拿 A1 抓到的那个码」去登录/注册的断言**级联红**
    #   （B2/B3/B4/C1../D../E2）。这不是「期望写窄」，而是这道变异本身破坏了验收脚本
    #   「码在流程中保持不变」的前提 —— 反过来说，A5 守的不只是限流，
    #   还是后续十几条断言的一条**前置条件**。
    ("① 去掉发码限流（60 秒内可反复发）",
     SMS_IMPL,
     "        if (Boolean.FALSE.equals(first)) {",
     "        if (false) {",
     ["A5"], False),

    ("② 未注册返回普通 400（丢掉专属业务码 4041）",
     CTRL,
     "            throw new BusinessException(ResultCode.PHONE_NOT_REGISTERED.getCode(),\n"
     "                    ResultCode.PHONE_NOT_REGISTERED.getMessage());",
     "            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),\n"
     "                    \"该手机号未注册，请先注册\");",
     ["B3"], True),

    ("③ 登录时就把验证码消费掉（verify → verifyAndConsume）",
     CTRL,
     "        smsCodeService.verify(dto.getPhone(), dto.getCode());",
     "        smsCodeService.verifyAndConsume(dto.getPhone(), dto.getCode());",
     ["B4"], False),   # 码被消费 ⇒ 后面 C/D 段会级联红，故不要求「零多余」

    ("④ 占位密码改成 encode(手机号)（可猜）",
     USER_IMPL,
     "        u.setPassword(passwordEncoder.encode(UUID.randomUUID().toString()));",
     "        u.setPassword(passwordEncoder.encode(phone));",
     ["C9b"], True),
]

_BASE = {}


def read(path):
    return io.open(path, encoding="utf-8", newline="").read()


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="").write(text)
    # ★ 写完立刻读回校验 —— 「write 成功但内容没变」本项目踩过不止一次
    return read(path) == text


def _nl(text, crlf):
    """把 Python 字面量里的 `\\n` 换成源码的真实换行风格。

    ★ Java 源码是 **CRLF**（实测），而多行变异模式在字面量里只有 `\\n` ——
      不转换的话**双行以上的模式永远匹配不上**。单行模式碰巧能过，
      所以这个 bug 只在多行模式上暴露（第一版第 ② 组就栽在这）。
    """
    return text.replace("\n", "\r\n") if crlf else text


def patch(path, old, new):
    if path not in _BASE:
        _BASE[path] = read(path)
    s = _BASE[path]
    crlf = "\r\n" in s
    o, n = _nl(old, crlf), _nl(new, crlf)
    assert o in s, ("变异模式在 %s 里找不到（CRLF=%s）：\n%s"
                    % (os.path.basename(path), crlf, o[:120]))
    ok = write(path, s.replace(o, n, 1))
    assert ok, "写回后内容不一致：%s" % path


def revert(path):
    ok = write(path, _BASE[path])
    assert ok, "还原后内容不一致：%s" % path


# ---------------------------------------------------------------- 进程 / 构建

def kill_app():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
          "Where-Object { $_.CommandLine -like '*%s*' } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % JAR)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, text=True, timeout=60)
    time.sleep(2)


def build():
    env = dict(os.environ, MAVEN_OPTS="-Xmx1024m")
    p = subprocess.run([MVN, "-o", "install", "-DskipTests"],
                       cwd=os.path.join(REPO, "backend", "mallx"),
                       env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out


def start_app():
    log = io.open(APP_LOG, "w", encoding="utf-8")
    subprocess.Popen([JAVA, "-Xmx384m", "-XX:MaxMetaspaceSize=160m",
                      "-XX:TieredStopAtLevel=1", "-XX:+UseSerialGC",
                      "-jar", JAR, "--server.port=8080"],
                     cwd=TARGET, stdout=log, stderr=subprocess.STDOUT)
    return wait_healthy()


def wait_healthy(timeout=90):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with opener.open("http://127.0.0.1:8080/api/hello", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


# ---------------------------------------------------------------- 跑验收

def run_verify():
    p = subprocess.run([sys.executable, SCRIPT], cwd=LOADTEST,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    fails = re.findall(r"^\[FAIL\]\s+(\S+)", out, re.M)
    return p.returncode, sorted(set(fails)), out


def precheck_infra():
    """★ 前提护栏：容器没起就说「环境问题」，别把 A1..A5 全红报成断言失败。

    首跑实测：Docker 引擎停了 ⇒ Redis 6380 / RabbitMQ 5672 全不可达 ⇒
    应用照样能起（`/api/hello` 200），但发码需要 Redis ⇒ 24 条断言一起红，
    看着像「实现全坏了」。**这类红必须与真断言失败分开**（rc=2 ≠ rc=1），
    否则人会去修一个根本没错的东西（Day 49 同款教训）。
    """
    problems = []
    checks = (
        ("redis", [DOCKER, "exec", "mallx-redis", "redis-cli", "PING"]),
        ("postgres", [DOCKER, "exec", "mallx-postgres",
                      "psql", "-U", "mallx", "-d", "mallx", "-tAc", "SELECT 1"]),
    )
    for name, cmd in checks:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
        except Exception as e:
            problems.append("%s（%s）" % (name, e))
            continue
        if p.returncode != 0 or not (p.stdout or "").strip():
            msg = ((p.stderr or p.stdout or "").strip().replace("\n", " "))[:90]
            problems.append("%s（%s）" % (name, msg))
    return problems


def main():
    print("=" * 78)
    print("Day 52 控制组：%d 组变异，每组都要经历 「改坏 → 重建 → 重启 → 回跑」" % len(CASES))
    print("=" * 78)

    probs = precheck_infra()
    if probs:
        print("★ 前提不成立：%s" % "；".join(probs))
        print("  ⇒ 这是【环境问题】（Docker 引擎 / 容器没起），不是断言失败。")
        print("     先起 Docker Desktop 并等容器 healthy，再重跑本脚本（rc=2）。")
        return 2

    # ── 基线之前先【重建 + 重启】——
    #   ★ 为什么不能直接用跑着的那个 jar：脚本若中途崩溃（首跑实测：第 2 组抛异常），
    #     收尾的「还原 → 重建」就被跳过了，**磁盘上的 jar 仍是上一次变异的代码**，
    #     而源码看着是干净的。此时直接跑基线会红得莫名其妙，且容易误判成「实现坏了」。
    print("[准备] 按当前源码重建并重启应用（保证基线反映的是干净源码）")
    kill_app()
    ok, out = build()
    if not ok:
        print("★ 构建失败，放弃：")
        for l in out.splitlines():
            if "ERROR" in l:
                print("  " + l.strip()[:150])
        return 2
    if not start_app():
        print("★ 应用起不来，放弃（环境问题，不是断言失败）")
        return 2

    # ── 基线：变异之前必须全绿，否则先修脚本而不是继续做变异 ──
    rc, fails, _ = run_verify()
    print("\n[基线] rc=%s 失败=%s" % (rc, fails or "无"))
    if rc != 0 or fails:
        print("★ 基线不绿 ⇒ 先修验收脚本 / 实现，别做变异（否则分不清谁的问题）")
        return 2
    print("  ⇒ 基线全绿，可以做变异\n")

    bad = 0
    for i, (desc, path, old, new, must, strict) in enumerate(CASES, 1):
        print("=" * 78)
        print("第 %d 组 · %s" % (i, desc))
        print("=" * 78)

        patch(path, old, new)
        kill_app()
        ok, out = build()
        if not ok:
            print("  ★ 构建失败（变异本身编译不过），跳过本组")
            for l in out.splitlines():
                if "ERROR" in l and (".java" in l or "symbol" in l):
                    print("    " + l.strip()[:150])
            revert(path)
            bad += 1
            continue
        if not start_app():
            print("  ★ 应用起不来，跳过本组")
            revert(path)
            bad += 1
            continue

        rc, fails, _ = run_verify()
        hit = [m for m in must if m in fails]
        extra = [f for f in fails if f not in must]

        print("  实际红的断言：%s" % (fails or "无"))
        print("  必须红的：%s ⇒ %s" % (must, "全部命中" if len(hit) == len(must) else "★ 缺 %s" % [m for m in must if m not in fails]))
        if extra:
            print("  额外的红：%s" % extra)

        good = (len(hit) == len(must)) and (not strict or not extra)
        if not good:
            bad += 1
            if not hit:
                print("  ★★ 一条都没红 ⇒ 这组断言【什么都没守住】（假绿）")
            elif strict and extra:
                print("  ★ 有多余的红 ⇒ 期望写窄了（先逐条看清原因再改期望）")
        print("  结论：%s\n" % ("符合预期" if good else "★ 不符预期"))

        revert(path)

    # ── 收尾：还原 → 复核工作区 → 重建 → 重启（把环境留成可用的样子）──
    print("=" * 78)
    print("收尾")
    print("=" * 78)
    dirty = []
    for path in _BASE:
        same = (read(path) == _BASE[path])
        print("  %-22s 还原%s" % (os.path.basename(path), "干净" if same else "★ 不干净"))
        if not same:
            dirty.append(path)

    kill_app()
    ok, out = build()
    print("  重建：%s" % ("成功" if ok else "★ 失败"))
    started = start_app() if ok else False
    print("  应用已重启：%s" % ("是" if started else "★ 否"))

    if started:
        rc, fails, _ = run_verify()
        print("  还原后回跑：rc=%s 失败=%s" % (rc, fails or "无"))

    print()
    if bad or dirty:
        print("VERDICT: FAIL —— %d 组不符预期，%d 个文件还原不干净" % (bad, len(dirty)))
        return 1
    print("VERDICT: PASS —— %d 组变异全部按预期命中，且还原干净" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
