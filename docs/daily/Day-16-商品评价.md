# Day 16 — 商品评价：走完里程碑 M1

> **一句话**：Day 15 让订单走到 `COMPLETED`。Day 16 补上最后一环 —— **评价**。
> 走完它，里程碑 **M1「下单 → 支付 → 收货 → 评价」** 就闭环了。
>
> **前置**：Day 15 收官 ✅（发货 + 确认收货 56/56，五条边全部打通，已 push `79e81e1`）。
> **路线依据**：`Day-12-从购物车下单.md:1024` 的里程碑图已排定 `Day 15/16 评价 → 里程碑 M1`；
> `Day-15-发货与确认收货.md:626` 的「本日不做」表把评价明确划给 **Day 16**，
> 并写明了本日要处理的两个前置：**「表已建未用、还缺唯一约束」**。

---

## 〇、开工前的四件事（★ 先看这一节）

### 0.1 事实盘点（2026-09-20 实查）

| 项 | 现状 |
|---|---|
| `orders` | 8 行（5 `PAID` + 3 `CANCELLED`）—— ★ **零 `COMPLETED`**（Day 15 的靶子自清了） |
| `reviews` | **0 行** —— Day 03 建表至今一次没写过 |
| `products` / `product_skus` | 5 SPU / 7 SKU |
| `payments` 5 / `order_items` 9 / `inventory_logs` 0 | 与 Day 15 收官一致 |
| 账号 | `demo/demo123`(id=1)、`intruder/intruder`(id=2)、`admin/admin123`(id=1) |
| **权限 seed** | ★ **零 review 相关权限**（`03-data.sql` 只有 `product:*` 6 个 + `order:list` / `order:ship`） |
| **DDL** | ★★ **本日有 DDL** —— 与 Day 15 的「零 DDL」正相反 |

★ 与 Day 14 的处境相同、与 Day 15 相反：**没有现成的 `COMPLETED` 靶子**，必须走 API 造一张。
但这次造的是一张**全链路**的单（下单 → 支付 → 发货 → 确认 → 评价）——
造靶子的过程本身就是 M1 的验收。

### 0.2 ★★ 发现：本日与 Day 13–15 的根本不同 —— 首次启用一张「建好却从未写过」的表

Day 13 支付、Day 14 取消/超时、Day 15 发货/确认，走的都是「**表已经有了，只是没人写过**」的路
（`payments`、`orders` 的 `cancelled_at` / `shipped_at` / `completed_at` 列都是 Day 03 建好的）。
但那些表**已经被约束保护住了**：`payments` 有 FK，`orders.status` 由 CAS 的 `WHERE` 兜着。

`reviews` **不是**。它建了 3 个 FK，却**一条唯一约束都没有** ——
于是「一个订单明细只能评一次」这条业务规则，**在数据库层完全没有牙齿**。

★★ 而更关键的是：**光加唯一约束还不够。**

### 0.3 ★★ 缺口与它的补法：两条 DDL，一条都不能少

`reviews` 的 `order_item_id` 是 **可空**（`is_nullable = YES`，已实测），
而 **PostgreSQL 的 `UNIQUE` 约束豁免 NULL** —— 两行 `order_item_id = NULL` 是「互不相等」的，
**全都合法**。所以：

| 只加什么 | 同一明细评两次 | `order_item_id` 传 NULL 评两次 | 结论 |
|---|---|---|---|
| 什么都不加 | ✗ 两次都进库 | ✗ 两次都进库 | 完全没防线 |
| 只加 `UNIQUE(order_item_id)` | ✅ 第二次被拒 | ✗ **两次都进库**（NULL 豁免） | **防线有洞** |
| `UNIQUE` + `NOT NULL` | ✅ 第二次被拒 | ✅ 第二次被拒（`23502`） | ✅ 完整 |

→ 本日 DDL 定稿（**两条**，顺序不能反）：

```sql
ALTER TABLE reviews ALTER COLUMN order_item_id SET NOT NULL;
ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
```

★ 顺序理由：`SET NOT NULL` 是针对「**存量数据里有没有 NULL**」的体检；
先体检再加约束，万一表里已经有脏数据，**体检会当场报错**（而不是加了个形同虚设的约束后才发现）。
本日 `reviews` 是 0 行，两条都会顺利通过 —— 但顺序仍按「先体检、后上锁」写。

### 0.4 ★★ 机制实证（已完成，5 个探针全部实测）

探针脚本 `backend/loadtest/day16-probe.sql`，**全部包在 `BEGIN/ROLLBACK` 里，跑完库回到原样**
（实测复核：`reviews` 仍 0 行、0 个新约束、`order_item_id` 仍可空）。

| # | 探针 | 期望 | **实测** |
|---|---|---|---|
| 0 | `reviews` 的列定义 | `order_item_id` 可空 | ✅ `is_nullable = YES` |
| 0b | `reviews` 现有约束 | 只有 FK + PK，无 UNIQUE | ✅ `fk_review_order` / `fk_review_product` / `fk_review_user` / `reviews_pkey`，**4 个，零 UNIQUE** |
| 1 | 无约束，同一 `order_item_id` 插两次 | 两次都成功（缺口真实） | ✅ `INSERT 0 1` ×2 → `count = 2` |
| 2 | 加 `UNIQUE` 后插同值 | 第二次失败 `23505` | ✅ `duplicate key value violates unique constraint "uk_reviews_order_item"` / `DETAIL: Key (order_item_id)=(1) already exists.` |
| 3 | 加 `UNIQUE` 后插两行 **NULL** | 两行都成功（NULL 豁免） | ✅ `INSERT 0 1` ×2 → `count = 2` |
| 4 | `NOT NULL` + `UNIQUE` + `ON CONFLICT DO NOTHING` | 第二次返回 **0 行** | ✅ `INSERT 0 1` 然后 **`INSERT 0 0`** → `count = 1` ★★ |
| 5 | 只加 `UNIQUE` 不加 `NOT NULL`，走 `ON CONFLICT` | NULL 行**绕过**防线 | ✅ `INSERT 0 1` ×2 → `count = 2` ★★ |
| 6 | 加 `NOT NULL` 后插 NULL | `23502` | ✅ `null value in column "order_item_id" violates not-null constraint` |

**探针 4 是本日最重要的发现**：`ON CONFLICT (order_item_id) DO NOTHING` 的**返回影响行数**
（第一次 `1`、第二次 `0`）—— 这正是本项目一直在用的 **CAS 语义**
（`UPDATE ... WHERE status = ?` 靠影响行数报答案），只不过这次用的是 **INSERT 的冲突检测**。

