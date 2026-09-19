# Day 11：C 端收货地址（mall-user 扩展）

> 日期：2026-09-18 / 2026-09-19
> 目标模块：`mall-user`（已存在，`description` 里早就写了「用户、收货地址」）
> 前置：Day 10 已提交（`e8bc10e` / `565f257`），本地 `ahead 6`（待你在终端 push）
> 学习模式：**陪练** —— 本文档给规划、模板、讲解；代码由你自己敲。

---

## 0. 今天要达成什么

一句话：**登录用户能维护自己的地址簿 —— 增、删、改、查、设为默认，且任意时刻最多只有一条默认地址。**

为什么值得单独一天：

| 能力 | 前面练过吗 | 今天的难度 |
|---|---|---|
| 多行写 + 事务 | Day 08（插主表 + 插子表） | 复习 |
| ★ **「改一行」+「改一片」必须原子** | ❌ 从没练过 | ★ 全新，今天主角 |
| IDOR 越权防护（404 伪装） | Day 10（购物车） | 复刻，应该能自己想到 |
| `boolean` 字段映射坑 | Day 10 摸过 `selected` | ★ 升级（`is_` 前缀会踩雷） |
| 正则校验（手机号） | ❌ 从没练过 | 小 |

和购物车的本质区别：**购物车是「行级私有」，地址是「集合级私有」** ——
不光要保证「这行是你的」，还要保证「你的这一堆行之间不能自相矛盾」（两条默认）。
**「多条行之间的不变式」，就是事务存在的理由。**

---

## 1. 现状调研（全部实测过）

### 1.1 `user_addresses` 表长什么样

```sql
CREATE TABLE IF NOT EXISTS user_addresses (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT       NOT NULL,
    receiver_name   VARCHAR(50)  NOT NULL,
    receiver_phone  VARCHAR(20)  NOT NULL,
    province        VARCHAR(50)  NOT NULL,
    city            VARCHAR(50)  NOT NULL,
    district        VARCHAR(50)  NOT NULL,
    detail_address  VARCHAR(255) NOT NULL,
    is_default      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_address_user FOREIGN KEY (user_id) REFERENCES users(id)
);
```

实测索引与约束（`\d user_addresses` 输出）：

```
Indexes:
    "user_addresses_pkey" PRIMARY KEY, btree (id)
    "idx_user_addresses_user_id" btree (user_id)
Foreign-key constraints:
    "fk_user_address_user" FOREIGN KEY (user_id) REFERENCES users(id)
```

三个关键结论：

| 点 | 含义 |
|---|---|
| **11 列，没有 `is_deleted`** | ⚠️ 别照抄 Product 加 `@TableLogic` —— 加了所有查询报「列不存在」。地址是真删 |
| **★ 没有任何 UNIQUE 约束** | 数据库**不会**阻止「一个用户两条 `is_default = true`」→ **唯一性只能靠事务里写代码保证**。这就是今天的核心 |
| `fk_user_address_user` | `user_id` 必须指向真实用户，导入假数据会撞外键 |

### 1.2 基线（实测）

| 表 | 行数 |
|---|---|
| `user_addresses` | **0** ← 空表起步 |
| `users` | 1（id = 1，`demo` 用户） |
| `cart_items` | 0 |

### 1.3 模块落位：`mall-user`，不用改任何 POM

```
backend/mallx/mall-user/
├── pom.xml          ← 只依赖 mall-common（已确认）
└── src/main/java/com/mallx/user/
    ├── controller/  ← UserController / AuthController
    ├── entity/      ← User
    ├── mapper/      ← UserMapper
    ├── service/     ≡ UserService / impl/UserServiceImpl
    └── security/    ← LoginUser / UserDetailsServiceImpl
```

- 新包 `com.mallx.user.address.*` 还是直接摊在 `com.mallx.user.*`？→ **直接摊开**（模块小，别再套一层）
- `@MapperScan("com.mallx.**.mapper")` 是全局的 → `com.mallx.user.mapper.UserAddressMapper` 自动注册
- ⚠️ **不要**在 `mall-user` 里写 XML —— 今天的表是单表 CRUD，用 MP 的 `LambdaQueryWrapper` / `LambdaUpdateWrapper` 就够了，**没有 JOIN 需求**（对比 Day 10 必须手写 XML 做跨模块 JOIN）

### 1.4 鉴权：白名单里没有它，天然要登录

`SecurityConfig` 第 49-52 行实测：

```java
.requestMatchers("/api/auth/login", "/api/auth/admin/login", "/api/hello", "/error").permitAll()
.requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
.requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
.anyRequest().authenticated()      // ← /api/addresses/** 落到这里，必须带 token
```

→ **不需要动 Security**，也不需要 `@PreAuthorize`（C 端 token 权限集为空，挂了必 403，Day 10 已定型）。

---

## 2. 接口设计（6 个）

