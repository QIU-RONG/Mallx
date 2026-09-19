# Day 14 — 订单状态机：取消 / 超时关单 / 库存回补 + 流水

> **一句话**：Day 13 只让 `orders.status` **往前走**（`PENDING_PAYMENT → PAID`）。
> Day 14 补上另外两条边：**往后退**（`→ CANCELLED`）和**自己走**（超时自动取消），
> 并把库存回补（`locked → available`）与库存流水（`inventory_logs`）一起补上。
>
> **前置**：Day 13 支付 ✅（`locked → sold` 已通）。
> **路线依据**：`Day-12-从购物车下单.md:1022` 的里程碑图已排定
> `Day 14 订单状态流转 / 取消 / 超时关单`；
> `InventoryService.java:8` 的 Javadoc 也已预告「取消订单的 `locked → available` 回补留到 Day 14 的订单状态机」。

---

## 〇、开工前的账目审计（★ 先看这一节）

Day 14 要动的是「订单状态」与「库存归属」，动手前必须先看清**账本现状**——
否则实验做完，分不清「代码对了」还是「数据本来就脏」。

### 0.1 事实盘点（2026-09-19 实查）

| 项 | 现状 |
|---|---|
| `orders` | **5 行，全部 `PAID`**（1 / 2 / 9002 / 9004 / 9005）—— **一张待支付都没有** |
| `payments` | 5 行，每个订单恰好 1 笔（压测的重复支付全部回滚，没留脏数据） |
| `inventories` | 7 个 SKU，**恒等式 `total = avail + locked + sold` 全部成立**，无负值 |
| `inventory_logs` | **0 行** —— Day 03 建表至今，一次都没写过 |
| 序列 | `orders_id_seq = 9005`、`payments_id_seq = 109` |
| 账号 | `demo/demo123`（id=1，5 张单）、`intruder/intruder`（id=2，**0 张单**） |
| 可复用常量 | `OrderStatus.CANCELLED` 已存在；`orders.cancelled_at` 列已存在 → **本日零 DDL** |
| `@EnableScheduling` | 启动类**没有** → 第 3 步要加 |

⚠️ **第一个坑**：Day 13 收官时把 Day 12 遗留的 `order #2` 付清了，所以
**「取消订单」这一步没有现成靶子** —— 必须先下一张单、把它留在 `PENDING_PAYMENT`。

### 0.2 ★ 发现：算术守恒 ≠ 业务守恒

恒等式全绿，但把条件换成**业务口径**再查一次，就露馅了：

```sql
-- locked 应该等于「所有未支付订单的明细之和」
SELECT i.sku_id, i.locked_stock AS actual,
       COALESCE(l.want, 0) AS want, i.locked_stock - COALESCE(l.want, 0) AS drift
FROM inventories i
LEFT JOIN (SELECT oi.sku_id, sum(oi.quantity) AS want
           FROM order_items oi JOIN orders o ON o.id = oi.order_id
           WHERE o.status = 'PENDING_PAYMENT' GROUP BY oi.sku_id) l ON l.sku_id = i.sku_id
WHERE i.locked_stock <> COALESCE(l.want, 0);
```

**实测结果**：

| SKU | `locked` 现值 | 应有 | 漂移 | `sold` 现值 | 应有 | 漂移 |
|---|---|---|---|---|---|---|
| 1 | 2 | 0 | **+2** | 2 | 0 | **+2** |
| 2 | 0 | 0 | 0 | 2 | 0 | **+2** |
| 3 | 0 | 0 | 0 | 4 | 4 | 0 ✅ |
| 4 | 1 | 0 | **+1** | 4 | 3 | **+1** |
| 5 | 0 | 0 | 0 | 3 | 3 | 0 ✅ |
| 6 | 1 | 0 | **+1** | 0 | 0 | 0 ✅ |
| 7 | 0 | 0 | 0 | 0 | 0 | 0 ✅ |

**读法**：库存里躺着 **4 件「无主锁定」**（没有对应订单）和 **5 件「虚构已售」**
（没有对应已支付明细，其中 sku1/sku2 的已售完全不来自任何订单）。

★ **这不是代码 bug，是实验副产品**：Day 10–13 的压测与反例实验为了复原现场，
多次用**手工 `UPDATE`** 调整库存 —— 只要保住「总数不变」，恒等式就不会报警，
但「货被记在哪个格子里」早已错位。Day 13 的 `day13-restore.sql` 本身就是按
「支付笔数 × 数量」倍数还原的，本来就允许偏差。

