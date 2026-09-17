# Day 08：商品多表写 + `@Transactional` 事务

> 项目：MallX 企业级电商系统
> 前置：Day 07 完成 —— 商品三个写接口 + RBAC 方法级鉴权；八项验收全绿；提交 `e09723f`
> 本日主题：**让"新建商品"从"只写 1 张表"升级为"写 3 张表"，并保证要么全成功、要么全不生效**
> 状态：**规划文档**（照着做，卡点看第 8 章）

---

## 0. 今日目标

| 维度 | 内容 |
|---|---|
| **一句话** | 新建商品时，商品主表 + N 个 SKU + M 张图集**一个事务写入** |
| **新概念** | `@Transactional`、事务边界、AOP 代理、回滚规则、`TypeHandler`（PG 的 JSONB 映射） |
| **改动量** | 新增 2 个类、改 5 个文件，**不动** `SecurityConfig` / JWT / RBAC |
| **难度** | ★★☆（概念是关键，代码量不大） |
| **验收** | 9 项，其中第 5、6 项是**亲手把事务打回滚**，这是今天最值钱的两步 |

### 为什么是今天这件事

Day 07 结束时，`GET /api/products/{id}` 这个详情接口**已经在读 SKU 和图集了**：

```java
// ProductServiceImpl.getDetail() 第 158–172 行（Day 05 就写好了）
List<ProductSku> skus = productSkuMapper.selectList(...);
vo.setSkus(skuVos);
List<ProductImage> images = productImageMapper.selectList(...);
vo.setImages(images.stream().map(ProductImage::getImageUrl).toList());
```

但是 `product_skus` 和 `product_images` 这两张表，**至今没有任何写接口** —— 库里那 7 行 SKU / 4 张图全是种子 SQL 手工插进去的静态数据。

> 也就是说：**商品模块现在是"半开"的** —— 能读 SKU，却没有任何办法造出一个带 SKU 的商品。
> 详情接口返回的 `skus` 永远是空数组，这不是 bug，是还没做。

今天就是把这个缺口补上。而且**接口路径一个字都不用改**（还是 `POST /api/products`），只是请求体能带更多东西 —— 这叫"接口不变、能力升级"。

---

## 1. 今日思路

### 1.1 为什么"多表写"必须用事务

先看一个你每天都在用的场景 —— **转账**：

```text
A 扣 100 元     ← 第 1 步成功
       ↓
B 加 100 元     ← 第 2 步失败（断电/网络/报错）
结果：100 元凭空消失
```

数据库里同样的场景：

```text
INSERT products       ← 成功（商品有了）
       ↓
INSERT product_skus   ← 第 2 个 SKU 的 sku_code 撞了唯一约束，失败
结果：库里留下一个"没有任何 SKU 的商品"   ← 孤儿数据
```

**事务（Transaction）就是解决这个的**：把这几个操作打包成一个"要么全做、要么全不做"的整体。

```text
BEGIN
  INSERT products         ✅
  INSERT product_skus #1  ✅
  INSERT product_skus #2  ❌ 报错
ROLLBACK   ← 前面两条插入一起撤销，数据库回到 BEGIN 之前的状态
```

> **一句话记住事务的四个字**：**全有或全无**（All or Nothing）。
> 它保证的不是"不出错"，而是"**出错时不留半成品**"。

### 1.2 今天要碰的三张表

```text
                    ┌──────────────────┐
                    │    products      │  ← 商品（SPU）
                    │  id, name, ...   │
                    └────────┬─────────┘
                             │ 1 : N
              ┌──────────────┴──────────────┐
              ▼                             ▼
    ┌──────────────────┐          ┌──────────────────┐
    │  product_skus    │          │ product_images   │
    │  规格/价格/库存前  │          │  图集（只存 URL） │
    │  sku_code 唯一    │          │  sort_order 排序  │
    └──────────────────┘          └──────────────────┘
```

关键约束（Day 03 建表时就定好了，今天正好用上）：

```sql
-- product_skus
sku_code  VARCHAR(100) NOT NULL UNIQUE    ← ★ 今天"制造失败"就靠它
product_id BIGINT NOT NULL REFERENCES products(id)

-- product_images
image_url VARCHAR(500) NOT NULL
product_id BIGINT NOT NULL REFERENCES products(id)
```

一套 SKU 的典型样子（注意 `attributes` 是 **JSONB**，不是文本）：

| id | product_id | sku_code | price | attributes |
|---|---|---|---|---|
| 1 | 6 | IP15-BLK-128 | 5999.00 | `{"color":"黑","storage":"128G"}` |
| 2 | 6 | IP15-WHT-256 | 6999.00 | `{"color":"白","storage":"256G"}` |

### 1.3 谁在"申请"这个事务（今天的架构图）

```text
  客户端
    │  POST /api/products   { 商品字段 + skus:[...] + images:[...] }
    ▼
┌──────────────────────────────────────────────────────┐
│ ProductController                                    │
│   @PreAuthorize("hasAuthority('product:create')")    │  ← Day 07 的权限门，今天不动
└────────────────────────┬─────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────┐
│ ProductServiceImpl.createProduct()                   │
│   @Transactional   ◄── ★ 今天唯一的"新武器"          │
│                                                      │
│   ┌── 一个数据库连接、一个事务 ──────────────────┐   │
│   │  1. 校验分类存在            （SELECT）        │   │
│   │  2. INSERT products                          │   │
│   │  3. INSERT product_skus  × N  （用新商品 id） │   │
│   │  4. INSERT product_images × M                │   │
│   └──────────────────────────────────────────────┘   │
│        任一步抛异常 → 整块 ROLLBACK                  │
└──────────────────────────────────────────────────────┘
                         ▼
                三张表同时生效 / 同时不生效
```

### 1.4 今天要新增/改动的文件一览

| # | 文件 | 动作 | 说明 |
|---|---|---|---|
| 1 | `mall-product/.../dto/SkuCreateDTO.java` | **新建** | 一个 SKU 的输入形态 |
| 2 | `mall-product/.../dto/ProductCreateDTO.java` | 改 | 加 `List<SkuCreateDTO> skus` + `List<String> images` |
| 3 | `mall-product/.../handler/JsonbMapTypeHandler.java` | **新建** | ★ PG 的 JSONB 必须靠它才能写进去（见第 4 步） |
| 4 | `mall-product/.../entity/ProductSku.java` | 改 | `attributes` 改类型 + `autoResultMap = true` + 指定 handler |
| 5 | `mall-product/.../vo/SkuVO.java` | 改 | `attributes` 跟着改成 `Map<String,Object>`（**必须同步，否则静默丢数据**） |
| 6 | `mall-product/.../service/impl/ProductServiceImpl.java` | 改 | `createProduct` 加 `@Transactional` + 写三张表 |
| 7 | `ProductController.java` / `ProductService.java` | **不用改** | 接口签名不变（`Long createProduct(ProductCreateDTO)`） |

