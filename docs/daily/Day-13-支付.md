# Day 13 · 支付（`PENDING_PAYMENT` → `PAID`）

> **一句话目标**：让订单「付钱」这一步真正跑通 —— 订单状态往前推一格、库存从「锁定」变「已售」，
> 并且保证**同一笔订单无论被点多少次、多少并发，都只成交一次**。

---

## 一、先看清战场（全部实测，不是推测）

### 1.1 `payments` 表 · 9 列

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | bigint PK / seq | |
| `payment_no` | varchar **NOT NULL · UNIQUE** | 第三方/内部支付流水号，**UNIQUE 是最后防线** |
| `order_id` | bigint NOT NULL · FK → `orders(id)` | |
| `amount` | numeric NOT NULL | |
| `method` | varchar NOT NULL | 无 CHECK，取值靠常量类 |
| `status` | varchar NOT NULL | 无 CHECK，取值靠常量类 |
| `paid_at` | timestamp **可空** | 业务手写，**禁止挂 fill** |
| `created_at` / `updated_at` | timestamp NOT NULL DEFAULT now() | |

### 1.2 索引与约束 —— 有一个细节很关键

```
payments_pkey                PRIMARY KEY (id)
payments_payment_no_key   u  UNIQUE (payment_no)
fk_payment_order          f  FOREIGN KEY (order_id) REFERENCES orders(id)
idx_payments_order_id        CREATE INDEX ... (order_id)      ← ★ 普通索引，不是唯一索引
```

★ `idx_payments_order_id` **是普通索引** ⇒ 一个订单**允许挂多笔支付记录**。
这不是漏洞，是真实业务形态：**支付失败重试 / 换支付方式 / 退款** 都会产生多条。
⇒ 「一单只能成功支付一次」这条不变式，**数据库管不了**（不像 `payment_no` 有 UNIQUE 兜底），
**只能靠业务状态机守住** —— 这正是本 Day 的核心。

### 1.3 `orders` 表（15 列）—— 注意「没有 version 列」

`id / order_no(UNIQUE) / user_id(FK) / total_amount / pay_amount / status / receiver_name / receiver_phone / receiver_address / created_at / paid_at / shipped_at / completed_at / cancelled_at / updated_at`

★ **没有 `version` / 乐观锁列** ⇒ 想防并发重复支付，只能靠「**条件 UPDATE**」，不能再指望版本号。

### 1.4 `inventory_logs`（8 列，**0 行，从未使用**）

`id / sku_id / change_quantity / before_stock / after_stock / type / reference_id / created_at` —— **零外键**，可以自由写。
> 本 Day **不动它**（只在下单/支付两处都记流水才对称，那是后续「库存对账」的话题）。

### 1.5 模块依赖现状

```
mall-order    → mall-common, mall-inventory
mall-payment  → mall-common                       ← 要动手的地方
mall-server   → ... mall-inventory, mall-order, mall-payment ✅ 已全量依赖
```

### 1.6 现成样本数据（直接当靶子）

| 订单 | 金额 | 明细 | 状态 |
|---|---|---|---|
| `#9002` | 24998.00 | iPhone 17 Pro ×2（sku3） | `PENDING_PAYMENT` |
| `#1` | 31997.00 | iPhone ×2 + Mate80 ×1（sku3+sku4） | `PENDING_PAYMENT` |
| `#2` | 19497.00 | Xiaomi 15 Ultra ×3（sku5） | `PENDING_PAYMENT` |

库存基线（恒等式**全部成立**）：
```
sku1  96/2/2   sku2  78/0/2   sku3  56/4/0   sku4 147/2/1
sku5 117/3/0   sku6  39/1/0   sku7  90/0/0        （available/locked/sold）
```

---

## 二、三条核心认知（本 Day 的全部价值）

### ★★★ 一、**状态迁移本身就是一次 CAS —— 一招同时解决 IDOR + 幂等 + 状态机**

```sql
UPDATE orders
   SET status = 'PAID', paid_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
 WHERE id = #{orderId} AND status = 'PENDING_PAYMENT'
```

`WHERE status = 'PENDING_PAYMENT'` 就是一个 **Compare-And-Set**：
**「只有现在还是待支付，才允许被我改成已支付」** —— 数据库替我们做原子比较。
**影响行数就是答案**：`1` = 抢到了，`0` = 被别人抢先/状态不对。

为什么不能「先查后改」：

```
线程 A                          线程 B
SELECT → status=PENDING_PAYMENT
                                SELECT → status=PENDING_PAYMENT   ← 两个都读到"可支付"
UPDATE SET status='PAID' ✅
                                UPDATE SET status='PAID' ✅        ← 收两笔钱！
```

★ 与 Day 12 扣库存的 `WHERE available_stock >= ?` 是**同一招的第二次使用**。
★ 既然没有 `version` 列，**状态字段自己就是版本号** —— 这就是状态机的威力。

### ★★ 二、**「先查做语义分流 + 条件 UPDATE 做并发防重」的组合拳**

条件 UPDATE 的 `0 行` 有个副作用：**它不告诉你是谁的问题**。可能的三种原因：
① 订单不存在 ② 订单不是你的（IDOR）③ 订单状态不对（已支付/已取消）。