**探针 5 是本日最重要的警告**：`ON CONFLICT` 的判定**也依赖唯一索引**，
所以 `NOT NULL` 不是「顺手加的礼貌约束」——**没有它，`ON CONFLICT` 会被 NULL 行整条绕过**。

★ 探针脚本的一个设计要点（踩过）：**在事务里做「预期失败」的实验时，失败之后该事务内所有后续语句都会被忽略**
（`current transaction is aborted, commands ignored until end of transaction block`）。
所以探针 2 / 6 里**把想看的 `SELECT` 一律放在会失败的语句之前**，或者干脆不依赖失败后的输出。

### 0.5 靶子怎么选：**零 `COMPLETED`，必须走 API 造一张**

那 5 张 `PAID` 单是 §0.1 里 `sold` 基线的唯一证据，**不能动**（与 Day 15 §0.3 同一条理由）。
本日要造的是**一张全链路单**：

```
下单 → 支付 → 发货(admin) → 确认收货 → 评价
                                  ↑
                          前四步 = M1 的前半段，第五步才是本日的新东西
```

★ 造靶子本身就是 M1 的端到端走查 —— 所以本日的验收脚本**天然同时覆盖 Day 12/13/15 的成果**。

### 0.6 开工准备（AI 已完成 ✅ 2026-09-20）

工作方式：**陪练** —— 生产代码（`backend/mallx/**`）由用户亲手写；AI 负责 DDL / 模块骨架 /
编译 / 起应用 / 跑验收 / 审查。

| 项 | 状态 | 提交 |
|---|---|---|
| 两条 DDL 执行 + 幂等复跑 + 结构复核 | ✅ `order_item_id` → `NOT NULL`、`uk_reviews_order_item` 已建 | `c072629` |
| **DDL 牙齿复核** | ✅ 同明细插两次 → `23505`；`ON CONFLICT` 第二次 → `INSERT 0 0`；插 NULL → `23502`（全程回滚零痕迹） | `e618197` |
| `mall-review` 模块骨架（4 处 pom + 包目录） | ✅ `mvn -o install -pl mall-review -am` → **BUILD SUCCESS** | `fcbda08` |
| 验收脚本 `day16-review-e2e.py`（13 组） | ✅ `py_compile` 通过；**待代码落地后跑** | `e618197` |

★ 剩下**全部是生产代码**：`mall-order` 侧的跨模块契约 + `mall-review` 的业务代码，见 §8.1 / §8.2。
★ `docs/daily/Day-16-商品评价.md` §8 的清单是「改哪一行、必须满足什么、别踩什么」；
`backend/loadtest/day16-review-e2e.py` 同时充当**验收标准**，写代码时对着它对。

### 0.7 ★★ 分工改档（2026-09-20 用户拍定）：AI 交**骨架**，逻辑全部由用户写

> 用户先是说「帮我写好」，随后改口 **「只要写好骨架就好了」** ——
> 于是本日最终形态是：**AI 交出能编译、能启动、能被路由的类骨架，方法体与 SQL 一律留 `TODO`。**

| 层 | AI 已交 | 用户要写 |
|---|---|---|
| **DDL** | ✅ 两条约束已执行 + 牙齿复核（§0.3 / §0.4） | —— |
| **模块接入** | ✅ 4 处 pom + 包目录（§2.4） | —— |
| **类骨架** | ✅ 14 个类/文件：包、注解、字段、方法签名、Javadoc、难点清单 | —— |
| **方法体** | ⬜ `TODO` 注释（含步骤拆解 + 要用的 import） | ★ **全部** |
| **SQL** | ⬜ `ReviewMapper.xml`（6 条）+ `OrderItemMapper.xml`（1 条），只留 `id` / `resultType` + TODO | ★ **全部** |
| **验收** | ✅ `day16-review-e2e.py`（13 组，验收标准）+ `day16-skeleton-smoke.py`（17 项，骨架自检） | —— |

**骨架自检结果**（`day16-skeleton-smoke.py`，✅ **17/17 全绿**）：

| 组 | 验的是什么 | 实测 |
|---|---|---|
| 1–2 | 应用起得来、能登录 | `/api/hello` 200、demo token 191 字符 |
| 3 | ★★ **`mall-review` 真的接进了 `mall-server`** | `GET /api/products/1/reviews` **匿名**可达（`code=500` = 走到 TODO；★ 若漏改 `mall-server/pom.xml` 这里会是 **404**） |
| 3 | ★ 白名单对任意 productId 生效 | `/api/products/999999/reviews` 匿名同样可达 |
| 4 | ★ 两个需登录端点的边界 | 匿名 `POST /api/reviews` / `GET /api/reviews/my` → **真 HTTP 401** |
| 5 | 带 token 能被路由 | 两个端点均 200 + `code=500`（TODO） |
| 6 | ★★ **DTO 校验收在骨架期就已生效** | `rating` 0/6/null、`content` 501 字、缺 `orderItemId` → 一律 `code=400` 且消息正确 |
| 7 | DDL 仍在位 | `is_nullable=NO`、`uk_reviews_order_item` 存在、`reviews` 0 行 |

★★ 第 3 组与第 6 组是本节的**两个关键证据**：
前者证明「模块接进去」这件事**不能靠编译成功来证明**（漏一处 pom 也编译成功），
后者的 5 条断言在**业务代码一行都没写**的情况下就全绿 ——
说明`@Valid` 与业务逻辑是两层，参数校验挂在 DTO 上，先于任何 Service 调用。

★ 骨架新增的两个 dev 工具（都不改生产行为）：
- `backend/loadtest/day16-skeleton-smoke.py` —— 骨架期自检（可重复跑、零写入）
- `backend/loadtest/day16-xml-check.py` —— 两个 mapper XML 的**良构性**检查（毫秒级）
  ⚠️ 它专门抓「XML 注释里出现连续两个减号」这个坑：**Maven 照抄不报错、MyBatis 启动才炸**。
  本次写骨架时 AI **自己就踩了一次**（`----` 用作项目符号）—— 靠这个脚本当场抓到。

★ 一处**脚本自身的假失败**已修（`day16-review-e2e.py` 分页边界组）：
原断言 `size=0 → n == 0` 照搬的是 MP 的原生行为（`LIMIT 0` → 空列表），
与 §4.4 定的夹紧规则（`size < 1` 归一到 1）**互斥** —— 实现按夹紧走，这条必假失败。
已改为断言「被夹到 1」。**教训：断言要对着【设计】写，不是对着【某个库的默认行为】写。**

