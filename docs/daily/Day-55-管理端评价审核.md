# Day 55 · 管理端评价审核（隐藏 / 恢复）

> 起点：Day 54 §6 的「本日没做的事」里写着 ——
> **「没有评价管理页：mall-review 只有 C 端接口，要做得先加接口」**。
> 本日把那半句话补完：先加管理端接口，再做页面。
>
> 一句话：**C 端评价链路（Day 16）缺的最后一块拼图，是「平台能处理一条不该展示的评价」。**
> 在此之前，唯一的处理方式是直接改库。

---

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 新增端点 | 2 个：`GET /api/admin/reviews`、`PUT /api/admin/reviews/{id}/status` |
| 新增页面 | 1 个：`ReviewList.vue`（管理端「评价管理」，含已隐藏） |
| 新增权限 | 2 条：`review:list(47)` / `review:status(48)`，落在 `sql/19-review-permissions.sql` |
| 表结构 | **零改动** —— `reviews.status` 从 Day 03 就在（见 §1） |
| 单测 | 后端 **9 条**（`ReviewServiceImplTest`，全库后端 71 条）；前端 **48 条**（+1：评价菜单的权限闸门） |
| 静态护栏 | `day47-perm-count-guard` **17/17**（权限总数 46 → 48，5 处常量全部同步） |
| 控制组 | 后端 3/3、前端 5/5 + 7/7 全部命中（§6） |
| 门禁 | `mvn test` 全绿 · `lint` 0 · `test` 48/48 · `build` 通过 |

---

## 1. 为什么这不是「加个删除按钮」

★★ **`reviews.status` 列从 Day 03 建表时就在**（`01-schema.sql:247`，`NOT NULL DEFAULT 1`），
而 C 端的**六处**读路径从 Day 16 起就全都带着 `AND status = 1`：

| 读路径 | 是否带 `status = 1` |
|---|---|
| 商品评价列表 `selectProductReviews` | ✅ |
| 商品平均分 `selectProductAvgRating` | ✅ |
| 商品评价总数 `selectProductReviewCount` | ✅ |
| 回查单条 `selectByOrderItemId` | —（按 order_item_id 唯一命中，不回显公开列表） |
| 我的评价 `selectMyReviews` | —（自己看自己的，不过滤） |
| 写评价 `insertReview` | 写死 `status=1` |

⇒ 于是本日**一次写入、四处生效**：置 0 之后，这条评价立刻从商品页列表消失、
不再计入平均分、也不再计入评价总数；置回 1，三处同时回来。
**没有任何冗余字段要同步、没有缓存要失效** —— 这就是「没有第二个真相」的直接收益。

⇒ 也正因为如此，本日做的是**隐藏**而不是删除：

- 删除 = 用户的话永久消失，且无法审计；
- 隐藏 = 数据还在、可恢复、可追溯，与项目一贯的「软删优先」一致；
- 更不做「编辑评价内容」：**平台改过的话，就不再是用户的评价了**。

---

## 2. 接口与权限

### 2.1 两个端点

| 方法 | 路径 | 权限码 | 说明 |
|---|---|---|---|
| GET | `/api/admin/reviews` | `review:list` | 分页；可按商品 / 评分 / 状态过滤；**status 不传 = 含已隐藏** |
| PUT | `/api/admin/reviews/{id}/status` | `review:status` | 1=显示 0=隐藏；影响 0 行 → 404 |

★ 路径必须走 `/api/admin/**`：`SecurityConfig` 白名单里有 `GET /api/products/**` 的 permitAll，
挂到 C 端前缀下会**静默变成匿名可访问**（与 AdminProduct / AdminRefund 同一条铁律）。

★ 参数名用 `current`（管理端 users / roles 的通用叫法），**不是** C 端 `/api/reviews/my` 的 `page`
—— 照各自签名叫，不要「统一」。

### 2.2 权限分发：2 / 2 / 1 / 0

| 角色 | review:list | review:status |
|---|---|---|
| SUPER_ADMIN (1) | ✅ | ✅ |
| PRODUCT_ADMIN (2) | ✅ | ❌ |
| ORDER_ADMIN (3) | ❌ | ❌ |

★★ **两个码刻意不发给同一批人**：

- `review:list` 给商品管理员 —— 评价挂在商品页上，他必须看得见「这件商品被说了什么」；
- `review:status` **只给超管** —— 隐藏一条评价会**直接改写商品页的展示与评分**，
  是以平台身份处理用户表达，与 `user:status`（禁用账号）同级；
- `role 3` 两个都不给 —— 订单管理员管「下单到收货」，评价发生在收货之后、改的是内容，
  不是订单生命周期的一环。

⇒ 验收的反向对照就是：**op_product 能列表、但改状态稳定 403**；
**op_order 连列表都 403**。权限矩阵的区分度全靠「谁没有」。

---

## 3. 为什么另建 `AdminReviewVO`，而不是给 `ReviewVO` 加 `status`

`ReviewVO` 同时是**公开接口**（`GET /api/products/{id}/reviews`）的出参。往里加字段的后果有两层：

1. **公开契约变了**。M1 里 day16 的断言是**键集合双向相等**（少一个 FAIL、多一个也 FAIL），
   加字段会当场把回归打红；
2. **语义不对**。`status` 是管理侧状态，C 端看到它没有意义（公开列表恒为 1）。

⇒ 与 `AdminRefundVO` / `RoleDetailVO` 同一条做法：**多出管理侧视角就另起一个类**。
反过来，`UserVO` 是 C 端与管理端共用的 —— 因为两边**字段集完全相同**、没有判据差异。
判据是「视角是不是同一个」，不是「要不要省一个类」。

