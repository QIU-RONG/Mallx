# Day 12：从购物车下单（mall-order + mall-inventory）

> 配套讲解：`并发扣库存_先查后改与条件更新对照`（本轮对话里的那张图）

---

## 0. 今天要达成什么

一句话：**把用户购物车里「已勾选」的商品，变成一张订单 —— 并且保证库存不会被卖穿。**

三个接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/orders` | 从购物车下单（body 只有 `addressId`），返回订单 id |
| `GET` | `/api/orders` | 我的订单列表（分页） |
| `GET` | `/api/orders/{id}` | 订单详情（含明细；非本人 404） |

### 为什么今天值一天

前面 11 天，每个请求都在动**一行或一片自己的数据**。今天第一次出现**多方争抢同一份资源**：`inventories.available_stock` 是全场唯一一条被所有用户共同读写的记录。

```
Day 10 购物车：这行是不是你的？      → 行级私有
Day 11 收货地址：你这堆行不能自相矛盾？ → 跨行不变式（事务）
Day 12 下单：100 个人抢 10 件，谁该赢？  → 并发竞争（原子性 + 条件更新）
```

「库存不能变负」这条规则，**不是靠事务就能守住的** —— 事务保证「要么全做要么全不做」，但两个事务各自都合法地执行完，结果照样超卖。今天要学的是**在事务之上再加一层：把判断和写入压成一个原子动作**。

---

## 1. 现状调研（全部实测过）

### 1.1 `orders`（15 列，实测）

| 列 | 类型 | 约束 | 备注 |
|---|---|---|---|
| `id` | bigint | PK, `nextval` | |
| `order_no` | varchar | **NOT NULL + UNIQUE** | 订单号，唯一索引 `orders_order_no_key` |
| `user_id` | bigint | NOT NULL, FK→users | |
| `total_amount` | numeric | NOT NULL | 商品总额 |
| `pay_amount` | numeric | NOT NULL | 实付（V1.0 无优惠，= total） |
| `status` | varchar | NOT NULL | 订单状态，VARCHAR 无 CHECK 约束 |
| `receiver_name` / `receiver_phone` / `receiver_address` | varchar | NOT NULL | ★ **收货信息快照**（不是 `address_id`） |
| `created_at` / `updated_at` | timestamp | NOT NULL | 走 `@TableField(fill)` |
| `paid_at` / `shipped_at` / `completed_at` / `cancelled_at` | timestamp | **可空** | ★ 业务时间戳，由业务代码手写，**不要**挂 `fill` |

- ⚠️ **无 `is_deleted` 列** → 禁止 `@TableLogic`（同 `user_addresses`）
- 已有索引：`orders_order_no_key`(UNIQUE) / `idx_orders_user_id` / `idx_orders_status` / `idx_orders_created_at` —— 列表查询（`user_id` + 时间倒序）现成的，不用加

### 1.2 `order_items`（11 列，实测）

| 列 | 类型 | 备注 |
|---|---|---|
| `id` | bigint | PK |
| `order_id` | bigint | FK→orders，`idx_order_items_order_id` |
| `product_id` / `sku_id` | bigint | 只有 id，**没有外键** |
| `product_name` | varchar **NOT NULL** | ★ 商品名快照 |
| `sku_name` | varchar 可空 | ★ 规格名快照 |
| `price` | numeric NOT NULL | ★ **下单时的单价**快照 |
| `quantity` / `total_amount` | int / numeric | |
| `image` | varchar 可空 | 图片快照 |
| `created_at` | timestamp | ⚠️ **没有 `updated_at`** → 实体只填 `createdAt` |

### 1.3 `inventories`（已实测）

```
 sku_id | total_stock | available_stock | locked_stock | sold_stock
    1   |     100     |       96        |      2       |     2
    2   |      80     |       78        |      0       |     2
    3   |      60     |       60        |      0       |     0
    4   |     150     |      148        |      1       |     1
    5   |     120     |      120        |      0       |     0
    6   |      40     |       39        |      1       |     0
    7   |      90     |       90        |      0       |     0
```

`sku_id` 上有 **UNIQUE 约束**（`inventories_sku_id_key`）→ 一 SKU 一行，条件 UPDATE 命中唯一行。

**四个字段的账（恒等式）**：

```
total_stock = available_stock + locked_stock + sold_stock
   100      =       96       +      2       +     2        ✓