> 注意第 4、5 条的关系：实体和 VO 的字段类型**必须一起改**。
> 只改一边的话，`BeanUtils.copyProperties` 遇到类型不匹配会**静默跳过**这个字段 ——
> 详情接口的 `attributes` 会变成 `null`，而且**不报任何错**。

---

## 2. 第 0 步：前置检查（15 分钟）

### 2.1 起环境

```powershell
# 1) Docker Desktop 要运行，容器 healthy（本项目 5434 → 容器 5432）
Test-NetConnection 127.0.0.1 -Port 5434

# 2) 应用（必须显式指定端口，本机 SERVER__PORT 环境变量有污染）
Set-Location D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o spring-boot:run -pl mall-server "-Dspring-boot.run.arguments=--server.port=8080"
```

> ⚠️ 本机三个已踩过的坑，别重踩：
> ① Docker 掉了要用 `& explorer.exe "…\Docker Desktop.exe"` 启动，**而且常常要拉两次**；
> ② `install` 覆盖 jar 后**必须先把旧进程杀掉**（Maven 父进程 + fork 出的 java 子进程），否则会看到"改了没生效"；
> ③ PG 刚起来时 Hikari 连接池**第一个请求可能握手失败**，重试一次就好，别误判成代码坏了。

### 2.2 记下改动前的基线（★ 今天回滚验证要靠它）

```powershell
$dx = "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
$sql = "SELECT (SELECT count(*) FROM products) AS products, (SELECT count(*) FROM product_skus) AS skus, (SELECT count(*) FROM product_images) AS images;"
& $dx exec -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx -c $sql
```

**今天开工前的实测值**（2026-09-17 16:50 实查，全部来自种子 SQL）：

| products | product_skus | product_images |
|---|---|---|
| 6 | 7 | 4 |

> `products = 6` 里的第 6 行（id=7 `落库验证商品`）是 Day 07 验收时**留下的测试残留**，已清理；
> 清理后基线回到 **products=5 / product_skus=7 / product_images=4**。

⚠️ **别用 `pg_stat_user_tables.n_live_tup` 当基线** —— 它是**估算值、会滞后**，刚才查它
`product_skus` / `product_images` 都显示 0，而真实 `count(*)` 是 7 和 4。
**基线必须用 `count(*)` 实查**，否则第 6 章的回滚比对会得出完全错误的结论。

做完今天，这两张表会**第一次由接口写入数据**：`product_skus` 7 → 9、`product_images` 4 → 6（以验收脚本建 2 SKU + 2 图为例）。

### 2.3 确认依赖已经就绪（不用改任何 pom）

| 需要的东西 | 现状 | 结论 |
|---|---|---|
| `spring-tx`（`@Transactional` 的来源） | `spring-tx:7.0.9` 经 `mybatis-plus-spring-boot4-starter` → `spring-boot-starter-jdbc` 传递而来 | ✅ 已在 classpath |
| 事务管理器 Bean | Spring Boot 自动配置 `JdbcTransactionManager` | ✅ **不用**加 `@EnableTransactionManagement` |
| `ProductSku` / `ProductImage` 实体 | 已存在 | ✅ 直接用 |
| `ProductSkuMapper` / `ProductImageMapper` | 已存在 | ✅ 直接注入 |
| `ProductSku.attributes` 的类型映射 | **有问题** | ❌ 今天第 4 步要修 |

---

## 3. 第 1 步：把"一个商品带 N 个 SKU"表达出来（DTO）

### 3.1 新建 `SkuCreateDTO`

```java
package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

import java.math.BigDecimal;
import java.util.Map;

/** 新建商品时随商品一起提交的一个 SKU */
@Data
public class SkuCreateDTO {

    @NotBlank(message = "SKU 编码不能为空")
    private String skuCode;

    private String name;

    @NotNull(message = "SKU 价格不能为空")
    @Positive(message = "SKU 价格必须大于 0")
    private BigDecimal price;

    private BigDecimal originalPrice;

    /** 动态规格，落库是 jsonb，出参是 JSON 对象：{"color":"黑","storage":"128G"} */
    private Map<String, Object> attributes;

    private String image;

    private Integer status;
}
```

**为什么不让接口直接收 `ProductSku` 实体？** 三个理由：

1. 实体里有 `id`、`createdAt`、`updatedAt` —— 这些是**数据库生成**的，不该由客户端指定；
2. 实体是"表的样子"，DTO 是"接口契约的样子"，两者需求不同就会分叉（比如客户端想传 `attributes` 对象，而表里存 jsonb）；
3. `productId` 在新增场景下**必须由服务端填**（商品还没建出来，哪来的 id）—— 实体里有这个字段就容易被误传。

> 一句话：**DTO 描述"客户端能给我什么"，实体描述"数据库里长什么样"，中间由 Service 负责翻译。**

### 3.2 改 `ProductCreateDTO`（只加两个字段）

```java
package com.mallx.product.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Data
public class ProductCreateDTO {
    @NotNull(message = "分类不能为null")
    private Long categoryId;
    private Long brandId;

    @NotBlank(message = "名称不能为空")
    @Size(max = 100, message = "商品名称不能超过100字")
    private String name;

    @Size(max = 200, message = "副标题不能超过200字")
    private String subtitle;

    private String description;

    private String mainImage;

    private Integer status;

    // ---------------- 以下为 Day 08 新增 ----------------

    /** 商品图集（按数组顺序入库为 sort_order）。可为空 —— 兼容 Day 07 的老请求体 */
    private List<String> images;

    /**
     * SKU 列表。可为空。
     * ⚠️ 字段上的 @Valid 是**级联校验**的开关：没有它，SkuCreateDTO 里的
     * @NotBlank/@Positive 全部不会执行，等于白写。
     */
    @Valid
    private List<SkuCreateDTO> skus;
}
```

**这里有个必须记住的细节**：`@Valid` 加在**字段**上才会级联到集合元素。

```java
@Valid private List<SkuCreateDTO> skus;      // ✅ 元素里的约束会生效
private List<SkuCreateDTO> skus;             // ❌ 元素里的 @NotBlank 全部静默失效
```

对比 Day 07：那时是 `@RequestBody @Valid ProductCreateDTO dto` —— `@Valid` 放在**参数**上。两个位置作用不同：

| `@Valid` 放哪 | 校验谁 |
|---|---|
| Controller 方法参数上 | 这个 DTO 自己的字段 |
| DTO 的集合字段上 | **集合里每个元素**的字段 |

### 3.3 今天的请求体长这样

```json
{
  "categoryId": 1,
  "brandId": 1,
  "name": "iPhone 15",
  "subtitle": "A16 芯片",
  "status": 1,
  "mainImage": "https://cdn.mallx.com/ip15-main.jpg",
  "images": [
    "https://cdn.mallx.com/ip15-1.jpg",
    "https://cdn.mallx.com/ip15-2.jpg"
  ],
  "skus": [
    { "skuCode": "IP15-BLK-128", "name": "黑色 128G", "price": 5999.00,
      "attributes": { "color": "黑", "storage": "128G" } },
    { "skuCode": "IP15-WHT-256", "name": "白色 256G", "price": 6999.00,
      "attributes": { "color": "白", "storage": "256G" } }
  ]
}
```

