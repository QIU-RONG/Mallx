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

---

## 八、第 2 步 · 动手模板（10 个文件：1 改 POM + 4 改 order + 5 新 payment）

> 方向：**你自己敲**，敲完我对照建表 SQL 与既有实体审查。
> 卡在任何一处直接问，别硬猜。

### 8.0 先想清楚三件事

1. **谁改订单状态？** `mall-order` 的 `OrderService.markPaid`（订单状态的变更逻辑留在 order 模块）。
2. **mall-payment 怎么拿到订单？** 直接注入 `OrderMapper` / `OrderItemMapper` / `OrderService` / `InventoryService`
   —— `@MapperScan("com.mallx.**.mapper")` 是全局的，跨模块注入 Mapper **不需要任何额外配置**。
3. **谁在事务里？** `PaymentServiceImpl.pay` 挂 `@Transactional`，它调用的 order / inventory 方法默认 `REQUIRED` 传播 → **自动加入同一事务**。

---

### 8.1 `mall-payment/pom.xml`（改：+2 条依赖）

在现有 `mall-common` 依赖后面加两块（**版本由父 POM 托管，不要写 `<version>`**）：

```xml
<dependency>
    <groupId>com.mallx</groupId>
    <artifactId>mall-order</artifactId>
</dependency>
<dependency>
    <groupId>com.mallx</groupId>
    <artifactId>mall-inventory</artifactId>
</dependency>
```

> ⚠️ 方向必须是这样：`mall-payment → mall-order`。**反过来（order → payment）会循环依赖**，
> 这也是接口只能挂 `PaymentController` 的原因。

---

### 8.2 `mall-order/.../mapper/OrderMapper.java`（改：+1 方法）

```java
/**
 * 支付成功：CAS 推进订单状态。
 * ★ 为什么用条件 UPDATE 而不是先查后改 —— 见类头注释与 Day 13 文档第二章。
 *
 * @param orderId 订单主键
 * @return 影响行数：1 = 抢到了；0 = 订单已被别人先付 / 已取消（状态不是 PENDING_PAYMENT）
 */
int markPaid(@Param("orderId") Long orderId);
```

---

### 8.3 `mall-order/.../resources/mapper/OrderMapper.xml`（改：+1 条 `<update>`）

**照抄结构，但 SET/WHERE 由你写**：

```xml
<update id="markPaid">
    UPDATE orders
       SET status     = ????,
           paid_at    = ????,
           updated_at = ????
     WHERE id = #{orderId}
       AND status = ????
</update>
```

**要你自己决定的四个空：**

| 空 | 提示 |
|---|---|
| `status =` | 目标是 `'PAID'`（与 `OrderStatus.PAID` 一致） |
| `paid_at =` | 业务时间戳，**不挂 fill**，这里要手写 |
| `updated_at =` | ⚠️ 自定义 XML 的 UPDATE **不走 `MetaObjectHandler`**，漏了它这格永远停在旧时间 |
| `WHERE status =` | 这一行才是胜负手：`'PENDING_PAYMENT'` |

> ★ 想想为什么 `WHERE` 里**不需要**再带 `user_id`？（提示：IDOR 在 Service 第一步已经分流过了；
> 带了反而让「不存在 / 不是你的 / 状态不对」三种 0 行原因重新糊在一起。）

---

### 8.4 `mall-order/.../service/OrderService.java`（改：+1 签名）

```java
/**
 * 支付成功：把订单从「待支付」推进到「已支付」。
 * 状态不对时抛业务异常（HTTP 200 + body.code=400）。
 */
void markPaid(Long orderId);
```

---

### 8.5 `mall-order/.../service/impl/OrderServiceImpl.java`（改：+1 实现）

骨架：

```java
@Override
public void markPaid(Long orderId) {
    int rows = orderMapper.markPaid(orderId);
    if (rows == 0) {
        throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "订单状态不允许支付");
    }
}
```

> ★ 这里返回 0 行是 **400**（用户可理解：订单已经付过了），不是 500
> —— 和第 1 步 `moveLockedToSold` 的 0 行语义正好相反。**判错误码前先问「这是谁的错」。**

---

### 8.6 `mall-payment/.../dto/PaymentCreateDTO.java`（新）

```java
@Data
public class PaymentCreateDTO {

    @NotNull(message = "订单 id 不能为空")
    private Long orderId;

    @NotBlank(message = "支付方式不能为空")
    @Pattern(regexp = "???", message = "支付方式不正确")
    private String method;
}
```

`@Pattern` 的正则把取值锁在 `PaymentMethod` 的三个常量里（用 `|` 分隔）。

> ⚠️ **故意没有 `amount` 字段** —— 金额必须取服务端 `orders.pay_amount`。
> 请求体里出现金额字段 = 让顾客自己填付多少。

---

### 8.7 `mall-payment/.../vo/PaymentVO.java`（新）

字段建议：`id / paymentNo / orderId / orderNo / amount / method / status / paidAt`

要求：`@Data` + `@AllArgsConstructor`（项目约定）。

---

### 8.8 `mall-payment/.../service/PaymentService.java`（新）

```java
PaymentVO pay(Long userId, PaymentCreateDTO dto);
```

---

### 8.9 `mall-payment/.../service/impl/PaymentServiceImpl.java`（新 · ★ 本步核心）

要注入 5 个 Bean：

```java
private final PaymentMapper paymentMapper;        // mall-payment
private final OrderMapper orderMapper;            // mall-order
private final OrderItemMapper orderItemMapper;    // mall-order
private final OrderService orderService;          // mall-order
private final InventoryService inventoryService;  // mall-inventory
```

`pay` 方法骨架（六步，**逐步填**）：

```java
@Override
@Transactional(rollbackFor = Exception.class)   // ★ 别漏
public PaymentVO pay(Long userId, PaymentCreateDTO dto) {

    // ① 查订单做「语义分流」—— 归属条件写在 WHERE 里
    Order order = orderMapper.selectOne(new LambdaQueryWrapper<Order>()
            .eq(Order::getId, dto.getOrderId())
            .eq(Order::getUserId, userId));
    if (order == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "订单不存在");
    }

    // ② 读明细，拿到要转移的 (skuId, quantity) 列表
    List<OrderItem> items = orderItemMapper.selectList(
            new LambdaQueryWrapper<OrderItem>().eq(OrderItem::getOrderId, order.getId()));
    if (items.isEmpty()) {
        throw new BusinessException(ResultCode.FAIL.getCode(), "订单明细缺失");
    }

    // ③ 插支付单（金额取 order.getPayAmount()，★ 绝不用 dto 里的）
    Payment payment = new Payment();
    payment.setPaymentNo(...);          // 自己写生成器，参考 OrderServiceImpl#generateOrderNo
    ...
    paymentMapper.insert(payment);

    // ④ CAS 改订单状态（0 行会在这里抛异常 → 整笔回滚）
    orderService.markPaid(order.getId());

    // ⑤ 逐个 SKU 做 locked → sold
    for (OrderItem item : items) {
        inventoryService.moveLockedToSold(item.getSkuId(), item.getQuantity());
    }

    // ⑥ 组装 VO 返回
    return ...;
}
```

**六个最容易踩的点：**

| # | 坑 | 说明 |
|---|---|---|
| 1 | ① 的 `equals(userId)` 少了 | 少了就是 IDOR：能查别人的订单 |
| 2 | ① 返回 null 时报 403 | ❌ 必须 **404**，403 会告诉攻击者「这个 id 真实存在」 |
| 3 | ③ 用了 `dto.getAmount()` | ❌ 金额只信服务端 |
| 4 | ④ 忘了调 | 订单永远停在待支付，但钱已经「收了」 |
| 5 | ⑤ 写成 `deductForOrder` | ❌ 那是下单用的（`available→locked`）；支付要用 `moveLockedToSold`，**`available` 不能再动** |
| 6 | 漏 `@Transactional` | ④ 成功 ⑤ 失败 → 订单已支付但库存没转，**账对不上** |

**关于 ④ 和 ⑤ 的顺序**：先 ④ 后 ⑤。④ 是「抢资格」，抢不到就没必要动库存。
两者在同一事务里，顺序不影响正确性，但先抢资格可以少做无用功。

---

### 8.10 `mall-payment/.../controller/PaymentController.java`（新）

```java
@RestController
@RequestMapping("/api/payments")
public class PaymentController {

    @PostMapping
    public Result<PaymentVO> pay(@AuthenticationPrincipal Long userId,
                                 @Valid @RequestBody PaymentCreateDTO dto) {
        return Result.success(paymentService.pay(userId, dto));
    }
}
```

