# Day 22：管理端补齐 —— 用户管理 + 仪表盘（收口 M2）

> 方向：**管理端补齐**（§5.1 Dashboard + §5.2 用户管理），RBAC 留给 Day 23。
> 陪练模式：本文档 + 结构改动 + 骨架由我出，**实现你亲手写**。
> ★ 本日**额外挖出并当场修掉一个真漏洞**（见 §二），它不是计划内的工作。

> ✅ **状态：已实现并验收通过（2026-09-24）**
> - 新建 14 个文件 + 改 4 个文件（清单见 §四）；DDL **零改动**（`users.status` 等列早已存在）。
> - **实现已完成**：7 处 Java（`AdminUserServiceImpl` 3 / `UserServiceImpl` 2 / `DashboardServiceImpl` 2）
>   + `DashboardMapper.xml` 的 5 条 SQL 全部落地（要点见 §五）。
> - `mvn -o install -DskipTests` → **12 / 12 BUILD SUCCESS**（27.6s）。
> - `day22-xml-check.py` → XML 良构 **7/7**、新增 statement **5/5**、双向一致 **0 差异**、
>   **空实现 0 条 / XML TODO 0 条 / Java 占位 0 处**。
> - `day22-perm-apply.py` → **7/7 PASS** + 幂等成立（`user:list` 的 path 已订正）。
> - `day22-admin-verify.py`（本日新建，A–F 六组）→ **67 / 67**；`EXPECTED=67` 护栏核过（无断言被跳过）、
>   **基线还原 YES**。★ 断言预期值全是设计值，无一顺着实测改。
> - `day22-skeleton-smoke.py` → 骨架期 **32 / 32**。★ 实现填完后它的 B/C 组会全部失效（500 → 200），
>   这是**正常的**，见 §二末段「两个脚本方向相反」。
> - 回归（同一轮内跑完，应用只起一次 7m19s）：**`day17-m1-regression.py` 198/198
>   + `BASELINE RESTORED: YES`**；`day17-a` 26/26、`day17-b` 21/21、`day19-search` 58/58、
>   `day20-l1l2` 33/33、`day20-l5-brand` 24/24、`day20` 82/82、`day21` 53/53。
> - 提交：`55e4514`（fix user 收口）/ `937339a`（feat admin 骨架）/ `8248b59`（feat order L7）/
>   `973cec2`（chore 权限 SQL + 脚本 + 文档）/ `ba675cc`（feat 实现）/ `6587d1e`（test 验收脚本 + 报告）。

---

## 一、为什么是这一块

| 事实 | 依据 |
|---|---|
| 计划里 **M2（Day 22）= 后端 API 完整含搜索/管理端数据** | `2026-09-18` 的里程碑定义（M1=Day18 全链路 / M2=Day22 / M3=Day30 前端+部署） |
| 原路线「Day 17–20 搜索与管理 → Day 21–22 收尾」被**优惠券插队** | Day 20/21 实际做的是券的阶段一/二（新加的），管理端那块被挤掉 |
| 按 Day-01 §5 需求逐条对账，缺口就是三块 | §5.1 Dashboard（**一块都没做**）/ §5.2 用户管理（**无管理端**）/ §5.6 权限管理（**零接口**） |
| 退款/售后**不在** V1.0 范围 | `Day-14:813` / `Day-15:627` / `Day-17:204,477` 三处都写明「属售后域，V2.0」；`after_sales` 表零行零接口 |

★ 上文最后一行是对我自己上一次推断的**推翻**：我曾把「退款/退券」当成 Day 22 的候选（因为 Day-21 §十一 预告过它），
但三处文档都明确把它划给了 V2.0 —— **计划文档里的「预告」不等于「排期」**，以需求对账为准。

---

## 二、★ 开工前实测：一个真漏洞（本日最重要的一件事）

**发现路径（代码级三条证据 → 实测 16 条断言）**

| # | 证据 | 出处 |
|---|---|---|
| ① | 白名单**不含** `/api/users` ⇒ 只需登录，不是公开 | `SecurityConfig:49-62` |
| ② | `UserController` 三个方法**都没有** `@PreAuthorize`（C 端 token 无 perms，挂了必 403 —— 所以「不挂」本身是对的），但也**没有任何归属过滤** | `UserController`（改前） |
| ③ | `User` 实体有 `password` 字段且**无 `@JsonIgnore`**，而三个方法直接返回 `Result<User>` / `Result<PageResult<User>>` | `User.java:16` |

