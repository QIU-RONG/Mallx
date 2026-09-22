# -*- coding: utf-8 -*-
"""清理 Day 18 骨架冒烟【意外写入】的商品（probe-tmp / smoke-tmp）。

【为什么会有这个脚本 —— 一次真实的事故记录】
day18-skeleton-smoke.py 的「迁移探测」栏最初用【合法 body】+ admin token 去打
    POST /api/products
设计意图是「探一探 C 端写接口还在不在」。但那个接口在 Day 09-11 就已经是
【完整实现】，管理员又确实带着 product:create 权限 —— 于是它真的插进了一行商品。

★ 教训（值得记进方法论）：
    探测一个「可能仍然活着」的写接口，绝不能用合法载荷。
    正确做法是让它【死在更早的一层】—— 用缺必填字段的 body：
      迁移前：过认证 + 过权限 + @Valid 失败 → 400（零写入）
      迁移后：方法映射不存在 → 405
    两者依旧可区分（400 vs 405），但都不会写库。

【本脚本的三步】
  1. 列出名字匹配的商品（含已软删）
  2. 检查子行（skus / images / cart_items）—— 有子行就拒绝删，先人工看
  3. 无子行才物理删（products 上的外键是 NO ACTION：
     谁引用我决定我能否物理删，空表跑得通不等于逻辑对）
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
DB_NAME = "mallx"

NAME_PATTERNS = ("probe-tmp", "smoke-tmp")

lines = []
say = lines.append


def psql(sql_text):
    args = [DOCKER, "exec", "-i",
            "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
            "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def q(sql):
    rc, out, err = psql(sql)
    if rc != 0:
        say("❌ SQL 失败 rc=%d err=%s" % (rc, err[:300]))
        raise SystemExit(1)
    return [ln for ln in out.splitlines() if ln.strip()]


where = " OR ".join("name LIKE '%s%%'" % p for p in NAME_PATTERNS)

say("=" * 74)
say("Day 18 冒烟残留清理 —— 名字匹配 %s" % ", ".join(NAME_PATTERNS))
say("=" * 74)

say("[1] 待清理的商品（含已软删）")
rows = q("SELECT id || ' | ' || name || ' | category_id=' || category_id "
         "|| ' | is_deleted=' || is_deleted FROM products WHERE %s ORDER BY id;" % where)
if not rows:
    say("      （无匹配 —— 已经清过了）")
else:
    for r in rows:
        say("      %s" % r)

ids = [r.split("|")[0].strip() for r in rows]

if ids:
    id_list = ",".join(ids)
    say("")
    say("[2] 子行检查（有引用就不许物理删）")
    blockers = False
    for tbl, col in (("product_skus", "product_id"),
                     ("product_images", "product_id"),
                     ("cart_items", "sku_id"),
                     ("reviews", "product_id")):
        if tbl == "cart_items":
            cnt = q("SELECT count(*) FROM cart_items c JOIN product_skus s ON s.id = c.sku_id "
                    "WHERE s.product_id IN (%s);" % id_list)
        else:
            cnt = q("SELECT count(*) FROM %s WHERE %s IN (%s);" % (tbl, col, id_list))
        n = int(cnt[0]) if cnt else -1
        flag = "✅ 0" if n == 0 else "⚠️ %d 行" % n
        if n != 0:
            blockers = True
        say("      %-16s %s" % (tbl, flag))

    say("")
    if blockers:
        say("[3] ❌ 发现引用，拒绝删除 —— 请先人工确认这些子行的来历")
    else:
        say("[3] 无任何引用，执行物理删")
        rc, out, err = psql("DELETE FROM products WHERE id IN (%s);" % id_list)
        say("      DELETE rc=%d %s" % (rc, out.replace("\n", " ")))
        left = q("SELECT count(*) FROM products WHERE %s;" % where)
        n_left = int(left[0]) if left else -1
        say("      残留复查：%d 行 %s" % (n_left, "✅" if n_left == 0 else "❌"))

say("")
say("[4] 顺带核对：种子 5 个商品是否安好（id 1..5 应全部存在）")
alive = q("SELECT id || ' | ' || name || ' | is_deleted=' || is_deleted "
          "FROM products WHERE id BETWEEN 1 AND 5 ORDER BY id;")
for r in alive:
    say("      %s" % r)
say("      期望 5 行、is_deleted 全为 0")

report = "\n".join(lines)
print(report)
raise SystemExit(0)