> ⚠️ **C 端 principal 是 `Long userId`，不是 `LoginUser`**（见 §三 安全约定）。
> ⚠️ C 端接口**不能挂 `@PreAuthorize`**（token 里没有 `perms`，挂了必 403），
> 靠白名单之外的 `anyRequest().authenticated()` 拦登录即可。
> 加 `@Tag` / `@Operation` 保持 Swagger 可读（项目约定）。

---

### 8.11 敲完的自检清单

- [ ] `mall-payment/pom.xml` 两条依赖**都没写 `<version>`**
- [ ] `OrderMapper.xml` 的 `<update id="markPaid">` 与接口方法名**逐字符一致**（差个字母就是 `Invalid bound statement`，编译器不提示）
- [ ] `markPaid` 的 `WHERE` 里**只有** `id` 和 `status`，**没有** `user_id`
- [ ] `PaymentCreateDTO` **没有金额字段**
- [ ] `PaymentServiceImpl.pay` 上有 `@Transactional`
- [ ] ③ 里 `payment.setAmount(order.getPayAmount())`
- [ ] ⑤ 用的是 `moveLockedToSold`，不是 `deductForOrder`
- [ ] `PaymentController` 上**没有** `@PreAuthorize`

### 8.12 敲完我会跑的 10 项验收（先给你，便于自查）

| # | 请求 | 期望 |
|---|---|---|
| 1 | 匿名 `POST /api/payments` | `401` |
| 2 | 支付不存在的订单 | `404 订单不存在` |
| 3 | 支付**别人的**订单（`users.id=2` 的靶子） | `404`（与 #2 完全一致，不可区分）|
| 4 | 缺 `method` | `400 支付方式不能为空` |
| 5 | `method="BITCOIN"` | `400 支付方式不正确` |
| 6 | 正常支付订单 `#9002` | `200`，返回 `paymentNo` / `amount=24998.00` / `status=SUCCESS` |
| 7 | 查库：`orders#9002` | `status=PAID`、`paid_at` 非空、`updated_at` 已刷新 |
| 8 | 查库：`payments` | 恰好 1 行，`amount=24998.00`、`method` 与请求一致 |
| 9 | 查库：`inventories` sku3 | `locked 4→2`、`sold 0→2`、**`available` 仍是 56**、恒等式成立 |
| 10 | **重复**支付 `#9002` | `400 订单状态不允许支付`，且 `payments` 仍只有 1 行、库存未再变 |

---

## 九、第 2 步 · 写法参考（对照用）

> 建议**先自己写**，卡住或写完再对照本节。§9.11 列了 4 处和 §8 模板不一致的地方，**以本节为准**。

### 9.0 写作顺序（自下而上，让编译器一路兜底）

```
① POM（+2 依赖）
② order 侧 4 处（Mapper 接口 → XML → Service 接口 → Service 实现）→ 可先编译一次
③ payment 侧 5 个新文件（DTO → VO → Service 接口 → ServiceImpl → Controller）→ 再编译
```

先写 order 侧的理由：payment 依赖 `markPaid`，**先把被依赖的一方准备好**，写 payment 时才有东西可调。
`order` 模块不依赖 payment，所以改完 ② 就能独立编译通过 —— **错的地方早发现一格**。

---

### 9.1 `mall-payment/pom.xml`（改：+2 条依赖）

在现有 `mall-common` 依赖块**后面**追加（放在 `<dependencies>` 里，**不写 `<version>`**）：

```xml
<dependency>
    <groupId>com.mallx</groupId>
    <artifactId>mall-order</artifactId>
</dependency>
<dependency>
    <groupId>com.mallx</groupId>
    <artifactId>mall-inventory</artifactId>
</dependency>
```

> `<version>` 由父 POM 的 `dependencyManagement` 统一托管，写了反而容易出现版本错配。
>
> ⚠️ 方向只能是 `mall-payment → mall-order`。反过来（`order → payment`）就是**循环依赖**，
> Maven 直接构建失败 —— 这正是接口必须挂 `PaymentController` 而不能挂 `OrderController` 的原因。
>
> 注：`mall-order` 已经传递带出了 `mall-inventory`，但**自己用到的依赖要自己声明**
> （直接依赖原则）—— 将来 order 去掉对 inventory 的依赖时，payment 不会莫名其妙编译失败。

---

### 9.2 `mall-order/.../mapper/OrderMapper.java`（改：+1 方法）

在 `deleteSelectedCartItems` 后面加：

```java
    /**
     * 支付成功：CAS 推进订单状态 —— 条件 UPDATE 在本项目的第三次使用。
     *
     * <p>★ 为什么不是「先查后改」：两个线程都先读到 {@code PENDING_PAYMENT}，
     * 就会各自 UPDATE 一次 → <b>收两笔钱</b>。{@code WHERE status = 'PENDING_PAYMENT'}
     * 让数据库替我们做原子比较：只有第一个匹配得上，第二个执行时状态已变 → 0 行。
     *
     * <p>★ 为什么 {@code WHERE} 里【不要再带 user_id】：归属已在支付 Service 第一步
     * （{@code SELECT … WHERE id = ? AND user_id = ?}）验完。带了会让
     * 「订单不存在 / 不是你的 / 状态不对」三种 0 行原因重新糊在一起，
     * 上层就没法把它稳定地翻成「400 状态不允许支付」。
     *
     * @param orderId 订单主键
     * @return 影响行数：1 = 抢到了；0 = 已被别人先付 / 已取消（状态不是 {@code PENDING_PAYMENT}）
     */
    int markPaid(@Param("orderId") Long orderId);
```

> ⚠️ 方法名与 `OrderMapper.xml` 的 `<update id="...">` 必须**逐字符一致**，
> 差一个字母就是运行时 `Invalid bound statement`，而**编译器不会提示**。

---

### 9.3 `mall-order/.../resources/mapper/OrderMapper.xml`（改：+1 条 `<update>`）

四个空填完后是这样：

```xml
    <!-- ④ 支付成功：CAS 推进订单状态（Day 13 的核心 SQL）。
         ★★ WHERE status = 'PENDING_PAYMENT' 就是 Compare-And-Set：
            「只有现在还是待支付，才允许被我改成已支付」—— 数据库替我们做原子比较。
            影响行数 1 = 抢到；0 = 已被别人付过 / 已取消 → 上层抛 400，整笔回滚。

         ★ 为什么【不】带 user_id：归属在 Service 第一步已经分流过；
           带了会让三种 0 行原因（不存在 / 不是你的 / 状态不对）重新糊在一起。

         ⚠️ updated_at 必须手写：自定义 XML 的 UPDATE【不走】MetaObjectHandler，
            漏了它这一格就永远停在旧时间。
         ⚠️ paid_at 也手写（不挂 fill）—— 它记的是「业务事实发生的那一刻」，
            不是「这一行被改过」。 -->
    <update id="markPaid">
        UPDATE orders
           SET status     = 'PAID',
               paid_at    = CURRENT_TIMESTAMP,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = #{orderId}
           AND status = 'PENDING_PAYMENT'
    </update>
```

四个空的答案与理由：

| 空 | 填 | 为什么 |
|---|---|---|
| `status =` | `'PAID'` | 必须与 `OrderStatus.PAID` 字面量一致（列无 CHECK，写错数据库不拦你） |
| `paid_at =` | `CURRENT_TIMESTAMP` | 业务时间戳，**不挂 fill**，只能这里手写 |
| `updated_at =` | `CURRENT_TIMESTAMP` | 自定义 XML 的 UPDATE 不走 `MetaObjectHandler`，漏了就永远停在旧时间 |
| `WHERE status =` | `'PENDING_PAYMENT'` | **这一行才是胜负手** |

> 这里我用了**字面量**而不是 `#{status}`。两种都对，取舍是：
> 字面量让「一条 SQL 自己就把语义说清楚」（读的人不用回 Service 看传了什么），
> 代价是状态值升级时要改 XML。对比 `InventoryMapper.deductStock` 用的是纯参数写法 ——
> 两种风格在本项目里共存，**关键是别一半一半**。

---

### 9.4 `mall-order/.../service/OrderService.java`（改：+1 签名）

```java
    /**
     * 支付成功：把订单从「待支付」推进到「已支付」（CAS 条件 UPDATE）。
     *
     * <p>★ 状态不对时抛业务异常（HTTP 200 + body.code=400）。
     * 这里是 400 而不是 500 —— 「订单已经付过了」是用户可理解的正常结果，
     * 刷新一下就能看到正确状态；对比 {@code InventoryService#moveLockedToSold} 的
     * 0 行是「服务端账目不一致」，那才报 500。
     *
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许支付
     */
    void markPaid(Long orderId);
```