★ **真正的教训**（也是第 4 步存在的理由）：

> **恒等式只能发现「凭空多货 / 少货」，发现不了「货被记在错误的格子里」。**
>
> `total = avail + locked + sold` 是**算术守恒**；
> `locked == Σ(未支付订单明细)` 才是**业务守恒**。
> 两者都成立才叫账对。而现在 —— 前者 7/7 成立，后者 4/7 不成立。

而这正是 `inventory_logs` 从 Day 03 建好却一直空着的代价：
**没有流水，就无法追溯任何一次库存变动，也无法自动发现这种漂移。**

### 0.3 基线校准（开工前建议先做）

不校准直接做实验，会出现这种迷惑现象：取消一张只锁了 1 件的订单，
`locked` 从 2 变成 1 —— **看着像没归零，其实归零了**（那 1 件是历史幽灵）。

校准原则：

| 漂移方向 | 处理 | 理由 |
|---|---|---|
| **多出的** `locked` / `sold`（drift > 0） | 退回 `available` | 有依据：这货本来就不该被占/被卖 |
| **缺少的**（drift < 0） | **不自动补**，只报出来 | 凭空补等于造货 —— 必须人工查 |
| `locked` 的应然值 | `Σ(PENDING_PAYMENT 订单明细)` | 当前为 **0**（没有待支付订单） |

当前数据全为 drift > 0，可一次修完。校准后应为：

| SKU | total | available | locked | sold | 业务守恒 |
|---|---|---|---|---|---|
| 1 | 100 | 100 | 0 | 0 | ✅ |
| 2 | 80 | 80 | 0 | 0 | ✅ |
| 3 | 60 | 56 | 0 | 4 | ✅ |
| 4 | 150 | 147 | 0 | 3 | ✅ |
| 5 | 120 | 117 | 0 | 3 | ✅ |
| 6 | 40 | 40 | 0 | 0 | ✅ |
| 7 | 90 | 90 | 0 | 0 | ✅ |

⚠️ 校准 SQL 里 **`locked` 全归零只对「无待支付订单」成立**；若将来存在待支付订单，
必须改成「只退多出的部分」，否则会把在途订单的锁一起退掉。

---

## 一、全景：4 步

| 步 | 内容 | 新增技术点 | 产物 |
|---|---|---|---|
| **1** | **取消订单** `POST /api/orders/{id}/cancel` | 状态机**反向边** + 库存**逆操作** `releaseLocked` | 1 新方法 + 1 新 XML + 3 改 |
| **2** | **取消 vs 支付 并发对照实验** | 两个**方向相反**的 CAS 抢同一个状态位 | 压测脚本 + 破坏性证据 |
| **3** | **超时关单**（`@Scheduled` 扫表） | 定时任务 + **无 SecurityContext 的系统视角** + 批量事务边界 | 1 新类 + 1 注解 |
| **4** | **`inventory_logs` 流水补齐** | 三个库存写点各记一条；`before/after` 从哪来 | 1 新实体 + 1 新 Mapper + 改 3 处 |
| **5** | 端到端 + 对账 + 收官 | —— | 验收脚本 + 文档 + 提交 |

**为什么把「流水」放第 4 步而不是最后**：它要横切**三个**已存在的库存写点
（`deductStock` / `moveLockedToSold` / 新的 `releaseLocked`）。前 3 步把
「写点」都造齐了，第 4 步才能一次改到位，不用回头返工。

---

## 二、状态机长什么样

```
                      ┌──────────────────┐
     下单 createFromCart│ PENDING_PAYMENT  │
                      └────────┬─────────┘
                               │
              ┌────────────────┼────────────────┐
              │ 支付            │                │ 取消 / 超时
              │ CAS:           │                │ CAS:
              │ status=        │                │ status=
              │ PENDING_PAYMENT│                │ PENDING_PAYMENT
              ▼                │                ▼
      ┌──────────┐             │        ┌────────────┐
      │   PAID   │             │        │ CANCELLED  │
      └────┬─────┘             │        └────────────┘
           │ 库存:              │              │ 库存:
           │ locked → sold      │              │ locked → available
           │ (available 不动)    │              │ (sold 不动)
           ▼                    │              ▼
      ┌──────────┐              │        ┌──────────────┐
      │ SHIPPED  │    ← Day 15+ │        │ 货回到可售池  │
      └────┬─────┘              │        └──────────────┘
           ▼                    │
      ┌───────────┐             │
      │ COMPLETED │             │
      └───────────┘             │
                                │
   ★ 两条出路【互斥】：都从 PENDING_PAYMENT 出发，
     都用同一条 CAS 抢同一个状态位 —— 谁先谁赢，输的拿 0 行。
```

