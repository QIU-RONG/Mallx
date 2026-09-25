# -*- coding: utf-8 -*-
"""Day 18 链路 C -- 管理端商品写 + C 端写接口迁移证据。

核心命题有三句：
  1. 「新增 → 改 → 上下架 → 软删」在 /api/admin/products 上全链路走得通；
  2. 事务边界成立：sku_code 撞库时【整体回滚】，库里不留半成品商品；
  3. ★ 迁移的正面证据是 405 —— C 端 /api/products 现在只剩 GET，
     任何人 POST/PUT/DELETE 都得到「路径还在、方法没了」。

★ 权限断言一律带【合法载荷】（Day 18 §6.4 实测：@Valid 跑在 @PreAuthorize 之前，
  非法请求会先撞 400，测到的就不是权限了）。

★ 可重复执行：跑前记全表 max(id) 作高水位；收尾按 id 物理删净夹具行
  （products 先删子表 skus/images 再删主表），并断言逐字节回基线。

★ 满额自校验：FULL_TOTAL 是写死的常量，不是 len(checks)。

Usage:
    python day18-c-admin-product-write-verify.py
报告（utf-8）与脚本同目录：day18-c-admin-product-write-verify-report.txt
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
ADMIN = "/api/admin/products"
CEND = "/api/products"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day18-c-admin-product-write-verify-report.txt")

# ★ 夹具一律纯 ASCII（本机 PS 管道会吃 CJK 字节）
FX_NAME = "FX-WRITE-PRODUCT"
FX_NAME2 = "FX-WRITE-PRODUCT-RENAMED"
FX_SKU_A = "FX-SKU-A"
FX_SKU_B = "FX-SKU-B"
FX_CATEGORY = 11          # 二级分类「智能手机」
FX_BRAND = 1              # Apple
SEED_ALIVE = 5

FULL_TOTAL = 42

_lines = []


def say(s=""):
    _lines.append(s)


def flush():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


# ---------------------------------------------------------------- http helper
def api(method, path, token=None, body=None, timeout=60):
    """★ 显式禁用代理：会话注入的 HTTP_PROXY 会把 127.0.0.1 也拦下（502 os error 10061）。"""
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


def short(raw, n=190):
    raw = raw.replace("\r", "").replace("\n", " ").strip()
    return raw if len(raw) <= n else raw[:n] + " ...(truncated)"


# ---------------------------------------------------------------- db helpers
def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip(), p.returncode


def one(sql):
    """单值。⚠️ docker exec 回传行尾带 \\r —— 不 strip 会让比对恒为假。"""
    return psql(sql)[0].strip()


def col(sql):
    """单列多行 → [str]。"""
    out = psql(sql)[0]
    return [l.strip() for l in out.splitlines() if l.strip()]


TABLES = ["products", "product_skus", "product_images", "categories", "brands",
          "orders", "order_items", "payments", "cart_items", "inventory_logs"]


def counters():
    return {t: int(one("SELECT count(*) FROM %s" % t)) for t in TABLES}


def alive_products():
    return int(one("SELECT count(*) FROM products WHERE is_deleted=0"))


def seed_snapshot():
    return one("SELECT string_agg(id||':'||status||':'||name, ' ; ' ORDER BY id) "
               "FROM products WHERE id <= %d" % SEED_ALIVE)


def hw():
    return int(one("SELECT COALESCE(MAX(id),0) FROM products"))


def new_body(sku_codes, name=FX_NAME, status=None):
    b = {"categoryId": FX_CATEGORY, "brandId": FX_BRAND, "name": name,
         "subtitle": "fx-sub", "mainImage": "/img/fx.png",
         "images": ["/img/fx-1.png", "/img/fx-2.png"],
         "skus": [{"skuCode": c, "name": "fx-sku", "price": 99.5,
                   "attributes": {"color": "black"}} for c in sku_codes]}
    if status is not None:
        b["status"] = status
    return b


# ================================================================ main
def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 18 链路 C -- 管理端商品写（新增/改/上下架/软删）+ C 端写接口迁移证据")
    say("target : %s%s" % (BASE, ADMIN))
    say("accounts: demo(C端,无perms) / op_order(ORDER_ADMIN) / op_product(PRODUCT_ADMIN) / admin(超管)")
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base_counts = counters()
    base_alive = alive_products()
    base_seed = seed_snapshot()
    base_hw = hw()
    say("  products 活行=%d 全表=%d 高水位=%d" % (base_alive, base_counts["products"], base_hw))
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base_counts.items())))
    chk("#1 基线：products 活行 == %d" % SEED_ALIVE, base_alive == SEED_ALIVE,
        "实得 %d" % base_alive)
    chk("#2 基线：categories == 7", base_counts["categories"] == 7,
        "实得 %d" % base_counts["categories"])
    chk("#3 基线：种子 5 条商品全部 is_deleted=0（无历史脏行干扰本次计数）",
        int(one("SELECT count(*) FROM products WHERE id<=%d AND is_deleted<>0" % SEED_ALIVE)) == 0,
        "软删种子=%s" % one("SELECT count(*) FROM products WHERE id<=%d AND is_deleted<>0" % SEED_ALIVE))

    # ---------------------------------------------------------- [1] login
    say("\n[1] 登录四个身份")

    def login(path, u, p):
        st_, b_, _ = japi("POST", path, body={"username": u, "password": p})
        return (b_.get("data") or {}).get("token"), b_.get("code")

    demo_t, c1 = login("/api/auth/login", "demo", "demo123")
    op_o_t, c2 = login("/api/auth/admin/login", "op_order", "op123456")
    op_p_t, c3 = login("/api/auth/admin/login", "op_product", "prod123456")
    adm_t, c4 = login("/api/auth/admin/login", "admin", "admin123")
    for nm, tk, cd in (("demo", demo_t, c1), ("op_order", op_o_t, c2),
                       ("op_product", op_p_t, c3), ("admin", adm_t, c4)):
        say("  %-11s code=%s token_len=%d" % (nm, cd, len(tk or "")))
    chk("#4 四个身份全部登录成功", all([demo_t, op_o_t, op_p_t, adm_t]),
        "op_product 缺失请先跑 day17-fixture-apply.py")

    # ---------------------------------------------------------- [2] 权限矩阵
    say("\n[2] 权限矩阵（写端点 · ★ 一律带合法载荷，否则测到的是 @Valid 不是权限）")
    st, raw = api("POST", ADMIN, body=new_body([FX_SKU_A]))
    say("  匿名   POST %s -> http=%s %s" % (ADMIN, st, short(raw, 90)))
    chk("#5 匿名新增被拒：真 HTTP 401", st == 401, "http=%s" % st)

    st, b, raw = japi("POST", ADMIN, demo_t, new_body([FX_SKU_A]))
    say("  demo   POST %s -> http=%s code=%s" % (ADMIN, st, code_of(b)))
    chk("#6 ★ C 端 token（无 perms）新增 → 403（不是 400 —— 载荷合法，拦在 @PreAuthorize）",
        st == 403, "http=%s" % st)

    st, b, raw = japi("POST", ADMIN, op_o_t, new_body([FX_SKU_A]))
    say("  op_ord POST %s -> http=%s code=%s" % (ADMIN, st, code_of(b)))
    chk("#7 ★ op_order（只有 order:*）新增 → 403", st == 403, "http=%s" % st)

    st, raw = api("PUT", "%s/1" % ADMIN, body={"name": "x"})
    chk("#8 匿名改被拒：真 HTTP 401", st == 401, "http=%s" % st)
    st, b, raw = japi("DELETE", "%s/1" % ADMIN, op_o_t)
    chk("#9 op_order 删除 → 403（★ 没真删掉商品 1，见 #41 基线复核）", st == 403, "http=%s" % st)
    st, raw = api("DELETE", "%s/1" % ADMIN)
    chk("#10 匿名删除被拒：真 HTTP 401", st == 401, "http=%s" % st)

    # ---------------------------------------------------------- [3] 新增
    say("\n[3] 新增（op_product —— 有 product:create，反向对照 op_order 的 403）")
    st, b, raw = japi("POST", ADMIN, op_p_t, new_body([FX_SKU_A, FX_SKU_B]))
    say("  op_pro POST %s -> http=%s code=%s %s" % (ADMIN, st, code_of(b), short(raw, 120)))
    new_id = b.get("data")
    chk("#11 ★ op_product 新增成功：code=200 且返回新 id", code_of(b) == 200 and isinstance(new_id, int),
        "code=%s data=%s" % (code_of(b), new_id))
    chk("#12 DB：products 活行 +1", alive_products() == base_alive + 1,
        "实得 %d 期望 %d" % (alive_products(), base_alive + 1))

    if isinstance(new_id, int):
        row = one("SELECT p.category_id::text||'|'||COALESCE(p.brand_id::text,'NULL')||'|'||"
                  "p.name||'|'||p.status::text FROM products p WHERE p.id=%d" % new_id)
        say("  DB 新行: category|brand|name|status = %s" % row)
        chk("#13 DB：新行字段与提交一致（category=11 / brand=1 / name=%s / status=1）" % FX_NAME,
            row == "11|1|%s|1" % FX_NAME, "实得 %s" % row)
        skus = col("SELECT sku_code FROM product_skus WHERE product_id=%d ORDER BY id" % new_id)
        chk("#14 DB：2 个 SKU 已落库且编码正确", skus == [FX_SKU_A, FX_SKU_B], "实得 %s" % skus)
        imgs = col("SELECT image_url||'@'||sort_order::text FROM product_images "
                   "WHERE product_id=%d ORDER BY sort_order" % new_id)
        chk("#15 DB：2 张图已落库且 sort_order = 数组下标 0,1",
            imgs == ["/img/fx-1.png@0", "/img/fx-2.png@1"], "实得 %s" % imgs)
        st2, d, raw2 = japi("GET", "%s/%d" % (ADMIN, new_id), adm_t)
        say("  详情 skus=%s images=%s" % (len(d.get("data", {}).get("skus") or []),
                                          len(d.get("data", {}).get("images") or [])))
        chk("#16 详情回读：skus=2 且 images=2（三张表同一事务都已提交）",
            len(d.get("data", {}).get("skus") or []) == 2 and
            len(d.get("data", {}).get("images") or []) == 2, short(raw2, 100))

    # ---------------------------------------------------------- [4] 撞库回滚
    say("\n[4] ★ sku_code 撞库 → 整体回滚（不留半成品商品）")
    before_alive = alive_products()
    before_max = hw()
    st, b, raw = japi("POST", ADMIN, adm_t, new_body([FX_SKU_A], name="FX-DUP-SHOULD-ROLLBACK"))
    say("  admin  POST（撞 %s）-> http=%s code=%s %s" % (FX_SKU_A, st, code_of(b), short(raw, 120)))
    chk("#17 撞库被拒：code != 200", code_of(b) != 200, "code=%s" % code_of(b))
    chk("#18 ★ DB：活行数未变（主表那行也被回滚了，不是『有商品无 SKU』的半成品）",
        alive_products() == before_alive, "实得 %d 期望 %d" % (alive_products(), before_alive))
    chk("#19 ★ DB：不存在 name='FX-DUP-SHOULD-ROLLBACK' 的残留行",
        int(one("SELECT count(*) FROM products WHERE name='FX-DUP-SHOULD-ROLLBACK'")) == 0,
        "残留=%s" % one("SELECT count(*) FROM products WHERE name='FX-DUP-SHOULD-ROLLBACK'"))
    chk("#20 DB：sku_code=%s 全库只有 1 行（没有半插入的重复）" % FX_SKU_A,
        int(one("SELECT count(*) FROM product_skus WHERE sku_code='%s'" % FX_SKU_A)) == 1,
        "实得 %s" % one("SELECT count(*) FROM product_skus WHERE sku_code='%s'" % FX_SKU_A))

    # ---------------------------------------------------------- [5] 改 + 下架
    say("\n[5] 改 + 下架（PUT —— 不单独开上下架端点）")
    if isinstance(new_id, int):
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN, new_id), adm_t,
                          {"name": FX_NAME2, "status": 0})
        say("  admin  PUT %s/%d -> http=%s code=%s" % (ADMIN, new_id, st, code_of(b)))
        chk("#21 修改成功 code=200", code_of(b) == 200, "code=%s" % code_of(b))
        nm = one("SELECT name FROM products WHERE id=%d" % new_id)
        stt = one("SELECT status FROM products WHERE id=%d" % new_id)
        chk("#22 DB：name 已改为 %s" % FX_NAME2, nm == FX_NAME2, "实得 %s" % nm)
        chk("#23 DB：status == 0（下架）", stt == "0", "实得 %s" % stt)
        _, lc, _ = japi("GET", "%s?current=1&size=10" % CEND)
        _, la, _ = japi("GET", "%s?current=1&size=10" % ADMIN, adm_t)
        t_c = ((lc.get("data") or {}).get("total"))
        t_a = ((la.get("data") or {}).get("total"))
        say("  C端 total=%s  管理端 total=%s" % (t_c, t_a))
        chk("#24 ★ 下架商品：C 端列表看不到（total=%d），管理端看得到（total=%d）"
            % (SEED_ALIVE, SEED_ALIVE + 1), t_c == SEED_ALIVE and t_a == SEED_ALIVE + 1,
            "C=%s A=%s" % (t_c, t_a))
        st2, d2, _ = japi("GET", "%s/%d" % (ADMIN, new_id), adm_t)
        chk("#25 管理端详情仍可读到下架商品（不判 status）",
            code_of(d2) == 200 and (d2.get("data") or {}).get("status") == 0,
            "code=%s" % code_of(d2))
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN, new_id), adm_t, {"status": 1})
        chk("#26 重新上架：code=200 且 DB status 回 1",
            code_of(b) == 200 and one("SELECT status FROM products WHERE id=%d" % new_id) == "1",
            "code=%s status=%s" % (code_of(b), one("SELECT status FROM products WHERE id=%d" % new_id)))

    # ---------------------------------------------------------- [6] 软删
    say("\n[6] 软删（DELETE —— @TableLogic 改写为 UPDATE is_deleted=1）")
    if isinstance(new_id, int):
        sku_before = col("SELECT id::text||':'||COALESCE(is_deleted::text,'NULL') FROM product_skus "
                         "WHERE product_id=%d ORDER BY id" % new_id)
        st, b, raw = japi("DELETE", "%s/%d" % (ADMIN, new_id), adm_t)
        say("  admin  DELETE %s/%d -> http=%s code=%s" % (ADMIN, new_id, st, code_of(b)))
        chk("#27 删除成功 code=200", code_of(b) == 200, "code=%s" % code_of(b))
        chk("#28 DB：products.is_deleted == 1（软删，不是物理删）",
            one("SELECT is_deleted FROM products WHERE id=%d" % new_id) == "1",
            "实得 %s" % one("SELECT is_deleted FROM products WHERE id=%d" % new_id))
        chk("#29 DB：活行数回落 %d" % SEED_ALIVE, alive_products() == SEED_ALIVE,
            "实得 %d" % alive_products())
        sku_after = col("SELECT id::text||':'||COALESCE(is_deleted::text,'NULL') FROM product_skus "
                        "WHERE product_id=%d ORDER BY id" % new_id)
        chk("#30 ★ DB：SKU 行原封不动（软删主表不碰子表）", sku_before == sku_after,
            "before=%s after=%s" % (sku_before, sku_after))
        _, la, _ = japi("GET", "%s?current=1&size=10" % ADMIN, adm_t)
        chk("#31 管理端分页不再列出（total 回 %d）" % SEED_ALIVE,
            ((la.get("data") or {}).get("total")) == SEED_ALIVE,
            "total=%s" % ((la.get("data") or {}).get("total")))

    # ---------------------------------------------------------- [7] 迁移证据
    say("\n[7] ★★ C 端写接口迁移证据 —— 405 = 「路径还在、方法没了」")
    st, raw = api("POST", CEND, body={"categoryId": 1, "name": "x"})
    say("  匿名   POST %s -> http=%s" % (CEND, st))
    chk("#32 匿名 POST /api/products → 401（白名单只放 GET）", st == 401, "http=%s" % st)
    st, raw = api("POST", CEND, demo_t, {"categoryId": 1, "name": "x"})
    say("  demo   POST %s -> http=%s" % (CEND, st))
    chk("#33 ★ C 端 token POST /api/products → 405", st == 405, "http=%s" % st)
    st, raw = api("POST", CEND, adm_t, {"categoryId": 1, "name": "x"})
    say("  admin  POST %s -> http=%s" % (CEND, st))
    chk("#34 ★ 超管 POST /api/products → 405（写能力已迁走，管理员也不能走老路）",
        st == 405, "http=%s" % st)
    st, raw = api("PUT", "%s/1" % CEND, adm_t, {"name": "x"})
    say("  admin  PUT  %s/1 -> http=%s" % (CEND, st))
    chk("#35 超管 PUT /api/products/1 → 405", st == 405, "http=%s" % st)
    st, raw = api("DELETE", "%s/1" % CEND, adm_t)
    say("  admin  DEL  %s/1 -> http=%s" % (CEND, st))
    chk("#36 超管 DELETE /api/products/1 → 405", st == 405, "http=%s" % st)
    st, raw = api("GET", "%s?current=1&size=10" % CEND)
    chk("#37 ★ 红线：匿名 GET /api/products 仍 200（白名单没被误伤）", st == 200, "http=%s" % st)
    st, raw = api("GET", "%s?current=1&size=10" % CEND, demo_t)
    chk("#38 登录用户 GET /api/products 仍 200", st == 200, "http=%s" % st)

    # ---------------------------------------------------------- [8] 清理
    say("\n[8] 清理夹具（物理删，按高水位 %d）+ 回基线" % base_hw)
    if isinstance(new_id, int):
        psql("DELETE FROM product_skus WHERE product_id > %d" % base_hw)
        psql("DELETE FROM product_images WHERE product_id > %d" % base_hw)
        psql("DELETE FROM products WHERE id > %d" % base_hw)
    left = int(one("SELECT count(*) FROM products WHERE id > %d" % base_hw))
    say("  高水位以上残留 products=%d ；活行=%d" % (left, alive_products()))
    chk("#39 高水位以上零残留", left == 0, "残留 %d" % left)
    chk("#40 活行数回基线 %d" % SEED_ALIVE, alive_products() == SEED_ALIVE,
        "实得 %d" % alive_products())
    now_seed = seed_snapshot()
    chk("#41 ★ 5 条种子商品逐字节不变", now_seed == base_seed,
        "before=%s\nafter =%s" % (base_seed, now_seed))
    end_counts = counters()
    same = all(end_counts[t] == base_counts[t]
               for t in ("products", "product_skus", "product_images", "categories", "brands"))
    chk("#42 收尾计数与基线一致（products/skus/images/categories/brands）", same,
        "diff=%s" % {t: (base_counts[t], end_counts[t]) for t in base_counts
                     if base_counts[t] != end_counts[t]})

    # ---------------------------------------------------------- verdict
    passed = sum(1 for _, g, _ in checks if g)
    say("\n" + "=" * 78)
    for nm, g, d in checks:
        say("%-4s %s%s" % ("PASS" if g else "FAIL", nm, ("   << " + d) if (d and not g) else ""))
    say("-" * 78)
    say("%d/%d passed" % (passed, len(checks)))
    say("★ 满额自校验：FULL_TOTAL = %d ；实得 %d ；%s"
        % (FULL_TOTAL, len(checks),
           "一致" if len(checks) == FULL_TOTAL else "★ 不一致 —— 有断言未被创建（分母缩水）"))
    say("VERDICT: %s" % ("ADMIN-PRODUCT-WRITE + MIGRATION OK"
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
