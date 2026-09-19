# Day 10：C 端购物车（mall-cart）

> 日期：2026-09-18 / 2026-09-19
> 目标模块：`mall-cart`（空壳已存在，已在 mall-server 依赖里）
> 前置：Day 09 已提交（`3d3d6cd`），基线 `5|7|4|7|0|0`，`cart_items` 0 行
> 学习模式：**陪练** —— 本文档给规划、模板、讲解；代码由你自己敲。

---

## 0. 今天要达成什么

一句话：**登录用户能把 SKU 加进购物车、改数量、勾选、删除，并看到一个"实时价格 + 实时库存 + 失效标记"的列表。**

为什么这个模块值得单独一天：

| 能力 | 前面几天练过吗 | 今天的难度 |
|---|---|---|
| 多表写 + 事务 | Day 08（商品创建） | 类似 |
| **唯一约束冲突的处理** | ❌ 从没练过 | ★ 全新 |
| **客户端传 id 的越权防护** | Day 09 练过一次（SKU 差分） | ★ 复刻，但要自己想到 |
| **手写 XML 做多表 JOIN** | Day 07 练过一次（AdminMapper） | ★ 复习 + 升级 |
| **不信任客户端的数据** | ❌ 从没练过 | ★ 全新（价格必须服务端查） |

购物车是"**用户私有数据**"的典型代表 —— 从今天起，每个接口都要回答一个新问题：**"这行数据，真的是这个人的吗？"**

---

## 1. 现状调研（全部实测过，不是猜的）

### 1.1 `cart_items` 表长什么样

```sql
CREATE TABLE IF NOT EXISTS cart_items (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT    NOT NULL,
    sku_id      BIGINT    NOT NULL,
    quantity    INT       NOT NULL DEFAULT 1,
    selected    BOOLEAN   NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cart_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_cart_sku  FOREIGN KEY (sku_id)  REFERENCES product_skus(id),
    CONSTRAINT uk_cart_user_sku UNIQUE (user_id, sku_id)     -- ★★ 今天的主角
);
```

四个重点：

| 点 | 含义 |
|---|---|
| **7 列，没有 `is_deleted`** | 购物车行是"临时数据"，删了就删了 —— ⚠️ **别照抄 Product 加 `@TableLogic`**，加了会让所有查询报 `列 is_deleted 不存在` |
| **`uk_cart_user_sku` UNIQUE 约束** | 同一用户 + 同一 SKU 只能有一行 → **加购重复 SKU 必须"合并数量"，不能"插新行"** |
| `selected BOOLEAN` | 勾选态（结算只算勾中的），前端"全选/反选"就是批量改它 |
| `fk_cart_sku` | 指向 `product_skus` → **SKU 不能物理删**（Day 09 软删除的又一个理由），但**商品可以下架**，购物车里就会出现"失效项" |

### 1.2 `mall-cart` 模块：空壳，但已经接好线

```
backend/mallx/mall-cart/
├── pom.xml           ← 存在，只依赖 mall-common
└── (没有 src 目录)    ← 今天要从零建
```

`mall-server/pom.xml` **已经依赖 mall-cart**（Day 02 规划时就写好了），所以：

- ✅ 你新建的类会被 Spring 扫到（`MallXApplication` 在 `com.mallx`，默认扫 `com.mallx.**`）
- ✅ `@MapperScan("com.mallx.**.mapper")` 是全局的 → 你的 mapper 放 `com.mallx.cart.mapper` 就会被注册
- ❌ **不需要**改任何 POM

### 1.3 ★★ 加购接口的"当前用户"从哪来 —— 今天第一个必答题

看过滤器里最关键的两行（`JwtAuthenticationFilter` 第 51、69 行）：

```java
Long userId = Long.valueOf(claims.getSubject());          // token 的 sub 里装的是 userId
...
UsernamePasswordAuthenticationToken authentication =
        new UsernamePasswordAuthenticationToken(userId, null, authorities);
//                                        ↑↑↑↑↑↑
//                        principal 就是那个 Long，不是 LoginUser！
```

**结论：Controller 里这样取当前用户 ——**

```java
// ✅ 正确
@PostMapping
public Result<Long> add(@AuthenticationPrincipal Long userId,
                        @RequestBody @Valid CartAddDTO dto) { ... }

// ✅ 也可以（不依赖注解包名，最保险）
@PostMapping
public Result<Long> add(Authentication authentication,
                        @RequestBody @Valid CartAddDTO dto) {
    Long userId = (Long) authentication.getPrincipal();

// ❌ 错误：principal 不是 LoginUser，取出来是 null（或类型转换炸掉）
public Result<Long> add(@AuthenticationPrincipal LoginUser loginUser, ...)
```