而这三者对用户要说完全相反的话 —— ① ② 必须**伪装成同一个 404**（不能泄露存在性），③ 要明说 `400 订单状态不允许支付`。所以：

| 阶段 | 手段 | 目的 |
|---|---|---|
| 第一步 | `SELECT ... WHERE id = ? AND user_id = ?` | 语义分流：`null` → **404「订单不存在」**（不区分① ②） |
| 第二步 | `UPDATE ... WHERE id = ? AND status = 'PENDING_PAYMENT'` | 并发防重：`0 行` → **400「订单状态不允许支付」** |

★ 注意第二步的 `WHERE ID` **不要再带 `user_id`** —— 归属已在第一步验完，带了反而让错误语义重新糊在一起。

### ★★ 三、**金额绝不信客户端**

`payments.amount` **必须取服务端 `orders.pay_amount`**，不接受请求体里的金额。
请求体只传 `orderId` + `method` —— 传金额等于「让顾客自己填付多少」。

---

## 三、链路全景

```
客户端 ──POST /api/payments {orderId, method}──▶ PaymentController (mall-payment)
                                                        │
                            ┌───────────────────────────▼───────────────────────────┐
                            │        @Transactional  PaymentServiceImpl.pay()       │
                            │                                                       │
                            │ ① 查订单  SELECT ... WHERE id=? AND user_id=?         │
                            │        └─ null ──▶ 404「订单不存在」（IDOR 伪装）      │
                            │ ② 读 order_items → 得到 (sku_id, quantity) 列表        │
                            │ ③ 金额 = 订单.pay_amount（★ 不信客户端）              │
                            │ ④ 插 payments 行（payment_no 生成，UNIQUE 兜底）       │
                            │ ⑤ CAS：UPDATE orders WHERE id=? AND status=           │
                            │          'PENDING_PAYMENT'                            │
                            │        └─ 0 行 ──▶ 抛异常 → 整单回滚 → 400            │
                            │ ⑥ 逐个 SKU：UPDATE inventories                        │
                            │       locked_stock -= q, sold_stock += q              │
                            │       WHERE sku_id=? AND locked_stock >= q            │
                            │       （★ available_stock 一动不动）                  │
                            └───────────────────────────────────────────────────────┘
```

**为什么要在一个事务里**：④ 插了支付单、⑤ 改了订单、⑥ 改了 N 个 SKU —— 任何一步失败都必须整体回滚，
否则出现「付了钱订单还是待支付」或「订单已支付但库存没转已售」这种对不上账的状态。
跨模块 Bean 调用默认 `REQUIRED` 传播 ⇒ 自动加入同一事务（Day 12 已确认）。

**⚠️ 架构坑：mall-payment 必须依赖 mall-order，所以接口不能放 OrderController**
若接口挂在 `OrderController`，就要求 `mall-order → mall-payment`；而支付又要写 `orders` 表 ⇒ `mall-payment → mall-order` ⇒ **循环依赖，Maven 直接编译失败**。
⇒ **Controller 只能放 `mall-payment` 的 `PaymentController`**，路径 `POST /api/payments`（订单 id 走 body）。

---

## 四、分 5 步

| 步 | 内容 | 验收 |
|---|---|---|
| **1** | `mall-payment` 开张：`entity/Payment`、`common/PaymentStatus`、`common/PaymentMethod`、`mapper/PaymentMapper`(+XML)、`InventoryService` 加 `moveLockedToSold` 条件 UPDATE | 冒烟 8 项 |
| **2** | 支付主链路：`dto/PaymentCreateDTO`、`vo/PaymentVO`、`service/PaymentService`(+Impl，编排出上面 6 步)、`controller/PaymentController`；`mall-payment/pom.xml` **加 2 条依赖**（mall-order + mall-inventory）；`OrderService` 加 `markPaid` | 验收 10 项 |
| **3** | ★ **并发压测**：20 线程并发支付**同一订单** → 断言「**恰好 1 次成功**、`payments` 恰好 1 行、`locked` 精确 −N、`sold` 精确 +N」；**对照实验**：把 CAS 换成「先查后改」→ 亲眼看见**重复支付**（20 笔支付记录 + 库存被扣 20 次） | 主组 + 对照组 |
| **4** | 支付记录查询：`GET /api/payments`（分页夹紧 + 只查自己的）+ `GET /api/payments/{id}`（IDOR 404） | 验收 6 项 |
| **5** | 端到端（建单 → **查详情确认 PENDING** → 支付 → 状态变 PAID → 库存对账 → 重复支付被拒 → 查支付记录）+ 清理 + `git push` | 11 项链路 |

---

## 五、顺带修的历史遗留？

`orders` 表的 `#1` / `#2` 是 Day 12 压测前的样本（还没测过「一车多单」），
Day 13 第 3 步的对照组实验**可以直接拿 `#1` 或 `#2` 当破坏靶子**（跑完再回滚数据），不必新建。

---

## 六、本 Day 结束时你应该能回答

