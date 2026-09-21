# Day 17 — 管理端订单 + 库存管理：把「运营的手」接上

> 里程碑 M1 已闭环（Day 16 收官，Day 17 起始先跑了一次全链路回归：198/198，见
> `backend/loadtest/day17-m1-regression-report.txt`）。
> 本日转向 **M1 的另一半**：发货是管理端动作，但管理端连订单列表都没有 ——
> 现在发货得手填订单 id，根本没法运营。

---

## 〇、开工前的四件事（★ 先看这一节）

### 0.1 事实盘点（2026-09-21 实查，不是回忆）

用 `psql` + 源码清点，管理端/库存域的真实状态：

| 项 | 现状 | 证据 |
|---|---|---|
| `mall-admin` 模块 | 只有 `AdminAuthController` + Admin/Role/Permission 实体与 Mapper | `mall-admin/src` 共 11 个文件 |
| `mall-order` 的写/读接口 | C 端 6 个全在 `OrderController`；**管理端只有 `POST /api/orders/{id}/ship`** | `OrderController.java:117` |
| `mall-inventory` | **一个 Controller 都没有** —— entity/mapper/service 三层齐全，没有出口 | `mall-inventory/src` 共 9 个文件 |
| 库存三个写点 | `deductStock` / `moveLockedToSold` / `releaseLocked` 全实现 + 都写流水 | `InventoryMapper.java` |
| 权限种子 | 8 条，**没有一条 `inventory:*`** | `permissions` 表实查 |
| `order:list` 权限 | 存在，但 `path = /api/orders GET` —— **指向的是 C 端端点，是个无效指向** | `permissions.id=6` |
| 角色-权限 | role2 商品(1-5)、role3 订单(6,7) | `role_permissions` 实查 |
| 管理员账号 | **只有 1 个**：`admin` / SUPER_ADMIN | `admins` 实查 |
| C 端账号 | `demo`(id=1)、`intruder`(id=2) —— 后者已在库，Day 13/14 脚本用它做越权对照 | `users` 实查 |
| 订单数据 | 8 张，**全部属于 user 1**；状态 `CANCELLED×3` + `PAID×5` | `orders` 实查 |

三个直接结论：
1. **不用建表、不用建模块、不用改 pom** —— 地基全是现成的（与 Day 16 相反）。
2. 库存域「服务层写好了但没出口」，本日的工作量集中在 Controller 与新查询上。
3. 权限种子**必须补发**（见 0.4），否则新接口挂上 `@PreAuthorize` 就是永远的 403。

### 0.2 ★★ 本日的本质：数据权限反转

前 16 天写过的每一个查询，防线的形态都是一样的 —— **归属过滤**：

```
C 端：WHERE user_id = #{userId}      ← 「只能看自己的」，条件写死在 SQL 里
```

本日第一次反过来写：

```
管理端：不加 user_id 条件            ← 「看所有人的」，防线换成了权限码
```

**这不是「少写一个 WHERE」，而是防线整体上移了一层**：

| | C 端 | 管理端 |
|---|---|---|
| 谁能调这个接口 | 登录即可（`anyRequest().authenticated()`） | **必须持有权限码**（`@PreAuthorize`） |
| 能看到哪些行 | 归属过滤，写死在 SQL | **不过滤**（或按运营自己传的条件过滤） |
| 失败形态 | 非本人 → 伪装 404 | 无权限 → **真 HTTP 403** |
| 越权的边界 | 「别人的数据」 | 「别人能不能拿到这个能力」 |

★ 一个必须记住的推论：**管理端的「不看归属」是允许的，前提是「有没有权限」这一关真的把住了**。
把关一旦失效（比如 `@PreAuthorize` 忘了挂），它就从「管理端接口」退化成
「任何登录用户都能拉全站订单」—— 不是一个 403 的 bug，是一个**全量数据泄露**。
所以本日的验收里，权限矩阵是**压在最前面**的一组（见 §5.1）。

### 0.3 ★★ 第一道新问题：管理端接口放在哪个模块？

三个方案：

