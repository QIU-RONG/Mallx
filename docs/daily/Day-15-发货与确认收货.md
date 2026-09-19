# Day 15 — 发货与确认收货：把状态机走完（里程碑 M1 闭环）

> **一句话**：Day 13 让订单走到 `PAID`，Day 14 补了「往后退」的取消边。
> Day 15 把正向剩下的两条边走完：`PAID --发货--> SHIPPED --确认--> COMPLETED`，
> 与 Day 16 的评价一起构成里程碑 **M1「下单 → 支付 → 收货 → 评价」闭环**。
>
> **前置**：Day 14 收官 ✅（取消 34/34、超时 22/22、流水 61/61、库级对账 28/28、端到端 A/B 67/67）。
> **路线依据**：`Day-12-从购物车下单.md:1024` 的里程碑图已排定 `Day 15/16 评价 → 里程碑 M1`；
> `OrderStatus.java:12` 的状态机注释早已画出这两条边；
> `Day-14-订单状态机.md:815` 的「本日不做」表把它们明确划给 **Day 15–16**。

---

## 〇、开工前的四件事（★ 先看这一节）

### 0.1 事实盘点（2026-09-19 实查）

| 项 | 现状 |
|---|---|
| `orders` | **8 行**（5 `PAID` + 3 `CANCELLED`）—— ★ 与 Day 14 相反，**这次有现成的 `PAID` 靶子** |
| `payments` | 5 行 |
| `order_items` | 9 行 |
| `inventories` | 7 SKU 恒等式全成立、**业务守恒 0 漂移**（= §0.3 基线） |
| `inventory_logs` | 0 行（Day 14 收官时清空） |
| `reviews` | **0 行** —— Day 03 建表至今一次没写（Day 16 用） |
| 序列 | `orders_id_seq = 9031`、`payments_id_seq = 197`（★ 比摸底时的 9028/195 大 —— Day 14 收官后又跑了两轮端到端走查。序列不回滚，有空洞是正常的，**不要拿序列当基线断言**） |
| 账号 | `demo/demo123`(id=1)、`intruder/intruder`(id=2)、`admin/admin123`(id=1) |
| **已预埋未用** | `OrderStatus.SHIPPED`/`COMPLETED` 常量、`orders.shipped_at`/`completed_at` 列、权限 `order:ship`、角色 `ORDER_ADMIN` |
| **DDL** | **本日零 DDL** —— 常量、列、权限、角色在 Day 03 就齐了 |

★ 对比 Day 14 §0.1 的抱怨（「一张待支付都没有，取消这一步没有现成靶子」），
本日**运气相反**：5 张 `PAID` 单就摆在那里。但见 §0.3 —— **恰恰不该用它们**。

### 0.2 ★★ 发现：状态机每长一条边，对账口径就要回头改一次

Day 14 §0.2 的教训是「**算术守恒 ≠ 业务守恒**」，并据此定下两条业务守恒式：

```
locked == Σ(PENDING_PAYMENT 订单明细)     ← 在途锁
sold   == Σ(PAID 订单明细)                 ← 已售
```

**今天第二条要失效了。** 原因：发货**不改库存**（`sold` 仍是 `sold`），
但订单状态从 `PAID` 变成 `SHIPPED` —— 于是它从 `Σ(PAID)` 里**掉出去了**。

实测当前 5 张 `PAID` 单撑起 `sold`：

| 订单 | 状态 | 明细 |
|---|---|---|
| #1 | PAID | sku3×2, sku4×1 |
| #2 | PAID | sku5×3 |
| #9002 | PAID | sku3×2 |
| #9004 | PAID | sku4×1 |
| #9005 | PAID | sku4×1 |

对账：sku3 `sold=4 = 2+2` ✅、sku4 `sold=3 = 1+1+1` ✅、sku5 `sold=3 = 3` ✅。

**现在把 #1 发出去**（sku3×2 + sku4×1，只是状态变 `SHIPPED`、库存一格不动）：

| SKU | `sold` 现值 | `Σ(PAID)` 发货后 | 漂移 |
|---|---|---|---|
| 3 | 4 | 2 | **+2** |
| 4 | 3 | 2 | **+1** |

→ **对账立刻报漂移，而这纯粹是口径过时造成的假警报。**

**只读证明**（不动物件，纯查询模拟「假设 #1 已发货」）：