---

## 4. 第 2 步：先跑通"写 SKU" —— 一定会撞上 JSONB（40 分钟）

**这一步只写 SKU，先不碰事务。** 两个概念分开落地，出问题才好定位。

### 4.1 为什么会撞：一个已验证的事实

`product_skus.attributes` 在数据库里是 **JSONB**，但实体里是 `String`。这看着"String 存 JSON 文本"很自然，实际会被 PostgreSQL 直接拒收。

我写了个最小探针连真实库验证过（`D:\MallX\learning\probe\JsonbProbe.java`，可重跑），结果如下：

```text
driver = 42.7.13
[1] setString -> jsonb         : FAIL -> PSQLException: ERROR: column "attrs" is of type jsonb
                                          but expression is of type character varying
[2] PGobject -> jsonb          : OK
[3] setString + ::jsonb        : OK
[4] setObject(Types.OTHER)     : OK
[5] PGobject + Types.OTHER     : OK
```

**报错原文值得记住**：

```text
column "attributes" is of type jsonb but expression is of type character varying
提示：You will need to rewrite or cast the expression.
```

翻译过来就是：**"我要 jsonb，你给的是一条 varchar，我不猜。"** PostgreSQL 的类型系统很严格，不会自动帮你把字符串转成 jsonb。

### 4.2 更坑的是：MyBatis-Plus 自带的 JSON handler 也不行

直觉上会去用 MP 的 `JacksonTypeHandler`：

```java
@TableName(value = "product_skus", autoResultMap = true)
public class ProductSku {
    @TableField(typeHandler = JacksonTypeHandler.class)
    private Map<String, Object> attributes;
}
```

看着很标准 —— 但它在**这个组合下同样会报上面那个错**。我用 `javap` 反编译了 MP 3.5.17 的字节码，`AbstractJsonTypeHandler.setNonNullParameter` 里面是：

```text
7: invokeinterface #87,  3   // InterfaceMethod java/sql/PreparedStatement.setString:(ILjava/lang/String;)V
                                  ↑ 就是探针里失败的那个 [1]
```

也就是说：**MP 的 JSON handler 一律走 `ps.setString(...)`，而 PG 的 jsonb 列拒收 `setString`。** 这不是你写错了，是这两个东西凑一起的固有冲突。

> **教训（比知识点更重要）**：网上搜到的"标准写法"默认后端是 MySQL。换到 PostgreSQL，光靠"看起来很标准"是不够的 —— **得看 jar 里到底怎么实现的**。

### 4.3 解决：自己写一个 TypeHandler

`TypeHandler` 是 MyBatis 的"**Java 类型 ↔ JDBC 类型翻译官**"。默认情况下 MyBatis 有一堆内置翻译官（String↔varchar、Long↔bigint…），但"Map ↔ jsonb"没人为你准备，得自己加一个。

**新建 `mall-product/.../handler/JsonbMapTypeHandler.java`：**

```java
package com.mallx.product.handler;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Map;

/**
 * Map&lt;String,Object&gt; ↔ PostgreSQL jsonb 的翻译官。
 * <p>
 * 【为什么需要它】
 * PG 的 jsonb 列拒收 setString（会报 "is of type jsonb but expression is of type character varying"），
 * 必须用 setObject(..., Types.OTHER) 告诉驱动"这个参数类型我不指定，交给数据库按上下文推断"。
 * MyBatis-Plus 自带的 JacksonTypeHandler 内部走的是 setString，因此在本项目里用不了。
 * <p>
 * 【为什么不用 @MappedTypes 注册成全局 handler】
 * 全局注册会按"Java 类型"匹配 —— 一旦注册，项目里**所有 String/Map 字段**都会被套上 jsonb 逻辑。
 * 这里只通过 @TableField(typeHandler = ...) 精确指定给 attributes 一个字段。
 */
public class JsonbMapTypeHandler extends BaseTypeHandler<Map<String, Object>> {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /** Java → JDBC：写库时把 Map 序列化成 JSON 文本，并声明为"未指定类型" */
    @Override
    public void setNonNullParameter(PreparedStatement ps, int i,
                                    Map<String, Object> parameter, JdbcType jdbcType) throws SQLException {
        ps.setObject(i, toJson(parameter), Types.OTHER);
    }

    /** JDBC → Java：读库时把 jsonb 文本反序列化回 Map（getString 对 jsonb 是安全的） */
    @Override
    public Map<String, Object> getNullableResult(ResultSet rs, String columnName) throws SQLException {
        return parse(rs.getString(columnName));
    }

    @Override
    public Map<String, Object> getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        return parse(rs.getString(columnIndex));
    }

    @Override
    public Map<String, Object> getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        return parse(cs.getString(columnIndex));
    }

    private String toJson(Map<String, Object> map) {
        try {
            return MAPPER.writeValueAsString(map);
        } catch (Exception e) {
            // 抛 RuntimeException：一是让事务能回滚，二是异常往外走才能被全局处理器看到
            throw new IllegalArgumentException("attributes 无法序列化为 JSON", e);
        }
    }

    private Map<String, Object> parse(String json) {
        if (json == null) {
            return null;
        }
        try {
            return MAPPER.readValue(json, new TypeReference<Map<String, Object>>() { });
        } catch (Exception e) {
            throw new IllegalArgumentException("attributes 不是合法 JSON：" + json, e);
        }
    }
}
```

**这个类要理解的只有三件事：**

| 方法 | 什么时候被调用 | 干什么 |
|---|---|---|
| `setNonNullParameter` | 写库（INSERT/UPDATE） | Map → JSON 文本，`Types.OTHER` 交给 PG 推断 |
| `getNullableResult` × 3 | 读库（SELECT） | jsonb 文本 → Map |
| 三个重载的区别 | — | 按列名取 / 按下标取 / 按存储过程取，**MyBatis 要求全部实现** |

> 三个 `getNullableResult` 长得一样但都必须写 —— 这是 `BaseTypeHandler` 接口的规定，少一个就编译不过。

**为什么 `Types.OTHER` 就行？** 因为它等于告诉驱动："这个参数**不指定** JDBC 类型"。PG 拿到一个未指定类型的参数，会按**目标列的类型**（jsonb）去解释它 —— 探针的 `[4]`、`[5]` 两条都验证过这条路是通的。

### 4.4 改实体和 VO（★ 两处必须一起改）

**`ProductSku.java`：**

```java
@Data
@TableName(value = "product_skus", autoResultMap = true)   // ← ① 加 autoResultMap
public class ProductSku {
    @TableId(type = IdType.AUTO)
    private Long id;

    private Long productId;

    private String skuCode;

    private String name;

    private BigDecimal price;

    private BigDecimal originalPrice;

    // ← ② 类型 String → Map，并指定 TypeHandler
    @TableField(typeHandler = JsonbMapTypeHandler.class)
    private Map<String, Object> attributes;

    private String image;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
```