---

### 9.5 `mall-order/.../service/impl/OrderServiceImpl.java`（改：+1 实现）

```java
    /**
     * ★ 本方法【故意不加】{@code @Transactional}：单条 UPDATE 自身即原子，
     * 事务边界应当由调用方（{@code PaymentServiceImpl.pay}）持有 ——
     * 让「插支付单 + 改订单状态 + 改 N 个 SKU 库存」共处一个事务才有意义。
     * （与 {@code InventoryServiceImpl.moveLockedToSold} 同一个理由。
     *   若将来加了，默认传播 REQUIRED 也会加入外层事务，行为一致 ——
     *   但绝不能出现 REQUIRES_NEW 这种「自己偷偷提交」。）
     */
    @Override
    public void markPaid(Long orderId) {
        int rows = orderMapper.markPaid(orderId);
        if (rows == 0) {
            // 这个 0 行【不可能是】「订单不存在」—— 存在性已由调用方第一步查过，
            // 所以这里能安心地说「状态不允许」，而不是含糊的「操作失败」。
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "订单状态不允许支付");
        }
    }
```

---

### 9.6 `mall-payment/.../dto/PaymentCreateDTO.java`（新）

```java
package com.mallx.payment.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

/**
 * 支付入参（POST /api/payments）
 *
 * <p>★ 只有 {@code orderId} + {@code method}，<b>故意没有 amount</b> ——
 * 金额唯一来源是服务端 {@code orders.pay_amount}。
 * 请求体里出现金额字段，等于让顾客自己填「我付多少」。
 *
 * <p>★ {@code @Pattern} 的正则<b>不带 {@code ^...$}</b>：Bean Validation 用
 * {@code Matcher.matches()} 匹配，本身就是「整串相等」语义。
 * ⚠️ 但 {@code @Pattern} 认为 {@code null} 是合法的 → 必须配 {@code @NotBlank}
 * 才能拦住 null 和空串，两个注解缺一不可。
 */
@Data
public class PaymentCreateDTO {

    @NotNull(message = "订单 id 不能为空")
    private Long orderId;

    @NotBlank(message = "支付方式不能为空")
    @Pattern(regexp = "ALIPAY|WECHAT|BALANCE", message = "支付方式不正确")
    private String method;
}
```

---

### 9.7 `mall-payment/.../vo/PaymentVO.java`（新）

```java
package com.mallx.payment.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 支付结果（POST /api/payments 的 data）。
 *
 * <p>带上 {@code orderNo} 方便前端直接展示「哪张订单付掉了」，不必再查一次订单接口。
 * 刻意【不带 userId】—— 内部归属字段不外泄（同 OrderVO / AddressVO 的规矩）。
 *
 * <p>⚠️ {@code @AllArgsConstructor} 的参数顺序 = <b>字段声明顺序</b>；
 * 且一旦有它，Lombok 就<b>不再生成无参构造</b> → 不能 {@code new PaymentVO()} 再 set。
 */
@Data
@AllArgsConstructor
public class PaymentVO {

    private Long id;

    private String paymentNo;

    private Long orderId;

    private String orderNo;

    private BigDecimal amount;

    private String method;

    private String status;

    private LocalDateTime paidAt;
}
```

---

### 9.8 `mall-payment/.../service/PaymentService.java`（新）

```java
package com.mallx.payment.service;

import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.vo.PaymentVO;

/**
 * 支付服务
 */
public interface PaymentService {

    /**
     * 支付一笔订单（V1.0 模拟支付：调用即成功，不真正调网关）。
     *
     * <p>整个过程在一个事务里：查订单归属 → 读明细 → 插支付单 → CAS 改订单
     * → 逐 SKU {@code locked → sold}。任何一步失败整笔回滚。
     *
     * <p>★ 「一单一付」的保证来自 {@code orders} 的条件 UPDATE，不是 payments 表的唯一索引。
     *
     * @param userId 当前登录用户（从 token 来，不接受客户端传参）
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在；code=400 状态不允许支付
     */
    PaymentVO pay(Long userId, PaymentCreateDTO dto);
}
```

---

### 9.9 `mall-payment/.../service/impl/PaymentServiceImpl.java`（新 · ★ 本步核心）

```java
package com.mallx.payment.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.order.entity.Order;
import com.mallx.order.entity.OrderItem;
import com.mallx.order.mapper.OrderItemMapper;
import com.mallx.order.mapper.OrderMapper;
import com.mallx.order.service.OrderService;
import com.mallx.payment.common.PaymentMethod;
import com.mallx.payment.common.PaymentStatus;
import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.entity.Payment;
import com.mallx.payment.mapper.PaymentMapper;
import com.mallx.payment.service.PaymentService;
import com.mallx.payment.vo.PaymentVO;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 支付服务实现
 *
 * <p>★★★ 本类是 Day 13 的核心，一句话概括它的两件事：
 * <ol>
 *   <li><b>语义分流</b>：先查（带归属条件）→ 把「不存在 / 不是你的」伪装成同一个 404；</li>
 *   <li><b>并发防重</b>：再 CAS（{@code WHERE status = 'PENDING_PAYMENT'}）→ 0 行说明状态不对，报 400。</li>
 * </ol>
 * 这两步【不能合并成一步条件 UPDATE】—— 合并后就分不清 404 和 400 了。
 */
@Service
public class PaymentServiceImpl implements PaymentService {

    /**
     * 支付方式白名单：DTO 的 {@code @Pattern} 是第一道，这里是第二道。
     * 防的不是 HTTP 请求（那个已经被 {@code @Valid} 拦了），
     * 而是将来别的调用方（定时任务 / 管理端 / 测试）绕开 Controller 直接调 Service。
     */
    private static final Set<String> ALLOWED_METHODS =
            Set.of(PaymentMethod.ALIPAY, PaymentMethod.WECHAT, PaymentMethod.BALANCE);

    private final PaymentMapper paymentMapper;        // mall-payment
    private final OrderMapper orderMapper;            // mall-order
    private final OrderItemMapper orderItemMapper;    // mall-order
    private final OrderService orderService;          // mall-order
    private final InventoryService inventoryService;  // mall-inventory

    public PaymentServiceImpl(PaymentMapper paymentMapper,
                              OrderMapper orderMapper,
                              OrderItemMapper orderItemMapper,
                              OrderService orderService,
                              InventoryService inventoryService) {
        this.paymentMapper = paymentMapper;
        this.orderMapper = orderMapper;
        this.orderItemMapper = orderItemMapper;
        this.orderService = orderService;
        this.inventoryService = inventoryService;
    }

    /**
     * ★★★ 支付主链路 —— 六步全在一个事务里。
     *
     * <p>★ {@code @Transactional} 【不能漏】：
     * ④ 成功而 ⑤ 失败时，若不回滚就留下「订单已支付、库存没转已售」这种对不上账的状态。
     * 跨模块调用（{@code orderService} / {@code inventoryService}）是同一个 JVM 里的普通
     * Bean 调用，默认传播 REQUIRED → 自动加入本事务，不需要额外配置。
     *
     * <p>⚠️ 异常必须【抛出去】：在里面 try-catch 吞掉再 return，事务不会回滚。
     * 统一由 GlobalExceptionHandler 在外层转成 body 里的 code。
     *
     * <p>★ {@code rollbackFor = Exception.class} 比裸 {@code @Transactional} 多兜一层
     * 「受检异常」；本项目的 {@code BusinessException} 继承 RuntimeException，
     * 所以裸注解其实也够（OrderServiceImpl 就是这么写的）—— 显式写出来是防御性，不是必须。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public PaymentVO pay(Long userId, PaymentCreateDTO dto) {

        // ⓪ 支付方式白名单（第二道防线）—— 不碰数据库，先挡下明显非法的入参
        if (!ALLOWED_METHODS.contains(dto.getMethod())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "支付方式不正确");
        }

        // ① 语义分流：归属条件直接写进 WHERE（不是查回来再用 if 比）—— 查不到就是 404
        Order order = orderMapper.selectOne(new LambdaQueryWrapper<Order>()
                .eq(Order::getId, dto.getOrderId())
                .eq(Order::getUserId, userId));
        if (order == null) {
            // 「订单不存在」与「订单不是你的」统一 404 —— 两种情况外部不可区分，
            // 否则攻击者遍历 id 看返回码就能画出「哪些订单真实存在」的地图。
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "订单不存在");
        }

        // ② 读明细：要转移的是哪几个 SKU、各多少件（只认服务端数据）
        List<OrderItem> items = orderItemMapper.selectList(
                new LambdaQueryWrapper<OrderItem>().eq(OrderItem::getOrderId, order.getId()));
        if (items.isEmpty()) {
            // 正常流程不可能发生（下单那一刻就写了明细）；
            // 真发生了说明数据被旁路改过 → 服务端异常态，用 FAIL(500)
            throw new BusinessException(ResultCode.FAIL.getCode(), "订单明细缺失");
        }

        // ③ 插支付单 —— ★ 金额取服务端 order.getPayAmount()，绝不看请求体
        Payment payment = new Payment();
        payment.setPaymentNo(generatePaymentNo());
        payment.setOrderId(order.getId());
        payment.setAmount(order.getPayAmount());
        payment.setMethod(dto.getMethod());
        payment.setStatus(PaymentStatus.SUCCESS);
        payment.setPaidAt(LocalDateTime.now());   // 业务时间戳手写（不挂 fill）
        paymentMapper.insert(payment);            // ★ 插入后自增 id 回填

        // ④ CAS 抢资格：抢不到就抛异常 → 整个事务回滚 → ③ 插的支付单一起消失
        orderService.markPaid(order.getId());

        // ⑤ 逐个 SKU 把 locked 搬进 sold（★ available 一动不动）
        //    排序不是必须的（同一订单的 SKU 数量少、且已经在①按订单串行化了），
        //    但按 skuId 升序能和其他事务保持一致的加锁顺序 —— 与下单链路同一套纪律。
        for (OrderItem item : items) {
            inventoryService.moveLockedToSold(item.getSkuId(), item.getQuantity());
        }

        // ⑥ 组装返回（因为 ③ 的回填，这里 id / paymentNo / paidAt 都是真值）
        return new PaymentVO(payment.getId(), payment.getPaymentNo(), order.getId(),
                order.getOrderNo(), payment.getAmount(), payment.getMethod(),
                payment.getStatus(), payment.getPaidAt());
    }

    /**
     * 支付流水号：{@code PAY + yyyyMMddHHmmssSSS + 4 位随机}，如 {@code PAY202609191430151238472}。
     *
     * <p>与 {@code OrderServiceImpl#generateOrderNo} 同一套思路。
     * ★ 它<b>拦不住「同一订单付两次」</b>（两次生成的号一定不同），只保证 payments 行本身不重号 —— 兜底靠 UNIQUE。
     */
    private String generatePaymentNo() {
        return "PAY"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS"))
                + String.format("%04d", ThreadLocalRandom.current().nextInt(10_000));
    }
}
```