| sku | `sold` | 旧口径 | 新口径 | 旧口径漂移（现在） | 新口径漂移（现在） | 旧口径漂移（假设 #1 已发货） |
|---|---|---|---|---|---|---|
| 3 | 4 | 4 | 4 | 0 | 0 | **+2** |
| 4 | 3 | 3 | 3 | 0 | 0 | **+1** |
| 5 | 3 | 3 | 3 | 0 | 0 | 0 |

★ 关键：**今天两个口径都是 0 漂移** —— 所以这次改口径是**安全的空操作**；
   但一旦有订单发货，旧口径立刻报假漂移。

★★ 所以本日必须**同时升级对账口径**：

```
sold == Σ(状态 ∈ {PAID, SHIPPED, COMPLETED} 的订单明细)
```

**真正的教训**（比 Day 14 那条更进一步）：

> Day 14 学会「恒等式 ≠ 业务守恒」；
> Day 15 要学的是「**业务守恒式本身会随状态机长大而失效**」——
> 状态机每加一条边，都要回头把对账口径重推一遍，
> 否则下一次审计报出来的「漂移」是**口径过时**，不是数据出错。

### 0.2.1 已完成的修正（改的是 `backend/loadtest/`，不是生产代码）

★ 摸底时以为只有 2 个文件，**实际是 7 个**（旧口径散得很开）：

| 文件 | 处数 | 性质 |
|---|---|---|
| `day14-recalibrate.sql` | 4 | 基线校准（含「应然值」定义） |
| `day14-restore.sql` | 3 | 实验后无条件归位 |
| `day14-cleanup.sql` | 1 | 漂移检查 |
| `day14-step5-cleanup.sql` | 1 | 漂移检查 |
| `day14-cancel-verify.py` | 1 | 漂移检查 |
| `day14-cancel-vs-pay.py` | 1 | 漂移检查 |
| `day14-e2e-walk.py` | 1 | 漂移检查 |

改法：`o.status = 'PAID'` → `o.status IN ('PAID','SHIPPED','COMPLETED')`，共 **12 处**，
并在两个 SQL 头与四处漂移查询旁补了口径说明。
★ **未误伤** 5 处「挑一张 `PAID` 单当靶子」的写法（`WHERE status='PAID'` / `SET status='PAID'`，
不带 `o.` 前缀）—— 那几处要的恰恰是「还没发货的已支付单」，不能改。
★ `day15-ship-confirm.py` 里刻意**保留**旧口径，用来做新旧对照。

**回归验证**：`day14-e2e-walk.py` 改后仍 **67/67**。

### 0.2.2 ★ 顺带发现的第二个问题：账本为空时，审计「失明」

回归时 `day14-reconcile.py` 报 **26/27**（Day 14 文档里写的是 28/28）。查下来**不是口径改动引起的**
（该脚本我一个字节都没碰），而是**收官清理把账本清空了**。

根因在审计 SQL 的回退写法：

```sql
COALESCE(f.before_stock, i.available_stock) + COALESCE(f.sum_change, 0) = i.available_stock
```

账本为空时 `f` 全为 NULL → 期望值退化成**现值本身** → **审计永远自洽**，
第 [4] 节那个「绕过服务做裸 UPDATE，审计应当报警」的**牙齿测试必然假失败**。

★★ 也就是说：**Day 14 收官之后，文档里的「28/28」是不可复现的** ——
收官清理清空了账本，同时也卸掉了审计的牙齿。

**修法**：让牙齿测试**先做一次合法变动给账本打底**（库存与流水同时改），
再做裸 UPDATE。这样账本空不空都能测出牙齿。
修后 **27/27 全绿**，且报告里能直接看到 `VERDICT: false`（审计确实报警了）。

★ 附注：断言总数是**数据依赖**的（账本非空时多一条 `has_ledger` 断言 → 28；
空时 27）。两种状态都全绿 —— 引用这个数字时要带上账本状态，否则会像「退步了」。


### 0.3 靶子怎么选：**不要动那 5 张历史 `PAID` 单**

它们现成、可直接发货，但它们是 §0.3 基线里 `sold = 4/3/3` 的**唯一证据**。
把它们发出去，基线就被自己毁了（而且 §0.2 的假漂移会立刻出现）。

→ 与 Day 14 端到端走查一致：**走 API 新建一张单**（下单 → 支付 → 发货 → 确认），用完自清。

### 0.4 ★★ 开工前的机制实证（2026-09-19 实测，用的都是**已有**端点）

本日最有价值的断言是「C 端 token 打 ship 必得 **403**」。
这条完全依赖 Day 07 的 RBAC 机制 —— 所以**不用等代码写完**，
现在就能拿已有的商品写接口（`ProductController` 的 `@PreAuthorize`）把它验掉。