---

## 一、全景：3 步

| 步 | 内容 | 新增技术点 | 产物 |
|---|---|---|---|
| **1** | **写评价** `POST /api/reviews` | ★ 新建 `mall-review` 模块（第 10 个）+ ★ **两条 DDL** + **三重派生** + `ON CONFLICT` 当 CAS + 跨模块契约对象 | 1 模块 + 3 个 order 侧改动 |
| **2** | **读评价**：商品评价列表（公开）+ 我的评价（登录）+ 评分聚合 | ★ 路径决定可见性（白名单）+ 别名映射坑 + 分页三坑 | 2 端点 + 2 VO |
| **3** | 端到端 **M1 闭环** + 评价域对账 + 收官 | ★ 新增评价域守恒式 | 验收脚本 + 文档 |

★ 与 Day 15 最大的不同：
- Day 15 是「**两条边都不碰库存**」；本日是「**一个字节的库存都不碰、也不碰订单状态**」——
  评价是**纯新增**，`orders` / `inventories` 全是只读。
- Day 15 零 DDL；本日 **2 条 DDL**（而且是本日最有教学价值的部分）。

---

## 二、数据模型与模块边界

### 2.1 `reviews` 表解剖（Day 03 建好，本日首次使用）

| 列 | 类型 | 现状 | 本日怎么用 |
|---|---|---|---|
| `id` | BIGSERIAL | PK | 自增 |
| `user_id` | BIGINT NOT NULL | FK → `users` | ★ **从 token 派生**，客户端不能传 |
| `product_id` | BIGINT NOT NULL | FK → `products` | ★★ **从 `order_items` 反查**，客户端绝不能传（见 §3.1） |
| `order_id` | BIGINT NOT NULL | FK → `orders` | ★ **从 `order_items` 反查** |
| `order_item_id` | BIGINT **可空** ← ★ 要改 | —— | 评价的**唯一入口**；★ 本日 `SET NOT NULL` |
| `rating` | SMALLINT NOT NULL | 无 CHECK | 应用层 `@Min(1) @Max(5)` |
| `content` | TEXT 可空 | **无长度上限** | 应用层 `@Size(max = 500)` |
| `images` | JSONB 可空 | —— | ★ **本日不用**（见 §四 取舍） |
| `status` | SMALLINT NOT NULL DEFAULT 1 | —— | 固定写 `1`；列表查询加 `WHERE status = 1` |
| `created_at` / `updated_at` | TIMESTAMP NOT NULL DEFAULT now() | —— | 自定义 XML INSERT **不走填充器** → **必须手写**（Day 13/14/15 同一个坑） |

★ 表里**没有** `order_no` / `is_anonymous` / `reply_content` 之类的列 —— 本日不扩表（`images` 已有列但不用）。

### 2.2 ★ 模块放哪：三个方案

| 方案 | 做法 | 评价 |
|---|---|---|
| **A（采用）** | **新建 `mall-review`**，依赖 `mall-common` + `mall-order` | 评价是独立业务域，与 22 张表的「七、评价模块」对齐；依赖方向干净；★ 好处是「新模块开张」这套流程**再走一遍**（Day 05 之后就没新建过模块了） |
| B | 放进 `mall-order`（评价是订单的延伸） | 最省（零新模块、零 pom 改动）；但 `OrderController` 会长出评价端点，「订单状态机」和「商品口碑」混成一锅 |
| C | 放进 `mall-product` | 语义上贴合（评价是商品的属性）；但要 `mall-product → mall-order`，把订单域拖进商品模块 |

★ 选 **A**。三个额外理由：
1. `mall-order` **不依赖** `mall-product`（只有 `mall-common` + `mall-inventory`），所以 `mall-review → mall-order` **无环**；
2. 项目在 Day 05 之后就没再新建过模块，`mall-marketing` 一直是空壳 —— 本日正好把「新模块开张」补一次实践；
3. 本日 DDL 要动 `reviews`，把它**关在自己的模块里**，改动面最小。

### 2.3 ★★ 为什么 `mall-review` **不需要**依赖 `mall-product`

这是个容易多写一个依赖的地方。查 `order_items` 表结构：

```
order_items: id, order_id, product_id, sku_id,
             product_name ★, sku_name ★, price, quantity, total_amount, image ★
```

★★ **`product_name` / `sku_name` / `image` 都是下单那一刻的快照** ——
评价列表要展示的商品信息**全在订单域内**，根本不用回 `products` 查。

这也正是 `OrderItemVO` 的类注释早就写明的事：

> 这里所有字段都是【快照值】，直接来自 `order_items` 表，不 JOIN `product_skus` / `products`
> —— 商品改了价、被软删，明细照原样显示。

→ 最终依赖图：

```
mall-review ──> mall-common     （Result / PageResult / BusinessException）
mall-review ──> mall-order      （拿「这笔购买的事实」＋ 跨模块契约对象）
```

### 2.4 ★ 新模块开张要改的 4 处（★ 漏一个就出「编译通过但运行 404」）

| # | 文件 | 改动 | 漏了会怎样 |
|---|---|---|---|
| 1 | `backend/mallx/pom.xml` | `<modules>` 加 `<module>mall-review</module>` | ★ 模块根本不被构建 |
| 2 | `backend/mallx/pom.xml` | `<dependencyManagement>` 加 `mall-review` 坐标（`${project.version}`） | 下游引用时版本解析失败 |
| 3 | `backend/mallx/mall-server/pom.xml` | `<dependencies>` 加 `mall-review` | ★★ **编译通过、启动成功、接口 404** —— Spring 扫不到这个模块的 Controller，最难查的一种 |
| 4 | `backend/mallx/mall-review/pom.xml` | 新建（依赖 `mall-common` + `mall-order`） | —— |

★ 记忆里那条「给空壳模块写代码**一律不用改 POM**」讲的是 **`mall-cart` / `mall-inventory` / `mall-marketing` 这类已存在的空壳**
（9 个模块坐标早已托管）。**新建第 10 个模块是另一回事** —— 3 处都要改。

★ 好消息：**模块内部零配置**依然成立 —— 全局 `@MapperScan("com.mallx.**.mapper")` +
`mapper-locations: classpath*:mapper/**/*.xml`（带星号才能扫到兄弟模块 jar 里的 XML）已覆盖新模块，
**不用加 `@Mapper`、不用改 yml**。

