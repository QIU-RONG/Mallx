# -*- coding: utf-8 -*-
"""Day 17 · 链路 A 验收 —— `GET /api/admin/orders`（管理端订单列表 · 数据权限反转）

与「骨架门禁」的分工：骨架门禁只答「路由通没通、权限挡没挡」，
本脚本答**第三层**：返回的东西**对不对**（对着设计断言，不采信接口自报）。

★★ 判据的三层结构（本项目已经踩过两次的教训）：
    ① 静态自检（XML 良构 / 方法名对齐）—— 拦命名类错，拦不住 SQL 语义
    ② 真跑（HTTP 200）—— 拦语法类错，拦不住「漏列 / 漏兜底」
    ③ 对着设计断言 + DB 对账  ← 本脚本

★ 「不信接口自报」落地成两件事：
    · 每一条 record 的每个字段，都去 `orders` 表里查真值逐字段比；
    · total 与 id 列表，都去 DB 数一遍，不用响应里的 total 反推。

★ 鉴权三态必须分开判（本项目约定）：
    真 HTTP 401 / 403 由 Security 过滤器层给出（不经过 @RestControllerAdvice）；
    业务错误才是 HTTP 200 + body.code。
"""
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8080"
REPORT = r"D:\MallX\backend\loadtest\day17-a-order-list-verify-report.txt"

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"

# ★ 显式清空代理：系统代理会连 127.0.0.1 一起拦，表现是 502 os error 10061（不是服务挂了）
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# AdminOrderVO 的 10 个字段（= 出参白名单）
VO_FIELDS = ["id", "orderNo", "userId", "userNickname",
             "totalAmount", "payAmount", "status",
             "receiverName", "receiverPhone", "createdAt"]

lines = []
say = lines.append
checks = []          # (name, ok, detail)