| # | 方法 | 路径 | 说明 | 关键要求 |
|---|---|---|---|---|
| 1 | GET | `/api/addresses` | 我的地址列表 | 默认地址排最前 |
| 2 | GET | `/api/addresses/{id}` | 地址详情 | 非本人 → **404** |
| 3 | POST | `/api/addresses` | 新增地址 | **第一条自动成默认** |
| 4 | PUT | `/api/addresses/{id}` | 修改地址 | 非本人 → **404** |
| 5 | DELETE | `/api/addresses/{id}` | 删除地址 | 删默认后**自动补位** |
| 6 | PUT | `/api/addresses/{id}/default` | 设为默认 | 事务内**互斥**，无 body |

出参统一 `AddressVO`（**绝不含 `userId`** —— 别把自己的内部字段泄给客户端）。

---

## 3. 核心难点讲解

### 3.1 ★ 默认地址互斥：先「清一片」，再「置一行」

**错误写法（会出两条默认）**：

```java
// ❌ 只更新目标行，旧的默认行没被清掉
addr.setIsDefault(true);
addressMapper.updateById(addr);
```

**正确写法（事务包住两次 UPDATE）**：

```java
@Override
@Transactional
public void setDefault(Long userId, Long addressId) {
    UserAddress addr = requireOwn(userId, addressId);   // ① IDOR 校验（顺带确认存在）

    // ② 把这个用户「其它」的默认标记全部清掉
    addressMapper.update(null, new LambdaUpdateWrapper<UserAddress>()
            .eq(UserAddress::getUserId, userId)
            .eq(UserAddress::getIsDefault, true)
            .set(UserAddress::getIsDefault, false));

    // ③ 再把目标行置为默认
    addr.setIsDefault(true);
    addressMapper.updateById(addr);
}
```

三个细节：

| 细节 | 说明 |
|---|---|
| `update(null, wrapper)` | 第一个参数传 `null` 表示「不需要实体，我自己用 wrapper 的 `set()` 指定要改哪些列」 |
| ② 里**不写** `.ne(id, addressId)` 也行 | 反正 ③ 会把它再置回 true，多一次无效 UPDATE 而已。但写了更干净 → 建议 `.ne(UserAddress::getId, addressId)` |
| **`@Transactional` 必须由外部调用** | 如果 `create()` 里写 `this.setDefault(...)` → **自调用不走代理，事务静默失效**。因为 `create` 自己也要事务，就让它自己写这两段，别相互调 |

**为什么必须事务？** 两次 UPDATE 之间如果进程崩了，用户会一条默认都没有；更糟的是并发下两个请求交错 → 两条默认。事务给的是「要么都成，要么都不成」。

> ⚠️ 事务只保证**原子性**，**不保证互斥** —— 两个并发请求各自开事务，仍可能都读到「没有默认」然后各插一条。
> 真正的兜底是数据库的 **部分唯一索引**（见 §6 延伸），今天不强求。

### 3.2 ★★ `is_default` 的字段映射坑（`is_` 前缀）

这是今天最容易静默踩死的地方。

| 实体写法 | Lombok 生成的 getter | MP 反推的列名 | 结果 |
|---|---|---|---|
| `private Boolean isDefault;` | `getIsDefault()` | `is_default` | ✅ 正确 |
| `private boolean isDefault;` | `isDefault()` | **`default`** | ❌ PG 保留字，SQL 直接报错 |

原因：MP 从 getter 名倒推属性名时，`is` 开头会**砍掉 `is`** ——
`isDefault()` → `Default` → `default`；而 `getIsDefault()` → `IsDefault` → `isDefault` → `is_default`。

**结论：一律用包装类型 `Boolean`，别用 `boolean`。**
（Day 10 的 `cart_items.selected` 没踩到，是因为它不叫 `is_selected`。）

> 这条理论推导在第 1 步冒烟里会**实测实锤** —— 插一行 `is_default = true`，再查出来看是不是 `true`。别只信我说的。

### 3.3 新增时「第一条自动成为默认」

```java
@Override
@Transactional
public Long create(Long userId, AddressSaveDTO dto) {

    long count = addressMapper.selectCount(new LambdaQueryWrapper<UserAddress>()
            .eq(UserAddress::getUserId, userId));

    boolean makeDefault = Boolean.TRUE.equals(dto.getIsDefault()) || count == 0;
    //                                        ↑ 用户显式要                              ↑ 或者这是第一条

    if (makeDefault) {
        clearDefault(userId, null);      // 把现有默认清掉（同事务内）
    }

    UserAddress addr = new UserAddress();
    addr.setUserId(userId);              // ★ userId 只从 token 取，绝不信客户端
    addr.setReceiverName(dto.getReceiverName());
    // ... 其余字段
    addr.setIsDefault(makeDefault);
    addressMapper.insert(addr);
    return addr.getId();
}
```

`clearDefault` 抽成私有方法（**两个公开方法各自在事务内调用它**，而不是公开方法互相调用）：

```java
private void clearDefault(Long userId, Long exceptId) {
    addressMapper.update(null, new LambdaUpdateWrapper<UserAddress>()
            .eq(UserAddress::getUserId, userId)
            .eq(UserAddress::getIsDefault, true)
            .ne(exceptId != null, UserAddress::getId, exceptId)   // ★ 条件成立才拼进 SQL
            .set(UserAddress::getIsDefault, false));
}
```

