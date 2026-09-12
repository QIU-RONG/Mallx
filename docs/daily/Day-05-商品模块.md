# Day 05：商品模块（mall-product）

> 项目：MallX 企业级电商系统
> 学习方式：**你自己动手写代码**。本文档是"分步计划 + 参考模板（卡住再对照）+ 避坑清单 + 验收标准"，不替你写。
> 前置：Day 04 已收官 —— 统一返回/异常/分页/自动填充/Swagger 地基齐全，mall-user CRUD 全链路验证通过。
> 路线依据：《Day-05-路线决策》选定 **A→B 组合**，先做 B（本文档），B 验收后再出 A（登录鉴权 JWT）的规划文档。

---

## 0. 今日目标

把 Day 04 的「实体 → Mapper → Service → Controller」套路，**独立复制**到商品域：产出 mall-product 模块的三个读接口——分类树、商品分页（可筛选）、商品详情（含 SKU/图集/分类品牌名）。

**本日验收标准（做完自检）：**
- [ ] 编译通过（`cd backend/mallx && bash mvnw.sh package`）
- [ ] `GET /api/categories/tree` 返回 3 个一级分类、每个挂着自己的子分类
- [ ] `GET /api/products` 分页返回 5 条上架商品，每条带 `categoryName`/`brandName`
- [ ] `GET /api/products?categoryId=11` 精确返回 3 条（iPhone 17 Pro / Mate 80 Pro / Xiaomi 15 Ultra）
- [ ] `GET /api/products?keyword=iPhone` 模糊匹配返回 1 条
- [ ] `GET /api/products/1` 返回详情：分类名=智能手机、品牌名=Apple、3 个 SKU、2 张图
- [ ] `GET /api/products/99999` 返回统一 JSON `{code:404, message:"商品不存在"}`
- [ ] Swagger UI 出现「商品」「商品分类」两个新分组

---

## 1. 今日思路：套路复用 + 恰好三个新知识点

Day 04 你已经会"造一个模块"。今天是**用最小的增量把套路焊死**，全程只加三个新知识点：

```text
① VO 出参        —— 不把实体直接扔给前端；用 BeanUtils 按同名字段拷贝
② 批量查关联     —— 分页列表要显示分类名/品牌名，不能在循环里一条条查（N+1 问题）
③ 内存建树       —— categories 是 parent_id 平铺表，在 Java 里组装成树
```

**刻意不做的事（也是计划的一部分）：**
- **不做商品的增/删/改接口。** 商品"看"是公开的；商品"管"是管理端行为，必须知道"谁在操作"——这正是路线 A（登录鉴权）的动机。先把这个问题留到 B 做完，动机自然浮出来。
- **不给 SKU/品牌/图片建 Service。** 它们只是被查询、无业务规则，直接在 ProductServiceImpl 里注入 Mapper 用。什么时候该建 Service？——出现业务规则（如"上架才能加购"）再抽。判断力也是今天要练的。
- **不动库存。** `inventories` 表属于 mall-inventory 模块的职责，Day 05 不跨界。模块化单体里"每张表有唯一属主模块"是这个架构的核心纪律。

**预计时长：2~4 小时**（大部分时间在复制套路，新东西只有三小块）。

---

## 2. 第 0 步：确认数据与依赖（5 分钟）

### 2.1 数据现状（决策文档有一处过时）

《Day-05-路线决策》说"products 还是 0 条"——**已过时**。Day 03 的 `backend/sql/03-data.sql` 实际带了这个量：

```text
categories      7 条（一级：1 手机通讯 / 2 电脑办公 / 3 家用电器；子级：11,12→1，21→2，31→3）
brands          7 条（Apple/Huawei/Xiaomi/Samsung/Lenovo/DJI/无品牌）
products        5 条 SPU（全部 status=1 上架，全挂在子分类 11 或 21 上）
product_skus    7 条（iPhone 3 个、Mate80 1 个、小米 1 个、ThinkPad 1 个、MacBook 1 个）
product_images  4 条（商品 1 两张、商品 2 一张、商品 3 一张）
inventories     7 条（一 SKU 一条，Day 05 不碰）
```