★ 这张图里 Day 14 新增的只有**两条**：`→ CANCELLED` 和它下面的 `locked → available`。
其余（`PAID` 及以上）都是已完成或后续。

---

## 三、第 1 步：取消订单（详细）

### 3.1 与「支付」是完全对称的孪生结构

写之前先对上这张对照表 —— 取消**不是**新套路，是支付那条链路的**镜像**：

| 环节 | 支付（Day 13，已实现） | 取消（Day 14，要写） |
|---|---|---|
| 接口 | `POST /api/payments`（body 带 orderId） | `POST /api/orders/{id}/cancel` |
| ① 归属 | `SELECT … WHERE id=? AND user_id=?` → null 报 404 | **同左**（同一句消息口径） |
| ② 明细 | 读 `order_items`（空 → 500） | **同左** |
| ③ 中间产物 | `INSERT payments`（金额信服务端） | **无**（取消失败没有"退款单"要写） |
| ④ 状态 CAS | `markPaid`：`WHERE status='PENDING_PAYMENT'` → 0 行报 **400** | `cancelOrder`：**同款 WHERE**，0 行报 **400** |
| ⑤ 库存 | `moveLockedToSold`：`WHERE locked >= qty` → 0 行报 **500** | `releaseLocked`：**同款 WHERE**，0 行报 **500** |
| ⑥ 事务 | `@Transactional` 包 ④⑤ | **同左** |
| 重复调用 | 400「订单状态不允许支付」 | 400「订单状态不允许取消」 |

★★ **两条链路的 ④ 是同一个状态位的两次争夺**，这就是第 2 步并发实验的由头。

### 3.2 要改的文件（1 新建 + 4 改，POM 不动）

| # | 文件 | 动作 |
|---|---|---|
| 1 | `mall-order/.../mapper/OrderMapper.xml` | **改**：+`<update id="cancelOrder">` |
| 2 | `mall-order/.../mapper/OrderMapper.java` | **改**：+`int cancelOrder(@Param("orderId") Long orderId)` |
| 3 | `mall-inventory/.../mapper/InventoryMapper.xml` | **改**：+`<update id="releaseLocked">` |
| 4 | `mall-inventory/.../mapper/InventoryMapper.java` | **改**：+`int releaseLocked(@Param("skuId") Long skuId, @Param("quantity") int quantity)` |
| 5 | `mall-inventory/.../service/InventoryService.java` + `Impl` | **改**：+`void releaseLocked(Long skuId, int quantity)`（0 行 → 500） |
| 6 | `mall-order/.../service/OrderService.java` + `Impl` | **改**：+`void cancel(Long userId, Long orderId)` |
| 7 | `mall-order/.../controller/OrderController.java` | **改**：+`POST /{id}/cancel` |

⚠️ **归属问题**：`cancel` 放在 `OrderService` 还是新开 `mall-payment` 那样的服务？
→ 放 **`OrderService`**。理由：取消**不需要** payments 表，它只碰 `orders` +
`inventories`，而 `mall-order` 已经依赖 `mall-inventory`（Day 12 下单时就在用
`deductForOrder`）。**不引入新依赖、不产生循环依赖**。

### 3.3 三处填空点（写的时候想清楚这三件事就够了）

**填空点 ①：`cancelOrder` 的 WHERE**

```xml
<update id="cancelOrder">
    UPDATE orders
    SET status = 'CANCELLED',
        cancelled_at = CURRENT_TIMESTAMP,
        updated_at   = CURRENT_TIMESTAMP
    WHERE id = #{orderId}
      AND status = 'PENDING_PAYMENT'
</update>
```

- `AND status = 'PENDING_PAYMENT'` **就是全部的技术含量** —— 去掉它，取消就能
  覆盖任何状态（包括把已付款的订单改成已取消）。