| 方案 | 做法 | 代价 |
|---|---|---|
| **A（推荐）** | 控制器留在**自己的业务域**（`mall-order` / `mall-inventory`），用 `/api/admin/**` 路径前缀 + `@PreAuthorize` 标明「这是管理端」 | 模块内 C 端/管理端混居 —— 但 Day 15 的 `ship` 已有先例 |
| B | 全部搬进 `mall-admin` | `mall-admin` 目前**只依赖 `mall-common`**。要读写订单/库存，要么 admin→order/inventory 反向依赖，要么让它们开一堆「写门面」。**写门面最致命**：调整库存必须「改库存 + 写流水」同事务，门面一拆就变成两个事务边界，会出现「库存改了、流水没写」 |
| C | 新建 `mall-admin-order` / `mall-admin-inventory` | 第 10、11 个模块（每个都要改 3 处 pom，漏一处就「编译通过、启动成功、接口 404」），为一个 Controller 付这个代价不值得 |

**结论：模块边界按「数据归属」划，不按「调用者是谁」划。**
订单数据的家是 `mall-order`，库存数据的家是 `mall-inventory` —— 管理端只是「以管理员的身份访问这些数据」，
身份由**权限码**表达，不由**模块位置**表达。

### 0.4 ★★ 权限种子必须「补发」

`backend/sql/03-data.sql` 里授权用的是这个写法：

```sql
INSERT INTO role_permissions (role_id, permission_id)
SELECT 3, p.id FROM permissions p WHERE p.code LIKE 'order:%'   -- ORDER_ADMIN
```

它**只在首次种子时执行过一次**。今天新增 `inventory:*`、`order:detail` 等权限时，
这条 `LIKE 'order:%'` **不会再跑** → 新权限插进 `permissions` 表，
但 `role_permissions` 里没有任何一行指向它们 → `@PreAuthorize("hasAuthority('inventory:adjust')")` **永远 403**。

★ 这个失败模式很坏：它看起来像「代码写错了」，实际是**数据没补**。
所以本日新增 `backend/sql/05-admin-permissions.sql`（幂等），做三件事：

1. **订正** `order:list` 的 path（`/api/orders` → `/api/admin/orders`）——它原来指向 C 端端点，是个无效指向；
2. **插入 5 条新权限**：`order:detail` / `order:cancel` / `inventory:list` / `inventory:adjust` / `inventory:log`；
3. **补发授权**：SUPER_ADMIN 拿全部、ORDER_ADMIN 拿 `order:%`、PRODUCT_ADMIN 拿 `inventory:%`。

### 0.5 ★ 一个路径风格分叉，本日选择「记录」而不是「消除」

Day 15 的 `ship` 路径是 `/api/orders/{id}/ship`；本日新增的走 `/api/admin/**`。
为什么不顺手把 `ship` 也搬过去？因为它已经被引用在三处：**权限种子 `path`**、
**Day 15 验收脚本**、**已提交的 Day 15 报告**。搬它要同时改三处，而且会让「昨天的证据」与「今天的代码」对不上。

→ 本日**保留两条路径风格并存**，在文档里把来历写清；等 V1.0 收尾时一次性迁移
（那时所有引用点都可以一起改，且不会污染任何一天的历史证据）。

---

## 一、全景：3 步

```
第 1 步  管理端订单    列表（全站分页） / 详情（不做归属分流） / 取消（仅待支付）
                              ↓
第 2 步  库存管理      库存分页（JOIN SKU/商品名） / 调整（★ 双格同改） / 流水查询
                              ↓
第 3 步  端到端验收    权限矩阵 × 数据可见性 × 库存守恒 × 并发 × 清理回基线
```

## 二、端点设计

### 2.1 管理端订单（`mall-order`，新建 `AdminOrderController`）

| 方法 | 路径 | 权限码 | 说明 |
|---|---|---|---|
| GET | `/api/admin/orders` | `order:list` | 全站订单分页；可选 `status` / `userId` 过滤 |
| GET | `/api/admin/orders/{id}` | `order:detail` | 任意订单详情，**不做归属分流** |
| POST | `/api/admin/orders/{id}/cancel` | `order:cancel` | **仅 `PENDING_PAYMENT`**，复用同一条库存回补路径 |

### 2.2 管理端库存（`mall-inventory`，新建 `AdminInventoryController`）

| 方法 | 路径 | 权限码 | 说明 |
|---|---|---|---|
| GET | `/api/admin/inventory/skus` | `inventory:list` | 库存分页，JOIN `product_skus` / `products` 取名称 |
| POST | `/api/admin/inventory/skus/{skuId}/adjust` | `inventory:adjust` | 调整库存（★ `total` 与 `available` 同步改） |
| GET | `/api/admin/inventory/logs` | `inventory:log` | 流水分页，可按 `skuId` / `type` 过滤 |