**实验**：对 `POST /api/products`（挂了 `@PreAuthorize("hasAuthority('product:create')")`）分别发三种请求：

| 请求 | 期望 | **实测** |
|---|---|---|
| 不带 token（匿名） | 401 | ✅ **HTTP 401** |
| demo 的 C 端 token | 403 | ✅ **HTTP 403** |
| admin 的管理端 token | 放行 | ✅ **HTTP 200** |

★ 三种结果全中 —— **说明 401/403 两个出口都是通的，本日不需要动 `GlobalExceptionHandler`**。

**为什么不用动**：Day 07 就已经为 `AccessDeniedException` 单独接了出口
（`GlobalExceptionHandler.java:99`），注释写明了不接的后果：

> `AccessDeniedException` 是 `RuntimeException` 的子类，本来会被 `handleException(Exception)`
> 先兜走 —— 结果 `@PreAuthorize` 拒绝反而返回 **200 + code=500**，403 永远出不来。

且它按「身份是否成立」分流：匿名 → 401、已认证但权限不够 → 403。
→ **本步只写业务代码，安全层零改动。**（这条要写进对照清单的「不要动」列。）

**★★ 顺带把 §3.3 的陷阱从推理变成了证据** —— 把两个 token 的 payload 解开看：

| token | payload（节选） | principal |
|---|---|---|
| demo（C 端） | `{"sub":"1","username":"demo","type":"USER"}` —— **没有 `perms` 字段** | `1L` |
| admin（管理端） | `{"sub":"1","username":"admin","type":"ADMIN","perms":["order:list","order:ship",...,"ROLE_SUPER_ADMIN"]}` | `1L` |

两个铁证：
1. C 端 token **确实没有 `perms`** → 权限集为空 → 一挂 `@PreAuthorize` 就 403（设计前提成立）；
2. **`sub` 都是 `"1"`** → 过滤器只把 `sub` 转 `Long` 当 principal，**无视 `type` 字段** →
   管理端 admin 与 C 端 demo 的 principal **数值相同、类型相同，无法区分**。
   §3.3 那条「不要把 principal 当发货人」不是假想，是**必然撞号**。

★ 附注：admin token 里 `order:ship` 明确在列（`perms` 第 2 项）—— 第 1 步的 RBAC 链路**上游已就绪**。

---

## 一、全景：3 步

| 步 | 内容 | 新增技术点 | 产物 |
|---|---|---|---|
| **1** | **发货** `POST /api/orders/{id}/ship` | ★ **全项目第一个真用 RBAC 的业务端点**（admin token）+ CAS `WHERE status='PAID'` | 1 方法 + 1 XML + 1 端点 |
| **2** | **确认收货** `POST /api/orders/{id}/confirm` | C 端动作 + CAS `WHERE status='SHIPPED'` + `requireOwn` 归属分流 | 1 方法 + 1 XML + 1 端点 |
| **3** | 端到端闭环 + **对账口径升级** + 收官 | —— | 验收脚本 + 改 2 处旧口径 + 文档 |

★ 与 Day 14 最大的不同：**本日两条边都不碰库存**。
发货与收货是**物流状态**，「货」的归属在支付那一刻（`locked → sold`）就已经定死了。
所以两条边都是**单条 UPDATE**，与 `markPaid` 同构，**都不需要 `@Transactional`**。

---

## 二、状态机：本日补完正向

```
                     ┌──────────────────┐
   下单 createFromCart │ PENDING_PAYMENT  │
                     └────────┬─────────┘
              ┌───────────────┼───────────────┐
              │ 支付           │               │ 取消 / 超时
              │ CAS:          │               │ CAS:
              │ PENDING_PAYMENT│              │ PENDING_PAYMENT
              ▼               │               ▼
      ┌──────────┐            │        ┌────────────┐
      │   PAID   │            │        │ CANCELLED  │
      └────┬─────┘            │        └────────────┘
           │ 发货 ★本日新增      │              │ 库存:
           │ CAS: PAID        │              │ locked → available
           │ 库存: 无           │              ▼
           ▼                  │        ┌──────────────┐
      ┌──────────┐            │        │ 货回到可售池  │
      │ SHIPPED  │            │        └──────────────┘
      └────┬─────┘            │
           │ 确认收货 ★本日新增  │
           │ CAS: SHIPPED      │
           │ 库存: 无           │
           ▼                   │
      ┌───────────┐            │
      │ COMPLETED │            │
      └───────────┘            │
```