---

## 三、第 1 步：写评价（要点）

### 3.1 ★★ 核心安全设计：三重派生 —— 客户端只能传一个 id

`POST /api/reviews` 的请求体里，**只有 3 个字段是客户端说了算的**：

| 字段 | 客户端能传？ | 服务端怎么来 |
|---|---|---|
| `orderItemId` | ✅ **唯一入口** | —— |
| `rating` | ✅ | `@NotNull @Min(1) @Max(5)` |
| `content` | ✅ | `@Size(max = 500)` |
| `userId` | ❌ **绝不** | token 的 principal（`(Long) authentication.getPrincipal()`） |
| `orderId` | ❌ **绝不** | 由 `orderItemId` 反查 `order_items` |
| `productId` | ❌ ★★ **绝不** | 由 `orderItemId` 反查 `order_items` |
| `status` | ❌ | 固定写 `1` |

★★ **为什么 `product_id` 绝对不能信客户端**：
`reviews` 对 `products` 只有 FK 约束（「商品得存在」），**没有「你得买过」的约束**。
若 `product_id` 由客户端传，攻击者只要拿**自己一张合法的已完成订单**，就能给**任意商品**刷五星好评 ——
一次下单，刷遍全站。这是「**派生字段原则**」最典型的反面教材：

> 凡是服务端能算出来的，就不要让客户端告诉你。

★ 设计上把它做成**结构性不可能**：DTO 里**根本没有** `userId` / `orderId` / `productId` 三个字段。
（Spring Boot 默认 `FAIL_ON_UNKNOWN_PROPERTIES=false`，客户端硬塞这些字段只会被**静默忽略**，
而不是报错 —— 所以验收里要专门断言「塞了也没用」，见 §六 第 9 组。）

### 3.2 ★★ 重复评价的防线：`ON CONFLICT` 就是 CAS

评价写入**不是**「先查再插」：

```xml
<insert id="insertReview">
    INSERT INTO reviews (user_id, product_id, order_id, order_item_id,
                         rating, content, status, created_at, updated_at)
    VALUES (#{userId}, #{productId}, #{orderId}, #{orderItemId},
            #{rating}, #{content}, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT (order_item_id) DO NOTHING
</insert>
```

返回的**影响行数**就是答案（探针 4 已实测）：

| 影响行数 | 含义 | 上层动作 |
|---|---|---|
| `1` | 插入成功 | 200 |
| `0` | ★ 该明细**已评过**，冲突被 `DO NOTHING` 吞掉 | `BusinessException(400, "该商品已评价过")` |

★★ 这与项目一路走来的 CAS **完全同构** —— 只不过前几次是
`UPDATE ... WHERE status = 'PAID'`「**条件不满足 → 0 行**」，
这次是 `INSERT ... ON CONFLICT DO NOTHING`「**冲突 → 0 行**」。
**「把判断交给数据库、把影响行数当返回值」是同一种思想。**

★ 为什么不「先 `SELECT` 查有没有、没有才 `INSERT`」：
两个并发请求会**同时**查到「没有」，然后**双双插入**（TOCTOU）——
除非加锁或事务隔离级别拉高。`ON CONFLICT` 把这件事压进**一条语句、一个原子操作**里。

★ 也不推荐「硬插 + `catch DuplicateKeyException`」：效果一样但要靠异常做控制流，
而且**默认会被 `GlobalExceptionHandler.handleException(Exception)` 兜成 500**
（`DuplicateKeyException` 是 `RuntimeException` 的子类，`GlobalExceptionHandler` 里**没有**它的专用出口
—— 这与 Day 07 的 `AccessDeniedException` 是同一个坑）。
走 `ON CONFLICT` 就**不用动 `GlobalExceptionHandler` 一个字节**。

### 3.3 跨模块契约：向 `mall-order` 要「这笔购买的事实」

评价模块要回答两个问题：**「这个明细的订单是不是我的？」**、**「订单完成了吗？」**
—— 这两个问题的权威答案在订单模块，**不该由 `mall-review` 自己裸读 `orders` 表**。

所以在 `mall-order` 侧开一个**只读门面**，并定义一个**跨模块契约对象**：

```java
// com.mallx.order.api.OrderItemBuyContext  ← 新建 api 包，明确「这是给别的模块看的」
public class OrderItemBuyContext {
    private Long   orderItemId;
    private Long   orderId;
    private Long   productId;      // ★ 从 order_items 快照反查
    private Long   skuId;
    private String productName;    // ★ 快照，评价列表直接展示，无需回 products
    private String skuName;
    private String image;
    private String orderStatus;    // ★ 供上层判 COMPLETED
}
```

`OrderService` 新增一个方法（返回 `null` 表示「不存在或不是你的」）：

```java
/**
 * 供评价模块调用：按「订单明细 id」取出这笔购买的事实。
 * 明细不存在 / 不属于该用户 → 返回 null（上层统一翻成 404，与订单详情口径一致）。
 */
OrderItemBuyContext getBuyContext(Long userId, Long orderItemId);
```

实现落在**新建的** `OrderItemMapper.xml` 里（★ 注意：`mall-order` 的 `resources/mapper/` 下
**目前只有 `OrderMapper.xml`**，`OrderItemMapper` 一直是靠 MP 的 BaseMapper 活的，本日是**第一次**给它写 XML）：

```xml
<!-- ★ 别名一律用【下划线】，靠 map-underscore-to-camel-case 自动转驼峰。
     写成 AS orderItemId 会被 PG 折成小写 orderitemid → 映射不上（见 §8.3 陷阱 6） -->
<select id="selectBuyContext" resultType="com.mallx.order.api.OrderItemBuyContext">
    SELECT oi.id           AS order_item_id,
           oi.order_id     AS order_id,
           oi.product_id   AS product_id,
           oi.sku_id       AS sku_id,
           oi.product_name AS product_name,
           oi.sku_name     AS sku_name,
           oi.image        AS image,
           o.status        AS order_status
      FROM order_items oi
      JOIN orders o ON o.id = oi.order_id
     WHERE oi.id = #{orderItemId}
       AND o.user_id = #{userId}
</select>
```

★★ **归属条件写在 `WHERE` 里** —— 这样「明细不存在」与「不是你的」在 SQL 层就**合成同一个 `null`**，
上层拿到的结论天然不可区分（与 Day 13/14/15 的 404 伪装是同一条原则，
只不过这次防线在**别的模块**里，所以更要写死在 SQL 里，不能靠调用方自觉）。