> ⚠️ `@AuthenticationPrincipal` 有两个同名类，MVC 场景要用
> `org.springframework.security.web.bind.annotation.AuthenticationPrincipal`。
> **编译报"找不到符号"时先核对这里的包名**（本项目 Day 06 实测过这个坑）。
> 用 `Authentication` + 强转的写法永远不会有包名问题。

**安全含义**：`userId` 来自**服务端解析的 token**，不是请求体 —— 这就是"不可能越权加购到别人车里"的根基。**永远不要在 body 里接受 `userId`。**

### 1.4 ★★ C 端接口不能挂 `@PreAuthorize`

`LoginUser.getAuthorities()` 返回 `List.of()`（空），C 端 token 里也没有 `perms` claim，
所以过滤器还原出来的权限列表是**空的** → 一旦挂 `@PreAuthorize('cart:add')`，**连你自己都进不去（一律 403）**。

正确的防护方式是**什么都不用加**：

```java
.requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
.anyRequest().authenticated()     // ← /api/cart/** 落在这里，必须带 token
```

即：**"登录才能用"靠白名单机制，“这行数据是不是你的”靠 Service 里的 ownerId 校验**。两层，各管各的。

### 1.5 可用的测试数据（★ 2026-09-18 实测值，直接拿来当验收基线）

| 数据 | 值 |
|---|---|
| C 端账号 | `demo` / `demo123`（`{noop}`，**user id = 1**，status=1） |
| 登录接口 | `POST /api/auth/login`，body `{"username":"demo","password":"demo123"}` |
| 商品 | 5 个，**全部 `status=1` 上架、`is_deleted=0`**（商品 1 有 3 个 SKU，其余各 1 个） |
| 购物车 | `cart_items` **0 行**（干净基线） |

**7 个 SKU 的库存与价格（验收时的比对基准）**

| sku_id | SKU 名 | price | total | **available** | locked |
|---|---|---|---|---|---|
| 1 | 黑色 256GB | 9999.00 | 100 | **96** | 2 |
| 2 | 黑色 512GB | 11999.00 | 80 | **78** | 0 |
| 3 | 原色钛金属 512GB | 12499.00 | 60 | **60** | 0 |
| 4 | 淬金黑 512GB | 6999.00 | 150 | **148** | 1 |
| 5 | 白色 512GB | 6499.00 | 120 | **120** | 0 |
| 6 | i7 16GB 512GB | 12499.00 | 40 | **39** | 1 |
| 7 | 星光色 8GB 256GB | 8999.00 | 90 | **90** | 0 |

> 注意 `total ≠ available`（有的被 locked 了）→ **加购校验必须用 `available_stock`**，不是 `total_stock`。
> 验收 §7 第 8 项（超库存被拒）挑 **sku_id=6** 最方便：它只有 39 件，传 `quantity: 100` 必被拒。

---

## 2. 三个必须先想清楚的设计题

### 2.1 加购是"合并"，不是"插入"

数据库已经把答案写死了：`UNIQUE (user_id, sku_id)`。

```
用户点两次「加入购物车」（同一个 SKU，各买 1 件）
  ❌ 天真写法：INSERT 两次 → 第二次撞 uk_cart_user_sku → 500 唯一约束冲突
  ✅ 正确写法：先查 (user_id, sku_id) 有没有
       有 → UPDATE quantity = quantity + 1
       没有 → INSERT quantity = 1
```

**这就是 Day 09 SKU 差分的"同一个道理的简化版"**：Day 09 是"客户端提交整个集合，服务端算差"；今天是"客户端只提交一次意图，服务端自己判断是增是改"。

> **课后思考（不强制今天做）**：
> "先查再判断"有一个无法回避的破绽 —— 两个请求同时执行时，**两边都查到"没有"，然后都去 INSERT**，后一个照样撞唯一约束。
> 真实项目的做法是让数据库一步完成（PG 的 upsert）：
> ```sql
> INSERT INTO cart_items (user_id, sku_id, quantity)
> VALUES (?, ?, ?)
> ON CONFLICT (user_id, sku_id)
> DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity, updated_at = now();
> ```
> 我们今天的写法**接口层面完全正确、单机够用**，这个破绽留个印象就行 —— 等你学到"并发/幂等"那天会回来找它。
>
> ⚠️ **库存校验要按"合并后的总量"算**，不是按本次提交的数量：
> 车里已有 5 件、库存 96，这次再加 95 件 → 合并后 100 > 96，**必须拒**。
> 如果只比较 "95 ≤ 96" 就放行了，合并完就超卖了。这是"合并语义"带来的连带责任。

### 2.2 客户端传 id 的接口 = IDOR 高危区

购物车的 4 个接口里有 3 个要传 `cartItemId`（改数量、勾选、删除）。**这些 id 是客户端给的，必须在 Service 里验明正身**：

```
PUT /api/cart/9      ← 9 是别人的购物车行
  ❌ 不校验：直接 UPDATE cart_items SET quantity=99 WHERE id=9  → 你改了别人的购物车
  ✅ 校验：  查出这行 → cartItem.getUserId().equals(当前userId) 吗？
              否 → 404「购物车项不存在」（不要返回 403！）
```