★ 本日新增只有**两条**：`PAID → SHIPPED` 与 `SHIPPED → COMPLETED`。

### 2.1 五条边的全貌（Day 13–15 合起来才完整）

| 边 | 触发者 | 起点 → 终点 | CAS 条件 | 库存副作用 |
|---|---|---|---|---|
| 支付 | 用户 | `PENDING_PAYMENT → PAID` | `status='PENDING_PAYMENT'` | `locked → sold` |
| 取消 | 用户 | `PENDING_PAYMENT → CANCELLED` | `status='PENDING_PAYMENT'` | `locked → available` |
| 超时 | **系统** | `PENDING_PAYMENT → CANCELLED` | 同上 + `created_at` | `locked → available` |
| **发货** | **管理员** | `PAID → SHIPPED` | `status='PAID'` | **无** |
| **确认** | 用户 | `SHIPPED → COMPLETED` | `status='SHIPPED'` | **无** |

★★ **读法**：前三条边的 CAS 条件**完全相同**（`PENDING_PAYMENT`），所以它们互相排斥、
只有一个能赢；后两条边的条件**各不相同**，所以只能**按顺序**发生。
「同一个状态位被多条边争抢」与「多条边各管一段」—— 这两种结构合起来才叫状态机。

---

## 三、第 1 步：发货（要点）

### 3.1 ★★ 本步真正的看点：第一个真用 RBAC 的业务端点

项目里 Day 07 就建好了 RBAC（角色 / 权限 / `@PreAuthorize`），但到目前为止，
**它只在商品写接口上用过**。C 端的三个控制器（`OrderController` / `CartController` /
`PaymentController`）**都刻意不挂 `@PreAuthorize`**，类注释写明了原因：

> C 端 token 的**权限集是空的**（没有 `perms` claim），一挂就 403。

发货不一样 —— 它是**管理员动作**。所以本步要把这条线第一次走通：

```
admin 登录 (/api/auth/admin/login)
   → token 里带 perms: [..., order:ship, ROLE_ORDER_ADMIN]
   → JwtAuthenticationFilter 把 perms 还原成 authorities
   → @PreAuthorize("hasAuthority('order:ship')") 放行
```

而 C 端 token 打同一个端点 → 权限集为空 → **403**。
**这就是 Day 07 RBAC 的首次业务验证**，也是本步最有价值的断言。

★ 这条链路已在 §0.4 用**已有的**商品写接口实测通过（401 / 403 / 200 三态全中），
  且确认 **`GlobalExceptionHandler` 无需改动** —— 本步只写业务代码。

### 3.2 端点放哪：三个方案

权限 seed（`03-data.sql:140`）已经把路径**定死**了：

```sql
(7, '订单发货', 'order:ship', 'API', '/api/orders/*/ship', 'POST')
```

所以路径只能是 `POST /api/orders/{id}/ship`。剩下的是**放哪个类**：

| 方案 | 做法 | 评价 |
|---|---|---|
| **A（采用）** | 放进现有 `OrderController`，**方法级**挂 `@PreAuthorize` | 与权限 seed 路径一致、零新文件；代价是同一个类里出现两种鉴权模型，**必须改类注释说清楚** |
| B | 新建 `AdminOrderController` 映射同一个 `/api/orders` 前缀 | 鉴权模型分得更干净；但要额外解释「为什么两个类映射同一前缀」 |
| C | 改权限 seed 路径为 `/api/admin/orders/*/ship` | ✗ 违背 Day 03 的既定设计，还要改 seed |

★ 选 **A**，因为 `@PreAuthorize` 天生是**方法级**的，「同类不同权限」是它支持的正常用法。
但要把类注释从「本类刻意不挂 `@PreAuthorize`」改成
「本类**默认**不挂（C 端），**唯独 `ship` 例外 —— 它是管理端动作**」。

### 3.3 ★★ 陷阱：不要把 principal 当成「发货人」

`JwtAuthenticationFilter` 只做两件事：把 `sub` 转成 `Long` 当 **principal**、把 `perms` 还原成 **authorities**。
它**完全忽略** token 里的 `type:"ADMIN"` claim（`JwtUtil.generateForAdmin` 明明签了它）。

后果：

| token | `sub` | principal | authorities |
|---|---|---|---|
| C 端（demo） | `1` | `1L` | 空 |
| 管理端（admin） | `1` | `1L` | `[order:ship, ROLE_SUPER_ADMIN, ...]` |

