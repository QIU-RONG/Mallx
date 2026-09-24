# 用户模块接口文档

> 对应代码：
> - C 端：`mall-user/src/main/java/com/mallx/user/controller/UserController.java`
> - 管理端：`mall-user/src/main/java/com/mallx/user/controller/AdminUserController.java`
> - 数据来源：Docker PostgreSQL `users` 表（Day 03 建表）
> - **更新时间：2026-09-25（Day 24 订正）**
>
> ## ⚠️ 本文件的两次生命（读之前先看这段）
>
> | 版本 | 时间 | 端点 | 出参 |
> |---|---|---|---|
> | **旧** | Day 06（2026-09-09） | `GET /api/users`（全站列表）、`GET /api/users/{id}`、`PUT /api/users/{id}/nickname`、`DELETE /api/users/{id}` | **`User` 实体，带 `password`**（旧文里注释成「学习阶段暂时返回」） |
> | **现** | Day 22 收口（2026-09-24），Day 24 补文档 | `GET /api/users/me`、`PUT /api/users/me/nickname` | `UserVO`（**结构上不含 password**） |
>
> ★★ **旧版的那四个端点不是「过时」，是「被删掉的漏洞」。**
> Day 22 用 `backend/loadtest/day22-sec-probe.py`（16 条断言）实证：
> 它们**既没有归属过滤、也没有 `@PreAuthorize`**，出口又是带 `password` 的实体本身
> ⇒ **任何登录用户（含只有 `order:*` 四个权限的 `op_order`）都能拉走全站口令哈希，
> 并改任何人的昵称**。修复前 16/16 坐实，修复后 3/16（那 13 条「漏洞存在」断言失效
> 本身就是修复证据）。
>
> ⇒ 所以本文件不是「更新了几个字段」，而是**删掉了一份漏洞说明书**。
> 旧版曾把 `"password": "demo123"` 写进返回示例并注明「学习阶段暂时返回」——
> 那正是这条漏洞被当成预期行为的记录。**已全部删除，不保留历史示例**
> （历史留痕在 `docs/daily/Day-22-管理端补齐.md`，那里才是存档该待的地方）。

---

## 0. 全局约定（先看这个，后面不重复）

### 统一返回结构

```json
{
  "code": 200,          // 业务状态码，见下表
  "message": "success", // 提示信息
  "data": ...           // 业务数据，可能是对象/数组/数字/null
}
```

**怎么判断成功？** 看 `code == 200`。

⚠️ 但本项目<b>有两套</b>状态，别混：

| 层 | 谁给的 | 长什么样 | 什么时候出现 |
|---|---|---|---|
| **协议层** | Spring Security 过滤器链 | **真 HTTP 401 / 403** | 没登录 / 登录了但权限不够 |
| **业务层** | `@RestControllerAdvice` | **HTTP 200 + `body.code`** | 参数校验失败、资源不存在、业务规则拒绝 |

⇒ 「业务失败」永远是 **HTTP 200 + `code != 200`**；
「被安全层拒绝」永远是 **HTTP 4xx**，此时响应体里**没有** `Result` 骨架。
**判成功必须看 `code`，判鉴权必须看 HTTP 状态码。**

### 业务状态码（来自 `ResultCode` 枚举）

| code | 含义 | 什么时候出现 |
|------|------|------------|
| 200 | 成功 | 正常返回 |
| 400 | 参数校验失败 / 业务规则拒绝 | `@Valid` 拦下，或 Service 抛 `BusinessException` |
| 404 | 资源不存在 | 查询的 id 不存在（`NOT_FOUND`） |
| 500 | 服务器错误 | 未知异常兜底 |

### 分页返回结构（`PageResult<T>`）

分页接口的 `data` 都长这样：

```json
{
  "records": [ ...本页数据数组... ],
  "total": 7,
  "current": 1,
  "size": 10
}
```

⚠️ 管理端分页的 `size` 会被**夹紧到 `1..100`**：
`size=-1` → 当作 **1**（不是「不限量」）、`size=0` → 当作 **1**、
`size=1000` → 当作 **100**（`MAX_PAGE_SIZE`）。

### 出参白名单（`UserVO`）

**所有用户接口都只返回这 7 个字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Long | 用户主键 |
| username | String | 用户名（唯一） |
| nickname | String | 昵称 |
| phone | String | 手机号（唯一），可为 null |
| email | String | 邮箱（唯一），可为 null |
| status | Integer | 1 = 正常，0 = 已禁用 |
| createdAt | LocalDateTime | 注册时间 |