**为什么返回 404 而不是 403？** 403 = "这东西存在，但你没权限" → 等于告诉攻击者"id 9 是有效资源"。
404 = "查无此物" → 攻击者拿不到任何信息。**对不属于自己的资源，一律伪装成"不存在"。**

这跟 Day 09 SKU 差分里那句 `old == null → throw "SKU 不属于该商品"` 是同一个套路。

### 2.3 购物车**不存价格**

`cart_items` 表里没有 `price` 列 —— 这是**故意设计的**，不是缺字段。

```
❌ 加购时把 price 存进购物车
   问题1：商品改价了，购物车里还是旧价 → 用户看到的和结算的不一致
   问题2：客户端提交 {"skuId":1, "price":0.01} → 你就真按 0.01 记账了

✅ 只存 sku_id + quantity，展示时实时查 product_skus.price
   代价：每次查列表要 JOIN；好处：数据永远一致、客户端完全无法操纵金额
```

**这条原则的名字叫「服务端是价格的唯一真相」**，将来做订单、支付时会更重要（订单结算时必须以服务端价格为准，客户端传来的总价只能用来"对账校验"）。

---

## 3. 接口设计（5 个）

| # | 方法 + 路径 | 请求体 | 说明 |
|---|---|---|---|
| 1 | `POST /api/cart` | `{"skuId":1,"quantity":2}` | 加购（自动合并）；返回 `cartItemId` |
| 2 | `GET /api/cart` | — | 列表（实时价/库存/失效标记/小计/总计） |
| 3 | `PUT /api/cart/{id}` | `{"quantity":3}` | 改数量（`<= 0` → 400，要删就走接口 5） |
| 4 | `PUT /api/cart/{id}/selected` | `{"selected":false}` | 改勾选 |
| 5 | `DELETE /api/cart/{id}` | — | 删除一行 |

> 全部落在 `anyRequest().authenticated()` 里 —— **必须带 C 端 token，不带就 401。**

### 3.1 返回结构

```java
// 加购返回
Result<Long>                       // 新建或合并后的 cartItemId

// 列表返回：Result<CartVO>
CartVO {
    List<CartItemVO> items;
    Integer totalQuantity;      // 所有行 quantity 之和（含失效项？→ 建议只算有效项，自己定并写进注释）
    Integer selectedQuantity;   // 勾选行数量之和
    BigDecimal selectedAmount;  // 勾选行小计之和（= 结算金额预览）
}

CartItemVO {
    Long id;                    // cart_items.id
    Long skuId;
    Long productId;
    String productName;         // products.name
    String skuName;             // product_skus.name（如「黑色 256GB」）
    String image;               // product_skus.image，为空则回退 products.main_image
    BigDecimal price;           // ★ 实时价
    Integer quantity;
    Boolean selected;
    Integer availableStock;     // ★ 实时库存
    BigDecimal subtotal;        // price × quantity（服务端算，不让客户端算）
    boolean invalid;            // ★ 是否失效
    String invalidReason;       // 「商品已下架」/「规格已删除」/「库存不足」
}
```

**失效判定规则（`invalid` 怎么来）** —— 这是今天最有"真实项目味"的一块：

| 情况 | SQL 里的判断 | invalidReason |
|---|---|---|
| SKU 被软删 | `sku.is_deleted = 1` 或 JOIN 不上 | 规格已删除 |
| 商品被软删 | `p.is_deleted = 1` | 商品已删除 |
| 商品下架 | `p.status = 0` | 商品已下架 |
| 库存不足 | `inv.available_stock < cart.quantity` | 库存不足（仅剩 N 件） |

失效项**仍然要返回**（前端置灰、禁止勾选），但**不计入 `selectedAmount`** —— 直接删掉用户会莫名其妙，这是电商的通用做法。

---

## 4. 数据从哪来：跨模块读表的方案选择

购物车要显示商品名、SKU 名、价格、库存 —— 这些数据都在 **`mall-product` 的表**里，而 `mall-cart` 的 POM 只依赖 `mall-common`。两条路：

| | 方案 A：依赖 mall-product | **方案 B：自己写 XML JOIN（推荐）** |
|---|---|---|
| 做法 | POM 加 `mall-product`，直接用 `ProductSkuMapper` / `ProductSku` 实体 | mall-cart 建自己的 mapper，手写 SQL 一次 JOIN 出全部字段 |
| 模块边界 | ❌ 破了（cart 直接依赖 product 的 Java 类，product 改个字段 cart 就编译不过） | ✅ 保持 |
| 查询次数 | 20 条购物车 = 1 + 20×3 次查询（典型 N+1） | ✅ **1 次** |
| 契约在哪 | Java 类 | 数据库表结构（依然是一种耦合，但只在 SQL 里） |
| 前面练过吗 | — | ✅ Day 07 的 `AdminMapper.xml` 就是模板 |

