# -*- coding: utf-8 -*-
"""Day 25 · SQL 补丁【严格模式】全量自检。

为什么需要它（这是本项目真实踩过的一次事故）：
  `docker-entrypoint-initdb.d` 是用 `psql -v ON_ERROR_STOP=1` 逐个执行 .sql 的
  ⇒ 任何一个文件报错，初始化当场停止，排在它【后面】的补丁全部【静默跳过】。
  实测事故：09 号补丁里有一段「故意撞唯一约束」的自检，在交互式 psql 下没问题，
  但在 initdb 里直接掐断了整个初始化 ⇒ 10/11/12/13/14 号补丁一个都没跑，
  容器里 permissions 只有 20 行（应 41）、品牌权限 39/40/41 缺失、
  `GET /api/admin/roles` 带超管 token 也 403。而 `docker compose ps` 全绿、app healthy。

  ⇒ 判据：**容器 healthy 只证明进程活着，不证明业务可用。**
  ⇒ 本脚本把「全新库 + 按序 + ON_ERROR_STOP=1」这件事搬到一次运行里，
     并且**逐文件**给出退出码，让「是哪一个文件把链掐断的」一眼可见。

做法：在运行中的 Postgres 容器里建一个【临时库】，把 01→14 按名字顺序灌进去，
      全程 `-v ON_ERROR_STOP=1`；结束后删库。★ 不碰开发库的任何数据。

运行：python day25-sql-strict-check.py
前置：容器 mallx-postgres 在运行（不要求应用在跑）。
"""
import glob
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
ADMIN_DB = "mallx"                 # 借它来 CREATE/DROP 临时库
PROBE_DB = "mallx_strict_probe"    # ★ 临时库，跑完就删
SQL_DIR = r"D:\MallX\backend\sql"
REPORT = r"D:\MallX\backend\loadtest\day25-sql-strict-check-report.txt"

# 14 份补丁的期望顺序（字典序恰好也是正确的执行序）
FILES = ["01-schema.sql", "02-index.sql", "03-data.sql", "04-review-constraints.sql",
         "05-admin-permissions.sql", "06-day17-fixtures.sql", "07-admin-permissions.sql",
         "08-marketing-permissions.sql", "09-user-coupons-unique.sql",
         "10-brand-permissions.sql", "11-order-discount.sql", "12-day22-permissions.sql",
         "13-day23-permissions.sql", "14-brand-crud-permissions.sql"]

# 满额护栏：文件清单被改动时立刻炸（防止「少跑一个文件却全绿」）
EXPECTED_FILES = 14
# 满额护栏：断言条数（防止「有检查项根本没被执行到」被当成通过）
EXPECTED_CHECKS = 16
# 跑完全部补丁后的硬事实（与 day24-perm-apply.py 的 EXPECT_PERM_TOTAL 同源）
EXPECT_PERM_TOTAL = 41

lines = []
say = lines.append
n_pass = n_fail = 0


def chk(name, ok, detail=""):
    global n_pass, n_fail
    if ok:
        n_pass += 1
        say("  [OK]   %s%s" % (name, ("   " + detail) if detail else ""))
    else:
        n_fail += 1
        say("  [FAIL] %s   %s" % (name, detail))
    return ok