- ★ **为什么这里可以裸写 `'CANCELLED'` 字符串**，而 Java 侧必须用 `OrderStatus.CANCELLED`：
  XML 是 SQL 字面量，没法引用 Java 常量。**代价是列上没有 CHECK 约束**，
  写错拼写数据库不拦 —— 所以注释里必须写明「此值对应 `OrderStatus.CANCELLED`」。
- ⚠️ `updated_at` 必须**显式写**：XML 自定义 UPDATE **不走** MyBatis-Plus 的
  `MetaObjectHandler`（同 `markPaid` 的坑，Day 13 已踩过）。
- ⚠️ XML 注释里**不能出现 `--`**（铁律④，Day 13 启动炸过一次）。

**填空点 ②：`releaseLocked` 的 WHERE —— 与 `deductStock` 严格互为逆操作**

```xml
<update id="releaseLocked">
    UPDATE inventories
    SET available_stock = available_stock + #{quantity},
        locked_stock    = locked_stock    - #{quantity},
        updated_at      = CURRENT_TIMESTAMP
    WHERE sku_id = #{skuId}
      AND locked_stock >= #{quantity}
</update>
```

★ 把三个库存写点并排看，**守卫条件的选法一目了然**：

| 方法 | 方向 | 守卫 | 0 行的含义 | 报错级别 |
|---|---|---|---|---|
| `deductStock` | `available → locked` | `available >= qty` | **库存不足**（用户能理解） | **400** |
| `moveLockedToSold` | `locked → sold` | `locked >= qty` | **账目不一致**（服务端错） | **500** |
| `releaseLocked` | `locked → available` | `locked >= qty` | **账目不一致**（服务端错） | **500** |
| 恒等式 | —— | `available + locked + sold = total` **始终不变** | | |

★ 前两行的守卫是 **`available`**，后两行是 **`locked`** —— 判据永远是
**「我要动的那个格子里的货够不够」**，不是「总库存够不够」。
讲反了就会写成「取消时判断 available」→ 那取消一张没锁定的订单也能"退回"货物 → **凭空造货**。

**填空点 ③：`cancel` 方法的步骤顺序**

照抄 `PaymentServiceImpl.pay` 的骨架，去掉 ③（插支付单）：

```
① SELECT orders WHERE id=? AND user_id=?   → null → 404「订单不存在」
② SELECT order_items WHERE order_id=?      → 空 → 500「订单明细缺失」
③ cancelOrder(orderId)                     → 0 行 → 400「订单状态不允许取消」  ← 抢资格
④ for (item : items) releaseLocked(...)    → 0 行 → 500（由 Service 内部抛）
```

★ **③ 必须在 ④ 之前**：③ 是「抢资格」。抢不到就没必要动库存（同支付的 ④→⑤ 顺序）。
★ ③ 抢到后如果 ④ 失败 → 整个事务回滚 → ③ 改的状态**自动退回**
（同 Day 13 已验证的机制）。

★ **④ 为什么必须是循环 + 每个 SKU 一条 UPDATE**：因为库存是按 SKU 分行存的，
一条 SQL 改不了多个 SKU 的不同 `locked_stock`。这与下单、支付完全一致。

### 3.4 两个「编译过、运行才炸」的坑

**坑 A：`intruder` 取消 demo 的订单，必须报 404 而不是 400。**
若把归属校验省掉（只按 id 查订单），攻击者就能**取消别人的订单** ——
这是**写操作的 IDOR**，比 Day 13 的读越权危险得多（读是泄漏，写是破坏）。
验证方法：`intruder` 对 demo 的订单发取消 → 必须与「不存在的 id」返回**逐字节相同**的 404。

**坑 B：`POST /api/orders/{id}/cancel` 别写成 `@PatchMapping` 或 `PUT`。**
本项目 C 端接口清一色 `POST`/`GET`（见 `OrderController`），
而且取消**不是幂等**的语义（第二次调用报 400），用 `POST` 表意正确。

---

## 四、第 2 步：取消 vs 支付 并发对照实验（要点）

**实验设计**：同一张 `PENDING_PAYMENT` 订单，20 个线程**奇偶交替**发取消/支付。

**主组（有守卫）断言要点**（脚本里最终落成 16 项，见 §9.1）：