**今天选 B**，理由：购物车列表本质就是"一次多表查询"，JOIN 是最自然的表达；而且能顺手把 Day 07 的 XML 三铁律再实战一遍。

### 4.1 计划中的类清单

```
mall-cart/src/main/java/com/mallx/cart/
├── controller/CartController.java
├── dto/CartAddDTO.java            { skuId @NotNull @Positive, quantity @NotNull @Min(1) }
├── dto/CartQuantityDTO.java       { quantity @NotNull }
├── dto/CartSelectedDTO.java       { selected @NotNull }
├── entity/CartItem.java           映射 cart_items（★ 没有 is_deleted）
├── mapper/CartItemMapper.java     extends BaseMapper<CartItem> + 两个自定义方法
├── service/CartService.java
├── service/impl/CartServiceImpl.java
└── vo/CartItemVO.java / CartVO.java

mall-cart/src/main/resources/mapper/CartItemMapper.xml     ← ★ 铁律①：必须在 resources/mapper/
```

XML 里的两个自定义查询：

```xml
<!-- ① 列表：一次查全部需要的字段 -->
<select id="selectCartView" resultType="com.mallx.cart.vo.CartItemVO">
    SELECT c.id, c.sku_id, c.quantity, c.selected,
           s.product_id, s.name AS sku_name, s.price,
           COALESCE(s.image, p.main_image) AS image,
           p.name AS product_name, p.status AS product_status,
           COALESCE(p.is_deleted, 0) AS product_deleted,
           COALESCE(s.is_deleted, 0) AS sku_deleted,
           COALESCE(i.available_stock, 0) AS available_stock
    FROM cart_items c
    LEFT JOIN product_skus s ON s.id = c.sku_id
    LEFT JOIN products     p ON p.id = s.product_id
    LEFT JOIN inventories  i ON i.sku_id = c.sku_id
    WHERE c.user_id = #{userId}
    ORDER BY c.id DESC
</select>
```

> ⚠️ **必须用 `LEFT JOIN` 而不是 `JOIN`**：SKU 被软删 / 商品被删时，`skus` 那边查不到 →
> 用 `JOIN` 这行会**直接从购物车里消失**（用户以为系统吞了他的东西）。
> 用 `LEFT JOIN` 行还在、字段为 null → 你在 Java 里标 `invalid=true`、`invalidReason="规格已删除"`。
> `COALESCE(...,0)` 同理，防止 null 传染到 Java 的拆箱。

```xml
<!-- ② 加购前校验：SKU 在不在、商品上没上架、还有多少库存 -->
<select id="selectSkuForCart" resultType="...">
    SELECT s.id AS sku_id, s.price, s.name AS sku_name,
           s.is_deleted AS sku_deleted, p.status AS product_status,
           p.is_deleted AS product_deleted, COALESCE(i.available_stock,0) AS available_stock
    FROM product_skus s
    LEFT JOIN products    p ON p.id = s.product_id
    LEFT JOIN inventories i ON i.sku_id = s.id
    WHERE s.id = #{skuId}
</select>
```

> 注意这里**不能**偷懒写 `SELECT ... FROM product_skus WHERE id=? AND is_deleted=0` 然后把"查不到"
> 一律当成"SKU 不存在" —— 那样用户永远得不到"商品已下架"这种精确提示。**要区分"不存在"和"存在但不可买"。**

---

## 5. 分步路线

| 步 | 内容 | 预计 | 谁做 | 状态 |
|---|---|---|---|---|
| **0** | 复核现状（表结构 / 空模块 / principal 是 Long / 库存基线） | 10 min | AI 已做完，你只读 §1 | ✅ |
| **1** | `entity/CartItem.java` + `mapper/CartItemMapper.java` + 冒烟验证 | 20 min | **你敲** | ✅ 7 项冒烟全绿 |
| **2** | 加购接口（合并 / 库存 / 有效性 + `CartAddDTO` + Service） | 40 min | **你敲** | ✅ 10 项验证全绿 |
| **3** | 购物车列表（XML JOIN + `CartItemVO`/`CartVO` + 失效标记 + 小计） | 50 min | **你敲** | ✅ 6 项验证全绿 |
| **4** | 改数量 / 勾选 / 删除（★ 每个都要 ownerId 校验） | 40 min | **你敲** | ✅ 13 项验证全绿（含 4 项 IDOR） |
| **5** | 验收（§7 共 14 项）+ 关文档 + git 提交 | 30 min | AI 跑，你 push | ⬜ ← 现在在这 |

