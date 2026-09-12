# 用户模块接口文档（/api/users）

> 对应代码：`mall-user/src/main/java/com/mallx/user/controller/UserController.java`
> 数据来源：Docker PostgreSQL `users` 表（Day 03 建表）
> 更新时间：2026-09-09

---

## 0. 全局约定（先看这个，后面不重复）

### 统一返回结构

所有接口都返回同一个 JSON 骨架，由 `Result<T>` 类定义：

```json
{
  "code": 200,          // 业务状态码，见下表
  "message": "success", // 提示信息
  "data": ...           // 业务数据，可能是对象/数组/数字/null
}
```

**怎么判断成功？** 看 `code == 200`，不要看 HTTP 状态码（HTTP 恒为 200，错误也包在 body 里返回）。

### 业务状态码（来自 `ResultCode` 枚举）

| code | 含义 | 什么时候出现 |
|------|------|------------|
| 200 | 成功 | 正常返回 |
| 400 | 参数校验失败 | 请求参数不合法 |
| 404 | 资源不存在 | 查询的 id 不存在（`NOT_FOUND`） |
| 500 | 服务器错误 | 未知异常兜底 |

### 时间字段说明

`createdAt` / `updatedAt` 由 `MyMetaObjectHandler` **自动填充**，前端传不传都无效：
- 新建时：两个都自动填当前时间
- 更新时：只自动刷新 `updatedAt`，`createdAt` 不变

### 分页返回结构（`PageResult<T>`）

所有分页接口的 `data` 都长这样：

```json
{
  "records": [ ...本页数据数组... ],
  "total": 7,      // 满足条件的总条数（用来算总页数）
  "current": 1,    // 当前第几页（从 1 开始）
  "size": 10       // 每页条数
}
```

---

## 1. 创建用户

**POST** `/api/users`

### 说明
新增一个用户，走 MyBatis-Plus 内置 `save()` → 自动生成 `INSERT` 语句。
返回自增主键 `id`（数据库 `BIGSERIAL` 自动分配）。

### 请求体（JSON）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | String | 是 | 用户名，数据库层面 UNIQUE，重复插入会报错 |
| password | String | 建议 | 实际项目应存 BCrypt 密文，明文仅学习阶段 |
| nickname | String | 否 | 昵称 |
| phone | String | 否 | 手机号，UNIQUE |
| email | String | 否 | 邮箱，UNIQUE |
| avatar | String | 否 | 头像 URL |
| status | Integer | 否 | 状态（1 正常 / 0 禁用），不传按数据库默认 |

> `id`、`createdAt`、`updatedAt` **不需要传**，分别由自增、自动填充接管。

### 请求示例

```bash
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","nickname":"张三","email":"zs@test.com"}'
```

### 返回示例

```json
{
  "code": 200,
  "message": "success",
  "data": 8        // 新用户的 id
}
```

### 可能的错误

| 场景 | 结果 |
|------|------|
| username 重复（撞 UNIQUE 约束） | code=500（学习阶段先这样，后续 Day 会转成 400 友好提示） |

---

## 2. 查询用户详情

**GET** `/api/users/{id}`

### 说明
按主键查单个用户，走 `getById()` → `SELECT ... WHERE id = ?`。
**查不到时抛 `BusinessException(404)`**，由 `GlobalExceptionHandler` 统一捕获转成 JSON——这就是第②步"业务异常 + 全局处理器"的实战落地。

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| id | Long | 用户主键 |

### 请求示例

```bash
curl http://localhost:8080/api/users/1
```