| # | 断言 |
|---|---|
| 1 | **成功者总数为 1**（支付赢或取消赢，不可能两个都赢） |
| 2 | 订单终态 ∈ {`PAID`, `CANCELLED`}（二选一，不是别的） |
| 3 | **终态与库存方向匹配** —— `PAID` ⇒ `sold += q` 且 `locked -= q` 且 `avail` 不变 |
| 4 | `CANCELLED` ⇒ `avail += q` 且 `locked -= q` 且 `sold` 不变 |
| 5 | **绝不出现**「订单 `CANCELLED` 而 `sold` 增加」或「`PAID` 而 `avail` 增加」 |
| 6 | 恒等式 + 业务守恒同时成立 |

**对照组（`naive`：同时去掉 orders 状态条件与 inventories 守卫）** —— 预期破坏形态：

```
起点：locked = L, avail = A, sold = S
取消执行一次 → avail = A+q, locked = L-q
支付执行一次 → locked = L-q-q, sold = S+q
终态：avail = A+q, locked = L-2q, sold = S+q
```

★ **同一件货凭空变成两件**（既退回了可售池、又算进了已售），且 `locked` 变负。
**而恒等式依然成立**（`+q -2q +q = 0`）—— 与 §0.2 的发现完全呼应：
**算术守恒永远骗得过眼睛，业务守恒才拦得住 bug。**

★ 这里有个必须讲清的机制：PG 在 READ COMMITTED 下，`UPDATE` 撞到被锁的行会等待，
锁释放后**重新求值 WHERE**（EvalPlanQual）—— 所以**带条件的** `UPDATE` 天然安全。
Day 13 的对照组之所以能收 12 笔钱，正是因为**把条件去掉了**。
换句话说：**CAS 的价值不在于"用 UPDATE"，而在于"UPDATE 里带条件"。**

⚠️ 实验前先下一张单造出 `PENDING_PAYMENT` 靶子；跑完记得还原（复用
`day13-restore.sql` 的思路，按实际成功笔数倍率还原）。

---

## 五、第 3 步：超时关单（要点）

**目标**：`PENDING_PAYMENT` 超过 N 分钟（建议**2 分钟**，便于实验观察）自动取消并释放库存。

**新增**：
- 启动类加 `@EnableScheduling`（**当前没有**）
- 新类 `mall-order/.../task/OrderTimeoutTask.java`，方法挂 `@Scheduled(fixedDelay = 60_000)`
- `OrderService` 加**系统视角**入口：`int cancelTimeoutOrders(int minutes)`（返回处理条数）

★ **三个真难点**：

1. **定时任务没有 SecurityContext** —— 不能取 `(Long) authentication.getPrincipal()`。
   所以**必须**拆成两个入口：
   - `cancel(userId, orderId)` ← 用户视角，带归属校验（IDOR）
   - `cancelTimeoutOrders(minutes)` ← 系统视角，**不带** `user_id` 条件（系统有权取消任何人的）
   
   ★ 这不是「省代码」，是**权限模型的分层**：前者是「你能取消你的」，后者是
   「系统能取消所有超时的」。混成一个方法，要么越权要么取消不了。

2. **批量循环不能整体一个事务** —— 一张订单取消失败不该让另外 99 张一起回滚。
   正确做法：循环里**逐单调用** `cancelTimeoutOrders` 内部的单笔逻辑，
   让每笔走自己的事务（`REQUIRED` 传播下，逐单方法各自带 `@Transactional`）。
   ⚠️ **自调用会让 `@Transactional` 失效**（本类调用本类方法不走代理）——
   所以单笔逻辑要么提成独立 Bean，要么用 `AopContext`（不推荐）。**推荐拆 Bean**。

3. **与用户支付的竞态** —— 超时任务正在取消的同时用户点了支付。
   这一条**不需要新代码**：还是 ④ 那条 CAS 兜住。定时任务只是「多了一个竞争者」。

---

## 六、第 4 步：`inventory_logs` 流水补齐（要点）

**目标**：让**三个**库存写点各留一条流水。

| 列 | 取值 |
|---|---|
| `sku_id` | 被改的 SKU |
| `change_quantity` | 变化量（带符号？还是恒正 + `type` 表方向？**要定**） |
| `before_stock` / `after_stock` | 变动前后的值（哪一个格子？`available` 还是 `total`？**要定**） |
| `type` | `ORDER_LOCK` / `PAY_SOLD` / `CANCEL_RELEASE` |
| `reference_id` | 关联的订单 id（可空） |