★★ **两者 principal 数值相同、类型相同，无法区分。**
所以「发货人是谁」这个问题，**靠 principal 是答不出来的** ——
若把 `(Long) authentication.getPrincipal()` 当成发货管理员 id 存进审计字段，
它会和 `userId=1` 的 demo **撞成同一个值**。

→ 本步的设计决定：**`ship` 方法既不接收也不读取 principal**。
发货端点只需要「有没有 `order:ship` 权限」这一个信息，不需要知道是哪个管理员。
（真要审计「谁发的货」，得先给 filter 加上区分 user/admin 的能力 —— 那是独立的一步，本日不做。）

### 3.4 改动清单（2 新 + 3 改，另 2 处注释/import —— 详见 §8.1）

| 文件 | 改动 |
|---|---|
| `OrderMapper.java` | 新增 `int shipOrder(@Param("orderId") Long orderId)` |
| `OrderMapper.xml` | 新增 `<update id="shipOrder">`，CAS `WHERE status='PAID'`，写 `shipped_at` + `updated_at` |
| `OrderService.java` | 新增 `void ship(Long orderId)`（**不带 userId**，见 §3.3） |
| `OrderServiceImpl.java` | 实现：0 行 → 400「订单状态不允许发货」；**不加 `@Transactional`** |
| `OrderController.java` | 新增 `@PostMapping("/{id}/ship")` + `@PreAuthorize("hasAuthority('order:ship')")`；改类注释 |

★ **0 行报 400 而不是 500**：与 `markPaid` / `cancelOrder` 同一个口径 ——
「订单不是已支付状态」是用户/管理员可理解的正常结果（可能刚被取消、或已经发过货了），
不是服务端账目不一致。★ 也**不是 404**：发货不校验归属，订单存不存在由 CAS 的 0 行统一表达。

⚠️ `shipped_at` 必须**手写**在 SQL 里：自定义 XML 的 UPDATE 不走 `MetaObjectHandler`，
`updated_at` 同理（Day 13/14 都踩过这个坑，`OrderMapper.xml` 里有注释）。

---

## 四、第 2 步：确认收货（要点）

### 4.1 与「取消」是同构的：都要 `requireOwn`

确认收货是**用户动作**，所以必须做**写操作的 IDOR 防线** —— 与 Day 14 的 `cancel` 完全一致：

```
① 归属分流  requireOwn(userId, orderId)   → 不是自己的与不存在的，同一个 404
② 状态 CAS  confirmReceipt(orderId)        → 0 行 400
```

★ 为什么 ① 必须在 ② 之前：与取消同一个理由 —— ② 的 `WHERE` 里**不带 `user_id`**，
否则「不存在 / 不是你的 / 状态不对」三种 0 行原因会重新糊在一起，
上层就没法把它稳定地翻成「400 状态不允许确认收货」。

### 4.2 改动清单（2 新 + 3 改 —— 详见 §8.2）

| 文件 | 改动 |
|---|---|
| `OrderMapper.java` | 新增 `int confirmReceipt(@Param("orderId") Long orderId)` |
| `OrderMapper.xml` | 新增 `<update id="confirmReceipt">`，CAS `WHERE status='SHIPPED'`，写 `completed_at` + `updated_at` |
| `OrderService.java` | 新增 `void confirm(Long userId, Long orderId)` |
| `OrderServiceImpl.java` | 实现：`requireOwn` → 0 行 → 400；**不加 `@Transactional`** |
| `OrderController.java` | 新增 `@PostMapping("/{id}/confirm")`，**不挂** `@PreAuthorize`（C 端） |

### 4.3 ★ 一个「不写」的决定：收货**不写流水**

Day 14 给三个**库存**写点各加了一条 `inventory_logs` 流水。
本步两条边**都不碰库存**，所以**一条流水都不写**。

★ 这不是偷懒：`inventory_logs` 记的是「**库存发生过什么**」。
发货和收货对库存的贡献是 **0**（货早在支付时就 `locked → sold` 了），
硬塞一条 `change_quantity = 0` 的行，只会让「账本能解释现值」这个性质变脏
（Day 14 §11 的 `PAY_SOLD change == 0` 是**支付**这条边真的碰了 `locked`，才需要留痕）。

→ 结论：**本步零库存写入、零流水**。订单状态的变化由 `orders.status` + 时间戳记录，
这才是它该待的地方。

---

## 五、第 3 步：端到端 + 口径升级 + 收官（要点）