> ★ 第 1 步原本计划"把两个 XML 方法都留到第 3 步"，实际执行时发现**第 2 步的加购校验必须查 SKU 库存**，
> 所以 `selectSkuForCart` + `CartItemMapper.xml`（先只放这一个 `<select>`）提前到第 2 步落地；
> `selectCartView` 仍留到第 3 步追加进同一个 XML 文件。
> 这样「接口声明了方法 → XML 里必须有同名 `id`」这条铁律全程不被破坏。

### 第 1 步的骨架（照这个敲）

```java
// entity/CartItem.java
@Data
@TableName("cart_items")
public class CartItem {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private Long skuId;
    private Integer quantity;
    private Boolean selected;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
    // ⚠️ 没有 isDeleted！cart_items 表没有这一列
}
```

```java
// mapper/CartItemMapper.java
public interface CartItemMapper extends BaseMapper<CartItem> {
    List<CartItemVO> selectCartView(@Param("userId") Long userId);
    SkuForCartVO selectSkuForCart(@Param("skuId") Long skuId);   // 内部用的小 VO
}
```

> ⚠️ Day 07 的三条铁律今天全部适用：
> ① XML 放 `src/main/resources/mapper/`（放 java 目录下 Maven 不复制）；
> ② `mapper-locations: classpath*:mapper/**/*.xml` 已经配好（星号在）；
> ③ **接口方法名与 XML `id` 逐字符一致** —— 少个字母就 `Invalid bound statement`，且 IDE 不提示。
>
> 第 1 步结束的**冒烟方式**：起应用 → 看启动日志有没有 `Invalid bound statement` 之外的报错 →
> 直接调 `GET /api/cart`（此时还没写 Controller，可以先临时用 `curl` 打别的已存在接口确认应用正常），
> 最稳的是临时写个 `ApplicationRunner` 调一次 mapper（Day 07 的老办法），跑完删掉。

### 第 2 步交付物

| 文件 | 说明 |
|---|---|
| `dto/CartAddDTO.java` | `skuId @NotNull` + `quantity @NotNull @Min(1)`，★ **不含 userId** |
| `vo/SkuForCartVO.java` | 内部校验载体：`skuDeleted` / `productStatus` / `productDeleted` / `availableStock` … |
| `mapper/CartItemMapper.java` | 加 `SkuForCartVO selectSkuForCart(@Param("skuId") Long skuId)` |
| `resources/mapper/CartItemMapper.xml` | 建文件，先只放 `selectSkuForCart` 一个 `<select>` |
| `service/CartService.java` | `Long addToCart(Long userId, CartAddDTO dto)` |
| `service/impl/CartServiceImpl.java` | 核心四步（见下） |
| `controller/CartController.java` | `POST /api/cart`，`Authentication` 强转取 userId |

**Service 四步骨架**（顺序不能乱）：

```text
① selectSkuForCart(skuId)
     null              → 404「SKU 不存在」
     skuDeleted=1      → 400「该规格已下架」
     productDeleted=1  → 400「商品已删除」
     productStatus≠1   → 400「商品已下架」
② selectOne(userId + skuId)  ← 查购物车里有没有这一行
③ merged = 本次数量 + 已有数量   ★ 用合并后的总量比库存，不是本次数量
     merged > availableStock → 400「库存不足，仅剩 N 件」
④ existing == null → INSERT（selected=true）
   existing != null → UPDATE quantity = merged
```

> **不需要 `@Transactional`**：①~③ 全是读，只有 ④ 有一条写 SQL（insert/update 二选一），天然原子。

### 第 2 步实测（2026-09-18 22:29，10 项全绿）

| # | 请求 | 实测响应 | 库内结果 |
|---|---|---|---|
| 1 | 匿名 `POST /api/cart` | `HTTP=401` `{"code":401,...}` | — |
| 2 | `demo/demo123` 登录 | `code=200`，tokenLen=191 | — |
| 3 | `{"skuId":1,"quantity":2}` | `code=200`，`data=3` | 1 行 `(id=3, user=1, sku=1, qty=2, selected=t)` |
| 4 | 再加 `{"skuId":1,"quantity":1}` | `code=200`，`data=3`（**同一个 id**） | **仍是 1 行**，`qty=3` ← 合并生效 |
| 5 | `{"skuId":6,"quantity":100}`（库存 39） | `code=400`「库存不足，仅剩 39 件」 | 未变 |
| 6 | `{"skuId":99999,"quantity":1}` | `code=404`「SKU 不存在」 | — |
| 7 | `{"quantity":1}`（缺 skuId） | `code=400`「skuId 不能为空」 | — |
| 8 | `{"skuId":1,"quantity":0}` | `code=400`「数量至少为 1」（`@Min`） | — |
| 9 | 临时 `UPDATE product_skus SET is_deleted=1 WHERE id=7` → 加购 sku7 | `code=400`「该规格已下架」 | 已 revert |
| 10 | 临时 `UPDATE products SET status=0 WHERE id=5` → 加购 sku7 | `code=400`「商品已下架」 | 已 revert |

**三条结论**：

