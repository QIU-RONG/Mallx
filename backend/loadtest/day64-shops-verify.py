# -*- coding: utf-8 -*-
"""Day 64 · 店铺（展示层）验收。

覆盖：
  [A] C 端商品详情带 shopId / shopName
  [B] 管理端店铺列表（含停用）
  [C] 新建 / 重名 400 / 编辑 / 停用
  [D] 越权面：C 端 token 403、匿名 401

依赖：后端运行、DB 已执行 20-shops.sql。
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.environ.get("MALLX_BASE", "http://127.0.0.1:8081")
n_pass = n_fail = 0
records = []


def chk(name, ok, detail=""):
    global n_pass, n_fail
    line = "[%s] %s%s" % ("OK" if ok else "FAIL", name, ("   " + detail) if detail else "")
    print(line)
    records.append(line)
    n_pass += 1 if ok else 0
    n_fail += 0 if ok else 1
    return ok


def http(method, path, body=None, token=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode(), json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {}


def login_admin():
    return http("POST", "/api/auth/admin/login", {"username": "admin", "password": "admin123"})[1]["data"]["token"]


def login_user():
    return http("POST", "/api/auth/login", {"username": "demo", "password": "demo123"})[1]["data"]["token"]


def main():
    print("=" * 78)
    print("Day 64 · 店铺展示层验收 · BASE=%s" % BASE)
    print("=" * 78)

    st, j = http("GET", "/api/products/1")
    d = j.get("data") or {}
    chk("A1 C 端商品详情带 shopId", st == 200 and d.get("shopId"), "shopId=%s" % d.get("shopId"))
    chk("A2 C 端商品详情带 shopName", bool(d.get("shopName")), "shopName=%s" % d.get("shopName"))

    admin = login_admin()
    st, j = http("GET", "/api/admin/shops", token=admin)
    shops = j.get("data") or []
    chk("B1 管理端店铺列表 ≥3 家", st == 200 and len(shops) >= 3, "n=%d" % len(shops))
    chk("B2 列表含状态字段", all("status" in s for s in shops), "keys=%s" % (sorted(shops[0].keys()) if shops else []))

    st, j = http("POST", "/api/admin/shops", {"name": "D64 验收店", "description": "临时"}, admin)
    sid = j.get("data")
    chk("C1 新建店铺", st == 200 and j.get("code") == 200 and sid, "id=%s" % sid)

    st, j = http("POST", "/api/admin/shops", {"name": "D64 验收店"}, admin)
    chk("C2 重名 → 400 人话（不是 500）",
        st == 200 and j.get("code") == 400 and "已存在" in (j.get("message") or ""),
        "code=%s msg=%s" % (j.get("code"), j.get("message")))

    st, j = http("PUT", "/api/admin/shops/%s" % sid, {"description": "改过", "status": 0}, admin)
    chk("C3 编辑（改说明 + 停用）", st == 200 and j.get("code") == 200, "code=%s" % j.get("code"))
    st, j = http("GET", "/api/admin/shops", token=admin)
    edited = [s for s in (j.get("data") or []) if s.get("id") == sid]
    chk("C4 编辑结果落库", bool(edited) and edited[0].get("status") == 0 and edited[0].get("description") == "改过",
        str(edited[0]) if edited else "missing")

    st, j = http("PUT", "/api/admin/shops/999999", {"description": "x"}, admin)
    chk("C5 编辑不存在的店 → 业务码 404", st == 200 and j.get("code") == 404, "code=%s" % j.get("code"))

    user = login_user()
    st, j = http("GET", "/api/admin/shops", token=user)
    chk("D1 C 端 token 打管理端店铺 → 403", st == 403, "http=%s" % st)
    st, j = http("GET", "/api/admin/shops")
    chk("D2 匿名打管理端店铺 → 401", st == 401, "http=%s" % st)

    print("\n" + "=" * 78)
    print("ASSERTIONS: %d / %d passed" % (n_pass, n_pass + n_fail))
    print("VERDICT: %s" % ("OK" if n_fail == 0 else "FAIL"))
    print("=" * 78)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "day64-shops-verify-report.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(records) + "\n\nASSERTIONS: %d / %d passed\nVERDICT: %s\n"
                % (n_pass, n_pass + n_fail, "OK" if n_fail == 0 else "FAIL"))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
