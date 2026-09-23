# Day 20：优惠券（阶段一）—— 建模块 + 发券 + 限量领取

> 方向：**A 优惠券 · 阶段一**（H 不碰下单链路）。陪练模式：本文档 + 骨架 + 脚本由我出，**实现你亲手写**。
> 阶段二（下单抵扣 + 核销）留 Day 21 —— 那个才会动 `OrderServiceImpl`、撞 M1 回归。

---

## 一、为什么是这一块

| 事实 | 证据 |
|---|---|
| `mall-marketing` 是 11 个模块里**唯一零 Java 文件**的 | `Glob mall-marketing/**/*.java` → 0 命中；只有 `pom.xml` 和一个空 jar |
| `coupons` / `user_coupons` **从未被任何代码引用** | 全仓 `Grep -i coupon` → 只命中 `01-schema.sql` / `02-index.sql` |
| **零种子数据** | `03-data.sql` 里没有 coupons 的 INSERT |
| V1.0 业务闭环的最后一块 | 已有：商品 → 购物车 → 下单 → 支付 → 库存 → 评价。缺：**券** |

**为什么先做「阶段一」而不是一次做完**：阶段二要在 `createFromCart` 里算券额，
而 M1 回归（198 条）**跑的就是真实下单链路**（Day 14/15/16 三个 E2E 脚本）。
把「模块立不起来」和「M1 挂了」两种不确定性分开，是这个 Day 的全部意义。

---

## 二、现状核查（不凭记忆，逐条查过）

### 2.1 建表 SQL（`01-schema.sql:282`）

```sql
coupons (
  id, name, type, discount_amount, discount_rate, min_amount,
  total_count INT NOT NULL DEFAULT 0, received_count INT NOT NULL DEFAULT 0,
  start_time TIMESTAMP NOT NULL, end_time TIMESTAMP NOT NULL,
  status SMALLINT NOT NULL DEFAULT 1, created_at, updated_at )

user_coupons (
  id, user_id BIGINT NOT NULL, coupon_id BIGINT NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'UNUSED',
  received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  used_at TIMESTAMP, order_id BIGINT,
  FK → users(id), FK → coupons(id) )
```

### 2.2 三个必须知道的现状（否则会写出错的断言）

| # | 现状 | 后果 |
|---|---|---|
| ① | `user_coupons` **没有 `UNIQUE(user_id, coupon_id)`** | 「一人一券」**没有牙齿** → 必须补 DDL（见 §五.3） |
| ② | 两列**都已经是 `NOT NULL`** | ★ 与 Day 16 的 `reviews.order_item_id` **不同**：那次必须先 `SET NOT NULL` 再加 UNIQUE；**这次不用**。铁律要先体检 |
| ③ | `type` / `status` **都没有 CHECK 约束** | 取值范围**只能靠应用层守**（`@Pattern` / 常量类），写错值 DB 一声不吭 |

### 2.3 已有索引（`02-index.sql:69`）

```
idx_coupons_status / idx_user_coupons_user_id / idx_user_coupons_coupon_id
```

★ 三个都是**普通索引**。补 UNIQUE 会**另建**一个唯一索引，不动这三个。

### 2.4 模块脚手架**已经配好**（我一开始判断错了，实测纠正）

| 位置 | 状态 |
|---|---|
| 父 `pom.xml` `<modules>` | ✅ 已有 `mall-marketing` |
| 父 `pom.xml` `<dependencyManagement>` | ✅ 已有 |
| **`mall-server/pom.xml` `<dependencies>`** | ✅ 已有 |

⇒ **本日一个字都不用改 pom**。★ 顺带记一条判据：漏改第三处的症状是
**编译启动全绿但接口 404**；本日会有一发匿名请求专门验它。

---

## 三、接口设计

### 3.1 C 端（`CouponController`，类级 `@RequestMapping("/api")`）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| `GET` | `/api/coupons` | **公开** | 可领券列表（分页） |
| `POST` | `/api/coupons/{couponId}/receive` | 需登录 | ★ **本日核心**：领券 |
| `GET` | `/api/coupons/my` | 需登录 | 我的券（分页，含是否过期） |

