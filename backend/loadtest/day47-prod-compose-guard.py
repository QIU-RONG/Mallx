# -*- coding: utf-8 -*-
"""Day 47（V1.4 后半段）· 生产编排【静态护栏】。

=============================================================================
为什么需要它
=============================================================================
远端托管最容易出的事故，全都长得很像「配置写少了几个字」：
  · 数据库顺手 `ports: 5432:5432`  ⇒ 公网可达的 PG，勒索软件当天就来；
  · 镜像 tag 用 `:latest`          ⇒ 「线上跑的是哪一版」无法回答，回滚变成伪命题；
  · 忘了 `mem_limit`               ⇒ `-XX:MaxRAMPercentage` 只能按宿主内存算，「容器感知」是摆设；
  · 部署脚本里一句 `down -v`       ⇒ 那不是重启，那是删库。

这些**没有任何一条会在 CI 的编译/测试里报错**，也不会在 `docker compose up -d` 时报错
—— 它们只在上线后的某一天变成事故。⇒ 只能靠静态判据提前拦。

=============================================================================
判据来源：对着【设计意图】写，不对着文件现状写
=============================================================================
每一条断言都对应上面某一类事故。**文件当前是绿的，不代表断言没用** ——
控制组（见下）才是它有用的证明。

解析方式说明（为什么要写这一段）
--------------------------------
本脚本用【缩进分段】的文本解析而不是 yaml 库：`deploy/*.yml` 的服务名固定顶两格，
比依赖 runner 上是否装了 PyYAML 更稳。
★ 但文本解析最大的风险是「悄悄解析失败 ⇒ 一条都没查 ⇒ 全绿」，
  所以 [A6] 专门断言「解析出的服务数 == 期望值」—— **解析本身也要有判据**。

=============================================================================
控制组（`python backend/loadtest/_d47_prod_ctrl.py`，4 组，全部必须 FAIL）
=============================================================================
  ① 给 postgres 加 `ports: 5432:5432`   ⇒ A1 红（1 条，零误伤）
  ② 镜像 tag 改成 `:latest`             ⇒ B1 红
  ③ 删掉 app 的 `mem_limit`             ⇒ C1 红
  ④ deploy.sh 里加一句 `down -v`        ⇒ D3 红（★ 部署脚本删库是死罪）

运行：python day47-prod-compose-guard.py      （纯静态，秒级，不需要 Docker/DB）
"""
from _paths import REPO_ROOT
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT = os.path.join(REPO_ROOT, "backend", "loadtest", "day47-prod-compose-guard-report.txt")
DEPLOY = os.path.join(REPO_ROOT, "deploy")
COMPOSE = os.path.join(DEPLOY, "docker-compose.prod.yml")
CADDYFILE = os.path.join(DEPLOY, "Caddyfile")
DEPLOY_SH = os.path.join(DEPLOY, "deploy.sh")
BACKUP_SH = os.path.join(DEPLOY, "backup-db.sh")

# 满额护栏（★ 别手工数：跑一遍看报告里的 ASSERTIONS 行与它是否相等）
EXPECTED_CHECKS = 19

# 期望的 5 个服务 —— 少了说明文件被改残或解析失败，多了说明有人加了没被审的服务
EXPECT_SERVICES = ["caddy", "app", "postgres", "redis", "rabbitmq"]

# ★ 必填项：这些必须写成 `${X:?...}`（缺失即拒绝启动），不能给默认值
REQUIRED_VARS = ["APP_DOMAIN", "IMAGE_TAG", "DB_PASSWORD", "JWT_SECRET", "REDIS_PASSWORD"]

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


def read(path):
    if not os.path.exists(path):
        return None
    return io.open(path, encoding="utf-8").read()