> ★ `.ne(条件, 列, 值)` 这个重载超好用：`exceptId == null` 时整段 `ne` 被跳过，不用写两个分支。

### 3.4 删除默认地址 → 自动补位

删掉默认地址后，如果不管，用户下单时会「没有默认地址」。业务上应该补位：

```java
@Override
@Transactional
public void remove(Long userId, Long addressId) {

    UserAddress addr = requireOwn(userId, addressId);
    addressMapper.deleteById(addr.getId());            // 真 DELETE

    if (Boolean.TRUE.equals(addr.getIsDefault())) {    // 删的正好是默认 → 补位
        UserAddress next = addressMapper.selectOne(new LambdaQueryWrapper<UserAddress>()
                .eq(UserAddress::getUserId, userId)
                .orderByAsc(UserAddress::getId)
                .last("LIMIT 1"));
        if (next != null) {
            next.setIsDefault(true);
            addressMapper.updateById(next);
        }
    }
}
```

**同一个事务里有 `DELETE` + `UPDATE`** —— 这是今天的第二次事务练习。
`last("LIMIT 1")` 是 MP 的「原样拼到 SQL 最后」，别滥用，但取一条够用。

### 3.5 IDOR：`requireOwn` 直接复刻 Day 10

```java
private UserAddress requireOwn(Long userId, Long addressId) {
    UserAddress addr = addressMapper.selectById(addressId);
    if (addr == null || !addr.getUserId().equals(userId)) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "地址不存在");
    }
    return addr;
}
```

**所有 5 个按 id 操作的接口（详情/改/删/设默认）第一行都必须调它**，一个都不能漏。
写成方法就是为了「漏不掉」—— 顺手抽私有方法的另一个好处。

### 3.6 参数校验（`AddressSaveDTO`）

```java
@Data
public class AddressSaveDTO {

    @NotBlank(message = "收件人不能为空")
    @Size(max = 50)
    private String receiverName;

    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1[3-9]\\d{9}$", message = "手机号格式不正确")
    private String receiverPhone;

    @NotBlank @Size(max = 50)   private String province;
    @NotBlank @Size(max = 50)   private String city;
    @NotBlank @Size(max = 50)   private String district;
    @NotBlank @Size(max = 255)  private String detailAddress;

    /** 可空：null 视作 false（是否设为默认由 Service 结合「是否首条」决定） */
    private Boolean isDefault;
}
```

⚠️ 三件事：

1. **`AddressSaveDTO` 里绝对不能有 `userId` 字段** —— 有了就等于把「这地址是谁的」交给客户端。Day 10 的 `CartAddDTO` 同理
2. `@NotBlank` 只对 `String` 有效；`isDefault` 是 `Boolean`，想强制非空用 `@NotNull`，但今天**故意放开可空**
3. 新增和修改**共用一个 DTO**（字段完全一样）。修改是全量覆盖语义（PUT），不做 Day 09 那种 PATCH 差分 —— 地址字段少，没必要

---

## 4. 分步任务

| 步 | 内容 | 新建 / 修改 | 预计 |
|---|---|---|---|
| **1** ✅ | 实体 + Mapper + 冒烟验证 | `entity/UserAddress.java`、`mapper/UserAddressMapper.java`、临时 `ApplicationRunner` | 7 项断言 |
| **2** ✅ | DTO/VO/Service 接口 + 列表 & 详情 & 新增 | `dto/AddressSaveDTO.java`、`vo/AddressVO.java`、`service/AddressService.java`、`impl/AddressServiceImpl.java`、`controller/AddressController.java` | 8 项 |
| **3** ✅ | 修改 + 删除（含默认补位） | 上表原地扩展 | 8 项 |
| **4** ✅ | ★ 设为默认（事务互斥） | 上表原地扩展 + `backend/sql/02-index.sql`（新增部分唯一索引） | 5 项常规 + 3 组实验 |
| **5** ✅ | 端到端验收 + Swagger 确认 + git 提交 | — | 11 项 |

### 第 1 步冒烟清单（必须真机跑）

| # | 断言 |
|---|---|
| 1 | `insert` 一行地址成功，`id` 回填非空 |
| 2 | **`is_default = true` 插进去、查出来还是 `true`** ← 实锤 §3.2 的映射 |
| 3 | `created_at` / `updated_at` 被自动填充（非 null） |
| 4 | `selectCount(userId=1)` == 1 |
| 5 | `selectById` 能把 8 个业务字段全部捞回 |
| 6 | 改 `is_default = false` 后 `updateById` 生效，且 `updated_at` 变了 |
| 7 | `deleteById` 后 `selectById` 返回 `null` |

> 冒烟跑完：`mvn -o clean -pl mall-user` 清掉临时 Runner 的 class，再删源码。

---

### ★ 第 1 步实测记录（2026-09-19 08:49，真机跑）

