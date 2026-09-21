"""Day 16 · 「本地 vs GitHub」逐文件比对

只回答一个问题：**本地受版本控制的每一个文件，GitHub 上有没有？**
做法：取远端 HEAD 的完整树（blob 列表），与本地 `git ls-files` 求差集。
纯只读，不改远端、不改本地。
"""

import json
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOCAL = r"D:\MallX"
API = "https://api.github.com/repos/QIU-RONG/Mallx"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path):
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "mallx-audit"},
    )
    with opener.open(req, timeout=40) as r:
        return json.load(r)


def git(*args):
    # ★ 必须带 core.quotepath=false：否则 git 把中文路径转义成
    #   "docs/daily/Day-01-\351\241..." 这种形式，与 GitHub 的正常路径永远对不上，
    #   会把【所有中文名文件】误报成「本地有、远端没有」。（本脚本首跑就踩了这个坑）
    return subprocess.run(
        ["git", "-C", LOCAL, "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


lines = []
say = lines.append

head = api("/commits/main")["sha"]
tree = api(f"/git/trees/{head}?recursive=1")["tree"]
remote_blobs = {e["path"] for e in tree if e["type"] == "blob"}
remote_dirs = {e["path"] for e in tree if e["type"] == "tree"}

local_tracked = set(git("ls-files").splitlines())
local_ignored = {
    ln[3:] for ln in git("status", "--short", "--ignored").splitlines()
    if ln.startswith("!!")
}
local_untracked = {
    ln[3:] for ln in git("status", "--short").splitlines() if ln.startswith("??")
}

say("=" * 74)
say(f"远端 HEAD : {head[:7]}")
say(f"远端文件  : {len(remote_blobs)} 个 blob / {len(remote_dirs)} 个目录")
say(f"本地跟踪  : {len(local_tracked)} 个（git ls-files）")
say("=" * 74)

only_local = sorted(local_tracked - remote_blobs)
say("")
say(f"■ 本地有、GitHub 没有的【受版本控制】文件：{len(only_local)} 个")
if only_local:
    unpushed = set(git("diff", "--name-only", f"{head}..main").splitlines())
    for p in only_local:
        why = "在未推送的提交里" if p in unpushed else "★ 不在任何提交里（异常！）"
        say(f"    {p}    <- {why}")
else:
    say("    （无）")
say("")
say(f"■ 远端有、本地没有的文件：{len(remote_blobs - local_tracked)} 个")
for p in sorted(remote_blobs - local_tracked):
    say(f"    {p}")
say("")
say(f"■ 工作区未跟踪（还没 git add 的）：{len(local_untracked)} 个")
for p in sorted(local_untracked):
    say(f"    {p}")
say("")
say(f"■ 被 .gitignore 排除（因此永远不会上 GitHub）：{len(local_ignored)} 条")
for p in sorted(local_ignored):
    say(f"    {p}")

say("")
say("=" * 74)
say("docs/daily 下，本地与远端各自的文档")
say("=" * 74)
local_docs = sorted(
    p for p in local_tracked if p.startswith("docs/daily/") and p.endswith(".md")
)
remote_docs = sorted(
    p for p in remote_blobs if p.startswith("docs/daily/") and p.endswith(".md")
)
say(f"  本地 {len(local_docs)} 篇 / 远端 {len(remote_docs)} 篇")
for p in local_docs:
    say(f"    {'OK ' if p in remote_blobs else 'MISS'}  {p}")
for p in remote_docs:
    if p not in local_tracked:
        say(f"    远端独有  {p}")

report = "\n".join(lines)
print(report)
with open(
    r"D:\MallX\backend\loadtest\day16-github-diff-report.txt", "w", encoding="utf-8"
) as f:
    f.write(report + "\n")