1. **端到端闭环**：下单 → 支付 → **发货** → **确认收货** → 逐段查状态与时间戳
2. **越权与顺序断言**：C 端 token 打 ship（403）、匿名打 ship（401）、
   `PENDING_PAYMENT` 直接 ship（400）、`PAID` 直接 confirm（400）、
   重复 confirm（400）、IDOR confirm（404）
3. ✅ **对账口径升级（已完成，见 §0.2.1）**：把 `sold` 的守恒式从 `Σ(PAID)` 改成
   `Σ(状态 ∈ {PAID, SHIPPED, COMPLETED})`，回改 **7 个文件共 12 处**旧口径
   （★ 摸底时以为只有 2 处）；并修掉 §0.2.2 的「空账本审计失明」（`day14-reconcile.py` 27/27）
4. ★ **库存全程不动的断言**：从支付完成到确认收货，`available`/`locked`/`sold` **一格不动**
5. **清理**：靶子订单按 §0.3 口径复原（自清、可重跑）
6. **文档**：补实测小节
7. **提交 + push** —— 提交由 AI 完成；**push 必须由用户在终端执行**（凭据原因，见 Day 14 §七 第 6 条）
8. **更新记忆**：`MEMORY.md` 补本日定型的坑；当日日志追加流水

---

## 六、验收计划

脚本：`backend/loadtest/day15-ship-confirm.py`（自清理、可重跑、断言计数）
报告：`backend/loadtest/day15-ship-confirm-report.txt`

★ 脚本**已写好**（11 个分组），但在生产代码落地前跑不了 ——
`ship` / `confirm` 两个端点不存在，脚本会在第 [4] 节失败。
它同时充当**验收标准**：把下面这张表当 checklist，代码写完直接跑。

| # | 分组 | 断言要点 |
|---|---|---|
| 0 | 基线 | 7 SKU 指纹快照；`orders`/`payments`/`order_items`/`inventory_logs` 行数 |
| 1 | 准备 | demo 登录、admin 登录（拿 `order:ship` 权限） |
| 2 | 下单 | `POST /api/orders` → `PENDING_PAYMENT`；库存 `-1/+1` |
| 3 | 支付 | → `PAID`；`locked → sold`；`paid_at` 非空 |
| 4 | **发货** | **admin token** → `SHIPPED`；`shipped_at` 非空；★ **库存三格全不动** |
| 5 | **确认** | **C 端 token** → `COMPLETED`；`completed_at` 非空；★ **库存三格全不动** |
| 6 | ★★ 越权 | **C 端 token 打 ship → 403**（RBAC 首次业务验证）；**匿名打 ship → 401** |
| 7 | 顺序 | `PENDING_PAYMENT` 直接 ship → 400；`PAID` 直接 confirm → 400 |
| 8 | 幂等 | 重复 confirm → 400；重复 ship → 400 |
| 9 | IDOR | `intruder` 打 demo 的 confirm → **业务 404**（与「不存在」不可区分） |
| 10 | ★ 口径 | 升级后的 `sold == Σ({PAID,SHIPPED,COMPLETED})` → 0 漂移；`locked` 守恒 → 0 漂移 |
| 11 | 清理 | 删靶子订单 + 明细 + 支付；**7 SKU 逐字段回到基线**；行数回基线；无孤儿行 |

---

## 七、提交清单（按主题分批）

**已由 AI 完成**：
1. `fix(loadtest)`: 对账口径升级（`sold` 口径 7 文件 12 处）+ 修掉「空账本审计失明」（`day14-reconcile.py` 27/27）
2. `docs`: 本规划文档（含 §0.2 口径发现、§0.4 机制实证、§八 对照清单）
3. `test(order)`: `day15-ship-confirm.py`（11 个分组，待代码落地后跑）

**待代码写完后提交**（★ 生产代码由用户自己写 —— 见 `.workbuddy-ai/memory/MEMORY.md` 的「工作方式约定」）：
2. `feat(order)`: 发货边（`shipOrder` + Service + 端点 + RBAC）
3. `feat(order)`: 确认收货边（`confirmReceipt` + Service + 端点 + IDOR）
4. `test(order)`: `day15-ship-confirm.py` + 报告
5. `docs`: Day 15 实测小节 + 状态行

---

## 八、写代码时的对照清单（★ 动手时对着这张表勾）

★ 本节是**规格**不是实现 —— 给你「改哪一行、必须满足什么、别踩什么」，
代码由你自己写（本日工作方式：我只交付设计/规划/验收标准，**不落实现到 `backend/mallx/**`**）。

### 8.1 逐文件改动 · 第 1 步（发货）

