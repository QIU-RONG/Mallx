# -*- coding: utf-8 -*-
"""Day 18 链路 D -- 管理端分类读（GET /api/admin/categories/tree）。

核心命题两句：
  1. 管理端树与 C 端树【同结构】（复用同一个 tree()），但守卫在权限码上；
  2. 权限矩阵有区分度：匿名 401 / C 端 token 403 / op_order 403（只有 order:*）
     / op_product 与超管 200 —— 且两者响应【逐字节相同】。

★ 只读链路：跑完 categories 行数必须不变（断言 #14）。

Usage:
    python day18-d-admin-category-read-verify.py
报告（utf-8）与脚本同目录：day18-d-admin-category-read-verify-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
ADMIN_TREE = "/api/admin/categories/tree"
CEND_TREE = "/api/categories/tree"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day18-d-admin-category-read-verify-report.txt")

SEED_CATS = 7
SEED_ALIVE = 5
FULL_TOTAL = 16

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


def api(method, path, token=None, body=None, timeout=60):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                                      # noqa: BLE001
        return -1, '{"transport_error": "%s"}' % repr(e)


def japi(method, path, token=None, body=None):
    st, raw = api(method, path, token, body)
    try:
        return st, json.loads(raw), raw
    except ValueError:
        return st, {"raw": raw}, raw


def short(raw, n=180):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip(), p.returncode


def one(sql):
    return psql(sql)[0].strip()


def col(sql):
    return [l.strip() for l in psql(sql)[0].splitlines() if l.strip()]


def counters():
    t = ["products", "product_skus", "product_images", "categories", "brands"]
    return {x: int(one("SELECT count(*) FROM %s" % x)) for x in t}


def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 18 链路 D -- 管理端分类读（树 + 权限矩阵）")
    say("target : %s%s" % (BASE, ADMIN_TREE))
    say("=" * 78)

    say("\n[0] BASELINE (psql)")
    base = counters()
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base.items())))
    chk("#1 基线：categories == %d" % SEED_CATS, base["categories"] == SEED_CATS,
        "实得 %d" % base["categories"])
    chk("#2 基线：products 活行 == %d" % SEED_ALIVE,
        int(one("SELECT count(*) FROM products WHERE is_deleted=0")) == SEED_ALIVE,
        "实得 %s" % one("SELECT count(*) FROM products WHERE is_deleted=0"))

    def login(path, u, p):
        _, b, _ = japi("POST", path, body={"username": u, "password": p})
        return (b.get("data") or {}).get("token"), b.get("code")

    say("\n[1] 登录 + 权限矩阵")
    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_o_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    op_p_t, c3 = login("/api/auth/admin/login", "op_product", "prod123456")
    adm_t, c4 = login("/api/auth/admin/login", "admin", "admin123")
    for nm, tk, cd in (("demo", demo_t, c1), ("op_order", op_o_t, c2),
                       ("op_product", op_p_t, c3), ("admin", adm_t, c4)):
        say("  %-11s code=%s token_len=%d" % (nm, cd, len(tk or "")))
    chk("#3 四个身份全部登录成功", all([demo_t, op_o_t, op_p_t, adm_t]), "见上")

    st, raw = api("GET", ADMIN_TREE)
    say("  匿名       -> http=%s %s" % (st, short(raw, 80)))
    chk("#4 匿名读树被拒：真 HTTP 401", st == 401, "http=%s" % st)
    st, _, raw = japi("GET", ADMIN_TREE, demo_t)
    say("  demo       -> http=%s %s" % (st, short(raw, 80)))
    chk("#5 C 端 token（无 perms）→ 403", st == 403, "http=%s" % st)
    st, _, raw = japi("GET", ADMIN_TREE, op_o_t)
    say("  op_order   -> http=%s %s" % (st, short(raw, 80)))
    chk("#6 ★ op_order（只有 order:*）→ 403（category:* 是新权限，没补发就永远 403）",
        st == 403, "http=%s" % st)
    st, bp, raw_p = japi("GET", ADMIN_TREE, op_p_t)
    st2, ba, raw_a = japi("GET", ADMIN_TREE, adm_t)
    say("  op_product -> http=%s ；admin -> http=%s" % (st, st2))
    chk("#7 op_product 与超管都 200", st == 200 and st2 == 200, "%s/%s" % (st, st2))
    chk("#8 ★ op_product 与超管的树【逐字节相同】（同一口径，无数据权限过滤）",
        raw_p == raw_a, "len %d vs %d" % (len(raw_p), len(raw_a)))

    say("\n[2] 树的结构（DB 对账）")
    data = (bp.get("data") or [])
    tops = [c.get("id") for c in data]
    say("  顶层 id = %s" % tops)
    db_tops = col("SELECT id::text FROM categories WHERE parent_id IS NULL ORDER BY sort_order, id")
    chk("#9 顶层 3 个且 id == 1,2,3（sort_order 升序）",
        [str(x) for x in tops] == ["1", "2", "3"] and db_tops == ["1", "2", "3"],
        "接口=%s DB=%s" % (tops, db_tops))
    children = {c.get("id"): sorted(x.get("id") for x in (c.get("children") or [])) for c in data}
    say("  children = %s" % children)
    chk("#10 二级挂载正确：1→[11,12] ；2→[21] ；3→[31]",
        children == {1: [11, 12], 2: [21], 3: [31]}, "实得 %s" % children)
    leaf_empty = all((x.get("children") or []) == []
                     for c in data for x in (c.get("children") or []))
    chk("#11 二级节点 children == []（两层封顶，不会无限嵌套）", leaf_empty, "见 #10")
    keys_ok = all(all(k in c for k in ("id", "name", "parentId", "sortOrder"))
                  for c in data)
    chk("#12 CategoryVO 字段完整（id/name/parentId/sortOrder 都在）", keys_ok,
        "样例=%s" % short(json.dumps(data[0], ensure_ascii=False), 150) if data else "空树")

    say("\n[3] 红线 + 只读性")
    st, raw_c = api("GET", CEND_TREE)
    chk("#13 ★ 红线：匿名 GET /api/categories/tree 仍 200（白名单没被误伤）", st == 200,
        "http=%s" % st)
    try:
        cend_tops = [c.get("id") for c in (json.loads(raw_c).get("data") or [])]
    except ValueError:
        cend_tops = None
    chk("#14 C 端树与管理端树结构一致（同 3 个顶层）",
        cend_tops == [1, 2, 3], "C端=%s" % cend_tops)

    end = counters()
    chk("#15 只读性：跑完 categories 仍 %d" % SEED_CATS, end["categories"] == SEED_CATS,
        "实得 %d" % end["categories"])
    chk("#16 只读性：products/skus/images/brands 计数全部不变",
        all(end[k] == base[k] for k in base),
        "diff=%s" % {k: (base[k], end[k]) for k in base if base[k] != end[k]})

    passed = sum(1 for _, g, _ in checks if g)
    say("\n" + "=" * 78)
    for nm, g, d in checks:
        say("%-4s %s%s" % ("PASS" if g else "FAIL", nm, ("   << " + d) if (d and not g) else ""))
    say("-" * 78)
    say("%d/%d passed" % (passed, len(checks)))
    say("★ 满额自校验：FULL_TOTAL = %d ；实得 %d ；%s"
        % (FULL_TOTAL, len(checks),
           "一致" if len(checks) == FULL_TOTAL else "★ 不一致 —— 有断言未被创建（分母缩水）"))
    say("VERDICT: %s" % ("ADMIN-CATEGORY-READ OK"
                         if (passed == len(checks) and len(checks) == FULL_TOTAL)
                         else "NOT CLEAN -- 见上面 FAIL 行"))
    flush()
    print("report -> %s   %d/%d passed (FULL_TOTAL=%d)" % (OUT, passed, len(checks), FULL_TOTAL))
    return 0 if (passed == len(checks) and len(checks) == FULL_TOTAL) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                                           # noqa: BLE001
        import traceback
        say("\nCRASH:\n" + traceback.format_exc())
        flush()
        raise