**六步与三条防线的落点：**

| 步 | 做的事 | 失败时 |
|---|---|---|
| ① | `SELECT … WHERE id = ? AND user_id = ?` | `null` → **404**（IDOR 伪装） |
| ② | 读 `order_items` | 空 → **500**「订单明细缺失」 |
| ③ | `INSERT payments`（金额取服务端） | 流水号撞号 → 数据库 UNIQUE 抛 23505 |
| ④ | **CAS** `UPDATE orders WHERE id AND status='PENDING_PAYMENT'` | `0 行` → **400** → 整笔回滚 |
| ⑤ | 逐 SKU `locked → sold`（`available` 不动） | `0 行` → **500** → 整笔回滚 |
| ⑥ | 组装 VO | — |

---

### 9.10 `mall-payment/.../controller/PaymentController.java`（新）

```java
package com.mallx.payment.controller;

import com.mallx.common.api.Result;
import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.service.PaymentService;
import com.mallx.payment.vo.PaymentVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 支付接口（需登录）
 *
 * <p>★ 为什么接口在 payment 模块而不是 OrderController：
 * 「支付」要写 orders 表 ⇒ {@code mall-payment → mall-order}。
 * 若接口挂 OrderController，就要求 {@code mall-order → mall-payment} ⇒ 循环依赖，构建失败。
 *
 * <p>★ 取当前用户只能写 {@code (Long) authentication.getPrincipal()} ——
 * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}，不是 LoginUser。
 *
 * <p>★ 本类刻意不挂 {@code @PreAuthorize}：C 端 token 的权限集是空的，一挂就 403。
 * 「登录才能用」由 {@code anyRequest().authenticated()} 兜住（/api/payments 不在白名单里）。
 *
 * <p>★ 接口【不接收 userId 参数】—— 用户是谁只从 token 来；
 * 订单 id 走 body（支付的是「哪个订单」是资源标识，不是身份）。
 */
@Tag(name = "支付")
@RestController
@RequestMapping("/api/payments")
public class PaymentController {

    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @Operation(summary = "支付订单（同一订单只能成功支付一次；重复支付返回 400）")
    @PostMapping
    public Result<PaymentVO> pay(Authentication authentication,
                                 @Valid @RequestBody PaymentCreateDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(paymentService.pay(userId, dto));
    }
}
```

---

### 9.11 ⚠️ 四处与 §8 模板不一致（按真实代码来，抄模板会踩）

| # | §8 模板写的 | 真实代码是 | 后果 |
|---|---|---|---|
| 1 | `Result.success(...)` | **`Result.ok(...)`** | `Result` 只有 `ok()` / `ok(T)` / `error(...)`，`success` 编译不过 |
| 2 | `@AuthenticationPrincipal Long userId` | **`Authentication authentication`** + `(Long) authentication.getPrincipal()` | 全项目 5 个 Controller 都这么写，0 处用 `@AuthenticationPrincipal` → 保持一致 |
| 3 | `@Transactional(rollbackFor = Exception.class)` | 裸 `@Transactional`（`OrderServiceImpl` 就是这么写的） | **两种都能跑**：`BusinessException extends RuntimeException`，裸注解一样回滚。显式 `rollbackFor` 是防御性写法，推荐保留 |
| 4 | VO「`@Data` + `@AllArgsConstructor`」 | 同 `LoginVO` 用法；⚠️ **`@AllArgsConstructor` 存在时 Lombok 不生成无参构造** | 不能 `new PaymentVO()` 再 setter —— 只能用全参构造，**且参数顺序 = 字段声明顺序** |

---

### 9.12 敲完的自检（编译前先扫一遍）

- [ ] `mall-payment/pom.xml` 两条依赖**都没写 `<version>`**
- [ ] `OrderMapper.java` 的方法名与 `OrderMapper.xml` 的 `<update id>` **逐字符一致**
- [ ] `markPaid` 的 `WHERE` 里**只有** `id` 和 `status`，**没有** `user_id`
- [ ] `markPaid` 的 `SET` 里**有** `updated_at`（自定义 XML 不走 `MetaObjectHandler`）
- [ ] `OrderServiceImpl.markPaid` 0 行报 **400**（不是 500、不是 404）
- [ ] `PaymentCreateDTO` **没有金额字段**
- [ ] `PaymentServiceImpl.pay` 上有 `@Transactional`
- [ ] ③ 里是 `payment.setAmount(order.getPayAmount())`
- [ ] ⑤ 用的是 `moveLockedToSold`，**不是** `deductForOrder`
- [ ] `PaymentController` 上**没有** `@PreAuthorize`、直接返回 `Result.ok(...)`

**随后编译：**
```powershell
$env:MAVEN_OPTS="-Xmx1024m"
Set-Location D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o install -DskipTests
```

---

## 十、第 2 步实测：支付主链路 ✅

### 10.1 产出（10 个文件 = 1 改 POM + 4 改 order + 5 新 payment）

| 文件 | 类型 | 要点 |
|---|---|---|
| `mall-payment/pom.xml` | 改 | +`mall-order` +`mall-inventory`（**无 `<version>`**）|
| `mall-order/.../mapper/OrderMapper.java` | 改 | +`markPaid` 声明；类头注释同步改成「四条语句走 XML」|
| `mall-order/.../resources/mapper/OrderMapper.xml` | 改 | +CAS `<update id="markPaid">` |
| `mall-order/.../service/OrderService.java` | 改 | +`markPaid` 签名 |
| `mall-order/.../service/impl/OrderServiceImpl.java` | 改 | +实现（0 行抛 `400`）|
| `mall-payment/.../dto/PaymentCreateDTO.java` | 新 | 只有 `orderId` + `method`，**无金额字段** |
| `mall-payment/.../vo/PaymentVO.java` | 新 | `@Data` + `@AllArgsConstructor` |
| `mall-payment/.../service/PaymentService.java` | 新 | `pay(userId, dto)` |
| `mall-payment/.../service/impl/PaymentServiceImpl.java` | 新 | ★ 六步编排 + `@Transactional` |
| `mall-payment/.../controller/PaymentController.java` | 新 | `POST /api/payments` |

