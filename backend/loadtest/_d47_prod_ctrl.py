# -*- coding: utf-8 -*-
"""V1.4 生产编排护栏的【控制组】—— 四组已知会出事故的改法，护栏必须 FAIL。

只测「好的那一侧」= 什么都没测。这个脚本存在的全部意义是证明 day47-prod-compose-guard.py 有牙。
跑法：python backend/loadtest/_d47_prod_ctrl.py
（会临时改动 2 个已入库文件，跑完用 git checkout 还原；每组还原后都会断言工作区干净）
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.abspath(__file__))            # backend/loadtest
REPO = os.path.dirname(os.path.dirname(ROOT))                # D:\MallX
GUARD = os.path.join(ROOT, "day47-prod-compose-guard.py")
COMPOSE_REL = "deploy/docker-compose.prod.yml"
SH_REL = "deploy/deploy.sh"


def run_guard():
    p = subprocess.run([sys.executable, GUARD], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = p.stdout or ""
    fails = [l.strip()[7:].strip() for l in out.splitlines() if l.strip().startswith("[FAIL]")]
    return p.returncode, fails


def dirty():
    """★ 只看【已跟踪】文件的改动 —— 未跟踪的新文件（??）不算脏。"""
    p = subprocess.run(["git", "status", "--short"], cwd=REPO, capture_output=True, text=True)
    return [l for l in (p.stdout or "").splitlines() if l.strip() and not l.startswith("??")]


_BACKUP = {}


def path_of(rel):
    return os.path.join(REPO, rel.replace("/", os.sep))


def write(rel, text):
    """★ 写完立刻读回校验 —— 落盘可能【静默失败】（本机实测过一次：open().write()
       返回成功、随后 grep 到的仍是旧内容）。不复验的话，控制组会给出「没红」的假结论，
       而假绿比假红危险得多。"""
    p = path_of(rel)
    io.open(p, "w", encoding="utf-8", newline="").write(text)
    back = io.open(p, encoding="utf-8", newline="").read()
    assert back == text, "写入未生效（%s）—— 控制组的结论不可信，请改用其它方式改文件" % rel


def patch(rel, old, new):
    """★ 用【内存备份】而不是 `git checkout` 还原：
       本轮新增的 deploy/*.yml 还没提交 ⇒ 未跟踪文件 checkout 不回来，
       第一版就栽在这（改动累积 ⇒ 后面几组的失败数是前面几组的叠加）。"""
    if rel not in _BACKUP:
        _BACKUP[rel] = io.open(path_of(rel), encoding="utf-8", newline="").read()
    s = _BACKUP[rel]
    assert old in s, "pattern not found in %s" % rel
    write(rel, s.replace(old, new, 1))


def restore(rel):
    write(rel, _BACKUP[rel])


cases = []


def case(name, mutate, expect, cleanup):
    mutate()
    rc, fails = run_guard()
    cleanup()
    left = dirty()
    hit = [f for f in fails if any(k in f for k in expect)]
    ok = rc != 0 and bool(hit) and not left
    cases.append((name, ok))
    print("[%s] %s   rc=%d  失败 %d 条" % ("OK " if ok else "FAIL", name, rc, len(fails)))
    for f in fails:
        print("        - %s" % f[:90])
    if left:
        print("        !! 未还原：%s" % left)


print("=" * 78)
print("V1.4 生产编排护栏 · 控制组（4 组，每组都必须 FAIL 且失败点命中预期）")
print("=" * 78)

rc, fails = run_guard()
print("[基线] 当前仓库 rc=%d 失败=%d 条（期望 0/0）" % (rc, len(fails)))
assert rc == 0, "基线不绿，控制组无从谈起"
print()

case("① postgres 发布 5432 到宿主（公网可达的 PG）",
     lambda: patch(COMPOSE_REL, '    container_name: mallx-postgres-prod\n',
                   '    container_name: mallx-postgres-prod\n    ports:\n      - "5432:5432"\n'),
     ["A ", "postgres"],
     lambda: restore(COMPOSE_REL))

case("② 镜像 tag 用 :latest（无法回答线上版本 / 无法回滚）",
     lambda: patch(COMPOSE_REL, ":${IMAGE_TAG:?IMAGE_TAG 未设置（例：1.4.0）}", ":latest"),
     ["B1"],
     lambda: restore(COMPOSE_REL))

case("③ 删掉 app 的 mem_limit（容器感知变摆设）",
     lambda: patch(COMPOSE_REL, "    mem_limit: ${APP_MEM_LIMIT:-768m}\n", ""),
     ["C1"],
     lambda: restore(COMPOSE_REL))

case("④ deploy.sh 里加一句 down -v（部署 = 删库）",
     lambda: patch(SH_REL, 'log "拉取镜像', 'docker compose -f "$COMPOSE_FILE" down -v\nlog "拉取镜像'),
     ["D3"],
     lambda: restore(SH_REL))

print()
print("=" * 78)
bad = [c for c in cases if not c[1]]
print("控制组结果：%d/%d 命中预期（失败数为 0 ⇒ 什么都没守住）" % (len(cases) - len(bad), len(cases)))
print("VERDICT: %s" % ("OK" if not bad else "FAIL"))
print("=" * 78)
sys.exit(0 if not bad else 1)