### 2.3 ⚠️ 为什么必须用 `/api/admin/**` 这个前缀

`SecurityConfig` 的白名单里有一条：

```java
.requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
```

`GET /api/products/**` 是**公开**的。如果管理端接口图省事挂在 `/api/products/...` 下
（比如「查商品库存」写成 `GET /api/products/{id}/stock`），它会**静默变成匿名可访问** ——
白名单是「先匹配先赢」，`anyRequest().authenticated()` 根本轮不到。

`/api/admin/**` 不在白名单里 → 默认要登录 → `@PreAuthorize` 再收紧到权限码。**两级都到位。**

---

## 三、第 1 步：管理端订单

### 3.1 ★★ 铁律：不要用布尔开关复用查询

看到「C 端查自己的、管理端查全部」时，最自然的念头是加一个开关：

```java
// ❌ 千万不要这样
PageResult<OrderVO> list(Long userId, boolean all) {
    // all == true 时不带 user_id 条件 …… 
}
```

**为什么这是错的**：

1. **开关一旦被外部可控（哪怕今天只是内部参数），一个布尔值就废掉整条越权防线。**
   今天它是 Service 的私有参数，明天有人加个 `@RequestParam(defaultValue="false") boolean all` 就全线失守 —— 而这行改动看起来人畜无害。
2. **两条路径共用一段 SQL，任何一次改动都要同时思考两种语义。** 某天有人为了修 C 端的分页，
   在 SQL 里加了个条件，管理端跟着变了 —— 没人会想到。
3. **它把「权限边界」降级成了「一个变量」。** 权限边界应该是**结构**，不是**值**。

正确做法：**两条独立的 SQL + 两个独立的服务方法**，
把「带不带 `user_id`」的差别**沉到 SQL 文本里**，而不是沉到一个变量里。

```
OrderMapper.xml
  ├─ selectMyOrders      WHERE o.user_id = #{userId}     ← C 端
  └─ selectAdminOrders   （无归属条件，条件由 <if> 拼）  ← 管理端
```

★ 附带的认知升级：**`userId` 在两个接口里的身份完全不同**。

| | C 端的 `userId` | 管理端的 `userId` 过滤条件 |
|---|---|---|
| 来源 | token（客户端连传的机会都没有） | **可选的查询条件**（运营想看某人的单） |
| 作用 | **权限边界** —— 拿掉它就泄露 | 纯粹的筛选 —— 有没有它都不影响「谁能调」 |

### 3.2 ★★ 取消：必须复用同一段回补代码

「管理端取消」和「用户取消」在业务上的差别只有一条：**要不要检查归属**。
其余（`WHERE status='PENDING_PAYMENT'` 抢资格、`releaseLocked` 回补、写流水）**必须逐字相同**。

```
用户取消   cancel(userId, orderId)    ：requireOwn（404） → CAS → 回补
管理端取消 cancelByAdmin(orderId)     ：            （跳过） → CAS → 回补
                                          ↑ 唯一差别
```

★ 为什么不能写第二份：`releaseLocked` 的守卫（`locked_stock >= quantity`）与流水口径
（`CANCEL_RELEASE` / `change = +n`）是和 Day 14 的全链路对账绑定在一起的。
两处各写一遍，早晚会分叉 —— 分叉之后，对账脚本会开始报「账目不一致」，
而错误会看起来像库存模块的 bug。

⚠️ **本日不做「管理员取消已支付订单」** —— 那是**退款**，属于售后域（要动 `mall-payment`、
要给状态机加边）。`cancelByAdmin` 的 CAS 条件与用户取消**完全一致**，
PAID 单过来会被 CAS 挡成 400 —— 这不是缺陷，是**本日边界的显式声明**。

### 3.3 VO 的取舍

管理端列表要看到**买家**（`user_id` + 昵称），C 端的 `OrderVO` 里没有这些。

| 选项 | 评价 |
|---|---|
| 复用 `OrderVO` | 会在响应当中凭空多出 `userId`（C 端不需要），且**C 端接口会跟着变胖** —— 一个 VO 服务两种可见性，违背「出参白名单」 |
| **新建 `AdminOrderVO`**（推荐） | 显式列 = 白名单；C 端的响应形状一个字都不动 |