**`day22-sec-probe.py` 实测结果（修复前 16/16 全绿 = 三条推论全部成立）**

```
[A] 匿名 GET /api/users            -> HTTP 401          （这一条本来就是对的）
[B] demo token GET /api/users      -> 200，返回全站 2 个用户，每条都带 password
                                    password 值与 DB 哈希【逐字节相同】
[C] demo token GET /api/users/2    -> 200，拿到别人的完整信息（含 password）
                                    「看自己」与「看别人」响应【结构同构】，无任何区分
[D] demo token PUT /api/users/2/nickname -> 200（能改【任何人的】昵称）
[E] op_order（只有 order:* 四个权限）同样能拉全站用户
    权限种子里 user:list 的 path = /api/users  ← C 端路径（Day 06 的遗留）
```

⇒ **任何登录用户都能拉走全站口令哈希、并改任何人的资料。** 这不是「练手代码不够优雅」，是实打实的越权 + 敏感信息泄露。

**修复手法（决策 1）：把 id 从入参里【移除】，而不是给它加校验**

```
改造前：GET /api/users/{id}       id 是【用户输入】⇒ 必须做 requireOwn（伪装 404）
改造后：GET /api/users/me         id 来自 token 的 principal ⇒ 结构上不可能越权
```

★ 这两条路的安全性差异是**性质**不同而非程度不同：前者靠「校验写对了」，后者靠「伪造入口不存在」。
同族：`requireOwn` 先判 null、`releaseByOrder` 必须在 CAS 之后 —— **位置/结构本身就是语义**。

**修复后的证据（`day22-sec-probe-report-AFTER-FIX.txt`：3/16 通过、13 条失效）**

13 条「漏洞存在」断言全部失效，且失效原因逐条对应修复本身：

| 断言 | 修复前 | 修复后 | 说明 |
|---|---|---|---|
| 旧 `GET /api/users` | 200 + 全站哈希 | **404** `{"code":404,"message":"接口不存在"}` | 端点已拆（★ 顺带证明 Day 20 补的 `NoResourceFoundException` handler 生效） |
| 旧 `GET /api/users/{id}` | 200 | **404** | 同上 |
| 旧 `PUT /api/users/{id}/nickname` | 200 | **404** | 同上 |
| 泄露的 password | `{noop}intruder` | **None** | 出口换成了 `UserVO` |
| `user:list` 的 path | `/api/users` | `/api/admin/users` | 权限表与代码重新对上 |
| `GET /api/admin/users` | 404（不存在） | 200 + code 500 | 本日新建的端点（骨架期长相） |

★ **只保留了 3 条通过**：A1/A2（匿名 401，本来就没问题）+ D2（DB 值未被改坏）。
★ 这个脚本的性质要明确：**它是「诊断快照」，不是「回归断言」** ——
它的期望值写的是「漏洞存在」，所以修复后它必然变成 3/16。**那 13 个 FAIL 就是修复证据本身。**
长期的安全回归断言放在 §六 的 `day22-admin-verify.py` 里（期望值反过来写）。

---

## 三、五条设计决策

| # | 决策 | 选定 | 理由 / 代价 |
|---|---|---|---|
| 1 | **C 端 `/api/users` 怎么收口** | **改成 `/api/users/me`**（删列表 + 按 id 查；出口一律走 VO） | 见 §二。代价：C 端「看别人」的能力被彻底移除 —— 这本来就是不该有的能力 |
| 2 | **Dashboard 6 个指标怎么切** | **两个端点**：`/overview`（4 个标量）+ `/trend?days=N`（按天序列） | 快照与时序的变化频率、缓存语义、入参都不同；合并会让 `days` 渗透到不需要它的那半边 |
| 3 | **销售额口径** | **支付流水口径**：`SELECT coalesce(sum(amount),0) FROM payments WHERE status='SUCCESS'` | `orders` 记「应当收的钱」，`payments` 记「钱实际动过的事实」。将来加退款（`REFUNDED`）时支付口径天然扣得掉。★ 口径写进 `DashboardOverviewVO` 的 javadoc，不只写在文档里 |
| 4 | **Dashboard 跨四表怎么取数** | **`mall-admin` 里手写 XML 直查表**（零 POM 改动） | 判据：**只读聚合不是业务写**。写操作跨模块必须走 Service 接口（事务与不变量在那边），而「算几个数」只依赖**表结构**，不构成语义依赖。★ 反面条件：一旦统计需要业务规则（扣退款、按渠道分组），就该换成「各模块暴露方法」或建 `mall-stat` |
| 5 | **`user:*` 权限发给谁** | `user:list` / `user:detail` → **超管 + 订单管理员**；`user:status` → **只给超管** | 订单管理员要核对买家（发货/纠纷）才能干活 ⇒ 读是必要的；而「禁用账号」是治理动作，只给最高权限。★ dashboard:* 发给**三个角色全部**（只读汇总、无个人敏感数据、无写操作，粒度太粗无法反推） |