编译：`BUILD SUCCESS`（`mall-order` 7.4s / `mall-payment` 3.9s，Reactor 11 模块全过）。

### 10.2 十项验收实测（真机，`users.id=2` 靶子订单 `#9003`）

| # | 请求 | 期望 | 实测 |
|---|---|---|---|
| 1 | 匿名 `POST /api/payments` | 401 | ✅ `401 未登录或登录已过期` |
| 2 | 支付不存在订单 `999999` | 404 | ✅ `404 订单不存在` |
| 3 | 支付**别人的**订单 `#9003`（user_id=2）| 404 | ✅ `404 订单不存在` —— **与 #2 逐字节相同** |
| 4 | 缺 `method` | 400 | ✅ `400 支付方式不能为空` |
| 5 | `method=BITCOIN` | 400 | ✅ `400 支付方式不正确` |
| 6 | 正常支付 `#9002` | 200 | ✅ `paymentNo=PAY202609191444101693228`、`amount=24998.00`、`status=SUCCESS`、`orderNo` 带出 |
| 7 | `orders#9002` | PAID / `paid_at` 非空 / `updated_at` 刷新 | ✅ `PAID`；`paid_at=14:44:10.16133`；`updated_at` 由 `11:43:44` → `14:44:10.16133` |
| 8 | `payments` 行数与内容 | 恰好 1 行、金额/方式一致 | ✅ `1` 行：`amount=24998.00 / method=ALIPAY / status=SUCCESS` |
| 9 | `inventories` sku3 | `locked 4→2`、`sold 0→2`、**`available` 仍 56** | ✅ `60/**56**/2/2`，恒等式 `t`；7 个 SKU 恒等式全 `t` |
| 10 | **重复**支付 `#9002` | 400 + 数据不变 | ✅ `400 订单状态不允许支付`；`payments` 仍 1 行、sku3 未再变 |

另外：靶子订单 `#9003` 全程保持 `PENDING_PAYMENT`（没被别人付掉）。

### 10.3 三条值得记下的实证

**① `#2` 与 `#3` 的响应逐字节相同** —— 这是 IDOR 伪装成功的最直接证据。
两者都是 `{"code":404,"message":"订单不存在","data":null}`，攻击者**无法**从响应区分
「这个 id 不存在」与「这个 id 是别人的」。若当初图省事把「不是你的」写成 403，这一项立刻就露。

**② sku3 的 `available_stock` 从验收开始到结束始终是 56** —— 支付只搬 `locked → sold`。
这一条和 Day 12 下单时 `available` 减少恰好互补，构成完整闭环：
```
下单：available -N , locked +N        （货被「预留」）
支付：            locked -N , sold +N （预留变「已售」）
```
全程 `available` 只被下单动过一次 —— 这就是「不会把同一件货扣两遍」的数学形式。

**③ `orders.paid_at` 与 `orders.updated_at` 精确相等（`14:44:10.16133`）** —— 因为它们是
**同一条 SQL 里的两个 `CURRENT_TIMESTAMP`**，而 **PG 的 `CURRENT_TIMESTAMP` 返回的是
「事务开始时间」**，同一事务内恒定不变。两个推论：
- 别指望用同一事务里的多个 `CURRENT_TIMESTAMP` 排先后（它们全相等）；
- 反过来，`payments.paid_at` 是 Java 侧 `LocalDateTime.now()`（`…170961`），比事务起点晚 9.6ms
  —— 这也说明**「DB 时间」与「应用时间」不是一回事**，跨机器部署时更明显。

### 10.4 清理与基线

- IDOR 靶子 `IDOR-TARGET-D13`（`#9003`）已删（`DELETE 1`）
- 保留 `orders`：`#1`（31997，PENDING）、`#2`（19497，PENDING）、`#9002`（24998，**PAID**）
- `payments = 1`；7 个 SKU 恒等式全 `t`；`sku3 = 60/56/2/2`
- ⚠️ `payments.id` 从 **2** 开始（不是 1）：第 1 步冒烟插的那行 `id=1` 被删了，但**自增序列不回滚**
  —— 属正常现象，不是脏数据

> ★ `#1` / `#2` 两张 `PENDING_PAYMENT` 订单正好是**第 3 步并发压测的天然靶子**（不必新建）。


## 十一、第 3 步实测：★ 并发支付压测（同一订单 × 20 线程）✅

一句话：**同一个订单，20 个线程同时付钱，正式代码只成交 1 次；把 CAS 换成「先查后改」后，同一张 19,497 元的订单被收了 12 笔钱 = 233,964 元。**

### 11.1 实验设计

| | 主组 | 对照组 |
|---|---|---|
| 靶子 | `#1`（sku3×2 + sku4×1，**双 SKU**） | `#2`（sku5×3，单 SKU） |
| 跑的代码 | **CAS 正式版** | 临时改成「先查后改」（3 处） |
| 预期 | 恰好 1 成功 / 19 拒绝 | 一单被收多次钱、库存被扣穿 |

靶子各用一张，互不干扰。**主组选双 SKU 的 `#1`**：支付时会走两轮 `moveLockedToSold`，
一次就能验「多个 SKU 各自精确 −N/+N」。

### 11.2 装备：审计触发器（比轮询可靠）

`day13-audit-setup.sql` 在 `inventories` 上挂 `AFTER UPDATE` 触发器，
把每次写入的 `(available, locked, sold)` 记进 `pay13_stock_audit` 表。

★ **这个触发器有个关键性质**：它的 INSERT 和业务 UPDATE 在**同一个事务**里 →
**被回滚的事务，连它的审计行一起消失**。所以审计表里留下的**只有真正提交的写入** ——
这本身就是「多少个事务真的提交了」的铁证，比事后轮询快照干净得多。

### 11.3 主组（CAS）：**18/18 全绿**

靶子 `#1`，基线 `sku3 = 60/56/2/2`、`sku4 = 150/147/2/1`。

| 观测点 | 实测 | 判定 |
|---|---|---|
| 成功 / 拒绝 | **1 / 19**（19 个全是 `code=400 订单状态不允许支付`） | ✅ 恰好 1 次成交 |
| `orders#1` | `PAID`，`paid_at` 已写 | ✅ |
| `payments` | **+1 行**，`sum = 31997.00` = `orders.pay_amount` | ✅ |
| `sku3` | `locked 2→0`、`sold 2→4`、**`available` 仍 56** | ✅ 精确 −2/+2 |
| `sku4` | `locked 2→1`、`sold 1→2`、**`available` 仍 147** | ✅ 精确 −1/+1 |
| 审计表 | **只有 2 行**（每 SKU 各 1 行） | ✅ 19 个失败者**一行都没留下** |
| `d_available` | 两个 SKU 都是 **+0** | ✅ 支付绝不动可售 |

★★ **最漂亮的证据是这一行**：

```
payments seq  : 43 -> 63  (consumed 20 ids)
```

序列**消费了 20 个 id**（每个线程都执行到了 ③ 的 `INSERT`），但**只活了 1 行**。
为什么会这样？因为 19 个失败线程是在 ④ 的 CAS 处拿到 0 行、抛异常 → **整笔事务回滚** →
它们插的支付单被一起撤销。而 **自增序列不参与回滚**，于是它成了「到底有几个线程真闯到
了 INSERT」的旁证。**没有这条序列证据，你无法区分「19 个线程被挡在门外」和
「19 个线程进来了又被赶出去」** —— 这两种情况的防御强度是不一样的。

### 11.4 对照组（先查后改）：一单收 12 笔钱

改动 3 处（跑完 `git checkout` 还原）：

| 文件 | 破坏点 |
|---|---|
| `OrderMapper.xml` / `markPaid` | 删掉 `AND status = 'PENDING_PAYMENT'` → 变成无条件 UPDATE |
| `InventoryMapper.xml` / `moveLockedToSold` | 删掉 `AND locked_stock >= #{quantity}` 守卫 |
| `PaymentServiceImpl` / ④ | 改成 Java 侧 `if (!PENDING_PAYMENT.equals(order.getStatus())) throw` |

关键：**那个 `if` 判断的是 ① 那一刻读回来的内存里的 `order.getStatus()`**。
20 个线程在 ① 读的时候订单还是 `PENDING_PAYMENT` → 全都通过检查。