⚠️ `PageResult` 只有 `of(IPage)`，**没有 `convert`**（这是 `mall-common` 里钉死的 API）。
新 VO 的装配要用 MP 的 `page.map(...)` 或手动装配，别去找 `PageResult.convert`。

---

## 四、第 2 步：库存查询 / 调整 / 流水

### 4.1 ★★ 第四个写点：管理员改的是**守恒式**，不是一个数

库存表的核心不变式（Day 12 定，全项目对账口径）：

```
total_stock = available_stock + locked_stock + sold_stock
```

管理员来「调整库存」，天真的写法是只改可售：

```sql
-- ❌ 立刻打破恒等式
UPDATE inventories SET available_stock = available_stock + 10 WHERE sku_id = ?;
```

恒等式一破，**此后所有对账脚本都会开始报警**，而错误会指向「库存流水不对」——
离真正的原因（管理端少改了一格）十万八千里。

**正确语义：调整 = 同时改 `total` 和 `available`，同样的量。**

```sql
UPDATE inventories
   SET total_stock     = total_stock     + #{delta},
       available_stock = available_stock + #{delta},
       updated_at      = CURRENT_TIMESTAMP
 WHERE sku_id = #{skuId}
   AND total_stock     + #{delta} >= 0      -- ★ 守卫①
   AND available_stock + #{delta} >= 0      -- ★ 守卫②
RETURNING available_stock                    -- ★ 拿 after_stock 写流水
```

三个必须理解的点：

1. **为什么 `total` 必须跟着动** —— 「调整」是「仓库里真多/真少了货」，那是总量变了；
   而 `available` 变是因为它要跟着总量走。这与「下单锁库」（`available → locked`，**total 不变**）
   是两件完全不同的事：**前者改的是「有多少货」，后者改的是「货归哪一格」**。
2. **为什么绝不碰 `locked` / `sold`** —— 那两格记的是**已发生的业务事实**（谁锁着、谁买过）。
   要把 `locked` 降下来，唯一合法的路径是「释放超时单」那条业务流程（它同时会改订单状态）；
   单独调 `locked` 等于**让账本和事实脱钩**。
3. **0 行 = 调整后会出现负数** → 400「调整后可用/总库存不能为负」。
   这是 CAP 式的守卫：**判断写在 `WHERE` 里，由数据库原子完成**，不是「先查再改」。

★ 实现细节沿用 Day 13 的定型做法：**用 `<select>` 包住一条 `UPDATE ... RETURNING`**
（`<update>` 会丢掉结果集，没法接 `RETURNING`），并且 **必须写 `flushCache="true"`**
（MyBatis 一级缓存默认 `SESSION`，`<select>` 会填充它；不刷的话同一事务里第二次调用**根本不会发 SQL**）。

### 4.2 流水：`InventoryLogType` 要加第四个常量

`inventory_logs` 的口径（Day 14 拍板）：`before/after_stock` 指 **`available_stock`**，
`change_quantity` **带符号**且恒等于 `after - before`。

新增：

```
ADMIN_ADJUST   change = delta   （available 跟着 total 动）
```

| type | 动作 | total | available | locked | sold | change |
|---|---|---|---|---|---|---|
| `ORDER_LOCK` | 下单 | — | −n | +n | — | `-n` |
| `PAY_SOLD` | 支付 | — | — | −n | +n | **`0`** |
| `CANCEL_RELEASE` | 取消 | — | +n | −n | — | `+n` |
| **`ADMIN_ADJUST`** | **管理端调整** | **±d** | **±d** | — | — | **`±d`** |

★ 三个「—」是承重结论，不是「没记到东西」。尤其：
**`ADMIN_ADJUST` 的 `total` 会变，这是它区别于其余三条的唯一特征** ——
`reference_id` 写 `NULL`（没有关联订单，与 `ORDER_LOCK` 同理由）。

⚠️ `InventoryLogType` 的类注释现在写着「**三个**常量与**三个**写点一一对应，不多不少」。
本日必须把这句改成四个 —— **说谎的注释比没有注释更坏**：下一个人会照着注释去找「只有三个写点」，
然后漏掉管理端这条路径。

### 4.3 调整接口的输入设计

```
POST /api/admin/inventory/skus/{skuId}/adjust
body: { "delta": 10, "reason": "补货入库" }
```

- `delta` **带符号**（正=补货/盘盈，负=报损/盘亏），`@NotNull` 且 `!= 0`；
- `reason` 必填（`@NotBlank`，≤200）：**管理端的每一次改动都要有理由**
  —— 这是审计的最低要求，成本是一个字段；
