# -*- coding: utf-8 -*-
"""Day 18 链路 E -- 管理端分类写（新增 / 改 / 删 + 三重引用校验）。

本日【唯一真正要想的部分】都在这条链路里，核心命题四句：

  1. 两级约束：新建三级分类被拒（400，不是 500）；
  2. 局部更新语义：parentId 传 null = 「不动」，不是「改为顶级」；
  3. ★★ 删分类的三重校验：有子分类 → 拒 / 有商品 → 拒 / 才真删；
  4. ★★★ 「商品已软删」照样不能被删分类 ——
        Product 上的 @TableLogic 会让 selectCount 自动补 is_deleted=0，
        漏掉软删商品 ⇒ 校验放行 ⇒ 物理删分类撞 fk_product_category ⇒ 500。
        所以 Service 必须用手写 XML 的 countByCategoryId（不带 is_deleted）。
        本脚本用「建分类 → 建商品 → 软删商品 → 删分类」把这条陷阱钉成断言。

★ 可重复执行：跑前记 categories / products 的全表 max(id) 作高水位；
  收尾按 id 物理删净（先子后父、先商品子表后主表），并断言逐字节回基线。

Usage:
    python day18-e-admin-category-write-verify.py
报告（utf-8）与脚本同目录：day18-e-admin-category-write-verify-report.txt
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
ADMIN_CAT = "/api/admin/categories"
ADMIN_PRD = "/api/admin/products"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day18-e-admin-category-write-verify-report.txt")

# ★ 夹具一律纯 ASCII
FX_TOP = "FX-CAT-TOP"
FX_SUB = "FX-CAT-SUB"
FX_LEAF = "FX-CAT-LEAF"
FX_LEAF2 = "FX-CAT-LEAF-RENAMED"
FX_LEAF3 = "FX-CAT-LEAF-RENAMED2"
FX_SOFT_CAT = "FX-CAT-SOFTDEL"
FX_SOFT_PRD = "FX-SOFTDEL-PRODUCT"
FX_SOFT_SKU = "FX-SOFTDEL-SKU"
HAS_PRODUCTS_CAT = 11      # 种子里挂了商品的二级分类
SEED_CATS = 7
SEED_ALIVE = 5

FULL_TOTAL = 40

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


def code_of(b):
    return b.get("code")


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


TABLES = ["products", "product_skus", "product_images", "categories", "brands"]


def counters():
    return {t: int(one("SELECT count(*) FROM %s" % t)) for t in TABLES}


def alive_products():
    return int(one("SELECT count(*) FROM products WHERE is_deleted=0"))


def seed_snapshot():
    return one("SELECT string_agg(id||':'||status||':'||name, ' ; ' ORDER BY id) "
               "FROM products WHERE id <= %d" % SEED_ALIVE)


def hw(table):
    return int(one("SELECT COALESCE(MAX(id),0) FROM %s" % table))


def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 18 链路 E -- 管理端分类写（两级约束 / 局部更新 / 删除三重校验）")
    say("target : %s%s" % (BASE, ADMIN_CAT))
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base = counters()
    base_seed = seed_snapshot()
    hw_cat = hw("categories")
    hw_prd = hw("products")
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base.items())))
    say("  高水位：categories=%d products=%d" % (hw_cat, hw_prd))
    chk("#1 基线：categories == %d" % SEED_CATS, base["categories"] == SEED_CATS,
        "实得 %d" % base["categories"])
    chk("#2 基线：products 活行 == %d" % SEED_ALIVE, alive_products() == SEED_ALIVE,
        "实得 %d" % alive_products())
    chk("#3 基线：分类 11 下确实有商品（#21『删有商品 → 拒』的前提）",
        int(one("SELECT count(*) FROM products WHERE category_id=%d" % HAS_PRODUCTS_CAT)) > 0,
        "商品数=%s" % one("SELECT count(*) FROM products WHERE category_id=%d" % HAS_PRODUCTS_CAT))

    def login(path, u, p):
        _, b, _ = japi("POST", path, body={"username": u, "password": p})
        return (b.get("data") or {}).get("token"), b.get("code")

    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_o_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    op_p_t, c3 = login("/api/auth/admin/login", "op_product", "prod123456")
    adm_t, c4 = login("/api/auth/admin/login", "admin", "admin123")
    for nm, tk, cd in (("demo", demo_t, c1), ("op_order", op_o_t, c2),
                       ("op_product", op_p_t, c3), ("admin", adm_t, c4)):
        say("  %-11s code=%s token_len=%d" % (nm, cd, len(tk or "")))
    chk("#4 四个身份全部登录成功", all([demo_t, op_o_t, op_p_t, adm_t]), "见上")

    # ---------------------------------------------------------- [1] 权限矩阵
    say("\n[1] 权限矩阵（★ 合法载荷，否则测到的是 @Valid 不是 @PreAuthorize）")
    st, raw = api("POST", ADMIN_CAT, body={"name": "x"})
    chk("#5 匿名新增被拒：真 HTTP 401", st == 401, "http=%s" % st)
    st, b, raw = japi("POST", ADMIN_CAT, demo_t, {"name": "x"})
    say("  demo     POST -> http=%s code=%s" % (st, code_of(b)))
    chk("#6 C 端 token（无 perms）→ 403", st == 403, "http=%s" % st)
    st, b, raw = japi("POST", ADMIN_CAT, op_o_t, {"name": "x"})
    say("  op_order POST -> http=%s code=%s" % (st, code_of(b)))
    chk("#7 op_order（只有 order:*）→ 403", st == 403, "http=%s" % st)
    st, b, raw = japi("DELETE", "%s/1" % ADMIN_CAT, op_o_t)
    chk("#8 op_order 删分类 → 403（且分类 1 仍在，未真删）",
        st == 403 and int(one("SELECT count(*) FROM categories WHERE id=1")) == 1,
        "http=%s id1=%s" % (st, one("SELECT count(*) FROM categories WHERE id=1")))

    # ---------------------------------------------------------- [2] 新增
    say("\n[2] 新增：两级约束")
    st, b, raw = japi("POST", ADMIN_CAT, op_p_t, {"name": FX_TOP, "sortOrder": 9})
    say("  op_product POST %s -> http=%s %s" % (FX_TOP, st, short(raw, 120)))
    top_id = b.get("data")
    chk("#9 ★ op_product 新增顶级成功（有 category:create）→ code=200 且返回 id",
        code_of(b) == 200 and isinstance(top_id, int), "code=%s data=%s" % (code_of(b), top_id))
    if isinstance(top_id, int):
        row = one("SELECT COALESCE(parent_id::text,'NULL')||'|'||name||'|'||sort_order::text "
                  "FROM categories WHERE id=%d" % top_id)
        say("  DB 新行 parent|name|sort = %s" % row)
        chk("#10 DB：顶级分类 parent_id IS NULL、name/sort_order 与提交一致",
            row == "NULL|%s|9" % FX_TOP, "实得 %s" % row)
    st, b, raw = japi("POST", ADMIN_CAT, op_p_t, {"parentId": top_id, "name": FX_SUB})
    sub_id = b.get("data")
    chk("#11 新增二级成功 → code=200",
        code_of(b) == 200 and isinstance(sub_id, int), "code=%s data=%s" % (code_of(b), sub_id))
    if isinstance(sub_id, int):
        chk("#12 DB：二级分类 parent_id == %s" % top_id,
            one("SELECT parent_id FROM categories WHERE id=%d" % sub_id) == str(top_id),
            "实得 %s" % one("SELECT parent_id FROM categories WHERE id=%d" % sub_id))
    st, b, raw = japi("POST", ADMIN_CAT, adm_t, {"parentId": sub_id, "name": "FX-CAT-LEVEL3"})
    say("  三级尝试 -> http=%s code=%s %s" % (st, code_of(b), short(raw, 120)))
    chk("#13 ★ 三级分类被拒：code=400（业务拒绝，不是 500 系统异常）",
        code_of(b) == 400, "code=%s" % code_of(b))
    chk("#14 DB：三级分类没有落库",
        int(one("SELECT count(*) FROM categories WHERE name='FX-CAT-LEVEL3'")) == 0, "见上")
    st, b, raw = japi("POST", ADMIN_CAT, adm_t, {"parentId": 99999999, "name": "FX-ORPHAN"})
    say("  父不存在 -> http=%s code=%s" % (st, code_of(b)))
    chk("#15 父分类不存在 → code=404", code_of(b) == 404, "code=%s" % code_of(b))
    st, b, raw = japi("POST", ADMIN_CAT, adm_t, {"name": ""})
    chk("#16 name 空串 → code=400（@NotBlank 在 @Valid 层拦住）",
        code_of(b) == 400, "code=%s" % code_of(b))

    # ---------------------------------------------------------- [3] 改
    say("\n[3] 改：局部更新语义")
    # 再造一个干净的二级叶子，专门留给后面的「删除成功」用例
    st, b, raw = japi("POST", ADMIN_CAT, adm_t, {"parentId": top_id, "name": FX_LEAF})
    leaf_id = b.get("data")
    chk("#17 造一个干净的二级叶子（后面 #29 用它测『删除成功』）",
        code_of(b) == 200 and isinstance(leaf_id, int), "code=%s" % code_of(b))
    if isinstance(leaf_id, int):
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_CAT, leaf_id), adm_t, {"name": FX_LEAF2})
        chk("#18 改名成功 code=200", code_of(b) == 200, "code=%s" % code_of(b))
        chk("#19 DB：name 已改为 %s" % FX_LEAF2,
            one("SELECT name FROM categories WHERE id=%d" % leaf_id) == FX_LEAF2,
            "实得 %s" % one("SELECT name FROM categories WHERE id=%d" % leaf_id))
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_CAT, leaf_id), adm_t, {"name": FX_LEAF3})
        chk("#20 ★ parentId 不传（null）= 不动：DB parent_id 仍是 %s" % top_id,
            one("SELECT parent_id FROM categories WHERE id=%d" % leaf_id) == str(top_id),
            "实得 %s" % one("SELECT parent_id FROM categories WHERE id=%d" % leaf_id))
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_CAT, leaf_id), adm_t, {"name": ""})
        chk("#21 传空串 name → code=400（Service 显式挡，@NotBlank 管不了这个）",
            code_of(b) == 400, "code=%s" % code_of(b))
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_CAT, leaf_id), adm_t, {"parentId": leaf_id})
        chk("#22 ★ 把自己设为父分类 → code=400", code_of(b) == 400, "code=%s" % code_of(b))
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_CAT, top_id), adm_t, {"parentId": 1})
        chk("#23 ★ 有子分类的分类不能移动 → code=400", code_of(b) == 400, "code=%s" % code_of(b))
        st, b, raw = japi("PUT", "%s/99999999" % ADMIN_CAT, adm_t, {"name": "x"})
        chk("#24 改不存在的分类 → code=404", code_of(b) == 404, "code=%s" % code_of(b))

    # ---------------------------------------------------------- [4] 删
    say("\n[4] 删：三重校验")
    st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_CAT, top_id), adm_t)
    say("  删有子分类 (%s) -> http=%s code=%s" % (top_id, st, code_of(b)))
    chk("#25 ★ 有子分类 → code=400（不是 500/外键错误）", code_of(b) == 400,
        "code=%s" % code_of(b))
    st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_CAT, HAS_PRODUCTS_CAT), adm_t)
    say("  删有商品 (%s) -> http=%s code=%s" % (HAS_PRODUCTS_CAT, st, code_of(b)))
    chk("#26 ★ 有商品 → code=400", code_of(b) == 400, "code=%s" % code_of(b))
    chk("#27 DB：分类 %d 仍在（拒绝不是假装的）" % HAS_PRODUCTS_CAT,
        int(one("SELECT count(*) FROM categories WHERE id=%d" % HAS_PRODUCTS_CAT)) == 1, "见上")

    # ★★ @TableLogic 陷阱：建分类 → 建商品 → 软删商品 → 删分类必须仍被拒
    say("\n[5] ★★ 商品已软删，分类照样不能删（@TableLogic 漏算陷阱）")
    st, b, raw = japi("POST", ADMIN_CAT, adm_t, {"name": FX_SOFT_CAT})
    soft_cat = b.get("data")
    chk("#28 建一个空分类 %s" % FX_SOFT_CAT,
        code_of(b) == 200 and isinstance(soft_cat, int), "code=%s" % code_of(b))
    soft_prd = None
    if isinstance(soft_cat, int):
        st, b, raw = japi("POST", ADMIN_PRD, adm_t,
                          {"categoryId": soft_cat, "name": FX_SOFT_PRD,
                           "skus": [{"skuCode": FX_SOFT_SKU, "price": 10.0}]})
        soft_prd = b.get("data")
        chk("#29 在该分类下建一个商品",
            code_of(b) == 200 and isinstance(soft_prd, int), "code=%s" % code_of(b))
        if isinstance(soft_prd, int):
            st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_PRD, soft_prd), adm_t)
            chk("#30 软删这个商品（is_deleted=1，但外键仍在）",
                code_of(b) == 200 and
                one("SELECT is_deleted FROM products WHERE id=%d" % soft_prd) == "1",
                "code=%s is_deleted=%s" % (code_of(b),
                                           one("SELECT is_deleted FROM products WHERE id=%d" % soft_prd)))
            st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_CAT, soft_cat), adm_t)
            say("  删『挂着已软删商品』的分类 -> http=%s code=%s %s"
                % (st, code_of(b), short(raw, 120)))
            chk("#31 ★★★ 商品已软删也拒绝删分类 → code=400"
                "（若用 selectCount 会被 @TableLogic 补 is_deleted=0 而漏算 → 放行后撞外键 500）",
                code_of(b) == 400, "code=%s" % code_of(b))

    st, b, raw = japi("DELETE", "%s/99999999" % ADMIN_CAT, adm_t)
    chk("#32 删不存在的分类 → code=404", code_of(b) == 404, "code=%s" % code_of(b))
    if isinstance(leaf_id, int):
        st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_CAT, leaf_id), adm_t)
        chk("#33 无引用的分类 → 删除成功 code=200", code_of(b) == 200, "code=%s" % code_of(b))
        chk("#34 DB：该分类行数 == 0（物理删，categories 无 is_deleted 列）",
            int(one("SELECT count(*) FROM categories WHERE id=%d" % leaf_id)) == 0,
            "残留=%s" % one("SELECT count(*) FROM categories WHERE id=%d" % leaf_id))

    # ---------------------------------------------------------- [6] 清理
    say("\n[6] 清理夹具 + 回基线（先子后父 / 先商品子表后主表）")
    psql("DELETE FROM product_skus WHERE product_id > %d" % hw_prd)
    psql("DELETE FROM product_images WHERE product_id > %d" % hw_prd)
    psql("DELETE FROM products WHERE id > %d" % hw_prd)
    psql("DELETE FROM categories WHERE parent_id > %d" % hw_cat)
    psql("DELETE FROM categories WHERE id > %d" % hw_cat)
    left_c = int(one("SELECT count(*) FROM categories WHERE id > %d" % hw_cat))
    left_p = int(one("SELECT count(*) FROM products WHERE id > %d" % hw_prd))
    say("  高水位以上残留：categories=%d products=%d" % (left_c, left_p))
    chk("#35 高水位以上零残留（分类与商品）", left_c == 0 and left_p == 0,
        "cat=%d prd=%d" % (left_c, left_p))
    chk("#36 categories 回基线 %d" % SEED_CATS,
        int(one("SELECT count(*) FROM categories")) == SEED_CATS,
        "实得 %s" % one("SELECT count(*) FROM categories"))
    chk("#37 products 活行回基线 %d" % SEED_ALIVE, alive_products() == SEED_ALIVE,
        "实得 %d" % alive_products())
    now_seed = seed_snapshot()
    chk("#38 ★ 5 条种子商品逐字节不变", now_seed == base_seed,
        "before=%s\nafter =%s" % (base_seed, now_seed))
    end = counters()
    chk("#39 收尾计数与基线一致", all(end[k] == base[k] for k in base),
        "diff=%s" % {k: (base[k], end[k]) for k in base if base[k] != end[k]})
    tops = one("SELECT string_agg(id::text, ',' ORDER BY id) FROM categories WHERE parent_id IS NULL")
    subs = one("SELECT string_agg(id::text, ',' ORDER BY id) FROM categories WHERE parent_id IS NOT NULL")
    chk("#40 分类拓扑复原：顶级 1,2,3 ；二级 11,12,21,31",
        tops == "1,2,3" and subs == "11,12,21,31", "top=%s sub=%s" % (tops, subs))

    passed = sum(1 for _, g, _ in checks if g)
    say("\n" + "=" * 78)
    for nm, g, d in checks:
        say("%-4s %s%s" % ("PASS" if g else "FAIL", nm, ("   << " + d) if (d and not g) else ""))
    say("-" * 78)
    say("%d/%d passed" % (passed, len(checks)))
    say("★ 满额自校验：FULL_TOTAL = %d ；实得 %d ；%s"
        % (FULL_TOTAL, len(checks),
           "一致" if len(checks) == FULL_TOTAL else "★ 不一致 —— 有断言未被创建（分母缩水）"))
    say("VERDICT: %s" % ("ADMIN-CATEGORY-WRITE OK -- 两级约束成立、"
                         "parentId null=不动、删除三重校验含『已软删商品』"
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