**动手验证**（Docker 没开就先 `docker compose -f deploy/docker-compose.yml up -d`）：

```bash
docker exec mallx-postgres psql -U mallx -d mallx -c \
  "SELECT 'products' t, count(*) FROM products UNION ALL SELECT 'product_skus', count(*) FROM product_skus UNION ALL SELECT 'categories', count(*) FROM categories UNION ALL SELECT 'brands', count(*) FROM brands;"
```

- 若 products = 5：数据就位，直接开工。
- 若 products = 0：重跑种子脚本即可（幂等）：
  ```bash
  psql -h localhost -p 5434 -U mallx -d mallx -f backend/sql/03-data.sql
  ```

### 2.2 依赖现状：今天零 POM 改动

三个事实（Day 02 已埋好，Day 04 验证过机制）：
- 父 POM 全局共享依赖已含：MyBatis-Plus 3.5.17（spring-boot4-starter）+ jsqlparser + springdoc 3.1.1 + validation + lombok + PG 驱动；
- `mall-product/pom.xml` 已依赖 `mall-common`（统一返回体/异常就来自这里）；
- `mall-server/pom.xml` 已聚合 `mall-product`。

**结论：今天一行 XML 都不用改，直接写 Java。**

### 2.3 对照表结构（把 Day 03 的表贴在手边）

今天用 5 张表的关键列：

```text
products:        id | category_id(非空FK) | brand_id(可空FK) | name | subtitle | description
                 main_image | status(默认0) | search_vector(触发器维护) | created_at/updated_at
categories:      id | parent_id(可空=顶级) | name | sort_order | status | created_at/updated_at
brands:          id | name(唯一) | logo | description | status | created_at/updated_at
product_skus:    id | product_id(FK) | sku_code(唯一) | name | price NUMERIC(12,2) | original_price
                 attributes JSONB | image | status | created_at/updated_at
product_images:  id | product_id(FK) | image_url | sort_order | created_at（注意：没有 updated_at）
```

三个和 users 表**不一样**的类型映射，先记住：

| 列类型 | Java 类型 | 说明 |
|---|---|---|
| `NUMERIC(12,2)` | `BigDecimal` | 金额永远不用 Double（精度丢失） |
| `JSONB` | `String`（本日只读） | PG 驱动 `getString` 直接给 JSON 字符串；**写入**才需要 TypeHandler |
| `TSVECTOR` | 不映射 | `search_vector` 由数据库触发器自动维护，实体里**没有**这个字段，MP 的 insert/select 就不会碰它 |

`products.status` 语义约定：**1=上架，0=下架**（表默认 0；种子数据显式置 1）。

---

## 3. 第 1 步：实体（5 个文件）

**路径**：`mall-product/src/main/java/com/mallx/product/entity/`（包名 `com.mallx.product`，Day 02 已定）

套路与 User 实体一模一样，逐个创建：

### 3.1 Product.java（SPU）

```java
package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 商品 SPU 实体，映射 products 表
 * 注意：表里的 search_vector 列不映射 —— 它由数据库触发器自动维护（01-schema.sql），
 *       实体没有这个字段，MyBatis-Plus 生成的 insert/select 就不会带上它。
 */
@Data
@TableName("products")
public class Product {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 所属分类（FK categories.id，非空） */
    private Long categoryId;

    /** 品牌（FK brands.id，可空） */
    private Long brandId;

    private String name;

    private String subtitle;

    private String description;

    private String mainImage;

    /** 1=上架 0=下架（表默认 0） */
    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
```

### 3.2 ProductSku.java