- ⚠️ `reason` 本日**只校验、不落库**（`inventory_logs` 没有备注列）。
  这是**显式取舍**：要落库就得加列（DDL + 实体 + VO 三处改动），
  而 V1.0 无前端、审计需求尚未成型 —— 记在这里，不做。

---

## 五、第 3 步：验收 + 对账 + 收官

### 5.1 ★★ 权限矩阵：本日压在最前面的一组

要把「登录就能用」和「有权限才能用」区分开，需要**三种身份**：

| 身份 | 来源 | 预期 |
|---|---|---|
| 匿名 | 不带头 | `/api/admin/**` → **真 HTTP 401** |
| C 端 `demo` | `/api/auth/login` | → **真 HTTP 403**（token 的 `perms` 是空集） |
| `admin`（SUPER_ADMIN） | `/api/auth/admin/login` | → 200 |
| **`op_order`（只挂 ORDER_ADMIN）** | 需新建 | 订单端点 200；**库存端点 403** |

★ 第 4 种身份是本日的**关键靶子**：`admin` 是超管、全权限，**它证明不了权限码真的在生效**
（任何 `@PreAuthorize` 写错都照样 200）。只有一个「有 `order:*` 但没有 `inventory:*`」的账号，
才能把权限矩阵从「都通过」变成**有区分度的实验**。

→ 需要夹具：`op_order` / `{noop}op123456` 挂角色 3（ORDER_ADMIN）。
幂等 INSERT + 序列校准（`admins` 表是显式 id 种子，别拿序列当基线断言）。

★ 401 与 403 都是**真实状态码**（由 Security 过滤器层给出，不经过 `@RestControllerAdvice`），
与业务异常的「HTTP 200 + body.code」不是一回事 —— 断言时要分开写，别用 `code_of()`。

### 5.2 ★★ 清理难题：流水是账本，可本日要求「逐字节回基线」

Day 14–16 的脚本都做到了 `VERIFY -- the database is byte-for-byte back at baseline`。
本日有一个新麻烦：**库存调整改变了 `total_stock`，而且留下了流水**。
`inventory_logs` 的口径是「只增不改」，清理时**删自己造的流水**合适吗？

**结论：合适，但有明确边界** —— 与既有做法一致（脚本一直在删自己造的订单/支付/评价）：

1. 开始时记 **流水 high-water id**（`max(id)`），只处理 `id > high-water` 的行；
2. 库存：**用反向调整还原**（`+d` 之后 `-d`）→ 顺带把这条反向流水也记进账本；
3. 清理阶段删除本轮产生的所有行（流水 / 订单 / 明细 / 支付）；
4. 最后断言 **7 个 SKU 五字段 + 6 张表计数** 与基线逐字节一致。

⚠️ 第 2 步与第 3 步的顺序有讲究：**先用业务接口反向调整，再删流水** ——
这样「清理动作走的是业务路径」这件事本身也被验证了一遍（反向调整的守卫同样要成立）。

### 5.3 ★★ 并发：库存调整也要打一次

单条 `UPDATE` 是原子的，但「**改库存 + 写流水**」是**两条语句**，
它们的同生共死靠 `@Transactional` —— 这是本日唯一一个真正的并发断言点：

- 8 线程同时对同一 SKU 调 `adjust {delta:-1}`，可用库存若只够 5 次 → 断言 **成功 5、失败 3**；
- 断言 **流水条数 == 成功次数**（一条不多、一条不少）；
- 断言 `Σ change == after - before`，且恒等式仍成立。

### 5.4 对账口径（第 4 次演进）

| 日 | 新增的守恒式 |
|---|---|
| Day 12–13 | `available + locked + sold == total` |
| Day 14 | `Σ(ORDER_LOCK.change) + Σ(CANCEL_RELEASE.change) == available − 初值`；`PAY_SOLD.change == 0` |
| Day 16 | 评价域：`count(reviews) <= count(COMPLETED 明细)`、一人一明细一条 |
| **Day 17** | **`Σ(ADMIN_ADJUST.change) == total − 调整前 total`**（管理端调整只该由这条流水解释） |

---

## 六、验收计划（`backend/loadtest/day17-admin-e2e.py`）