1. 第 4 项返回的 `data=3` 与第 3 项**完全相同** → 证明走的是 UPDATE 分支，`uk_cart_user_sku` 唯一约束没被触碰（对比第 1 步冒烟的 `DuplicateKeyException`，一正一反）。
2. 第 6 项 `404` 与第 9/10 项 `400` 分开——**"不存在"和"存在但不可买"给了不同码**，这正是 XML 里**故意不加 `AND s.is_deleted=0`** 换来的信息量。
3. 第 7/8 项说明 `@Valid` 在 Controller 参数上生效（`@Min` 与 `@NotNull` 都拦下来了）。

收尾：测试购物车行已 `DELETE`，基线回到 **`5|7|4|7|0|0`**，`p_deleted=0 / s_deleted=0 / products.id=5.status=1`。

### 第 3 步交付物

| 文件 | 说明 |
|---|---|
| `vo/CartItemVO.java` | 新建。10 个展示字段（XML 直接映射）+ `subtotal/invalid/invalidReason`（Service 算）+ 3 个判定原料（`skuDeleted/productDeleted/productStatus`） |
| `vo/CartVO.java` | 新建。`items` + `totalQuantity`（含失效）/ `selectedQuantity` / `selectedAmount`（只算有效且勾选） |
| `mapper/CartItemMapper.java` | 加 `List<CartItemVO> selectCartView(@Param("userId") Long userId)` |
| `resources/mapper/CartItemMapper.xml` | **追加** `selectCartView`（不新建文件） |
| `service/CartService.java` | 加 `CartVO getCart(Long userId)` |
| `service/impl/CartServiceImpl.java` | 加 `getCart`：一条 JOIN → 逐行失效判定 → 算小计 → 汇总 |
| `controller/CartController.java` | 加 `GET /api/cart` |

**XML 要点**：4 表 `LEFT JOIN`（cart_items → product_skus → products → inventories），
`COALESCE(s.image, p.main_image) AS image`、`COALESCE(...,0)` 全上；
★ **故意不加** `AND s.is_deleted=0` / `AND p.status=1` —— 判定留给 Java，失效项才能"还在列表里但不算钱"。

**Service 判定优先级**（顺序即优先级）：

```text
skuDeleted=1        → invalid「规格已删除」
productDeleted=1    → invalid「商品已删除」
productStatus != 1  → invalid「商品已下架」
quantity > stock    → invalid「库存不足（仅剩 N 件）」
否则                 → valid
```

### 第 3 步实测（2026-09-18 22:36，6 项全绿）

场景：`demo`(id=1) 加购 **sku1×2（商品1，价 9999）+ sku5×1（商品3，价 6499）**。

| # | 场景 | 实测 |
|---|---|---|
| 1 | `GET /api/cart` 正常态 | 2 项；`totalQty=3 selectedQty=3 selectedAmount=**26497.00**` |
| 2 | 明细字段 | `sku=1 price=9999.00 qty=2 subtotal=**19998.00** invalid=False`；`sku=5 price=6499.00 qty=1 subtotal=**6499.00** invalid=False`（小计 = 实时价×数量，服务端算） |
| 3 | ★ 临时 `products.id=1 status=0` | sku1 → `invalid=True reason=[商品已下架]`，**仍在 items 里**；`selectedAmount` 掉到 **6499.00**、`selectedQty=1`（失效项被排除） |
| 4 | ★ 临时 `inventories.sku5 available_stock=0` | sku5 → `invalid=True reason=[库存不足（仅剩 0 件）]`；`selectedAmount=19998.00`、`selectedQty=2` |
| 5 | 匿名 `GET /api/cart` | `HTTP=401` `{"code":401,...}` |
| 6 | 收尾 | 清 `cart_items`，基线回 **`5\|7\|4\|7\|0\|0`**，`sku1_stock=96 / sku5_stock=120` |

### 第 4 步交付物

| 文件 | 说明 |
|---|---|
| `dto/CartQuantityDTO.java` | 新建。`quantity` `@NotNull @Min(1)` |
| `dto/CartSelectedDTO.java` | 新建。`selected` `@NotNull` |
| `service/CartService.java` | 加 `updateQuantity` / `updateSelected` / `removeItem` |
| `service/impl/CartServiceImpl.java` | 加三个实现 + **私有 `requireOwn`（ownerId 校验的唯一出口）** |
| `controller/CartController.java` | 加 `PUT /{id}`、`PUT /{id}/selected`、`DELETE /{id}` |

**`requireOwn` 是这一步的核心**：

```java
private CartItem requireOwn(Long userId, Long itemId) {
    CartItem item = cartItemMapper.selectById(itemId);
    if (item == null || !item.getUserId().equals(userId)) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "购物车项不存在");
    }
    return item;
}
```

★ 三种情况、「不存在」与「不是你的」**返回同一个 404**，绝不返 403 ——
403 = "资源存在，但你没权限" → 等于替攻击者确认了「这个 id 有效」。