```java
package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** 商品 SKU 实体，映射 product_skus 表 */
@Data
@TableName("product_skus")
public class ProductSku {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 所属 SPU（FK products.id） */
    private Long productId;

    private String skuCode;

    private String name;

    /** NUMERIC(12,2) → 金额一律 BigDecimal，别用 Double */
    private BigDecimal price;

    private BigDecimal originalPrice;

    /** JSONB 列：读时驱动 getString 直接返回 JSON 字符串；写入需 TypeHandler，本模块暂只读 */
    private String attributes;

    private String image;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
```

### 3.3 Category.java

```java
package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 商品分类实体，映射 categories 表（parent_id 支持多级树） */
@Data
@TableName("categories")
public class Category {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 父分类 id；顶级分类为 null */
    private Long parentId;

    private String name;

    private Integer sortOrder;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
```

### 3.4 Brand.java

```java
package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 品牌实体，映射 brands 表 */
@Data
@TableName("brands")
public class Brand {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String name;

    private String logo;

    private String description;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
```

### 3.5 ProductImage.java

```java
package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 商品图片实体，映射 product_images 表（该表只有 created_at，DB 默认值兜底） */
@Data
@TableName("product_images")
public class ProductImage {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long productId;

    private String imageUrl;

    private Integer sortOrder;

    private LocalDateTime createdAt;
}
```

---

## 4. 第 2 步：Mapper（5 个一行体）

**路径**：`mall-product/src/main/java/com/mallx/product/mapper/`

照抄模板换类型，5 个文件（ProductMapper / ProductSkuMapper / CategoryMapper / BrandMapper / ProductImageMapper）：

```java
package com.mallx.product.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.product.entity.Product;

/** 商品 Mapper：继承 BaseMapper 即获得单表 CRUD（不需要 @Mapper，启动类已 @MapperScan） */
public interface ProductMapper extends BaseMapper<Product> {
}
```

> 包名必须以 `.mapper` 结尾——启动类的 `@MapperScan("com.mallx.**.mapper")` 只扫这个后缀。

### ✅ 编译检查点

```bash
cd D:\MallX\backend\mallx
bash mvnw.sh package
```

预期：BUILD SUCCESS。有报错先修再走（此时只有实体和 Mapper，报错只会是包名/注解打错）。

---

## 5. 第 3 步：VO 出参（4 个文件，新知识点①）

**路径**：`mall-product/src/main/java/com/mallx/product/vo/`（新包）

**为什么需要 VO？** `Product` 实体里没有 categoryName/brandName（它们在别的表），而前端列表恰恰要显示这两个名字。把"实体 + 组装出来的字段"装进专门的出参对象，就是 VO（View Object）。顺带好处：以后实体加敏感字段也不会直接漏给前端。

### 5.1 ProductVO.java（列表项）

```java
package com.mallx.product.vo;

import lombok.Data;

/** 商品列表项 VO：实体字段 + 关联表的"名字" */
@Data
public class ProductVO {
    private Long id;
    private Long categoryId;
    private String categoryName;
    private Long brandId;
    private String brandName;
    private String name;
    private String subtitle;
    private String mainImage;
    private Integer status;
}
```

### 5.2 SkuVO.java

```java
package com.mallx.product.vo;

import lombok.Data;

import java.math.BigDecimal;

/** SKU 视图对象 */
@Data
public class SkuVO {
    private Long id;
    private String skuCode;
    private String name;
    private BigDecimal price;
    private BigDecimal originalPrice;
    private String attributes;   // JSONB 读出来就是 JSON 字符串，原样透给前端
    private String image;
}
```

### 5.3 ProductDetailVO.java（继承列表 VO）

```java
package com.mallx.product.vo;

import lombok.Data;
import lombok.EqualsAndHashCode;

import java.util.List;

/**
 * 商品详情 VO：在列表字段之上多给 描述 + SKU 列表 + 图集
 * 继承 ProductVO 复用全部字段；@EqualsAndHashCode 消除 lombok 对子类 @Data 的告警
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class ProductDetailVO extends ProductVO {
    private String description;
    private List<SkuVO> skus = List.of();
    private List<String> images = List.of();
}
```