| # | 文件 | 锚点 | 必须满足 |
|---|---|---|---|
| 1 | `OrderMapper.java` | 在 `cancelOrder`（第 94 行）**之后**、`selectTimeoutOrderIds` 的 Javadoc（第 96 行）**之前**插入 | 签名 `int shipOrder(@Param("orderId") Long orderId);` —— 方法名与 XML 的 `<update id>` **逐字符一致**（否则启动不报错、一调用 `Invalid bound statement`） |
| 1b | `OrderMapper.java` | **类注释**第 19–21 行 | 「现有五个」→「现有七个」，清单补 `shipOrder` / `confirmReceipt`。★ 漏改不会编译失败，但会留下假文档 |
| 2 | `OrderMapper.xml` | 在 `cancelOrder` 的 `</update>`（第 108 行）**之后**追加 | `<update id="shipOrder">`：`SET status='SHIPPED', shipped_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP` + `WHERE id=#{orderId} AND status='PAID'`。★ `shipped_at` 与 `updated_at` **都必须手写** |
| 3 | `OrderService.java` | 在 `cancelTimeoutOrders`（第 109 行）**之后**追加 | `void ship(Long orderId);` —— ★ **不带 userId**（§3.3，principal 撞号） |
| 4 | `OrderServiceImpl.java` | 在 `cancelTimeoutOrders`（结束于第 305 行）**之后**、查询小节注释（第 308 行）**之前** | 建「发货」小节。实现只需 3 行：调 `orderMapper.shipOrder` → `rows == 0` → 抛 `BusinessException(VALIDATE_FAILED, "订单状态不允许发货")`。★ **不加 `@Transactional`** |
| 5 | `OrderController.java` | 在 `cancel`（结束于第 74 行）**之后** | `@PostMapping("/{id}/ship")` + `@PreAuthorize("hasAuthority('order:ship')")`。★ 方法**不要 `Authentication` 参数** |
| 5b | `OrderController.java` | **类注释**第 27 行 | 从「本类刻意不挂 `@PreAuthorize`」改成「本类**默认**不挂（C 端），**唯独 `ship` 例外 —— 管理端动作**」。★ 不改就是自相矛盾的注释 |
| 5c | `OrderController.java` | **import 区**（第 12 行附近） | 补 `import org.springframework.security.access.prepost.PreAuthorize;` —— 现有 import 里**没有**它 |

### 8.2 逐文件改动 · 第 2 步（确认收货）

| # | 文件 | 锚点 | 必须满足 |
|---|---|---|---|
| 6 | `OrderMapper.java` | 紧接着 `shipOrder` 声明之后 | `int confirmReceipt(@Param("orderId") Long orderId);` |
| 7 | `OrderMapper.xml` | 紧接着 `<update id="shipOrder">` 之后 | `SET status='COMPLETED', completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP` + `WHERE id=#{orderId} AND status='SHIPPED'`。★ **`WHERE` 里不要带 `user_id`**（§4.1） |
| 8 | `OrderService.java` | 紧接着 `ship` 之后 | `void confirm(Long userId, Long orderId);` —— ★ **带 userId**，与 ship 相反 |
| 9 | `OrderServiceImpl.java` | 紧接着 `ship` 实现之后 | 两步：① `requireOwn(userId, orderId)`（★ 复用**已有**私有方法，在第 395 行，直接调即可）② `rows == 0` → 抛 `"订单状态不允许确认收货"`。★ **不加 `@Transactional`** |
| 10 | `OrderController.java` | 紧接着 `ship` 端点之后 | `@PostMapping("/{id}/confirm")`，★ **不挂** `@PreAuthorize`，★ **要 `Authentication` 参数**（C 端，与 ship 相反） |

★ 两条边的**对称性**就是这份清单的记忆点：
`ship` 不带 userId / 挂权限 / 不要 Authentication；`confirm` 带 userId / 不挂权限 / 要 Authentication。
—— **两组三个「相反」**，写的时候一起看就不会串。

### 8.3 陷阱清单（★ 写一行勾一行）