---

## 4. 分页与过滤的三个细节

1. **`status` 不传 = 两者都要**，不是「默认 1」。后者会让隐藏变成单向失明（藏完找不到）。
   单测 `nullStatusMeansIncludeHidden` 直接钉住这一点。
2. **夹紧必须在 `new Page<>()` 之前**：`size=9999 → 100`、`size=-1 → 1`（MP 里 -1 表示「不执行分页」）。
   漏了它不报错，只会在数据量起来后变成「一次请求拖走整张评价表」。
3. **`productId` 从表单的空串转 `null`**：后端是 `Long`，收到 `""` 直接 400。
   前端把「没填」表达成 `null`，是这一层唯一正确的翻译。

---

## 5. 第 10 次补发权限：这次是护栏先说话

新增 2 条权限后，**「权限总数」这份事实被钉在 5 处**：
`ci.yml`（3 个位置：就绪判据 / 步骤名 / 报错文案）、`day24-perm-apply.py`（2 个常量）、
`day25-sql-strict-check.py`（总数 + 文件清单 18→19）、`day25-compose-verify.py`、`day43-run-full-stack.ps1`。

本日没有靠记性 —— **先改 SQL，再跑 `day47-perm-count-guard.py`，让它逐处点名**：

```text
[OK] B1 ci.yml · initdb 数据判据 == total(48)   命中 2 处，值=[48, 48]
[OK] B2 ci.yml · 步骤名/日志文案 == total(48)   命中 2 处，值=[48, 48]
[OK] B3 ci.yml · 报错文案「期望 N」 == total(48) 命中 1 处，值=[48]
... 共 9 处
[OK] C3 backend/sql 文件数(19) == day25-sql-strict · EXPECTED_FILES
ASSERTIONS: 17 / 17 passed   VERDICT: OK
```

★ 一个容易漏的点：**B2 会扫描 `ci.yml` 全文的 `permissions=数字`，包括注释**。
所以「步骤名里写着 `permissions=48`」和「文件头注释里写着 `permissions=48`」是**两个声明点**，
只改一处会让 B2 报「命中 2 处，值=[48, 46]」。这正是它比人可靠的地方 —— 它不依赖你想得起来。

---

## 6. 验证

### 6.1 后端

```
mvn -o -pl mall-review -am test
Tests run: 9, Failures: 0, Errors: 0     ← ReviewServiceImplTest
（全库：common 9 + inventory 21 + marketing 32 + review 9 = 71）
BUILD SUCCESS
```

9 条断言分三组：

| 组 | 条数 | 锁什么 |
|---|---|---|
| `pageAdmin` · 夹紧 | 3 | size 上限 100 / 负数夹到 1 / page=0 → 1 |
| `pageAdmin` · 过滤与装配 | 2 | 三过滤透传；**status=null 不被改写成 1** |
| `updateStatus` · 三层判据 | 4 | 成功路径 / 0 行 → 404 / status=2 → 400 且不碰库 / null → 400 |

### 6.2 控制组（`_d55_review_unit_ctrl.py`）

| # | 变异 | 必须红 | 结果 |
|---|---|---|---|
| ① | 去掉 `Math.min(..., MAX_PAGE_SIZE)` | `sizeIsCappedAt100` | ✅ 1 条 |
| ② | 不判「影响 0 行」 | `notFoundThrows404` | ✅ 1 条 |
| ③ | 去掉 `status ∈ {0,1}` 判据 | `illegalStatusThrows400` | ✅ 1 条 |

基线 9/9 → 3/3 命中 → 收尾回 9/9，文件还原干净。

★★ **控制组脚本自己先踩了一次假红**：第一版把输出里所有 `Tests run:` 行**累加**，
而 Surefire 每个 `@Nested` 类各打一行、最后 `Results:` 再打一行 ⇒ 9 条被数成 **18 条**，
基线直接判「条数不是 9」。修法是**只取最后一段汇总**。
这与 D43-B 同源：**护栏的读数逻辑自己也会错，而且错的方向通常是「先制造假红」**。

### 6.3 前端

| 项 | 结果 |
|---|---|
| `npm run lint` | 0 警告 |
| `npm run test` | **48 / 48**（Day 54 的 47 + 评价菜单 1 条） |
| `npm run build` | 通过（vue-tsc + vite） |
| 控制组 `_d54` / `_d53` | **5/5、7/7 命中**，基线 48 全绿（常量已同步 47 → 48） |

新增的那条前端断言很具体：**只给 `review:status` 而不给 `review:list` 时，菜单里不能出现「评价管理」**
—— 否则商品管理员之外的账号会看到入口、点进去 403。

---

## 7. 本日没做的事（写清楚，不留给下一个人猜）

1. **没有真实 HTTP / DB 验证**。本机没有 `docker` CLI，原生 PostgreSQL 的口令未知 ⇒
   拿不到一个可用的 `mallx` 库。本日的证据是「单测 + 静态护栏 + 类型检查」，
   **不是**「端到端跑通」。下次能起全栈时，建议补一个 `day55-review-verify.py`：
   登录三种角色 → 列表 200/403 → 隐藏一条 → C 端列表少一条、平均分回退 → 恢复后一致。
2. **没有做「批量隐藏」**：单条足够覆盖治理场景；批量要配审计日志，属于 V2。
3. **没有评价举报入口（C 端）**：本日解决的是「平台能处理」，不是「用户能举报」。