### ★★ 3.2 白名单：这次必须动 `SecurityConfig`（1 行），理由是能实测

`GET /api/coupons` 要公开，但 **`GET /api/coupons/my` 绝不能公开**。

```java
.requestMatchers(HttpMethod.GET, "/api/coupons").permitAll()   // ← 精确路径，不是 /** ！
```

| 写法 | `/api/coupons` | `/api/coupons/my` |
|---|---|---|
| `/api/coupons` （**要用这个**） | 放行 | **仍需登录** ✅ |
| `/api/coupons/**` | 放行 | **静默公开** ❌ |

★ 这正是 Day 16 `ReviewController` 类头写过的坑（当时为了绕开，只能把类级映射退到 `/api`）。
**今天用「精确路径」正面解决它** —— 验收里会有一组断言专门证明「没误伤 my」：
匿名打 `/api/coupons` → 200，匿名打 `/api/coupons/my` → **401**。这一对就是白名单粒度的证据。

⚠️ 且 `GET /api/coupons` 是**公开接口**，**不能依赖登录态**：匿名时拿不到 userId，
所以列表里**不含「我是否已领」** —— 那个状态由 `/api/coupons/my` 承担。这不是妥协，是分工。

### 3.3 管理端（`AdminCouponController`，`/api/admin/coupons`）

| # | 方法 | 路径 | 权限码 |
|---|---|---|---|
| 1 | `GET` | `/api/admin/coupons` | `coupon:list` |
| 2 | `POST` | `/api/admin/coupons` | `coupon:create` |
| 3 | `DELETE` | `/api/admin/coupons/{id}` | `coupon:delete` |

★★ **刻意不做 `PUT`（改券）** —— 这不是偷懒，是业务判断：**券一旦发出去，改面额会与
已领取用户的预期冲突**（他领的是「满 100 减 20」，你把面额改成 10，他手里的券算什么？）。
真实系统的做法是「作废旧券 + 新建一张」，而不是原地改。
⇒ V1.0 就按「建 / 停（把 `status` 置 0）/ 删」三件事走。
（若你想加 `PUT`，告诉我，`coupon:update` 一并补上。）

### 3.4 错误消息口径（★ 这里是本日第二个设计点）

「领不到券」有 4 种原因：**不存在 / 已下架 / 不在有效期 / 已抢光**。

| 方案 | 问题 |
|---|---|
| 先 `SELECT` 查券，逐个判，再 CAS | **先查后改 = TOCTOU**，并发下会超发 |
| CAS 失败后一律返回「领不到」 | 用户不知道是抢光了还是没开始 —— 体验差 |

**采用：快速路径 CAS + 慢路径诊断**。

```text
① CAS 更新（数量+1 且满足所有可领条件）→ 影响行数 ≠ 0 ⇒ 成功，直接往下走
② 0 行 ⇒ 此时【再查一次券详情】，只为把错误消息说清楚
   （这次查询不参与正确性判断 —— CAS 已经失败了，查得准不准都不影响并发安全）
③ 查不到 ⇒ "优惠券不存在"；查到 ⇒ 按 status / 时间窗 / 余量给出具体原因
```

★ 关键认知：**只有「① 影响行数」是并发安全的判据**，②只是文案。二者不可颠倒。

---

## 四、两个核心难点

### 4.1 限量并发领取 = 条件 UPDATE（与 Day 17 扣库存**同构**）

```sql
UPDATE coupons
   SET received_count = received_count + 1
 WHERE id = #{couponId}
   AND status = 1
   AND start_time <= CURRENT_TIMESTAMP
   AND end_time   >= CURRENT_TIMESTAMP
   AND received_count < total_count
```

| 对应关系 | Day 17 扣库存 | Day 20 领券 |
|---|---|---|
| 要动的格子 | `available_stock` | `received_count` |
| 守卫 | `available_stock >= #{q}` | `received_count < total_count` |
| 0 行的含义 | 库存不足 | 抢光 / 未开始 / 已过期 / 已下架 |
| 判据 | **影响行数** | **影响行数** |

★ **减法由数据库做**（`SET x = x - q`）；这里加号同理 —— 绝不「先 SELECT 出当前值，再算好了 UPDATE 回去」。