```

- `available` = 现在还能卖多少
- `locked` = 已被订单占用、还没付款（**今天要往这里搬**）
- `sold` = 已付款成交（Day 13 支付成功时 locked → sold）

⚠️ 种子里 `locked` / `sold` 已有非零值，那是「历史遗留数据」，不影响今天的验证 —— 但基线断言要按**实测值**比，别按 0 比。

### 1.4 基线（实测，2026-09-19 10:05）

```
users=1 | user_addresses=0 | cart_items=0 | orders=0 | order_items=0 | inventories=7 | products=5
```

⚠️ `user_addresses=0` —— 第 12 步要下单必须先有地址，测试前用 `POST /api/addresses` 现造一条。

### 1.5 环境

- 应用 8080 ✅ / PG 5434 ✅（都热着，还在跑）
- Swagger 现 **16 个路径**，今天要涨到 **19**
- 白名单里没有 `/api/orders/**` → 落 `anyRequest().authenticated()` → **Security 一行都不用改**

### 1.6 模块落位：要动 2 个 POM

| 模块 | 现状 | 今天要做什么 |
|---|---|---|
| `mall-inventory` | **空壳**（`src` 下无文件），POM 只依赖 mall-common | 建库存实体 / Mapper / Service —— **今天它开张** |
| `mall-order` | **空壳**（`src` 下无文件），POM 只依赖 mall-common | 建订单全套 + **加一条 `mall-inventory` 依赖** |

`mall-order/pom.xml` 要加：

```xml
        <dependency>
            <groupId>com.mallx</groupId>
            <artifactId>mall-inventory</artifactId>
        </dependency>
```

版本不用写 —— 父 POM 的 `<dependencyManagement>` 已经托管了全部 9 个子模块坐标。

**为什么扣库存要单独放 `mall-inventory`，而不是在 order 的 XML 里直接 UPDATE？**

因为「库存怎么扣」属于库存领域的规则。以后加「秒杀限购」「库存预占超时释放」「盘点」都会落在同一个模块里。`mall-order` 只负责「我需要扣 3 个 SKU」，扣的细节不外泄 —— 这就是模块化单体的边界感。

> 跨模块调用 = 同一个 JVM 里的普通 Spring Bean 调用，`@Transactional` 默认传播 `REQUIRED` → **自动加入调用方的事务**，不需要任何额外配置。这是 Day 12 要顺带确认的一件事。

### 1.7 全项目第一次「多表写入 + 并发」，前 11 天没碰过

| 之前的写操作 | 今天的写操作 |
|---|---|
| 单表 INSERT / UPDATE / DELETE | **5 张表**：`inventories`(UPDATE) + `orders`(INSERT) + `order_items`(INSERT×N) + `cart_items`(DELETE) |
| 无并发压力 | 多用户争抢同一行库存 |

---

## 2. 接口设计（3 个）

### `POST /api/orders` —— 从购物车下单

```
Header: Authorization: Bearer <token>
Body:   { "addressId": 1 }
返回:   Result<Long>   ← 订单 id
```

**为什么 body 里是 `addressId` 而不是收货信息**：地址是用户维护的独立资源，下单时按 id 引用、把内容**拷贝成快照**存进 `orders`。这样用户事后改地址或删地址，历史订单不受影响。

**为什么 body 里没有 `skuIds` / `quantity`**：下单项的唯一来源是**购物车里 `selected = true` 的行**。客户端只表达「用哪个地址」，不表达「买什么、买几件」—— 少一个可以被伪造的输入面。

### `GET /api/orders?page=1&size=10`

```
返回: Result<PageResult<OrderVO>>
```
按 `created_at DESC` 排（新的在前）。

### `GET /api/orders/{id}`

```
返回: Result<OrderDetailVO>   ← 订单头 + List<OrderItemVO>
非本人 → code 404「订单不存在」
```

---

## 3. 核心难点讲解

### 3.1 ★★★ 并发扣库存：把判断塞进 `UPDATE` 的 WHERE

这是今天的全部重点。上面那张图是结论，这里说清**为什么**。

**错误写法（几乎所有人第一版都会这么写）**：

```java
Inventory inv = inventoryMapper.selectById(skuId);      // ① 查
if (inv.getAvailableStock() < quantity) {               // ② 判断
    throw new BusinessException(...);                   // ③ 拒绝
}
inv.setAvailableStock(inv.getAvailableStock() - quantity);
inventoryMapper.updateById(inv);                        // ④ 写
```

**它在单线程下 100% 正确，在并发下必然超卖。** 因为 ①②之间、②④之间有**时间窗**：

```
时刻  A 线程                      B 线程                    DB available_stock
 t1   ① 读到 1                                              1
 t2                              ① 读到 1                   1
 t3   ② 1 >= 1 够卖 ✓                                       1
 t4                              ② 1 >= 1 够卖 ✓            1
 t5   ④ 算出 0，写 0                                         0
 t6                              ④ 算出 0，写 0             0      ← 卖出 2 件，库存只减了 1
```

这个模式有个名字：**check-then-act（先检查后执行）**。它的问题不是"写得不好看"，而是**检查和执行是两个独立的原子动作，中间可以被别人插进来**。

**正确写法：把条件写进 `UPDATE` 的 `WHERE`，用影响行数当答案**：

```sql
UPDATE inventories
   SET available_stock = available_stock - #{quantity},
       locked_stock    = locked_stock    + #{quantity},
       updated_at      = CURRENT_TIMESTAMP
 WHERE sku_id = #{skuId}
   AND available_stock >= #{quantity}
```

```java
int affected = inventoryMapper.deductStock(skuId, quantity);
if (affected == 0) {
    throw new BusinessException(VALIDATE_FAILED, "库存不足");
}
```

为什么这样就对了 —— 三个关键点：

| 点 | 说明 |
|---|---|
| **`SET x = x - n` 而不是 `SET x = 具体值`** | 减法由**数据库**做，不是 Java 算完再写。Java 算的前提是"我知道当前值"，而这个前提在并发下不成立 |
| **`WHERE available_stock >= n` 是判断** | 判断和执行在同一条 SQL 里 → 数据库保证这一条语句是原子的 |
| **影响行数就是答案** | `1` = 扣成功；`0` = WHERE 不成立（库存不够）或 sku 不存在。**不需要再查一次** |

PostgreSQL 执行这条 UPDATE 时会给命中行加**行级排他锁**，第二条 UPDATE 必须等第一条提交/回滚 —— 相当于数据库帮你把两个并发请求**排队**了。这就是图右边那两块。

> ⚠️ 「判断 + 写入」这件事，凡是能用一条带 WHERE 的 UPDATE 表达，就**绝不要**拆成两条语句。数据库的原子性是免费的，应用层的原子性要自己拿锁换。

### 3.2 ★★ 为什么不能用 `updateById` 扣库存

MP 的 `updateById(entity)` 生成的是**全字段覆盖**：

```sql
UPDATE inventories SET total_stock=?, available_stock=?, locked_stock=?, sold_stock=?, ... WHERE id=?
```

即使你只想改 `available_stock`，它也会把**读到的那一刻的其他字段值原样写回去** —— 如果中间别人改了 `locked_stock`，你的 `updateById` 会把它**覆盖回旧值**（丢失更新 / lost update）。这是比超卖更隐蔽的数据损坏。

所以扣库存必须走**只写需要改变的列 + 带条件**的自定义 SQL。MP 里两条路：

| 方式 | 用法 | 评价 |
|---|---|---|
| `UpdateWrapper.setSql("available_stock = available_stock - " + n)` | 字符串拼接 | ⚠️ 拼字符串，有注入风险（哪怕 n 是 Integer 也不推荐养成习惯） |
| **XML 手写 `UPDATE`** | `#{}` 参数化 | ✅ 本次采用，也是全项目第一个**写操作** XML |

### 3.3 ★ 多 SKU 扣减必须按 `sku_id` 升序

一个订单有 3 个 SKU，就得执行 3 次 UPDATE。**顺序不能按购物车里的顺序，必须按 `sku_id` 升序**。

原因 —— 两个订单交叉持锁会死锁：

```
订单 M（先扣 5，再扣 3）          订单 N（先扣 3，再扣 5）
 拿到 5 的行锁，等 3                拿到 3 的行锁，等 5
        ↓                                ↓
     互相等对方释放 → PostgreSQL 检测到死锁，杀掉其中一个事务（SQLState 40P01）
```

只要**所有事务都按同一个固定顺序**取锁（升序最自然），环形等待就不可能形成，死锁消失。这是"锁顺序"这个通用原则在数据库里的具体样子。

一句话口诀：**同一批资源，谁都得按同一个顺序排队。**

### 3.4 ★ 订单快照：`order_items` 为什么冗余存商品名和价格

`order_items` 明明可以 `sku_id` 关联 `product_skus` 实时查，为什么还要把 `product_name` / `sku_name` / `price` / `image` 拷一份？

因为商品是**会被改的**：

| 场景 | 如果实时关联 | 快照方案 |
|---|---|---|
| 商家把价格从 9999 改成 8888 | 三个月前的订单显示 8888 → **对账对不上** | 订单里永远是 9999 ✓ |
| 商品改名 / 下架 / 软删 | 订单里名字变空或消失 | 订单里名字原样保留 ✓ |
| SKU 被删 | 订单查不出东西 | 完好 ✓ |

**订单是「某个时间点的商业事实」，一旦写下就不能被后续的商品维护改口。** 所以：`snapshot（快照）` 而不是 `reference（引用）`。

这也是订单模块**不需要**对 `product_skus` 建外键的原因（`order_items` 里 `product_id` / `sku_id` 都只是裸 bigint）。

### 3.5 订单号生成

`orders.order_no` 有 **UNIQUE 约束**，所以生成规则只要满足两点：基本不撞、撞了能被数据库拦住。

本次方案：

```java
String orderNo = "MX"
        + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS"))
        + String.format("%04d", ThreadLocalRandom.current().nextInt(10_000));
// 例：MX202609191030151238472
```

- 长度 23，`VARCHAR(50)` 装得下
- `SSS` 毫秒 + 4 位随机 → 同一毫秒内还有 1 万种可能
- **唯一索引是最终防线**：真撞了会抛 23505（`DuplicateKeyException`），而不是悄悄写进两条相同订单号

> ⚠️ 这是**够用**的方案，不是**生产级**方案。生产会用雪花算法（趋势递增、无中心依赖）或号段模式（一次从库里领 1000 个号，内存里发）。V1.0 不上这些。

### 3.6 事务边界：一次下单 = 一个事务

```java
@Transactional
public Long createFromCart(Long userId, OrderCreateDTO dto) {
    // ① 校验地址归属
    // ② 读选中项  →  ③ 校验失效  →  ④ 算金额
    // ⑤ 扣库存（逐个，按 sku_id 升序）
    // ⑥ 插 orders + order_items
    // ⑦ 清购物车选中项
}
```

**为什么整段必须一个事务**：⑤~⑦ 任何一步失败都要整体回滚。

| 失败点 | 若不在同一事务 |
|---|---|
| 第 3 个 SKU 库存不足 | 前 2 个的库存**已经被扣掉了**，用户的购物车却还在 → 凭空少货 |
| 插入订单失败 | 库存扣了、购物车清了，但**订单没生成** → 用户钱货两空（V1.0 无支付，但库存丢了） |
| 清购物车失败 | 订单成了、库存扣了，购物车里东西还在 → 用户重复下单 |

⚠️ 因此：**这个方法的异常必须往外抛**。如果你在里面 `try-catch` 吞掉业务异常再返回，事务**不会回滚**（`@Transactional` 只认抛出的异常）。统一由 `GlobalExceptionHandler` 在外层转成 body 里的 `code` —— 这也正好符合项目「HTTP 200 + body code」的既有约定。

---

## 4. 分步任务

### 第 1 步：让 `mall-inventory` 开张（实体 + 条件扣减 + 冒烟）

**新建**（`com.mallx.inventory` 下）：

```
backend/mallx/mall-inventory/src/main/java/com/mallx/inventory/
├── entity/Inventory.java              ← 新建
├── mapper/InventoryMapper.java        ← 新建（★ 自定义 deductStock）
├── service/InventoryService.java      ← 新建
└── service/impl/InventoryServiceImpl.java ← 新建
backend/mallx/mall-inventory/src/main/resources/mapper/InventoryMapper.xml ← 新建
```

**`Inventory` 实体要盯的点**：

| 点 | 说明 |
|---|---|
| `@TableName("inventories")` | 类名 `Inventory` → 默认表名 `inventory`（少了 ies 变 y），必错 |
| 四个 `Integer` 字段 | `totalStock` / `availableStock` / `lockedStock` / `soldStock` |
| `createdAt` 用 `@TableField(fill = INSERT)`，`updatedAt` 用 `INSERT_UPDATE` | 与既有实体一致 |
| **不加 `@TableLogic`** | `inventories` 没有 `is_deleted` 列 |

**`InventoryMapper` 的关键方法**：

```java
    /** 扣减可售库存、同时锁入 locked_stock。返回影响行数：1=成功，0=库存不足 */
    int deductStock(@Param("skuId") Long skuId, @Param("quantity") int quantity);