实测（连接池临时调到 32）：

| 观测点 | 实测 | 对照主组 |
|---|---|---|
| 成功 / 拒绝 | **12 / 8** | 1 / 19 |
| `payments` | **+12 行**，`sum = 233,964.00` | +1 行 / 31,997.00 |
| `sku5.locked` | `3 → `**`-33`** ▶ **负数** | 精确 −3 |
| `sku5.sold` | `0 → `**`36`** | 精确 +3 |
| `available` | 仍 117（**+0**） | 同样 +0 |

审计轨迹（12 次提交，一次一行，每次 −3/+3）：

```
#01 locked=   0 sold=  3     #05 locked= -12 sold= 15     #09 locked= -24 sold= 27
#02 locked=  -3 sold=  6     #06 locked= -15 sold= 18     #10 locked= -27 sold= 30
#03 locked=  -6 sold=  9     #07 locked= -18 sold= 21     #11 locked= -30 sold= 33
#04 locked=  -9 sold= 12     #08 locked= -21 sold= 24     #12 locked= -33 sold= 36
```

**账目已经彻底崩了**：这张订单实际只该卖 3 件、只该收 19,497 元。现在收了 12 笔钱
（**超收 214,467 元**），库存从「锁定 3」变成「锁定 −33」—— 也就是凭空多卖了 36 件
根本不存在的货。而且 `total = avail + locked + sold` 这个**恒等式仍然成立**（120 = 117 − 33 + 36），
所以**光看恒等式根本发现不了问题** —— 这和 Day 12 对照组的教训完全一致。

### 11.5 ★★ 意外收获：瓶颈居然在压测客户端

第一版对照组只跑出 **7 笔**重复支付，而不是预期的 20 笔。查下去发现**问题不在服务端，
在我自己的脚本**：

| | 发请求方式 | 20 个请求实际到达间隔 | 重复支付 |
|---|---|---|---|
| 第一版 | `urllib.request.urlopen()`，**每次新开一条 TCP** | ~165ms | **7 笔** |
| 改进版 | **预热连接**（先 `GET /api/hello` 建连，屏障放行后复用同一条 socket） | ~35ms | **12 笔** |

原因是 `urlopen()` 每次建连，而建连被 Python 的 GIL 串行化 → 20 个"同时"启动的线程
实际间隔 8ms 一个。**竞态窗口是有限的**（从最早的 ① 读 到 最早的 COMMIT），
到达晚了的线程在 ① 读到的是 `PAID`，于是被**正确地**拒绝了（8 个 400 就是这么来的）。

两条结论：

1. **做并发测试前，先确认你的客户端真的是并发的。** 否则你测出来的是客户端有多串行。
2. **破坏力 ∝ 落在竞态窗口内的线程数**。不是「只要并发就一定 20/20」——
   这恰恰说明 CAS 的防线是渐进的：窗口越短、防线越紧。

> 想跑出更震撼的 20/20，只能在代码里人为塞一个 sleep 把窗口撑开（属于演示手法）；
> 或者用 ab / k6 这类原生客户端。**演示归演示，真相是「窗口有限但真实存在」**。

### 11.6 还原：代码 + 数据 + 装备

| 项 | 做法 |
|---|---|
| 代码 | `git checkout --` 3 个文件 → 编译验证 `AND status` 回来（1 处）、`locked_stock >=` 回来（1 处）、Java 侧 `if` 消失（0 处） |
| 靶子数据 | `day13-restore.sql -v target=2` → `DELETE 12` 行支付、状态回 `PENDING_PAYMENT`、库存复原 |
| 装备 | `day13-audit-teardown.sql` 拆掉触发器 + 函数 + 表 |
| 运行环境 | 杀进程 → `install` → 按**默认连接池**重启 |

⚠️ **顺手修掉回滚 SQL 的一个真 bug**：原版只按「1 次支付」的量还原（`locked + qty`），
但对照组实际扣了 N 次 → **会还原不足、残留负库存，而且静默不报错**。
改成从 `payments` 实际行数现算倍数（`qty * times`）后，主组（N=1）和对照组（N=12）都正确。

**反证（很重要）**：还原后对**已经支付的** `#1` 再发一次支付请求 →
`{"code":400,"message":"订单状态不允许支付"}`，说明 CAS 真的回来了，不是「看起来干净」。

### 11.7 第 3 步结束时的基线

```
orders     : #1 PAID(31997)   #2 PENDING_PAYMENT(19497)   #9002 PAID(24998)
payments   : 2 行     payments_id_seq.last_value = 103（烧掉的 id 看着大，是正常的）
inventories: sku3 60/56/0/4   sku4 150/147/1/2   sku5 120/117/3/0   恒等式全 t
触发器/审计表: 已拆除
应用        : 默认连接池重启，/api/payments 在线
```

---

## 十二、第 4 步 · 支付记录查询（规划）

### 12.1 一句话战场：`payments` 表【没有 user_id】

```sql
payments : id, payment_no, order_id, amount, method, status, paid_at, created_at, updated_at   -- 9 列，没有 user_id
orders   : id, user_id, ...                                                                     -- 归属在这张表上
```

⇒ 「只查我自己的支付记录」这句话，在 `payments` 上**无处可写** ——
归属条件必须**跨表落到 `orders.user_id`**。这是本步唯一的新知识点，也是唯一真正的坑。

⚠️ 由这一点还引出一条安全事实：**支付记录的越权泄漏比订单更严重** ——
它一次暴露「买了什么价、用的什么方式、什么时候付的」。所以这个接口的归属校验
不是「顺手加一下」，而是本步的主体。

### 12.2 三种方案

| 方案 | 做法 | 分页 | 越权条件放哪 | 代价 |
|---|---|---|---|---|
| **A. XML JOIN（推荐）** | `payments p INNER JOIN orders o ON o.id=p.order_id WHERE o.user_id=#{userId}`；Mapper 方法**首参 `IPage`** | DB 真分页（MP 插件改写 SQL） | **SQL 的 WHERE 里** | 新写一个 XML 文件 |
| B. 两段式（Java join） | 先 `orderMapper.selectList(eq(userId))` 拿订单 id+orderNo → 再 `in(Payment::getOrderId, ids)` | DB 真分页 | Java 组装 | 订单多了 `IN` 列表爆炸；两次查询；`orderNo` 要手工 map |
| C. 子查询 `inSql` | `.inSql(Payment::getOrderId, "SELECT id FROM orders WHERE user_id=" + userId)` | DB 真分页 | SQL 里（但是拼字符串） | 拼字符串习惯差；`IN` 语义在订单多时同样退化 |

**选 A**，三个理由：
1. 一条 SQL 同时拿到 `payments` 全部字段 + `orders.order_no`（`PaymentVO` 正好有这个字段，直接复用，**不用新建 VO**）；
2. 分页在数据库层完成（不是查全表再内存切）；
3. 越权条件**天然进 WHERE** —— 与 Day 12 的 `selectAddressForOrder` 完全同构，查不到就是 null，上层统一 404。

### 12.3 文件清单（1 新 + 6 改）

| 文件 | 类型 | 要点 |
|---|---|---|
| `mall-payment/.../vo/PaymentVO.java` | 改 | **加 `@NoArgsConstructor`** ← 见 12.5 坑① |
| `mall-payment/.../mapper/PaymentMapper.java` | 改 | +2 方法，**首参必须是 `IPage`** |
| `mall-payment/src/main/resources/mapper/PaymentMapper.xml` | **新** | ⚠️ 目录要新建（现在整个 `resources/` 都不存在） |
| `mall-payment/.../service/PaymentService.java` | 改 | +2 签名 |
| `mall-payment/.../service/impl/PaymentServiceImpl.java` | 改 | +2 实现 + `MAX_PAGE_SIZE` 常量 |
| `mall-payment/.../controller/PaymentController.java` | 改 | +2 个 `@GetMapping` |
| `mall-payment/pom.xml` | — | **不用动**（`mall-common`/`mall-order` 已在） |

### 12.4 六个决定