### ★★ 4.2 一人一券 = 唯一约束 + `ON CONFLICT`（与 Day 16 评价**同构**）

领取要写两张表，**必须同一事务**：

```text
coupons.received_count + 1     （占名额）
user_coupons 插一行             （发到手）
```

**顺序选「先 CAS 后 INSERT」**，理由：

| 顺序 | 重复领时会发生什么 |
|---|---|
| **先 CAS 后 INSERT**（选它） | 占了名额 → INSERT 撞唯一约束 → 抛异常 → **整个事务回滚，名额退回** ✅ |
| 先 INSERT 后 CAS | 插进去了 → CAS 发现抢光 → 抛异常 → 回滚。也对，但多写一次行 |

⇒ 判定「是否重复领」**不靠 SELECT 查**，靠 `INSERT ... ON CONFLICT (user_id, coupon_id) DO NOTHING`
的**影响行数**（1 = 领到，0 = 已领过）—— 与 Day 16 评价的写法逐字同构。

⚠️ **`ON CONFLICT (user_id, coupon_id)` 硬依赖那个唯一约束** ——
DDL 补丁没跑，这条 SQL **直接报 `there is no unique or exclusion constraint matching...`**，
不是静默降级（Day 16 记录过）。

### 4.3 过期怎么判：**惰性计算，不改状态**

`user_coupons.status` 有 `UNUSED / USED / EXPIRED` 三个取值，本日**只写 `UNUSED`**。

「已过期」由**查询时计算**得出（`c.end_time < CURRENT_TIMESTAMP`），
**不写回 `EXPIRED`**：

| 方案 | 代价 |
|---|---|
| 惰性（本日选它） | 每次查多一个比较；**零调度、零副作用、可无限重跑** |
| 定时任务扫全表置 `EXPIRED` | 要引入 `@Scheduled`（项目里已有 `OrderTimeoutTask` 的范式）；**多一个会改库的写点**，验收时得为它单独维权 |

★ 阶段二「核销」才是真正的状态机（`UNUSED → USED`），那时再评估要不要引入 `EXPIRED` 落库。

---

## 五、SQL / DDL 要点

### 5.1 可领券列表（`selectAvailableCoupons`）

```sql
SELECT id, name, type, discount_amount, discount_rate, min_amount,
       total_count, received_count, start_time, end_time
  FROM coupons
 WHERE status = 1
   AND start_time <= CURRENT_TIMESTAMP
   AND end_time   >= CURRENT_TIMESTAMP
   AND received_count < total_count      -- ★ 抢光的就不展示了
 ORDER BY id DESC
```

★ 三个条件与 §4.1 的 CAS 守卫**逐字对应** —— 列表里**展示得出来的，就是领得到的**。
这是「口径一致」的一条硬规矩：两边写岔了，用户会看到「列表里有、点进去说抢光了」。

⚠️ 分页由插件改写（XML 里**不写 LIMIT**），首参必须传 `IPage`。

### 5.2 领券的 CAS（`increaseReceivedCount`）

见 §4.1。`resultType` 用 `int`（受影响行数），**不是** VO。

### 5.3 DDL 补丁（`backend/sql/09-user-coupons-unique.sql`）

```sql
ALTER TABLE user_coupons
  ADD CONSTRAINT uk_user_coupons_user_coupon UNIQUE (user_id, coupon_id);
```

★ 与前例的差别（**必须先体检再照抄**）：

| | Day 16 `reviews.order_item_id` | Day 20 `user_coupons` |
|---|---|---|
| 起始状态 | **可空** → 必须**先 `SET NOT NULL`** | 已经是 `NOT NULL` ✅ |
| 若不先 SET NOT NULL | UNIQUE **被 NULL 行整条绕过**（错得安静） | 不适用 |

⇒ 顺序不能死记。**每次都要先 `\d 表名` 看清列的可空性**。
幂等写法：`DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='...') ... $$;`

⚠️ 加约束前先查存量重复行（本日是空表，但仍写进去 —— 换台机器就是有数据的）。