```

**`InventoryMapper.xml`**（★ 今天最重要的一段 SQL）：

```xml
<update id="deductStock">
    UPDATE inventories
       SET available_stock = available_stock - #{quantity},
           locked_stock    = locked_stock    + #{quantity},
           updated_at      = CURRENT_TIMESTAMP
     WHERE sku_id = #{skuId}
       AND available_stock >= #{quantity}
</update>
```

⚠️ 注意这里**故意手写 `updated_at = CURRENT_TIMESTAMP`** —— 不靠 `MetaObjectHandler`（它是给 `updateById` 走的填充链，自定义 XML UPDATE 根本不经过它）。

**`InventoryService`**：

```java
public interface InventoryService {
    /** 为订单锁定库存；不足则抛 BusinessException(400, "库存不足") */
    void deductForOrder(Long skuId, int quantity);
}
```

**第 1 步冒烟清单（8 项，真机跑）**：

| # | 断言 |
|---|---|
| 1 | `GET` 一条 inventory（`sku_id=3`，实测 `available=60 / locked=0`） |
| 2 | `deductStock(3, 1)` 返回 **1**（成功）→ 复查 `available=59 / locked=1` |
| 3 | `deductStock(3, 59)` 返回 **1** → `available=0 / locked=60`，**刚好扣完不报错**（关键边界：`>=` 而非 `>`） |
| 4 | `deductStock(3, 1)` 返回 **0**（库存为 0，扣不动） |
| 5 | `available_stock` **从未变成负数** |
| 6 | 恒等式 `total = available + locked + sold` 成立 |
| 7 | `deductStock(99999, 1)` 返回 **0**（sku 不存在，不抛异常） |
| 8 | 列表/`SELECT` 里 `available_stock` 正确回读（实体映射无误） |

跑完把库存改回原值（`available=60 / locked=0`），别留垃圾。

#### 第 1 步实测记录（2026-09-19 10:13，真机，✅ 已完成）

一次编译通过，**9 项全绿**（临时 `InventorySmokeRunner` 跑完即删）：

| # | 断言 | 实测 |
|---|---|---|
| 0 | 基线（`sku_id=3`） | `total=60 available=60 locked=0 sold=0` |
| 1 | `deductStock(3,10)` 返回 **1** | ✅ `rows=1` |
| 2 | `available` 精确 `-10` / `locked` 精确 `+10` | ✅ `available=50 locked=10` |
| 3 | 恒等式 `total = available + locked + sold` | ✅ `60 = 50 + 10 + 0` |
| 4 | 超量扣减 `999999` 返回 **0** | ✅ `rows=0` |
| 5 | 超量扣减后数据**一字未动** | ✅ 仍 `50 / 10` |
| 6 | Service 层超量 → `BusinessException` | ✅ `msg=库存不足` |
| 7 | ★ **刚好扣完**（`quantity == available == 50`）返回 1 且 `available=0` | ✅ 关键边界（`>=` 而非 `> `） |
| 8 | 归零后再扣 1 → 返回 0 且 `available` 不为负 | ✅ `rows=0 available=0` |
| 9 | 不存在的 sku → 返回 0（未抛 SQL 异常） | ✅ `rows=0` |

跑完已把 `sku_id=3` 复原为 `available=60 / locked=0`。

**SQL 实锤**（临时打开 `log-impl` 抓到的原文，已关回注释）：

```sql
SELECT id,sku_id,total_stock,available_stock,locked_stock,sold_stock,created_at,updated_at
  FROM inventories WHERE (sku_id = ?)
--  ↑ 列名映射全对，@TableName("inventories") 生效（否则这里就是 inventory，直接报表不存在）

UPDATE inventories
   SET available_stock = available_stock - ?, locked_stock = locked_stock + ?,
       updated_at = CURRENT_TIMESTAMP
 WHERE sku_id = ? AND available_stock >= ?
