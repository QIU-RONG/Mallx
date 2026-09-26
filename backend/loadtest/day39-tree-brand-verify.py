# -*- coding: utf-8 -*-
"""Day 39 · 分类树 / 品牌列表 cache-aside 验收（V1.1）

同一代次键域的另外两层缓存：目录写 bump 一次，detail / tree / brands 三层同时受益。
断言结构与 day38 同款，含毒性注入对照组：
  1. 首次 GET → Redis 出现 v{gen} 的树/列表 key（回填）
  2. ★ 毒性注入 → GET 必须读到毒值（证明命中路径真实生效）
  3. 管理端改名 → gen+1 → 读到新数据（旧代次整批失活）
  4. 夹具无商品引用 ⇒ API 干净删除（高水位归零，无需 psql）
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
REPORT = lp(r"D:\MallX\backend\loadtest\day39-tree-brand-verify-report.txt")

DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
REDIS_CONTAINER = "mallx-redis"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

lines = []
say = lines.append
checks = []
EXPECTED_CHECKS = 22          # 满额护栏


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
    rc, out, _e = redis_cli("GET", key)
    return None if rc != 0 or out in ("", "(nil)") else out


def gen_of():
    return redis_get("mallx:catalog:gen") or "0"


TS = str(int(time.time()))


def find_node(nodes, nid):
    for c in nodes or []:
        if c.get("id") == nid:
            return c
        hit = find_node(c.get("children"), nid)
        if hit is not None:
            return hit
    return None


def main():
    say("=" * 78)
    say("Day 39 · 分类树 / 品牌列表 cache-aside 验收")
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
    say("[1] 管理端登录 + 夹具（分类/品牌，无商品引用 ⇒ 结束可 API 干净删除）")
    j, ok = api("POST", "/api/auth/admin/login", body={"username": "admin", "password": "admin123"})
    chk("管理端登录", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    if not ok:
        return bail()
    token = j["data"]["token"]
    j, ok = api("POST", "/api/admin/categories", token=token, body={"name": "C39-分类-" + TS})
    chk("建夹具分类", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    cat_id = j.get("data") if ok else None
    j, ok = api("POST", "/api/admin/brands", token=token, body={"name": "C39-品牌-" + TS})
    chk("建夹具品牌", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    brand_id = j.get("data") if ok else None
    if not (cat_id and brand_id):
        return bail()

    say("")
    say("[2] 分类树：miss→回填→★毒性注入")
    gen0 = gen_of()
    tree_key = "mallx:cache:category:tree:v" + gen0
    code, raw = req("GET", "/api/categories/tree")
    j0 = json.loads(raw)
    chk("首次 GET /api/categories/tree 200 + code 200", code == 200 and j0.get("code") == 200)
    cached0 = redis_get(tree_key)
    chk("树缓存 key 出现（v%s）" % gen0, cached0 is not None)
    try:
        poison_tree = json.loads(cached0) if cached0 else None
    except Exception:                                                 # noqa: BLE001
        poison_tree = None
    node = find_node(poison_tree, cat_id) if poison_tree else None
    if node is not None:
        node["name"] = "POISON-树-" + TS
        rc, _o, err = redis_cli("SET", tree_key, json.dumps(poison_tree, ensure_ascii=False))
        chk("毒性注入：覆写树缓存", rc == 0, err[:120])
        j1 = json.loads(req("GET", "/api/categories/tree")[1])
        chk("★ GET 树读到毒值 ⇒ 命中路径真实生效",
            find_node(j1.get("data"), cat_id) is not None
            and find_node(j1["data"], cat_id)["name"] == node["name"])
    else:
        redis_cli("SET", tree_key, json.dumps({"_orphan": True}))
        chk("毒性注入：覆写树缓存", False, "夹具节点不在缓存树里（回填缺失或不在首层）")
        chk("★ GET 树读到毒值 ⇒ 命中路径真实生效", False, "无注入点")

    say("")
    say("[3] 树失效：分类改名 ⇒ gen+1 ⇒ 读到新名")
    new_cat = "C39-分类改名-" + TS
    j, ok = api("PUT", "/api/admin/categories/%s" % cat_id, token=token, body={"name": new_cat})
    chk("管理端 PUT 分类改名", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    gen1 = gen_of()
    chk("代次号已 +1（%s -> %s）" % (gen0, gen1), int(gen1) > int(gen0))
    j2 = json.loads(req("GET", "/api/categories/tree")[1])
    chk("★ 树读到新名（毒值随旧代次消失）",
        find_node(j2.get("data"), cat_id) is not None
        and find_node(j2["data"], cat_id)["name"] == new_cat)

    say("")
    say("[4] 品牌列表：miss→回填→★毒性注入")
    brand_key = "mallx:cache:brand:list:v%s:1" % gen1
    code, raw = req("GET", "/api/brands")
    j3 = json.loads(raw)
    chk("首次 GET /api/brands 200 + code 200", code == 200 and j3.get("code") == 200)
    cached_b = redis_get(brand_key)
    chk("品牌列表 key 出现（v%s:1）" % gen1, cached_b is not None)
    try:
        poison_b = json.loads(cached_b) if cached_b else None
    except Exception:                                                 # noqa: BLE001
        poison_b = None
    bnode = next((b for b in (poison_b or []) if b.get("id") == brand_id), None)
    if bnode is not None:
        bnode["name"] = "POISON-品牌-" + TS
        rc, _o, err = redis_cli("SET", brand_key, json.dumps(poison_b, ensure_ascii=False))
        chk("毒性注入：覆写品牌列表缓存", rc == 0, err[:120])
        j4 = json.loads(req("GET", "/api/brands")[1])
        bname = next((b["name"] for b in j4.get("data") or [] if b.get("id") == brand_id), None)
        chk("★ GET 品牌读到毒值 ⇒ 命中路径真实生效", bname == bnode["name"], "name=%s" % bname)
    else:
        redis_cli("SET", brand_key, json.dumps([]))
        chk("毒性注入：覆写品牌列表缓存", False, "夹具品牌不在缓存列表里（回填缺失）")
        chk("★ GET 品牌读到毒值 ⇒ 命中路径真实生效", False, "无注入点")

    say("")
    say("[5] 品牌失效：改名 ⇒ gen+1 ⇒ 读到新名")
    new_brand = "C39-品牌改名-" + TS
    j, ok = api("PUT", "/api/admin/brands/%s" % brand_id, token=token, body={"name": new_brand})
    chk("管理端 PUT 品牌改名", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    j5 = json.loads(req("GET", "/api/brands")[1])
    bname2 = next((b["name"] for b in j5.get("data") or [] if b.get("id") == brand_id), None)
    chk("★ 品牌读到新名（旧代次失活）", bname2 == new_brand, "name=%s" % bname2)

    say("")
    say("[6] 清理（无商品引用 ⇒ API 可删，高水位归零）")
    j, ok = api("DELETE", "/api/admin/categories/%s" % cat_id, token=token)
    chk("删除夹具分类", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    j, ok = api("DELETE", "/api/admin/brands/%s" % brand_id, token=token)
    chk("删除夹具品牌", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    j6 = json.loads(req("GET", "/api/categories/tree")[1])
    j7 = json.loads(req("GET", "/api/brands")[1])
    chk("树里已无夹具分类", find_node(j6.get("data"), cat_id) is None)
    chk("品牌列表已无夹具品牌", all(b.get("id") != brand_id for b in j7.get("data") or []))

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
    say("VERDICT: %s" % ("OK -- tree/brands 缓存的回填/命中/失效全部成立" if ok
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
