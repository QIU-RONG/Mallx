# Day 43 · 前端全栈联调（两个 dev server + 一个后端）

> 产出：`backend/loadtest/day43-fe-full-stack-e2e.py`（54 条断言，含对照组）+ 本报告。
> 结果：**54 通过 / 0 失败**；跑完复跑 M1 收集器 → **245/245 OK，(c) 数据库回基线 YES**。

---

## 一、为什么还要单独做一次

FE1–FE3 的验收是**分端**做的：mall-app 单独跑通、admin-app 单独跑通。
「各自能跑」与「合起来能跑」是两件事，中间至少隔着三层：

| 层 | 分端验收覆盖到了吗 | 全栈联调覆盖 |
|---|---|---|
| 两个 dev server 同时在跑、端口不打架 | ❌（从没同时起过） | ✅ |
| Vite dev proxy `/api → 8080` 的配置 | 各自验过一次 | ✅ 两个代理一起验 |
| **前端真正依赖的字段名** | ❌（脚本按后端视角写断言） | ✅ 以**前端自己的类型定义**为准 |
| 跨端状态流转（C 端支付的单，管理端能不能发） | ❌ | ✅ 同一张单跨两个应用走完 |
| 权限是否按【端】分开 | 各自验过 | ✅ A 端 token 打 B 端接口 |

```
                 ┌──────────────────┐        ┌──────────────────┐
       浏览器 →  │ mall-app  :5173  │        │ admin-app :5174  │
                 └────────┬─────────┘        └────────┬─────────┘
                          │  /api（Vite dev proxy）    │
                          └────────────┬──────────────┘
                                       ▼
                            mall-server :8080  →  PostgreSQL :5434
```

★ 全部请求都打**代理**，不直连 8080。这样每条断言同时覆盖：代理配置 + 接口契约 +
**前端会用到的那几个字段名**。直接打 8080 只能证明后端对，证明不了「前端接得上」。

---

## 二、跨端链路（同一张订单走完两个应用）

本次跑出的订单（跑完已删）：

```
C 端(5173)  加购 SKU4 → 改数量 → 勾选 → 下单 → 支付(ALIPAY)
            ↓ DB: PENDING_PAYMENT → PAID，paid_at 写入，available −1
管理端(5174) admin 登录 → 订单列表看到这张单 → 读详情 → 发货
            ↓ DB: SHIPPED，shipped_at 写入
C 端(5173)  确认收货 → 评价（只传 orderItemId）
            ↓ DB: COMPLETED，completed_at 写入；reviews +1，order_id/product_id 由后端反查
```

沿途的**反向对照**（证明状态机真的在把关，不是「什么都能过」）：

| 动作 | 期望 | 实测 |
|---|---|---|
| 重复发货 | 拒 | code != 200 ✅ |
| 已发货再取消 | 拒 | code != 200 ✅ |
| 同一 `orderItemId` 重复评价 | 拒 | code != 200 ✅ |
| 匿名读他人订单 | 拒 | code != 200 ✅ |
| 错误密码登录 | 拒 | code != 200 ✅ |
| C 端 token 打 `/api/admin/roles` | 拒 | **HTTP 403** ✅ |
| ★ 管理端 token 打同一接口（正向对照） | 通 | 200 ✅ |

> ⚠️ 一条「记录但不判定」的观察：**管理端 token 打 C 端 `/api/cart` 返回 200**。
> 这属于设计外用法（C 端接口把 principal 当 userId，管理端的 principal 是 adminId），
> 本项目既没规定也没禁止。**记录在案，不预设结论** —— 要判定得先有设计决定。

---

## 三、54 条断言分布

| 段 | 内容 | 条数 |
|---|---|---|
| 1 | 两个 dev server 都返回可挂载的 HTML | 2 |
| 2 | 后端经**两个**代理都可达 | 2 |
| 3 | C 端登录成功 / 错误密码被拒 | 2 |
| 4 | 商品列表与详情，及**前端 ProductVO / SkuVO 必需的字段** | 5 |
| 5 | 购物车 → 下单 → 支付（含 DB 状态、金额恒等式、库存锁定） | 14 |
| 6 | 管理端看到该单 + 发货（含状态机反向对照） | 7 |
| 7 | C 端收货 + 评价（含反查校验与重复评价拒绝） | 8 |
| 8 | 跨端权限对照（含正向对照） | 4 |
| 9 | 账目对账（支付流水、库存三分量、评价数） | 6 |
| 10 | 清理与基线还原 | 3 |
| | **合计** | **54** |