**两个设计决策（写代码前必须拍板）**：

**决策 ①：`before/after` 指哪个字段？**
→ 建议指 **`available_stock`**，并在 Javadoc 写明。理由：它是用户唯一能感知的
「还剩几件可买」，也是唯一「一生只被改一次」的字段（Day 13 结论）。
若指 `total`，三条流水的值会一模一样（total 从不被库存操作改动）→ 没有信息量。

**决策 ②：`before/after` 的值从哪来？**（★ 本步真正的技术难点）

我们现在的库存写点全是**原子 `UPDATE`**，它只回传「影响行数」，**不回传新旧值**。
三条路：

| 方案 | 写法 | 代价 |
|---|---|---|
| A. 先查后改 | `SELECT … FOR UPDATE` 拿旧值 → `UPDATE` → 算新值 | **丢掉原子性**：判定与修改被拆成两条语句，必须靠行锁续命 |
| B. 改后重查 | `UPDATE` 后再 `SELECT` 一次 | 同事务内能读到自己的改动，但**多一次往返**，且并发下读的是自己的值（要确认隔离级别） |
| **C. `UPDATE … RETURNING`** | SQL 末尾加 `RETURNING available_stock` | ★ **PG 原生支持，一条语句同时拿到"改了"和"改成多少"**，原子性无损 |

→ **选 C**。这是 PG 相对 MySQL 的一个实打实的优势，也是本项目第一次用 `RETURNING`。
⚠️ 难点在 **MyBatis 怎么接 `RETURNING`**：`<update>` 标签配 `resultType` +
`useGeneratedKeys` 不适用；可行做法是把方法返回类型从 `int` 改成实体/`Map`，
让 MyBatis 把 `RETURNING` 的结果集当作查询结果映射（**需要实测确认**）。

★ **流水的附带价值**：有了它，§0.2 的漂移可以被**自动审计** ——
`Σ(inventory_logs.change)`（按 SKU 汇总）应与 `inventories` 现值对得上。
**这才是这张表当初被建出来的意义。**

---

## 七、第 5 步：端到端 + 收官（要点）

1. **端到端链路**：下单 → 取消 → 查库对账 → 再下单 → 支付 → 对账（两条出路各走一次）
2. **超时关单实测**：下单 → 等 > 2 分钟 → 观察任务日志与状态自动变化
3. **流水审计**：`inventory_logs` 累加值 vs `inventories` 现值，逐 SKU 对上
4. **清理**：临时探针 SQL 删除；靶子订单与库存按 §0.3 口径复原
5. **文档**：补实测小节
6. **提交 + push**（走 `win-git-push` 技能脚本，★ 脚本内已修为 `GIT_TERMINAL_PROMPT=1`）
7. **更新记忆**：`MEMORY.md` 补 Day 14 定型的坑；当日日志追加流水

---

## 八、第 1 步实测：取消链路 —— 34/34 全绿

**改动：2 XML + 7 Java（POM 未动）**

| 模块 | 文件 | 改了什么 |
|---|---|---|
| mall-inventory | `InventoryMapper.xml` | +`releaseLocked`（`deductStock` 的严格逆操作，守卫仍是 `locked_stock >= #{quantity}`） |
| | `InventoryMapper.java` | +方法签名 |
| | `InventoryService` / `Impl` | +`releaseLocked`（**0 行 → 500**：账目不一致，与「库存不足 → 400」是两回事） |
| mall-order | `OrderMapper.xml` | +`cancelOrder`（**首次写入 `cancelled_at`**） |
| | `OrderMapper.java` | +方法签名 |
| | `OrderService` / `Impl` | +`cancel`（四步）/ `markCancelled`（0 行 → 400） |
| | `OrderController` | +`POST /api/orders/{id}/cancel` |

取消放在 `OrderService` 而不是新模块 —— 它只碰 `orders` + `inventories`，而 `mall-order` 已经依赖 `mall-inventory`，**零新依赖**。

**验收脚本 `backend/loadtest/day14-cancel-verify.py`（16 站 / 34 项断言）**