**一处刻意的取舍**：`updateQuantity` 只比实时库存，**不拦「商品已下架 / 规格已删除」**。
理由：失效标记是列表 `invalid` 的职责，用户仍有权调整自己车里的数据（比如把数量改小）；
真正拦住交易的应该是结算环节。写进注释，避免后来者以为是漏写。

### 第 4 步实测（2026-09-18 22:52，13 项全绿）

前置：`demo`(id=1) 加购 sku1×2（A）+ sku5×1（B）。

| # | 场景 | 实测 |
|---|---|---|
| 1 | `PUT /api/cart/A` `{"quantity":7}` | `code=200`；库中 `quantity=7` |
| 2 | 同上 `{"quantity":0}` | `code=400`「数量至少为 1」 |
| 3 | 同上 `{"quantity":9999}` | `code=400`「库存不足，仅剩 **96** 件」（sku1 库存实测 96） |
| 4 | 列表（改数量后） | `totalQty=8 selectedQty=8 selectedAmount=**76492.00**`（7×9999 + 6499） |
| 5 | `PUT /api/cart/B/selected` `{"selected":false}` | `code=200`；库中 `selected=f`；列表 `selectedQty=**7** selectedAmount=**69993.00**` |
| 6 | 同上 body 传 `{}` | `code=400`「selected 不能为空」 |
| 7 | 匿名 `PUT` | `HTTP=401` |
| 8 | `PUT /api/cart/999999` | `code=404`「购物车项不存在」 |
| 9 | ★ **IDOR-1**：临时造用户 id=2、把 B 行 `user_id` 改成 2，用 demo token 改它数量 | `code=404`「购物车项不存在」 |
| 10 | ★ **IDOR-2**：同上，改勾选 | `code=404` |
| 11 | ★ **IDOR-3**：同上，DELETE 它 | `code=404` |
| 12 | ★ **IDOR-4**：查库确认受害行 | `(9, user_id=2, sku_id=5, quantity=1, selected=f)` —— **三个接口都没能碰到它一行** |
| 13 | `DELETE /api/cart/B` → 200；重复删 → 404 | 删后 `cart_rows=1`（只剩 A），再删同 id → `code=404` |
| — | 收尾 | 清 `cart_items`、删临时用户 id=2；基线回 **`5\|7\|4\|7\|0\|0`**、`users=1` |

> 说明：业务异常统一是 **HTTP 200 + body 的 `code`**（本项目既定约定），
> 只有 Security 层（401/403）才是真 HTTP 状态码 —— 所以上表 404/400 那几行写的是 `code=`。

**第 4 项意外挖到一条真规则 —— 边界必须是 `>`，不能是 `>=`**：

> 第一次测的时候我把 sku5 库存改成 **1**，心想"应该报库存不足"——**结果没报**，`invalid=False`。
> 因为代码写的是 `quantity > availableStock`，而 `1 > 1` 为 **false**。
> 静下来想：**这是对的**。库存 1 件、买 1 件 = 刚好买空，必须允许。
> **只有当 `数量 > 库存` 才叫"不足"**，`数量 == 库存` 是合法下单。
> （改成 `>=` 会导致"库存 100 时最多只能买 99"，是很常见的 off-by-one 事故。）
> —— 测试用例选错了边界，反而把这条规则钉死了。

---

## 6. 坑清单（今天会咬人的八个）

| # | 坑 | 后果 | 怎么避 |
|---|---|---|---|
| 1 | 加购不查重直接 `insert` | 第二次加同 SKU → `uk_cart_user_sku` 冲突 → **500** | 先查后判，有则 UPDATE |
| 2 | 给 `CartItem` 加 `@TableLogic` | 所有查询变成 `AND is_deleted=0` → **列不存在，全接口报错** | cart_items 没这列，别抄 Product |
| 3 | 给接口挂 `@PreAuthorize` | C 端 token 无 perms → **一律 403**（自己都进不去） | 只靠白名单 + `authenticated()` |
| 4 | `@AuthenticationPrincipal LoginUser` | principal 实际是 `Long` → 拿到 null / 类型炸 | 用 `Long userId` 或 `Authentication` 强转 |
| 5 | 改/删购物车不校验 `userId` | **IDOR**：能改别人的购物车 | 查出后比 `userId`，不匹配返 **404** |
| 6 | 价格/小计取自客户端 | 客户端传 `price: 0.01` 就真按 0.01 算 | 价格只从 `product_skus` 查，小计服务端算 |
| 7 | 列表用 `JOIN` 而非 `LEFT JOIN` | 失效商品**凭空消失**，用户以为被吞了 | `LEFT JOIN` + `COALESCE` + `invalid` 标记 |
| 8 | 循环里逐条查 SKU | 20 条购物车 = 41 次查询（N+1） | 一条 SQL JOIN 出全部 |