def ck(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    say("  %s %-58s %s" % ("✅" if ok else "❌", name, detail))


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


def wait_app(deadline=180):
    t0 = time.time()
    while time.time() - t0 < deadline:
        if req("GET", "/api/hello")[0] != -1:
            return True, time.time() - t0
        time.sleep(2)
    return False, time.time() - t0


def login(path, username, password):
    code, body = req("POST", path, body={"username": username, "password": password})
    try:
        j = json.loads(body)
    except Exception:                                                 # noqa: BLE001
        return None, "HTTP %s / 非 JSON: %s" % (code, body[:160])
    if j.get("code") != 200:
        return None, "登录失败: %s" % body[:160]
    return j["data"]["token"], "OK"


def psql(sql):
    p = subprocess.run([DOCKER, "exec", "-i", CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-t", "-A", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("psql 失败: %s" % (p.stderr or "")[:300])
    return [r for r in (p.stdout or "").strip().splitlines() if r.strip()]


def page_of(token, query=""):
    """取一页，返回 (http_code, body_json_or_text)。"""
    code, body = req("GET", "/api/admin/orders" + query, token=token)
    try:
        return code, json.loads(body)
    except Exception:                                                 # noqa: BLE001
        return code, body


say("=" * 78)
say("Day 17 · 链路 A 验收 —— GET /api/admin/orders")
say("=" * 78)

# ============ 0. 应用可达 ============
ok, secs = wait_app()
say("应用可达: %s（等待 %.1fs）" % ("是" if ok else "否", secs))
if not ok:
    say("❌ 应用没起来，中止。")
    print("\n".join(lines))
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    raise SystemExit(1)
say("")

# ============ 1. DB 基线（不信接口自报） ============
db_rows = {}
for r in psql("SELECT o.id, o.order_no, o.user_id, COALESCE(u.nickname,'用户****'), "
              "o.total_amount, o.pay_amount, o.status, o.receiver_name, o.receiver_phone, "
              "o.created_at FROM orders o LEFT JOIN users u ON u.id = o.user_id "
              "ORDER BY o.id DESC;"):
    f = r.split("|")
    db_rows[int(f[0])] = dict(zip(
        ["id", "orderNo", "userId", "userNickname", "totalAmount", "payAmount",
         "status", "receiverName", "receiverPhone", "createdAt"], f))
db_ids_desc = list(db_rows.keys())

say("[1] DB 基线（直接查库，作为唯一真相）")
say("      orders 总行数 = %d" % len(db_ids_desc))
say("      id 降序 = %s" % db_ids_desc)
for st in ("PAID", "PENDING_PAYMENT", "CANCELLED"):
    n = len(psql("SELECT id FROM orders WHERE status='%s';" % st))
    say("      status=%-16s -> %d 行" % (st, n))
say("")

# ============ 2. 登录 ============
demo_token, demo_msg = login("/api/auth/login", "demo", "demo123")
admin_token, admin_msg = login("/api/auth/admin/login", "admin", "admin123")
say("[2] 登录  demo: %s   admin: %s" % (demo_msg, admin_msg))
say("")

# ============ 3. 权限三态 ============
say("[3] 权限三态（真 HTTP 状态码，不是 body.code）")
c_anon, _ = req("GET", "/api/admin/orders")
ck("匿名（不带头）-> 真 HTTP 401", c_anon == 401, "实得 %s" % c_anon)
c_demo, _ = req("GET", "/api/admin/orders", token=demo_token)
ck("C 端 demo token -> 真 HTTP 403", c_demo == 403, "实得 %s" % c_demo)
say("")

# ============ 4. 超管正常返回 ============
say("[4] 超管：HTTP 与业务码")
code, j = page_of(admin_token)
ck("HTTP 200", code == 200, "实得 %s" % code)
ck("body.code == 200", isinstance(j, dict) and j.get("code") == 200,
   "实得 %s" % (j.get("code") if isinstance(j, dict) else j))
data = j["data"] if isinstance(j, dict) else {}
ck("PageResult 四字段齐（records/total/current/size）",
   all(k in data for k in ("records", "total", "current", "size")), "keys=%s" % sorted(data.keys()))
recs = data.get("records", [])
ck("total 与 DB 行数一致", data.get("total") == len(db_ids_desc),
   "接口 %s / DB %s" % (data.get("total"), len(db_ids_desc)))
say("")

# ============ 5. ★ 逐记录逐字段对账 ============
say("[5] ★ 逐记录逐字段对账（接口 vs DB，10 字段全覆盖）")
api_ids = [r.get("id") for r in recs]
ck("id 列表与 DB 逐位一致且降序", api_ids == db_ids_desc,
   "接口 %s" % api_ids)
missing_keys, mism = [], []
for r in recs:
    rid = r.get("id")
    if set(r.keys()) != set(VO_FIELDS):
        missing_keys.append((rid, sorted(set(VO_FIELDS) - set(r.keys()))))
    for nul in VO_FIELDS:
        if r.get(nul) is None:
            mism.append("id=%s 字段 %s 为 null" % (rid, nul))
    d = db_rows.get(rid)
    if not d:
        mism.append("id=%s 在 DB 里不存在（幽灵行）" % rid)
        continue
    if r.get("orderNo") != d["orderNo"]:
        mism.append("id=%s orderNo %r != %r" % (rid, r.get("orderNo"), d["orderNo"]))
    if r.get("status") != d["status"]:
        mism.append("id=%s status %r != %r" % (rid, r.get("status"), d["status"]))
    if str(r.get("userId")) != str(d["userId"]):
        mism.append("id=%s userId %r != %r" % (rid, r.get("userId"), d["userId"]))
    if r.get("userNickname") != d["userNickname"]:
        mism.append("id=%s userNickname %r != %r" % (rid, r.get("userNickname"), d["userNickname"]))
    if r.get("receiverName") != d["receiverName"] or r.get("receiverPhone") != d["receiverPhone"]:
        mism.append("id=%s 收货人/电话 与 DB 不符" % rid)
    for k in ("totalAmount", "payAmount"):
        try:
            if abs(float(r.get(k)) - float(d[k])) > 0.001:
                mism.append("id=%s %s %s != %s" % (rid, k, r.get(k), d[k]))
        except Exception:                                             # noqa: BLE001
            mism.append("id=%s %s 无法比较: %r" % (rid, k, r.get(k)))
    if str(r.get("createdAt", "")).replace("T", " ")[:19] != d["createdAt"][:19]:
        mism.append("id=%s createdAt %r != %r" % (rid, r.get("createdAt"), d["createdAt"]))
ck("每条 record 的 key 集合 == VO 的 10 字段", not missing_keys, str(missing_keys[:3]))
ck("无 null 字段（含上轮漏掉的 orderNo / status）", not [m for m in mism if "为 null" in m],
   str([m for m in mism if "为 null" in m][:3]))
ck("逐字段值与 DB 完全一致", not mism, str(mism[:3]))
say("")

# ============ 6. 筛选条件 ============
say("[6] 两个可选筛选条件（<if>）")
_, j2 = page_of(admin_token, "?status=PAID")
n_paid_db = len(psql("SELECT id FROM orders WHERE status='PAID';"))
ck("?status=PAID -> total 与 DB 一致", j2["data"]["total"] == n_paid_db,
   "接口 %s / DB %s" % (j2["data"]["total"], n_paid_db))
ck("?status=PAID -> 每条 status 都是 PAID",
   all(r["status"] == "PAID" for r in j2["data"]["records"]))
ck("?status=PAID -> id 集合与 DB 一致",
   [r["id"] for r in j2["data"]["records"]] ==
   [int(x) for x in psql("SELECT id FROM orders WHERE status='PAID' ORDER BY id DESC;")])

n_u1 = len(psql("SELECT id FROM orders WHERE user_id=1;"))
_, j3 = page_of(admin_token, "?userId=1")
ck("?userId=1 -> total 与 DB 一致", j3["data"]["total"] == n_u1,
   "接口 %s / DB %s" % (j3["data"]["total"], n_u1))

n_u2 = len(psql("SELECT id FROM orders WHERE user_id=2;"))
_, j4 = page_of(admin_token, "?userId=2")
ck("?userId=2（DB 里 0 单）-> total=0 且不报错",
   j4["data"]["total"] == n_u2 == 0, "接口 %s / DB %s" % (j4["data"]["total"], n_u2))

ck("?status=PENDING_PAYMENT（DB 里 0 单）-> total=0",
   page_of(admin_token, "?status=PENDING_PAYMENT")[1]["data"]["total"] ==
   len(psql("SELECT id FROM orders WHERE status='PENDING_PAYMENT';")))
ck("?status= (空串) -> 等同不筛",
   page_of(admin_token, "?status=")[1]["data"]["total"] == len(db_ids_desc))
# ★★ 这一条才是真正区分「Java 侧 isBlank 归一化」的判据：
#    空格串 != '' ，XML 那个 != '' 拦不住它 -> 没归一化的话会拼出 AND status=' ' -> 0 行
ck("?status=%20(空格) -> 等同不筛【★区分性判据】",
   page_of(admin_token, "?status=%20")[1]["data"]["total"] == len(db_ids_desc),
   "实得 total=%s，期望 %s" % (page_of(admin_token, "?status=%20")[1]["data"]["total"], len(db_ids_desc)))
say("")

# ============ 7. 分页：不重不漏 + 夹紧 ============
say("[7] 分页正确性（不重不漏）与参数夹紧")
p1 = page_of(admin_token, "?page=1&size=3")[1]["data"]
p2 = page_of(admin_token, "?page=2&size=3")[1]["data"]
p3 = page_of(admin_token, "?page=3&size=3")[1]["data"]
ids1 = [r["id"] for r in p1["records"]]
ids2 = [r["id"] for r in p2["records"]]
ids3 = [r["id"] for r in p3["records"]]
ck("每页 size=3", len(ids1) == len(ids2) == 3, "%s/%s/%s" % (len(ids1), len(ids2), len(ids3)))
ck("翻页不重不漏（并集 == 全量、无交集）",
   ids1 + ids2 + ids3 == db_ids_desc and len(set(ids1) & set(ids2)) == 0,
   "%s + %s + %s" % (ids1, ids2, ids3))
ck("current 回显正确", (p1["current"], p2["current"], p3["current"]) == (1, 2, 3),
   "%s/%s/%s" % (p1["current"], p2["current"], p3["current"]))

r0 = page_of(admin_token, "?size=0")[1]["data"]
ck("?size=0 -> 夹紧成 1 行（不夹紧时 MP 会返回空列表）",
   len(r0["records"]) == 1 and r0["size"] == 1,
   "len=%s size=%s" % (len(r0["records"]), r0["size"]))
rneg = page_of(admin_token, "?size=-5")[1]["data"]
ck("?size=-5 -> 夹紧成 1 行（不夹紧时 size<0 = 不执行分页、查全表）",
   len(rneg["records"]) == 1 and rneg["size"] == 1,
   "len=%s size=%s" % (len(rneg["records"]), rneg["size"]))
rbig = page_of(admin_token, "?size=99999")[1]["data"]
ck("?size=99999 -> 被截到上限（<=100）", rbig["size"] <= 100, "size=%s" % rbig["size"])
rp0 = page_of(admin_token, "?page=0")[1]["data"]
ck("?page=0 -> current 规范化为 1", rp0["current"] == 1, "current=%s" % rp0["current"])
say("")

# ============ 8. 排序稳定性 ============
say("[8] 排序（不带排序的分页 = 随机翻页 / 漏行）")
ck("严格按 id 降序", api_ids == sorted(api_ids, reverse=True), "%s" % api_ids)
say("")

# ============ 汇总 ============
bad = [c for c in checks if not c[1]]
say("=" * 78)
if bad:
    say("VERDICT: FAIL —— %d / %d 项不符" % (len(bad), len(checks)))
    for n, _, d in bad:
        say("   · %s   %s" % (n, d))
else:
    say("VERDICT: OK —— %d / %d 项全过" % (len(checks), len(checks)))
    say("  路由 + 权限三态 + 60 项字段对账 + 筛选/分页/夹紧全部成立。")
say("=" * 78)

report = "\n".join(lines)
print(report)
open(REPORT, "w", encoding="utf-8").write(report + "\n")
raise SystemExit(0 if not bad else 1)
