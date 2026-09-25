"""Day 16 · GitHub 远端核对

回答一个问题：本地提交的代码，GitHub 上到底有没有？
做法：直连 GitHub REST API（**绕过系统代理**，与 git 的 http.proxy 是两套东西），
      取远端分支 / 提交时间线 / 文件树，与本地 git 的事实逐项对照。

纯只读：只用 GET，不动远端、不动本地仓库。
"""
from _paths import lp

import json
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = "QIU-RONG/Mallx"
API = f"https://api.github.com/repos/{REPO}"
LOCAL = r"D:\MallX"

# ★ 必须显式清空代理：本机 git 走 Clash（127.0.0.1:9674），
#   但 GitHub API 直连是通的；若继承系统代理而代理没开，就会假失败。
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path):
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "mallx-audit"},
    )
    with opener.open(req, timeout=30) as r:
        return json.load(r)


def git(*args):
    out = subprocess.run(
        ["git", "-C", LOCAL, *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return out.stdout.strip()


lines = []
say = lines.append

say("=" * 74)
say("远端仓库事实")
say("=" * 74)

repo = api("")
say(f"  仓库           : {repo['full_name']}")
say(f"  default_branch : {repo['default_branch']}")
say(f"  是否私有        : {repo['private']}")
say(f"  pushed_at      : {repo['pushed_at']}")

branches = api("/branches")
say(f"  远端分支       : {', '.join(b['name'] for b in branches)}")

# 远端默认分支的 HEAD
head = api(f"/commits/{repo['default_branch']}")["sha"]
say(f"  远端 HEAD      : {head[:7]}")

say("")
say("=" * 74)
say("本地 vs 远端：SHA 逐层对齐")
say("=" * 74)

local_head = git("rev-parse", "main")
local_count = git("rev-list", "--count", "main")
say(f"  本地 main      : {local_head[:7]}   （共 {local_count} 个提交）")
say(f"  远端 main      : {head[:7]}")

# 远端 HEAD 是否是本地 main 的祖先（= 远端没有本地没有的东西）
anc = subprocess.run(
    ["git", "-C", LOCAL, "merge-base", "--is-ancestor", head, local_head],
    capture_output=True,
)
say(f"  远端 HEAD 是本地祖先 : {'是 -> 远端是本地的一个前缀，没有分叉' if anc.returncode == 0 else '否 -> 历史分叉了！'}")

ahead = git("rev-list", "--count", f"{head}..{local_head}")
say(f"  本地领先远端的提交数 : {ahead}")
if ahead != "0":
    say("  未推送的提交：")
    for ln in git("log", "--oneline", f"{head}..{local_head}").splitlines():
        say(f"    {ln}")

# 未提交（工作区）改动
dirty = git("status", "--short")
say("")
say(f"  工作区未提交改动 ({len(dirty.splitlines())} 个) :")
for ln in dirty.splitlines():
    say(f"    {ln}")

say("")
say("=" * 74)
say("远端提交时间线（最近 12 条）")
say("=" * 74)
commits = api("/commits?per_page=100")
say(f"  第一页取回 {len(commits)} 条（per_page=100 上限）")
for c in commits[:12]:
    msg = c["commit"]["message"].splitlines()[0]
    say(f"  {c['sha'][:7]}  {c['commit']['author']['date']}  {msg[:58]}")
say("  ...")
for c in commits[-3:]:
    msg = c["commit"]["message"].splitlines()[0]
    say(f"  {c['sha'][:7]}  {c['commit']['author']['date']}  {msg[:58]}")

say("")
say("=" * 74)
say("远端文件树里，历日关键产物是否都在")
say("=" * 74)
tree = api(f"/git/trees/{head}?recursive=1")["tree"]
paths = [e["path"] for e in tree]
say(f"  远端树条目数 : {len(paths)}")

probes = [
    ("Day 09 起停脚本", "learning/day09/start-app.bat"),
    ("Day 12 下单文档", "docs/daily/Day-12-从购物车下单.md"),
    ("Day 13 端到端脚本", "backend/loadtest/day13-e2e.py"),
    ("Day 14 校准 SQL", "backend/loadtest/day14-recalibrate.sql"),
    ("Day 15 验收脚本", "backend/loadtest/day15-ship-confirm.py"),
    ("Day 15 文档", "docs/daily/Day-15-发货与确认收货.md"),
    ("Day 16 DDL 补丁", "backend/sql/04-review-constraints.sql"),
    ("Day 16 模块 pom", "backend/mallx/mall-review/pom.xml"),
    ("Day 16 契约类", "backend/mallx/mall-order/src/main/java/com/mallx/order/api/OrderItemBuyContext.java"),
    ("Day 16 服务骨架", "backend/mallx/mall-review/src/main/java/com/mallx/review/service/impl/ReviewServiceImpl.java"),
    ("Day 16 规划文档", "docs/daily/Day-16-商品评价.md"),
]
for label, p in probes:
    say(f"  {'OK ' if p in paths else 'MISS'}  {label:16} {p}")

say("")
say("=" * 74)
say("被 .gitignore 排除、因此【永远】不会出现在 GitHub 上的东西")
say("=" * 74)
ignored = subprocess.run(
    ["git", "-C", LOCAL, "status", "--short", "--ignored"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
).stdout.splitlines()
ign = [ln[3:] for ln in ignored if ln.startswith("!!")]
for p in ign:
    say(f"  !  {p}")

say("")
say("=" * 74)
say("小结")
say("=" * 74)
missing = [p for _, p in probes if p not in paths]
say(f"  远端缺失的关键产物 : {len(missing)} 个" + ("" if not missing else f" -> {missing}"))
say(f"  本地未推送的提交   : {ahead} 个")
say(f"  工作区未提交改动   : {len(dirty.splitlines())} 个")
say(f"  被 ignore 的路径   : {len(ign)} 个（这些不是「没推」，是「不该进版本库」）")

report = "\n".join(lines)
print(report)
with open(
    lp(r"D:\MallX\backend\loadtest\day16-github-audit-report.txt"), "w", encoding="utf-8"
) as f:
    f.write(report + "\n")