**`SkuVO.java`：**

```java
@Data
public class SkuVO {
    private Long id;
    private String skuCode;
    private String name;
    private BigDecimal price;
    private BigDecimal originalPrice;
    private Map<String, Object> attributes;   // ← 跟着实体一起改
    private String image;
}
```

两个关键字解释：

| 关键字 | 不加会怎样 | 为什么 |
|---|---|---|
| `@TableField(typeHandler = ...)` | 写库时报 jsonb 类型错误 | 告诉 MP"这个字段用哪个翻译官" |
| `@TableName(autoResultMap = true)` | **写库正常、读库出错**（或 attributes 读出来是 null） | MP 查询默认用自动生成的 resultMap，它不认自定义 handler；开了这个才会把 handler 带进 resultMap |

> `autoResultMap` 是最容易漏的一个：**只加 `@TableField` 只解决"写"，不解决"读"**。写进去一切正常，回头一查详情发现 `attributes` 是空的 —— 而且不报错。

⚠️ **千万别这么干**：在 `application.yml` 里加 `mybatis-plus.type-handlers-package: com.mallx.product.handler` 全局注册。全局注册是按 **Java 类型**匹配的，我们的 handler 声明处理 `Map`，一旦全局注册，项目里所有 `Map` 参数都会被当成 jsonb 送出去 —— 这类问题排查起来极其难受。**只用在字段上精确指定。**

### 4.5 先验证"单表写 SKU"通了

在 `createProduct` 里**临时**加一段只写 SKU 的代码（这段一会儿要重写成事务版）：

```java
this.save(product);                              // 商品主表
if (productCreateDTO.getSkus() != null) {
    for (SkuCreateDTO s : productCreateDTO.getSkus()) {
        ProductSku sku = new ProductSku();
        BeanUtils.copyProperties(s, sku);
        sku.setProductId(product.getId());        // ★ 服务端填，不能用客户端传的
        productSkuMapper.insert(sku);
    }
}
```

请求体用 3.3 的两 SKU 版本（带 `attributes`），应该 **200**。

**立刻验证"读"也通**（这一步专门为了验证 `autoResultMap`）：

```powershell
curl.exe "http://localhost:8080/api/products/6"      # 换成本次新建的 id
```

返回里 `skus[0].attributes` 应该是 **JSON 对象**：

```json
"skus": [
  { "skuCode": "IP15-BLK-128", "price": 5999.00,
    "attributes": { "color": "黑", "storage": "128G" } }
]
```

如果 `attributes` 是 `null` → `autoResultMap` 没加或没生效；如果是转义字符串 → 实体没改类型。

---

#### ✅ 第 1、2 步实装记录（2026-09-17 16:56 真机验证通过）

骨架已落位并**跑通**，你可以直接从第 3 步（事务）开始写。实测证据：

| 检查 | 实测结果 |
|---|---|
| `mvn -o install -DskipTests` | **BUILD SUCCESS**（mall-product 9.08s） |
| `POST /api/products`（商品 + 2 SKU，SKU 带 jsonb `attributes`） | **HTTP 200** + `{"code":200,"data":10}` |
| `GET /api/products/10` | `skus` 长度 **2**，`attributes` 是 **JSON 对象**（不是字符串、不是 null） |
| DB 直查 `jsonb_typeof(attributes)` | **object** ✅ |
| 中文真身（`encode(convert_to(...),'hex')`） | `e9bb91`=黑、`e799bd`=白 ✅（psql 里显示成 `榛?`/`鐧?` 是终端编码假象） |
| 清理后基线 | products **5** / product_skus **7** / product_images **4**（测试数据已删） |

两个顺带确认的事实：

- `images` 长度为 **0** —— 符合预期，第 2 步还没写图集，这是第 3 步的事。
- `product_skus` 序列已推进到 **9**，下一个新 SKU 拿 **10**（不会撞已有主键）。

> 也就是说：`JsonbMapTypeHandler` + `@TableField(typeHandler=...)` + `autoResultMap=true` 这套组合
> 在本项目（PG 16 + 无 `stringtype=unspecified`）下**是通的**。
> 以后如果这段代码报 `is of type jsonb but expression is of type character varying`，
> 说明是**后来改坏了**（比如有人把 handler 换成了 MP 自带的 `JacksonTypeHandler`），不是本来就跑不通。

---

## 5. 第 3 步：升级成"三张表一个事务"（40 分钟）

### 5.1 改 `ProductServiceImpl.createProduct`

```java
    /**
     * 新建商品：商品主表 + N 个 SKU + M 张图集，三张表一个事务。
     * <p>
     * 【为什么必须 @Transactional】
     * 这三张表是"1 主 + 2 子"的关系，缺任何一半都是脏数据：
     * 只有商品没有 SKU → 用户点进去无货可买；
     * 有 SKU 却没有商品 → 外键也会直接拒绝。
     * 任一步失败必须整体撤销，否则库里会留下"半成品"。
     * <p>
     * 【为什么注解加在这里，而不是 Controller】
     * ① 事务只要包住"业务与数据库相关的那几行"，加在 Controller 会把参数校验、
     *    JSON 序列化都圈进事务里，事务被拉长、占着数据库连接；
     * ② 异常在 Service 抛出、穿过代理时才触发回滚，放在最贴近数据库的一层最准。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createProduct(ProductCreateDTO dto) {
        // ① 校验分类存在（不是外键兜底 —— 是要给出人看得懂的提示）
        if (categoryMapper.selectById(dto.getCategoryId()) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "分类不存在");
        }

        // ② 商品主表
        Product product = new Product();
        BeanUtils.copyProperties(dto, product);
        if (product.getStatus() == null) {
            product.setStatus(1);
        }
        this.save(product);                     // 之后 product.getId() 才有值
        Long productId = product.getId();

        // ③ 图集：数组顺序即 sort_order
        List<String> images = dto.getImages();
        if (images != null && !images.isEmpty()) {
            for (int i = 0; i < images.size(); i++) {
                String url = images.get(i);
                if (url == null || url.isBlank()) {
                    continue;
                }
                ProductImage img = new ProductImage();
                img.setProductId(productId);
                img.setImageUrl(url);
                img.setSortOrder(i);
                productImageMapper.insert(img);
            }
        }

        // ④ SKU：productId 必须由服务端填（商品 id 是刚拿到的）
        List<SkuCreateDTO> skus = dto.getSkus();
        if (skus != null && !skus.isEmpty()) {
            for (SkuCreateDTO s : skus) {
                ProductSku sku = new ProductSku();
                BeanUtils.copyProperties(s, sku);
                sku.setProductId(productId);
                if (sku.getStatus() == null) {
                    sku.setStatus(1);
                }
                productSkuMapper.insert(sku);   // ★ 这里就是"能被制造失败"的那一行
            }
        }

        return productId;
    }
```