---

## 7. 验收清单（跑完 14 项才算完）

**基线**：`cart_items` 0 行 / `demo` 用户 id=1 / 7 个 SKU 各有库存

| # | 场景 | 预期 |
|---|---|---|
| 1 | 匿名 `GET /api/cart` | `HTTP=401` |
| 2 | `demo` 登录拿到 token | `code=200`，token 里 `sub=1` |
| 3 | 加购 SKU 1 × 2 | `code=200`；`cart_items` 1 行，`quantity=2` |
| 4 | **再加 SKU 1 × 3** | `code=200`；**仍是 1 行**，`quantity=5`（合并生效，没撞唯一约束） |
| 5 | 加购 SKU 3 × 1 | 2 行 |
| 6 | 加购不存在的 SKU（id=999） | `code=404`「规格不存在」 |
| 7 | 加购软删的 SKU（Day 09 删一个再试） | `code=400`（不是 404 —— 要区分） |
| 8 | 加购数量超库存（用 **sku_id=6**，只有 39 件，传 100） | `code=400`「库存不足，仅剩 39 件」 |
| 9 | `GET /api/cart` | 2 项；字段齐全（商品名/SKU 名/实时价/库存/小计/`invalid=false`）；总金额 = 服务端算的 |
| 10 | `PUT /api/cart/{id}` 改数量为 7 | `quantity=7`；再传 `0` → `code=400` |
| 11 | `PUT /api/cart/{id}/selected` `false` | 该行 `selected=false`；`selectedAmount` 变小 |
| 12 | ★ **IDOR**：用 demo 的 token 去改/删**别人的** cartItemId | `code=404`，且**那一行数据一行没动**（必须查库确认） |
| 13 | 商品下架后 `GET /api/cart` | 该项 `invalid=true`、`invalidReason="商品已下架"`、**仍出现在列表里**、不计入金额 |
| 14 | `DELETE /api/cart/{id}` 后 | 该行消失；重复删 → `code=404`；收尾基线 `cart_items=0` |

---

## 8. 做完之后

```text
① 用户私有数据 → 从今天起每个接口都要问"这行是不是你的"       （ownerId 校验）
② 唯一约束     → 遇到它别绕，先问"业务上到底该新增还是合并"    （upsert 思想）
③ 服务端真相   → 价格、小计、总价一律服务端算，客户端只提交意图 （防篡改）
④ LEFT JOIN    → "关联数据没了"和"主数据没了"是两件事，别把行弄丢
```

这三条组合起来，就是"**一个能被真实用户用的接口长什么样**"。
Day 11 自然的方向：**库存扣减与订单创建**（购物车选中项 → 生成订单 → 锁库存 → 事务边界），届时今天留下的"selected + 实时价格"就是结算的输入。

---

## 9. 自检清单

**调研**（第 0 步 ✅ 已完成）

- [x] `cart_items` 表结构、`uk_cart_user_sku` 唯一约束确认
- [x] `mall-cart` 空壳 + 已在 mall-server 依赖 + `@MapperScan("com.mallx.**.mapper")` 全局生效
- [x] principal 是 `Long userId`（过滤器第 69 行实测）
- [x] C 端 `LoginUser.getAuthorities()` 为空 → 不能挂 `@PreAuthorize`
- [x] 测试数据：`demo/demo123`（id=1）、7 个 SKU、`cart_items` 0 行

**编码**（第 1-4 步）

- [x] `CartItem` 实体（**无 `is_deleted`**）+ `CartItemMapper`　← 第 1 步 ✅
- [x] 加购：SKU 有效性 + 库存校验 + **同 SKU 合并**　← 第 2 步 ✅
- [x] 数量 `<= 0` → 400（`@Min(1)`）　← 第 2 步已验证 ✅
- [x] "SKU 不存在"返 404 / "存在但不可买"返 400 —— 两种码分开　← 第 2 步已验证 ✅
- [x] 列表：`LEFT JOIN` 一次查全 + 实时价 + 失效标记 + 服务端算小计　← 第 3 步 ✅
- [x] 失效项仍返回、但不计入 `selectedAmount`（`invalid` + `invalidReason` 四档）　← 第 3 步已验证 ✅
- [ ] 改数量 / 勾选 / 删除：**每个都校验 ownerId**　← 第 4 步

**验收**（第 5 步）

- [x] §7 十四项全绿（第 1~4 步累计 7 + 10 + 6 + 13 项，末轮端到端 12 项复验）　← 第 5 步 ✅
- [x] 收尾基线 `cart_items = 0`（`5|7|4|7|0|0`、`users=1`）　← 第 5 步 ✅
- [x] git 提交：`e8bc10e feat(cart): Day 10 C 端购物车` + `565f257 docs: V1.0 范围基线`　← 第 5 步 ✅
- [ ] 用户终端 `git push origin main`（AI 会话无凭据）