★★ **末节还写了一段「功能验证」**（插两次、期望第二次撞唯一约束，包在 `BEGIN/ROLLBACK` 里
做零痕迹取证）。★ 写它的过程踩了个坑，已记入 §九.3：
**第一次没先造父数据，结果撞的是外键而不是唯一约束** —— 那段验证「看似报错、其实什么都没验」。
加约束这类 DDL 补丁，**只验「约束存在」是不够的，必须让它真的拦下一次插入**。

### 5.4 权限补丁（`backend/sql/08-marketing-permissions.sql`）

权限码 **id 18..20**（现 max = 17）：

```sql
(18, '优惠券列表', 'coupon:list',   'API', '/api/admin/coupons',     'GET'),
(19, '新建优惠券', 'coupon:create', 'API', '/api/admin/coupons',     'POST'),
(20, '删除优惠券', 'coupon:delete', 'API', '/api/admin/coupons/*',   'DELETE')
```

**授权只给超管（role 1）**，`op_product`（role 2）/ `op_order`（role 3）**刻意不给**：

| 账号 | 角色 | 期望 |
|---|---|---|
| `admin` | SUPER_ADMIN | 200 ✅ |
| `op_product` | PRODUCT_ADMIN | **403**（★ 反向对照） |
| `op_order` | ORDER_ADMIN | **403**（★ 反向对照） |

★ 理由要说得出来：**营销在 V1.0 是独立岗位**，种子里的三个角色是「商品 / 订单 / 超管」，
没有 MARKETING_ADMIN。给商品管理员发券是**越权**，不是省事。
★ 「权限矩阵的区分度全靠谁没有」—— 这条 Day 17 已定型，今天第二次应用。

⚠️ 别忘了：**`permissions` 用显式 id 插入后必须校准序列**（第四节），
且 `role_permissions` 的补发语句**只增不改**（`NOT EXISTS` 双保险）。

### 5.5 实体的两个 `@TableName`

| 类 | 反推表名 | 真实表名 |
|---|---|---|
| `Coupon` | `coupon` | **`coupons`** |
| `UserCoupon` | `user_coupon` | **`user_coupons`** |

MP 的驼峰转换**不做复数→单数**，也**不加 s** → 两个类都必须显式 `@TableName`。
漏了 = 所有 SQL 报「表不存在」。

⚠️ `coupons` / `user_coupons` **都没有 `is_deleted` 列** → **禁止加 `@TableLogic`**。

---

## 六、骨架清单（TODO 分布）

| # | 文件 | 动作 | TODO |
|---|---|---|---|
| 1 | `entity/Coupon.java` | 新建 | 0 |
| 2 | `entity/UserCoupon.java` | 新建 | 0 |
| 3 | `dto/CouponCreateDTO.java` | 新建（含 `@NotNull` / `@Min` / `@DecimalMin`） | 0 |
| 4 | `vo/CouponVO.java` | 新建 | 0 |
| 5 | `vo/UserCouponVO.java` | 新建（含 `expired` 布尔） | 0 |
| 6 | `mapper/CouponMapper.java` | 新建（2 个方法声明） | 0 |
| 7 | `mapper/UserCouponMapper.java` | 新建（1 个方法声明） | 0 |
| 8 | `resources/mapper/CouponMapper.xml` | 新建 | **2** |
| 9 | `resources/mapper/UserCouponMapper.xml` | 新建 | **2** |
| 10 | `service/CouponService.java` | 新建（6 个方法声明） | 0 |
| 11 | `service/impl/CouponServiceImpl.java` | 新建 | **5** |
| 12 | `controller/CouponController.java` | 新建（3 端点） | **3** |
| 13 | `controller/AdminCouponController.java` | 新建（3 端点） | **3** |
| — | `SecurityConfig.java` | **改 1 行**（不用你写，我加） | 0 |

合计 **15 处 TODO**。★ 与本项目此前最大的一次（Day 18 的 14 处）相当，
但**结构更整齐**：4 条 SQL + 5 个 Service 方法 + 6 个一行转发。

### 手写顺序（每步都能单独验）

