# -*- coding: utf-8 -*-
"""Day 38 · 商品详情 cache-aside 验收（V1.1）

回答四件事（对着设计断言，不采信接口自报）：
  1. miss→回源→回填：首次 GET 后，Redis 里必须出现 v{gen}:{id} 的 key
  2. 命中路径真的在被用：★ 对照组 = 毒性注入 —— 直接改写缓存里的 name 为毒值，
     再 GET 必须读到毒值。（若实现错成"永远读库"，本条必挂 —— 护栏有分辨力）
  3. 失效：商品改名 / 分类改名（detail 内嵌 categoryName）都让 gen+1，
     旧 key 一次性失活，新 GET 读到新数据
  4. 降级：Redis 停机后 GET 仍 200 且数据正确（回源），恢复后一切照旧

零副作用：夹具（分类/品牌/商品）通过管理端 API 创建、结束通过 API 删除；
对 Redis 只写会被代次淘汰的临时 key。
"""
from _paths import lp
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = lp(r"D:\MallX\backend\loadtest\day38-redis-detail-verify-report.txt")

DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
REDIS_CONTAINER = "mallx-redis"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

lines = []
say = lines.append
checks = []
EXPECTED_CHECKS = 25          # 满额护栏：数一数下面的 chk()（[4] 毒性注入段恒为 2 条）