def psql(db, sql_text, stop=True, timeout=180):
    """把 SQL 用 stdin 灌给 psql。★ 不走命令行：命令行会撞 PS 的 % 展开坑。"""
    args = [DOCKER, "exec", "-i",
            "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql",
            "-U", DB_USER, "-d", db]
    if stop:
        args += ["-v", "ON_ERROR_STOP=1"]
    args += ["-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def main():
    say("=" * 78)
    say("SQL 补丁严格模式全量自检（全新临时库 %s，ON_ERROR_STOP=1）" % PROBE_DB)
    say("=" * 78)

    files = [os.path.join(SQL_DIR, f) for f in FILES]
    missing = [f for f in files if not os.path.exists(f)]
    say("")
    say("[0] 文件清单：实得 %d 份，期望 %d 份" % (len(files), EXPECTED_FILES))
    chk("清单份数 == %d" % EXPECTED_FILES, len(files) == EXPECTED_FILES,
        "got=%d" % len(files))
    chk("清单里每个文件都存在", not missing, "missing=%s" % missing)
    if missing:
        return bail()

    # 磁盘上是否还有清单以外的 .sql（防止「新加的补丁忘了进清单」）
    on_disk = sorted(os.path.basename(p) for p in glob.glob(os.path.join(SQL_DIR, "*.sql")))
    extra = [f for f in on_disk if f not in FILES]
    chk("磁盘上没有清单外的 .sql", not extra, "extra=%s" % extra)

    # ---------- 1. 建临时库 ----------
    say("")
    say("[1] 建临时库（★ 会先 DROP 掉同名库，只动这一个名字）")
    rc, _out, err = psql(ADMIN_DB,
                         "DROP DATABASE IF EXISTS %s;\nCREATE DATABASE %s;" % (PROBE_DB, PROBE_DB))
    chk("CREATE DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:300]))
    if rc != 0:
        return bail()

    try:
        # ---------- 2. 按序灌补丁 ----------
        # ★★ 这里必须忠实模拟 initdb 的【熔断语义】：
        #    官方 entrypoint 是 `for f in /docker-entrypoint-initdb.d/*; do psql -v ON_ERROR_STOP=1 -f "$f"; done`，
        #    而整个 entrypoint 处在 `set -e` 之下 ⇒ 第一个非零退出码就让脚本结束，
        #    排在后面的文件【根本不会被执行】。
        #    ⚠️ 这一点是被本脚本的【控制组】逼出来的（2026-09-25）：第一版是「逐个独立调用、
        #    不中断」，结果拿仓库里的缺陷版 09 去跑时，10–14 全都显示 rc=0 ——
        #    连「permissions 只有 20 行」都没复现出来，等于没测到那个事故。
        #    ⇒ 不模拟熔断，就只是「14 个独立的语法检查」，而不是「initdb 会不会被掐断」。
        say("")
        say("[2] 按序执行（★ 忠实模拟 initdb：第一个 rc != 0 之后，其余文件【不会被执行】）")
        bad = []
        skipped = []
        notice_09 = False
        for name in FILES:
            if bad:
                skipped.append(name)
                say("      [SKIP] %-34s （initdb 里执行不到这里）" % name)
                continue
            path = os.path.join(SQL_DIR, name)
            body = open(path, encoding="utf-8").read()
            rc, out, err = psql(PROBE_DB, body)
            flag = "OK  " if rc == 0 else "FAIL"
            say("      [%s] %-34s rc=%d" % (flag, name, rc))
            if rc != 0:
                bad.append(name)
                say("             stderr: %s" % err.replace("\n", " | ")[:400])
            if "SELF-CHECK OK" in (err + out):
                notice_09 = True
        chk("14 个文件全部 rc == 0（没有任何文件把链掐断）", not bad, "bad=%s" % bad)
        chk("★ 没有被跳过的文件（initdb 语义：前面的失败会掐断后面全部）", not skipped,
            "会被跳过 %d 个：%s" % (len(skipped), skipped))

        say("")
        say("[3] ★ 09 号那段「期望抛错」的探针是否被内部消化（NOTICE 而不是 ERROR）")
        chk("09 输出了 NOTICE「SELF-CHECK OK」（异常在库内被接住）", notice_09,
            "★ 没看到该 NOTICE ⇒ 要么探针没执行，要么异常漏到了 psql 层")

        # ---------- 4. 跑完后的硬事实 ----------
        say("")
        say("[4] 跑完全部补丁后的硬事实（必须与 day24-perm-apply.py 的口径一致）")
        rc, out, err = psql(PROBE_DB, "SELECT count(*) FROM permissions")
        chk("permissions 行数 == %d" % EXPECT_PERM_TOTAL,
            rc == 0 and out == str(EXPECT_PERM_TOTAL), "got=%r" % out)

        rc, out, err = psql(PROBE_DB, "SELECT max(id) FROM permissions")
        chk("permissions max(id) == %d（显式 id 种子区间连续）"
            % EXPECT_PERM_TOTAL, rc == 0 and out == str(EXPECT_PERM_TOTAL), "got=%r" % out)

        rc, out, err = psql(PROBE_DB,
                            "SELECT count(*) FROM information_schema.columns "
                            "WHERE table_name='orders' AND column_name='discount_amount'")
        chk("DDL 补丁 11 号生效（orders.discount_amount 存在）", rc == 0 and out == "1",
            "got=%r" % out)

        rc, out, err = psql(PROBE_DB,
                            "SELECT count(*) FROM pg_constraint "
                            "WHERE conname='uk_user_coupons_user_coupon'")
        chk("DDL 补丁 09 号生效（uk_user_coupons_user_coupon 存在）",
            rc == 0 and out == "1", "got=%r" % out)

        rc, out, err = psql(PROBE_DB,
                            "SELECT count(*) FROM role_permissions rp "
                            "JOIN permissions p ON p.id = rp.permission_id "
                            "WHERE p.code LIKE 'brand:%' AND rp.role_id = 1")
        chk("最后一份补丁 14 号的授权也在（超管持有 4 条 brand:*）",
            rc == 0 and out == "4", "got=%r" % out)

        rc, out, err = psql(PROBE_DB,
                            "SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema='public'")
        n_tab = int(out) if rc == 0 and out.isdigit() else -1
        chk("核心表建齐（public schema 表数 >= 22）", n_tab >= 22, "tables=%s" % n_tab)

        # ---------- 5. 探针零痕迹 ----------
        say("")
        say("[5] ★ 探针是否留下痕迹（09 用 ROLLBACK 保证零痕迹）")
        rc, out, err = psql(PROBE_DB, "SELECT count(*) FROM coupons WHERE id = 999999")
        chk("临时券 id=999999 不存在（探针零痕迹）", rc == 0 and out == "0", "got=%r" % out)
        rc, out, err = psql(PROBE_DB, "SELECT count(*) FROM user_coupons")
        chk("user_coupons 为空（探针那两次 INSERT 已随 ROLLBACK 消失）",
            rc == 0 and out == "0", "got=%r" % out)

    finally:
        say("")
        say("[6] 删临时库")
        rc, _out, err = psql(ADMIN_DB, "DROP DATABASE IF EXISTS %s;" % PROBE_DB)
        chk("DROP DATABASE %s" % PROBE_DB, rc == 0, "rc=%d err=%s" % (rc, err[:200]))

    return bail()


def bail(code=None):
    total = n_pass + n_fail
    say("")
    say("=" * 78)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (n_pass, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条断言，期望 %d 条 ⇒ 有检查项根本没被执行到"
            % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 14 份补丁在全新库上按序跑通，initdb 不会被掐断" if ok
                         else "FAIL -- 见上面 FAIL 行"))
    say("=" * 78)
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("report -> %s" % REPORT)
    if code is None:
        code = 0 if ok else 1
    return code


if __name__ == "__main__":
    sys.exit(main())