### 5.4 CategoryVO.java（树节点）

```java
package com.mallx.product.vo;

import lombok.Data;

import java.util.List;

/** 分类树节点：children 是下一层同样的结构 */
@Data
public class CategoryVO {
    private Long id;
    private Long parentId;
    private String name;
    private Integer sortOrder;
    /** 默认空列表而不是 null，前端拿到就不必判空 */
    private List<CategoryVO> children = List.of();
}
```

---

## 6. 第 4 步：CategoryService + 分类树（新知识点③）

**只给 Category 建 Service**（它有"建树"这条业务规则）；Brand/Image/Sku 维持"Mapper 直用"（见第 7 步）。

### 6.1 CategoryService.java

**路径**：`service/CategoryService.java`

```java
package com.mallx.product.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.entity.Category;
import com.mallx.product.vo.CategoryVO;

import java.util.List;

/** 分类服务：继承 IService 获得通用 CRUD；tree 是本模块第一条真正的"业务方法" */
public interface CategoryService extends IService<Category> {

    /** 分类树（内存构建，支持多级） */
    List<CategoryVO> tree();
}
```

> ⚠️ 再念一遍 3.5.17 的咒语：`IService` 在 `com.baomidou.mybatisplus.spring.service`，**不是** `extension.service`（Day 04 踩过的坑，别回退）。

### 6.2 CategoryServiceImpl.java

**路径**：`service/impl/CategoryServiceImpl.java`

```java
package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.product.entity.Category;
import com.mallx.product.mapper.CategoryMapper;
import com.mallx.product.service.CategoryService;
import com.mallx.product.vo.CategoryVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/** 分类服务实现 */
@Service
public class CategoryServiceImpl extends ServiceImpl<CategoryMapper, Category> implements CategoryService {

    @Override
    public List<CategoryVO> tree() {
        // 1. 全量查出（分类数量少，内存建树最简单），按 sort_order, id 排好
        List<Category> all = this.list(new LambdaQueryWrapper<Category>()
                .orderByAsc(Category::getSortOrder)
                .orderByAsc(Category::getId));

        // 2. 实体转 VO
        List<CategoryVO> vos = new ArrayList<>();
        for (Category c : all) {
            CategoryVO vo = new CategoryVO();
            BeanUtils.copyProperties(c, vo);   // 按同名字段拷贝（id/parentId/name/sortOrder）
            vos.add(vo);
        }

        // 3. 按 parentId 分组。根节点 parentId 为 null，HashMap 不喜欢 null key，用哨兵值 -1L 归拢
        Map<Long, List<CategoryVO>> byParent = vos.stream()
                .collect(Collectors.groupingBy(v -> v.getParentId() == null ? -1L : v.getParentId()));

        // 4. 每个节点挂上自己的孩子。VO 是引用：挂一层 = 整棵树都挂好（三级以上的树同样适用）
        for (CategoryVO vo : vos) {
            vo.setChildren(byParent.getOrDefault(vo.getId(), List.of()));
        }

        // 5. 根节点集合就是树
        return byParent.getOrDefault(-1L, List.of());
    }
}
```

> 今天唯一的 Java 新语法是 Stream（`stream()/groupingBy/方法引用`）。第 4 步那段是它的核心用法：**先按父 id 分桶，再让每个节点领走自己的桶**。看不懂就先抄，验收通过后回头再读一遍注释。

### 6.3 CategoryController.java

**路径**：`controller/CategoryController.java`

```java
package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.product.service.CategoryService;
import com.mallx.product.vo.CategoryVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** 商品分类接口 */
@Tag(name = "商品分类")
@RestController
@RequestMapping("/api/categories")
public class CategoryController {

    private final CategoryService categoryService;

    public CategoryController(CategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @Operation(summary = "分类树（含二级子分类）")
    @GetMapping("/tree")
    public Result<List<CategoryVO>> tree() {
        return Result.ok(categoryService.tree());
    }
}
```