**写入的完整流程**（`ReviewServiceImpl.create`）：

```
① orderService.getBuyContext(userId, orderItemId)
     null → BusinessException(404, "订单明细不存在")
② !"COMPLETED".equals(ctx.getOrderStatus())
     → BusinessException(400, "只有已完成的订单才能评价")
③ insertReview(...)   ← ON CONFLICT DO NOTHING
     rows == 0 → BusinessException(400, "该商品已评价过")
④ 回查并返回 ReviewVO
```

★ 三步的顺序不能换：**先归属（404）→ 再状态（400）→ 最后冲突（400）**。
与 `confirm` 的 `requireOwn` → CAS 是同一个结构：
防御性检查**由外向内**，越靠外的越先跑。

★ **不加 `@Transactional`** —— 单条 INSERT 自身即原子，`ON CONFLICT` 已经是并发安全的。
（第 ④ 步的回查若单独走一次 `SELECT`，也不需要在同一事务里：刚插入的行拿得到就拿，拿不到也不影响正确性。）

### 3.4 端点与路径

权限 seed 里**没有** review 相关条目，所以路径**不受既定设计约束**，但要满足两条硬约束：

| 端点 | 可见性 | 为什么要这个路径 |
|---|---|---|
| `POST /api/reviews` | 需登录 | `anyRequest().authenticated()` 兜住；C 端 token 权限集为空，**不能挂 `@PreAuthorize`** |
| `GET /api/products/{productId}/reviews` | ★ **公开** | ★★ 见 §4.1 —— 只有挂在 `/api/products/**` 下才**天然落在白名单里** |
| `GET /api/reviews/my` | 需登录 | 与 `POST` 同前缀，被 `anyRequest()` 兜住 |

★ 三个端点**都不接收 `userId` 参数** —— 用户是谁只从 token 来（与 `PaymentController` 同一条铁律）。

★ 一个「不写」的决定：**本日不 seed 任何 review 权限，也不挂 `@PreAuthorize`**。
理由：评价是 **C 端动作**，而 C 端 token 的权限集是空的（Day 15 §0.4 已实测两个 token 的 payload），
一挂就必然 403。管理端审核评价是 V2.0 的事（V1.0 连管理端页面都没有）。

---

## 四、第 2 步：读评价（要点）

### 4.1 ★ 路径决定可见性：白名单是按【路径 + 方法】匹配的

`SecurityConfig.java:51` 的白名单是：

```java
.requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
```

★★ **`GET /api/products/{productId}/reviews` 天然在白名单内** —— 游客也能看评价，
这正是电商的实情（未登录用户逛商品详情页时就该看到评价）。

而如果评价列表写成 `GET /api/reviews?productId=x`，它会被 `anyRequest().authenticated()` 兜住
→ **游客看不了评价**；把它加进白名单又会连 `/api/reviews/my` 一起公开
（白名单只认路径，**不认「同一个 Controller 里的不同方法」**）。

→ 结论：**商品维度的列表必须挂在 `/api/products/{id}/reviews` 下**。
代价是 `ReviewController` 要映射两个不同的前缀：

```java
@RestController
@RequestMapping("/api")          // ★ 类级只到 /api
public class ReviewController {
    @GetMapping("/products/{productId}/reviews")   // 公开（白名单覆盖）
    @GetMapping("/reviews/my")                     // 需登录
    @PostMapping("/reviews")                       // 需登录
}
```

★ 这不是 hack —— Spring 允许多个模块映射同一个路径前缀（这里是 `/api/products`，
`ProductController` 已经占着它），只要**完整路径不重复**即可。
但要在类注释里写清楚「为什么评价接口挂到商品路径下」，否则后来人一定会觉得莫名其妙。

★ 一个「不写」的决定：**不改 `SecurityConfig`**。白名单已经够用，动安全配置的收益是 0。

### 4.2 评分聚合：跟着列表一起返回

`products` 表**没有** `rating` / `review_count` 列（已核对），所以聚合只能实时算：

```sql
-- 与列表同一批数据源，一次查两件事（或两次查询）
SELECT COALESCE(ROUND(AVG(rating)::numeric, 1), 0) AS avg_rating,
       COUNT(*)                                    AS review_count
  FROM reviews
 WHERE product_id = #{productId} AND status = 1
```

★ **不做冗余列**（不加 `products.rating`）的理由：冗余列要靠「每次评价后重算」维护，
一旦漏算就**永久漂移**（本项目 Day 14 已经花了一整个白天处理账目漂移）。
实时 `AVG` 的值**必然等于明细重算** —— 这是「没有第二个真相」的又一处体现。

★ 返回结构：`Result<ReviewPageVO>`，其中

```java
public class ReviewPageVO {
    private BigDecimal avgRating;   // 平均分，1 位小数；无评价时 0
    private long       reviewCount; // 评价总数
    private List<ReviewVO> records;
    private long total;             // 分页信息
    private long current;
    private long size;
}
```

★★ **为什么不复用 `PageResult<T>`**：`PageResult` 是个**纯分页壳**（`records/total/current/size`），
往里塞 `avgRating` 会让它变成「什么都能装的袋子」—— 之后每个业务都想往它身上挂点私货。
聚合评分是**评价域**的概念，就让它在**评价域的 VO** 里。
（`GET /api/reviews/my` 没有聚合需求，**照旧复用 `PageResult`** —— 该复用的复用，该分的分。）

### 4.3 ★ 要不要 JOIN `users`：一个显式的取舍

评价列表要显示「谁评的」。三个选项：

| 选项 | 做法 | 评价 |
|---|---|---|
| **A（采用）** | XML 里 `LEFT JOIN users` 取 `nickname` / `avatar` | ★ **跨域只读表**，不引入模块依赖 —— 与 `PaymentMapper.xml` JOIN `orders` 是同一种做法 |
| B | 依赖 `mall-user` 模块，调它的 Service | 为一个昵称引入一个模块依赖 + 一个跨模块调用，收益不划算 |
| C | 完全不显示昵称 | 评价列表没有「谁」就没有可信度 |

★ 采用 A，并把取舍**写进 `ReviewMapper.xml` 的注释**：
「这里 JOIN `users` 是**只读**的跨域查询，不是模块依赖。`mall-review` 的编译期依赖仍然只有 `mall-common` + `mall-order`。」