1. **INNER JOIN，不是 LEFT JOIN** —— `payments.order_id` 是 `NOT NULL` + 外键，行行都能在 `orders` 找到；LEFT JOIN 在这里是错的心智模型（还会让 count 变松）。**这是全项目第一个真正的 JOIN 查询**（Day 12 的 `selectSelectedCartItems` 是 4 表 LEFT JOIN，动机不同）。
2. **列名显式列出，禁止 `p.*`** —— 将来 `payments` 加一列敏感字段（如 `channel_trade_no`），`p.*` 会**当场泄漏**；显式列 = 出参白名单。
3. **详情接口的归属条件同样写进 SQL** —— `WHERE p.id=#{id} AND o.user_id=#{userId}`。禁止「先 `selectById` 再 Java 比」：`payments` 根本没有 `user_id` 可比，硬比就得再查一次订单，白多一次往返。
4. **404 的两种原因不可区分**（id 不存在 / 是别人的）—— 同 Day 12 的 `requireOwn`，防枚举攻击。
5. **分页夹紧照抄 `listMyOrders`** —— `Math.max(page, 1)` + `Math.min(Math.max(size, 1), 100)`。理由与三种静默变形（`size=-1` 查全表 / `size=0` 空列表 / `size=99999` 全表拖走）见 §10 ... `listMyOrders` 的 Javadoc。`MAX_PAGE_SIZE` 在本模块再定义一份（跨模块抽公共常量属于重构，不塞进本步）。
6. **不过滤 `status`** —— V1.0 只有 `SUCCESS`；真实业务里失败 / 退款记录**也要展示**，所以先别写 `WHERE status='SUCCESS'`，那是把未来的自己坑住。

### 12.5 两个坑（都是「编译通过、运行才炸」）

**坑① `PaymentVO` 没有无参构造 → MyBatis 反射建对象失败**

`@Data` + `@AllArgsConstructor` ⇒ Lombok **不再生成无参构造** ⇒ 使用 `resultType="com.mallx.payment.vo.PaymentVO"` 时，
MyBatis 在 `DefaultObjectFactory.create()` 里 `getDeclaredConstructor()` 直接抛 `NoSuchMethodException`。
症状：

```
ReflectionException: Error instantiating class com.mallx.payment.vo.PaymentVO
    with invalid types () or values (). Cause: java.lang.NoSuchMethodException: ...<init>()
```

修法：类上加 `@NoArgsConstructor`（与 `@AllArgsConstructor` 共存，第 2 步那句 `new PaymentVO(...)` 照旧可用）。
★ 顺手要改 `PaymentVO` 的 Javadoc —— 现在写的是「一旦有它，Lombok 就不再生成无参构造 → 不能 `new PaymentVO()` 再 setter」，加了注解后这句话就**讲反了**。

**坑② XML 必须放 `src/main/resources/mapper/`，而该目录现在不存在**

`mall-payment/src/main/resources/` 目前**整个目录都没有**（第 1~3 步这张表只写不读，没写过 XML）。
放 `src/main/java` 下 Maven **不复制**；`mapper-locations: classpath*:mapper/**/*.xml` 靠 `classpath*` 才能扫到 jar 内的 XML。
症状：

```
Invalid bound statement (not found): com.mallx.payment.mapper.PaymentMapper.selectMyPayments
```

（外加铁律③：接口方法名与 XML `id` 必须**逐字符一致**，差一个 `s` 就报上面这个错。）

### 12.6 验收 8 项（靶子现成，不用造数据）

| 账号 | 现状 |
|---|---|
| `demo / demo123`（users.id=**1**） | 3 张订单、**2 条支付记录**：`id=2`→order 9002（24998 元）、`id=44`→order 1（31997 元） |
| `intruder / intruder`（users.id=**2**） | **0 张订单、0 条支付记录** ← 天然攻击者账号（Day 12 建的） |

| # | 请求 | 期望 |
|---|---|---|
| 1 | `GET /api/payments`（demo） | `total=2`，`records[0].id=44`（**倒序**），且每行 `orderNo` **有值**（JOIN 生效） |
| 2 | `GET /api/payments`（**intruder**） | `total=0`、`records=[]` ← ★ **本步最重要的一条：只查自己的** |
| 3 | `GET /api/payments?size=99999`（demo） | 回显 `size=100`（夹紧） |
| 4 | `GET /api/payments?size=0`（demo） | 回显 `size=1`、返回 **1 条**（不是空列表） |
| 5 | `GET /api/payments/44`（demo） | 200，返回 `id=44 / orderNo=MX...060` |
| 6 | `GET /api/payments/44`（**intruder**） | **404「支付记录不存在」**（同一条记录、两个身份、两种结果 = IDOR 铁证） |
| 7 | `GET /api/payments/999999`（demo） | 404 **同款消息**（与 #6 不可区分） |
| 8 | 任意接口不带 token | **401** |

★ #5 + #6 是同一条 `payments` 记录 `id=44`：demo 看得到、intruder 看不到 ——
这比任何文字说明都有力。

### 12.7 零重启负向对照实测（psql 直连，7 组）

脚本 `backend/loadtest/day13-s4-idor-contrast.sql`，把「带 / 不带归属条件」的 SQL 并排跑一遍 ——
**结果集自己会说话**（同一份数据、同一条记录，只是 WHERE 差一个条件）：

| # | SQL | 身份 | 结果 |
|---|---|---|---|
| ① | 带 `o.user_id=1` 的列表 | demo | **2 行**（`id=44` 在前，倒序 ✅） |
| ② | 带 `o.user_id=2` 的列表 | intruder | **0 行** ✅ |
| ③ | **漏掉**归属条件的列表 | 任何登录用户 | **2 行全泄漏**（31997 WECHAT + 24998 ALIPAY） |
| ④ | 详情**只按** `p.id=44` | intruder | **1 行泄漏**（31997 元那张单） |
| ⑤ | 详情带 `AND o.user_id=2` | intruder | **0 行** ✅ |
| ⑥ | 详情带 `AND o.user_id=1` | demo | **1 行** ✅ |
| ⑦ | `INNER JOIN` vs `LEFT JOIN` 的 count | — | 2 / 2（本数据集不分叉） |

★ ③④ 就是「少写一行 WHERE 的代价」：泄漏的不是订单号，而是**金额 + 支付方式 + 支付时间**。
★ ⑤⑥ 打的是**同一条 `payments.id=44`**：demo 看得到、intruder 看不到 —— IDOR 伪装的可观测形态。
★ ⑦ 要诚实：本数据集上 INNER 与 LEFT 结果相同，**不是**因为 LEFT 也对，而是外键
  `fk_payment_order` 保证了 payments 里不存在孤儿行。用 INNER 是把「这个前提当前成立」
  写进 SQL，而不是靠运气。

⚠️ 顺手记一个工具坑：psql 的 `\echo '中文'` 在 docker exec 通道里会显示成 `?`
（`PGCLIENTENCODING` 管不到 `\echo` 的客户端输出），**但 `SELECT` 的结果集中文完全正常**
—— 别因此以为数据坏了，标签改用英文即可。

---

## 十三、第 4 步 · 骨架与自检（自己敲，AI 只审）

### 13.1 接口契约（三处必须逐字符对上，否则 `Invalid bound statement`）

**`PaymentMapper.java`**（+2 方法，★ **首参必须是 `IPage`**，否则分页插件不拦、静默查全表）：

```java
IPage<PaymentVO> selectMyPayments(IPage<PaymentVO> page, @Param("userId") Long userId);

PaymentVO selectMyPaymentById(@Param("paymentId") Long paymentId,
                              @Param("userId") Long userId);
```

**`PaymentMapper.xml`**（新建 `mall-payment/src/main/resources/mapper/PaymentMapper.xml`）：
`namespace` = 上面那个接口全限定名，两个 `id` 与方法名**逐字符一致**；
`resultType` = `com.mallx.payment.vo.PaymentVO`（不是实体 `Payment` —— 因为要带 `order_no`）。

**`PaymentService.java`**（+2 签名）：

```java
PageResult<PaymentVO> listMyPayments(Long userId, long page, long size);

PaymentVO detailMyPayment(Long userId, Long paymentId);
```

**`PaymentController.java`**（+2 个 `@GetMapping`，路径与 `POST /api/payments` 不冲突）：

```java
@GetMapping            → Result<PageResult<PaymentVO>> list(Authentication, page, size)   // 带 defaultValue
@GetMapping("/{id}")   → Result<PaymentVO>            detail(Authentication, @PathVariable Long id)
```

### 13.2 三处「填空点」（本步的全部智力都在这里）

| 填空点 | 写在哪 | 判断标准 |
|---|---|---|
| ① 分页夹紧 | `listMyPayments` 第一二行 | `size` 那一行才是救命的，`page` 那行是规范化（见 `listMyOrders` Javadoc） |
| ② 归属条件 | **XML 的 WHERE 里**，不是 Java 的 `if` | 详情那句要写成 `WHERE p.id = #{paymentId} AND o.user_id = #{userId}` |
| ③ 404 分支 | `detailMyPayment` | `vo == null` → `BusinessException(NOT_FOUND, "支付记录不存在")`；**两种 null 原因共用同一句消息** |