临时 `AddressSmokeRunner`（跑完即删）+ 临时打开 `log-impl` 抓真实 SQL。

| # | 断言 | 结果 |
|---|---|---|
| 1 | `count(before) = 0` | ✅ |
| 2 | `insert rows=1 id=1` | ✅ |
| 3 | `createdAt` / `updatedAt` 自动填充 | ✅ |
| 4 | 全字段回读：`isDefault=true`、中文地址完整 | ✅ |
| 5 | `count(userId=1)=1`、`count(isDefault=true)=1` | ✅ |
| 6 | `updateById` 生效（`isDefault` → `false`） | ⚠️ 字段改了，但 **`updatedAt` 没变** |
| 6b | 手动 `setUpdatedAt(null)` 后再 `update` | ✅ **时间戳立刻变了** → 假设证实 |
| 7 | `deleteById` 后 `selectById=null`、`count=0` | ✅ |

**★★ 实锤 SQL**（`log-impl` 抓的原文）

```sql
INSERT INTO user_addresses ( user_id, receiver_name, receiver_phone, province, city, district,
                             detail_address, is_default, created_at, updated_at )
       VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )
SELECT COUNT(*) AS total FROM user_addresses WHERE (is_default = ?)
DELETE FROM user_addresses WHERE id=?
```

→ **`is_default` 列名推导完全正确**，§3.2 从「理论推导」升级为「实测实锤」；
→ 最后那条是真 `DELETE`，印证本表无软删除。

---

### ★★★ 意外收获：`updateById` 不会刷新 `updated_at`

**现象**：从 DB 读回来的实体（`updatedAt` 非 null）走 `updateById`，`updated_at` **保持旧值不动**；
手动 `setUpdatedAt(null)` 后再 `updateById`，时间戳**立刻刷新**（`.690858 → .774921`）。

**根因**（读源码坐实）：`MyMetaObjectHandler.updateFill` 用的是 `strictUpdateFill`，
而 **MP 的 `strict*Fill` 语义是「字段为 `null` 才填充」**，不是「每次 update 都刷」。

```java
// mall-server/.../config/MyMetaObjectHandler.java 第 21 行
this.strictUpdateFill(metaObject, "updatedAt", LocalDateTime.class, LocalDateTime.now());
```

**影响面**（这是要记住的）：

| 写法 | `updated_at` 是否刷新 |
|---|---|
| `new Xxx()` + 只 set 业务字段 → `updateById` | ✅ 会（因为 `updatedAt` 是 null） |
| `selectById` → 改字段 → `updateById` | ❌ **不会** |

而 Day 09/10 的代码里 **`selectById → 改 → updateById` 是主流写法**
（`CartServiceImpl.updateQuantity` / `updateSelected` 都是）→ 那些接口的 `updated_at` 其实一直没刷新。

**三种处理方式**（选一个并全项目保持一致）：

1. **不管** —— `updated_at` 只是审计字段，业务不依赖它（当前状态，可接受）
2. `entity.setUpdatedAt(null)` —— 有效但丑，容易忘
3. `update(null, wrapper.set(...))` 显式指定要改的列 —— 最可控，代价是代码变长

> 第 3 步写「删除后补位」时会**再遇到一次**这个选择（`next.setIsDefault(true); updateById(next)`），到时候你就有判断依据了。

---

### ★ 第 2 步实测记录（2026-09-19 09:18，真机跑）

5 个文件：`AddressSaveDTO` / `AddressVO` / `AddressService` / `AddressServiceImpl` / `AddressController`。
首次编译**失败** → 修正后编译通过 → 重启应用 → 8 项全绿。

#### 首次编译失败的原因（值得回看）

```
[ERROR] .../AddressServiceImpl.java:[43,42] 非法的表达式开始
```

**javac 只报了 1 个错，不代表只有 1 个错 —— 语法错误会让它直接中断**，后面的错误全被挡住。
手动核完，实际有 6 处：

| # | 问题 | 后果 | 教训 |
|---|---|---|---|
| 1 | `boolean makeDefault = /* 待填 */;` 空着 | **语法错误**（编译器唯一报出的那条） | 语法错会掩盖后续所有错 |
| 2 | `selectList(...).eq(...))` **括号提前闭合**，后面 `.orderByDesc/.orderByAsc` 挂到了返回的 `List` 上 | `List` 没有这两个方法 | ★★ **括号闭合的位置决定这条链挂在哪个对象上**，不是排版风格 |
| 3 | 调用 `this::toVo`，方法名是 `toVO` | 找不到符号 | 大小写敏感 |
| 4 | 缺 `LambdaUpdateWrapper` / `ResultCode` / `BusinessException` / `BeanUtils` 四个 import | 找不到符号 ×3 | import 是纯体力活，别漏 |
| 5 | `create()` 少 `@Transactional` | **能编译能跑，语义错** | ★★ 见下 |
| 6 | 空 ② 未填 | 功能缺失 | — |

#### ★★ 为什么 `create()` 必须挂 `@Transactional`

`create()` = 「清旧默认（UPDATE）」+「插新行（INSERT）」两次写操作，中间有一个**能被别人看见的时间窗**：