★ 决策 5 的那条非对称（读给业务角色、写给超管）正是夹具 `op_order` 存在的意义 ——
验收里必须有一条 `op_order` 打 `/status` 得 **403** 的反向断言，否则「只给超管」这件事无人验证。

---

## 四、交付清单

### 新建（14 个）

| 文件 | 作用 |
|---|---|
| `mall-user/vo/UserVO.java` | **用户可公开字段**（C 端 `/me` 与管理端共用）—— 本类存在的唯一理由是**把 password 挡在出口之外** |
| `mall-user/dto/UserStatusUpdateDTO.java` | 管理端改状态载荷（`@NotNull` + `@Min(0)` + `@Max(1)`） |
| `mall-user/dto/NicknameUpdateDTO.java` | 改昵称载荷（`@NotBlank` + `@Size(max=50)`）—— 取代原来的裸 `@RequestBody String` |
| `mall-user/service/AdminUserService.java` + `impl/AdminUserServiceImpl.java` | 管理端用户服务（**不做归属过滤**，防线是权限码） |
| `mall-user/controller/AdminUserController.java` | `GET /api/admin/users`、`GET /api/admin/users/{id}`、`PUT /api/admin/users/{id}/status` |
| `mall-admin/vo/DashboardOverviewVO.java` | 4 个标量 + 口径 javadoc |
| `mall-admin/vo/TrendPointVO.java` | 一天两个值（订单量 + 销售额） |
| `mall-admin/mapper/DashboardMapper.java` + `resources/mapper/DashboardMapper.xml` | 5 条只读聚合（SQL 形状与坑写在 XML 注释里） |
| `mall-admin/service/DashboardService.java` + `impl/DashboardServiceImpl.java` | 薄 Service（只有夹紧一行判断） |
| `mall-admin/controller/AdminDashboardController.java` | `GET /api/admin/dashboard/overview`、`/trend` |
| `backend/sql/12-day22-permissions.sql` | 4 条新权限（id 22–25）+ **订正 `user:list` 的 path** + 幂等 + 序列校准 + 四段自检 |

### 改动（4 个）

| 文件 | 改动 |
|---|---|
| `mall-user/controller/UserController.java` | **收口重写**：三个旧端点 → `/me` 与 `/me/nickname`；出口换 `UserVO` |
| `mall-user/service/UserService.java` + `impl/UserServiceImpl.java` | 加 `getMyProfile(userId)` / `updateMyNickname(userId, nickname)`（★ 入参一律带 userId） |
| `mall-order/vo/OrderDetailVO.java`、`OrderVO.java` | **L7**：各加 `discountAmount` |
| `mall-order/service/impl/OrderServiceImpl.java` | **L7**：`buildDetail` 与 `toOrderVO` 各加一行 setter |
| `backend/loadtest/day17-b-order-detail-verify.py` | **L7 的断言同步**（3 处：字段白名单 14→15、DB 快照加 `discount_amount`、逐字段对账加 `discountAmount`）★ 见 §七 坑 4 |

---

## 五、那 7 处实现（2026-09-24 已落地）

> 骨架交付时是 7 处 `UnsupportedOperationException` + 5 条空 SQL；下面是**当初给实现者的要点**，
> 保留原文以便对照「设计意图 → 实际落地」是否一致。
> ★ 实际落地时**只做了一处补充决定**：手动 `UpdateWrapper` 的 UPDATE 不走自动填充器 ⇒
> `users.updated_at` 会静默停在旧值，而实体声明的正是 `INSERT_UPDATE`。骨架把「补它」列为可选项，
> 实现时**两处写点都显式补了** `.set(User::getUpdatedAt, LocalDateTime.now())`。
> 不影响幂等（PG 按 `WHERE` 命中计数，值没变也算 1 行）—— 验收 B14 已钉住这条。
> ⚠️ 这与同模块 `AddressServiceImpl` 的既定选择（`updateById` + 「审计字段业务不依赖，不管它」）
> **不一致**，登记为待决项。