| 站 | 实测 |
|---|---|
| [0] 基线 | sku4 `total=150 avail=147 locked=0 sold=3`；库内 `PENDING_PAYMENT=0`、`max_order_id=9005` |
| [1] 匿名 | **真 HTTP 401** ← Security 过滤器写的响应，不走 `@RestControllerAdvice` |
| [2] 登录 | demo(id=1) / intruder(id=2) 各一枚 token（内存内，不落盘） |
| [3] 造靶子 A | `POST /api/orders` → **#9006**，`PENDING_PAYMENT` |
| [4] ★ 下单即锁库 | `available 147→146`、`locked 0→1`、`sold 3` 不动 |
| [5] 取消 | `HTTP 200 + code=200`，`data=null`（`Result<Void>`） |
| [6] 终态 | `CANCELLED`、`cancelledAt` 有值、**`paidAt` 仍为 `null`** |
| [7] ★★ 库存回补 | `available 146→147`、`locked 1→0`、`sold 3` 不动 → **与基线逐字段相等** |
| [8] 重复取消 | `HTTP 200 + code=400`「订单状态不允许取消」，库存未被再动 |
| [9]–[11] ★★ 写 IDOR | intruder 取消 demo 的 #9007 → `code=404`，与 `99999999` **逐字节相同**；**DB 侧佐证**：订单**仍 `PENDING_PAYMENT`**、`cancelled_at` **仍 NULL**、库存**仍锁着** |
| [12] | demo 自己取消 #9007 → 200，库存再次回到基线 ← 证明 [11] 挡的是**归属**，不是功能坏了 |
| [13] | 已 `PAID` 的订单取消 → `code=400`，`cancelled_at` 保持 NULL |
| [14] | 不存在的 id → 404；`/abc` → `code=400` |
| [15] 终局审计 | 7 个 SKU 恒等式全成立、无负库存、**业务守恒 drift = `-`（0 行）** |

★ 这步的三条硬证据：

1. **写 IDOR 必须用数据库佐证** —— 只断言「返回 404」证明不了「没写进去」。所以 [11] 额外查了 `orders.status` / `cancelled_at` / `inventories` 三处，全都说「没动」。
2. **`releaseLocked` 是 `deductStock` 的严格逆操作** —— [7] 的 delta `-1/+1/0` 与 [4] 的 `+1/-1/0` 严格互为相反数，且回到基线**逐字段相等**。
3. **对称性在数据层面也成立**：`paid_at` 与 `cancelled_at` 互斥（[6] 验前者、[13] 验后者），并在第 2 步的对照组里被打破。

---

## 九、第 2 步实测：取消 vs 支付抢同一个状态位

**装置**：`backend/loadtest/day14-cancel-vs-pay.py` —— 自包含（`orderId` 传 `0` 时自己下单造靶子）；复用
`day13-audit-setup.sql` 的审计触发器，记录**每一次** `inventories` 写入（含被回滚的）。

### 9.1 主组（`cas`）—— 16/16 全绿

20 线程（10 取消 + 10 支付，预热连接 + Barrier 同时发起）：

| 观察 | 值 |
|---|---|
| 成功 | **取消 1、支付 0** —— 19 个输家全是 `HTTP 200 + code=400` |
| 订单终态 | `CANCELLED`、`cancelled_at` 有值、`paid_at = False` |
| `payments` | `+0 行`、`sum = 0` |
| **`payments` 序列** | **`119 → 129`（烧掉 10 个 id）** ← 10 个支付线程**全都闯到了 `INSERT payments`**，却只留下 **0 行** |
| 库存 | `d_avail = +1  d_locked = -1  d_sold = +0` |
| **审计表** | 比赛期间**只有 1 行**（`147/0/3`）← 19 个失败事务**连审计行都被一起回滚** |
| 业务守恒 | `drifting SKUs: -` |

★ **连跑 4 轮全是取消赢** —— 不是巧合：取消的 SQL 路径更短（支付要先 `INSERT payments` 才走到 CAS），先到先得。
但**「有且只有一个赢家」是确定的** —— 这正是 CAS 的保证：**谁赢是竞速的偶然，赢几个是设计的必然。**

### 9.2 对照组（`naive`：同时摘掉 `orders` 状态条件与 `inventories` 守卫）

4 处守卫（`markPaid` / `cancelOrder` / `moveLockedToSold` / `releaseLocked`）全摘 → 11/11 全绿（全是 `DAMAGE:` 断言）：