★ 隐私细节：`nickname` 为 NULL 时回退成固定串（如 `用户****`），**不暴露 `user_id`**（`ReviewVO` 里根本没有这个字段）。

### 4.4 分页：把三坑一次性处理掉

Day 12 已实测的三个坑（不是推理）：

| 输入 | 实际行为 | 本日怎么处理 |
|---|---|---|
| `size < 0` | ★ MP **不执行分页 = 查全表** | 夹到 `[1, 100]` |
| `size = 0` | 返回**空列表**但 `total` 正常（比报错更难发现） | 同上 |
| `size > 100` | 无上限 | 截到 100 |
| `page < 1` | ★ MP 双层兜住（`Page` 构造 + `offset()` 都防了），实测安然无恙 | 只做防御性 `Math.max(page, 1)`，**不等于说它需要防** |

★ 夹紧一律写在 `new Page<>()` **之前**。
★ `page` 参数名对外用 `page`（与 `PaymentController` 的列表接口保持一致的对外叫法）。

---

## 五、第 3 步：端到端 M1 + 对账 + 收官（要点）

1. **全链路走查**：下单 → 支付 → 发货(admin) → 确认收货 → **评价** → 回查商品评价列表能看到刚写的那条
2. **写入侧断言**：三重派生正确（DB 里 `user_id` / `order_id` / `product_id` 与 `order_items` 逐字段一致）
3. **防线断言**：重复评价 → 400；★ **并发重复评价 → 恰好 1 条入库**（见下）
4. **越权断言**：`intruder` 用 `demo` 的 `orderItemId` → **404**（与「明细不存在」逐字节相同）
5. **资格断言**：`PENDING_PAYMENT` / `PAID` / `SHIPPED` 的订单评价 → 400
6. **参数断言**：`rating` 为 `0` / `6` / `null` → 400；`content` 超长 → 400
7. ★ **伪造断言**：请求体里硬塞 `productId` / `userId` / `orderId` → **被忽略**，入库值仍是派生值
8. ★★ **对账（本日新增评价域守恒式）**
9. **清理**：靶子订单 + 明细 + 支付 + 评价全删，7 SKU 逐字段回基线
10. **文档**：补实测小节
11. **提交 + push**
12. **更新记忆**

### 5.1 ★★ 并发重复评价：唯一约束的牙齿

Day 14 的并发对照（支付 vs 取消抢同一张单）证明的是 **`UPDATE` 的 CAS**；
本日要证明的是 **`INSERT` 的唯一约束**：

```
N 个线程同时 POST /api/reviews，同一个 orderItemId
        ↓
恰好 1 个返回 200，其余全部返回 400「该商品已评价过」
        ↓
DB 侧：该 order_item_id 恰好 1 行 ★★
```

★ 这一条之所以有价值，是因为它**把「`ON CONFLICT` 是原子的」从文档变成了实测** ——
如果实现写成「先查再插」，这个实验会**直接暴露**（N 个线程全查到「没有」，然后插进去 N 行）。

### 5.2 ★★ 评价域守恒式（对账口径的第三次升级）

Day 14 学会了「恒等式 ≠ 业务守恒」，Day 15 学会了「**守恒式本身会随状态机长大而失效**」。
本日不改库存口径（评价不碰库存），而是**给评价表自己立一条守恒式**：

```sql
-- ① 不存在「无购买依据」的评价：每条评价都能在 order_items 上找到同 order / 同 product 的依据
SELECT count(*) FROM reviews r
  LEFT JOIN order_items oi ON oi.id = r.order_item_id
 WHERE oi.id IS NULL
    OR oi.order_id   <> r.order_id
    OR oi.product_id <> r.product_id      -- ★ 期望 0

-- ② 不存在「一明细多评」：唯一约束的直接推论
SELECT count(*) FROM (SELECT order_item_id FROM reviews GROUP BY order_item_id HAVING count(*) > 1) t
                                           -- ★ 期望 0

-- ③ 评价数不会超过「已完成订单的明细数」（上限约束）
SELECT (SELECT count(*) FROM reviews) <=
       (SELECT count(*) FROM order_items oi JOIN orders o ON o.id = oi.order_id
         WHERE o.status = 'COMPLETED') AS ok      -- ★ 期望 true
```

★ 守恒式 ① 是**三重派生真的生效**的证据：若 `product_id` 由客户端传，这条立刻会报漂移。
★★ 这也是「对账」这个动作在项目里第一次**跨出库存域** ——
**「有账可对」不是库存表的特权，而是任何「派生数据」都该有的性质。**

### 5.3 对账口径不用改（Day 15 的升级继续有效）

`Day-15` 把 `sold` 的口径升级成了 `Σ(状态 ∈ {PAID, SHIPPED, COMPLETED})`。
本日评价**不改订单状态、不碰库存** → **口径原样可用，零改动**。

★ 但要**跑一遍验证**（验收脚本第 11 组）：确认今天没有把口径搞坏 ——
「今天不用改」这件事本身，也值得用一条全绿的断言来证明。

---

## 六、验收计划

脚本：`backend/loadtest/day16-review-e2e.py`（自清理、可重跑、相对量断言）
报告：`backend/loadtest/day16-review-e2e-report.txt`

| # | 分组 | 断言要点 |
|---|---|---|
| 0 | 基线 | 7 SKU 指纹快照；`orders` / `payments` / `order_items` / `reviews` / `inventory_logs` 行数 |
| 1 | 准备 | demo / intruder / admin 三个 token |
| 2 | 造靶子 | 下单 → 支付 → 发货(admin) → 确认(demo)，每步验状态 |
| 3 | **写评价** | → 200；★ DB 侧 `user_id` / `order_id` / `product_id` **与 `order_items` 逐字段一致** |
| 4 | 幂等 | 再评一次 → `code=400`；★ DB 侧**仍 1 行** |
| 5 | ★★ **并发** | 8 线程同 `orderItemId` → **恰好 1 个 200、7 个 400**；DB 侧**恰好 1 行** |
| 6 | 越权 | intruder 用 demo 的 `orderItemId` → `code=404`；不存在的 `orderItemId` → `code=404`（**两者响应逐字节相同**） |
| 7 | 资格 | `PENDING_PAYMENT` / `PAID` / `SHIPPED` 三种订单评价 → `code=400` |
| 8 | 参数 | `rating` = 0 / 6 / null → `code=400`；`content` 501 字 → `code=400` |
| 9 | ★ 伪造 | 请求体塞 `userId` / `orderId` / `productId` → **被静默忽略**，入库值仍是派生值 |
| 10 | 读 | 商品列表（公开，**不带 token**）能查到刚写的；`avgRating` / `reviewCount` 正确；「我的评价」能查到；分页 `size=0` / `size=-1` / `page=0` 三个边界不炸 |
| 11 | ★★ 对账 | 评价域守恒式 ①②③ 全绿；库存口径 `sold` / `locked` 沿用 Day 15 版本 → **0 漂移** |
| 12 | 清理 | 删靶子订单 + 明细 + 支付 + 评价；★ 7 SKU 逐字段回基线；行数回基线；无孤儿行 |