--                 ↑ ★ 判定条件确实在 WHERE 里，且是 >=
```

两点被 SQL 原文坐实：

1. **减法由数据库做** —— `available_stock - ?` 出现在 SQL 里，而不是 Java 算好新值再 `SET available_stock = ?`。这就是「原子动作」与「先查后改」的分水岭。
2. **手写的 `updated_at` 生效** —— 自定义 XML 的 UPDATE 不经过 `MetaObjectHandler`，漏了它这一格会永远停在旧时间（第 6 步的 `updateById` 则反之）。

**环境已复原**：`InventorySmokeRunner` 源码删除 + `mvn clean -pl mall-inventory` 清 class；`log-impl` 关回注释；重启后 `INVENTORY SMOKE` 0 条、`Preparing:` 0 条，验收行齐全。

> ⚠️ 本轮环境坑：`Remove-Item` 删临时源码**确实删掉了**，但整条 PowerShell 脚本在这一行之后被终止（后续 `mvn clean` / 重启全都没执行，几个 `.txt` 输出文件一个都没生成）—— 疑为沙箱拦截删除动作。**对策：清临时类只跑 `mvn clean -pl <模块>`，不在同一脚本里混 `Remove-Item`。**

---

### 第 2 步：下单主链路（★ 全部重点）

**改 1 个 POM**：`mall-order/pom.xml` 加 `mall-inventory` 依赖

**新建**（`com.mallx.order` 下）：

```
entity/Order.java                  entity/OrderItem.java
mapper/OrderMapper.java            mapper/OrderItemMapper.java
resources/mapper/OrderMapper.xml   ← 读 user_addresses + 读选中购物车
dto/OrderCreateDTO.java
vo/OrderVO.java  vo/OrderItemVO.java  vo/OrderDetailVO.java
vo/AddressForOrderVO.java          vo/OrderItemSourceVO.java
service/OrderService.java          service/impl/OrderServiceImpl.java
controller/OrderController.java
common/OrderStatus.java            ← 状态常量
```

**`OrderMapper.xml` 里两条 `SELECT`**：

```xml
<!-- 读地址：WHERE 里同时做 IDOR 校验 —— 不是自己的地址直接查不出来 → 404 -->
<select id="selectAddressForOrder" resultType="com.mallx.order.vo.AddressForOrderVO">
    SELECT receiver_name, receiver_phone, province, city, district, detail_address
      FROM user_addresses
     WHERE id = #{addressId} AND user_id = #{userId}
</select>

<!-- 读购物车里"已勾选"的项：跨模块 LEFT JOIN 三个表 -->
<select id="selectSelectedCartItems" resultType="com.mallx.order.vo.OrderItemSourceVO">
    SELECT c.id AS cart_item_id, c.sku_id, c.quantity,
           s.product_id, s.name AS sku_name, s.price,
           COALESCE(s.image, p.main_image) AS image, p.name AS product_name,
           p.status AS product_status,
           COALESCE(p.is_deleted, 0) AS product_deleted,
           COALESCE(s.is_deleted, 0) AS sku_deleted,
           COALESCE(i.available_stock, 0) AS available_stock
      FROM cart_items c
               LEFT JOIN product_skus s ON s.id = c.sku_id
               LEFT JOIN products     p ON p.id = s.product_id
               LEFT JOIN inventories  i ON i.sku_id = c.sku_id
     WHERE c.user_id = #{userId} AND c.selected = TRUE
</select>
```

⚠️ 规则同 Day 10：**必须 `LEFT JOIN` + 故意不加 `is_deleted=0` 过滤** —— 失效项要能被查出来**报错**，而不是悄悄消失。悄悄消失的后果是「用户以为买了 5 件，只收到 4 件」。

**`OrderServiceImpl.createFromCart` 逐步展开**：

| 步 | 做什么 | 失败怎么办 |
|---|---|---|
| ① | `selectAddressForOrder(addressId, userId)` | `null` → 404「地址不存在」 |
| ② | `selectSelectedCartItems(userId)` | 空 → 400「请先勾选要购买的商品」 |
| ③ | 逐项失效判定（顺序复刻 Day 10：规格删→商品删→下架→库存） | 400，消息里带**具体是哪件**（商品名 + 原因） |
| ④ | 算 `total_amount`（`BigDecimal`，`price × quantity` 求和） | |
| ⑤ | **按 `skuId` 升序排序**后逐个 `inventoryService.deductForOrder()` | 抛 400「库存不足」，整单回滚 |
| ⑥ | `orderMapper.insert(order)` → `orderItemMapper.insert()` × N | |
| ⑦ | `DELETE FROM cart_items WHERE user_id=? AND selected=TRUE` | |

**`③` 的判定顺序**（和 Day 10 一致 —— 先判最根本的原因）：

1. `sku_deleted = 1` → 「规格已删除」
2. `product_deleted = 1` → 「商品已删除」
3. `product_status ≠ 1` → 「商品已下架」
4. `quantity > available_stock` → 「库存不足（仅剩 N 件）」

> 第 4 条这里**可以有**（提前给出友好提示），**但不能只靠它** —— 真正的防线是第 ⑤ 步的条件 UPDATE。两者同时保留：前者负责「说人话」，后者负责「不出事」。

**`⑥` 的订单组装**：

```java
Order order = new Order();
order.setOrderNo(generateOrderNo());
order.setUserId(userId);
order.setTotalAmount(totalAmount);
order.setPayAmount(totalAmount);            // V1.0 无优惠
order.setStatus(OrderStatus.PENDING_PAYMENT);
order.setReceiverName(addr.getReceiverName());
order.setReceiverPhone(addr.getReceiverPhone());
order.setReceiverAddress(addr.getProvince() + addr.getCity() + addr.getDistrict() + addr.getDetailAddress());
orderMapper.insert(order);                  // ★ 插入后 id 自动回填
```

⚠️ 收货地址是**拼成一句话**存进单个 `receiver_address` 列（`广东省深圳市南山区科技园路1号A座1001`）—— 表里就是这么设计的，没有省市区三个独立列。

**`Order` 实体要盯的点**：

| 点 | 说明 |
|---|---|
| `@TableName("orders")` | 类名 `Order` → 默认表名 `order`。★ **`order` 是 SQL 保留字**！漏了注解会生成 `SELECT ... FROM order` 直接语法错误 |
| `id` 用 `@TableId(type = IdType.AUTO)` | 插入后要拿回 id 给 `order_items` 用 |
| `createdAt` / `updatedAt` 挂 fill | |
| `paidAt` / `shippedAt` / `completedAt` / `cancelledAt` | **不挂 fill**，业务代码手动 set |
| 不加 `@TableLogic` | 没这列 |

**`OrderItem` 实体**：只填 `createdAt`（表里没有 `updated_at`）。

**第 2 步验收（9 项）**：

| # | 场景 | 期望 |
|---|---|---|
| 1 | 匿名 `POST /api/orders` | 401 |
| 2 | 空购物车下单 | `code=400`「请先勾选要购买的商品」 |
| 3 | `addressId` 传别人的地址（造靶子） | `code=404`「地址不存在」 |
| 4 | 正常下单（购物车 2 项，都勾选） | `code=200`，返回订单 id |
| 5 | 查库 `orders` | 1 行，`status=PENDING_PAYMENT`，金额 = Σ(price×qty)，收货地址是拼接串 |
| 6 | 查库 `order_items` | 2 行，`product_name`/`price` **是快照值** |
| 7 | 查库 `inventories` | 对应 SKU `available -= qty`、`locked += qty`，恒等式成立 |
| 8 | 查库 `cart_items` | 已勾选的行**被清掉**；未勾选的行**还在** |
| 9 | 购物车里只勾选 1 项时下单 | `order_items` 只有 1 行，未勾选那项的库存**没动** |

#### 第 2 步实测记录（2026-09-19 10:40，真机，✅ 已完成）

**产出：15 个新文件（14 个 `.java` + 1 个 `OrderMapper.xml`）+ 1 处 POM 改动**（2a 结构层 12 个 + 2b 业务层 3 个）

| 层 | 文件 | 盯点 |
|---|---|---|
| 2a | `entity/Order.java` | ★ `@TableName("orders")`（`order` 是保留字）；4 个业务时间戳**不挂 fill** |
| 2a | `entity/OrderItem.java` | ⚠️ **只有 `createdAt`**，绝不写 `INSERT_UPDATE` |
| 2a | `common/OrderStatus.java` | 列无 CHECK，靠常量类当唯一真相源 |
| 2a | `mapper/OrderMapper.java` | 3 个方法 ↔ XML 3 个 id |
| 2a | `mapper/OrderItemMapper.java` | 纯 BaseMapper，**不需要 XML** |
| 2a | `resources/mapper/OrderMapper.xml` | 2 SELECT + 1 DELETE |
| 2a | `dto/OrderCreateDTO.java` | 只有 `addressId`（+`@NotNull`） |
| 2a | `vo/AddressForOrderVO.java` | 地址快照原料 |
| 2a | `vo/OrderItemSourceVO.java` | 购物车现场 + 4 个失效判定原料 |
| 2a | `vo/OrderVO.java` / `vo/OrderItemVO.java` / `vo/OrderDetailVO.java` | 均**不含 userId** |
| 2b | `service/OrderService.java` | 只定义 `createFromCart` |
| 2b | `service/impl/OrderServiceImpl.java` | ★★ `@Transactional` + 7 步 + 按 skuId 升序扣减 |
| 2b | `controller/OrderController.java` | `POST /api/orders`，无 `@PreAuthorize` |
| POM | `mall-order/pom.xml` | 加 `mall-inventory` 依赖（不写 version） |

**编译**：`BUILD SUCCESS`，mall-order 编译 **14 个源文件**；`mall-server` 已依赖 mall-order → **POM 只改 1 处**。

**9 项验收（真机 curl，全部通过）**：

| # | 场景 | 实测 |
|---|---|---|
| 1 | 匿名 `POST /api/orders` | ✅ `HTTP=401 code=401 未登录或登录已过期` |
| 2 | 空购物车下单（有合法地址） | ✅ `code=400 请先勾选要购买的商品` |
| 3 | `addressId=9001`（user_id=2 的地址） | ✅ `code=404 地址不存在`（靶子行未被读走） |
| 4 | 正常下单（勾选 sku3×2 + sku4×1，未勾 sku5×3） | ✅ `code=200`，订单 `id=1` |
| 5 | `orders` | ✅ 1 行：`order_no=MX202609191040569691060`、`total_amount=pay_amount=31997.00`（=2×12499+1×6999）、`status=PENDING_PAYMENT`、地址 `广东省深圳市南山区科技园路1号A座1001`、`paid_at` 为空 |
| 6 | `order_items` | ✅ 2 行，`product_name/sku_name/price/image` 全是快照（`Apple iPhone 17 Pro / 原色钛金属 512GB / 12499.00`） |
| 7 | `inventories` | ✅ sku3 `60→58 / locked 0→2`；sku4 `148→147 / locked 1→2`；**sku5 未勾选一字未动**；三个 `identity_ok=t` |
| 8 | `cart_items` | ✅ 勾选的 13/14 被清，未勾选的 15 还在（`selected=f`） |
| 9 | 只勾选 sku5 再下单 | ✅ `order_items` 只新增 1 行（订单 2 = sku5×3 = 19497.00）；sku5 `120→117 / locked 0→3`；**sku4 保持 147/2 不动**；购物车只剩未勾选的 16 |

**订单号实锤**：`MX202609191040569691060` = `MX` + 17 位时间 + 4 位随机 = **23 字符**，`VARCHAR(50)` 装得下。

**★ 实测暴露的一个顺序细节**：`createFromCart` 里 **① 地址校验在 ② 读购物车之前**，所以「空车下单」必须**同时给一个合法地址**才会走到 `400 请先勾选要购买的商品`；地址不合法时先报 `404 地址不存在`。两个失败原因同时存在时，**先报哪个由代码顺序决定** —— 写文档/写测试时别按直觉想当然。

**环境**：Swagger 路径数 **16 → 17**（`/api/orders` 已在列）；为验证新代码重启过一次应用，启动日志含 `Global AuthenticationManager configured with userDetailsServiceImpl`，无 ERROR。

**遗留**：`orders` 2 行 / `order_items` 3 行**保留**（第 3、4 步当样本）；`users.id=2 intruder` 保留（第 4 步造「别人的订单」靶子用）；`cart_items=0`；地址 `#1`（user_id=1）保留。

