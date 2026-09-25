# -*- coding: utf-8 -*-
"""Day 24 验收 —— L5② 管理端品牌 CRUD（`/api/admin/brands` 的 create / update / delete）。

本日的核心命题四句，全部钉成断言：

  1. ★ 权限矩阵有【反向对照】：op_product（PRODUCT_ADMIN，有 brand:*）能写；
     op_order（ORDER_ADMIN）连 list 都 403 —— 只用全权 admin 测 = 什么都证明不了。
  2. ★★ 品牌 status 有【真实消费方】，所以两端口径必须分开断言：
     把品牌停用之后，【C 端 GET /api/brands 看不见它】＋【管理端 GET /api/admin/brands 看得见它】
     —— 这一【对】断言才是「status 真的生效」的完整证据。只断一侧：
       只断 C 端看不见 ⇒ 可能是接口坏了；只断管理端看得见 ⇒ 可能是它压根不过滤 status。
  3. ★★ 局部更新语义：PUT 只传 logo 时，name / status 一个字都不许动
     （这是 DTO 用「null = 不动」而非「null = 清空」换来的，必须实测）。
  4. ★★★ 删除前的引用校验必须【绕开 @TableLogic】：
     「建商品 → 挂到品牌 → 软删商品 → 删品牌」必须仍被拒（400）。
     用 productMapper.selectCount 会被自动追加 is_deleted=0 ⇒ 漏算已软删商品
     ⇒ 放行物理删 ⇒ 撞 fk_product_brand（NO ACTION）→ 现场 500。
     所以 Service 必须用手写 XML 的 countByBrandId（**不带** is_deleted）。
     这条与 Day 18 的 countByCategoryId 是【同一个缺陷的两个出口】。

★ 可重复执行：跑前记 brands / products / product_skus 的全表 max(id) 作高水位；
  收尾按 id 物理删净（先商品子表后主表），并断言四表计数与种子快照逐字节回基线。

★ 提示：本脚本需要先应用 backend/sql/14-brand-crud-permissions.sql
  （`python day24-perm-apply.py`），否则 **所有** 管理端品牌写调用都会 403（包括超管）。

Usage:
    python day24-brand-crud-verify.py
报告（utf-8）与脚本同目录：day24-brand-crud-verify-report.txt
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "day24-brand-crud-verify-report.txt")

ADMIN_BRAND = "/api/admin/brands"
ADMIN_PRD = "/api/admin/products"
C_BRAND = "/api/brands"

# ★ 夹具一律纯 ASCII（同 day18-e）
FX_BRAND_MAIN = "FX-BRAND-MAIN"        # 主夹具：被改名 / 停用 / 启用 / 最终删除
FX_BRAND_DEFAULT = "FX-BRAND-NOSTATUS"  # 不传 status ⇒ 走 DDL 默认 1
FX_BRAND_TRIM = "FX-BRAND-TRIMMED"      # 名字前后带空格，验证 trim
FX_BRAND_NEW_NAME = "FX-BRAND-RENAMED"  # 主夹具改名后的名字
# ★ 「别人」用【种子品牌】的名字，而不是再造一个 FX-* ——
#   第一版这里犯过一个错（已修）：我写了 FX-BRAND-DUP 这个名字，
#   但**从来没创建过这个品牌** ⇒ 「改成 FX-BRAND-DUP」其实是「改成一个新的、没人用的名字」，
#   返回 200 是【正确行为】，而断言却期望 400 ⇒ 假 FAIL。
#   ★ 同族判据（第 3 次现形）：**样本必须落在判据的取值域里**
#     —— 要测「重名」，那个名字就必须先真实存在。
#     种子里的 Apple 一定在（基线快照已断言 7 条）⇒ 用它最省事也最真实。
SEED_BRAND_NAME = "Apple"               # 种子品牌（id=1），用作「别人的名字」
FX_PRD = "FX-BRAND-PRODUCT"
FX_SKU = "FX-BRAND-SKU"
SEED_BRANDS = 7
SEED_PRODUCTS_ALIVE = 5
HAS_CATEGORY = 11                       # 种子里挂了商品的二级分类

FULL_TOTAL = 43

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
         CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True)
    return p.stdout.decode("utf-8", "replace").strip(), p.returncode


def one(sql):
    return psql(sql)[0].strip()


TABLES = ["brands", "products", "product_skus", "product_images"]


def counters():
    return {t: int(one("SELECT count(*) FROM %s" % t)) for t in TABLES}


def alive_products():
    return int(one("SELECT count(*) FROM products WHERE is_deleted=0"))


def seed_brand_snapshot():
    """种子 7 条品牌的 id / name / status 逐条快照（★ 收尾要比对）"""
    return one("SELECT COALESCE(string_agg(id||':'||name||':'||status, ' ; ' ORDER BY id), 'NONE') "
               "FROM brands WHERE id <= %d" % SEED_BRANDS)


def hw(table):
    return int(one("SELECT COALESCE(MAX(id),0) FROM %s" % table))


def c_brand_ids():
    """C 端品牌字典里出现的 id 集合（走真实接口，不信 DB）。"""
    st, b, raw = japi("GET", C_BRAND)
    if code_of(b) != 200:
        return None, st, short(raw, 120)
    return {r.get("id") for r in (b.get("data") or [])}, st, ""


def adm_brand_ids(token):
    """管理端品牌字典里出现的 id 集合。"""
    st, b, raw = japi("GET", ADMIN_BRAND, token)
    if code_of(b) != 200:
        return None, st, short(raw, 120)
    return {r.get("id") for r in (b.get("data") or [])}, st, ""


def main():
    checks = []

    def chk(name, good, detail=""):
        checks.append((name, bool(good), detail))

    say("=" * 78)
    say("Day 24 验收 -- L5② 管理端品牌 CRUD（%s）" % ADMIN_BRAND)
    say("target : %s%s" % (BASE, ADMIN_BRAND))
    say("=" * 78)

    # ---------------------------------------------------------- [0] baseline
    say("\n[0] BASELINE (psql)")
    base = counters()
    base_seed = seed_brand_snapshot()
    hw_brand = hw("brands")
    hw_prd = hw("products")
    say("  counters: %s" % ", ".join("%s=%d" % kv for kv in sorted(base.items())))
    say("  高水位：brands=%d products=%d" % (hw_brand, hw_prd))
    say("  种子品牌快照：%s" % base_seed)
    chk("#1 基线：brands == %d（03-data.sql 的 7 条种子）" % SEED_BRANDS,
        base["brands"] == SEED_BRANDS, "实得 %d" % base["brands"])
    chk("#2 基线：products 活行 == %d" % SEED_PRODUCTS_ALIVE,
        alive_products() == SEED_PRODUCTS_ALIVE, "实得 %d" % alive_products())
    chk("#3 基线：分类 %d 存在（建夹具商品的前提）" % HAS_CATEGORY,
        int(one("SELECT count(*) FROM categories WHERE id=%d" % HAS_CATEGORY)) == 1,
        "见上")

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
    say("")

    # ---------------------------------------------------------- [1] 权限矩阵
    say("[1] 权限矩阵（★ 全部用【合法载荷】，否则测到的是 @Valid 不是 @PreAuthorize）")
    st, raw = api("POST", ADMIN_BRAND, body={"name": FX_BRAND_MAIN})
    say("  匿名          POST -> http=%s" % st)
    chk("#4 匿名新增 → 真 HTTP 401", st == 401, "http=%s" % st)

    st, b, raw = japi("POST", ADMIN_BRAND, demo_t, {"name": FX_BRAND_MAIN})
    say("  demo(C 端)    POST -> http=%s code=%s" % (st, code_of(b)))
    chk("#5 C 端 token（无 perms）→ 403", st == 403, "http=%s" % st)

    st, b, raw = japi("POST", ADMIN_BRAND, op_o_t, {"name": FX_BRAND_MAIN})
    say("  op_order      POST -> http=%s code=%s" % (st, code_of(b)))
    chk("#6 ★ 反向对照：op_order（只有 order:*）POST → 403", st == 403, "http=%s" % st)

    st, b, raw = japi("GET", ADMIN_BRAND, op_o_t)
    say("  op_order      GET  -> http=%s code=%s" % (st, code_of(b)))
    chk("#7 ★ 反向对照：op_order 连 GET（brand:list）都 → 403", st == 403, "http=%s" % st)

    st, b, raw = japi("POST", ADMIN_BRAND, op_p_t,
                      {"name": FX_BRAND_MAIN, "logo": "https://mallx.local/fx-main.png",
                       "description": "day24 fixture", "status": 0})
    main_id = b.get("data")
    say("  op_product    POST -> http=%s code=%s data=%s" % (st, code_of(b), main_id))
    chk("#8 ★ op_product（PRODUCT_ADMIN，有 brand:create）→ 200 且返回 id",
        code_of(b) == 200 and isinstance(main_id, int),
        "code=%s data=%s" % (code_of(b), main_id))

    ids, st, err = adm_brand_ids(op_p_t)
    chk("#9 ★ op_product GET /api/admin/brands → 200 且能看到含停用的它",
        ids is not None and (isinstance(main_id, int) and main_id in ids),
        "http=%s ids=%s %s" % (st, sorted(ids) if ids else None, err))

    # ---------------------------------------------------------- [2] create
    say("\n[2] 新增：字段落库 / 默认值 / trim / 唯一约束 / 校验")
    if isinstance(main_id, int):
        row = one("SELECT name||'|'||logo||'|'||description||'|'||status::text "
                  "FROM brands WHERE id=%d" % main_id)
        say("  DB 主夹具行 name|logo|desc|status = %s" % row)
        chk("#10 DB：四个字段与提交逐字一致",
            row == "%s|https://mallx.local/fx-main.png|day24 fixture|0" % FX_BRAND_MAIN,
            "实得 %s" % row)
        chk("#11 ★ status=0 真的落库为 0（没被 DDL 默认值 1 覆盖）",
            one("SELECT status FROM brands WHERE id=%d" % main_id) == "0",
            "实得 %s" % one("SELECT status FROM brands WHERE id=%d" % main_id))

    st, b, raw = japi("POST", ADMIN_BRAND, op_p_t, {"name": FX_BRAND_DEFAULT})
    dflt_id = b.get("data")
    say("  不传 status   POST -> code=%s data=%s" % (code_of(b), dflt_id))
    chk("#12 不传 status → 走 DDL 默认值：DB status == 1",
        code_of(b) == 200 and isinstance(dflt_id, int) and
        one("SELECT status FROM brands WHERE id=%d" % dflt_id) == "1",
        "code=%s status=%s" % (code_of(b),
                               one("SELECT status FROM brands WHERE id=%d" % dflt_id)
                               if isinstance(dflt_id, int) else None))

    st, b, raw = japi("POST", ADMIN_BRAND, op_p_t, {"name": "  %s  " % FX_BRAND_TRIM})
    trim_id = b.get("data")
    trimmed = one("SELECT name FROM brands WHERE id=%d" % trim_id) if isinstance(trim_id, int) else None
    say("  name 带空格   POST -> code=%s 入库 name=%r" % (code_of(b), trimmed))
    chk("#13 ★ name 前后空格被 trim 后入库（Service 显式 trim）",
        code_of(b) == 200 and trimmed == FX_BRAND_TRIM, "入库=%r" % trimmed)

    st, b, raw = japi("POST", ADMIN_BRAND, op_p_t, {"name": FX_BRAND_MAIN})
    say("  重名         POST -> code=%s %s" % (code_of(b), short(raw, 100)))
    chk("#14 ★ 重名 → code=400（人话，不是 23505 冒成 500）", code_of(b) == 400,
        "code=%s" % code_of(b))
    chk("#15 DB：重名的那次没有插进去",
        int(one("SELECT count(*) FROM brands WHERE name='%s'" % FX_BRAND_MAIN)) == 1,
        "行数=%s" % one("SELECT count(*) FROM brands WHERE name='%s'" % FX_BRAND_MAIN))

    st, b, raw = japi("POST", ADMIN_BRAND, op_p_t, {"name": ""})
    say("  name 空串     POST -> code=%s" % code_of(b))
    chk("#16 name 空串 → code=400（@NotBlank 在 @Valid 层拦住）", code_of(b) == 400,
        "code=%s" % code_of(b))

    st, b, raw = japi("POST", ADMIN_BRAND, op_p_t, {"name": "FX-BRAND-BADSTATUS", "status": 2})
    say("  status=2     POST -> code=%s" % code_of(b))
    chk("#17 status=2 → code=400（@Max 拦住；不校验会写进库里当「第三个状态」）",
        code_of(b) == 400, "code=%s" % code_of(b))

    # ---------------------------------------------------------- [3] update
    say("\n[3] 修改：局部更新 / 重名 / 状态两端口径")
    if isinstance(main_id, int):
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_BRAND, main_id), op_p_t,
                          {"name": FX_BRAND_NEW_NAME})
        say("  改名         PUT -> code=%s" % code_of(b))
        chk("#18 改名 → code=200", code_of(b) == 200, "code=%s" % code_of(b))
        chk("#19 DB：name 已改为 %s" % FX_BRAND_NEW_NAME,
            one("SELECT name FROM brands WHERE id=%d" % main_id) == FX_BRAND_NEW_NAME,
            "实得 %s" % one("SELECT name FROM brands WHERE id=%d" % main_id))

        # ★ 局部更新：只传 logo
        before_row = one("SELECT name||'|'||status::text||'|'||COALESCE(logo,'NULL') "
                         "FROM brands WHERE id=%d" % main_id)
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_BRAND, main_id), op_p_t,
                          {"logo": "https://mallx.local/fx-main-v2.png"})
        after_row = one("SELECT name||'|'||status::text||'|'||COALESCE(logo,'NULL') "
                        "FROM brands WHERE id=%d" % main_id)
        say("  只传 logo    PUT -> code=%s" % code_of(b))
        say("      before = %s" % before_row)
        say("      after  = %s" % after_row)
        chk("#20 ★ 局部更新：只传 logo 时 logo 变、name 与 status 一个字不动",
            code_of(b) == 200 and after_row == "%s|0|https://mallx.local/fx-main-v2.png"
            % FX_BRAND_NEW_NAME,
            "实得 %s" % after_row)

        # ★ 改成「自己现在的名字」→ 不该被判重名
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_BRAND, main_id), op_p_t,
                          {"name": FX_BRAND_NEW_NAME})
        say("  改成自己同名 PUT -> code=%s" % code_of(b))
        chk("#21 ★ 改成「自己现在的名字」→ 200（查重必须排除自己，否则一改其他字段就误报）",
            code_of(b) == 200, "code=%s" % code_of(b))

        # ★ 改成别人的名字 → 400（「别人」= 种子品牌 Apple，它在基线上真实存在）
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_BRAND, main_id), op_p_t,
                          {"name": SEED_BRAND_NAME})
        say("  改成别人的名字（%s）PUT -> code=%s %s"
            % (SEED_BRAND_NAME, code_of(b), short(raw, 90)))
        chk("#22 ★ 改成别人的名字 → code=400"
            "（★ 样本必须是【真实存在】的名字，否则测到的是「改成一个没人用的新名字」= 200）",
            code_of(b) == 400, "code=%s" % code_of(b))

        # C 端此刻应该【看不见】它（status=0）
        c_ids_before, st_c, err_c = c_brand_ids()
        chk("#23 ★★ 两端口径（前情）：status=0 时 C 端字典里【没有】它",
            c_ids_before is not None and main_id not in c_ids_before,
            "http=%s 含?=%s" % (st_c, (main_id in c_ids_before) if c_ids_before else None))
        ad_ids, st_a, err_a = adm_brand_ids(adm_t)
        chk("#24 ★★ 同一时刻管理端字典里【有】它（含停用）—— 与 #23 成对才算证据",
            ad_ids is not None and main_id in ad_ids,
            "http=%s 含?=%s" % (st_a, (main_id in ad_ids) if ad_ids else None))

        # 改成 status=1 → C 端又能看见
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_BRAND, main_id), op_p_t, {"status": 1})
        chk("#25 重新启用 → code=200 且 DB status=1",
            code_of(b) == 200 and one("SELECT status FROM brands WHERE id=%d" % main_id) == "1",
            "code=%s status=%s" % (code_of(b), one("SELECT status FROM brands WHERE id=%d" % main_id)))
        c_ids_after, st_c2, _ = c_brand_ids()
        chk("#26 ★★ C 端字典里【又出现】它 —— 证明 #23 不是「接口坏了/永远看不见」",
            c_ids_after is not None and main_id in c_ids_after,
            "http=%s 含?=%s" % (st_c2, (main_id in c_ids_after) if c_ids_after else None))

    st, b, raw = japi("PUT", "%s/99999999" % ADMIN_BRAND, op_p_t, {"name": "x"})
    say("  改不存在 id  PUT -> code=%s" % code_of(b))
    chk("#27 改不存在的品牌 → code=404", code_of(b) == 404, "code=%s" % code_of(b))

    if isinstance(main_id, int):
        st, b, raw = japi("PUT", "%s/%d" % (ADMIN_BRAND, main_id), op_p_t, {"name": ""})
        say("  空串 name    PUT -> code=%s" % code_of(b))
        chk("#28 传空串 name → code=400（Service 显式挡：@Size 管不了空串）",
            code_of(b) == 400, "code=%s" % code_of(b))

    # ---------------------------------------------------------- [4] delete
    say("\n[4] 删除：引用校验（★ 含已软删商品）")
    fx_prd = None
    if isinstance(main_id, int):
        st, b, raw = japi("POST", ADMIN_PRD, adm_t,
                          {"categoryId": HAS_CATEGORY, "brandId": main_id, "name": FX_PRD,
                           "skus": [{"skuCode": FX_SKU, "price": 10.0}]})
        fx_prd = b.get("data")
        say("  建夹具商品   POST -> code=%s data=%s" % (code_of(b), fx_prd))
        chk("#29 在品牌 %s 下建一个商品（建立引用）" % main_id,
            code_of(b) == 200 and isinstance(fx_prd, int), "code=%s" % code_of(b))

    if isinstance(fx_prd, int):
        chk("#30 DB：该商品的 brand_id 确实指向 %s" % main_id,
            one("SELECT brand_id FROM products WHERE id=%d" % fx_prd) == str(main_id),
            "实得 %s" % one("SELECT brand_id FROM products WHERE id=%d" % fx_prd))

        st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_BRAND, main_id), adm_t)
        say("  删『有商品的品牌』-> code=%s %s" % (code_of(b), short(raw, 110)))
        chk("#31 ★ 有商品引用 → code=400（不是 500/外键错误）", code_of(b) == 400,
            "code=%s" % code_of(b))
        chk("#32 DB：品牌仍在（拒绝不是假装的）",
            int(one("SELECT count(*) FROM brands WHERE id=%d" % main_id)) == 1, "见上")

        st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_PRD, fx_prd), adm_t)
        soft_ok = one("SELECT is_deleted FROM products WHERE id=%d" % fx_prd) == "1"
        say("  软删该商品   DELETE -> code=%s is_deleted=%s" % (code_of(b), soft_ok))
        chk("#33 软删商品成功（is_deleted=1，但 fk_product_brand 的引用仍在）",
            code_of(b) == 200 and soft_ok, "code=%s is_deleted=%s" % (code_of(b), soft_ok))

        st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_BRAND, main_id), adm_t)
        say("  删『只挂着已软删商品』的品牌 -> code=%s %s" % (code_of(b), short(raw, 110)))
        chk("#34 ★★★ 商品已软删也拒绝删品牌 → code=400"
            "（若用 selectCount 会被 @TableLogic 补 is_deleted=0 而漏算 → 放行后撞外键 500）",
            code_of(b) == 400, "code=%s" % code_of(b))

        # 物理清掉夹具商品，解除引用（前提护栏：必须已软删，否则说明前面的断言没成立）
        chk("#35 前提护栏：夹具商品已软删（否则下面 §收尾的物理删会绕过业务语义）",
            one("SELECT is_deleted FROM products WHERE id=%d" % fx_prd) == "1",
            "is_deleted=%s" % one("SELECT is_deleted FROM products WHERE id=%d" % fx_prd))
        psql("DELETE FROM product_skus  WHERE product_id=%d" % fx_prd)
        psql("DELETE FROM product_images WHERE product_id=%d" % fx_prd)
        psql("DELETE FROM products       WHERE id=%d" % fx_prd)
        chk("#36 夹具商品已物理清除（引用解除）",
            int(one("SELECT count(*) FROM products WHERE id=%d" % fx_prd)) == 0, "见上")

        st, b, raw = japi("DELETE", "%s/%d" % (ADMIN_BRAND, main_id), adm_t)
        say("  删『无引用』的品牌 -> code=%s" % code_of(b))
        chk("#37 无引用的品牌 → 删除成功 code=200", code_of(b) == 200,
            "code=%s" % code_of(b))
        chk("#38 DB：该品牌行数 == 0（物理删，brands 无 is_deleted 列）",
            int(one("SELECT count(*) FROM brands WHERE id=%d" % main_id)) == 0,
            "残留=%s" % one("SELECT count(*) FROM brands WHERE id=%d" % main_id))

    st, b, raw = japi("DELETE", "%s/99999999" % ADMIN_BRAND, adm_t)
    say("  删不存在 id  DELETE -> code=%s" % code_of(b))
    chk("#39 删不存在的品牌 → code=404", code_of(b) == 404, "code=%s" % code_of(b))

    # ---------------------------------------------------------- [5] 清理
    say("\n[5] 清理夹具 + 回基线（先商品子表后主表）")
    psql("DELETE FROM product_skus  WHERE product_id > %d" % hw_prd)
    psql("DELETE FROM product_images WHERE product_id > %d" % hw_prd)
    psql("DELETE FROM products       WHERE id > %d" % hw_prd)
    psql("DELETE FROM brands         WHERE id > %d" % hw_brand)
    left_b = int(one("SELECT count(*) FROM brands WHERE id > %d" % hw_brand))
    left_p = int(one("SELECT count(*) FROM products WHERE id > %d" % hw_prd))
    say("  高水位以上残留：brands=%d products=%d" % (left_b, left_p))
    chk("#40 高水位以上零残留（brands 与 products）", left_b == 0 and left_p == 0,
        "brand=%d prd=%d" % (left_b, left_p))
    any_fx = int(one("SELECT (SELECT count(*) FROM brands WHERE name LIKE 'FX-%') "
                     "+ (SELECT count(*) FROM products WHERE name LIKE 'FX-%')"))
    chk("#41 全库无 FX- 前缀残留（跨表）", any_fx == 0, "残留=%d" % any_fx)
    chk("#42 ★ brands 回基线 %d 且种子 7 条逐字节不变" % SEED_BRANDS,
        int(one("SELECT count(*) FROM brands")) == SEED_BRANDS and
        seed_brand_snapshot() == base_seed,
        "count=%s\nbefore=%s\nafter =%s" % (one("SELECT count(*) FROM brands"),
                                            base_seed, seed_brand_snapshot()))
    end = counters()
    say("  收尾计数 vs 基线：%s" % {k: (base[k], end[k]) for k in base if base[k] != end[k]})
    chk("#43 收尾四表计数与基线一致（products 活行也回 %d）" % SEED_PRODUCTS_ALIVE,
        all(end[k] == base[k] for k in base) and alive_products() == SEED_PRODUCTS_ALIVE,
        "diff=%s alive=%d" % ({k: (base[k], end[k]) for k in base if base[k] != end[k]},
                              alive_products()))

    passed = sum(1 for _, g, _ in checks if g)
    say("\n" + "=" * 78)
    for nm, g, d in checks:
        say("%-4s %s%s" % ("PASS" if g else "FAIL", nm, ("   << " + d) if (d and not g) else ""))
    say("-" * 78)
    say("%d/%d passed" % (passed, len(checks)))
    say("★ 满额自校验：FULL_TOTAL = %d ；实得 %d ；%s"
        % (FULL_TOTAL, len(checks),
           "一致" if len(checks) == FULL_TOTAL else "★ 不一致 —— 有断言未被创建（分母缩水）"))
    say("VERDICT: %s" % ("BRAND-CRUD OK -- 权限矩阵有反向对照、status 两端口径成对断言、"
                         "局部更新成立、删除引用校验含『已软删商品』"
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