def chk(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    say("  %s %s%s" % ("[OK]  " if ok else "[FAIL]", name, ("   " + detail) if detail else ""))


def req(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with opener.open(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                            # noqa: BLE001
        return -1, "%s: %s" % (type(e).__name__, e)


def api(method, path, token=None, body=None):
    """业务口径：HTTP 200 + body.code==200 才算成功。返回 (j, ok)。"""
    code, raw = req(method, path, token=token, body=body)
    try:
        j = json.loads(raw)
    except Exception:                                                 # noqa: BLE001
        return {"_http": code, "_raw": raw[:200]}, False
    return j, (code == 200 and j.get("code") == 200)


def wait_app(deadline=180):
    t0 = time.time()
    while time.time() - t0 < deadline:
        if req("GET", "/api/hello")[0] != -1:
            return True
        time.sleep(2)
    return False


def redis_cli(*args, timeout=30):
    p = subprocess.run([DOCKER, "exec", REDIS_CONTAINER, "redis-cli", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def redis_get(key):
    rc, out, _err = redis_cli("GET", key)
    if rc != 0 or out in ("", "(nil)"):
        return None
    return out


def redis_wait_ready(deadline=60):
    t0 = time.time()
    while time.time() - t0 < deadline:
        rc, out, _e = redis_cli("PING", timeout=5)
        if rc == 0 and out == "PONG":
            return True
        time.sleep(2)
    return False


def detail_key(gen, pid):
    return "mallx:cache:product:detail:v%s:%d" % (gen, pid)


PG_CONTAINER = "mallx-postgres"


def psql_exec(sql, fetch=False):
    """执行 psql；fetch=True 时返回 stdout（-t -A，供行数断言），否则返回是否 rc==0。"""
    p = subprocess.run([DOCKER, "exec", "-i", PG_CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-t", "-A", "-v", "ON_ERROR_STOP=1"],
                       input=sql, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if fetch:
        return (p.stdout or "").strip()
    return p.returncode == 0


def gen_of():
    return redis_get("mallx:catalog:gen") or "0"


TS = str(int(time.time()))

# ============================ main ============================

def main():
    say("=" * 78)
    say("Day 38 · 商品详情 cache-aside 验收（miss/命中/失效/降级）")
    say("=" * 78)

    say("")
    say("[0] 前置：应用可达 + Redis 可达")
    if not wait_app():
        say("  应用不可达，中止。")
        return bail()
    chk("应用可达（/api/hello 200）", True)
    rc, out, _e = redis_cli("PING", timeout=5)
    chk("Redis 可达（redis-cli PING）", rc == 0 and out == "PONG", "out=%s" % out)
    if rc != 0:
        return bail()

    say("")
    say("[1] 管理端登录 + 造夹具（分类/品牌/商品，全部走 API，结束删除）")
    j, ok = api("POST", "/api/auth/admin/login", body={"username": "admin", "password": "admin123"})
    chk("管理端登录", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    if not ok:
        return bail()
    token = j["data"]["token"]

    j, ok = api("POST", "/api/admin/categories", token=token, body={"name": "C38-分类-" + TS})
    chk("建夹具分类", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    cat_id = j.get("data") if ok else None

    j, ok = api("POST", "/api/admin/brands", token=token, body={"name": "C38-品牌-" + TS})
    chk("建夹具品牌", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    brand_id = j.get("data") if ok else None
    if not (ok and cat_id and brand_id):
        return bail()

    body = {"categoryId": cat_id, "brandId": brand_id,
            "name": "C38-商品-" + TS, "subtitle": "缓存验收",
            "description": "cache-aside verify", "mainImage": "/img/c38.jpg",
            "images": ["/img/c38-1.jpg"],
            "skus": [{"skuCode": "C38-%s-1" % TS, "name": "C38 SKU1", "price": 19.9,
                      "attributes": {"color": "red"}, "status": 1}]}
    j, ok = api("POST", "/api/admin/products", token=token, body=body)
    chk("建夹具商品（1 SKU + 1 图）", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    pid = j.get("data") if ok else None
    if not pid:
        return bail()
    say("      夹具：categoryId=%s brandId=%s productId=%s" % (cat_id, brand_id, pid))

    gen0 = gen_of()
    say("      当前代次 gen=%s" % gen0)

    say("")
    say("[2] miss → 回源 → 回填")
    code, raw = req("GET", "/api/products/%d" % pid)
    try:
        first = json.loads(raw)
    except Exception:                                                 # noqa: BLE001
        first = {"_raw": raw[:200]}
    chk("首次 GET 200 + code 200", code == 200 and first.get("code") == 200)
    key0 = detail_key(gen0, pid)
    cached0 = redis_get(key0)
    chk("首次 GET 后 Redis 出现 v%s:%d 的 key（miss→回填）" % (gen0, pid),
        cached0 is not None)
    if cached0:
        try:
            chk("缓存内容可反序列化且 name 一致",
                json.loads(cached0).get("name") == first["data"]["name"])
        except Exception as e:                                        # noqa: BLE001
            chk("缓存内容可反序列化且 name 一致", False, str(e)[:120])

    say("")
    say("[3] 命中路径：二次 GET 与首次逐字节一致")
    code2, raw2 = req("GET", "/api/products/%d" % pid)
    chk("二次 GET 200 + code 200", code2 == 200 and json.loads(raw2).get("code") == 200)
    chk("两次响应 data 逐字节一致（命中缓存）", json.loads(raw2)["data"] == first["data"])

    say("")
    say("[4] ★ 对照组：毒性注入 —— 证明读路径真的走缓存（而不是装样子读库）")
    # 两分支 chk 数恒等（3 条）：cached0 缺失时注入一个「必然不被读」的假 JSON，
    # 断言会 FAIL —— 这正是护栏要的信号（缓存没回填 = 实现错）。
    try:
        poison = json.loads(cached0) if cached0 else {"name": "POISON-毒-" + TS, "_orphan": True}
    except Exception:                                                 # noqa: BLE001
        poison = {"name": "POISON-毒-" + TS, "_orphan": True}
    rc, _o, err = redis_cli("SET", key0, json.dumps(poison, ensure_ascii=False))
    chk("毒性注入：覆写缓存成功", rc == 0, err[:120])
    j3, ok3 = api("GET", "/api/products/%d" % pid)
    got_name = (j3.get("data", {}) or {}).get("name")
    if cached0:
        chk("★ GET 读到毒值 ⇒ 命中路径真实生效", ok3 and got_name == poison["name"],
            "name=%s" % got_name)
    else:
        chk("★ GET 读到毒值 ⇒ 命中路径真实生效", False, "cached0 缺失（回填没发生），注入无效")

    say("")
    say("[5] 失效：商品改名 ⇒ 代次 +1 ⇒ 读到新名字")
    new_name = "C38-改名-" + TS
    j, ok = api("PUT", "/api/admin/products/%d" % pid, token=token, body={"name": new_name})
    chk("管理端 PUT 改名", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    gen1 = gen_of()
    chk("代次号已 +1（%s -> %s）" % (gen0, gen1), int(gen1) > int(gen0))
    j4, ok4 = api("GET", "/api/products/%d" % pid)
    chk("★ GET 读到新名字（旧 key 整批失活）", ok4 and j4["data"]["name"] == new_name,
        "name=%s" % (j4.get("data", {}) or {}).get("name"))
    chk("新代次 key 出现（v%s:%d）" % (gen1, pid), redis_get(detail_key(gen1, pid)) is not None)

    say("")
    say("[6] 非商品写也失效：分类改名 ⇒ detail 内嵌 categoryName 更新")
    new_cat = "C38-分类改名-" + TS
    j, ok = api("PUT", "/api/admin/categories/%s" % cat_id, token=token, body={"name": new_cat})
    chk("管理端 PUT 分类改名", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    j5, ok5 = api("GET", "/api/products/%d" % pid)
    chk("★ GET 的 categoryName = 新分类名（B 型脏点被覆盖）",
        ok5 and j5["data"]["categoryName"] == new_cat,
        "categoryName=%s" % (j5.get("data", {}) or {}).get("categoryName"))

    say("")
    say("[7] 降级：Redis 停机 ⇒ 接口照常（回源）")
    subprocess.run([DOCKER, "stop", REDIS_CONTAINER],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        j6, ok6 = api("GET", "/api/products/%d" % pid)
        chk("★ Redis 停机后 GET 仍 200 + 数据正确（回源降级）",
            ok6 and j6["data"]["name"] == new_name)
    finally:
        subprocess.run([DOCKER, "start", REDIS_CONTAINER],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        ready = redis_wait_ready()
        chk("Redis 已恢复（PING）", ready)
    # 重启后 gen 计数器可能清零（无持久化）—— bump 一次把代次推离历史值（见文档 §四）
    api("PUT", "/api/admin/products/%d" % pid, token=token, body={"subtitle": "c38-after-restart"})

    say("")
    say("[8] 清理 + 删除失效")
    j, ok = api("DELETE", "/api/admin/products/%d" % pid, token=token)
    chk("删除夹具商品", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    j7, ok7 = api("GET", "/api/products/%d" % pid)
    chk("★ 已删商品 GET = code 404（软删 + 伪装，缓存没有复活它）",
        ok7 is False and j7.get("code") == 404, "code=%s" % j7.get("code"))
    # ★ 物理清理（项目先例 = day26 夹具）：软删的商品会让 countByCategoryId 永远拒绝
    #   删分类（含已软删商品口径）⇒ API 删不掉夹具，只能 psql 按子表→主表顺序清。
    purge = ("DELETE FROM inventories WHERE sku_id IN (SELECT id FROM product_skus WHERE product_id=%d);"
             "DELETE FROM product_skus WHERE product_id=%d;"
             "DELETE FROM product_images WHERE product_id=%d;"
             "DELETE FROM products WHERE id=%d;"
             "DELETE FROM categories WHERE id=%s;"
             "DELETE FROM brands WHERE id=%s;" % (pid, pid, pid, pid, cat_id, brand_id))
    purge_ok = psql_exec(purge)
    chk("psql 物理清理夹具（inventories→skus→images→products→categories→brands）", purge_ok)
    n_left = psql_exec("SELECT count(*) FROM products WHERE id=%d; SELECT count(*) FROM categories WHERE id=%s;"
                       "SELECT count(*) FROM brands WHERE id=%s;" % (pid, cat_id, brand_id),
                       fetch=True)
    chk("夹具高水位归零（products/categories/brands 均 0 行）",
        n_left is not None and n_left.split() == ["0", "0", "0"], "counts=%s" % n_left)

    return bail()


def bail(code=None):
    say("")
    say("=" * 78)
    total = len(checks)
    n_fail = sum(1 for _n, ok, _d in checks if not ok)
    say("ASSERTIONS: %d / %d passed   (EXPECTED=%d)" % (total - n_fail, total, EXPECTED_CHECKS))
    full = (total == EXPECTED_CHECKS)
    if not full:
        say("★ 满额护栏未过：实得 %d 条，期望 %d 条 ⇒ 有检查项没被执行到" % (total, EXPECTED_CHECKS))
    ok = (n_fail == 0) and full
    say("VERDICT: %s" % ("OK -- 详情缓存的 miss/命中/失效/降级四件事全部成立" if ok
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