### 13.3 敲完的自检（编译前扫一遍）

- [ ] `PaymentVO` 加了 `@NoArgsConstructor`（否则运行期 `NoSuchMethodException`）
- [ ] XML 在 `src/main/resources/mapper/` 下，且 `resources/` 目录是新建的
- [ ] `IPage` 的 import 是 `com.baomidou.mybatisplus.core.metadata.IPage`（不是 `extension` 里的 `Page` 张冠李戴）
- [ ] XML 列名与 VO 字段靠 `map-underscore-to-camel-case` 对齐：`payment_no→paymentNo`、`order_no→orderNo`、`paid_at→paidAt`
- [ ] 列**显式列出**，没写 `p.*`
- [ ] `ORDER BY p.id DESC`（不带排序的分页是随机翻页）
- [ ] `PaymentMapper.xml` 里**没有** `--` 形式的注释（XML 铁律④，会 `SAXParseException`）
- [ ] 改完 `PaymentVO` 的 Javadoc（原来那句「不能 `new PaymentVO()` 再 setter」现在讲反了）

### 13.4 你敲完，我会照 §12.6 的 8 项跑一遍

外加两条我会额外查的：
- `GET /api/payments?size=-1` —— 夹紧后应返回 1 条（**不夹紧会返回全表**）
- `payment_no` 有没有在列表里被 `p.*` 之外的别名写错（对齐失败时 MyBatis 不报错，只是字段为 `null` —— **静默**）

---

## 十四、第 4 步实测：支付记录查询（分页夹紧 + IDOR）✅

### 14.1 产出（1 新 + 6 改，POM 未动）

| 文件 | 类型 | 要点 |
|---|---|---|
| `mall-payment/src/main/resources/mapper/PaymentMapper.xml` | **新** | 目录一并新建（此前 `resources/` 整个不存在） |
| `mall-payment/.../vo/PaymentVO.java` | 改 | **+`@NoArgsConstructor`**（坑①）+ 改「无参构造」那段 Javadoc（原话讲反了） |
| `mall-payment/.../mapper/PaymentMapper.java` | 改 | +2 方法（首参 `IPage`）+3 import；类头 Javadoc 从「本表不需要 XML」改成「查询必须写 XML」 |
| `mall-payment/.../service/PaymentService.java` | 改 | +2 签名 |
| `mall-payment/.../service/impl/PaymentServiceImpl.java` | 改 | +`MAX_PAGE_SIZE` +2 实现 +3 import |
| `mall-payment/.../controller/PaymentController.java` | 改 | +2 个 `@GetMapping`（`GET /api/payments`、`GET /api/payments/{id}`） |

**一次编译通过（BUILD SUCCESS，26 s）**；`target/classes/mapper/PaymentMapper.xml` 已生成。

### 14.2 十一项验收（真机 curl，全绿）

| # | 请求 | 实测 |
|---|---|---|
| 1 | 匿名 `GET /api/payments` | `http=401 code=401 未登录或登录已过期` |
| 2 | demo 列表 | `total=2`、`records[0].id=44`（**倒序**）、**8 个字段全映射**（`paymentNo/orderId/orderNo/amount/method/status/paidAt`）|
| 3 | **intruder 列表** | `total=0 records=[]` ← ★ **越权防线生效**（库里 payments 明明有 2 行）|
| 4 | `?size=99999` | 回显 `size=100` |
| 5 | `?size=0` | 回显 `size=1`、返回 **1 条**（不是空列表）|
| 6 | `?size=-1` | 回显 `size=1`、返回 **1 条**（★ 不夹紧时这里会**返回全表**）|
| 7 | `?page=0` | `current=1 n=2`（MP 自保，无需干预）|
| 8 | demo `GET /api/payments/44` | 200 → `id=44 / orderNo=MX202609191040569691060 / 31997.00 / WECHAT` |
| 9 | **intruder `GET /api/payments/44`** | `code=404 支付记录不存在` |
| 10 | demo `GET /api/payments/999999` | `code=404 支付记录不存在` |
| 11 | demo `GET /api/payments/abc` | `code=400 参数 id 格式不正确` |

★★ **#9 与 #10 的响应逐字节相同**（脚本内实比 `body9 == body10` → `True`）：

```json
{"code":404,"message":"支付记录不存在","data":null}
```

「id 不存在」与「id 是别人的」在外部**完全不可区分** → 枚举攻击筛不出一条真实记录。

★ **#3 的证据结构**：库里 `payments` 有 2 行（`id=2` → order 9002、`id=44` → order 1，都属 users.id=1），
intruder 拿到 `total=0`。这与 Day 12 订单列表「demo 看到 `total=2` 而库里有 3 行」是**同一种证据**：
**分母里被减掉的那一行，就是越权防线存在的证明。**

### 14.3 三条技术佐证

1. **JOIN 的 count 正确**：`total=2`（不是 0 也不是全表）→ 分页插件对**自定义 XML** 生成的
   count 是对的（`SELECT COUNT(*) FROM payments p INNER JOIN orders o ...`，自动去掉 `ORDER BY`）。
2. **字段映射零静默失败**：`o.order_no → orderNo` 是本查询唯一来自 `orders` 的列，实测有值；
   `payment_no → paymentNo`、`paid_at → paidAt` 也都有值 → `map-underscore-to-camel-case` 生效。
   ⚠️ 这类错**不报警**，字段只会是 `null`，所以必须**逐字段肉眼确认**，不能只看 `code=200`。
3. **启动日志干净**：`ERROR count = 0`、`Invalid bound statement count = 0`。
   日志里 3 处 `Exception` 命中全是 `GlobalExceptionHandler` 的 **WARN** 常规记录，
   恰好对应验收 #9 / #10（业务 404）与 #11（参数类型不匹配）—— 是预期行为，不是故障。

### 14.4 两个坑的验证结果（都没炸）

- **坑①（`PaymentVO` 无参构造）**：写代码时就加了 `@NoArgsConstructor`，所以这次**没机会亲眼看见**
  `ReflectionException`。它的证据是**反过来的** —— 删掉那个注解，第 2 项立刻 500。★ 留作自证题。
- **坑②（XML 位置）**：`target/classes/mapper/PaymentMapper.xml` 存在 → `classpath*:mapper/**/*.xml`
  确实扫到了 jar 内的新 XML；`Invalid bound statement` 计数为 0。

### 14.5 环境与基线

```
orders     : #1 PAID(31997)   #2 PENDING_PAYMENT(19497)   #9002 PAID(24998)
payments   : 2 行（id=2 → order 9002 / id=44 → order 1）
users      : demo(id=1) / intruder(id=2)
Swagger    : 19 → 20 路径（新增 /api/payments/{id}）
启动       : Tomcat started on port 8080 + Global AuthenticationManager ... userDetailsServiceImpl ✅
```

### 14.6 收尾发现：push 静默失败的真凶是 `GIT_TERMINAL_PROMPT=0`

提交后照例 push（代理 `9674=True`）→ 又是 `rc=128` 且 stdout/stderr **全空**。逐项对照后定位：

| 方式 | `GIT_TERMINAL_PROMPT` | 结果 |
|---|---|---|
| PS `git push --dry-run` | 显式 `1` / `0` | ❌ 两种都 `rc=128` 零输出 |
| Python `subprocess.run(...)` | 继承会话的 `0` | ❌ `rc=128` 零输出 |
| **Python `subprocess.run(...)`** | **显式 `"1"`** | ✅ `rc=0`，`ae9f2c4..8916f1e  main -> main` |

⇒ 会话环境注入了 **`GIT_TERMINAL_PROMPT=0`**，**连 Python 也救不了**；必须显式覆盖成 `1`。

★ 更隐蔽的一层：`win-git-push/scripts/push.py` 里**自己主动写死**了 `env["GIT_TERMINAL_PROMPT"] = "0"`
（Day 12 加的，当时误以为「禁止交互」更安全）——
所以「用 Python 就稳」这条经验**一直带着一个隐藏前提**在生效，直到这次才暴露。
→ 已把脚本改成 `"1"`，并同步更新 `SKILL.md`（顶部「两个坑」→「三个坑」+ 六行对照表 + 三步排查顺序）。

★ 三重验证：`local head == remote head == 8916f1e`，`git status -sb` 不再 ahead ✅。


