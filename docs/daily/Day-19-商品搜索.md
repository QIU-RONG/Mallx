# Day 19 — 商品搜索（PostgreSQL 全文 / trgm / JSONB）

> 承接 Day 18（管理端商品与分类）收官。本日**首次启用 Day 03 埋下、却一次都没被调用过的三件 PG 利器**。
> 模式：陪练 —— AI 出规划 + 骨架 + 验收器，**实现由你亲手写**。

---

## 一、本日范围（已拍板）

| 项 | 决定 |
|---|---|
| 做什么 | C 端新增**搜索入口** `GET /api/products/search`：关键词检索 + 分类过滤 + SKU 属性筛选 |
| 用什么 | `products.search_vector`（tsvector + GIN）、`products.name`（pg_trgm + GIN）、`product_skus.attributes`（JSONB + GIN） |
| **不做什么** | ★ **不改既有 `GET /api/products`** —— 它被 M1 回归 198 条断言逐字节守门，改它 = 动基线 |
| 顺带做什么 | 保留 C 端旧 `keyword`（LIKE 版）当**对照组**，用数据打表说明两者差异 |
| 界面 | 沿用 V1.0 口径：Swagger UI |

**为什么不改造旧接口，宁可新增一个**：旧 `page()` 的 `keyword` 是 `LIKE '%kw%'`（Day 09 口径），
它被 198 条基线钉住了。**新增**是最小侵入，且留下对照组 —— 同一关键词两种检索各自返回几条，
这件事本身就是本日最有力的证据（见 §七 链路 B）。

---

## 二、现状盘点（已探明，勿重查）

| 利器 | 建在哪 | 现在谁在维护它 | 代码引用数 |
|---|---|---|---|
| `products.search_vector TSVECTOR` | `01-schema.sql:89` | ★ 触发器 `trg_products_search_vector` **自动**维护 | **0** |
| `idx_products_search`（GIN） | `02-index.sql:90` | — | **0** |
| `idx_product_skus_attributes`（GIN, `attributes` JSONB） | `02-index.sql:83` | — | **0** |
| `idx_products_name_trgm`（GIN, `gin_trgm_ops`） | `02-index.sql:97` | — | **0** |
| `pg_trgm` 扩展 | `01-schema.sql:15` | — | **0** |

触发器给 `search_vector` 填的内容（`01-schema.sql:375-382`）：

```text
search_vector = setweight(to_tsvector('simple', name),        'A')   -- 权重最高
             || setweight(to_tsvector('simple', subtitle),    'B')
             || setweight(to_tsvector('simple', description), 'C')   -- 权重最低
```

★ **数据已经躺在库里了** —— `03-data.sql` 那 5 个商品插进去的瞬间，`search_vector` 就被写好了。
本日做的不是「建索引」，而是**第一次去读它**。

现存商品（`03-data.sql:49-57`）—— 注意名字是**大小写混合**：

| id | name | subtitle |
|---|---|---|
| 1 | `Apple iPhone 17 Pro` | 钛金属边框 3nm A19 Pro 芯片 |
| 2 | `Huawei Mate 80 Pro` | 卫星通信 麒麟芯片 徕卡影像 |
| 3 | `Xiaomi 15 Ultra` | 徕卡光学 一英寸大底 |
| 4 | `Lenovo ThinkPad X1 Carbon` | 商务轻薄本 2.2K 屏 |
| 5 | `Apple MacBook Air M3` | 8GB 统一内存 轻至 1.24kg |

SKU 属性（`product_skus.attributes`，JSONB，**值是中文**）：

```json
{"color":"黑色","storage":"256GB","ram":"8GB"}     -- sku 1,2
{"color":"原色钛金属","storage":"512GB","ram":"8GB"} -- sku 3
{"cpu":"Core i7","ram":"16GB","storage":"512GB"}    -- sku 6（笔记本）
{"chip":"M3","ram":"8GB","storage":"256GB"}         -- sku 7（笔记本）
```

---

## 三、★ 核心认知：三者不是「三选一」，是**分工**

这是本日最值钱的一张表 —— 每种手段的**边界**都是可实测的：