| # | 文件 | 方法 | 关键点 |
|---|---|---|---|
| 1 | `AdminUserServiceImpl` | `pageUsers` | 三列 `keyword` 必须用 `.and(w -> ...)` **包一层括号**（否则 `status=? AND a OR b` 会让已禁用行漏进来）；夹紧两行在 `new Page<>()` 之前；换壳时记得搬 `total/current/size` |
| 2 | `AdminUserServiceImpl` | `getDetail` | null → **真 404**（管理端不伪装）；返回 `UserVO` |
| 3 | `AdminUserServiceImpl` | `updateStatus` | **条件更新一句到底**，影响行数即答案（0 行 = 404）；幂等（1→1 也是 1 行）；不加 `@Transactional` |
| 4 | `UserServiceImpl` | `getMyProfile` | `getById` + `BeanUtils.copyProperties` → `UserVO`；★ 出口绝不能是 `User` |
| 5 | `UserServiceImpl` | `updateMyNickname` | 条件更新 + 影响行数即答案；⚠️ 手写 `UpdateWrapper` 的 UPDATE **不走自动填充** ⇒ `updated_at` 需显式处理 |
| 6 | `DashboardServiceImpl` | `getOverview` | 4 次 Mapper 调用 + 逐个 setter（该 VO 无全参构造）；**不要**再补一次 null 兜底（那会掩盖 SQL 里的 `coalesce`） |
| 7 | `DashboardServiceImpl` | `getTrend` | ★ **先夹紧再算日期**：`safeDays` 夹到 1..90，`startDate = LocalDate.now().minusDays(safeDays - 1)` |
| 8 | `DashboardMapper.xml` | 5 条 SQL | 形状与四个坑写在注释里（**日期骨架 LEFT JOIN 补 0** / 别名用下划线 / `to_char` 的格式串是单引号 / 两个 LEFT JOIN 各自独立） |

★ 加上 `DashboardMapper.xml` 那 5 条 SQL，实际是 **7 个 Java 方法 + 5 条 SQL**。
★ 落地后 `day22-xml-check.py` 复跑：Java 占位 **0**、XML TODO **0**、空实现 **0**（三处同时清零）。

---

## 六、验收（`day22-admin-verify.py` —— 已落地，**67 / 67**）

> ✅ 已按下面的规划实现并跑通：**67 / 67**、`EXPECTED=67` 护栏核过、基线还原 YES。
> ★ 与骨架期的 `day22-skeleton-smoke.py` **方向相反**：那个期望「200 + code 500」，这个期望真数据；
> 两个都留着各司其职（smoke 是骨架期门禁，本脚本是长期回归）。

按 Day 20/21 的规格（造数 + 高水位线清理 + 逐条 `psql` 对账 + `EXPECTED` 常量护栏）：

| 组 | 内容 |
|---|---|
| **A · 安全回归** | 把 `day22-sec-probe.py` 的断言**反过来写**：旧三个端点必须 404；`/me` 只能看自己（拿别人的 id 无从传）；响应体**不含** `password` 键；`user:list` 的 path 已订正 |
| **B · 用户管理** | 分页夹紧（`size=-1 → 1`、`size=0 → 1`、`size=1000 → 100`）；`keyword` 跨三列命中 + **括号正确性**（造一条「昵称命中但已禁用」的行，过滤 `status=1` 时它必须不出现 —— 这是 `.and()` 是否漏括号的唯一判据）；`status` 不传 = 两者都要；改状态后 DB 对账；0 行 → 404 |
| **C · 权限矩阵** | `op_order` 打 `/users` 200、打 `/status` **403**；`op_product` 打 `/users` **403**；C 端 token 打管理端 **403**；匿名 **401** |
| **D · Dashboard** | 4 个标量与 DB 逐值对账（销售额**支付口径**：造一条 `FAILED` 支付，它必须不计入）；趋势天数断言 = 请求天数（**补 0 的证据**）；`days=-1 → 夹到 1`、`days=100000 → 夹到 90`；★ 造一条「昨天有单、今天没单」的数据来证明补 0 真的发生（否则样本量陷阱，断言恒真） |
| **E · L7** | 三个数一起断（`pay = total - discount`）；不用券时 `discountAmount = 0.00` 而非 `null` |