| 无事务 | 有事务 |
|---|---|
| 清默认先自动提交 → 此刻该用户**一条默认都没有** | 外界看不到中间态 |
| `insert` 失败（断连 / 约束冲突）→ 旧默认**已被清掉且不回滚** | `insert` 失败 → 清默认**一起回滚**，原状不变 |

`user_addresses` **没有任何 UNIQUE 约束**，「每个用户最多一条默认」这条跨行不变式数据库管不了 → **只能靠事务在代码里保证**。这是今天从「行级私有」（Day 10 购物车）升级到「集合级不变式」的关键一跃。

#### 8 项验收（全部真机 curl，`demo/demo123`）

| # | 请求 | 期望 | 实际 |
|---|---|---|---|
| 1 | 匿名 `GET /api/addresses` | 401 | ✅ `http=401 {"code":401,"message":"未登录或登录已过期"}` |
| 2 | `POST` 第 1 条（**不传** `isDefault`） | 200，库里 `is_default=true` | ✅ `code=200 id=3` |
| 3 | `POST` 第 2 条（**不传** `isDefault`） | 200，库里 `is_default=false` | ✅ `code=200 id=4` |
| 4 | `GET /api/addresses` | 默认那条排最前 | ✅ `count=2`，顺序 `#3 张三 default=True` → `#4 李四 default=False` |
| 5 | `GET /api/addresses/3` | 字段齐全，**响应无 `userId`** | ✅ `含userId字段=False`，中文地址完整 |
| 6 | `POST` 手机号 `12345` | `code=400` | ✅ `手机号格式不正确` |
| 7 | `GET /api/addresses/99999` | `code=404` | ✅ `地址不存在` |
| 8 | `POST` 缺 `receiverName` | `code=400` | ✅ `收件人不能为空` |

#### 数据库实锤（不靠接口自报）

```sql
SELECT id, user_id, receiver_name, is_default FROM user_addresses ORDER BY id;
--  3 | 1 | 张三 | t
--  4 | 1 | 李四 | f

SELECT user_id, count(*) total, count(*) FILTER (WHERE is_default) defaults FROM user_addresses GROUP BY user_id;
--  1 | 2 | 1        ← 「至多一条默认」成立
```

> ⚠️ psql 输出里 `张三` 显示成 `寮犱笁` 是**管道显示假象**（记忆里的老坑），接口返回的 `张三` 才是真身。

#### 遗留数据

第 2 步结束时 `user_addresses` 留下 **2 行（id=3/4，user_id=1）**，第 3 步（改/删）和第 4 步（设为默认）正好拿它们当靶子，**不用清**。

---

### ★ 第 3 步实测记录（2026-09-19 09:44，真机跑）

改 3 个文件（`AddressService` 加 2 个签名、`AddressServiceImpl` 加 2 个方法、`AddressController` 加 2 个端点 + 2 个 import）。
**一次编译通过**（`BUILD_EXIT=0`），8 项全绿。

#### 本步的设计决策：把「取消默认」这条路封掉

昨天的不变式只说「最多一条默认」，本步因为要做补位，升级成更强的一条：

```
有 0 条地址  →  0 条默认      正常
有 ≥1 条地址 →  恰好 1 条默认   ★ 本步要守住的不变式
```

于是 `PUT` 里 `isDefault` 是**唯一不做全量覆盖**的字段：

| `dto.isDefault` | 行为 |
|---|---|
| `true` | 设为默认（`clearDefault(userId, addressId)` 排除自己，再置 `true`） |
| `null` | **不动**当前默认状态 |
| `false` | **不动**（等于忽略） |

**为什么不许 `false` 直接取消？** 那会造出「有地址、零默认」的状态，和 `remove()` 的补位逻辑自相矛盾（删了要补、改了却能取消，说不通）。
换默认的唯一途径 = **把另一条设为默认**。默认地址永远恰好一条，只是它指谁可以变。

#### `remove()` 的顺序：先删、再补

```java
addressMapper.deleteById(addressId);     // ① 真删
if (wasDefault) {                        // ② 删的正好是默认 → 补位
    UserAddress next = addressMapper.selectOne(... .orderByAsc(id).last("LIMIT 1"));
    if (next != null) { next.setIsDefault(true); addressMapper.updateById(next); }
}
```

- **先删再查**：删完再查「剩下的」，天然把被删行排除掉，不用额外 `ne(id, ...)`
- ★ `selectOne` 在结果 **>1 行时会直接抛异常**，所以**必须配 `LIMIT 1`**；`last()` 是往 SQL 尾巴拼原生片段 —— **只许写死常量，绝不能拼用户输入**
- ★ `next != null` 必须判：删的是最后一条地址时它就是 `null`
- ★ `DELETE` + 补位 `UPDATE` **必须同事务** —— 中间那一刻该用户是「有地址、零默认」

#### 8 项验收（真机 curl，`demo/demo123`）