| # | 陷阱 | 后果 | 依据 |
|---|---|---|---|
| 1 | XML 注释里出现**连续两个减号** | 启动才炸（解析器报错） | Day 13 踩过，`OrderMapper.xml:124` 有注释 |
| 2 | Javadoc 里直接写 `/api/orders/*/ship` | `*/` **提前结束注释** → 后面中文被当代码 → 编译报「非法字符: `\u3010`」 | ★ 本日已踩，改用 `{@code POST /api/orders/&#123;id&#125;/ship}` |
| 3 | 漏写 `updated_at` | 该格永远停在旧时间（自定义 XML 的 UPDATE **不走** `MetaObjectHandler`） | Day 13/14 都踩过 |
| 4 | 把 `(Long) auth.getPrincipal()` 当**发货人** | admin(1) 与 demo(1) **撞成同一个值** | §0.4 已实测两 token 的 `sub` 都是 `"1"` |
| 5 | 给 `ship` / `confirm` 加 `@Transactional` | 无害但**无意义** —— 单条 UPDATE 自身即原子 | §一 的 ★ |
| 6 | 给 `confirm` 的 CAS `WHERE` 加 `user_id` | 「不存在 / 不是你的 / 状态不对」三种 0 行**重新糊在一起** → 翻不成稳定的 400 | §4.1 |
| 7 | 给 `confirm` 挂 `@PreAuthorize` | C 端 token 权限集为空 → **必 403**，收货永远做不成 | §0.4 |
| 8 | 在两条边里写 `inventory_logs` 流水 | 账本被 `change_quantity=0` 的行污染，**「账本能解释现值」这个性质变脏** | §4.3 |
| 9 | 改 `03-data.sql:140` 的权限路径去迁就代码 | 违背 Day 03 既定设计，还要改 seed | §3.2 方案 C |
| 10 | 拿序列（`orders_id_seq` 等）当基线断言 | 序列不回滚，**有空洞是正常的** → 断言必然假失败 | §0.1 |

### 8.4 ★ 「不要动」清单（省得白改）

| 文件 | 为什么不用动 |
|---|---|
| `GlobalExceptionHandler.java` | Day 07 已为 `AccessDeniedException` 建好 401/403 分流出口（第 99 行），§0.4 实测三态全中 |
| `SecurityConfig.java` | `@EnableMethodSecurity` 已开（第 21 行）；`anyRequest().authenticated()` 已兜住匿名 → 401 |
| `JwtAuthenticationFilter` / `JwtUtil` | 权限还原链路已通（`perms` → authorities）；**区分 user/admin 是独立一步，本日不做** |
| `OrderStatus.java` / `orders` 表结构 | 常量、`shipped_at` / `completed_at` 列 Day 03 就齐了 —— **本日零 DDL** |
| `backend/sql/03-data.sql` | 权限 `order:ship` + 角色 `ORDER_ADMIN` + `admin`→`SUPER_ADMIN` 已 seed，且 §0.4 实测 admin token 里确实带 `order:ship` |

### 8.5 自检顺序（写完按这个顺序验）

1. **编译**：`mvn install -pl mall-order -am`（★ 必须 install 到本地仓库，不能只 compile）
2. **重启**：杀 `MallXApplication` → 确认 8080 空 → `mvn spring-boot:run -pl mall-server`（★ **不带** `-am`）
3. **冒烟**：admin token 打 `/api/orders/{id}/ship`、C 端 token 打 `/api/orders/{id}/confirm`
4. **正式验收**：`python backend/loadtest/day15-ship-confirm.py` —— 11 个分组，报告落在
   `backend/loadtest/day15-ship-confirm-report.txt`
5. **对账复核**：脚本第 [10] 组会跑新旧两条口径 —— 期望**都是 0 漂移**（§0.2 已证今天是安全空操作）
6. **确认基线复位**：7 SKU 逐字段回到 §0.3（`100/80/56/147/117/40/90` 的可售列 +
   `sold = 0/0/4/3/3/0/0`），`orders=8`、`payments=5`、`order_items=9`、`inventory_logs=0`

---

## 附：本日不做的候选（留档，避免走偏）

| 候选 | 为什么不做 |
|---|---|
| 评价（`reviews`） | 里程碑里明确排在 **Day 16**；它是**新模块**（表已建未用、还缺唯一约束），与「状态机走完」是两件事 |
| 退款 / 退货（`REFUNDED`） | 已支付订单的退款是**独立业务**（V2.0）；本日只走正向 |
| 发货物流单号 / 快递公司 | V1.0 的 `orders` 表**没有**这两个列 → 一加就是 DDL，超出「零 DDL」范围 |
| 管理端「谁发的货」审计 | 需要先让 `JwtAuthenticationFilter` 能区分 user / admin token（§3.3）—— 独立一步 |
| 自动确认收货（`SHIPPED` 超时 → `COMPLETED`） | 与 Day 14 的超时关单同构，但属**锦上添花**；先把手动闭环走通 |
