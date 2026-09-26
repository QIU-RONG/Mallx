# -*- coding: utf-8 -*-
"""Day 41 · RabbitMQ 延迟关单验收（V1.1）

设计断言：下单 → afterCommit 发延迟消息（TTL 可配）→ TTL 到期经 DLX 进 close 队列 →
listener 走 cancelOne CAS 关单。**秒级关闭** —— 扫描兜底是 60s 周期 + 2min 超时，
所以「几十秒内就关了」只有 MQ 路径能解释（本脚本启动的应用用 ORDER_CLOSE_DELAY_MS=5000）。
断言：新单 ~10s 内 PENDING_PAYMENT → CANCELLED；.elapsed 远小于扫描周期。
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
REPORT = lp(r"D:\MallX\backend\loadtest\day41-rabbitmq-close-verify-report.txt")

DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
MQ_CONTAINER = "mallx-rabbitmq"
TARGET_SKU = 4
ADDRESS_ID = 2              # demo 的默认地址（day26 夹具）

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

lines = []
say = lines.append
checks = []
EXPECTED_CHECKS = 12         # 满额护栏


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


def mq_ping():
    p = subprocess.run([DOCKER, "exec", MQ_CONTAINER, "rabbitmq-diagnostics", "-q", "ping"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    out = p.stdout or ""
    # 3.13 输出 "Ping succeeded"（旧版是 "pong"）—— 两种都认
    return p.returncode == 0 and ("pong" in out or "Ping succeeded" in out)


PG_CONTAINER = "mallx-postgres"


def psql_exec(sql, fetch=False):
    p = subprocess.run([DOCKER, "exec", "-i", PG_CONTAINER, "psql", "-U", "mallx", "-d", "mallx",
                        "-X", "-t", "-A", "-v", "ON_ERROR_STOP=1"],
                       input=sql, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if fetch:
        return (p.stdout or "").strip()
    return p.returncode == 0


def main():
    say("=" * 78)
    say("Day 41 · RabbitMQ 延迟关单验收（下单 → TTL → DLX → cancelOne）")
    say("=" * 78)

    say("")
    say("[0] 前置：应用可达 + RabbitMQ 可达")
    if not wait_app():
        say("  应用不可达，中止。")
        return bail()
    chk("应用可达（/api/hello 200）", True)
    chk("RabbitMQ 可达（rabbitmq-diagnostics ping）", mq_ping())
    if not mq_ping():
        return bail()
    ledger_watermark = int(psql_exec("SELECT COALESCE(max(id),0) FROM inventory_logs;", fetch=True) or "0")
    say("      inventory_logs 水位 = %d" % ledger_watermark)

    say("")
    say("[1] C 端登录（demo）+ 地址 + 加购勾选")
    j, ok = api("POST", "/api/auth/login", body={"username": "demo", "password": "demo123"})
    chk("demo 登录", ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    if not ok:
        return bail()
    token = j["data"]["token"]

    j, ok = api("GET", "/api/addresses", token=token)
    addrs = j.get("data") or [] if ok else []
    chk("demo 有可用地址（id=%s）" % (addrs[0]["id"] if addrs else "-"), bool(addrs))
    if not addrs:
        return bail()
    address_id = addrs[0]["id"]

    j, ok = api("POST", "/api/cart", token=token, body={"skuId": TARGET_SKU, "quantity": 1})
    chk("加购 SKU %d" % TARGET_SKU, ok, "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    # 只勾选刚加的这一条（createFromCart 消费所有已勾选项）
    j, ok = api("GET", "/api/cart", token=token)
    items = (j.get("data") or {}).get("items") or []
    it = next((x for x in items if x.get("skuId") == TARGET_SKU), None)
    chk("购物车里有目标 SKU", it is not None)
    if not it:
        return bail()
    for x in items:
        want = (x["id"] == it["id"])
        if bool(x.get("selected")) != want:
            api("PUT", "/api/cart/%s/selected" % x["id"], token=token, body={"selected": want})

    say("")
    say("[2] 下单 + 计时：PENDING_PAYMENT → CANCELLED（秒级）")
    j, ok = api("POST", "/api/orders", token=token, body={"addressId": address_id})
    chk("下单成功（code 200）", ok and isinstance(j.get("data"), int),
        "" if ok else json.dumps(j, ensure_ascii=False)[:160])
    oid = j.get("data") if ok else None
    if not oid:
        return bail()
    t_place = time.time()
    j, ok = api("GET", "/api/orders/%d" % oid, token=token)
    chk("下单后状态 = PENDING_PAYMENT", ok and j["data"]["status"] == "PENDING_PAYMENT",
        "status=%s" % (j.get("data", {}) or {}).get("status"))

    deadline = time.time() + 45
    status = None
    while time.time() < deadline:
        j, ok = api("GET", "/api/orders/%d" % oid, token=token)
        status = (j.get("data") or {}).get("status") if ok else None
        if status == "CANCELLED":
            break
        time.sleep(2)
    elapsed = time.time() - t_place
    chk("★ %0.1fs 内订单被关单（status=%s）—— 只有 MQ 路径能这么快（扫描 60s 周期 + 2min 超时）"
        % (elapsed, status), status == "CANCELLED" and elapsed < 45, "elapsed=%.1fs" % elapsed)
    chk("库存已回补口径：关单时间 < 扫描周期（60s）", elapsed < 55, "elapsed=%.1fs" % elapsed)

    say("")
    say("[3] 收尾")
    j, ok = api("GET", "/api/orders/%d" % oid, token=token)
    chk("订单详情可查（CANCELLED 终态稳定）", ok and j["data"]["status"] == "CANCELLED")
    # 高水位清理：本单写入的 inventory_logs（ORDER_LOCK/CANCEL_RELEASE）会破坏
    # day14 的「ledger 全空」基线 ⇒ 只删 id > 起始水位的行（day14 同款手法）。
    # ★ 订单本体也要物理清（CANCELLED 单会留在 orders 里，把 day26 夹具的
    #   「6 单基线」顶成 7 ⇒ 收集器 (c) 数据库回基线必挂）。
    chk("清掉本单写入的库存流水（day14 基线不被污染）",
        psql_exec("DELETE FROM inventory_logs WHERE id > %d;" % ledger_watermark))
    chk("清掉本单的订单与明细（day26 基线不被污染）",
        psql_exec("DELETE FROM order_items WHERE order_id=%d; DELETE FROM orders WHERE id=%d;"
                  % (oid, oid)))

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
    say("VERDICT: %s" % ("OK -- MQ 延迟关单秒级生效（扫描兜底保留）" if ok
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