| 手段 | 强项 | 弱项（★ 必须记住） | 吃哪个索引 |
|---|---|---|---|
| `LIKE '%kw%'` | 中文子串也能搜 | ① **大小写敏感**；② **前导通配符让索引彻底失效**（必全表扫） | 无 |
| `search_vector @@ plainto_tsquery` | 英文按**词**命中、**大小写不敏感**、能用 `ts_rank` 排出**相关性** | `simple` 字典**不切中文** → 中文只能「整段 token」命中 | `idx_products_search` |
| `name % kw`（pg_trgm） | 走 GIN 的**索引化模糊匹配**；短词对长名有效 | 是「**整体相似**」不是「子串包含」；只覆盖建了索引的那一列 | `idx_products_name_trgm` |
| `attributes @> jsonb_build_object(k,v)` | 规格属性**精确等值**筛选，含中文值 | 只能等值，不能范围（`price > x` 它管不了） | `idx_product_skus_attributes` |

### 3.1 三个必须实测确认的坑

**坑 1：`LIKE` 大小写敏感** ⇒ 搜 `iphone` 对 `Apple iPhone 17 Pro` **返回 0 条**。
这不是 bug，是 SQL 标准行为（要忽略大小写得用 `ILIKE`）。而 `search_vector` 里存的是
`simple` 字典小写化后的 `iphone`，**照样命中**。→ 本日核心对照实验。

**坑 2：`simple` 字典不切中文**。`to_tsvector('simple', '商务轻薄本 2.2K 屏')` 按**空白和标点**分词：

```text
['商务轻薄本', '2.2k', '屏']      ← "商务" "轻薄本" 都不是 token
```

所以搜 `商务` **搜不到**商品 4 —— 因为 `tsquery` 匹配的是**完整 lexeme**，不做部分匹配。
中文要真正分词得装 `zhparser` / `pg_jieba`（V1.0 不引入，如实记录为已知限制）。

**坑 3：`plainto_tsquery` vs `to_tsquery`**。用户输入不可信：

| 输入 | `to_tsquery('simple', ?)` | `plainto_tsquery('simple', ?)` |
|---|---|---|
| `iphone &` | ★ **抛错** `syntax error in tsquery` | 安全：当成纯文本 `iphone` |
| `a \| b` | 当成「a 或 b」的**语法** | 当成两个普通词 |
| `!'` | 抛错 | 安全 |

⇒ **必须用 `plainto_tsquery`**：把用户输入当**纯文本**，不做语法解析。这是一条安全边界，不是风格偏好。

### 3.2 由 3.1 推出的接口设计（唯一自洽的那种）

矛盾在这里：**中文要能搜到**（只能靠 `ILIKE`，但它没索引）＋ **英文要能排序**（只能靠全文）。
第一版选择「**全文负责英文命中与排序，ILIKE 负责中文兜底**」：

```text
keyword 的召回 = search_vector @@ plainto_tsquery(...)     -- 英文 + 相关性排序
              OR name      ILIKE '%kw%'                    -- 中文/子串兜底
              OR subtitle  ILIKE '%kw%'
```

★ 诚实记录代价：**两条 `ILIKE` 会把整条查询拖回全表扫描**（5 行数据无所谓；真上量时
正确做法是把 `name || ' ' || subtitle` 建成**表达式 trgm 索引**，再换成 `%` 运算符 ——
但那是 Day 19 之后的事，本日不引入，避免一次做两件事）。

---

## 四、接口设计

```
GET /api/products/search
  ?keyword=iphone                可选：关键词
  &categoryId=11                 可选：分类过滤
  &attrKey=color&attrValue=黑色   可选：SKU 属性筛选（★ 必须成对）
  &current=1&size=10             分页
```

返回：`Result<PageResult<ProductSearchVO>>`

| 字段 | 说明 |
|---|---|
| `id` / `name` / `subtitle` / `mainImage` | 列表卡片要的 |
| `categoryId` / `categoryName` | 走 `LEFT JOIN categories` |
| `minPrice` | 子查询取该商品**在售未删** SKU 的最低价 |
| `searchRank` | `ts_rank(...)`，★ 无关键词时为 0 |

### 4.1 ★ 路径冲突：`/api/products/search` vs `/api/products/{id}`

