# -*- coding: utf-8 -*-
"""
Fix a garbled git commit message on Windows.

Why this exists
---------------
On this box, piping a UTF-8 commit message through PowerShell mangles it:
the CJK bytes never reach git, and the stored message becomes "????".
This script writes the message with Python (which controls its own encoding)
and hands it to `git commit -F`, so the bytes git reads are the bytes we wrote.

Usage:
    python git_commit_utf8.py <repo> <message-file> [--amend]
"""
import subprocess
import sys


def main():
    if len(sys.argv) < 3:
        print("usage: git_commit_utf8.py <repo> <message-file> [--amend]")
        return 2
    repo, msg_file = sys.argv[1], sys.argv[2]
    amend = "--amend" in sys.argv

    with open(msg_file, "r", encoding="utf-8") as fh:
        subject = fh.read().splitlines()[0]
    print("subject: %s" % subject)

    cmd = ["git", "-C", repo, "commit", "-F", msg_file, "--cleanup=whitespace"]
    if amend:
        cmd.append("--amend")

    env_patch = {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}
    import os
    env = dict(os.environ)
    env.update(env_patch)

    p = subprocess.run(cmd, capture_output=True, env=env)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    print("rc=%d" % p.returncode)
    if out:
        print(out)
    if err:
        print("stderr: %s" % err)

    # Read it back the same way, and decode explicitly -- this is the only
    # check that proves what is ACTUALLY stored, not what the terminal shows.
    v = subprocess.run(["git", "-C", repo, "log", "-1", "--pretty=format:%s"],
                       capture_output=True, env=env)
    stored = v.stdout.decode("utf-8", "replace").strip()
    print("stored : %s" % stored)
    print("MATCH  : %s" % ("YES" if stored == subject else "NO -- still garbled"))
    return 0 if stored == subject else 1


if __name__ == "__main__":
    raise SystemExit(main())