---

### 第 3 步：★★★ 并发压测 —— 证明它真的不会超卖

这一步是今天的高光。**不压测，前面所有的"应该不会超卖"都只是信仰。**

**准备**：把某个 SKU 的库存设成一个好观察的值（如 `sku_id=3` → `available=10, locked=0, sold=0`，`total=10`）。

**压测脚本**（Python 标准库 `threading` + `urllib`，20 个线程同时打）：

1. 前置：给用户建地址、往购物车塞这个 SKU（每次下单都要重新塞 —— 下单会清车）
2. 20 个线程同时 `POST /api/orders`
3. 统计：成功几个、失败几个、失败原因
4. **查库**：`available_stock` 最终值、`locked_stock`、恒等式

**断言**：

| # | 断言 |
|---|---|
| 1 | 成功数 **恰好 = 10**（不多不少） |
| 2 | 失败数 = 10，全部是 `code=400 库存不足`（不是 500！） |
| 3 | `available_stock` **最终 = 0，且压测过程中从未为负** |
| 4 | `locked_stock` 增加了 **10** |
| 5 | `orders` 表新增 **10** 行，`order_no` 全不重复 |
| 6 | 恒等式 `total = available + locked + sold` 仍成立 |

> ⚠️ 下单会清空购物车，所以 20 个线程不能靠"购物车里 20 份"。做法：**每个线程下单前先 `POST /api/cart` 加 1 件**（加购本身就带库存校验，会把一部分请求挡在购物车那一步 —— 所以要统计的是 `orders` 表的最终行数 vs 库存）。更干净的做法是**每个线程用不同的"下单量"**。
>
> 实操上我会这样设计：**循环 20 次「加购 1 件 → 下单」**，用 10 个线程并发跑，断言最终 `orders` 行数 = 10、`available` = 0。中途因为库存校验失败是正常的，关键看**有没有让库存变负 / 有没有 >10 个订单成功**。

**★ 对照实验（建议做，最有说服力）**：

临时把 `deductStock` 换成 Day 10 那种「先 `selectById` 判断、再 `updateById` 写入」的写法，重跑同一个压测 → **看它超卖**。然后把 XML 改回来。

亲手看见"错误写法真的会超卖"，这条知识才会长在你身上。做完记得 `git diff` 确认 XML 已还原。

#### ✅ 第 3 步实测记录（3 个实验，全部真机跑完）

**夹具**：`backend/loadtest/day12-loadtest-setup.sql`（纯 ASCII、幂等、可反复重跑）

| 项 | 值 |
|---|---|
| 并发主体 | `users 1001~1020` —— 20 个**独立账号**（`{noop}loadtest123`） |
| 地址 | 每人 1 条，id 固定 = `1000 + user_id` → 2001~2020 |
| 库存靶子 | `sku_id=3` → `total=10 / available=10 / locked=0` |
| 观测装置 | `inventories` 上挂 `AFTER UPDATE` 触发器 → 把**每一次写入之后**的 `available/locked/sold` 记进 `lt_stock_audit` |
| 压测脚本 | `backend/loadtest/day12-concurrent-order.py`（Python 标准库 `threading` + `urllib`，`Barrier` 同步） |