两个映射都能匹配这个 URL，谁赢？**Spring 的 `PathPattern` 规则是「字面量优先于变量」** ⇒
`search` 会命中搜索方法，而不是被当成 `id=search`。

★ 但**必须实测**，不能靠背规则。好在项目里已有现成的判据（`GlobalExceptionHandler`）：

| 实际路由 | 抛什么 | 客户端收到 |
|---|---|---|
| 命中 `search`（骨架期 `throw`） | `UnsupportedOperationException` | **`code=500`** |
| 落到 `{id}`（`"search"` → `Long` 失败） | `MethodArgumentTypeMismatchException` | **`code=400`** + `"参数 id 格式不正确"` |

⇒ **骨架期打一次 `/api/products/search`，看是 500 还是 400，就知道谁优先。**
（Day 18 补的 `MethodArgumentTypeMismatchException` 专用 handler，本日正好当尺子用。）

### 4.2 权限：不用改 `SecurityConfig`

C 端白名单里已有 `GET /api/products/**`，`/**` 匹配任意深度 ⇒ `/api/products/search` **自动公开**。
这与 Day 18 的红线（管理端接口绝不能挂在白名单路径下）正好是一体两面：**这里挂 C 端是对的**。

---

## 五、SQL 设计（7 个要点，写 XML 时逐条对照）

**① 必须手动补 `p.is_deleted = 0`** ★★
`Product` 实体上有 `@TableLogic`，**但手写 XML 不受它管辖**。
这件事 Day 18 刚遇到过，结论正好相反：

| | Day 18 `countByCategoryId` | Day 19 `searchProducts` |
|---|---|---|
| 目的 | 统计**含**软删（外键不认 `is_deleted`，计数口径要跟外键一致） | 只搜**未删** |
| 做法 | **绕开** `@TableLogic` 的自动追加 | **手动补上** `p.is_deleted = 0` |

⇒ 判据统一为一句：**手写 XML 里 `is_deleted` 的取舍，由「这条 SQL 的语义」决定，不由实体决定。**

**② 手写 XML 也不受 `@TableLogic` 保护** —— 漏写就是「已删除的商品能搜出来」，且**不报错**。

**③ keyword 归一化放在 Service**（`null → ""`、`trim`），XML 里只判 `!= ''`。
★ 不要写 `#{keyword} IS NULL`：MyBatis 对 `null` 参数会 `setNull(JdbcType.OTHER)`，
PostgreSQL 会报 **`could not determine data type of parameter`** —— 这是 PG 特有的坑。
把 null 在 Java 侧消掉，SQL 侧就只剩一种形态。

**④ `ORDER BY search_rank DESC, p.id ASC`**（`p.id` 兜底保证**顺序稳定**，同库存对账视图的思路）。
★ `rank` 是 **PostgreSQL 保留字**，不能直接当列别名 → 用 `search_rank`，Java 字段 `searchRank`（下划线自动映射）。

**⑤ 别名一律下划线**（`main_image AS main_image`）。写成 `AS mainImage` 会被 PG 折成
`mainimage` → 字段**静默为 null**、不报错。这条已在 `InventoryMapper.xml` 反复标红。

**⑥ JSONB 筛选必须用 `jsonb_build_object(#{attrKey}, #{attrValue})`**，
**禁止**拼字符串（`'{"' || #{k} || '":...'`）—— 那是注入口 + 转义地狱。
属性筛选是「商品**任一在售未删 SKU** 匹配」⇒ 用 `EXISTS (SELECT 1 FROM product_skus ...)`，别 JOIN（会因多 SKU 产生**重复行**，把分页总数打乱）。

**⑦ 分页**：Mapper 方法是**首参 `IPage`**，XML 里**不写** `LIMIT/OFFSET`（分页插件靠首参改写 SQL）。
照抄 `InventoryMapper.selectInventoryPage` 的形状。★ 夹紧（`current ≥ 1`、`size ∈ [1,100]`）在 **Service**，
且必须在 `new Page<>(...)` **之前**。

---

## 六、骨架清单

