# -*- coding: utf-8 -*-
"""Day 40 · 缓存护栏验收 —— 负缓存（防穿透）+ 代次翻转安全性

负缓存的完整生命周期（对着设计断言）：
  A. 下架 → GET 404（miss 回源）→ key = NEG → 再 GET 仍 404（NEG 短路，不再打库）
  B. ★ 重新上架 → bump ⇒ 旧代次 NEG 整批失活 → GET 200（负缓存没有误伤恢复）
  C. 不存在的 id → 404 + NEG（穿透被挡）→ 再 GET 仍 404
对照组语义：A 的「key == NEG」若实现错成「404 不写缓存」，本条必挂；
B 若实现错成「NEG 永不过期/不随代次失活」，上架后仍 404，本条必挂。
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
REPORT = lp(r"D:\MallX\backend\loadtest\day40-redis-guard-verify-report.txt")

DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
REDIS_CONTAINER = "mallx-redis"
PG_CONTAINER = "mallx-postgres"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

lines = []
say = lines.append
checks = []
EXPECTED_CHECKS = 19          # 满额护栏


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
    code, raw = req(method, path, token=token, body=body)
    try:
        j = json.loads(raw)
    except Exception:                                                 # noqa: BLE001
        return {"_http": code}, False
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
    rc, out, _e = redis_cli("GET", key)
    return None if rc != 0 or out in ("", "(nil)") else out


def gen_of():
    return redis_get("mallx:catalog:gen") or "0"


def psql_exec(sql, fetch=False):
    p = subprocess.run([DOCKER, "exec", "-i", PG_CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-t", "-A", "-v", "ON_ERROR_STOP=1"],
                       input=sql, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if fetch:
        return (p.stdout or "").strip()
    return p.returncode == 0


TS = str(int(time.time()))


def main():
    say("=" * 78)
    say("Day 40 · 缓存护栏验收 —— 负缓存（防穿透）+ 代次翻转")
    say("=" * 78)

    say("")
    say("[0] 前置")
    if not wait_app():
        say("  应用不可达，中止。")
        return bail()
    chk("应用可达（/api/hello 200）", True)
    rc, out, _e = redis_cli("PING", timeout=5)
    chk("Redis 可达（PING）", rc == 0 and out == "PONG", "out=%s" % out)
    if rc != 0:
        return bail()

    say("")
    say("[1] 登录 + 夹具（上架中商品）")
    j, ok = api("POST", "/api/auth/admin/login", body={"username": "admin", "password": "admin123"})
    chk("管理端登录", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    if not ok:
        return bail()
    token = j["data"]["token"]
    j, ok = api("POST", "/api/admin/categories", token=token, body={"name": "C40-分类-" + TS})
    chk("建夹具分类", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    cat_id = j.get("data") if ok else None
    j, ok = api("POST", "/api/admin/brands", token=token, body={"name": "C40-品牌-" + TS})
    chk("建夹具品牌", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    brand_id = j.get("data") if ok else None
    if not (cat_id and brand_id):
        return bail()
    body = {"categoryId": cat_id, "brandId": brand_id, "name": "C40-商品-" + TS,
            "subtitle": "护栏验收", "mainImage": "/img/c40.jpg", "status": 1,
            "skus": [{"skuCode": "C40-%s-1" % TS, "name": "C40 SKU1", "price": 9.9, "status": 1}]}
    j, ok = api("POST", "/api/admin/products", token=token, body=body)
    chk("建夹具商品", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    pid = j.get("data") if ok else None
    if not pid:
        return bail()

    say("")
    say("[2] A · 下架 → 404 → NEG 落地 → 再 GET 仍 404（NEG 短路）")
    j, ok = api("PUT", "/api/admin/products/%d" % pid, token=token, body={"status": 0})
    chk("管理端 PUT 下架（status=0）", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    gen0 = gen_of()   # ★ 下架本身会 bump ⇒ 负缓存写在 PUT 之后的代次（先取后拼 key）
    key = "mallx:cache:product:detail:v%s:%d" % (gen0, pid)
    j1, ok1 = api("GET", "/api/products/%d" % pid)
    chk("下架后 GET = code 404（伪装口径）", ok1 is False and j1.get("code") == 404,
        "code=%s" % j1.get("code"))
    chk("key = NEG（负缓存落地）", redis_get(key) == "NEG")
    j2, ok2 = api("GET", "/api/products/%d" % pid)
    chk("再 GET 仍 404（NEG 命中，不再回源）", ok2 is False and j2.get("code") == 404)

    say("")
    say("[3] B · ★ 重新上架 → 代次翻转 ⇒ NEG 失活 → GET 200")
    j, ok = api("PUT", "/api/admin/products/%d" % pid, token=token, body={"status": 1})
    chk("管理端 PUT 上架（status=1）", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    gen1 = gen_of()
    chk("代次号已 +1（%s -> %s）" % (gen0, gen1), int(gen1) > int(gen0))
    j3, ok3 = api("GET", "/api/products/%d" % pid)
    chk("★ 上架后 GET = 200（负缓存随旧代次失活，没有误伤恢复）",
        ok3 and j3["data"]["name"] == "C40-商品-" + TS)

    say("")
    say("[4] C · 不存在的 id → 404 + NEG（穿透被挡）")
    ghost = 999999999
    gkey = "mallx:cache:product:detail:v%s:%d" % (gen1, ghost)
    j4, ok4 = api("GET", "/api/products/%d" % ghost)
    chk("幽灵 id GET = code 404", ok4 is False and j4.get("code") == 404)
    chk("幽灵 key = NEG（穿透不再打库）", redis_get(gkey) == "NEG")
    j5, ok5 = api("GET", "/api/products/%d" % ghost)
    chk("幽灵 id 再 GET 仍 404（NEG 命中）", ok5 is False and j5.get("code") == 404)

    say("")
    say("[5] 清理（软删堵分类 ⇒ psql 物理清理，day26 先例）")
    j, ok = api("DELETE", "/api/admin/products/%d" % pid, token=token)
    chk("删除夹具商品", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    purge = ("DELETE FROM inventories WHERE sku_id IN (SELECT id FROM product_skus WHERE product_id=%d);"
             "DELETE FROM product_skus WHERE product_id=%d;"
             "DELETE FROM product_images WHERE product_id=%d;"
             "DELETE FROM products WHERE id=%d;"
             "DELETE FROM categories WHERE id=%s;"
             "DELETE FROM brands WHERE id=%s;" % (pid, pid, pid, pid, cat_id, brand_id))
    chk("psql 物理清理夹具", psql_exec(purge))
    counts = psql_exec("SELECT count(*) FROM products WHERE id=%d; "
                       "SELECT count(*) FROM categories WHERE id=%s; "
                       "SELECT count(*) FROM brands WHERE id=%s;" % (pid, cat_id, brand_id),
                       fetch=True)
    chk("夹具高水位归零", counts.split() == ["0", "0", "0"], "counts=%s" % counts.replace("\n", ","))

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
    say("VERDICT: %s" % ("OK -- 负缓存生命周期与代次翻转安全性全部成立" if ok
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