为测补位先 `POST` 出第 3 条（`id=5`）；为测 IDOR 造了靶子行 `user_addresses.id=9001 / user_id=2 / VICTIM`（`user_addresses.user_id` 有外键 `fk_user_address_user`，所以还得先造一个 `users.id=2`）。

| # | 请求 | 期望 | 实际 |
|---|---|---|---|
| 1 | `PUT /3` 改姓名+城市 | 全量覆盖生效 | ✅ `name=张三丰 city=广州市 district=天河区` |
| 2 | `PUT /4` 带 `isDefault=true` | 默认转移到 #4，#3 被清 | ✅ 列表 `#4:李四:def=True  #3:张三丰:def=False  #5:王五:def=False` |
| 3 | `PUT /4` **不传** `isDefault` | 默认状态不变 | ✅ `name=李四改 isDefault=True` |
| 4 | `PUT /3` 手机号 `12345` | `code=400` | ✅ `手机号格式不正确` |
| 5 | `PUT /99999` | `code=404` | ✅ `地址不存在` |
| 6 | `PUT /9001`（**别人的行**） | `code=404`，且行未被改 | ✅ `地址不存在` |
| 7 | `DELETE /4`（默认项） | **补位**：`{3,5}` 中 id 最小者接任 | ✅ 列表 `#3:张三丰:def=True  #5:王五:def=False` |
| 8 | `DELETE /99999` + `DELETE /9001` | 均 `code=404` | ✅ 两条都是 `地址不存在` |

#### 数据库实锤（查库，不看接口自报）

```sql
 id  | user_id | receiver_name | receiver_phone | is_default
  3  |       1 | 张三丰         | 13800000001    | t      ← 全量覆盖成功、补位接任
  5  |       1 | 王五           | 13700000003    | f
9001 |       2 | VICTIM        | 13900000099    | t      ← 名字/城市原封不动 → IDOR 被挡住
```

`user_id=1 → total=2, defaults=1`（至多一条默认仍成立）。

#### 遗留数据

- `user_addresses` 现在 **3 行**：`#3 张三丰(默认)`、`#5 王五`、`#9001 VICTIM(user_id=2)`
- `users` 多了一行 `id=2 intruder`（IDOR 靶子的外键依赖）
- ★ 这两条是**测试夹具**，第 4 步还要用来测 IDOR，**第 5 步收尾时一起清掉**（`DELETE FROM user_addresses WHERE user_id=2; DELETE FROM users WHERE id=2;`）

#### ⚠️ 新踩的编码坑

用 `Get-Content "$env:TEMP\fixture.sql" -Raw | & docker.exe exec -i ... psql` 灌含中文的 SQL 时，报：

```
ERROR: syntax error at or near "13800000099"
LINE 2: VALUES (2, 'intruder', '{noop}intruder', '?????, '1380000009...
```

原因：**PS 5.1 的 `Get-Content` 不带 `-Encoding` 时按 ANSI(GBK) 读**，UTF-8 的中文被读成乱码、再管道出去就成了 `?????`，SQL 字符串提前断掉。
对策：① 管道时加 `-Encoding utf8`；② **测试夹具 SQL 一律写纯 ASCII**（本次采用 ②，靶子行名字直接用 `VICTIM`，顺带让"没被改动"的断言更好比对）。

---

### ★ 第 4 步实测记录（2026-09-19 09:52，真机跑）

`PUT /api/addresses/{id}/default`（无 body）。**一次编译通过，5 项常规验收全绿**：

| # | 请求 | 期望 | 实际 |
|---|---|---|---|
| 1 | 匿名 `PUT /3/default` | 401 | ✅ `http=401 未登录或登录已过期` |
| 2 | `PUT /5/default` | 默认从 #3 转到 #5 | ✅ `[#5:def=True  #3:def=False]` |
| 3 | 再调一次 `PUT /5/default` | 幂等，默认仍 1 条 | ✅ 默认条数=1 |
| 4 | `PUT /9001/default`（别人的行） | 404 且行不变 | ✅ `code=404 地址不存在`（复查库中 `9001` 仍 `t`） |
| 5 | `PUT /99999/default` | 404 | ✅ `code=404 地址不存在` |

#### ★★ 实验 A：脏数据面前，幂等短路会「见死不救」

绕过应用直接 UPDATE，造出「user 1 两条默认」的脏状态（`defaults_now=2`），然后调接口：

| 调用 | 结果 | 库中状态 |
|---|---|---|
| `PUT /3/default`（#3 已是 true） | `code=200` | ❌ 仍是两条 `true` |
| `PUT /5/default`（#5 已是 true） | `code=200` | ❌ 仍是两条 `true` |

**结论（本轮最重要的认知）**：`if (Boolean.TRUE.equals(old.getIsDefault())) return;` 这三行短路，把"重复请求"挡在 DB 门外（省两条 UPDATE），代价是**当脏状态已经存在时，这个接口无法修复它** —— 两行都是 `true`，任何一次 `setDefault` 都会短路返回。

所以两条结论同时成立：

