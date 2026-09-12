# Day 05：路线决策 — 登录鉴权(JWT) vs 商品模块(mall-product)

> 项目：MallX 企业级电商系统
> 状态：**决策文档**（先看这篇再定 Day 05 做什么）
> 前置：Day 04 已收官 —— 后端地基齐全（统一返回/异常/分页/自动填充/Swagger），mall-user CRUD 全链路验证通过，users 表可读写。

---

## 0. 你现在站在哪

Day 04 结束，你已经有：
- ✅ 一套能真实读写 PG 的**完整 CRUD 模板**（User 实体 → Mapper → Service → Controller）
- ✅ 分页、异常、统一返回、Swagger 全部就绪

**你学会了"造一个模块"的方法**。Day 05 面临两个方向，本文帮你决策。

---

## 1. 路线 A：登录鉴权（Spring Security + JWT）

### 是什么
让系统"认得出你是谁"：用户注册 → 登录发 Token → 之后每个请求带 Token，系统校验身份，未登录的请求被拦截。

### 难度 ★★★★☆（偏难，概念最多）
Spring Security 是 Java 后端**最劝退的一块**（过滤器链、SecurityContext、加密、Token），但也是企业项目**绕不开的核心**。

### 为什么有价值（最大理由）
Day 04 那种接口是"裸奔"的——任何人调 `/api/users/1` 都能看到数据。真实系统里**修改/删除/订单都必须知道"是谁在操作"**。没有鉴权，后面做订单、购物车全都做不了（不知道是谁下的单）。**它是所有"带用户身份"功能的解锁前置。**

### 技术栈（README 已定）
Spring Security + JWT。users 表已建好，password 字段已有（255 长度，够存 BCrypt 密文）。

### 大致要做的事（预览，不是全部）
```text
1. 密码处理：引入 BCrypt 加密（现 demo 的 {noop}demo123 是明文标记，要处理）
2. 引入依赖：spring-boot-starter-security + jjwt（JWT 库）
3. 写 SecurityConfig：放行 注册/登录，其余接口要 Token
4. 写 JwtUtil：生成/解析 Token
5. 写 LoginRequest/RegisterRequest DTO + AuthController（/api/auth/register、/api/auth/login）
6. 写 JwtAuthFilter：从请求头取 Token → 解析 → 塞进 SecurityContext
7. 写 UserDetailsService：登录时按用户名查用户、比对密码
8. 改造 User 实体返回：不把 password 泄露出去
9. 联调验收：注册→登录拿 Token→带 Token 访问受保护接口→无 Token 返回 401
```

### 会踩的坑（提前预警）
- Spring Security 默认**把所有接口都锁住**，配错了连 Swagger 都打不开
- Spring Boot 4.x 的 Security 配置写法 vs 网上 3.x 教程不同（`SecurityFilterChain` Bean 仍在，但包/自动配置可能有差异）
- `{noop}` 前缀密码不加密，正式要 BCrypt（涉及存量数据处理）
- JWT 库选型（jjwt 0.12+ API 和旧版不一样）

---

## 2. 路线 B：商品模块（mall-product）

### 是什么
把 Day 04 的"用户 CRUD"套路，**复制到商品上**：SPU 商品 + SKU 规格的列表/详情/按分类查。

### 难度 ★★☆☆☆（延续 Day 04，最顺）
几乎就是 Day 04 的翻版，只是表不同、加一点连表查询（商品挂分类/品牌）。

### 为什么有价值
- **巩固 Day 04 学的东西**（实体映射、分页、ServiceImpl），练熟"造模块"的手感
- 商品是电商的门面，商品列表/详情是后面所有页面的数据源
- 数据里 categories/brands 已有 7+7 条，但 **products 还是 0 条**——做这个模块正好补上商品数据

### 技术栈
不用新依赖，纯 MyBatis-Plus（沿用 Day 04 全部套路）。

### 大致要做的事（预览）
```text
1. 建 Product(SPU) 实体：@TableName("products")，字段对齐表（category_id/brand_id/name/...）
2. ProductMapper extends BaseMapper
3. ProductService + ProductServiceImpl
4. ProductController：商品列表分页、按分类查、详情（可含主图/描述）
5. 进阶可选：SKU 实体 + 按商品查 SKU（多一层关系）
6. 造几条商品数据，Swagger 验证
```

### 特点
**不引入任何新概念**，纯复用。做完你会更有信心，但学的"新东西"比路线 A 少。

---

## 3. 两条路线对比

| 维度 | A：登录鉴权(JWT) | B：商品模块 |
|------|----------------|-----------|
| 难度 | ★★★★ 偏难 | ★★ 偏易 |
| 新概念量 | 多（过滤器/安全上下文/Token/加密） | 少（基本是 Day04 复用） |
| 解锁后续 | **订单/购物车/评价的前置**（需身份） | 商品列表数据源 |
| 巩固 Day04 | 一般 | **非常好** |
| 成就感 | 高（"系统会认人了"） | 中 |
| 卡住风险 | 较高（Security 坑多） | 低 |

### 我的建议（组合拳）
**先做路线 B（商品），再做路线 A（鉴权）。**

理由：
1. **B 几乎不失败**——用你已会的套路快速再产出一个完整模块，正反馈强，把 Day 04 的方法论焊死。
2. 做 B 时你会发现"商品列表要不要登录才能看？"这种问题自然引出**鉴权的必要性**——到那时再做 A，动机更清晰、学得更透。
3. 先难后易容易劝退；先易后难，A 的难点正好是**从"能造模块"迈向"能造安全系统"的坎**，放到你有信心的节点。

> 如果你更想挑战/时间充裕，直接 A 也完全 OK，只是心理准备 Security 会比想象中折腾。

---

## 4. 决定后告诉我

选 **A**：我写《Day-05 登录鉴权(JWT) 完整规划文档》（分步+模板+避坑）
选 **B**：我写《Day-05 商品模块(mall-product) 完整规划文档》
选 **A→B**：先出 B 文档，做完再补 A

（本文档不建大目录，作为决策参考放在 daily 下。）