★★ **`UserVO` 是「用户的可公开字段」这个定义的唯一载体 —— `password` 在里面连字段都没有。**
这不是「忘了填」，而是一条硬规则：出口用 VO、不用实体
（`User` 实体有 `password` 且**没有** `@JsonIgnore`）。
⚠️ 以后往 `UserVO` 加字段前先自问：**这个字段给【任何】已登录用户看，有没有问题？**

⚠️ 另：表里有 `avatar` 列，但 `User` 实体未映射它 ⇒ `UserVO` 里也没有。
**不造「有字段但无来源」的列**。

---

## 1. C 端 · 我的资料

**GET** `/api/users/me`

### 说明

返回**当前登录用户自己**的资料。

★★ **为什么路径是 `/me` 而不是 `/{id}`**（这是本模块最重要的一处设计）：
`id` **不在入参里**，而是取自 token 的 `principal`
（`(Long) authentication.getPrincipal()`）⇒ **结构上不可能越权**。

> 对照：`GET /api/users/{id}` + `requireOwn(...)` 是「靠校验写对了」；
> `GET /api/users/me` 是「伪造入口不存在」。
> 后者少一段可以写错的代码 —— **可省掉的校验是最安全的校验**。

### 请求示例

```bash
curl "http://localhost:8080/api/users/me" \
  -H "Authorization: Bearer <token>"
```

### 返回示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "username": "demo",
    "nickname": "演示用户",
    "phone": null,
    "email": null,
    "status": 1,
    "createdAt": "2026-09-07T22:30:15"
  }
}
```

★ 注意示例里**没有 `password`** —— 那是刻意的，也是 Day 22 修复的核心。

### 可能的错误

| 场景 | 结果 |
|---|---|
| 不带头 / token 无效或过期 | **HTTP 401**（不是 200+code） |
| C 端 token 打管理端接口 | **HTTP 403** |

⚠️ C 端接口**不挂 `@PreAuthorize`**：C 端 token 里**没有 `perms`**（管理端才有），
挂了必然 403。本模块的防线是「**必须登录**」——
由 `SecurityConfig` 的 `anyRequest().authenticated()` 在公开白名单之外兜住。

---

## 2. C 端 · 改我的昵称

**PUT** `/api/users/me/nickname`

### 说明

只改**自己的**昵称（同样：id 不在入参里，从 principal 取）。

### 请求体（JSON）

| 字段 | 类型 | 必填 | 校验 |
|---|---|---|---|
| nickname | String | 是 | `@NotBlank` + 最长 50 字符 |

### 请求示例

```bash
curl -X PUT "http://localhost:8080/api/users/me/nickname" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"nickname":"改名后的昵称"}'
```

### 返回示例

```json
{ "code": 200, "message": "success", "data": null }
```

### 可能的错误

| 场景 | 结果 |
|---|---|
| 不带头 | **HTTP 401** |
| `nickname` 缺失 / 空串 / 纯空格 / 超 50 字 | `code=400`（`@Valid` 拦下） |

★ **返回值从「裸字符串」升级成了 DTO 对象**（`NicknameUpdateDTO`），三个理由：
① 裸 String **没法加校验**（空串、纯空格、超长都能直写进库）；
② `@NotBlank` 才能挡住「只发一个空格」这种**看起来非空、实际为空**的入参；
③ 裸字符串写法**依赖 `Content-Type`** —— 传 `{"nickname":"x"}` 会被连花括号一起存进去。
⚠️ 旧版文档里的示例是 `-d '"新昵称"'`（body 直接是字符串字面量），**那个写法已作废**。

⚠️ **昵称唯一性不校验**：业务上昵称可以重复。唯一性只属于 `username` / `phone` / `email`
三列（DB 各有唯一索引）。

---

## 3. 管理端 · 用户分页

**GET** `/api/admin/users` — 需权限码 **`user:list`**

### 说明

分页查**全部**用户（含已禁用）。与 C 端的「数据权限反转」是同一批设计：
C 端 `WHERE user_id = ?` 在 SQL 里过滤 ↔ 管理端**不过滤**，防线改成**权限码**。

### Query 参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| current | long | 1 | 第几页，从 1 开始 |
| size | long | 10 | 每页条数（★ 夹紧到 1..100） |
| keyword | String | 无 | 模糊匹配 **username / nickname / phone** 三个字段；不传 = 不过滤 |
| status | Integer | 无 | `1` = 只看正常，`0` = 只看已禁用；**不传 = 两者都要** |

★ `status` 用 `Integer` 而非 `int`：只有 `null` 才表达得出「不过滤」
（`int` 的默认值 `0` 会把「不传」静默判成「只看已禁用」）。

### 请求示例

```bash
curl "http://localhost:8080/api/admin/users?current=1&size=2&keyword=demo" \
  -H "Authorization: Bearer <admin-token>"