> **为什么必须是 20 个独立用户**：`createFromCart` 读的是「一个用户已勾选的购物车行」，读完还要**清掉**。20 个线程若共用一个账号，它们会往同一行 `cart_items` 里累加，`quantity` 变成 20 —— 最多只能成交 1 单，**永远压不到库存边界**。压测里「共享可变状态」必须先被隔离，否则测的不是你想测的东西。

> **为什么用触发器而不是轮询采样**：Python 每查一次库要起一个 `docker exec`（~200ms），而整场竞争只有 0.5 秒 —— 轮询只能采到 2 个点，等于没采。触发器是**每一次写入都留痕**，这才是硬证据。

---

##### 实验 A：正式版（条件 UPDATE）→ 不超卖

```
20 线程 × 各买 1 件 sku3，库存只有 10 件
成功 10 单（orderId 23~32）  失败 10 单（全部 code=400 库存不足）
available 10 → 0    locked 0 → 10    identity_ok = t
订单号 12/12 唯一   elapsed 0.53s
```

**审计日志 —— 12 项断言全绿的关键证据**：

| # | available | locked | # | available | locked |
|---|---|---|---|---|---|
| 01 | 9 | 1 | 06 | 4 | 6 |
| 02 | 8 | 2 | 07 | 3 | 7 |
| 03 | 7 | 3 | 08 | 2 | 8 |
| 04 | 6 | 4 | 09 | 1 | 9 |
| 05 | 5 | 5 | 10 | **0** | **10** |

**恰好 10 次写入、严格递减、没有一次脏值** —— 20 个并发请求被行锁**串行化成 10 次干净扣减**，另外 10 个在 `WHERE available_stock >= 1` 处被原子地挡掉。这不是「看起来没超卖」，是每一次数据库写入都留下了签名。

| # | 断言 | 结果 |
|---|---|---|
| 1 | 审计恰好捕获 10 次写入 | ✅ |
| 2 | 任何一次写入都不是负数 | ✅ |
| 3 | available 严格递减 10 → 0 | ✅ |
| 4 | 成功数 == 库存 10 | ✅ |
| 5 | 失败数 == 10 | ✅ |
| 6 | 失败全是 HTTP 200 + `code=400`（**不是 500**） | ✅ |
| 7 | `available == 初始 - 成交量` | ✅ |
| 8 | `locked == 初始 + 成交量` | ✅ |
| 9 | `total = available + locked + sold` | ✅ |
| 10 | orders 增量 == 成功数 | ✅ |
| 11 | `order_no` 全不重复 | ✅ |
| 12 | 无超卖（订单数 ≤ 库存） | ✅ |

---

##### 实验 B：对照组（先查后改）→ 亲眼看见超卖

把 `InventoryServiceImpl.deductForOrder` 临时换成「`SELECT` 出来 → Java 里算 → `updateById` 写回去」，**同一份夹具、同一个脚本**重跑：

| | 正式版（条件 UPDATE） | 对照组（先查后改） |
|---|---|---|
| 成功订单 | **恰好 10** | **20（全部成功，一单没拒）** |
| 失败数 | 10（库存不足） | 0 |
| `available` 最终 | 0 | **8** |
| `locked` 最终 | 10 | **2** |
| 实际卖出 / 实际扣减 | 10 / 10 | **20 / 2** ← 超卖 10 件 |
| 耗时 | 0.53s | 2.81s（20 个 UPDATE 争同一把行锁，必须排队） |

**对照组审计日志（20 行，节选）**：

```
#01 available=9    #08 available=9    #14 available=8    #19 available=7
#02 available=9    #09 available=8    #15 available=8    #20 available=8
#03 available=9    #10 available=8    #16 available=7
#04 available=9    #11 available=9 ← 涨回去了！
#05 available=9    #12 available=8    #17 available=9 ← 又涨回去！
#06 available=9    #13 available=8    #18 available=8
#07 available=9
```

**三个值得刻进脑子的观察**：

1. **同一个值被连写了 8 遍**（`available=9` 出现 8 次）。20 个事务各自读到 `10`、各自算出 `10-1=9`、各自写 `9` —— 后写的覆盖先写的，**只有最后一次生效**。这就是**丢失更新（lost update）**。
2. **审计里数值会「涨回去」**：`#10` 已经是 8 了，`#11` 又变回 9；`#16` 降到 7，`#17` 又回到 9。因为 `#11`、`#17` 这两个事务早就读到 10 了，只是在行锁队列里排到后面才写。**这不是 bug 的副作用，这就是 bug 本身。**
3. ★★ **`total = available + locked + sold` 依然成立**（`8 + 2 = 10`）。**光靠库存恒等式发现不了超卖** —— 它只保证「账目不矛盾」，不保证「卖出的没超过库存」。真正的判据是 **订单数 vs 库存扣减量**：`20 vs 2`。

跑完立刻还原（这正是「先提交再压测」的回报 —— 改坏的东西一行命令回滚，还有 `git diff` 作证）：

```
git checkout -- backend/mallx/mall-inventory/src/main/java/com/mallx/inventory/service/impl/InventoryServiceImpl.java
git diff --stat          # 输出为空 → 确认已还原
```

还原后重编译重启再跑一次实验 A → **12/12 全绿**，确认正式版完全恢复。

---

##### 实验 C：一车多单 —— 库存没问题，是订单侧缺幂等

模拟「用户手抖点两次提交订单」：10 个线程压**同一个账号的同一个购物车**（车里只有 1 件 `sku3`，库存给足 100）。

```
1 件商品的购物车  →  7 个订单（orderId 79~85）
3 个线程扑空 → 400「请先勾选要购买的商品」（车已被前面的线程清掉）
库存 100 → 93 / locked 0 → 7      ← 算术完全正确
脚本：backend/loadtest/day12-one-cart-multi-order.py
```

| 判据 | 结论 |
|---|---|
| 库存算术 | ✅ 一致（扣 7 件 ↔ 7 张订单，**没有超卖**） |
| 订单唯一性 | ❌ **1 件商品开出 7 张单** |

**性质与实验 B 完全不同**：

| | 实验 B | 实验 C |
|---|---|---|
| 现象 | 卖 20 件、只扣 2 件 | 扣 7 件、开 7 单 |
| 病灶 | 库存扣减**丢失更新** | 订单侧**没有幂等保护** |
| 一句话 | 库存算错了 | 库存算对了，但单开多了 |

并发请求都读到了同一份购物车快照，每个都在别人 commit 之前写下了自己的订单 —— 这就是生产环境里「下单按钮连点两次 / 网络重试」的真实后果，也正是 Day 13+ 要用 **`requestId` 唯一索引**（或 Redis 去重）解决的问题。

---

##### 夹具清理

`backend/loadtest/day12-loadtest-cleanup.sql` 一次跑完：

| 项 | 结果 |
|---|---|
| 测试用户 / 地址 | 20 / 20 → 全删 |
| 压测订单 | `orders_lt = 10` + demo 实验单 13 → 全删；**样本订单 1、2 保留** |
| 审计装置 | `DROP TRIGGER` / `DROP FUNCTION` / `DROP TABLE` |
| `sku3` 库存 | 复原 `60 / 58 / 2 / 0`（= 第 2 步验收后） |
| 全库恒等式 | **7 个 SKU 全部 `identity_ok = t`** |