1. **真正守护不变式的是 `clearDefault + setIsDefault(true)` 这对组合，短路只是优化**；
2. **"能写脏数据"这件事本身才是病根** —— 靠某个接口自愈不靠谱，得让脏数据写不进来。

#### ★★★ 实验 B：把规则下推到数据库（部分唯一索引）

```sql
CREATE UNIQUE INDEX uk_user_addresses_default
    ON user_addresses(user_id) WHERE is_default = true;
```

| # | 操作 | 结果 |
|---|---|---|
| B1 | **在脏数据上**建索引 | ✅（按预期失败）`ERROR: could not create unique index ... DETAIL: Key (user_id)=(1) is duplicated.` |
| B2 | 先清脏（`UPDATE ... SET is_default=false WHERE user_id=1 AND id<>3`）再建 | ✅ `CREATE INDEX`，`pg_indexes` 中可见 `... WHERE (is_default = true)` |
| B3 | 索引建好后**再次手工造脏** | ✅（按预期被拒）`ERROR: duplicate key value violates unique constraint "uk_user_addresses_default"` + `DETAIL: Key (user_id)=(1) already exists.`；数据未被改动 |
| B4 | `PUT /5/default` | ✅ `code=200`，`#5` 接任，默认条数=1 |
| B5 | `PUT /3`（body 带 `isDefault=true`） | ✅ `code=200`，`#3` 接任，默认条数=1 |
| B6 | `POST`（body 带 `isDefault=true`） | ✅ `code=200 newId=6`，`#6` 接任，默认条数=1 |

B4-B6 是**回归验证**：索引是新增的**全局约束**，所有「写 `is_default=true`」的路径都可能撞上它。三条路径全部正常，因为它们在写 `true` 之前都先在同一事务内把旧的清成了 `false`。

#### 三层防线（本轮定型）

| 层 | 位置 | 作用 | 失效后果 |
|---|---|---|---|
| 1 | Java 幂等短路 | 挡重复请求，省无谓 UPDATE 与行锁 | 脏数据无法自愈（实验 A） |
| 2 | `@Transactional` 清一片 + 置一行 | 保证操作前后不变式成立、中途不可被看见 | 并发下仍可能被别的写入路径破坏 |
| 3 | **DB 部分唯一索引** | **兜底：违反者直接 23505，脏数据落不了库** | — |

★ 与 Day 09 `sku_code` 的部分索引（`WHERE is_deleted = 0`）是同一招的第二次使用：**把"靠纪律维持的不变式"翻译成"数据库主动拒绝"**。索引 DDL 已同步进 `backend/sql/02-index.sql`（第一节 用户索引）。

#### 遗留数据

`user_addresses` 现有 4 行：`#3 张三丰`、`#5 王五`、`#6 赵六(默认)`、`#9001 VICTIM(user_id=2)`；`users` 有 `id=2 intruder`。**第 5 步收尾时一起清**：

```sql
DELETE FROM user_addresses WHERE user_id = 2;
DELETE FROM user_addresses WHERE id IN (3,5,6);
DELETE FROM users WHERE id = 2;
```

（第 5 步端到端还会用到，先留着。）

---

## 5. 端到端验收清单（第 5 步）

| # | 请求 | 期望 |
|---|---|---|
| 1 | `POST /api/auth/login`（demo） | 200 + token |
| 2 | `GET /api/addresses`（无 token） | **401** |
| 3 | `POST /api/addresses` 新增第 1 条（不传 isDefault） | 200，`is_default` 自动 `true` |
| 4 | `POST /api/addresses` 新增第 2 条（不传 isDefault） | 200，`is_default = false`（只能有一条默认） |
| 5 | `GET /api/addresses` | 2 条，**默认那条排在最前** |
| 6 | `PUT /api/addresses/{第2条}/default` | 200 → 再查列表：第 2 条 `true`、第 1 条 `false` ✅ |
| 7 | `GET /api/addresses` 复查 | **恰好 1 条 `is_default = true`**（反例防火墙） |
| 8 | `POST` 手机号 `12345` | 400（`@Pattern` 生效） |
| 9 | **IDOR**：伪造一条属于 user_id=999 的地址，用 demo 的 token 去 `PUT`/`DELETE`/`PUT .../default`/`GET` | **全部 404**，且该行**分毫未动**（要复查 DB） |
| 10 | `DELETE` 当前默认地址 | 200 → 列表里剩下的那条**自动变成默认** |
| 11 | 删除最后一条后再 `DELETE` 同 id | 404 |

### ★ 第 5 步实测记录（2026-09-19 09:57，真机跑）

先把 demo 的地址清空，让链路从「空地址簿」开始，**11 项全绿**：