### 返回示例（存在）

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": 1,
    "username": "demo",
    "password": "demo123",   // ⚠️ 学习阶段暂时返回，正式项目必须过滤掉
    "nickname": "演示用户",
    "phone": null,
    "email": null,
    "avatar": null,
    "status": 1,
    "createdAt": "2026-09-07T22:30:15",
    "updatedAt": "2026-09-07T22:30:15"
  }
}
```

### 返回示例（不存在）

```json
{
  "code": 404,
  "message": "用户不存在",
  "data": null
}
```

---

## 3. 分页查询用户 ⭐（本日核心：验证分页插件）

**GET** `/api/users?current=1&size=2`

### 说明
分页查所有用户。走 `userService.page(new Page<>(current, size))`，
第③步配的 **`PaginationInnerInterceptor` 会自动把 SQL 改写为 PostgreSQL 的 `LIMIT ... OFFSET ...`** 并追加一条 `COUNT` 查询算总数——**这个接口跑通 = 分页插件验证成功**。

### Query 参数（拼在 URL 上，不是 JSON body）

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| current | long | 1 | 第几页，从 1 开始 |
| size | long | 10 | 每页条数 |

### 请求示例

```bash
# 第 1 页，每页 2 条
curl "http://localhost:8080/api/users?current=1&size=2"

# 不传参数 → 默认 current=1, size=10
curl http://localhost:8080/api/users
```

### 返回示例

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "records": [
      { "id": 1, "username": "demo", "nickname": "演示用户", "...": "..." },
      { "id": 2, "username": "zhangsan", "nickname": "张三", "...": "..." }
    ],
    "total": 7,     // 库里总共 7 个用户
    "current": 1,
    "size": 2
  }
}
```

### 怎么确认分页真的生效了？

1. 库里造 >size 条数据（多调几次创建接口）
2. 请求 `current=1&size=2` → records 只有 2 条，total 是真实总数
3. 请求 `current=2&size=2` → 返回第 3、4 条数据
4. （进阶）把 `application.yml` 的 SQL 日志打开，能看到 `LIMIT ... OFFSET ...`

---

## 4. 删除用户

**DELETE** `/api/users/{id}`

### 说明
按主键删除，走 `removeById()` → `DELETE FROM users WHERE id = ?`。
**注意**：删除一个不存在的 id 也返回 200（MP 的 removeById 返回影响行数，这里没有做存在性校验）——学习阶段可接受，后续可改成"删不到返回 404"。

### 请求示例

```bash
curl -X DELETE http://localhost:8080/api/users/8
```

### 返回示例

```json
{ "code": 200, "message": "success", "data": null }
```

---

## 5. 修改昵称

**PUT** `/api/users/{id}/nickname`

### 说明
只改昵称这一个字段。核心机制：**`updateById()` 只更新非 null 字段**——
代码里 new 了一个 User 只 set 了 id 和 nickname，所以生成的 SQL 是
`UPDATE users SET nickname = ?, updated_at = ? WHERE id = ?`（`updated_at` 由自动填充刷新），
**不会**把其他字段覆盖成 null。

### 请求体

直接传字符串字面量（学习阶段简化写法；正式项目应封装成 DTO 对象）：

```json
"新昵称"
```

### 请求示例

```bash
curl -X PUT http://localhost:8080/api/users/1/nickname \
  -H "Content-Type: application/json" \
  -d '"改名后的昵称"'
```

### 返回示例

```json
{ "code": 200, "message": "success", "data": null }
```

### 验证时间自动填充

改完昵称后再查详情（接口 2），对比 `updatedAt` 已变成当前时间、`createdAt` 没变——
**这就是第③步 `MyMetaObjectHandler` 生效的铁证**。

---

## 6. 接口一览表

| # | 方法 | 路径 | 用途 | 底层 MP 方法 | 依赖的 Day04 基础设施 |
|---|------|------|------|-------------|---------------------|
| 1 | POST | /api/users | 创建 | save() | Result、自动填充 |
| 2 | GET | /api/users/{id} | 详情 | getById() | Result、BusinessException、全局异常处理器 |
| 3 | GET | /api/users?current=&size= | 分页 | page() | Result、PageResult、**分页插件** |
| 4 | DELETE | /api/users/{id} | 删除 | removeById() | Result |
| 5 | PUT | /api/users/{id}/nickname | 改昵称 | updateById() | Result、自动填充 |