| 步 | 位置 | 量 | 为什么排这儿 |
|---|---|---|---|
| **1** | `CouponMapper.xml` → `increaseReceivedCount` | 1 条 SQL | 核心中的核心，最短、最能单独验 |
| **2** | `UserCouponMapper.xml` → `insertIgnore` | 1 条 SQL | 与 Day 16 逐字同构，热身 |
| **3** | `CouponServiceImpl.receive` | 10 行 | 把 1+2 串成「占名额 → 发到手 → 诊断」 |
| **4** | `CouponController.receive` | 1 行 | 让核心**能从 HTTP 打到** |
| **5** | `CouponMapper.xml` → `selectAvailableCoupons` | 1 条 | 列表，与 ① 的守卫逐字对应 |
| **6** | `UserCouponMapper.xml` → `selectMyCoupons` | 1 条 | 含 `expired` 计算 |
| **7** | 两个 Controller 其余 5 个转发 | 各 1 行 | 收尾 |

★ 第 4 步做完就能起应用打第一发真实领券 —— **越早打通 HTTP，越早发现问题**。

---

## 七、验收清单（逐条落成断言）

| 链路 | 内容 | 关键断言 |
|---|---|---|
| **A 路由与白名单** | ① 匿名 `GET /api/coupons` → **200**（精确白名单生效）<br>② 匿名 `GET /api/coupons/my` → **401**（★ **没被误伤**，这是白名单粒度的证据）<br>③ 匿名 `GET /api/admin/coupons` → **401** | 三条层级分明 |
| **B 骨架期长相** | 带 token 打三个端点 → `HTTP 200 + code=500`（走到 `UnsupportedOperationException`） | 与 `404`（漏改 pom）区分开 |
| **C 发券（管理端）** | `POST /api/admin/coupons` 建券 → DB 核 13 个字段；**重复建**不报错（券名不唯一） | 断言回到 `code=200` + psql 对账 |
| **D 领券（核心）** | ① 领到 → `received_count` **+1**、`user_coupons` **+1** 行且 `status='UNUSED'`<br>② **再领一次** → `code=400`，**且 count 不变、无新行**（★ 事务回滚的证据） | ★ 每个断言都配 psql 对账 |
| **E 限量** | 建一张 `total_count=2` 的券，用 **3 个用户**并发/顺序领 → 恰好 **2 个成功**、`received_count` **恰好 = 2**（不超发） | 满额断言写死常量 `2` |
| **F 时间窗与状态** | ① 未开始（`start_time` 在未来）→ 领不到，且**不出现在列表**<br>② 已下架（`status=0`）→ 同上<br>③ 已过期（`end_time` 在过去）→ 同上 | 三条都走 **CAS 的 0 行**这条同一个出口 |
| **G 我的券 / 过期** | ① `GET /api/coupons/my` 只含自己的券（**IDOR**：换个 token 看不到）<br>② 过期券 `expired=true`，且 **DB 里 `status` 仍是 `'UNUSED'`**（惰性计算的反证） | ★ IDOR 光看状态码不够，要核 DB |
| **H 权限矩阵** | `admin` → 200；`op_product` / `op_order` → **403**（`coupon:list` / `coupon:create` / `coupon:delete` 各一条） | ★ **断言必须给合法载荷**（`@Valid` 先于 `@PreAuthorize`） |
| **I 健壮性** | ① 券类型 `FIXED` 缺 `discount_amount` → `code=400`<br>② `DISCOUNT` 缺 `discount_rate` → `code=400`<br>③ `total_count=0` → 建得出来但**谁都领不到**<br>④ `size=999` → 夹到 100 | 逐条断言 |
| **J 零写入** | 全表计数与内容在验收前后一致（跑完自己清理造的券） | `BASELINE RESTORED` |
| **K M1 回归** | `day17-m1-regression.py` | **198/198** + `BASELINE RESTORED YES` |

### ★ 验收脚本的清理必须**按引用顺序**删

本日新建的券会被 `user_coupons` 引用（FK `NO ACTION`）→ 直接删券**会报外键错**：

```text
先 DELETE FROM user_coupons WHERE coupon_id > 水位
再 DELETE FROM coupons       WHERE id        > 水位
```