| 组 | 断言要点 |
|---|---|
| `[0]` | 基线指纹：7 SKU × 5 字段 + 6 张表计数 + 流水 high-water id |
| `[1]` | 四种身份登录（demo / admin / op_order / 匿名）|
| `[2]` | ★★ **权限矩阵 6 端点 × 4 身份**：匿名 401、C 端 403、`op_order` 订单通/库存 403、超管全通 |
| `[3]` | ★★ 数据可见性反转：demo 与 intruder 各造一单 → **管理端列表同时看见两张**，各自 C 端列表只看见自己那张 |
| `[4]` | `status` / `userId` 过滤正确；**分页夹紧**（`size=0`→1、`size=-1`→1 不拖全表、`size=999`→100、`page=0` 被容忍） |
| `[5]` | 管理端详情：任意订单 200；不存在 → 业务 404；`abc` → 业务 400 |
| `[6]` | 管理端取消：`PENDING_PAYMENT` → 200 且 `locked→available` 回补 + 1 条 `CANCEL_RELEASE`；`PAID` → 400 且**库存一格未动** |
| `[7]` | 库存列表：四格数字与 DB 一致；JOIN 出的 SKU/商品名非空 |
| `[8]` | ★★ 调整：`+10` 后 `total+10` 且 `available+10`、`locked/sold` 不变、流水 `change=+10`；再 `-10` 还原；**恒等式仍成立** |
| `[9]` | ★★ 越界：调到负数 → 400，且 **DB 一行未动 + 流水一条未写**（CAS 0 行的双重证据） |
| `[10]` | ★★ 8 线程并发扣同一 SKU：成功数 == 流水条数 == 库存实际变化量 |
| `[11]` | 流水查询：分页 + `skuId` 过滤 + `type` 过滤 |
| `[12]` | 对账：§5.4 四条守恒式全 0 |
| `[13]` | 清理 → `[14]` 逐字节回基线 |

**脚本与实现打架时，改脚本，不是改设计**（Day 16 的 `orderItemId=1` 事件）。

---

## 七、提交清单（按主题分批）

```
① 地基      backend/sql/05-admin-permissions.sql（权限补发，幂等）
② 功能 1    mall-order 的 AdminOrderController / AdminOrderVO / mapper+XML / OrderService 3 方法
③ 功能 2    mall-inventory 的 AdminInventoryController / DTO / VO×2 / mapper+XML
            / InventoryLogType（+ADMIN_ADJUST）/ InventoryService 3 方法
④ 验收      day17-admin-e2e.py + day17-m1-regression.py（已提交）+ 两份报告
⑤ 文档      docs/daily/Day-17-管理端订单与库存.md + docs/daily/README 索引（如有）
```

★ 提交前先 `git reset`（IDEA 会自动 `add` 新文件）；含 CJK 的 message 走 `git_commit_utf8.py`。

---

## 八、动手对照清单（★ 写一行勾一行）

### 8.1 逐文件改动 · 第 1 步（管理端订单）

| 文件 | 改动 |
|---|---|
| `mall-order/.../mapper/OrderMapper.xml` | 新增 `selectAdminOrders`（**无归属条件**，`<if>` 拼可选条件，`ORDER BY o.id DESC` 兜底） |
| `mall-order/.../mapper/OrderMapper.java` | 声明 `selectAdminOrders(IPage, status, userId)` |
| `mall-order/.../vo/AdminOrderVO.java` | 新建（含 `userId` / `userNickname` / `status` / `payAmount` / `createdAt`） |
| `mall-order/.../service/OrderService.java` | 新增 `listAllOrders` / `detailByAdmin` / `cancelByAdmin` |
| `mall-order/.../service/impl/OrderServiceImpl.java` | 实现三个；`cancelByAdmin` **复用**取消链路的 CAS + 回补 |
| `mall-order/.../controller/AdminOrderController.java` | 新建，三个端点，**每个方法都挂 `@PreAuthorize`** |

### 8.2 逐文件改动 · 第 2 步（库存管理）