### ✅ 小验收（第一口正反馈）

重新打包、启动：

```bash
cd D:\MallX\backend\mallx
bash mvnw.sh package
java -jar mall-server/target/mall-server-0.0.1-SNAPSHOT.jar --server.port=8080
```

```bash
curl http://localhost:8080/api/categories/tree
```

预期 `data`：3 个根节点——`手机通讯`（children 含 智能手机/手机配件）、`电脑办公`（含 笔记本电脑）、`家用电器`（含 电视）。

---

## 7. 第 5 步：ProductService（新知识点②：批量查关联，防 N+1）

### 7.1 ProductService.java

**路径**：`service/ProductService.java`

```java
package com.mallx.product.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.entity.Product;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductVO;

/** 商品服务：本日只提供"看"的能力；管理端写接口等鉴权落地后再加 */
public interface ProductService extends IService<Product> {

    /** 分页查上架商品（可按分类精确过滤、按名称模糊搜索），并组装分类名/品牌名 */
    Page<ProductVO> pageProducts(long current, long size, Long categoryId, String keyword);

    /** 商品详情：分类/品牌名 + SKU 列表 + 图片列表 */
    ProductDetailVO getDetail(Long id);
}
```

### 7.2 ProductServiceImpl.java（今天最核心的一个类）

**路径**：`service/impl/ProductServiceImpl.java`

**关于注入**：Category/Brand/Sku/Image 不建 Service，这里直接注入它们的 Mapper。构造器注入 4 个 Mapper + 继承 ServiceImpl 拿到自己的 `getById/page`。