| # | 请求 | 实际 |
|---|---|---|
| 1 | `POST /api/auth/login`（demo） | ✅ `code=200`，token 191 字符 |
| 2 | 匿名 `GET /api/addresses` | ✅ `http=401 未登录或登录已过期` |
| 3 | `POST` 第 1 条（不传 `isDefault`） | ✅ `id=7`，列表 `#7:def=True`（**首条自动默认**） |
| 4 | `POST` 第 2 条（不传 `isDefault`） | ✅ `id=8`，`#7:def=True  #8:def=False` |
| 5 | `GET` 列表 | ✅ 返回顺序 `[#7, #8]`（**默认排最前**） |
| 6 | `PUT /8/default`（无 body） | ✅ `code=200` → `#8:def=True  #7:def=False` |
| 7 | 复查默认条数 | ✅ **恰好 1** |
| 8 | `POST` 手机号 `12345` | ✅ `code=400 手机号格式不正确` |
| 9 | **IDOR × 4**：`GET` / `PUT` / `PUT .../default` / `DELETE` 打 `/9001` | ✅ 四次全 `code=404 地址不存在` |
| 10 | `DELETE /8`（当前默认） | ✅ `code=200` → 列表 `#7:def=True`（**自动补位**） |
| 11 | `DELETE /7`（最后一条，也是默认） | ✅ `code=200` → 列表变空，**`next == null` 未 NPE**；再删同 id → `code=404` |

**查库实锤**（不看接口自报）：

```
  id  | user_id | receiver_name |  city   | is_default
 9001 |       2 | VICTIM        | CHENGDU | t          ← IDOR 那四下分毫未动
```

第 11 项一次覆盖两个边界：**「删掉最后一条地址」（补位时 `next == null`）** 和 **「已删除的 id 再删一次」**。

#### 收尾清理与最终基线

```sql
DELETE FROM user_addresses WHERE user_id = 2;   -- 清 IDOR 靶子
DELETE FROM users WHERE id = 2;                 -- 清靶子的父行
```

- 最终基线：**`users=1 | user_addresses=0 | cart_items=0 | products=5`**
  （序列 `users_id_seq=2`、`user_addresses_id_seq=8` —— 跳号但不撞主键）
- `uk_user_addresses_default` **保留**：它是 schema 的一部分，不是测试夹具
- Swagger `/v3/api-docs` **16 个路径**（新增 `/api/addresses`、`/api/addresses/{id}`、`/api/addresses/{id}/default`）
- git：`b302104 feat(address)` + `a928b85 docs`，工作区干净

---

## 6. 坑预判

| 坑 | 症状 | 预防 |
|---|---|---|
| `boolean`（基本类型）写 `isDefault` | `column "default" does not exist` 或语法错误 | 用 `Boolean` 包装类型 |
| `@Transactional` 自调用 | 事务不生效，中间失败留脏数据 | 公开方法不互相调，抽私有方法共享 |
| 忘了 `requireOwn` | IDOR 漏洞：能改别人的地址 | 5 个按 id 的接口逐个过一遍 |
| DTO 里放 `userId` | 客户端能指定地址归属 | 只用 `(Long) authentication.getPrincipal()` |
| 新增时不判断 `count == 0` | 第一条地址不是默认，下单页空着 | §3.3 |
| `updateById` 传整个实体 | 注意 MP 的 NOT_NULL 策略：`null` 字段不入 SQL；但自动填充每次都会写 `updated_at` | 已知行为，不算坑 |
| 以为表有 UNIQUE 兜底 | 并发下出现两条默认 | §6 延伸，或至少知道这是「代码保证」而非「数据库保证」 |

---

## 7. 延伸思考（不强制做）

1. ~~**数据库层兜底**~~ → **已在第 4 步实现 ✅**：PG 的部分唯一索引把「每个用户最多一条默认」下推到数据库：
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS uk_user_addresses_default
       ON user_addresses(user_id) WHERE is_default = true;
   ```
   已同步进 `backend/sql/02-index.sql`。实测（见 §4 第 4 步记录）：**在脏数据上建索引会直接失败** —— `could not create unique index ... Key (user_id)=(1) is duplicated`；建好后手工造第二条默认撞 **23505**。
   这是 PG 特色能力（SQL Server / MySQL 没有），代价是「先清后置」的顺序一旦写反就会撞 23505。

2. **并发的真实后果**：拿两个终端同时 `PUT .../default`，看会不会出两条默认。
   这能让你亲手感受到「事务 ≠ 锁」。

3. **`@Transactional` 的另外三个常用参数**：`readOnly = true`（只读事务）、
   `rollbackFor = Exception.class`（默认只回滚 RuntimeException）、`propagation = REQUIRES_NEW`。

---

## 8. 今日产出

- [x] `entity/UserAddress.java`
- [x] `mapper/UserAddressMapper.java`
- [x] `dto/AddressSaveDTO.java`
- [x] `vo/AddressVO.java`
- [x] `service/AddressService.java` + `impl/AddressServiceImpl.java`
- [x] `controller/AddressController.java`
- [x] `backend/sql/02-index.sql` 新增部分唯一索引 `uk_user_addresses_default`
- [x] 6 个接口在 Swagger UI 里可调（`/v3/api-docs` 16 个路径）
- [x] 端到端 11 项全绿
- [x] git 提交（`b302104 feat(address): ...` + `a928b85 docs: ...`）
- [ ] ⬜ 用户终端 `git push origin main`（AI 会话无凭据，本地已 `ahead 8`）