| 观察 | 值 |
|---|---|
| 成功 | **取消 10 + 支付 10 = 20 全成功** |
| 订单终态 | `CANCELLED`，**`paid_at` 与 `cancelled_at` 同时有值** ← 一单既已支付又已取消 |
| 钱 | `payments` **10 行 / 69,990.00** ← 同一单收了 10 倍钱 |
| 库存 | `avail 146→156 (+10)`、`sold 3→13 (+10)`、`locked 1→-19 (-20)` |
| **恒等式** | **依然成立**（156 − 19 + 13 = 150） |
| **业务守恒** | **`drifting SKUs: 4`** ← 终于破了 |
| 审计轨迹 | 20 行：`147/0/3 → 147/-1/4 → 148/-2/4 → 148/-3/5 → … → 156/-19/13`，**一行行看得到两个方向在交替改写同一行** |

★★ **同一件货凭空变成两件**：`available +10`（退回可售池）**且** `sold +10`（同时算作已售），
`locked` 被两边各减一次变成 **-19**。算术上 `+10 −20 +10 = 0`，恒等式毫无异常 ——
**只有业务守恒能发现它**。这与 §0.2 的发现是同一件事的两次现身。

★ 机制补充（PG 的 EvalPlanQual）：READ COMMITTED 下 `UPDATE` 撞到被锁的行会**等待**，
锁一释放就**重新求值 WHERE** —— 所以**带条件的** `UPDATE` 天然安全，**去掉条件才危险**。
**CAS 的价值不在「用 UPDATE」，而在「UPDATE 里带条件」。**

### 9.3 复原与清理

| 动作 | 结果 |
|---|---|
| `day14-restore.sql`（按业务守恒**无条件**归位：`locked`/`sold` 从订单明细反推，`available = total − locked − sold`） | `156/-19/13 → 147/0/3`，drift 归零 |
| `day14-cleanup.sql`（删 9008–9014 七个靶子：**20 行 payments / 7 行 order_items / 7 张 orders**） | 保留 9006/9007（第 1 步的干净 `CANCELLED` 样本）；sku4 仍 `147/0/3`、drift 0 行、7 个 SKU 全干净 |
| 代码 `git checkout --` 还原两个 XML | 守卫计数回到 `2 + 2`，`git diff --stat` 为空 |

⚠️ **不能复用 `day14-recalibrate.sql` 复原**：校准脚本只处理 `drift > 0`，而对照组把 `locked` 打成了**负数**，
它的 `WHERE locked_stock > 0` 那一段**根本不命中**。对照组需要的是「无条件归位」。

### 9.4 ★ 一个意外收获（比设计的实验更有价值）

还原代码后**忘记先复原库存**就复跑了主组，于是 20 个线程**全部被 500 拒绝**：

- `stock before: locked = -18`（上一轮破坏的残留）→ 所有 `locked >= 1` 守卫**全部不成立** → 0 行
- 订单状态因此停在 `PENDING_PAYMENT` —— ④ 的 CAS 明明成功了，却被 ⑤ 的 500 **整笔回滚**

这是**守卫有效性的反向铁证**：**账上根本没有锁定货的时候，两个方向都动不了它**；
也顺手再证一次「一个 HTTP 请求写三张表」是**一个事务**。复原库存、换干净靶子复跑 → **16/16 全绿**。

**运行环境**：对照组用 `--spring.datasource.hikari.maximum-pool-size=32` 启动（默认 10 会限制并发威力），跑完已改回默认。

---

**状态**：✅ 第 1 步（取消订单，34/34）+ ✅ 第 2 步（并发对照，主组 16/16、对照组 11/11）已完成并提交；
⬜ 第 3 步（超时关单）、⬜ 第 4 步（`inventory_logs` 流水）、⬜ 第 5 步（端到端 + 收官）待开工。

---

## 附：本日不做的候选（留档，避免走偏）

| 候选 | 为什么不做 |
|---|---|
| 退款（`payments` 加 `REFUNDED` 状态 + 退款单） | 取消只覆盖**未支付**订单；已支付订单的退款是独立业务（V2.0） |
| 一车多单的 `requestId` 幂等 | Day 12 遗留项，与「状态机」是两条独立的线，不宜混在一天 |
| 发货 / 确认收货（`SHIPPED` / `COMPLETED`） | 属 Day 15–16 里程碑 M1 的收尾，本日只把「取消」这条边补上 |