---

## 七、坑（本日专属，逐条都有翻车现场）

### 1. ★★ 同一个文件的多个 `Edit` **必须串行**

**现场**：我在同一条消息里给 `OrderServiceImpl.java` 发了两个 `Edit`（`buildDetail` 一处、`toOrderVO` 一处），
**两个都返回 success，但只有第二个生效** —— 第一个被覆盖了。
现象极隐蔽：`OrderDetailVO`/`OrderVO` 的**字段**都在（那是另一个文件的 Edit），
只有 `buildDetail` 里那行 setter 不见了 ⇒ 接口 `discountAmount` 键存在但**值恒为 null**。

**后果**：这个错**编译过、启动过、`day22-skeleton-smoke` 的 D1「键存在」断言照样 PASS**，
只有 D2（值对账）抓住它。⇒ 这正是「键集合断言 ≠ 值断言」的活例。

**应对**：同文件多改 → 一次一个 `Edit`；并且**落盘后立刻 Grep 复验**（本项目铁律，我这次也漏了）。

### 2. ★ 断言之前先确认「这个接口的出口是哪个 VO」，别按 URL 猜

**现场**：`day22-skeleton-smoke.py` 第一版拿 `GET /api/admin/orders`（管理端列表）去断 `OrderVO` 的新字段，
得到一条**假 FAIL** —— 那个接口用的是 `AdminOrderVO`（由手写 SQL `selectAdminOrders` 装配），
`OrderVO` 只服务 C 端 `/api/orders`。从 FAIL 的「首行键」里一眼看出是别的类（它有 `userId`/`userNickname`）。

### 3. ★★ 改了出参 VO 的字段集 → 全项目 grep「键集合相等」式断言

**现场**：项目里有 5 个脚本用 `set(r.keys()) == set(VO_FIELDS)` 这种**双向**断言
（`day17-a` / `day17-b` / `day17-d` / `day17-f` / `day18-b`）。
给 `OrderDetailVO` 加 `discountAmount` ⇒ `day17-b` 立即会 FAIL（15 ≠ 14）。

**★ 这是本次挖到的回归覆盖盲区**：`day17-b` **不在 `day17-m1-regression.py` 的名单里**
（M1 只跑 `day14/15/16` 三个 E2E）⇒ **没有任何自动回归会因为漏改这个常量而报警**，只能靠人记得。
已同步 `day17-b` 的三处（字段白名单 / DB 快照 SQL / 逐字段对账），并把它登记进 `backlog` 的 T2。

### 4. ★ 给 VO 加了字段，就要给「值」也加断言

`day17-b` 的逐字段对账原来只比 `totalAmount` / `payAmount`。
如果只把 `discountAmount` 加进字段白名单、不加进对账循环，
那「字段在、值恒 null」这个错在它那里**永远不会被发现**（白名单只证明字段存在）。
已一并加上 —— 这条与坑 1 是同一个坑的两端。

### 5. ★ `Docker` 起来后立刻构建会 `malloc failed`（老坑，本日又踩一次）

`Chunk::new` / `Native memory allocation` ⇒ 是**环境**不是代码；等 5434 OPEN 后重跑即好。

### 6. jar 被上一个应用实例锁住

`repackage` 报 `Unable to rename ...jar.original` ⇒ 判据是「报错在 `spring-boot-maven-plugin:repackage` 而不是 compile」；
先停应用再构建（本日构建前先 kill 了 8080 上的实例）。

---

## 八、与 Day 23 的分界

| | 本日 | Day 23 |
|---|---|---|
| 管理端补齐 | ✅ 用户管理 + 仪表盘 | **§5.6 RBAC**：管理员 / 角色 / 权限的 CRUD 与分配 |
| 权限码 | 22–25 已发（`user:detail` / `user:status` / `dashboard:*`） | RBAC 自身需要的 `admin:*` / `role:*` / `permission:*` |
| ★ 核心难题 | — | **权限是签进 token 的 `perms` claim**（`AdminAuthController:71`）⇒ 改了角色权限后，**已签发的 token 里的权限快照不会变**。三条路线：① V1.0 认下「改完要重新登录」并写进文档；② 加 token 版本号（角色权限变更时递增，过滤器比对）；③ 每次请求回查 DB（一致性最强、性能代价最大） |
| 其他遗留 | L7 已完成；T2（回归名单扩围）已登记 | §5.3 品牌 CRUD（L5②）仍未做 |
