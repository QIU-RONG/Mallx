# -*- coding: utf-8 -*-
"""
Day 21 优惠券（阶段二）验收：A 不用券原路 / B 满减核销 / C 折扣与边界 / D 归属(IDOR) / E 退券 / F 库存对账。

对应 docs/daily/Day-21-优惠券阶段二.md §八 的验收清单。设计原则沿用项目模板
（day17-f-* / day20-coupon-verify.py）：
  1. 不信接口自报 —— 每条业务断言都配一次 psql 对账。
  2. 业务失败 = HTTP 200 + body.code（协议层失败才是真 HTTP 码）。
  3. 满额断言写死常量 EXPECTED，并核对 PASS + FAIL == EXPECTED（不许断言被静默跳过）。
  4. 可重复执行 + 高水位线清理：跑完把库还原到脚本开始时的样子。

★★ 为什么本脚本要自造「商品 + SKU + 库存 + 用户 + 地址」而不用库里的真实 SKU：
  库里 7 个 SKU 的价格全在 6499–12499 之间，而本日要断言的边界是
  「封顶（面额 300 > 总额 200）」「小数位 HALF_UP（总额 33.45 × 0.10 = 3.345）」
  「门槛差一分（99.99 < 100）」—— 拿几千块的商品**造不出**这些总额。
  所以自造 4 个价格受控的临时 SKU（100.00 / 200.00 / 99.99 / 33.45），
  跑完连商品带库存一起删掉（M1 会把 skus 与 inventories 逐行指纹比对，残留必红）。
  ★ 临时 SKU 的库存给足 1000 件 ⇒ 全程不碰真实 SKU 的库存行。

★★ 为什么边界用的券也是 SQL 直造（不走发券接口）：
  ① `rate=80` 这种「脏券」按定义就**过不了接口**（Day 21 决策 A 把 DTO 收到 1.00），
     两道防线的分工是「DTO 挡配置期输入 / calcDiscount 挡绕过接口写进来的脏数据」——
     要验后者就必须绕过前者；
  ② 已过期 / 尚未开始 / 已下架三种券**都领不到**（领券 CAS 守窗口两端），
     想拿到「我手里有一张过期券」这个状态只能直接插 user_coupons。

运行：python day21-coupon-use-verify.py
"""

import atexit
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
APP = "http://127.0.0.1:8080"
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
PSQL = [DOCKER, "exec", "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
        "-t", "-A", "-F", "|"]

PREFIX = "D21-TMP-"                # 临时券名 / 商品名统一前缀（清理靠它）
SKU_PREFIX = "D21-TMP-"            # 临时 SKU 的 sku_code 前缀
UNAME = "d21tmp1"                  # 临时 C 端用户（下单人）
PW = "d21pw123"
INTRUDER = "intruder"              # 库里已有的另一个 C 端用户 —— 用来当「别人的券」的主人

OK, VF, NF = 200, 400, 404         # 本项目 ResultCode：业务成功 = 200（不是 0）

# 临时 SKU 的价格（写死常量：所有金额期望值都由这 4 个数推出来）
P_S1, P_S2, P_S3, P_S4 = "100.00", "200.00", "99.99", "33.45"
STOCK = 1000                       # 临时 SKU 库存给足，避免与真实库存纠缠

# 满额断言条数（★ 首次跑后按报告 TOTAL 行校准）
EXPECTED = 53

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LINES = []
PASS = 0
FAIL = 0
FAILS = []


def say(line=""):
    print(line)
    LINES.append(line)


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        say("  [PASS] %s" % name)
    else:
        FAIL += 1
        FAILS.append(name)
        say("  [FAIL] %s   %s" % (name, extra))