★ 这与「谁引用我决定我能否物理删」是同一条规矩（Day 03 记录，Day 18 又踩过一次）。
★ 清理用**高水位线**（跑前记 `MAX(id)`），且**券和领券记录各记一条**。

---

## 八、风险与注意

1. **`coupon:list` 等三条权限必须补发 `role_permissions`** —— 否则 `@PreAuthorize` **永远 403**，
   且症状长得像「注解拼错了」。这是本项目第 4 次重复同一件事（05 / 07 / 08 …），
   §5.4 的自检 SQL 专门查这个。
2. **DDL 补丁必须先跑再验收** —— 漏跑的直接症状是领券接口报
   `there is no unique or exclusion constraint matching the ON CONFLICT specification`。
3. **XML 注释里绝不能出现连续两个减号**（`--`）→ `SAXParseException`，**启动才炸**。
   本项目已有 3 次记录，且 AI 自己就踩过。
4. `@Valid` 的 message 里**别写敏感业务规则**（它会回显给调用方）。
5. **管理端 Controller 绝不挂 `/api/coupons/**`** —— 它是白名单里的 GET，会**静默公开**。
   一律走 `/api/admin/coupons`。
6. 本日**不改** `01-schema.sql` / `02-index.sql` / `03-data.sql`：
   所有 DDL 走 `09-*.sql` 补丁（幂等），权限走 `08-*.sql`（幂等）—— 与 Day 16/17/18 同一套路。
7. 起应用验收：端口**显式** `--server.port=8080`，「起应用 + 跑完验收」**必须在同一轮内**。
8. 骨架期门禁脚本**必须带前提护栏**（扫不到 `UnsupportedOperationException` 就拒绝执行）——
   Day 18 的污染事故就是这么来的。

---

## 九、骨架期自查结果（实测回填，2026-09-23）

### 9.1 两道自检门

| 项 | 结果 |
|---|---|
| `day20-xml-check.py`（本日新建） | **5 / 5 XML 良构**、4 个新 statement 全在、**Java↔XML 双向一致** |
| 其附带产物：Java 骨架占位计数 | **11 处**（预期基线 11）= AdminCouponController 3 + CouponController 3 + CouponServiceImpl 5 |
| XML SQL 停在 TODO | **4 条**（本日主角两条 SQL × 2 个 XML） |
| 构建 | `BUILD SUCCESS`（`mall-marketing` **首次带代码**编译，此前只有一个空 jar） |
| `day20-skeleton-smoke.py`（本日新建） | **VERDICT: OK**，25 项断言全绿 |
| 数据零写入 | `coupons = 0` / `user_coupons = 0`（门禁全程没写一个字节） |

★ 占位总数 **11 + 4 = 15**，与 §六 的清单一致 —— 这个数字是「骨架填完了吗」的机器判据，
下次由脚本自动核对，不靠人眼数。

### 9.2 补丁应用结果

`08-marketing-permissions.sql`（`ON_ERROR_STOP=1`，rc=0）：

```text
INSERT 0 3                        ← 3 条权限
setval → 20                       ← 序列校准到 MAX(id)
coupon_perms_total | super | product_admin | order_admin
                 3 |     3 |             0 |           0
```

★ 顺带看到全量授权现状：**SUPER_ADMIN = 20 条**（1..20 全量）、
PRODUCT_ADMIN = 12 条、ORDER_ADMIN = 4 条。三个角色的权限数**互不相同**，
这正是「权限矩阵有区分度」的量化形式。

`09-user-coupons-unique.sql`（`ON_ERROR_STOP=0`，因为末节有一段故意报错的功能验证）：

```text
user_id / coupon_id  is_nullable = NO / NO     ← 前提体检通过（不必 SET NOT NULL）
存量重复行           = 0 行                     ← 前提体检通过（可安全加约束）
uk_user_coupons_user_coupon | u | UNIQUE (user_id, coupon_id)     ← 约束已建
索引 4 个（含新加的 uk_...）
```

### ★★ 9.3 一次「验证脚本自己无效」的现场

`09` 的第三节原本写的是：直接插两次 `user_coupons(1, 1)`，期望第二次撞**唯一约束**。

**实测撞的是外键**：