新增 import：

```java
import com.mallx.product.dto.SkuCreateDTO;
import org.springframework.transaction.annotation.Transactional;
```

> ⚠️ `@Transactional` 是 `org.springframework.transaction.annotation.Transactional`。
> 别被 IDE 补成 `jakarta.transaction.Transactional`（那个是 JavaEE 的，本项目没引，编译不过）。

### 5.2 `@Transactional` 能不能生效，就看这五条（重要）

| # | 条件 | 违反了会怎样 |
|---|---|---|
| 1 | 方法必须是 **`public`** | 非 public 直接**静默失效**（Spring 6+ 起连日志都没有） |
| 2 | 必须**从外部经代理调用** | 类内部 `this.createXxx()` 自调用**不走代理 → 注解失效** |
| 3 | 默认只对 **`RuntimeException` / `Error`** 回滚 | 抛受检异常（`IOException` 等）**不回滚** → 所以上面写了 `rollbackFor = Exception.class` |
| 4 | 异常必须**抛出去** | 自己 `try { … } catch (Exception e) { log.error(...); }` 吞掉 → **回滚不会发生** |
| 5 | 事务要**短** | 事务里别做 HTTP 调用／发消息／读大文件 —— 会长时间占着数据库连接 |

**第 2 条特别容易踩**，看个反例：

```java
@Service
public class ProductServiceImpl implements ProductService {

    @Override
    public Long createProduct(ProductCreateDTO dto) {
        this.insertSkus(1L, dto.getSkus());   // ❌ 自调用：this 是原始对象，不是代理
    }

    @Transactional
    public void insertSkus(Long productId, List<SkuCreateDTO> skus) {
        // 这里的 @Transactional 完全不生效
    }
}
```

**为什么？** Spring 的事务是**代理**实现的，调用链是这样的：

```text
外部 → [代理] → 开事务 → [真实对象.createProduct()] → 方法体 → 提交/回滚
                ↑ 事务在这里开

自调用：真实对象.createProduct() → this.insertSkus()   ← 根本没经过代理，没人开事务
```

**记忆口诀**：**「自己调自己不生效」**。真要拆方法，就用 `AopContext.currentProxy()` 或干脆把子方法放到另一个 Bean 里。

> 顺带一个相关现象：如果内层方法（另一个 Service）也有 `@Transactional` 且加入了外层事务，内层抛异常被外层 `catch` 住继续走 —— 提交时会报
> `UnexpectedRollbackException: Transaction silently rolled back because it has been marked as rollback-only`。
> 原因：内层已经把整个事务标记为"必须回滚"，外层却想提交。**事务标记是全局的，不会因为你 catch 了异常就撤销。**

### 5.3 关于"要不要用 `saveBatch`"

MP 的 `ServiceImpl` 提供了 `saveBatch(list)` 批量插入。今天**不用**，两个原因：

1. SKU/图片是**个位数**，循环 `insert` 已经完全够用，而且代码更直白；
2. `saveBatch` 走的是 MyBatis 的 `ExecutorType.BATCH`，`IdType.AUTO` 下**回填主键的行为与单条 `insert` 不同**（单条 `insert` 之后 `sku.getId()` 一定有值，批量则不一定）。今天不需要子表 id，但把两种写法的差异记在心里：**要拿到自增 id 就用单条**。

---

## 6. 第 4 步：亲手把事务打回滚（30 分钟，今天最值钱的一步）

看书看一百遍"事务会回滚"，不如自己让它回滚一次。

### 6.1 设计一个"一定会失败"的请求

`sku_code` 上有 **UNIQUE** 约束，这就是天然的失败开关。设计原则：**让第 2 个 SKU 的 `sku_code` 撞上已经入库的那一条。**

```json
{
  "categoryId": 1,
  "name": "回滚验证商品",
  "status": 1,
  "images": ["https://cdn.mallx.com/rollback-1.jpg"],
  "skus": [
    { "skuCode": "SKU-ROLLBACK-A", "name": "能成功", "price": 100.00 },
    { "skuCode": "SKU-ROLLBACK-A", "name": "一定失败", "price": 200.00 }
  ]
}
```

执行顺序会是：

```text
BEGIN
  INSERT products            ✅ 商品建出来了，拿到 id = N
  INSERT product_images      ✅ 图集写进去了
  INSERT product_skus #1     ✅ SKU-ROLLBACK-A 入库
  INSERT product_skus #2     ❌ duplicate key value violates unique constraint "product_skus_sku_code_key"
ROLLBACK   ← 上面三条全部撤销
```

> **为什么不让第 1、2 个 SKU 就用同一个 code？** 那也行，但"撞**库里已有**的数据"更贴近真实场景 ——
> 真实世界里的唯一冲突几乎都来自并发（两个人同时提交了同一个编码），
> 这也顺便回答了后面 6.4 的问题。

### 6.2 观察三件事

**① HTTP 响应** —— 期望 `code=500`（因为唯一约束异常会落到兜底的 `Exception.class` 处理器）

```json
{ "code": 500, "message": "fail", "data": null }
```

**② 日志** —— 应该能看到异常栈，关键是这几行：

```text
系统异常
org.springframework.dao.DuplicateKeyException: ...
Caused by: org.postgresql.util.PSQLException: ERROR: duplicate key value violates unique constraint "product_skus_sku_code_key"
```

> **`DuplicateKeyException` 是从哪来的？** PG 抛的是 `PSQLException`（JDBC 层），
> Spring 的 `SQLExceptionTranslator` 把它**翻译**成了 `org.springframework.dao.DuplicateKeyException`
> （`DataIntegrityViolationException` 的子类，属于 `RuntimeException`）。
> 所以它能触发默认回滚 —— 这也是为什么 **JDBC 的异常体系必须被 Spring 翻译**，否则事务判断不了该不该回滚。

**③ ★ 三张表行数（决定性证据）**

```powershell
$dx = "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
& $dx exec -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx -c `
  "SELECT (SELECT count(*) FROM products) AS products, (SELECT count(*) FROM product_skus) AS skus;"