def split_services(text):
    """按顶两格的 `name:` 把 compose 切成 {服务名: 块文本}。

    ★ 只取 `services:` 到下一个顶层段之间的部分 —— 否则 `volumes:` 下的
      `pgdata:` / `caddy-data:` 也是顶两格，会被当成服务（第一版就踩了，
      表现是 [A0] 直接红）。
    """
    m = re.search(r"^services:\s*$", text, re.M)
    if m:
        rest = text[m.end():]
        nxt = re.search(r"^[a-zA-Z_]+:\s*$", rest, re.M)     # volumes: / networks: …
        text = rest[:nxt.start()] if nxt else rest
    blocks = {}
    cur = None
    buf = []
    for line in text.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if m:
            if cur:
                blocks[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
            continue
        if cur:
            buf.append(line)
    if cur:
        blocks[cur] = "\n".join(buf)
    return blocks


def has_ports(block):
    """有没有把端口发布到宿主（`ports:` 段）—— `expose` 不算。"""
    m = re.search(r"^    ports:\s*$", block, re.M)
    return bool(m)


def main():
    say("=" * 78)
    say("Day 47（V1.4 后半段）· 生产编排静态护栏")
    say("对象：deploy/docker-compose.prod.yml / Caddyfile / deploy.sh / backup-db.sh")
    say("=" * 78)

    comp = read(COMPOSE)
    if comp is None:
        chk("docker-compose.prod.yml 存在", False)
        return verdict()
    svcs = split_services(comp)

    # ---------------- [A] 暴露面 ----------------
    say("")
    say("[A] 暴露面（★ 公网可达的中间件 = 事故，不是配置风格问题）")
    chk("A0 解析出的服务数与期望一致（★ 解析本身也要有判据，否则全绿可能是没查）",
        sorted(svcs) == sorted(EXPECT_SERVICES), "实得=%s" % sorted(svcs))

    for name in ("postgres", "redis", "rabbitmq"):
        blk = svcs.get(name, "")
        chk("A %s 【不】发布端口到宿主（要进去用 exec，不要 ports:）" % name,
            name in svcs and not has_ports(blk))

    app = svcs.get("app", "")
    chk("A app 【不】直接对外发布 8080（统一由 caddy 反代，TLS 只在一处终止）",
        "app" in svcs and not has_ports(app) and re.search(r"^\s+- \"?8080\"?\s*$", app, re.M)
        is not None)
    caddy = svcs.get("caddy", "")
    chk("A caddy 发布 80 / 443（它是唯一的公网入口）",
        "caddy" in svcs and "\"80:80\"" in caddy and "\"443:443\"" in caddy)

    # ---------------- [B] 镜像与版本 ----------------
    say("")
    say("[B] 镜像与版本（★ 可回答「线上是哪一版」是所有回滚操作的前提）")
    img = re.search(r"^\s+image:\s*(\S+)", app, re.M)
    img = img.group(1) if img else ""
    chk("B1 镜像 tag 不是 :latest（latest 无法回答版本、无法回滚）",
        bool(img) and not img.endswith(":latest") and "${IMAGE_TAG" in img, "image=%s" % img)
    chk("B2 app 段没有 `build:`（★ 远端不编译：那会让线上跑的不是验收过的那个 jar）",
        not re.search(r"^\s+build:", app, re.M))
    missing = [v for v in REQUIRED_VARS if ("${%s:?" % v) not in comp]
    chk("B3 必填项一律用 `${X:?}`（缺失即拒绝启动，不给默认值）",
        not missing, "缺=%s" % (missing or "无"))

    # ---------------- [C] 运行时与反向代理 ----------------
    say("")
    say("[C] 运行时 / 反代")
    chk("C1 app 有 mem_limit（没有它，MaxRAMPercentage 只能按宿主算 ⇒ 容器感知是摆设）",
        re.search(r"^\s+mem_limit:", app, re.M) is not None)
    no_restart = [n for n in EXPECT_SERVICES if not re.search(r"^\s+restart:\s*always",
                                                             svcs.get(n, ""), re.M)]
    chk("C2 所有服务 restart: always", not no_restart, "缺=%s" % (no_restart or "无"))
    no_log = [n for n in EXPECT_SERVICES if "logging:" not in svcs.get(n, "")]
    chk("C3 所有服务都限制了日志体积（无限增长的 json.log 是磁盘满头号成因）",
        not no_log, "缺=%s" % (no_log or "无"))
    # ★ 只看【探针那一行】：整个 app 块里有注释在讨论 /api/hello（说它为什么不够用），
    #   拿整块去匹配会被自己写的注释带偏（第一版就红在这）。
    probe = re.search(r"^\s+test:\s*\[.*$", svcs.get("app", ""), re.M)
    probe = probe.group(0) if probe else ""
    chk("C4 app 的健康检查用 actuator readiness（探针行里不能出现 /api/hello）",
        "actuator/health/readiness" in probe and "/api/hello" not in probe,
        "probe=%s" % (probe.strip()[:80] or "无"))

    cf = read(CADDYFILE) or ""
    chk("C5 Caddy 显式拒绝 /actuator/**（返回 404 而不是 403 —— 403 等于承认它存在）",
        bool(re.search(r"@actuator\s+path\s+/actuator", cf)) and "respond @actuator 404" in cf)
    chk("C6 Caddy 显式拒绝 swagger（接口清单不该出现在公网）",
        "@docs" in cf and "respond @docs 404" in cf)

    # ---------------- [D] 部署 / 备份脚本 ----------------
    say("")
    say("[D] 部署 / 备份脚本")
    ds = read(DEPLOY_SH) or ""
    # ★ 只看【非注释行】：脚本顶部的注释里专门解释了「为什么不能写 down -v」，
    #   拿全文去匹配会被自己写的注释带偏（与上面 C4 同一个教训）。
    ds_code = "\n".join(l for l in ds.splitlines() if not l.lstrip().startswith("#"))
    chk("D1 deploy.sh 带【失败自动回滚】（up -d 的退出码证明不了应用能用）",
        "OLD_TAG" in ds_code and "回滚" in ds_code)
    chk("D2 deploy.sh 拒绝 latest 作为发布版本", "latest" in ds_code and "die" in ds_code)
    # ★★ 部署脚本里出现 down -v = 删库。这条断言存在的理由不需要更多解释。
    chk("D3 ★ deploy.sh 的【代码行】里没有 `down -v`（部署 = 更新，不是删库）",
        not re.search(r"down\s+-[a-z]*v", ds_code))
    bs = read(BACKUP_SH) or ""
    chk("D4 备份用 pg_dump -Fc（custom 格式才支持【只恢复某一张表】—— 真出事时要的就是这个）",
        "pg_dump" in bs and "-Fc" in bs)

    return verdict()


def verdict():
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, n_pass + n_fail, EXPECTED_CHECKS))
    if n_pass + n_fail != EXPECTED_CHECKS:
        say("★ 护栏未过：实得 %d 条，期望 %d 条" % (n_pass + n_fail, EXPECTED_CHECKS))
    ok = (n_fail == 0 and n_pass + n_fail == EXPECTED_CHECKS)
    say("VERDICT: %s" % ("OK" if ok else "FAIL"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines_out) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