```java
package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.entity.Brand;
import com.mallx.product.entity.Category;
import com.mallx.product.entity.Product;
import com.mallx.product.entity.ProductImage;
import com.mallx.product.entity.ProductSku;
import com.mallx.product.mapper.BrandMapper;
import com.mallx.product.mapper.CategoryMapper;
import com.mallx.product.mapper.ProductImageMapper;
import com.mallx.product.mapper.ProductMapper;
import com.mallx.product.mapper.ProductSkuMapper;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductVO;
import com.mallx.product.vo.SkuVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 商品服务实现 */
@Service
public class ProductServiceImpl extends ServiceImpl<ProductMapper, Product> implements ProductService {

    /** 关联表走 Mapper 直查（无业务规则，不抽 Service） */
    private final CategoryMapper categoryMapper;
    private final BrandMapper brandMapper;
    private final ProductSkuMapper productSkuMapper;
    private final ProductImageMapper productImageMapper;

    public ProductServiceImpl(CategoryMapper categoryMapper, BrandMapper brandMapper,
                              ProductSkuMapper productSkuMapper, ProductImageMapper productImageMapper) {
        this.categoryMapper = categoryMapper;
        this.brandMapper = brandMapper;
        this.productSkuMapper = productSkuMapper;
        this.productImageMapper = productImageMapper;
    }

    @Override
    public Page<ProductVO> pageProducts(long current, long size, Long categoryId, String keyword) {
        LambdaQueryWrapper<Product> wrapper = new LambdaQueryWrapper<Product>()
                .eq(Product::getStatus, 1)                                   // C 端只看上架
                .eq(categoryId != null, Product::getCategoryId, categoryId)  // 布尔条件为 false 时，该条件不拼进 SQL
                .like(keyword != null && !keyword.isBlank(), Product::getName, keyword)
                .orderByDesc(Product::getId);

        Page<Product> page = this.page(new Page<>(current, size), wrapper);

        // 实体 → VO
        List<Product> records = page.getRecords();
        List<ProductVO> voList = new ArrayList<>();
        for (Product p : records) {
            ProductVO vo = new ProductVO();
            BeanUtils.copyProperties(p, vo);
            voList.add(vo);
        }
        fillNames(voList, records);

        // 分页元信息换壳：total/current/size 搬到 Page<ProductVO> 上
        Page<ProductVO> voPage = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        voPage.setRecords(voList);
        return voPage;
    }

    /**
     * 批量补齐 categoryName / brandName：
     * 先收集 id → 各查一次（批量）→ 内存配对。
     * 千万别在 for 循环里一条条 selectById —— 5 条记录查 10 次库，就是典型的 N+1。
     */
    private void fillNames(List<ProductVO> voList, List<Product> records) {
        if (records.isEmpty()) {
            return;
        }
        // 1. 收集本页出现过的 id（去重）；brand_id 可空，要挡
        Set<Long> categoryIds = new HashSet<>();
        Set<Long> brandIds = new HashSet<>();
        for (Product p : records) {
            categoryIds.add(p.getCategoryId());
            if (p.getBrandId() != null) {
                brandIds.add(p.getBrandId());
            }
        }

        // 2. 各查一次。selectByIds(集合) = WHERE id IN (...)
        Map<Long, String> categoryNames = new HashMap<>();
        for (Category c : categoryMapper.selectByIds(categoryIds)) {
            categoryNames.put(c.getId(), c.getName());
        }
        Map<Long, String> brandNames = new HashMap<>();
        if (!brandIds.isEmpty()) {
            for (Brand b : brandMapper.selectByIds(brandIds)) {
                brandNames.put(b.getId(), b.getName());
            }
        }

        // 3. 内存配对。brandId 为 null 时 get 返回 null → brandName 留空，合法
        for (int i = 0; i < records.size(); i++) {
            Product p = records.get(i);
            voList.get(i).setCategoryName(categoryNames.get(p.getCategoryId()));
            voList.get(i).setBrandName(brandNames.get(p.getBrandId()));
        }
    }

    @Override
    public ProductDetailVO getDetail(Long id) {
        Product product = this.getById(id);
        if (product == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }

        ProductDetailVO vo = new ProductDetailVO();
        BeanUtils.copyProperties(product, vo);

        // 分类名（category_id 非空约束，理论必有；仍按防御式判 null）
        Category category = categoryMapper.selectById(product.getCategoryId());
        if (category != null) {
            vo.setCategoryName(category.getName());
        }

        // 品牌名（brand_id 可空）
        if (product.getBrandId() != null) {
            Brand brand = brandMapper.selectById(product.getBrandId());
            if (brand != null) {
                vo.setBrandName(brand.getName());
            }
        }

        // SKU 列表
        List<ProductSku> skus = productSkuMapper.selectList(new LambdaQueryWrapper<ProductSku>()
                .eq(ProductSku::getProductId, id)
                .orderByAsc(ProductSku::getId));
        List<SkuVO> skuVos = new ArrayList<>();
        for (ProductSku sku : skus) {
            SkuVO sv = new SkuVO();
            BeanUtils.copyProperties(sku, sv);
            skuVos.add(sv);
        }
        vo.setSkus(skuVos);

        // 图集（按 sort_order 升序 → 前端轮播顺序）
        List<ProductImage> images = productImageMapper.selectList(new LambdaQueryWrapper<ProductImage>()
                .eq(ProductImage::getProductId, id)
                .orderByAsc(ProductImage::getSortOrder));
        vo.setImages(images.stream().map(ProductImage::getImageUrl).toList());

        return vo;
    }
}
```

> **两个 API 都已对本机 Maven 仓库里的 mybatis-plus 3.5.17 真实 jar 验证过：**
> - `BaseMapper.selectByIds(Collection<? extends Serializable>)`：3.5.17 里叫 `selectByIds`（老教程的 `selectBatchIds` 在这个版本已不是主推写法）；
> - `eq(boolean, column, val)` / `like(boolean, ...)`：Wrapper 的"条件重载"确实存在——条件为 false 该片段不进 SQL，省掉一堆 if。

---

## 8. 第 6 步：ProductController（替换占位类）

`mall-product` 里躺着一个 Day 02 留下的空壳 `ProductController.java`（只有空类体）。**整体替换**为：