# ---------------------------------------------------------------- DB
def sql(statement):
    r = subprocess.run(PSQL + ["-c", statement], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or "ERROR" in (r.stderr or ""):
        raise RuntimeError("psql rc=%s: %s" % (r.returncode, (r.stderr or "").strip()[:300]))
    return [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]


def sql1(statement):
    rows = sql(statement)
    if not rows:
        # ★ 空串而不是 0 行 —— 本项目的老坑：Docker 引擎自停时 psql 返回空串，
        #   脚本会崩在 int('')，看着像脚本 bug。这里显式翻译成人话。
        raise RuntimeError("psql 返回空输出 —— 多半是 Docker 引擎没起（不是脚本问题）。SQL: %s"
                           % statement)
    return rows[0]


def count(table, where="TRUE"):
    return int(sql1("SELECT count(*) FROM %s WHERE %s" % (table, where)))


# ---------------------------------------------------------------- HTTP
def api_raw(opener, method, path, token=None, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(APP + path, method=method, data=data, headers=headers)
    try:
        with opener.open(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
            st = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        st = e.code
    except Exception as e:                                        # noqa: BLE001
        return -1, None, "%s: %s" % (type(e).__name__, e)
    try:
        return st, json.loads(raw), raw
    except Exception:                                             # noqa: BLE001
        return st, None, raw


def api(method, path, token=None, body=None):
    return api_raw(_opener, method, path, token=token, body=body)


def code_of(j):
    return j.get("code") if isinstance(j, dict) else None


def data_of(j):
    return (j.get("data") if isinstance(j, dict) else None)


def login(path, username, password):
    st, j, raw = api("POST", path, body={"username": username, "password": password})
    if code_of(j) != OK:
        return None, "HTTP %s / %s" % (st, raw[:120])
    return (data_of(j) or {}).get("token"), "OK"


def wait_ready(deadline=150):
    t0 = time.time()
    while time.time() - t0 < deadline:
        st, _j, _r = api("GET", "/api/hello")
        if st != -1:
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------- 时间
def ts(dt):
    """psql 的 timestamp 字面量（不带 T，避免时区/格式歧义）。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


NOW = datetime.now()
T_PAST_START = ts(NOW - timedelta(days=365))
T_PAST_END = ts(NOW - timedelta(days=1))
T_FUT_START = ts(NOW + timedelta(days=1))
T_FUT_END = ts(NOW + timedelta(days=365))
T_OK_START = ts(NOW - timedelta(days=1))
T_OK_END = ts(NOW + timedelta(days=30))


# ================================================================ 夹具
def mk_user(username, password):
    sql("INSERT INTO users (username, password, nickname, status) "
        "VALUES ('%s', '{noop}%s', 'Day21 temp', 1)" % (username, password))
    return int(sql1("SELECT id FROM users WHERE username = '%s'" % username))


def mk_address(user_id):
    sql("INSERT INTO user_addresses "
        "(user_id, receiver_name, receiver_phone, province, city, district, detail_address, is_default) "
        "VALUES (%d, 'Day21 Temp', '13800000000', '广东省', '深圳市', '南山区', '科技园 1 号 D21', true)"
        % user_id)
    return int(sql1("SELECT max(id) FROM user_addresses WHERE user_id = %d" % user_id))


def mk_sku(index, price):
    """造 1 个临时 SKU + 1 行库存，返回 sku_id。"""
    code = "%sS%d" % (SKU_PREFIX, index)
    sql("INSERT INTO product_skus (product_id, sku_code, name, price, status, is_deleted) "
        "VALUES (%d, '%s', '%sSKU-%d', %s, 1, 0)"
        % (PRODUCT_ID, code, SKU_PREFIX, index, price))
    sid = int(sql1("SELECT id FROM product_skus WHERE sku_code = '%s'" % code))
    sql("INSERT INTO inventories (sku_id, total_stock, available_stock, locked_stock, sold_stock) "
        "VALUES (%d, %d, %d, 0, 0)" % (sid, STOCK, STOCK))
    return sid


def mk_coupon(key, type_, amount=None, rate=None, min_amount="0.00", status=1,
              start=None, end=None):
    """SQL 直造一张券（绕过发券接口 —— 边界券必须能造出「接口不许造」的状态）。"""
    cols = ["name", "type", "min_amount", "total_count", "received_count",
            "start_time", "end_time", "status"]
    vals = ["'%s%s'" % (PREFIX, key), "'%s'" % type_, min_amount, "1000", "0",
            "timestamp '%s'" % (start or T_OK_START),
            "timestamp '%s'" % (end or T_OK_END), str(status)]
    if amount is not None:
        cols.append("discount_amount")
        vals.append(amount)
    if rate is not None:
        cols.append("discount_rate")
        vals.append(rate)
    sql("INSERT INTO coupons (%s) VALUES (%s)" % (", ".join(cols), ", ".join(vals)))
    return int(sql1("SELECT id FROM coupons WHERE name = '%s%s'" % (PREFIX, key)))


def give(user_id, coupon_id, status="UNUSED"):
    """把券发到某个用户名下，返回 user_coupons.id。"""
    sql("INSERT INTO user_coupons (user_id, coupon_id, status, received_at) "
        "VALUES (%d, %d, '%s', CURRENT_TIMESTAMP)" % (user_id, coupon_id, status))
    return int(sql1("SELECT id FROM user_coupons WHERE user_id = %d AND coupon_id = %d"
                    % (user_id, coupon_id)))


def uc_triple(uc_id):
    """★ 一张券的三样同时取回来 —— 只断 status 不算验过核销/退券。"""
    return sql1("SELECT status||'|'||coalesce(order_id::text, '-')||'|'"
                "||coalesce(used_at::text, '-') FROM user_coupons WHERE id = %d" % uc_id).split("|")


def seed_cart(sku_id, qty=1):
    sql("DELETE FROM cart_items WHERE user_id = %d" % UID)
    sql("INSERT INTO cart_items (user_id, sku_id, quantity, selected) "
        "VALUES (%d, %d, %d, true)" % (UID, sku_id, qty))


ORDER_HWM = None      # ★ None = 还没读出来 —— 此时【禁止】清理（见 cleanup 的护栏）
LOG_HWM = None
PRODUCT_ID = 0
LAST_HTTP = -1        # 最近一次 place() 的 HTTP 状态码（D3 要断「协议层 200」）


def cleanup():
    """★ 按 FK 引用顺序删：先子表再父表（FK 全是 NO ACTION，顺序错了会撞约束）。
       订单族用高水位线（id > HWM）—— 只删本脚本造的，不碰历史 8 条订单。

    ★★ 护栏：水位线没读出来时【拒绝执行】。
       真实风险：`ORDER_HWM` 若还是初始值 0，那么 `DELETE FROM orders WHERE id > 0`
       会把这台机器上**全部历史订单**一起删掉（本项目一共 8 条，删了 M1 立刻红）。
       与 Day 18「骨架脚本误跑真写库」是同一类事故 —— 所以护栏要判「前提是否成立」，
       而不是「变量看起来像不像 0」。"""
    if ORDER_HWM is None or LOG_HWM is None:
        raise RuntimeError("高水位线未初始化 —— 拒绝清理（否则会连历史订单一起删）")
    sql("DELETE FROM order_items WHERE order_id IN "
        "(SELECT id FROM orders WHERE id > %d)" % ORDER_HWM)
    sql("DELETE FROM inventory_logs WHERE id > %d" % LOG_HWM)
    sql("DELETE FROM orders WHERE id > %d" % ORDER_HWM)
    sql("DELETE FROM user_coupons WHERE coupon_id IN "
        "(SELECT id FROM coupons WHERE name LIKE '%s%%')" % PREFIX)
    sql("DELETE FROM coupons WHERE name LIKE '%s%%'" % PREFIX)
    sql("DELETE FROM cart_items WHERE user_id IN "
        "(SELECT id FROM users WHERE username LIKE 'd21tmp%%')")
    sql("DELETE FROM inventories WHERE sku_id IN "
        "(SELECT id FROM product_skus WHERE sku_code LIKE '%s%%')" % SKU_PREFIX)
    sql("DELETE FROM product_skus WHERE sku_code LIKE '%s%%'" % SKU_PREFIX)
    sql("DELETE FROM products WHERE name LIKE '%s%%'" % PREFIX)
    sql("DELETE FROM user_addresses WHERE user_id IN "
        "(SELECT id FROM users WHERE username LIKE 'd21tmp%%')")
    sql("DELETE FROM users WHERE username LIKE 'd21tmp%%'")


def _safe_cleanup():
    """★ 无论脚本怎么退出（含断言崩溃、psql 异常）都尝试清一次 ——
       否则残留的临时商品/库存会让 M1 的逐 SKU 库存指纹比对当场红。"""
    try:
        cleanup()
    except Exception:                                             # noqa: BLE001
        pass


atexit.register(_safe_cleanup)


# ================================================================ main
say("=" * 78)
say("Day 21 优惠券（阶段二）验收：A 不用券原路 / B 满减核销 / C 折扣与边界")
say("                              D 归属(IDOR) / E 退券 / F 库存对账")
say("=" * 78)

say()
say("[等待应用就绪] 127.0.0.1:8080 ...")
if not wait_ready():
    say("  [FATAL] 应用 150 秒内未就绪，终止（先去看应用日志）。")
    raise SystemExit(2)
say("  应用已就绪。")

# ---------------------------------------------------------------- [0] 夹具
say()
say("-" * 78)
say("[0] 夹具：临时用户 + 地址 + 商品 + 4 个价格受控的 SKU + 库存 + 券")
say("-" * 78)

# ★ 顺序要紧：先读水位线、再清理。反过来就是「拿一个未初始化的水位线去删数据」。
ORDER_HWM = int(sql1("SELECT coalesce(max(id),0) FROM orders"))
LOG_HWM = int(sql1("SELECT coalesce(max(id),0) FROM inventory_logs"))
try:
    cleanup()                       # 清上一次跑剩下的（可重复执行的前提）
except RuntimeError as e:
    say("  [FATAL] 清理旧残留失败：%s" % e)
    raise SystemExit(2)

BASE_ORDERS = count("orders")
BASE_LOGS = count("inventory_logs")
BASE_COUPONS = count("coupons")
BASE_UC = count("user_coupons")
BASE_USERS = count("users")
say("  高水位线：orders > %d / inventory_logs > %d" % (ORDER_HWM, LOG_HWM))
say("  基线：orders=%d  inventory_logs=%d  coupons=%d  user_coupons=%d  users=%d"
    % (BASE_ORDERS, BASE_LOGS, BASE_COUPONS, BASE_UC, BASE_USERS))

UID = mk_user(UNAME, PW)
ADDR_ID = mk_address(UID)
INTRUDER_ID = int(sql1("SELECT id FROM users WHERE username = '%s'" % INTRUDER))

sql("INSERT INTO products (category_id, name, status, is_deleted) "
    "VALUES (1, '%sPROD', 1, 0)" % PREFIX)
PRODUCT_ID = int(sql1("SELECT id FROM products WHERE name = '%sPROD'" % PREFIX))
S1 = mk_sku(1, P_S1)
S2 = mk_sku(2, P_S2)
S3 = mk_sku(3, P_S3)
S4 = mk_sku(4, P_S4)

# 券：C1 满减(正常) / C2 封顶 / C3 门槛 / C4 折扣 / C5 舍入
#     C6 脏折扣率 / C7 已过期 / C8 尚未开始 / C9 已下架 / C10 别人的券 / C11 退券用
CU = {}
CU["C1"] = mk_coupon("C1-fixed20-min100", "FIXED", amount="20.00", min_amount="100.00")
CU["C2"] = mk_coupon("C2-fixed300-cap", "FIXED", amount="300.00")
CU["C3"] = mk_coupon("C3-fixed20-min100b", "FIXED", amount="20.00", min_amount="100.00")
CU["C4"] = mk_coupon("C4-discount080", "DISCOUNT", rate="0.80")
CU["C5"] = mk_coupon("C5-discount090", "DISCOUNT", rate="0.90")
CU["C6"] = mk_coupon("C6-dirty-rate80", "DISCOUNT", rate="80.00")
CU["C7"] = mk_coupon("C7-expired", "FIXED", amount="20.00",
                     start=T_PAST_START, end=T_PAST_END)
CU["C8"] = mk_coupon("C8-notstarted", "FIXED", amount="20.00",
                     start=T_FUT_START, end=T_FUT_END)
CU["C9"] = mk_coupon("C9-offline", "FIXED", amount="20.00", status=0)
CU["C10"] = mk_coupon("C10-othersbelt", "FIXED", amount="20.00")
CU["C11"] = mk_coupon("C11-returnable", "FIXED", amount="20.00")

UC = {}
for k in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C11"]:
    UC[k] = give(UID, CU[k])
UC["C10"] = give(INTRUDER_ID, CU["C10"])          # ★ 别人的券（IDOR 靶子）

TOKEN, msg = login("/api/auth/login", UNAME, PW)
check("0.1 临时用户 %s 登录成功（password 列写 {noop} 明文，不必算 BCrypt）" % UNAME,
      bool(TOKEN), msg)
check("0.2 夹具就位：4 个临时 SKU（%s/%s/%s/%s）+ 库存 %d + 11 张券 + 1 个地址"
      % (P_S1, P_S2, P_S3, P_S4, STOCK),
      count("product_skus", "sku_code LIKE '%s%%'" % SKU_PREFIX) == 4
      and count("inventories", "sku_id IN (SELECT id FROM product_skus "
                               "WHERE sku_code LIKE '%s%%')" % SKU_PREFIX) == 4
      and count("coupons", "name LIKE '%s%%'" % PREFIX) == 11
      and ADDR_ID > 0)

say()
say("  临时数据：user=%d  address=%d  product=%d  sku=%s  coupons=%s"
    % (UID, ADDR_ID, PRODUCT_ID, [S1, S2, S3, S4], sorted(CU.values())))
say("  user_coupons：%s" % sorted(UC.items()))


def place(coupon, sku, label, qty=1):
    """下一单。coupon=None 表示不用券。返回 (code, raw, order_id)；HTTP 状态放 LAST_HTTP。"""
    global LAST_HTTP
    seed_cart(sku, qty)
    body = {"addressId": ADDR_ID}
    if coupon is not None:
        body["userCouponId"] = coupon
    st, j, raw = api("POST", "/api/orders", token=TOKEN, body=body)
    oid = data_of(j) if code_of(j) == OK and isinstance(data_of(j), int) else None
    say("    %-28s coupon=%-6s sku=%-2d -> http=%s code=%s order=%s"
        % (label, coupon, sku, st, code_of(j), oid))
    LAST_HTTP = st
    return code_of(j), raw, oid


def order_amounts(oid):
    return sql1("SELECT total_amount||'|'||pay_amount||'|'||discount_amount "
                "FROM orders WHERE id = %d" % oid).split("|")


# ---------------------------------------------------------------- A 组
say()
say("-" * 78)
say("A 组 · 不用券原路（★ 本日最高优先级：M1 跑的就是这条链路）")
say("-" * 78)

USED_BEFORE = count("user_coupons", "status = 'USED'")
code, _raw, OA = place(None, S1, "A1 不用券下单")
check("A1 不带 userCouponId 下单 → code=200（老链路一个字节都没变）", code == OK,
      "code=%s" % code)

tot, pay, disc = order_amounts(OA)
check("A2 DB：discount_amount = 0.00（不是 null）且 pay == total == %s" % P_S1,
      disc == "0.00" and pay == P_S1 and tot == P_S1,
      "total=%s pay=%s discount=%s" % (tot, pay, disc))

items_sum = sql1("SELECT coalesce(sum(price*quantity),0) FROM order_items "
                 "WHERE order_id = %d" % OA)
check("A3 DB：total_amount == Σ(price×quantity)（服务端算钱，不信接口自报）",
      str(items_sum) == tot, "Σ明细=%s 订单总额=%s" % (items_sum, tot))

USED_AFTER = count("user_coupons", "status = 'USED'")
check("A4 不用券下单【完全没碰券】：status='USED' 的行数不变（%d）" % USED_BEFORE,
      USED_AFTER == USED_BEFORE, "调用后 %d" % USED_AFTER)

ident = count("orders", "pay_amount <> total_amount - discount_amount")
check("A5 ★ 恒等式全表成立：pay_amount = total_amount - discount_amount（违反 0 行）",
      ident == 0, "违反 %d 行" % ident)

# ---------------------------------------------------------------- B 组
say()
say("-" * 78)
say("B 组 · 满减券（FIXED 20 / 门槛 100）核销")
say("-" * 78)

code, _raw, OB = place(UC["C1"], S1, "B1 用 C1 满减 20")
check("B1 用满减券下单 → code=200", code == OK, "code=%s" % code)

tot, pay, disc = order_amounts(OB)
check("B2 DB：discount_amount=20.00 且 pay_amount=80.00（total − 20）",
      disc == "20.00" and pay == "80.00" and tot == "100.00",
      "total=%s pay=%s discount=%s" % (tot, pay, disc))

st_c, oid_c, used_c = uc_triple(UC["C1"])
check("B3 券行 status='USED'", st_c == "USED", "实际 %s" % st_c)
check("B4 券行 order_id = 新订单 id(%d)（不是留空、也不是别的单）" % OB,
      oid_c == str(OB), "实际 %s" % oid_c)
check("B5 券行 used_at 非空（自定义 XML 的 UPDATE 不走填充器，漏写就是 null）",
      used_c != "-", "实际 %s" % used_c)

code, _raw, OB2 = place(UC["C1"], S1, "B6 同一张券再用")
check("B6 同一张券再用 → code=400（被 markUsed 的 CAS 挡下）", code == VF,
      "code=%s" % code)
check("B7 ★ 第 6 步失败 → 订单没建成（orders 数没涨）",
      count("orders") == BASE_ORDERS + 2, "实际 orders=%d" % count("orders"))
st_c2, oid_c2, _u2 = uc_triple(UC["C1"])
check("B8 ★ 失败后被核销的那行没被改写：order_id 仍指向 B1 的订单",
      st_c2 == "USED" and oid_c2 == str(OB), "实际 %s|%s" % (st_c2, oid_c2))

# ---------------------------------------------------------------- C 组
say()
say("-" * 78)
say("C 组 · 折扣券（DISCOUNT）与四条边界")
say("-" * 78)

code, _raw, OC = place(UC["C4"], S1, "C1 rate=0.80")
tot, pay, disc = order_amounts(OC)
check("C1 rate=0.80 + 总额 100.00 → code=200", code == OK, "code=%s" % code)
check("C2 rate=0.80 → 抵扣 20.00（= total×(1−0.80)；把 0.80 读成 80 会算出负数）",
      disc == "20.00" and pay == "80.00", "discount=%s pay=%s" % (disc, pay))

code, _raw, OC2 = place(UC["C2"], S2, "C3 封顶 300>200")
tot, pay, disc = order_amounts(OC2)
check("C3 面额 300 > 总额 200 → code=200（V1.0 选封顶，不让下单失败）", code == OK,
      "code=%s" % code)
check("C4 ★ 抵扣封顶到 total：discount=200.00 且 pay_amount=0.00（绝不为负）",
      disc == "200.00" and pay == "0.00", "discount=%s pay=%s" % (disc, pay))

code, _raw, OC3 = place(UC["C5"], S4, "C5 舍入 33.45×0.10")
tot, pay, disc = order_amounts(OC3)
check("C5 总额 33.45 + rate=0.90 → code=200", code == OK, "code=%s" % code)
check("C6 ★ 抵扣 = 3.345 → 3.35（HALF_UP）而不是 3.34（BigDecimal 默认 HALF_EVEN）",
      disc == "3.35", "实际 %s（3.34 = 用了默认舍入模式）" % disc)

ORDERS_BEFORE_BAD = count("orders")
code, _raw, _o = place(UC["C6"], S1, "C7 脏券 rate=80")
check("C7 ★ rate=80 的脏券 → code=400「折扣率取值必须是 0 到 1 之间」（不许算出负数）",
      code == VF, "code=%s" % code)

code, _raw, _o = place(UC["C3"], S3, "C8 门槛差一分")
check("C8 总额 99.99 < 门槛 100 → code=400（差一分也不能用）", code == VF, "code=%s" % code)

code, _raw, _o = place(UC["C7"], S1, "C9 已过期")
check("C9 已过期的券 → code=400", code == VF, "code=%s" % code)

code, _raw, _o = place(UC["C8"], S1, "C10 尚未开始")
check("C10 ★ 尚未开始的券 → code=400（★ 靶子是 start_time 在未来的券，"
      "库里现有券全在过去 ⇒ 不造数据这条恒真）", code == VF, "code=%s" % code)

code, _raw, _o = place(UC["C9"], S1, "C11 已下架")
check("C11 券种已下架 → code=400", code == VF, "code=%s" % code)

check("C12 ★ 上面 5 个失败用例【一个订单都没建成】（抛异常 ⇒ 事务整体回滚）",
      count("orders") == ORDERS_BEFORE_BAD,
      "失败前 %d 失败后 %d" % (ORDERS_BEFORE_BAD, count("orders")))

# ---------------------------------------------------------------- D 组
say()
say("-" * 78)
say("D 组 · 归属（IDOR）—— ★ 光看状态码什么也证明不了，必须去 DB 核")
say("-" * 78)

D_BEFORE = uc_triple(UC["C10"])
code, raw_idor, _o = place(UC["C10"], S1, "D1 用别人的券")
check("D1 用【别人】的 userCouponId 下单 → code=404（伪装 404，与不存在同码同文案）",
      code == NF, "code=%s" % code)
check("D2 ★ DB：那张券【原封不动】（status/order_id/used_at 三样都没变）",
      uc_triple(UC["C10"]) == D_BEFORE)
check("D3 ★ HTTP 层是 200 —— 404 是【业务码】而不是协议码（本项目状态码混合约定；"
      "光看 HTTP 码会以为「下单成功」）", LAST_HTTP == 200, "实际 http=%s" % LAST_HTTP)

code, raw_missing, _o = place(99999999, S1, "D4 不存在的券")
check("D4 不存在的 userCouponId → code=404", code == NF, "code=%s" % code)
check("D5 ★★ 与 D1 的响应【逐字节相同】—— 这是「伪装 404」的判据："
      "两者可区分就说明 IDOR 防线有裂缝", raw_idor == raw_missing,
      "\n      IDOR  : %s\n      不存在: %s" % (raw_idor, raw_missing))

code, _raw, _o = place(UC["C1"], S1, "D6 已核销的券（归属对、状态错）")
check("D6 ★ 反向对照：自己的【已核销】券 → code=400 而不是 404"
      "（证明 404 不是「什么都报 404」）", code == VF, "code=%s" % code)

# ---------------------------------------------------------------- E 组
say()
say("-" * 78)
say("E 组 · 退券（逆向，本日含金量最高的一组）")
say("-" * 78)

code, _raw, OE1 = place(UC["C11"], S1, "E1 用 C11 下单")
check("E1 用券下单 → code=200", code == OK, "code=%s" % code)
st_c, oid_c, _u = uc_triple(UC["C11"])
check("E2 DB：下单即核销 —— status='USED' 且 order_id=%d" % OE1,
      st_c == "USED" and oid_c == str(OE1), "实际 %s|%s" % (st_c, oid_c))

st, j, _raw = api("POST", "/api/orders/%d/cancel" % OE1, token=TOKEN)
check("E3 取消该订单 → code=200", code_of(j) == OK, "http=%s code=%s" % (st, code_of(j)))

st_c, oid_c, used_c = uc_triple(UC["C11"])
check("E4 ★ 退券后 status='UNUSED'", st_c == "UNUSED", "实际 %s" % st_c)
check("E5 ★ 且 order_id IS NULL（把旧订单号擦干净，不是只改状态）",
      oid_c == "-", "实际 %s" % oid_c)
check("E6 ★ 且 used_at IS NULL（三样缺一不算退干净）", used_c == "-", "实际 %s" % used_c)

USED_BEFORE_E7 = count("user_coupons", "status = 'USED'")
code, _raw, OE2 = place(UC["C11"], S1, "E7 退回来的券再用一次")
st_c, oid_c, _u = uc_triple(UC["C11"])
check("E7 ★ 退回来的券能再次使用 → code=200", code == OK, "code=%s" % code)
check("E8 ★ 且 order_id 指向【新】订单 %d（不是旧订单 %d）" % (OE2, OE1),
      oid_c == str(OE2) and OE2 != OE1, "实际 %s" % oid_c)
say("    （E7 前 USED 行数 = %d）" % USED_BEFORE_E7)

code, _raw, OE3 = place(None, S1, "E9 不用券下单（为退款对照）")
USED_BEFORE_CANCEL = count("user_coupons", "status = 'USED'")
st, j, _raw = api("POST", "/api/orders/%d/cancel" % OE3, token=TOKEN)
check("E9 ★ 反向对照：不用券的订单取消 → code=200"
      "（退券 0 行是常态，不许当失败 —— 当成失败 M1 当场红）",
      code_of(j) == OK and code == OK, "下单 code=%s 取消 code=%s" % (code, code_of(j)))
check("E10 ★ 取消【没用券】的订单不会误动别人的券：USED 行数不变（%d）"
      % USED_BEFORE_CANCEL,
      count("user_coupons", "status = 'USED'") == USED_BEFORE_CANCEL,
      "取消后 %d" % count("user_coupons", "status = 'USED'"))

st, j, _raw = api("POST", "/api/orders/%d/cancel" % OE3, token=TOKEN)
check("E11 同一张订单重复取消 → code=400（CAS 抢不到，且不会再退一次券）",
      code_of(j) == VF, "http=%s code=%s" % (st, code_of(j)))

# ---------------------------------------------------------------- F 组
say()
say("-" * 78)
say("F 组 · 库存对账（锁定量 = 未取消订单占用的件数）")
say("-" * 78)

bad = int(sql1("SELECT count(*) FROM inventories WHERE sku_id IN "
               "(SELECT id FROM product_skus WHERE sku_code LIKE '%s%%') "
               "AND (available_stock + locked_stock + sold_stock <> total_stock "
               "     OR total_stock <> %d OR available_stock < 0)" % (SKU_PREFIX, STOCK)))
check("F1 ★ 4 个临时 SKU 的库存守恒：available+locked+sold==total 且 total 未被改动",
      bad == 0, "违例行数 %d" % bad)

locked = int(sql1("SELECT locked_stock FROM inventories WHERE sku_id = %d" % S1))
expect_locked = int(sql1(
    "SELECT coalesce(sum(oi.quantity),0) FROM order_items oi "
    "JOIN orders o ON o.id = oi.order_id "
    "WHERE oi.sku_id = %d AND o.status = 'PENDING_PAYMENT'" % S1))
check("F2 ★ S1 的 locked_stock(%d) == 未取消订单占用的件数(%d) —— 取消要真的回补库存"
      % (locked, expect_locked), locked == expect_locked)

ident = count("orders", "pay_amount <> total_amount - discount_amount")
check("F3 ★ 恒等式全表成立（收尾再断一次：整轮的写入都没破坏它）", ident == 0,
      "违反 %d 行" % ident)

# ---------------------------------------------------------------- G 组
say()
say("-" * 78)
say("G 组 · 清理（高水位线 + 前后缀，跑完回基线）")
say("-" * 78)

cleanup()
check("G1 临时券已删干净（残留 %d 张）" % count("coupons", "name LIKE '%s%%'" % PREFIX),
      count("coupons", "name LIKE '%s%%'" % PREFIX) == 0)
check("G2 临时商品/SKU/库存已删干净（残留 SKU %d 个）"
      % count("product_skus", "sku_code LIKE '%s%%'" % SKU_PREFIX),
      count("product_skus", "sku_code LIKE '%s%%'" % SKU_PREFIX) == 0
      and count("products", "name LIKE '%s%%'" % PREFIX) == 0)
check("G3 临时用户/地址/购物车已删干净（残留用户 %d 个）"
      % count("users", "username LIKE 'd21tmp%%'"),
      count("users", "username LIKE 'd21tmp%%'") == 0
      and count("cart_items", "user_id NOT IN (SELECT id FROM users)") == 0)
check("G4 ★ 订单族回基线：orders=%d、inventory_logs=%d（都是本脚本开始时的值）"
      % (BASE_ORDERS, BASE_LOGS),
      count("orders") == BASE_ORDERS and count("inventory_logs") == BASE_LOGS,
      "实际 orders=%d logs=%d" % (count("orders"), count("inventory_logs")))
check("G5 券族回基线：coupons=%d、user_coupons=%d" % (BASE_COUPONS, BASE_UC),
      count("coupons") == BASE_COUPONS and count("user_coupons") == BASE_UC,
      "实际 %d / %d" % (count("coupons"), count("user_coupons")))
check("G6 users 回基线 %d（临时用户已删）" % BASE_USERS, count("users") == BASE_USERS,
      "实际 %d" % count("users"))

# ---------------------------------------------------------------- 汇总
say()
say("=" * 78)
say("TOTAL: PASS=%d  FAIL=%d   （期望断言数 %d）" % (PASS, FAIL, EXPECTED))
if PASS + FAIL != EXPECTED:
    say("[FAIL] 断言总数与 EXPECTED 不符 —— 有断言被静默跳过，或 EXPECTED 需要校准！")
    FAILS.append("ASSERTION COUNT MISMATCH (actual %d, expected %d)" % (PASS + FAIL, EXPECTED))
say("VERDICT: %s" % ("OK 全绿" if FAIL == 0 else ("FAILED -> " + "; ".join(FAILS))))
say("=" * 78)
say("下一步：python day17-m1-regression.py --baseline → 三条 E2E → 不带参数再跑一次（期望 198/198）")

with open(os.path.join(HERE, "day21-coupon-use-verify-report.txt"), "w",
          encoding="utf-8") as f:
    f.write("\n".join(LINES) + "\n")

raise SystemExit(0 if FAIL == 0 else 1)