---

## 四、这次踩到的三个坑 —— 全都是「我以为」而不是「事实」

### 坑 1 · 我以为商品列表有 `price`

第一版断言 `列表项带 id/name/price` ⇒ **FAIL**。
查 `ProductVO`（后端）与 `frontend/mall-app/src/types/api.d.ts`（前端）：**列表 VO 里没有价格** ——
价格挂在 SKU 上，列表页并不显示价格。

⇒ 修法不是「把断言删掉」，而是**以前端自己的类型定义为准**重写：
列表断言 `id/name/status`，详情断言 `skus[].id/price`。

> ★ 这正是「经代理、按前端契约断言」的价值所在：直接打 8080 只会验后端对不对，
> **验不出「前端拿到的字段名对不对」**。

### 坑 2 · 我以为同义字段同名

`SELECT pay_amount FROM payments` ⇒ `ERROR: column "pay_amount" does not exist`。
`payments` 的金额列叫 **`amount`**；`pay_amount` 是 **`orders`** 上的列。
⇒ 列名以 `backend/sql/01-schema.sql` 为准，不按「语义相同就该同名」猜。

### 坑 3 · 我以为 `numeric` 能 `int()`

`int(row["total"])` ⇒ `ValueError: invalid literal for int() with base 10: '6999.00'`。
psql 回的是定点字符串。⇒ 金额一律走 `Decimal(str(x))` 比较。

### 附带的第二个设计教训：清场之外还得留证据

坑 3 那次异常**冒出了 `try`**，`finally` 把场清干净了，但脚本随即崩溃 ——
**已经跑过的 40 多条断言连同整份报告一起丢了**（报告文件根本没生成）。
⇒ 补一层 `except Exception`：记录异常 + `chk(..., False)`，**保证报告一定落盘**。
**清场很重要，但「把发生过什么留下证据」同样重要。**

### 还有一条关于「数数」的

`EXPECTED_CHECKS` 我连错两次：第一版按「chk 调用行数」写了 40，于是 **54/0 全过也判 FAIL**；
第二版静态减掉「不会执行的分支」又漏了**循环里执行两次**的那两条（两个 dev server、两个代理）。
⇒ 最终 **54**。**这类数字要对着实跑报告核，不要对着源码数** ——
写死它的意义是防「断言没被创建」的假绿，写错了就反过来制造假红。

---

## 五、复现步骤

```bash
# ① 起后端（宿主 java，默认 profile）
cd backend/mallx/mall-server/target
java -Xmx384m -XX:MaxMetaspaceSize=160m -jar mall-server-0.0.1-SNAPSHOT.jar --server.port=8080

# ② 起两个 dev server（不同终端）
cd frontend/mall-app  && npm run dev      # :5173
cd frontend/admin-app && npm run dev      # :5174

# ③ 夹具 + 联调 + 复跑 M1 证明基线没被破坏
cd backend/loadtest
python day26-m1-fixture.py
python day43-fe-full-stack-e2e.py         # 判定看退出码
python day17-m1-regression.py --baseline
python day14-e2e-walk.py && python day15-ship-confirm.py && python day16-review-e2e.py
python day17-a-order-list-verify.py && python day17-b-order-detail-verify.py
python day17-m1-regression.py
```

★ 两个本机专属前提（都在脚本 docstring 里写明了）：
**Vite 8 dev 只绑 localhost（IPv6）** ⇒ 必须用 `localhost`，`127.0.0.1` 拿到 000；
**系统代理会拦 localhost** ⇒ 脚本内用 `ProxyHandler({})` 显式绕过，否则 502 假故障。

---

## 六、下一步

- **可以把它排进 CI 了**：FE4 当时说的是「前端 e2e 等出现一次真实契约回归再上」——
  本次坑 1 就是那个信号（前端依赖的字段名与后端返回不一致，编译期查不出来）。
  代价是 `ci` job 要额外装 node + 起两个 dev server（约 +2 分钟），本次先不加大 CI 时长。
- 管理端 token 打 C 端接口返回 200 这件事，值得补一条**设计决定**（允许 / 禁止），
  否则它会一直停在「记录在案」的状态。