| 文件 | 改动 |
|---|---|
| `mall-inventory/.../common/InventoryLogType.java` | 加 `ADMIN_ADJUST`；★ 改类注释「三个」→「四个」 |
| `mall-inventory/.../mapper/InventoryMapper.java` | 加 `adjustStock`（`<select>` 包 `UPDATE ... RETURNING`） |
| `mall-inventory/.../resources/mapper/InventoryMapper.xml` | 加 `adjustStock`（`flushCache="true"`）+ `selectInventoryPage`（JOIN 名称） |
| `mall-inventory/.../mapper/InventoryLogMapper.java` / `.xml` | 加分页查询（按 `skuId` / `type` 可选过滤） |
| `mall-inventory/.../dto/InventoryAdjustDTO.java` | 新建（`delta` + `reason`） |
| `mall-inventory/.../vo/InventoryVO.java` / `InventoryLogVO.java` | 新建 |
| `mall-inventory/.../service/InventoryService.java` + `Impl` | 加 `listSkus` / `adjust` / `listLogs`；`adjust` **必须 `@Transactional`**（改库存 + 写流水） |
| `mall-inventory/.../controller/AdminInventoryController.java` | 新建，三个端点 + `@PreAuthorize` |

### 8.3 陷阱清单

1. ★★ **每个管理端方法都要挂 `@PreAuthorize`** —— 漏一个，那个接口静默变成「登录即可用」。
   `@EnableMethodSecurity` 已开，但**不挂注解就没有任何方法级检查**，不会有任何警告。
2. ★★ **绝不能挂在 `/api/products/**` 下** —— 那条路径 `GET` 是白名单，会静默公开。
3. ★★ **新权限不补发 → 永远 403**（见 §0.4）。改完 SQL 要**重新执行**并核对 `role_permissions`。
4. ★ **`<select>` 包 `UPDATE ... RETURNING` 必须 `flushCache="true"`**（一级缓存坑，Day 13 实测过）。
5. **XML 四铁律**：放 `resources/mapper/`、方法名与 `id` 逐字符一致、**别名全用下划线**（`AS adminOrderId` 会被 PG 折成小写 → 字段静默为 null）、注释里**不能出现连续两个减号**。
6. **分页夹紧写在 `new Page<>()` 之前**；`size<0` 是「不执行分页、查全表」。
7. **`PageResult` 没有 `convert`**，新 VO 用 `page.map(...)`。
8. **管理端列表不要复用 C 端 SQL**、不要布尔开关（§3.1）。
9. **新 VO 用作 `resultType` 必须加 `@NoArgsConstructor`**（走反射无参构造）。
10. **`@Transactional` 加在 `adjust` 上**（跨两张表：`inventories` + `inventory_logs`）；
    但**不要**加在 `cancelByAdmin` 之外的地方乱加 —— `ship` 当初不加是因为它只写一张表。

### 8.4 ★ 「不要动」清单（省得白改）

- 周 `SecurityConfig` 的**白名单** —— `/api/admin/**` 默认「要登录」，加进去就是自毁。
- `OrderController` 里现成的 6 个 C 端端点 + `ship`（路径不迁移，见 §0.5）。
- `InventoryService` 的三个已验收写点（`deductForOrder` / `moveLockedToSold` / `releaseLocked`）——
  本日只**新增**第四个，不改已有的。
- `03-data.sql`（历史种子）—— 新授权进 `05-admin-permissions.sql`，别回头改历史文件。
- 订单状态机（`OrderStatus` 的五条边）—— 本日**不加边**，不加状态。

### 8.5 自检顺序（写完按这个顺序验）

```
1. sql/05-admin-permissions.sql 重新执行 → 查 role_permissions 是否真的补上
2. mvn -o install -DskipTests                     → 编译
3. day17-xml-check（复用 day16-xml-check.py 思路）→ XML 良构 + statement 齐全
4. 起 Docker + 起应用（★ 直接跑 jar，别用 spring-boot:run）
5. day17-admin-e2e.py                             → 15 组
6. day16-review-e2e.py                            → 75/75（回归：确认没碰坏评价域）
7. git 分批提交 + push.py 推送 + 三重验证
```

---

## 附：本日不做的（留档，避免走偏）

| 候选 | 为什么不做 |
|---|---|
| 管理员取消**已支付**订单 / 退款 | 属售后域，要动 `mall-payment` + 给状态机加边（Day 14 刚调稳） |
| Dashboard 统计 | 纯读聚合，随时能补，且没有新概念 |
| 评价审核（`reviews.status` 置 0） | 已有列，但属「评价域收尾」，与本日主线无关 |
| 库存告警 / 阈值 | 需要新列或新表，本日不引入 DDL |
| `reason` 落库 | 需要给 `inventory_logs` 加列（§4.3 已记取舍） |
| 用户管理接口（`user:list` 已有权限码） | 留作候选，与本日「订单 + 库存」主题不一致 |