```java
package com.mallx.product.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 商品接口（本日只做「看」；管理端「管」的写接口等鉴权后补） */
@Tag(name = "商品")
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @Operation(summary = "商品分页列表（上架中，可按分类/关键词过滤）")
    @GetMapping
    public Result<PageResult<ProductVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword) {
        Page<ProductVO> voPage = productService.pageProducts(current, size, categoryId, keyword);
        return Result.ok(PageResult.of(voPage));
    }

    @Operation(summary = "商品详情（分类/品牌名 + SKU + 图集）")
    @GetMapping("/{id}")
    public Result<ProductDetailVO> detail(@PathVariable Long id) {
        return Result.ok(productService.getDetail(id));
    }
}
```

> 本工程 `PageResult.of(IPage<T>)`（Day 04 实际落地签名）吃一切 `Page<T>`，所以 `Page<ProductVO>` 直接传。

---

## 9. 第 7 步（进阶可选）：点父分类带出子分类

**问题**：种子数据里所有商品都挂在子分类（11/21）上，所以 `GET /api/products?categoryId=1`（父分类"手机通讯"）目前返回 **0 条**——但用户点"手机通讯"显然想看到所有手机。把"精确 eq"升级成"父 + 所有子孙 in"。

**ProductServiceImpl 里加一个私有方法**：

```java
/**
 * 进阶：把一个 categoryId 扩展成「它自己和它所有子孙」的 id 集合。
 * 分类量很小，全量查一次内存配对即可；selectList(null) 表示无过滤条件 = 全表。
 * 注意：Java 实参先求值——wrapper 里写 expandCategoryIds(categoryId) 时它总会执行，
 *       所以 null 必须在方法内部挡掉，不能指望外层的条件布尔重载。
 */
private Set<Long> expandCategoryIds(Long categoryId) {
    Set<Long> ids = new HashSet<>();
    if (categoryId == null) {
        return ids;
    }
    ids.add(categoryId);
    for (Category c : categoryMapper.selectList(null)) {
        if (categoryId.equals(c.getParentId())) {
            ids.add(c.getId());
        }
    }
    return ids;
}
```

**pageProducts 的 wrapper 里改一行**（其余不动）：

```java
// 把 .eq(categoryId != null, Product::getCategoryId, categoryId) 替换为：
.in(categoryId != null, Product::getCategoryId, expandCategoryIds(categoryId))
```

> 这 8 行是全文档唯一使用"递归思维"的地方。两层分类用"找一遍孩子"就够；如果将来分类到三级，把循环换成"队列逐层下钻"即可——留给你自己改造（提示：`ArrayDeque<Long>`）。

---

## 10. 构建与验收

```bash
cd D:\MallX\backend\mallx
bash mvnw.sh package
java -jar mall-server/target/mall-server-0.0.1-SNAPSHOT.jar --server.port=8080
```

逐项跑（对照第 0 章验收标准）：

```bash
# 1) 旧接口不回归
curl http://localhost:8080/api/hello

# 2) 分类树：3 根节点各挂子分类
curl http://localhost:8080/api/categories/tree

# 3) 商品分页：total=5，共 5 条（按 id 倒序）；records[0]=Apple MacBook Air M3（id=5，最新在前）、
#    每条都带 categoryName/brandName（如 id=1 Apple iPhone 17 Pro → 智能手机 / Apple）
curl "http://localhost:8080/api/products?current=1&size=10"

# 4) 按子分类精确过滤：3 条（iPhone/Mate80/小米15）
curl "http://localhost:8080/api/products?categoryId=11"

# 5) 按父分类：改造前进阶=0 条；做完第 9 步后=3 条（1 手机通讯 → 11,12）
curl "http://localhost:8080/api/products?categoryId=1"

# 6) 关键词：1 条
curl "http://localhost:8080/api/products?keyword=iPhone"

# 7) 详情：categoryName=智能手机、brandName=Apple、skus 3 条（IP17P-*）、images 2 张
curl http://localhost:8080/api/products/1

# 8) 详情 404：统一 JSON {"code":404,"message":"商品不存在","data":null}
curl http://localhost:8080/api/products/99999
```