★ 第 5 组（并发）与第 9 组（伪造）是本日**新增的两类断言**，前几天的脚本里没有对应物。
★ 脚本必须**可重复执行**：商品评价列表是公开的，但「我的评价」会累积 ——
所以清理**必须**按 `order_item_id` 精确删靶子的那条评价，不能整表清空。

---

## 七、提交清单（按主题分批）

| # | 提交 | 内容 |
|---|---|---|
| 1 | `feat(db)` | 2 条 DDL：`04-review-constraints.sql`（幂等补丁）+ 同步 `01-schema.sql` 的 `reviews` 段 |
| 2 | `feat(review)` | 新模块 `mall-review`（pom ×4 处改动 + 模块代码） |
| 3 | `feat(order)` | 跨模块契约：`OrderItemBuyContext` + `getBuyContext` + `OrderItemMapper.xml`（新建） |
| 4 | `test(review)` | `day16-review-e2e.py` + 报告 + `day16-probe.sql` |
| 5 | `docs` | Day 16 实测小节 + 状态行 |

---

## 八、写代码时的对照清单（★ 动手时对着这张表勾）

> ★★ **2026-09-20 现状**：下表里 §8.1 的 1–6 与 §8.2 的 17–18（数据类）**已由 AI 交成骨架**，
> 其余每一格的**方法体与 SQL 都是 `TODO`**，等你填。
> 骨架的每个 `TODO` 旁边都写了「步骤拆解 + 需要哪个 import」，直接照着写即可。
> 填完的顺序见 **§8.5 自检顺序**；每填完一块可先跑 `day16-skeleton-smoke.py` 看有没有把线接错。

### 8.1 逐文件改动 · 第 1 步（写评价）

| # | 文件 | 锚点 | 必须满足 |
|---|---|---|---|
| 1 | `backend/sql/04-review-constraints.sql` | 新建 | 幂等（`DO $$ ... IF ... $$`）：先 `SET NOT NULL`，再加 `UNIQUE (order_item_id)` |
| 2 | `backend/sql/01-schema.sql` | `reviews` 建表段（第 233–248 行） | `order_item_id BIGINT NOT NULL` + 加 `CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id)`，并**注明与 04 补丁的关系** |
| 3 | `backend/mallx/pom.xml` | `<modules>`（第 22–33 行） | 加 `<module>mall-review</module>` |
| 4 | `backend/mallx/pom.xml` | `<dependencyManagement>`（第 47–127 行） | 加 `mall-review` 坐标 |
| 5 | `backend/mallx/mall-server/pom.xml` | `<dependencies>`（第 17–54 行） | 加 `mall-review` —— ★ 漏了就是「编译通过但 404」 |
| 6 | `mall-review/pom.xml` | 新建 | 依赖 `mall-common` + `mall-order`（不写 version） |
| 7 | `mall-review/.../mapper/ReviewMapper.java` | 新建 | `int insertReview(Review review)`（或逐参数）★ 方法名与 XML `id` **逐字符一致** |
| 8 | `mall-review/.../mapper/ReviewMapper.xml` | 新建 ★ 放 `src/main/resources/mapper/` | `<insert id="insertReview">` 带 `ON CONFLICT (order_item_id) DO NOTHING`；`created_at` / `updated_at` **手写** |
| 9 | `mall-order/.../api/OrderItemBuyContext.java` | 新建 api 包 | 8 个字段（见 §3.3） |
| 10 | `mall-order/.../mapper/OrderItemMapper.java` | 现有接口 | 加 `OrderItemBuyContext selectBuyContext(@Param("userId") Long userId, @Param("orderItemId") Long orderItemId);` |
| 11 | `mall-order/.../resources/mapper/OrderItemMapper.xml` | ★ **新建文件**（该目录下目前只有 `OrderMapper.xml`） | 别名一律**下划线**；`WHERE` 里带 `o.user_id` |
| 12 | `mall-order/.../service/OrderService.java` | 现有接口 | 加 `OrderItemBuyContext getBuyContext(Long userId, Long orderItemId);` |
| 13 | `mall-order/.../service/impl/OrderServiceImpl.java` | 现有实现 | 实现：直接转调 `orderItemMapper.selectBuyContext`；`null` 由上层处理 |
| 14 | `mall-review/.../service/impl/ReviewServiceImpl.java` | 新建 | 三步顺序：`getBuyContext` → null 抛 404 → 状态非 `COMPLETED` 抛 400 → `insertReview` 0 行抛 400。★ **不加 `@Transactional`** |
| 15 | `mall-review/.../controller/ReviewController.java` | 新建 | `@RequestMapping("/api")` + 三个方法级完整路径；★ **不挂 `@PreAuthorize`** |

### 8.2 逐文件改动 · 第 2 步（读评价）

| # | 文件 | 锚点 | 必须满足 |
|---|---|---|---|
| 16 | `mall-review/.../mapper/ReviewMapper.xml` | 接着 `insertReview` 之后 | ① 商品维度分页（`WHERE product_id = ? AND status = 1`，`LEFT JOIN users`，**首参 `IPage`**）② 我的评价分页（`WHERE user_id = ?`）③ 聚合 `AVG` / `COUNT` |
| 17 | `mall-review/.../vo/ReviewVO.java` | 新建 | `id` / `orderItemId` / `productId` / `productName` / `skuName` / `image` / `rating` / `content` / `userNickname` / `createdAt`。★ **不要有 `userId`** |
| 18 | `mall-review/.../vo/ReviewPageVO.java` | 新建 | `avgRating` / `reviewCount` + 分页四件套（理由见 §4.2） |
| 19 | `mall-review/.../service/ReviewService.java` + `Impl` | 新建 | 三个方法：`create` / `pageByProduct` / `pageMine`；★ 分页夹紧写在 `new Page<>()` **之前** |
| 20 | `mall-review/.../controller/ReviewController.java` | 补两个 `@GetMapping` | 商品列表**要允许匿名**（方法参数里**不要** `Authentication`）；我的评价**要** `Authentication` |