---

### 第 4 步：订单列表 + 详情

**`GET /api/orders`**（分页 + 只查自己的）：

```java
Page<Order> page = new Page<>(current, size);
Page<Order> result = orderMapper.selectPage(page, new LambdaQueryWrapper<Order>()
        .eq(Order::getUserId, userId)          // ★ 越权防线：永远带 user_id 条件
        .orderByDesc(Order::getCreatedAt)
        .orderByDesc(Order::getId));           // 同一毫秒的兜底排序（Day 11 学的）
return PageResult.of(result.convert(this::toVO));
```

**`GET /api/orders/{id}`**：

```java
Order order = requireOwn(userId, orderId);     // 复刻 Day 10/11 的 404 伪装
List<OrderItem> items = orderItemMapper.selectList(
        new LambdaQueryWrapper<OrderItem>().eq(OrderItem::getOrderId, orderId));
```

**⚠️ 分页参数必须夹紧**（这是新东西）：

```java
// size 不夹紧的话，?size=1000000 会让一个人把整张表拖出来
long safeSize = Math.min(Math.max(size, 1), 100);
long safeCurrent = Math.max(current, 1);
```

### 第 4 步 ✅ 已完成（真机 11 项全绿）

**产出：0 个新文件，只改 3 个已有文件**（`OrderService` / `OrderServiceImpl` / `OrderController`）+ 1 处全局异常处理修复。

> 基础设施全是现成的，**一行 POM、一条 SQL 都不用加**：
> `PageResult` 已在 `mall-common/api`；`MybatisPlusConfig` 已注册 `PaginationInnerInterceptor(POSTGRE_SQL)`；
> `mybatis-plus-jsqlparser` 已在父 POM 传递依赖里（第 142/147 行）。
> ⚠️ 若分页插件没注册，`selectPage` **不报错** —— 只是 `total=0` 且返回**全部**记录。静默失效，最难查。

**★★ 本步的灵魂：分页参数不夹紧会「变形」，不是「多返回几条」**

| 输入 | 不夹紧的真实后果 | 夹紧写法 |
|---|---|---|
| `?size=99999` | 一个人一次把整张 `orders` 拖走（DoS） | `Math.min(size, 100)` |
| `?size=-1` | ⚠️ **MyBatis-Plus 特例：`size < 0` = 不执行分页 = 查全表** | `Math.max(size, 1)` |
| `?page=0` | ⚠️ `offset = (0-1)*size` 为负 → PG 抛 `OFFSET must not be negative` | `Math.max(page, 1)` |

★ 夹紧必须写在 `new Page<>(...)` **之前** —— 构造进去的值才是最终发给 DB 的值。

**11 项验收（真机 curl + 查库，全绿）**

| # | 请求 | 实际 |
|---|---|---|
| 1 | 匿名 `GET /api/orders` | ✅ `http=401 code=401 未登录或登录已过期` |
| 2 | `GET /api/orders` | ✅ `total=2 current=1 size=10 n=2`；顺序 `id=2(10:41:29) → id=1(10:40:56)` 倒序；`hasUserId=False` |
| 3 | `?page=1&size=1` | ✅ `total=2`（**全部**）`current=1 size=1 n=1 ids=2` |
| 4 | `?page=999` | ✅ `code=200 current=999 n=0`（空数组，不报错） |
| 5 | `?size=99999` | ✅ `size=100 n=2`（被夹到 100） |
| 6 | `GET /api/orders/1` | ✅ `items=2` 快照齐全（`Apple iPhone 17 Pro / 原色钛金属 512GB / 12499.00 ×2`、`Huawei Mate 80 Pro / 曜金黑 512GB / 6999.00 ×1`）；`paidAt=[]` |
| 7 | `GET /api/orders/9001`（**别人的**） | ✅ `code=404 订单不存在` |
| 8 | `GET /api/orders/99999` | ✅ `code=404 订单不存在` |
| 9 | 🆕 `?page=0` | ✅ `code=200 current=1 size=10 n=2` —— 被夹到 1，**没有**负 offset 报错 |
| 10 | 🆕 `?size=-1` | ✅ `code=200 size=1 n=1` —— 挡住了 MP 的「负数 = 查全部」 |
| 11 | 🆕 `GET /api/orders/abc` | ✅ `code=400 参数 id 格式不正确`（修复前是 `code=500`） |

**★ 4 项关键证据（比「11 项都过了」更值钱）**

1. **越权防线是真的**：demo（`users.id=1`）的列表 `total=2`，而库里 `orders` 共 **3** 行（第 3 行 `id=9001` 属于 `users.id=2`）
   → `eq(userId)` 生效：别人的订单**根本进不了结果集**，不是「查出来再过滤掉」。
2. **VO 不外泄内部字段**：列表行 `hasUserId=False` —— `OrderVO` 刻意不含 `userId`（同 Day 11 `AddressVO` 的规矩）。
3. **夹紧真的生效**：`?size=99999` → 响应 `size=100`；`?size=-1` → 响应 `size=1` 且 `n=1`
   （**若没夹紧，MP 会返回全部 2 条**，第 10 项就是靠 `n=1` 而不是 `n=2` 证明的）。
4. **IDOR 的 404 伪装**：`/9001`（别人的订单，**真实存在**）与 `/99999`（**不存在**）返回**完全一样**的
   `code=404 订单不存在` → 外部无法区分「不属于我」和「根本不存在」，枚举攻击拿不到有效信息。

**验收用的靶子**（`users.id=2` 是 Day 12 第 2 步就保留的 `intruder`；第 5 步收尾时清）：

```sql
INSERT INTO orders (id, order_no, user_id, total_amount, pay_amount, status,
                    receiver_name, receiver_phone, receiver_address, created_at, updated_at)
VALUES (9001, 'MX-TARGET-9001', 2, 100.00, 100.00, 'PENDING_PAYMENT',
        'VICTIM', '13800000099', 'SOMEWHERE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
-- ⚠️ 显式给 id 插入后必须校准序列，否则下一次自然插入撞主键
SELECT setval(pg_get_serial_sequence('orders','id'), (SELECT MAX(id) FROM orders));
```

Swagger 路径 **17 → 18**（新增 path 是 `/api/orders/{id}`；`/api/orders` 的 GET 与 POST 共用一个 path，不另计）。

---

#### 第 4 步附带修复：`GET /api/orders/abc` 从 500 变 400

**现象**：路径变量要 `Long`，传 `abc` → Spring 抛 `MethodArgumentTypeMismatchException`
→ 它是 `Exception` 的子类且没有更具体的 handler → 被 `GlobalExceptionHandler.handleException(Exception)`
兜走 → 客户端收到 **`200 + code=500 系统繁忙`**。

**为什么必须修**：把「**调用方传错参数**」误报成「**服务端故障**」，
排障时会被日志里的「系统异常」带偏（明明是自己传错）；对前端也不友好。

**修法**（`mall-common/.../exception/GlobalExceptionHandler.java`）：

```java
@ExceptionHandler(MethodArgumentTypeMismatchException.class)
public Result<Void> handleTypeMismatch(MethodArgumentTypeMismatchException e){
    log.warn("参数类型不匹配: name={}, value={}", e.getName(), e.getValue());
    return Result.error(ResultCode.VALIDATE_FAILED.getCode(), "参数 " + e.getName() + " 格式不正确");
}
```