```

| 结果 | 说明 |
|---|---|
| products **没变**、skus **没变** | ✅ 事务生效：三条插入全撤销了 |
| products 多了 1 行 | ❌ 事务没生效 —— 去查第 5.2 章的五个条件 |

### 6.3 ★ 反证实验：把 `@Transactional` 注释掉再跑一次

**这一步别跳过。** 不对比，你永远不知道那行注解到底干了什么。

```java
    // @Transactional(rollbackFor = Exception.class)   ← 注释掉
    public Long createProduct(ProductCreateDTO dto) {
```

重启后**用完全相同的请求**再调一次，然后查库：

| 结果 | 说明 |
|---|---|
| products **多了 1 行**（那个"回滚验证商品"留下了） | ✅ 这才叫"证明注解有用" |
| product_skus **也多了 1 行**（第 1 个 SKU 成功入库、第 2 个被唯一约束挡住） | 注意：**不是"仍是基线 7 行"** —— 第 1 个 SKU 是能插进去的，它会跟着主表一起残留 |
| product_images **同样多了 1 行** | 图集排在 SKU 之前，早就写完了，自然一起残留 |

**这就是"孤儿商品"**：用户能看到商品、点进去却没有一个 SKU 可买。没有 `@Transactional`，这类脏数据会一直留在库里，而且**接口返回的还是错误提示，看起来"没成功"** —— 前端以为没建，后台却多了一条。

**别忘了把注解加回去。**（真忘了的话，第 7 章的验收第 5 项会替你抓住。）

### 6.4 顺带发现的两个问题（都是好问题）

**① 唯一约束错误现在返回 `500 系统异常`，对客户端毫无意义**

用户看到的是"系统异常"，但真实原因只是"这个 SKU 编码已存在"。可以在 `GlobalExceptionHandler` 里加一个出口：

```java
@ExceptionHandler(DuplicateKeyException.class)
@ResponseStatus(HttpStatus.CONFLICT)
public Result<Void> handleDuplicateKey(DuplicateKeyException e) {
    log.warn("唯一约束冲突: {}", e.getMessage());
    return Result.error(ResultCode.VALIDATE_FAILED.getCode(), "数据已存在（编码重复）");
}
```

> ⚠️ 注意类型选 `DuplicateKeyException`（最具体），**不要**用它的父类 `DataIntegrityViolationException`
> —— 那会把"非空约束""外键约束"也一起归成"编码重复"。异常处理的粒度原则：
> **catch 得越具体，提示才能越准确。**
>
> 这个改动**今天可选**（会不会让验收第 4 项的期望值从 500 变成 409，得先定下来）。想加就加，改动很小。

**② "提交前先在 Java 里查一遍 sku_code 存不存在" —— 能替代唯一约束吗？**

**不能。** 因为存在**竞态**：

```text
线程 A: 查询 SKU-X → 不存在        ┐
线程 B: 查询 SKU-X → 不存在        │ 两个都以为安全
线程 A: INSERT SKU-X → 成功        │
线程 B: INSERT SKU-X → 冲突出错    ┘
```

**"先查后插"在任何并发场景下都不可靠**（中间隔着的那点时间足够另一个事务插进去）。
所以：

| 手段 | 作用 |
|---|---|
| Java 层预检查 | **优化体验** —— 让 99% 的正常重复立刻返回友好提示 |
| 数据库唯一约束 | **保证正确** —— 最后一道防线，并发下唯一可信的守卫 |

两者是**互补**，不是二选一。这也是为什么建表时那些 `UNIQUE` 一个都不能省。

---

## 7. 第 5 步：构建、启动与验收（40 分钟）

### 7.1 构建

```powershell
$env:MAVEN_OPTS="-Xmx1024m"
Set-Location D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o install -DskipTests
```

### 7.2 启动

```powershell
# ★ 先把旧进程杀干净（Maven 父进程 + fork 的 java 子进程），否则改了没生效
Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
  Where-Object { $_.CommandLine -match 'mall|spring-boot' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 再启动（后台）
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o spring-boot:run -pl mall-server "-Dspring-boot.run.arguments=--server.port=8080"
```

### 7.3 九项验收

> ⚠️ 用 PowerShell 调 curl 时，**响应一律 `-o` 落盘再 `Get-Content -Raw` 读**。
> 直接把 stdout 接进 `ConvertFrom-Json` 会被控制台的自动折行切碎，导致"token 是空的"这类假故障（Day 07 在这儿卡过 3 轮）。

| # | 验收项 | 期望 | 在证明什么 |
|---|---|---|---|
| 1 | admin 建"商品 + 2 SKU + 2 图" | `code=200` + 新 id | 三表写入链路通 |
| 2 | `GET /api/products/{新id}` | `skus` 长度 2、`images` 长度 2、`attributes` 是**对象** | `autoResultMap` + TypeHandler 的读回都正常 |
| 3 | DB 直查三张表 | products +1、**product_skus 首次非 0**、product_images +2 | 真的落库了，不是只返回了 200 |
| 4 | 用**已存在**的 `sku_code` 再建一次 | `code=500`（或改过 handler 后 409） | 唯一约束被触发 |
| 5 | ★ DB 查 `products`：那个商品**不存在** | 无此行 | **主表被回滚了** |
| 6 | ★ 注释掉 `@Transactional` 重跑第 4 项 | **商品残留** | 反证注解的作用 |
| 7 | 恢复注解；不传 `skus`/`images` 建商品 | `code=200` | 向后兼容，Day 07 的老请求体仍可用 |
| 8 | 匿名 / demo token 建商品 | `401` / `403` | Day 07 的权限没被破坏 |
| 9 | Day 07 的 PUT / DELETE 回归 | `code=200` | 改动没误伤既有接口 |

**建议的验收脚本骨架**（沿用 Day 07 的落盘写法）：

```powershell
$B   = "http://localhost:8080"
$dir = "D:\MallX\learning\day08"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$enc = New-Object System.Text.UTF8Encoding($false)

# admin token
& curl.exe -s -o "$dir\admin.json" -X POST "$B/api/auth/admin/login" `
  -H "Content-Type: application/json" --data-binary "@D:\MallX\learning\day07\admin-login.json"
$T = ((Get-Content "$dir\admin.json" -Raw -Encoding utf8) | ConvertFrom-Json).data.token
$h = "Authorization: Bearer $T"

# 正常建（商品 + 2 SKU + 2 图）
$body = '{"categoryId":1,"name":"Day08多表写","status":1,"images":["https://cdn.mallx.com/a.jpg","https://cdn.mallx.com/b.jpg"],'
      + '"skus":[{"skuCode":"DAY08-A","name":"规格A","price":100.00,"attributes":{"color":"黑"}},'
      + '{"skuCode":"DAY08-B","name":"规格B","price":200.00,"attributes":{"color":"白"}}]}'
[System.IO.File]::WriteAllText("$dir\create.json", $body, $enc)

& curl.exe -s -o "$dir\r1.json" -w "http=%{http_code}" -X POST "$B/api/products" `
  -H "Content-Type: application/json" -H $h --data-binary "@$dir\create.json"
Get-Content "$dir\r1.json" -Raw -Encoding utf8        # 期望 code=200 + 新 id
```

---

#### ✅ 7.4 九项验收实测记录（2026-09-17 21:37 真机跑通）

**环境**：PG 5434 通 / 应用 8080 / 启动日志有 `Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl`（**没有** `Found 2 UserDetailsService` 警告）

**基线**（`count(*)` 实查）：products **5** / product_skus **7** / product_images **4**

| # | 验收项 | 实测 | 结论 |
|---|---|---|---|
| 1 | admin 建「商品 + 2 SKU + 2 图」 | `http=200 code=200`，新 id=**11** | ✅ |
| 2 | `GET /api/products/11` | `skus=2`、`images=2`、`attributes=color=黑,storage=128G`、类型 **OBJECT** | ✅ 读回三件套都对 |
| 3 | DB 直查三张表 | **6 \| 9 \| 6**（基线 5\|7\|4） | ✅ +1 / +2 / +2，真落库 |
| 4 | 用已存在 `sku_code` 再建 | `code=500 msg=fail` | ✅ 唯一约束被触发 |
| 5 | ★ 查那个商品是否存在 | 「Day08-回滚验证机」**残留 0 行**；第 1 个 SKU `D08V-C` **也 0 行** | ✅ **主表 + 子表一起回滚** |
| 6 | ★ 注释 `@Transactional` 重跑 | 见下表 | ✅ 反证成立 |
| 7 | 不传 `skus`/`images` 建商品 | `code=200`，id=13 | ✅ 向后兼容 |
| 8 | 匿名 / demo token 建商品 | **401** / **403** | ✅ 权限没被破坏 |
| 9 | Day 07 的 PUT / DELETE 回归 | PUT `200`；DELETE **第一次 500** → 修复后 `200` | ⚠️ 见 7.5 |

**第 6 项：同一冲突场景，有无注解的对照**

| | 无 `@Transactional` | 有 `@Transactional` |
|---|---|---|
| 请求 | `[D08V-D(新), D08V-A(库中已有)]` | `[D08V-E(新), D08V-A(库中已有)]` |
| 响应 | `code=500 msg=fail` | `code=500 msg=fail` |
| products | 6 → **7（+1，残留）** | 7 → **7（不变）** |
| product_skus | 9 → **10（+1，残留）** | 10 → **10（不变）** |
| product_images | 5 → **6（+1，残留）** | 6 → **6（不变）** |
| 结论 | **半成品脏数据真实存在** | **整体回滚，一行不多** |

> 两次响应都是 `code=500` —— **光看接口返回根本分辨不出有没有事务**。
> 差别只在库里：一个留下了"解释不通的商品"，另一个什么都没留。
> 这就是为什么"看响应 200/500"永远证明不了事务是否生效，**必须查库**。

> ⚠️ 做这个实验时踩了一个小坑：第一次把「已存在」的 `sku_code` 选成了 `D08V-A`，
> 而它在上一步 `DELETE 11` 时已被**级联删除**了，于是两个 SKU 都插成功、返回 `code=200`，
> 实验完全失效。**制造冲突前必须先确认那个值此刻确实在库里** —— 别拿记忆当依据。

---

#### 🐛 7.5 验收第 9 项钓出的真实 bug：删除商品撞外键

**现象**：`DELETE /api/products/11` → `code=500`，日志里是

```text
org.springframework.dao.DataIntegrityViolationException:
### Error updating database. Cause: org.postgresql.util.PSQLException:
ERROR: update or delete on table "products" violates foreign key constraint "fk_sku_product" on table "product_skus"
```

**根因**：Day 07 写的 `deleteProduct` 只做了一件事 ——

```java
this.removeById(id);      // 只删主表
```

而 `products` 被 **3 张表**用外键指着，且都是 `NO ACTION`：

| 外键名 | 子表 | `confdeltype` | 含义 |
|---|---|---|---|
| `fk_sku_product` | product_skus | `a` | NO ACTION —— 有引用就拒绝删 |
| `fk_product_image_product` | product_images | `a` | 同上 |
| `fk_review_product` | reviews | `a` | 同上 |

所以只要商品有 SKU 或图集，主表就删不掉。

> **为什么 Day 07 没暴露？** 因为那时**还没有写 SKU/图集的接口**，被删的测试商品子表是空的，
> 外键自然不生效。Day 08 一有真 SKU，这个洞立刻露出来 ——
> **这正是"验收要覆盖真实数据形态"的价值：空表跑得通，不代表逻辑对。**

**修复**（`ProductServiceImpl.deleteProduct`）：

```java
@Override
@Transactional(rollbackFor = Exception.class)
public void deleteProduct(Long id) {
    if (this.getById(id) == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
    }
    // ★ 顺序不能反：先子后主（与新增时正好相反）
    productSkuMapper.delete(new LambdaQueryWrapper<ProductSku>()
            .eq(ProductSku::getProductId, id));
    productImageMapper.delete(new LambdaQueryWrapper<ProductImage>()
            .eq(ProductImage::getProductId, id));
    this.removeById(id);
}
```

**修复后实测**（同一次收尾里连续验证）：

| 操作 | 三张表变化 |
|---|---|
| 删 id=11（带 2 SKU + 2 图） | 7\|9\|6 → **6\|7\|4** |
| 删 id=14（带 2 SKU + 1 图） | 6\|8\|5 → **6\|7\|4** |
| 删 id=15（带 1 SKU + 1 图） | → **5\|7\|4** ✅ 基线完整恢复 |
| 最终校验 | Day08 残留商品 **0**、D08V 残留 SKU **0** |

**带走的三条**：

1. **删除也要事务** —— 三次删除是一个整体，删一半同样是脏数据；
2. **删除顺序与插入相反**：插入是"主 → 子"（子表要用主表刚生成的 id），删除是"子 → 主"（主表被子表指着）；
3. **生产系统更常用的其实是软删除**（`status = 0` / `deleted = 1`），因为订单、评价等历史数据还要引用商品。物理级联删只适合本阶段这种纯学习场景。

> ⚠️ 还有个坑没碰：`reviews` 表也指向 `products`，目前是空表所以删得掉。
> 将来有了评价数据，删商品还得处理评价 —— 那正是"软删除"要解决的问题。

---

## 8. 常见卡点速查

| 现象 | 原因 | 解法 |
|---|---|---|
| `column "attributes" is of type jsonb but expression is of type character varying` | 用 `setString` 写 jsonb（**MP 自带的 `JacksonTypeHandler` 也走这条**） | 用第 4 步的 `JsonbMapTypeHandler`（`setObject(..., Types.OTHER)`） |
| 写库成功，但详情接口 `attributes` 永远是 `null` | 实体没加 `@TableName(autoResultMap = true)` | 加上；**只加 `@TableField(typeHandler=...)` 只解决写，不解决读** |
| 详情接口 `attributes` 是转义字符串 `"{\"color\":\"黑\"}"` | 实体改了 `Map` 但 VO 还是 `String`（或反之） | 实体与 VO **必须同步改类型**；`BeanUtils` 对类型不匹配是**静默跳过**，不报错 |
| `@Transactional` 加了但没回滚 | ①方法非 `public` ②自调用 ③异常被 `catch` 吞了 ④抛的是受检异常且没配 `rollbackFor` | 逐条对第 5.2 章那五条 |
| 事务回滚了，但接口返回的还是 200 | 正常 —— 回滚发生在异常**穿出代理**时；`@ExceptionHandler` 在更外层，接住异常**不影响**已发生的回滚 | 不用改。看响应 body 里的 `code` |
| `UnexpectedRollbackException: ... marked as rollback-only` | 内层事务已标记回滚，外层却想提交 | 别在外层 `catch` 内层事务异常后继续走；让异常一直抛出去 |
| 同一个 `sku_code` 并发提交，只有一个成功 | 这是**正确行为**，唯一约束在干活 | 用 6.4 的 `DuplicateKeyException` 处理器给出友好提示 |
| 改了代码但行为没变 | 旧进程没杀干净 / jar 被 `install` 覆盖后没重启 | 杀掉 Maven 父进程 + java 子进程，重启 |
| `curl` 返回的 JSON 解析失败、token 是空的 | PowerShell 对原生命令 stdout 的自动折行 | `-o` 落盘 + `Get-Content -Raw -Encoding utf8` |
| `DELETE /api/products/{id}` 报 `violates foreign key constraint "fk_sku_product"` | 只删了主表，子表还有引用行（外键是 NO ACTION） | 先 `delete` 子表再删主表（顺序与插入相反），并加 `@Transactional` |
| 制造唯一冲突的"实验"返回了 `code=200` | 拿来当"已存在"的那个 `sku_code` 其实**已经被删掉了** | 制造冲突前先 `SELECT` 确认它在库里 —— 别凭记忆 |
| 首次 INSERT 报 `products_pkey` 冲突 | （Day 07 已修）种子 SQL 显式插 id 未推进序列 | 已写入 `03-data.sql` 第九节；若换库重跑一遍该节 |

---

## 9. 本日成果自检清单

**代码**

- [x] `SkuCreateDTO` 新建，含 `skuCode/price/attributes` 校验
- [x] `ProductCreateDTO` 加 `images` + `@Valid List<SkuCreateDTO> skus`
- [x] `JsonbMapTypeHandler` 新建，四个回调都实现，**没有**注册成全局 handler
- [x] `ProductSku` 实体：`autoResultMap = true` + `attributes` 改 `Map` + 指定 handler
- [x] `SkuVO.attributes` 同步改成 `Map<String, Object>`
- [x] ★ `createProduct` 加 `@Transactional(rollbackFor = Exception.class)`，写三张表
- [x] `createProduct` 补 `product_images` 写入（images 下标 = sort_order）
- [x] ★ 验收钓出的 bug：`deleteProduct` 改为"先子后主" + `@Transactional`（见 7.5）
- [x] `ProductController` / `ProductService` **没改**（接口不变）

**验收**

- [x] 9 项验收全绿（第 9 项先 500，修复后转 200，见 7.5）
- [x] ★ 第 5 项：人为制造唯一冲突后，**products 表没有多出那一行**（残留 0 行，第 1 个 SKU 也 0 行）
- [x] ★ 第 6 项：注释掉 `@Transactional` 重跑，**商品残留了** —— 亲眼看到注解的作用（无事务 +1/+1/+1，有事务 0/0/0）
- [x] 正常建商品时 `product_skus` / `product_images` **行数比基线各 +2**（基线：products 5 / skus 7 / images 4）
- [x] 详情接口返回的 `attributes` 是 JSON **对象**（不是字符串、不是 null）—— 第 2 步已验证
- [x] `products` / `product_skus` 序列已对齐（本次自增 id 一路用到 15 未撞主键）
- [x] 验收后测试数据全部清理，基线恢复 **5 / 7 / 4**（Day08 残留 0、D08V 残留 0）

**理解（能不看文档讲出来）**

- [ ] 事务保证的是"**全有或全无**"，它防的是**脏数据**，不是"出错"
- [ ] `@Transactional` 生效的五个条件，尤其是「**自调用失效**」和「**默认只回滚 RuntimeException**」
- [ ] 为什么异常被全局处理器 `catch` 住，**回滚照样发生**（层次：处理器在事务代理之外）
- [ ] 为什么 PG 的 jsonb 必须用 `setObject(..., Types.OTHER)`，而 **MP 自带的 JSON handler 在本项目用不了**
- [ ] 为什么"Java 层先查一遍"**替代不了**数据库唯一约束（竞态）

**Git**

- [x] 提交：`feat: Day 08 商品多表写 - @Transactional 事务 + PG jsonb 映射`

---

## 10. 做完之后

今天之后，你手上多了两样**通用**的能力：

```text
① 事务            → 任何"多表联动"的场景都要用它
                   订单（建订单 + 扣库存 + 清购物车）、支付、退款
② TypeHandler     → 任何"Java 类型 ≠ 数据库类型"的场景
                   jsonb / 枚举 / 加密字段 / 数组 / 时间戳
```

**Day 09 的几个方向：**

```text
· 库存模块（mall-inventory）  → 商品建好了，但还没库存行：inventories 是 1:1 挂 SKU 的
                              正好练"先扣库存再建 SKU"和"跨模块事务传播"
· 购物车（mall-cart）         → 第一次让数据挂到 user_id，用 @AuthenticationPrincipal
· 给已有商品补 SKU            → POST /api/products/{id}/skus（今天做的都是"一次建全套"）
· 商品的编辑与删除            → PUT 目前只改主表，改不到 SKU/图集；
                               DELETE 虽已修好级联，但 reviews 表的外键还没处理 —— 引出"软删除"话题
```

> **今天最该带走的一句话**：
> **事务不是"防止出错"，而是"出错时不留半成品"。** 判断标准很简单 ——
> 问自己："这几步之间如果断了，库里会不会留下一条解释不通的数据？" 会，就该加 `@Transactional`。

---

## 附：今日术语表

| 术语 | 一句话解释 |
|---|---|
| 事务（Transaction） | 一组操作"全有或全无"，ACID 里的 A（原子性） |
| `@Transactional` | 声明式事务：加在方法上，由 Spring 代理自动 BEGIN/COMMIT/ROLLBACK |
| AOP 代理 | Spring 在你写的类外面套的一层壳，事务、鉴权都靠它插进去 |
| 自调用失效 | 类内部 `this.xxx()` 不经过代理，加 `@Transactional` 也没用 |
| `rollbackFor` | 指定哪些异常触发回滚；默认只认 `RuntimeException`/`Error` |
| 事务传播（REQUIRED） | 默认行为：有事务就加入，没有就新建 |
| `rollback-only` | 事务被标记"只能回滚"，此时外层再想提交就会 `UnexpectedRollbackException` |
| 脏数据 / 孤儿数据 | 只写了一半、业务上解释不通的数据（如没有 SKU 的商品） |
| `TypeHandler` | MyBatis 的"Java 类型 ↔ JDBC 类型"翻译官 |
| `autoResultMap` | MP 开关：让自定义 TypeHandler 也作用于**查询**结果映射 |
| JSONB | PostgreSQL 的二进制 JSON 类型，可索引、会校验 JSON 合法性 |
| `Types.OTHER` | JDBC 的"类型未指定"，让 PG 按目标列自行推断类型 |
| `DuplicateKeyException` | Spring 把 PG 的唯一约束冲突翻译成的异常（`RuntimeException`） |
| 竞态（Race Condition） | 两个线程"先查后插"，都以为安全，插的时候才撞上 |