### 8.3 陷阱清单（★ 写一行勾一行）

| # | 陷阱 | 后果 | 依据 |
|---|---|---|---|
| 1 | ★★ 只加 `UNIQUE` 不加 `NOT NULL` | NULL 行**绕过防线**，「一明细多评」照样发生 | §0.3 + 探针 5 **实测** |
| 2 | 用「先 `SELECT` 再 `INSERT`」代替 `ON CONFLICT` | 并发下双写（TOCTOU） | §3.2 |
| 3 | 硬插 + `catch DuplicateKeyException` 但没加专用 handler | 落进 `handleException(Exception)` → **200 + code=500** | §3.2（Day 07 的 `AccessDeniedException` 同款坑） |
| 4 | ★★ 把 `product_id` / `order_id` / `user_id` 放进请求 DTO | 拿一张自己的合法订单可以给**任意商品**刷好评 | §3.1 |
| 5 | SQL 别名写成 `AS orderItemId` | PG 折成小写 `orderitemid` → **映射不上、字段为 null**（不报错！） | §3.3 —— 别名一律写**下划线** |
| 6 | 评价列表挂 `/api/reviews?productId=` | 不在白名单 → 游客 403/401，看不了评价 | §4.1 |
| 7 | 给评价端点挂 `@PreAuthorize` | C 端 token 权限集为空 → **必 403** | Day 15 §0.4 实测 |
| 8 | XML INSERT 里漏写 `created_at` / `updated_at` | 两列永远是旧值（自定义 XML **不走** `MetaObjectHandler`） | Day 13/14/15 都踩过 |
| 9 | XML 注释里出现连续两个减号 | ★ **编译通过、启动才炸**（`SAXParseException`） | Day 13 踩过 |
| 10 | 新建模块只改了 `mall-review/pom.xml` | ★★ 编译过、启动成功、**接口 404** | §2.4 第 3 处 |
| 11 | `pageByProduct` 方法里加 `Authentication` 参数 | 匿名访问直接 500/401（游客本该能看） | §4.1 |
| 12 | 分页 `size` 不夹紧 | `size<0` → **查全表**；`size=0` → 空列表但 total 正常 | Day 12 实测 |
| 13 | 拿序列（`reviews_id_seq`）当基线断言 | 序列不回滚 → 必然假失败 | Day 15 §8.3 第 10 条 |
| 14 | 清理时整表清空 `reviews` | 破坏可重复执行（别人的历史评价也没了） | §六 的 ★ |

### 8.4 ★ 「不要动」清单（省得白改）

| 文件 | 为什么不用动 |
|---|---|
| `GlobalExceptionHandler.java` | 走 `ON CONFLICT` 就不会有 `DuplicateKeyException`；**不需要**新增 handler |
| `SecurityConfig.java` | `/api/products/**` 的 GET 白名单已经把评价列表覆盖了（§4.1） |
| `JwtAuthenticationFilter` / `JwtUtil` | 取 userId 的链路与 C 端其它模块完全一致 |
| `orders` / `order_items` / `inventories` 表 | **本日零改动** —— 评价纯新增，订单与库存全是只读 |
| `OrderStatus.java` | 评价**不改订单状态**（订单状态机已是终态 `COMPLETED`，评价不参与状态机） |
| `backend/sql/03-data.sql` | 本日**不 seed 权限**（§3.4） |
| `02-index.sql` | `UNIQUE (order_item_id)` 自带索引；`idx_reviews_product_id` / `idx_reviews_user_id` 已够用 |
| 对账口径（7 个 loadtest 文件里的 `sold` 守恒式） | Day 15 的版本继续有效，本日不碰（§5.3） |
| `mall-product` 模块 | ★ 评价模块**不依赖**它（§2.3） |

### 8.5 自检顺序（写完按这个顺序验）

1. **执行 DDL**：`04-review-constraints.sql`（幂等，可重复跑）；立即复核
   `\d reviews` 的 `order_item_id` 变成 `not null` + 出现 `uk_reviews_order_item`
2. **编译**：`mvn -o install -pl mall-review -am -DskipTests`
   （★ 必须 `install` 到本地仓库 —— `spring-boot:run` 读的是仓库里的 jar，不是 `target/classes`）
3. **重启**：杀 `MallXApplication`（★ 只杀命令含 `com.mallx.MallXApplication` / `plexus-classworlds` 的，
   **绝不能无脑杀所有 `java.exe`**）→ 确认 8080 空 → `mvn -o spring-boot:run -pl mall-server "-Dspring-boot.run.arguments=--server.port=8080"`
4. **冒烟**：`POST /api/reviews` 打一发；`GET /api/products/{id}/reviews` **不带 token** 打一发
5. **正式验收**：`python backend/loadtest/day16-review-e2e.py` → 12 个分组，报告落盘
6. **对账复核**：评价域守恒式 ①②③ 全绿 + 库存口径 0 漂移
7. **确认基线复位**：7 SKU 逐字段回 `Day-15 §8.5` 的基线，行数与开跑时一致

---

## 附：本日不做的候选（留档，避免走偏）

| 候选 | 为什么不做 |
|---|---|
| 评价晒图（`images` JSONB） | 需要一个**图片上传接口**（对象存储 / 静态目录），是独立的一步；`images` 列留着不用，V1.0 不碰 |
| 管理端审核评价（`status = 0`） | V1.0 没有管理端页面，审核流**没有入口**；而且需要 seed 权限（本日刻意不 seed） |
| 商家回复评价（`reply_content`） | 表里**没有这一列** → 一加就是 DDL + 一套新接口 |
| 追加评价 / 修改评价 | 「一次购买一次评价」是本日的明确规则；可改评价需要引入评价版本/编辑历史 |
| 评分聚合冗余列（`products.rating`） | 冗余靠维护，漏算即长期漂移（§4.2 已论证用实时聚合代替） |
| 匿名评价（`is_anonymous`） | 表里没有这一列；且匿名与「不暴露 `user_id`」是两件事，现在的设计已经**不泄露 id** |
| `ORDER BY` 之外的高级排序（按评分/有用数） | 没有「有用」计数列；V1.0 按 `created_at DESC` 固定即可 |