- 新增 import `org.springframework.web.method.annotation.MethodArgumentTypeMismatchException`
- **返回 HTTP 200 + code=400，不是 HTTP 400** —— 遵循项目约定「参数类失败统一看 body 的 code」，
  前端只判一处；`Security` 层的真实 401/403 是唯一例外（那是过滤器直接写的响应）
- 顺带修正方法名拼写：`handleVaildException` → `handleValidException`
- ⚠️ 同类问题还有 `HttpMessageNotReadableException`（请求体 JSON 语法错）也会被兜成 500，本步未动

---

### 第 5 步：端到端 + 提交

一条完整业务链路，从空车开始：

```
① 建地址 → ② 加购 2 个 SKU → ③ 取消勾选其中 1 个
→ ④ 下单 → ⑤ 查列表 → ⑥ 查详情 → ⑦ 查库对账（订单/明细/库存/购物车）
→ ⑧ 再下一次单（车里已空）→ 400
```

**验收 10 项**，最后清理夹具 + 提交。

---

## 5. 端到端验收清单（第 5 步）

| # | 步骤 | 期望 |
|---|---|---|
| 1 | 匿名 `POST /api/orders` | 401 |
| 2 | 建地址 | 200 |
| 3 | 加购 SKU-A ×2、SKU-B ×1 | 200 |
| 4 | 把 SKU-B 取消勾选 | 200 |
| 5 | `POST /api/orders {addressId}` | 200，返回订单 id |
| 6 | 查库 `order_items` | **只有 1 行**（SKU-A），`quantity=2`，名字/价格是快照 |
| 7 | 查库 `inventories` | SKU-A `available -= 2 / locked += 2`；**SKU-B 一个数没动** |
| 8 | 查库 `cart_items` | SKU-A 已删、**SKU-B 仍在**（未勾选不清） |
| 9 | `GET /api/orders` + 详情 | 金额一致、明细 1 条、`status=PENDING_PAYMENT` |
| 10 | 再次 `POST /api/orders` | `code=400`「请先勾选要购买的商品」 |

---

## 6. 坑预判

| # | 坑 | 症状 | 对策 |
|---|---|---|---|
| 1 | `@TableName("orders")` 漏写 | `SELECT ... FROM order` → 语法错误（`order` 是保留字） | 类上必须有 `@TableName("orders")` |
| 2 | `@TableName("inventories")` 漏写 | MP 推成 `inventory` → 表不存在 | 同上 |
| 3 | `order_items` 没有 `updated_at` | 实体挂 `INSERT_UPDATE` 也不会报错（列不存在才会炸） | 只填 `createdAt` |
| 4 | 自定义 XML UPDATE **不走** `MetaObjectHandler` | `updated_at` 不变 | XML 里手写 `updated_at = CURRENT_TIMESTAMP` |
| 5 | 下单方法里 `try-catch` 吞异常 | 事务不回滚，库存扣了订单没生成 | 异常必须抛出，交给全局异常处理 |
| 6 | 多 SKU 扣减不排序 | 并发时死锁 `40P01` | **按 `sku_id` 升序**逐个扣 |
| 7 | 用 `updateById` 扣库存 | 丢失更新（覆盖别人的 `locked_stock`） | 必须条件 UPDATE |
| 8 | 判定写成 `available_stock > #{quantity}` | 库存刚好等于购买量时买不了 | 用 `>=`（Day 10 踩过同一个边界） |
| 9 | 购物车失效项**静默跳过** | 用户以为买了 5 件，收到 4 件 | 校验失败**整单拒绝**，消息里说明哪件不能买 |
| 10 | `DELETE` 购物车写成删全部 | 把未勾选的也删了 | `WHERE user_id=? AND selected = TRUE` |
| 11 | 列表查询漏 `user_id` 条件 | 能看到别人的订单（越权） | `eq(Order::getUserId, userId)` 永远带上 |
| 12 | 分页 `size` 不夹紧 | 一次请求拖全表 | `Math.min(Math.max(size,1),100)` |
| 13 | 订单号用 `UUID` | 太长（36 字符），且无时间趋势 | 用时间戳 + 随机；UNIQUE 兜底 |
| 14 | 金额用 `double` | 精度丢失（0.1+0.2≠0.3） | 一律 `BigDecimal` |

---

## 7. 延伸思考（不强制做）

1. **幂等**：用户手抖点两次「提交订单」→ 两张订单、两份库存。生产做法是客户端带 `requestId`，服务端用唯一索引去重（Redis 或 `order_request` 表）。V1.0 先记着。
2. **超时关单**：订单 30 分钟未支付自动取消 + 释放锁定库存。这是 Day 13 之后的定时任务活儿。
3. **`SELECT ... FOR UPDATE` 悲观锁**方案对比：`SELECT ... FOR UPDATE` 也能防超卖，代价是持有行锁期间阻塞所有人。**条件 UPDATE 更轻**（只在写入那一刻拿锁），是更常用的方案。
4. **库存日志**：`inventory_logs` 表（`change_quantity` / `before_stock` / `after_stock` / `type` / `reference_id`）就是为记录每次库存变动设计的，今天没写。加进去后每一次扣减都有据可查 —— 值得作为 Day 13 的加餐。
5. **`total = available + locked + sold` 要不要加 CHECK 约束**？PG 支持表级 CHECK，能兜住所有写入路径。和 Day 11 那条部分唯一索引一个思路。

---

## 8. 今日产出

- [x] `mall-inventory`：`entity/Inventory`、`mapper/InventoryMapper`(+XML)、`service/InventoryService`(+Impl)
- [x] `mall-order/pom.xml` 加 `mall-inventory` 依赖
- [x] `mall-order`：`Order` / `OrderItem` 实体 + 两个 Mapper(+XML)
- [x] `mall-order`：`OrderCreateDTO` + 5 个 VO + `OrderStatus`
- [x] `mall-order`：`OrderService`(+Impl)，`createFromCart` ★ 全部重点
- [~] `mall-order`：`OrderController` —— 第 2 步已上 `POST /api/orders`，列表/详情在第 4 步
- [x] 第 3 步并发压测证明「不超卖」（**12/12 断言全绿**）+ 对照实验证明「先查后改会超卖」（20 单成交 / 库存只扣 2 件）
- [x] 一车多单实验：1 件商品开出 **7 张单**（订单侧缺幂等，与超卖性质不同）
- [x] 压测装置入库：`backend/loadtest/` 4 个文件（setup / cleanup / 两个压测脚本）
- [~] 3 个接口在 Swagger UI 里可调（路径 16 → **17**，`POST /api/orders` 已在列）
- [ ] 端到端 10 项全绿
- [~] git 提交：第 1、2 步已提（`37c24d5` / `cd651e1` / `5a7b445`），第 3 步的脚本 + 文档待提

---

## 附：与里程碑的关系

```
Day 10 购物车 ✅  →  Day 11 收货地址 ✅  →  ★ Day 12 下单（今天）
                                              ↓
                                       Day 13 支付（locked → sold）
                                              ↓
                                       Day 14 订单状态流转 / 取消 / 超时关单
                                              ↓
                                       Day 15/16 评价 → 里程碑 M1「下单→支付→收货→评价」打通
```