```text
ERROR: insert or update on table "user_coupons" violates
       foreign key constraint "fk_user_coupon_coupon"
DETAIL: Key (coupon_id)=(1) is not present in table "coupons".
```

原因：`coupons` 表是**空的**，`coupon_id = 1` 根本不存在 ⇒ 外键先于唯一约束暴露
⇒ 这段「功能验证」**什么都没验到**，而且**它看起来是绿的**（确实报错了嘛）——
比不写还坏。

**修法**：先造一张临时券（把它摆到「所有外键都满足」的状态），再插两次领取记录：

```text
BEGIN
INSERT 0 1     ← 造临时券（id=999999）
INSERT 0 1     ← 领一次，成功
               ← 再领一次 → duplicate key ... "uk_user_coupons_user_coupon" ★ 这才验到了
ROLLBACK
```

★ 与 Day 19 的教训同源：**探针的「前提」必须先建好**，否则测的不是你以为的东西。
Day 19 的版本是「断言照着想象的列写」，今天是「探针少建了一行父数据」——
都属于「脚本对了、前提错了」。

### 9.4 门禁的成绩单（本日最值钱的一组）

```text
[2] ★★ 白名单粒度
    ✅ 匿名 GET /api/coupons      HTTP 200 / body.code=500   ← 精确路径放行
    ✅ 匿名 GET /api/coupons/my   HTTP 401                    ← ★ 没被误伤

[3] 管理端 3 端点 × 5 身份
                     匿名  demo  op_order  op_product  admin
    GET    list        401   403     403        403      200+500
    POST   create      401   403     403        403      200+500
    DELETE delete      401   403     403        403      200+500
```

**两条本日独有的证据：**

1. **白名单粒度**：`/api/coupons` 匿名 200、`/api/coupons/my` 匿名 **401**。
   若把白名单写成 `/**`，第二条会变成 200 ——
   而那意味着**任何人可以看任何人的券，且服务端不报任何错**。
   这一对断言就是「精确路径 vs 通配路径」的可执行区别。★ 这是 Day 16
   那个坑的**正解**（当时为绕开它，只能把类级映射退到 `/api`）。

2. **权限矩阵的区分度**：`op_product` / `op_order` 全是 403 ——
   它们**有各自岗位的权限**（12 条 / 4 条），**没有 `coupon:*`**。
   反向对照成立，说明「只给超管」这个决定真的生效了
   （若给所有管理员都发一遍，这一列会全是 200，矩阵就退化成「一次登录测试」）。

★ 顺带证明 **mall-marketing 真的被扫到了**：6 个端点无一 404。
（本项目「新模块漏改 `mall-server/pom.xml`」的症状就是「编译启动全绿但接口 404」——
本日 pom 早就配好，但这条断言仍然要打，因为它验的是**事实**而不是**[假设]**。）

### 9.5 现在轮到你了

骨架期到此为止。**15 处 TODO 全在你手上**，建议顺序见 §六（从 `increaseReceivedCount`
那条最短的 CAS 开始）。填完后的验收计划见 §七 —— 到那时本节的 `code=500`
应该全部变成 `200` 或 `400`，而门禁脚本会**拒绝再跑**（它的护栏：扫不到
`UnsupportedOperationException` 就罢工，理由见 §八.8）。

---

## 十、与阶段二的分界（Day 21 预告）

| | 阶段一（本日） | 阶段二（Day 21） |
|---|---|---|
| 券的产生与获取 | ✅ 管理端发券 + C 端领券 | — |
| 券的使用 | — | 下单时选券、算抵扣额、写 `user_coupons.status='USED'` + `order_id` + `used_at` |
| 动下单链路 | **不动** | ✅ 改 `OrderServiceImpl.createFromCart` |
| M1 回归 | 与今日无关（稳过） | ★ **会成为主要风险** |
| 新课题 | 限量 CAS、唯一约束、惰性过期 | 金额计算链、取消订单时**退券**（与 `releaseLocked` 同构的逆向操作） |

★ 阶段二会碰一个本阶段刻意避开的问题：**订单取消时券要不要退回**。
那是「状态机逆向 + 金额守恒」，含金量比本阶段更高，也更需要 M1 的护栏。