1. 为什么「先查订单状态再更新」在并发下会收两笔钱？条件 UPDATE 是怎么堵住的？
2. 条件 UPDATE 返回 0 行时，为什么不能直接把它当成「订单不存在」？
3. 支付时库存 `available_stock` 为什么**一动不动**？它在下单那一刻就已经被「扣」过了吗？
4. `payments` 表为什么不给 `order_id` 加 UNIQUE 索引？

---

## 七、第 1 步实测：`mall-payment` 开张 + 库存 `locked → sold` ✅

### 7.1 产出（8 个文件 = 4 新 + 4 改）

| 文件 | 类型 | 要点 |
|---|---|---|
| `mall-payment/entity/Payment.java` | 新 | **必须 `@TableName("payments")`**（`Payment` → 默认反推 `payment`）；`paidAt` **不挂 fill** |
| `mall-payment/common/PaymentStatus.java` | 新 | `SUCCESS` 会被写；`FAILED`/`REFUNDED` 为真实网关占位 |
| `mall-payment/common/PaymentMethod.java` | 新 | `ALIPAY`/`WECHAT`/`BALANCE`，DTO 用 `@Pattern` 锁死取值 |
| `mall-payment/mapper/PaymentMapper.java` | 新 | **纯 BaseMapper，本表不需要 XML** |
| `mall-inventory/mapper/InventoryMapper.java` | 改 | +`moveLockedToSold` |
| `mall-inventory/resources/mapper/InventoryMapper.xml` | 改 | +条件 UPDATE（`available_stock` **不在 SET 里**）|
| `mall-inventory/service/InventoryService.java` | 改 | +`moveLockedToSold` 签名 |
| `mall-inventory/service/impl/InventoryServiceImpl.java` | 改 | +实现，**0 行抛 `FAIL(500)`** |

> ★ 与规划的一处偏差：规划写的是「`PaymentMapper`(+XML)」，实际**不需要 XML** ——
> 支付单写入是一句无条件的 `INSERT`，BaseMapper 足够；「一单只付一次」的防线根本不在这个 Mapper 上，
> 而在 `orders` 的状态条件 UPDATE（第 2 步）。

### 7.2 冒烟实测（真机启动跑 `ApplicationRunner`，`sku_id=3`，基线 `60/56/4/0`）

| # | 断言 | 实测 |
|---|---|---|
| A1 | `insert` 返回 1 且回填主键 | ✅ `rows=1 generatedId=1` |
| A2 | `selectById` 逐字段核对 | ✅ `orderId=1 / amount=24998.00 / method=ALIPAY / status=SUCCESS / paidAt` 非空，`createdAt`+`updatedAt` 自动填充 |
| A3 | 清理删除 | ✅ `rows=1` |
| B0 | 基线 | ✅ `60/56/4/0` `identity_ok=true` |
| B1 | `moveLockedToSold(3, 2)` → 1 行 | ✅ `60/**56**/2/2` |
| B2 | 超量 999 → 0 行，且**数据一字未动** | ✅ 仍 `60/56/2/2` |
| B3 | 扣完剩余 2 件 → 1 行 | ✅ `60/**56**/0/4` |
| B4 | 锁定已空再扣 → 0 行 | ✅ `60/56/0/4` |
| B5 | 不存在的 sku → 0 行（**未抛 SQL 异常**）| ✅ |
| B6 | Service 遇 0 行 → `BusinessException` | ✅ `code=500 msg=库存锁定状态异常，支付已回滚` |
| B7 | 复原 | ✅ `60/56/4/0` `identity_ok=true` |

**两条最重要的实证：**

1. **A2 证明 `@TableName("payments")` 真的生效了** —— 映射对不对，**编译是证明不了的**，只能真调一次。
2. **B0→B4 的 `available_stock` 始终是 56，一步没动** —— 这就是「支付只搬 `locked→sold`」的铁证。
   若哪版实现顺手又减了 `available`，等于把同一件货扣两遍。

### 7.3 为什么这里 0 行报 `500` 而不是 `400`

| 方法 | 0 行的含义 | 语义 | code |
|---|---|---|---|
| `deductForOrder` | 库存不足 | 用户可理解的正常结果 | `400` |
| `moveLockedToSold` | 订单说锁了 3 件、库存说只锁了 1 件 | **服务端账目不一致**，重试无意义，必须整笔回滚 | `500` |

**同一个「影响行数 0」，在两种业务里是完全不同的意思** —— 判错误码前先问一句「这是谁的错」。

### 7.4 环境与基线

- 冒烟类 `Day13SmokeRunner` 已删（`src_exists=False` / `class_exists=False`），`mvn clean -pl mall-server` 后重建
- 重启日志：`Tomcat started on port 8080` ✅、`Global AuthenticationManager configured with userDetailsServiceImpl` ✅、**`DAY13 SMOKE` 命中 0** ✅
- `/api/hello` → `200 {"code":200,"message":"success","data":"Hello MallX"}`
- 基线：`orders=3 / order_items=4 / payments=0 / cart_items=1 / user_addresses=2 / users=2`；7 个 SKU **恒等式全 `t`**；`sku3 = 60/56/4/0`