**Swagger 人工检查**：浏览器开 `http://localhost:8080/swagger-ui.html`，应出现「商品」「商品分类」两个分组，详情/分页参数说明齐全。

**注意**：今天是纯读接口，数据库不会有任何写入——这本身就是验收项（跑完后再执行第 2.1 的 count 语句，数字应与跑之前一致）。

---

## 11. 常见卡点速查

| 现象 | 原因 / 解法 |
|---|---|
| 编译报「程序包 `com.baomidou.mybatisplus.extension.service` 不存在」 | 3.5.17 老坑复发：`IService/ServiceImpl` 必须用 `com.baomidou.mybatisplus.spring.service(.impl)` |
| `selectByIds` 方法找不到/想用老写法 | 3.5.17 用 `selectByIds(Collection)`（本机 3.5.17 jar 已验证）；`selectBatchIds` 是旧版写法 |
| `copyProperties` 拷了没反应 | 导错包：要 `org.springframework.beans.BeanUtils`（Spring 的参数是 源,目标）；Apache Commons 的 BeanUtils 参数顺序相反 |
| 建树报 NPE | `groupingBy` 的 key 直接用了可空的 parentId → 先把 null 映射成哨兵值 -1L 再分组 |
| 分页 data 里 records 正确但 total=0 | 直接把实体 Page 的 records 换成 VO 列表但没搬 total —— 必须用 `new Page<>(current, size, total)` 换壳 |
| `PageResult.of` 编译不过 | 本工程签名是 `of(IPage<T>)`（与 Day-04 文档里的 `Page<T>` 版本不同），传 `Page<ProductVO>` 即可 |
| 进阶 `in` 报 NPE | Java 实参先求值：`expandCategoryIds(null)` 会先执行 → null 判断要写在方法内部 |
| 想顺手 save 一个 SKU 却报类型错误 | `attributes` 是 String 写 JSONB 列，PG 拒绝隐式转换——JSONB 写入需要 TypeHandler，本日只读 |
| 新接口 404 | ProductController 占位类没替换 / Controller 不在 `com.mallx.product.controller` 包 / jar 没重新打包就启动了 |
| Mapper 注入报 bean 找不到 | Mapper 接口的包必须以 `.mapper` 结尾（`@MapperScan("com.mallx.**.mapper")`），且全量重新 package |

---

## 12. 本日成果自检清单

- [ ] mall-product：entity×5、mapper×5、vo×4、service×4、controller×2（含替换占位类）全部落位
- [ ] 零 POM 改动、零 SQL 改动（读接口日）
- [ ] 编译通过、应用启动、第 10 章全部 curl 符合预期
- [ ] Swagger 出现「商品」「商品分类」分组
- [ ] 理解并口述三件套：VO 为什么要存在 / N+1 是什么怎么防 / 平铺表怎么内存建树
- [ ] Git 提交（建议信息：`feat: Day 05 商品模块 - 分类树/商品分页筛选/详情(分类品牌名+SKU+图集)`）

---

## 13. 做完之后

把今天刻意不做的写接口列出来，就是路线 A 的需求清单：

```text
POST   /api/products        新增商品   —— 谁在操作？管理端只有管理员能做
PUT    /api/products/{id}   改价/上下架 —— 改错了要能追责
DELETE /api/products/{id}   删除      —— 不可逆，更要身份
```

再往前看一步：订单要有 `user_id`、购物车要挂在人身上、评价不能匿名刷——**这些全都卡在"系统认不出你是谁"**。

B 验收通过后告诉我，我出《Day-06-登录鉴权(JWT)》规划文档（分步+模板+避坑，含 Spring Boot 4.x Security 配置差异、BCrypt 存量数据处理、jjwt 选型这些坑位）。