| 文件 | 动作 | TODO |
|---|---|---|
| `vo/ProductSearchVO.java` | 新建（完整给全，数据容器没有"要你写的逻辑"） | 0 |
| `product/mapper/ProductMapper.java` | 加 `searchProducts` 声明 + Javadoc 要点 | 0 |
| `resources/mapper/ProductMapper.xml` | 加 `<select id="searchProducts">` 占位 | **1 ← 本日主菜** |
| `product/service/ProductService.java` | 加方法声明 + Javadoc | 0 |
| `.../service/impl/ProductServiceImpl.java` | 加方法体（归一化 + 夹紧 + 调用） | **1** |
| `product/controller/ProductController.java` | 加 `GET /search` 端点（一行转发） | **1** |

合计 **3 处 TODO**。比 Day 18 的 14 处少，因为本日的重活集中在**一条 SQL** 上 ——
那条 SQL 要同时处理全文、ILIKE、JOIN、EXISTS、排序、别名六件事。

---

## 七、验收清单（逐条落成断言）

| 链路 | 内容 | 关键断言 |
|---|---|---|
| **A 路由/骨架** | `/api/products/search` 命中谁 | ★ `code=500`（**不是 400**）⇒ 字面量优先于 `{id}` |
| **B ★核心对照** | `keyword=iphone` | 新接口 **≥1 条**（含商品 1）；旧接口 `GET /api/products?keyword=iphone` **0 条** ⇒ 大小写铁证 |
| **C 相关性** | `keyword=徕卡` | 商品 2/3 命中，且 `searchRank` 降序可断言 |
| **D JSONB 属性** | `attrKey=color&attrValue=黑色` | 命中商品 1；换 `attrValue=原色钛金属` 命中商品 1（sku 3） |
| **E 中文边界** | `keyword=笔记本` | ★ **如实打表**：全文 0 条 / ILIKE 2 条（商品 4、5）⇒ 记录 `simple` 字典限制 |
| **F 健壮性** | ① `attrKey` 单给 → `code=400`；② `keyword=iphone & \| !` → **不 500**（`plainto_tsquery` 的证据）；③ `size=999` → 夹到 100；④ `size=0/-1` | 逐条断言 |
| **G 索引** | `EXPLAIN` 三件索引 | ★ 见下方「小表陷阱」说明 |
| **H M1 回归** | `day17-m1-regression.py` | **198/198** + `BASELINE RESTORED YES` |

### ★★ 链路 G 的「小表陷阱」（不写清楚会白忙一场）

**5 行数据的表上，PostgreSQL 规划器一定选 Seq Scan** —— 全表扫描比「读索引再回表」便宜。
所以直接在 5 行数据上跑 `EXPLAIN` 看不到 GIN 索引，**这不是做错了**。

正确验法（零写入，不污染库）：

```sql
SET LOCAL enable_seqscan = off;   -- 只是「逼」规划器暴露备选方案，不是生产做法
EXPLAIN SELECT ... ;
```

断言计划里出现 `Bitmap Index Scan on idx_products_search` ⇒ 证明**索引本身可用**。
同时诚实记录：真实数据量到几万行时，规划器会**自己**改选索引。

★ 绝不为了"让 EXPLAIN 好看"往库里插几千行测试数据 —— Day 18 的污染事故（误建商品 31 / 分类 36-37）
就是这么来的。**验收脚本一律零写入。**

---

## 八、风险与注意

1. **XML 注释不能出现连续两个减号**（`--`）→ `SAXParseException`，**启动才炸**，编译期不报。
   在 XML 里写 SQL 说明时特别容易踩（比如 `IN (1,2) -- 说明`）。
2. **`resultType` 的 VO 必须有无参构造**（`@Data` 已足够；显式写 `@NoArgsConstructor` 更保险）。
3. 本日**不改** `02-index.sql`。若后续要做表达式 trgm 索引，那是独立一步（改索引脚本要重跑且幂等）。
4. **不要动 `GET /api/products`**（M1 基线）；新增端点不在 M1 覆盖范围内，但 M1 仍必须跑绿。
5. `search_vector` 是**触发器**维护的 ⇒ 商品名改了它会自动跟着变，**只有绕过触发器的写入
   （如直接 `UPDATE ... SET search_vector`）才会不同步** —— 本日不碰。
6. 起应用验收时：端口**显式** `--server.port=8080`，「起应用 + 跑完验收」**必须在同一轮内**完成。