```

### 返回示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "records": [ { "id": 1, "username": "demo", "nickname": "演示用户", "...": "..." } ],
    "total": 2,
    "current": 1,
    "size": 2
  }
}
```

### 可能的错误

| 场景 | 结果 |
|---|---|
| 匿名 | **HTTP 401** |
| 有 token 但无 `user:list`（如 `op_product`） | **HTTP 403** |

---

## 4. 管理端 · 用户详情

**GET** `/api/admin/users/{id}` — 需权限码 **`user:detail`**

### 说明

按主键查用户。★ **已禁用的用户也能看**（管理端要能看见才能把它解禁 ——
与 C 端商品详情「下架商品管理端仍可看」是同一条理由）。

### 请求示例

```bash
curl "http://localhost:8080/api/admin/users/1" \
  -H "Authorization: Bearer <admin-token>"
```

### 返回示例

```json
{ "code": 200, "message": "success", "data": { "id": 1, "username": "demo", "...": "..." } }
```

### 可能的错误

| 场景 | 结果 |
|---|---|
| id 不存在 | `code=404`（业务码，HTTP 仍是 200） |
| 匿名 / 无 `user:detail` | **HTTP 401 / 403** |

---

## 5. 管理端 · 改用户状态

**PUT** `/api/admin/users/{id}/status` — 需权限码 **`user:status`**

### 说明

启用 / 禁用账号。★ 权限码 `user:status` **只发给超管** ——
禁用账号是**治理动作**，与「能看用户列表」不是同一件事
（所以它是单独一个码，而不是并进 `user:detail`）。

### 请求体（JSON）

| 字段 | 类型 | 必填 | 校验 |
|---|---|---|---|
| status | Integer | 是 | `@NotNull` + `@Min(0)` + `@Max(1)` |

### 请求示例

```bash
curl -X PUT "http://localhost:8080/api/admin/users/2/status" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"status":0}'
```

### 返回示例

```json
{ "code": 200, "message": "success", "data": null }
```

### 可能的错误

| 场景 | 结果 |
|---|---|
| `status` 缺失 | `code=400` |
| `status` = 2 或 -1 | `code=400` |
| 有 `user:list` 但无 `user:status` | **HTTP 403** |

★ **为什么是 `PUT /{id}/status` 而不是 `PUT /{id}`**（与商品管理端刻意相反）：
商品那边「编辑」的语义**本来就包含**上下架，所以并进 PUT 全字段；
用户这里**没有**「编辑用户」这个需求，只开一个**定点**端点，
免得将来出现「改状态时顺手把昵称也覆盖了」。

⚠️ 断言权限时必须给**合法载荷**：`@Valid` 跑在 `@PreAuthorize` **之前**，
非法 body 永远先撞 400，与有没有权限无关。

---

## 6. 接口一览表

| # | 方法 | 路径 | 用途 | 权限 | 出参 |
|---|---|---|---|---|---|
| 1 | GET | `/api/users/me` | 我的资料 | 仅需登录（C 端 token） | `UserVO` |
| 2 | PUT | `/api/users/me/nickname` | 改我的昵称 | 仅需登录 | `void` |
| 3 | GET | `/api/admin/users` | 用户分页（含禁用） | `user:list` | `PageResult<UserVO>` |
| 4 | GET | `/api/admin/users/{id}` | 用户详情（含禁用） | `user:detail` | `UserVO` |
| 5 | PUT | `/api/admin/users/{id}/status` | 启用/禁用 | `user:status`（**仅超管**） | `void` |

### 已下线端点（★ 不要照它们调接口，全部 404）

| 旧路径（Day 06） | 为什么没了 |
|---|---|
| `POST /api/users` | 公开注册不在 §5 范围内；用户由 `03-data.sql` 种子与后续流程产生 |
| `GET /api/users` | ★ **漏洞**：全站用户列表 + 每条带 `password`，无归属过滤、无权限码 |
| `GET /api/users/{id}` | ★ **漏洞**：任意人详情 + `password`（实测与 DB 里的哈希**逐字节相同**） |
| `PUT /api/users/{id}/nickname` | ★ **漏洞**：能改**任何人**的昵称 |
| `DELETE /api/users/{id}` | 练手期端点；用户删除未进 §5 需求（涉及订单/评价等引用，需先定级联口径） |

> 前三条的实测证据与修复过程：`backend/loadtest/day22-sec-probe.py`（16 条断言）
> 与 `docs/daily/Day-22-管理端补齐.md`。
