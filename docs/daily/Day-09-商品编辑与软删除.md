# Day 09：商品编辑与软删除 —— 差分更新 + 逻辑删除

> **前置**：Day 08 已完成（提交 `cb8230c`）。商品可以"一次建全套"：商品主表 + N 个 SKU + M 张图，三张表一个事务。
> **今天**：把商品模块**真正闭环** —— 改得动、删得掉。
> **主线**：`@Transactional` 的进阶用法（差分更新） + 软删除（逻辑删除）。

---

## 0. 今日目标

三句话：

```text
① DELETE 从"物理删除"改成"软删除" —— 实测发现，物理删除这条路上有一堵撞不穿的墙
② PUT 从"只改主表"升级到"能改 SKU 和图集" —— 难点不在写 SQL，在"哪些该插、哪些该改、哪些该删"
③ 顺手拍板一个已经存在的设计矛盾：这个 PUT 到底是"整体覆盖"还是"局部更新"
```

完成标准（每条都能在 §8 验收里对到编号）：

| # | 标准 | 验收项 |
|---|---|---|
| 1 | `DELETE /api/products/1`（带 3 SKU + 3 行库存的种子商品）从 **500 → 200** | [1] [2] |
| 2 | 删除后主表行**还在**（`is_deleted=1`），子表一行没少 | [3] [4] |
| 3 | `GET /api/products/1` 自动 404，列表里也不再出现 | [5] [6] |
| 4 | `PUT` 能改 SKU 价格、能加 SKU、能去掉 SKU | [8] [9] [10] |
| 5 | 伪造别人的 SKU id 改不动别人的数据 | [11] |

### 为什么是今天这件事

Day 08 收尾时我说过"商品模块闭环了"——**那句话不完全对**。

当时只验收了"新建"。删除只用**刚建出来的测试商品**测过（`id=11/14/15`），那些商品的库存表里没有行，所以删得干净利落。

今天拿**种子商品**试一下，立刻就炸。

而且这一炸，暴露的不是一个 bug，是**一个设计层面的结论**。

---

## 1. 今日思路

### 1.1 ★ 先看实测：删商品 1 → 500

环境沿用 Day 08（应用 8080 + PG 5434 都在跑）。基线：

```text
products 5 | product_skus 7 | product_images 4 | inventories 7 | reviews 0 | cart_items 0
```

拿 admin token 打 `DELETE /api/products/1`：

```text
HTTP=200  code=500  msg=fail
```

> ⚠️ `HTTP 200` + body 里的 `code:500` —— 这是本项目的约定：**业务异常统一返回 HTTP 200，只有 Security 层的 401/403 是真 HTTP 状态码**（Day 07 的遗留思考题）。
> 所以判断成败永远要**看 body 里的 code**，不能看 HTTP 状态码。

日志里的真话：

```text
### Cause: org.postgresql.util.PSQLException: ERROR: update or delete on table "product_skus"
violates foreign key constraint "fk_inventory_sku" on table "inventories"
```

注意它连 `product_skus` 都删不掉 —— 还没走到 `product_images`，更没走到 `reviews`。

好消息是 `@Transactional` 又救了一次：删失败 → 整体回滚 → 商品 1 完好如初。

```text
p1 | s1 | i1
 1 |  3 |  2      ← 商品在、3 个 SKU 在、2 张图在。什么都没少。
```

**记住这个感觉：事务负责"失败不留痕"，但事务不能"让不可能的事变可能"。**

### 1.2 外键全景图：为什么种子商品一个都删不掉

项目 22 张表、**22 条外键**。和商品相关的这一段是这样：

```text
                  categories ─┐
                              │ fk_product_category
                   brands ────┼──►  products  ◄─────┐
                              │                    │ fk_review_product
      ┌───────────────────────┴──────────┐         │
      │ fk_sku_product     fk_product_image_product │
      ▼                                  ▼         ▼
  product_skus                   product_images   reviews
   (7 行)                          (4 行)         (0 行)
      │      ▲                   ★ 无人引用它
      │      └───────┐
      │              │
 fk_inventory_sku  fk_cart_sku
      ▼              ▼
  inventories     cart_items
   (7 行)          (0 行)
```

摊成表格，三个层次一目了然：

| 表 | 谁指着它 | 当前行数 | 能不能物理删 |
|---|---|---|---|
| `products` | `product_skus` / `product_images` / `reviews` | 5 | ❌ 撞外键 |
| `product_skus` | `inventories`（7 行）/ `cart_items`（0 行） | 7 | ❌ 撞外键 |
| `product_images` | **没有任何表引用它** | 4 | ✅ 随便删 |

**5 个种子商品，每一个都有 `inventories` 行**（1 SKU 1 行库存，卖货的前提）：

| id | 商品 | SKU | 图 | 库存行 |
|---|---|---|---|---|
| 1 | Apple iPhone 17 Pro | 3 | 2 | 3 |
| 2 | Huawei Mate 80 Pro | 1 | 1 | 1 |
| 3 | Xiaomi 15 Ultra | 1 | 1 | 1 |
| 4 | Lenovo ThinkPad X1 Carbon | 1 | 0 | 1 |
| 5 | Apple MacBook Air M3 | 1 | 0 | 1 |

所以：**这 5 个商品一个都删不掉**。能删的只有 Day 08 之后新建的、还没进过库存的商品。

> **Day 08 验收为什么没发现？** 因为删的是 `id=11/14/15` —— 刚建出来、`inventories` 里没有它们 SKU 的测试数据。
>
> 还是同一句话，这次换了个说法：**子表空跑得通 ≠ 逻辑对。**

### 1.3 结论：物理删除这条路上有一堵撞不穿的墙

想一个真实上线的电商系统：

```text
商品被买过   → order_items 引用它
商品被评过   → reviews 引用它
商品有库存   → inventories 引用它的 SKU
商品被人加购 → cart_items 引用它的 SKU
```

**只要商品"被使用过"，它就永远删不掉了。** 而且这是对的 —— 后台管理员点一下"删除"，凭什么把三个月前的订单明细也一起抹掉？用户翻历史订单会看到一堆"未知商品"。

所以真实电商系统里，"删除"其实是两件不同的事：

```text
"下架" = 业务问题  → status = 0，商品还在，只是不卖
"删除" = 数据问题  → 数据必须留着（订单要引用），但对用户"看不见"
```

这就是**软删除**（也叫逻辑删除 / Soft Delete）：**不执行 DELETE，改成 UPDATE 一个标记位。**

```text
物理删除： DELETE FROM products WHERE id = 1        ← 撞外键，而且真的丢数据
软删除：   UPDATE products SET is_deleted = 1 WHERE id = 1
           ↑ 没有 DELETE 语句 → 外键根本不会被触发
```

> **今天最重要的机制，一句话记住：软删除绕过了外键 —— 不是绕过约束，而是根本没有 DELETE 动作。**

### 1.4 第二个缺口：PUT 改不到 SKU 和图集

`ProductUpdateDTO` 现在只有 5 个字段：

```java
name / subtitle / description / mainImage / status
```

所以 `PUT /api/products/1` **改得了标题，改不了价格**（价格在 SKU 上），也**改不了图集**。

这不是小事：一个商品后台，最常改的就是"价格"和"图片"。

难点不在"多写几张表的 update"，而在于：

```text
客户端这次提交了 3 个 SKU，库里原来有 5 个。请问：
  · 库里那 5 个，哪些要改？（靠什么认出"这一个是那一个"）
  · 哪些是这次新增的？
  · 库里 5 个里本次没出现的 2 个 —— 是"删掉"，还是"这次不想动它"？
```

**这就是差分更新（diff update）**：不是简单地 INSERT 或 UPDATE，而是**把"库里的状态"和"客户端想要的状态"对齐**。

它是多表写入里最容易写出脏数据的地方，也是今天真正的主课。

### 1.5 今天要改 / 新增的文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `backend/sql/01-schema.sql` | 改 | `products` / `product_skus` 各加一列 `is_deleted` |
| `…/product/entity/Product.java` | 改 | 加 `isDeleted` 字段 + `@TableLogic` |
| `…/product/entity/ProductSku.java` | 改 | 同上 |
| `…/product/dto/SkuUpdateDTO.java` | **新建** | 比 `SkuCreateDTO` 多一个 `id` |
| `…/product/dto/ProductUpdateDTO.java` | 改 | 加 `images` + `skus`；摘掉 `name` 上的 `@NotBlank` |
| `…/product/service/impl/ProductServiceImpl.java` | 改 | `deleteProduct` 简化成一行；`updateProduct` 重写 |
| `docs/daily/Day-09-*.md` | 本文档 | |

**不改的**：`ProductController`（路径不变）、`ProductService` 接口（`updateProduct` / `deleteProduct` 签名不变）、任何 `pom.xml`。

> 接口不变、签名不变，只是"内部从假实现换成真实现"。
> **这是好设计的表现：调用方一无所知。**

### 1.6 今天的三个决策点

三个都要你拍板，我给了建议和理由：

| # | 决策 | 建议 | 在哪 |
|---|---|---|---|
| A | 用什么列标记删除：`is_deleted` / `deleted_at` / 复用 `status` | `is_deleted SMALLINT DEFAULT 0` | §3.1 |
| B | 删商品时，子表（SKU / 图集）要不要跟着删 | **一行都不动** | §5.2 |
| C | 差分更新里靠什么认人：`sku.id` 还是 `sku.sku_code` | **用 `id`** | §6.2 |

---

## 2. 第 0 步：前置检查（15 分钟）

### 2.1 起环境

```powershell
# Docker Desktop（若已退出，用 explorer 拉起 —— Start-Process 会被沙箱杀掉）
& explorer.exe "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"
# 等约 20s，然后验通（★ 必须用 Test-NetConnection，Get-NetTCPConnection 永远是假的）
Test-NetConnection 127.0.0.1 -Port 5434 -InformationLevel Quiet

# 应用（改动前先杀干净，Maven 父进程 + fork 的 java 子进程都要杀）
Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
    Where-Object { $_.CommandLine -match 'mall|spring-boot' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Set-Location D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o spring-boot:run -pl mall-server `
    "-Dspring-boot.run.arguments=--server.port=8080"
```

> ⚠️ `--server.port=8080` 必须显式写。会话注入的 `SERVER__PORT` 会经 relaxed binding 盖过 `application.yml`。

### 2.2 记下基线

**必须 `count(*)` 实查**，不要看 `pg_stat_user_tables.n_live_tup`（估算值滞后，Day 08 被它坑过一次）：

```powershell
$dx = "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
$q = "SELECT (SELECT count(*) FROM products) p, (SELECT count(*) FROM product_skus) s, (SELECT count(*) FROM product_images) i, (SELECT count(*) FROM inventories) v, (SELECT count(*) FROM reviews) r, (SELECT count(*) FROM cart_items) c;"
& $dx exec -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx -c $q
```

期望：

```text
 p | s | i | v | r | c
---+---+---+---+---+---
 5 | 7 | 4 | 7 | 0 | 0
```

### 2.3 ★ 先亲眼看见那个 500

**动手改之前，先把问题复现一遍。** 这一步只要两分钟，但它决定了你今天是不是"在修一个自己看见的问题"。

```powershell
$B = "http://localhost:8080"
$d = "D:\MallX\learning\day09"
New-Item -ItemType Directory -Force -Path $d | Out-Null

# 拿 admin token（记得落盘读，curl 在 PS 里 stdout 会折行）
& curl.exe -s --noproxy "*" -o "$d\admin-login.json" -X POST "$B/api/auth/admin/login" `
    -H "Content-Type: application/json" `
    --data-binary "@D:\MallX\learning\day08\admin-login.json"
$T = ((Get-Content "$d\admin-login.json" -Raw -Encoding utf8) | ConvertFrom-Json).data.token

# 删商品 1 —— 现在必然失败
curl.exe -s --noproxy "*" -X DELETE "$B/api/products/1" -H "Authorization: Bearer $T"
```

期望看到：

```json
{"code":500,"message":"fail","data":null}
```

去应用日志里搜 `foreign key`，确认是 `fk_inventory_sku`。

**然后再查一遍 2.2 的基线 —— 应该一模一样（事务回滚生效）。**

---

## 3. 第 1 步：给 products 加一列（20 分钟）

### 3.1 ★ 决策 A：三种"标记删除"的方案

| 方案 | 长什么样 | 优点 | 致命问题 |
|---|---|---|---|
| **A. `is_deleted SMALLINT DEFAULT 0`** | 0=正常，1=已删 | MyBatis-Plus 开箱支持，条件简单 | 记不住"什么时候删的" |
| B. `deleted_at TIMESTAMP NULL` | NULL=正常，有时间=已删 | 自带删除时间，能排序 | MP 要用 `@TableLogic(value="null", delval="now()")`，SQL 生成依赖字符串拼接，坑多 |
| C. 复用 `status` | 1=上架，0=下架，2=? | 不加列 | ❌ **语义打架**，见下 |

**为什么 C 一定不行 —— 三个理由，一个比一个硬：**

```text
① 语义不同：status 是"卖不卖"（业务），is_deleted 是"还在不在"（数据）
   后台需要能看到"下架商品"并重新上架；但"已删除商品"默认不该出现在任何列表里。
   混用 → "已删除"会伪装成"下架" → 后台想上架一个已删商品，一点就活过来。

② 值不够用：status 是 NOT NULL DEFAULT 0，而 0 已经是"下架"了。
   没有空闲值能表示"删除"（除非你约定 2=删除，那就等着某天有人写 status=2 表示"预售"）。

③ 组合爆炸：将来会有"删除 + 上架"、"不删 + 下架"、"删除 + 下架"……
   一个字段表达两件事，条件判断会写成 if(status==1 && is_deleted==0) 这种鬼东西。
```

> **通用原则：一个字段只表达一件事。** 当你发现自己在给字段的取值赋予"复合含义"（0 表示 A，1 表示 B，2 表示"A 且 B"），就该拆字段了。

**方案 B 的 `deleted_at` 更"专业"**，但今天**不推荐**：它要求 MP 生成 `SET deleted_at = now()` 和 `WHERE deleted_at IS NULL`，靠字符串配置拼 SQL，出问题不好查。初学者先走最稳的路。

**推荐：方案 A。** 而且已经用字节码核实过 MP 的默认值（见 §4.2）—— 加了注解**不用任何额外配置**就能跑。

> 想要"删除时间"怎么办？**两个都要**：`is_deleted` 给 MP 用，`deleted_at` 给自己看。
> 今天只在自检清单里留作可选，不强制。

### 3.2 改 `backend/sql/01-schema.sql`

**两处都要改**：`CREATE TABLE` 里加（给新库），文件末尾追加幂等 `ALTER`（给已存在的库）。

**① `products`（约第 79 行）：**

```sql
CREATE TABLE IF NOT EXISTS products (
    id            BIGSERIAL PRIMARY KEY,
    category_id   BIGINT       NOT NULL,
    brand_id      BIGINT,
    name          VARCHAR(200) NOT NULL,
    subtitle      VARCHAR(500),
    description   TEXT,
    main_image    VARCHAR(500),
    status        SMALLINT     NOT NULL DEFAULT 0,
    is_deleted    SMALLINT     NOT NULL DEFAULT 0,      -- ★ 新增：0=正常 1=已删除
    search_vector TSVECTOR,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_product_category FOREIGN KEY (category_id) REFERENCES categories(id),
    CONSTRAINT fk_product_brand    FOREIGN KEY (brand_id)    REFERENCES brands(id)
);
```

**② `product_skus`（约第 96 行）同样加一行** `is_deleted SMALLINT NOT NULL DEFAULT 0,`。

**③ 文件最末尾追加一段"幂等补丁"**（照 Day 08 序列校准那一段的风格）：

```sql
-- ============================================================
-- 十二、软删除列（Day 09 追加）
-- 说明：上面 CREATE TABLE IF NOT EXISTS 对已存在的库不会加列，
--       所以老库要靠这一段 ALTER 补齐；IF NOT EXISTS 保证重复执行不报错。
-- ============================================================

ALTER TABLE products     ADD COLUMN IF NOT EXISTS is_deleted SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE product_skus ADD COLUMN IF NOT EXISTS is_deleted SMALLINT NOT NULL DEFAULT 0;

-- 顺带给查询加索引（列表查询会带 is_deleted = 0）
CREATE INDEX IF NOT EXISTS idx_products_is_deleted     ON products(is_deleted);
CREATE INDEX IF NOT EXISTS idx_product_skus_is_deleted ON product_skus(is_deleted);
```

> 这段就是**手写迁移脚本（migration）的雏形**。真实项目用 Flyway / Liquibase 管这个，
> 核心思想一样：**每次改表结构，都留一个能重复执行的、带顺序的脚本。**

### 3.3 线上执行（不用重建库）

把上面那段 ALTER 存成文件再执行 —— PS 里传多行 SQL 用 `-i` 走 stdin：

```powershell
$dx = "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
Get-Content D:\MallX\learning\day09\day09-alter.sql -Raw |
    & $dx exec -i -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx
```

验证列真的加上了、且老数据默认值正确：

```powershell
$q = "SELECT id, name, is_deleted FROM products ORDER BY id;"
& $dx exec -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx -c $q
```

期望 5 行，`is_deleted` 全是 **0**（因为 `DEFAULT 0` 会回填到已有行）。

> ⚠️ **`NOT NULL DEFAULT 0` 的 ALTER 在 PG 11+ 是瞬时完成的**（只改元数据，不重写表）。
> 但如果是 `ADD COLUMN xxx VARCHAR` 且带复杂默认值，大表上会锁表 —— 生产环境要知道这件事。

---

## 4. 第 2 步：让 MyBatis-Plus 自动过滤（30 分钟）

### 4.1 `@TableLogic` 一句话原理

在实体字段上打一个注解，MP 会**改写它生成的每一条 SQL**：

```text
你写的代码                        MP 实际发给 PG 的 SQL
────────────────────────────────────────────────────────────────────
selectById(1)              →   SELECT ... FROM products WHERE id=1 AND is_deleted=0
selectList(wrapper)        →   SELECT ... FROM products WHERE (...) AND is_deleted=0
removeById(1)              →   UPDATE products SET is_deleted=1 WHERE id=1 AND is_deleted=0
updateById(p)              →   UPDATE products SET ... WHERE id=? AND is_deleted=0
```

**价值在哪？** 它把"记得加 `is_deleted = 0`"这件**必须做、又极容易忘**的事，从"人的责任"变成了"框架的责任"。

本项目现在有 `pageProducts`、`getDetail`、`createProduct`、`updateProduct`、`deleteProduct` 五个方法要查商品表。手写条件的话，五个地方都得记着加，将来再来十个接口就得再记十次。**漏一个就是一个"已删除商品还能被看到"的 bug。**

> 这就是"约定优于配置"：**用一行注解换掉 N 处手工条件。**

### 4.2 ★ 实测过的默认值（别信教程，看字节码）

不同 MP 版本的行为有差异，Day 08 已经在"自带 JacksonTypeHandler"上栽过一次，所以这次直接反编译核实。

`@TableLogic` 注解本身的默认值（`javap -v`）：

```text
public abstract java.lang.String value();
    AnnotationDefault:
      default_value: s#10
        ""          ← 空串，意思是"没指定，用全局配置"
public abstract java.lang.String delval();
    AnnotationDefault:
      default_value: s#7   ""
```

全局配置的默认值（`javap -c` 看 `GlobalConfig$DbConfig` 构造器字节码）：

```text
22: ldc  #25   // String 1     →  logicDeleteValue    = "1"
28: ldc  #31   // String 0     →  logicNotDeleteValue = "0"
```

**结论：**

```text
① 注解上什么都不写（@TableLogic 光秃秃）→ 用全局默认值：正常=0，已删=1
② 我们的列是 SMALLINT DEFAULT 0，正好对上 → 零配置可用 ✅
③ 如果以后想把已删标成 -1 或者用 deleted_at，才需要写 @TableLogic(value=..., delval=...)
```

**顺手核实的两件事：**

| 检查 | 结果 |
|---|---|
| 项目里已有几处 `@TableLogic` / `deleted` 字段？ | **0 处**（全库搜过），今天是从零引它的第一处 |
| 项目里有手写 SQL 会绕过 `@TableLogic` 吗？ | 只有 `mall-admin/src/main/resources/mapper/AdminMapper.xml` 一个 XML，**不碰商品表** → 今天无影响 |

> 第二条很重要，见 §4.5 的第 1 条。

### 4.3 改两个实体

**`Product.java`** —— 加一个字段：

```java
    /** 软删除标记：0=正常 1=已删除。@TableLogic 会让 MP 自动过滤和改写删除语句 */
    @TableLogic
    private Integer isDeleted;
```

**`ProductSku.java`** —— 同样加一个：

```java
    @TableLogic
    private Integer isDeleted;
```

别忘了 `import com.baomidou.mybatisplus.annotation.TableLogic;`。

> **为什么 SKU 也要加？** 因为 `product_skus` **也被两张表指着**（`inventories` / `cart_items`），跟 `products` 是同一个处境。
> 而 `product_images` **没有任何表引用它**，所以**不加** —— 它可以放心地"全删再插"（§7）。
>
> **规则记牢：有没有人指着我，决定我能不能被物理删。** 这句话今天要反复用到。

### 4.4 ★ 怎么验证它真的生效（关键：开 SQL 日志）

改完实体、编译、重启 —— 但**光是"接口还正常返回"证明不了任何事**。要看见 MP 到底发了什么 SQL。

**临时**在 `application.yml` 里打开 SQL 日志：

```yaml
mybatis-plus:
  configuration:
    map-underscore-to-camel-case: true
    # ★ 临时打开：把 MP 生成的每条 SQL 打到控制台（验收完记得关掉）
    log-impl: org.apache.ibatis.logging.stdout.StdOutImpl
```

重启后请求 `GET /api/products/1`，日志里应该看到带 `AND is_deleted=0` 的 SQL：

```text
==>  Preparing: SELECT id,category_id,... FROM products WHERE id=? AND is_deleted=0
==> Parameters: 1(Long)
```

**三个探针，逐个看：**

```powershell
# 探针①：一般查询带条件了吗
curl.exe -s --noproxy "*" "http://localhost:8080/api/products" | Select-Object -First 1

# 探针②：removeById 变成了 UPDATE 吗（用新建的测试商品试，别动种子数据）
curl.exe -s --noproxy "*" -X DELETE "$B/api/products/<测试商品id>" -H "Authorization: Bearer $T"

# 探针③：手动把某行 is_deleted 改成 1，看接口是否立刻"看不见"它
```

探针③ 最直接：

```sql
UPDATE products SET is_deleted = 1 WHERE id = 5;
-- 然后 GET /api/products/5  → 应该 code=404
-- 再 GET /api/products      → 列表里没有 id=5
UPDATE products SET is_deleted = 0 WHERE id = 5;   -- 改回来
```

**如果这三步都对上了，`@TableLogic` 就真的在工作。** 然后**把 `log-impl` 那行删掉**（或注释），否则日志会很吵。

### 4.5 ⚠️ `@TableLogic` 的五个边界（都会咬人）

| # | 边界 | 说明 |
|---|---|---|
| 1 | **只作用于 MP 生成的 SQL** | 手写 XML / `@Select` 的 SQL **不会**自动加条件，要自己写 `AND is_deleted = 0`。本项目今天无此问题（唯一 XML 在 mall-admin，不碰商品） |
| 2 | **它不会级联处理子表** | 删主表时，子表一行不动 —— 这正是 §5.2 我们要的选择，但要**知道**这是框架限制，不是"它帮我们做对了" |
| 3 | **`updateById` 也会带上 `AND is_deleted=0`** | 对已删除行做 UPDATE 会"影响 0 行但接口返回成功"—— 跟 Day 07 那个"updateById 静默成功"是同一个坑。所以改之前要先 `getById` 判存在（现有代码已经这么做了 ✅）。**这条可以在 §4.4 的 SQL 日志里直接验证**：改一次商品，看 `UPDATE` 语句的 `WHERE` 里有没有 `is_deleted=0` |
| 4 | **唯一约束与软删除天然冲突** | 软删的行**仍占着唯一值**。`product_skus.sku_code` 是 UNIQUE → 删掉的 SKU 的编码不能复用。见 §5.3 |
| 5 | **它没有"查询已删除数据"的开关** | MP 不提供"这次查询我想看到已删除的"的标准 API。要做"回收站"功能，只能手写 SQL（手写就不走 `@TableLogic`，正好） |

---

## 5. 第 3 步：把 `deleteProduct` 改成软删除（20 分钟）

### 5.1 新代码：从三行 DELETE 变成一行 UPDATE

Day 08 修好的版本是这样的（**当时是对的**）：

```java
@Transactional(rollbackFor = Exception.class)
public void deleteProduct(Long id) {
    if (this.getById(id) == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
    }
    // ★ 顺序不能反：先子后主
    productSkuMapper.delete(new LambdaQueryWrapper<ProductSku>().eq(ProductSku::getProductId, id));
    productImageMapper.delete(new LambdaQueryWrapper<ProductImage>().eq(ProductImage::getProductId, id));
    this.removeById(id);
}
```

**今天要改成：**

```java
/**
 * 删除商品：软删除主表一行，子表一行不动。
 * <p>
 * 【为什么不再删子表】子表的唯一入口是 product_id，主表被 is_deleted=1 过滤掉之后
 * 整棵子树都不可达，不需要连锁标记。反过来做反而会制造"孤儿商品"：
 * 商品恢复了，被标记删的 SKU 和物理删掉的图集却回不来。
 * <p>
 * 【为什么外键不再是问题】@TableLogic 把 removeById 改写成了
 * UPDATE products SET is_deleted=1 WHERE id=? AND is_deleted=0 ——
 * 全程没有 DELETE 语句，fk_sku_product / fk_inventory_sku / fk_review_product
 * 这些 NO ACTION 外键根本不会被触发。
 * <p>
 * 【为什么保留 @Transactional】单条 UPDATE 自身是原子的，但 getById 判存在 +
 * removeById 是一对"检查—再操作"，且删商品在真实项目里总会陆续加上写日志、
 * 清缓存、发通知等语句。留着事务边界成本≈0，省得将来补。
 */
@Override
@Transactional(rollbackFor = Exception.class)
public void deleteProduct(Long id) {
    if (this.getById(id) == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
    }
    this.removeById(id);
}
```

**要删掉的就是那两行子表 DELETE。** 注意改完之后 **Javadoc 也必须整段重写** —— Day 08 那段注释讲的是"必须先清子表再删主表"，代码一改它就跟事实相反了，留着比没有更糟（下一个人会照着它去写代码）。

> 一天前刚加的东西，一天后又要删 —— 这**不是反复横跳**，而是**方案换了，结论就跟着换**：
> ```text
> 物理删主表 → 子表必须先删（否则撞外键）
> 软删主表   → 子表一行都不能删（否则孤儿商品）
> ```
> 两次都对，前提不同。**记住的是推理，不是结论。**

### 5.2 ★ 决策 B：为什么子表一行都不动

| 方案 | 做法 | 评价 |
|---|---|---|
| **主表软删 + 子表不动** | 只 UPDATE `products.is_deleted=1` | ✅ **推荐** |
| 主表软删 + 子表也软删 | 两张表都 UPDATE | 复杂，恢复时要记"哪些子表原本就删了" |
| 主表软删 + 子表物理删 | UPDATE 主表 + DELETE 子表 | ❌ 直接 500（撞 `fk_inventory_sku`） |

**推荐第一条，三个理由：**

```text
① 没必要：子表的唯一访问入口是 product_id。
   getDetail 先 getById(商品) —— 已被 @TableLogic 挡住 → 根本走不到查 SKU 那一步。
   pageProducts 只查主表。所以"主表挡住 = 全挡住"。

② 不能删：子表被 inventories / cart_items 指着，物理删必然 500。
   （注意：这里说的是删 product_skus。product_images 没人指着，删得掉，
     但删了它，将来"恢复商品"就变成一个有商品、没图的残缺品）

③ 恢复是无损的：因为子表一行没动，恢复 = UPDATE products SET is_deleted=0 WHERE id=?
   一条 SQL，商品连 SKU 带图完整复活。这是软删除最漂亮的地方。
```

**恢复验证（★ 今天必做）：**

```sql
-- 删掉商品 1 之后，把它"复活"
UPDATE products SET is_deleted = 0 WHERE id = 1;
```

然后 `GET /api/products/1` 应该又能拿到，`skus` 还是 3 个、`images` 还是 2 张。**一行 SQL 完成恢复 —— 这就是为什么软删除在生产环境几乎是标配。**

### 5.3 ⚠️ 副作用：`sku_code` 被永久占用（这是特性，不是 bug）

`product_skus.sku_code` 是 `VARCHAR(100) NOT NULL UNIQUE`。软删除**不删行**，所以：

```text
商品 1 有一个 SKU：sku_code = 'IP17-256-BLK'
软删商品 1 之后：
  · 那一行还在，is_deleted = 1
  · sku_code 仍被它占着
  · 新建一个同款商品、再用 'IP17-256-BLK' → 唯一约束冲突，插不进去
```

**第一反应是"这是个 bug"，其实不是 —— 想清楚业务：**

```text
删掉旧商品后又建一个同款，期望是什么？
  A. 恢复旧的（历史订单、评论、库存都还挂在它身上）  ← 这才是对的
  B. 真的建一个全新的（历史数据全断掉）
```

选 A，那 `sku_code` 被占用**正好帮你挡住了 B** —— 系统在说："这个编码是它，不是新的。"

**所以正确做法是"恢复"，不是"重建"。** 这不是限制，是保护。

> ★ **可选进阶（想动手再做，今天不强制）**：如果确实要支持"删掉后复用同一个 sku_code"，正解是把唯一约束改成**部分唯一索引**：
> ```sql
> ALTER TABLE product_skus DROP CONSTRAINT product_skus_sku_code_key;
> CREATE UNIQUE INDEX uk_sku_code_alive ON product_skus(sku_code) WHERE is_deleted = 0;
> ```
> 含义："**只对活着的行**要求 sku_code 唯一"。这招叫 partial index，PG 独有（MySQL 没有），真实项目里很常用。
> 若你做了这一步，记得把这条 SQL 也写进 `01-schema.sql` 的第十二节。

### 5.4 ★ 实测记录（2026-09-18 已跑）

**改完后的删除过程只剩两条 SQL** —— 这是本步唯一要盯的东西：

```sql
-- ① 判存在
SELECT id,category_id,brand_id,...,is_deleted FROM products WHERE id=? AND is_deleted=0
-- ② 软删主表
UPDATE products SET updated_at=?, is_deleted=1 WHERE id=? AND is_deleted=0
```

**断言：日志里不能再出现任何 `product_skus` / `product_images` 的写语句** ✅ 通过。

| # | 检查项 | 实测 |
|---|---|---|
| 1 | `POST /api/products`（1 SKU + 2 图）| `200`，id=18，落库 `1\|1\|2` ✅ |
| 2 | `DELETE /api/products/18` | `http=200 code=200`，SQL 只有上列 2 条 ✅ |
| 3 | 删后 DB | `p_del=1 \| sku_alive=1 \| sku_dead=0 \| img=2` ← **子表一行未动** ✅ |
| 4 | 删后 `GET /api/products/18` | `code=404 商品不存在` ✅ |
| 5 | ★ **恢复后** `GET /api/products/18` | `skus=1 images=2`，`attributes={color:银,storage:256G}` ✅ **无损还原** |
| 6 | 删种子商品 5（**有 inventories**）| `200` ✅ 外键不再阻挡 |
| 7 | 列表过滤 | `total=5 ids=[18,4,3,2,1]` ← 5 被过滤掉 ✅ |
| 8 | 不存在的 id | `code=404` ✅ |
| 9 | 重复删同一 id | 第 1 次 `200` → 第 2 次 `code=404` ✅（软删后 `getById` 返回 null） |
| 10 | `GET /api/products/1` 回归 | `200 skus=3` ✅ |
| 11 | 匿名 DELETE | `401` ✅ |
| 12 | 收尾 | 基线回 **`5\|7\|4\|7\|0\|0`**，残留 `0\|0\|0` ✅ |

#### ★ 第 5 项和第 2 步探针② 的对照（这一步的验收眼）

同一个场景，同样的"删了再恢复"，**改前改后是两个结果**：

| | 第 2 步（子表还带着 delete） | 第 3 步（已删掉） |
|---|---|---|
| 恢复后 `skus` | **0** ❌ | **1** ✅ |
| 恢复后 `images` | **0** ❌（图集被**物理删**，不可逆） | **2** ✅ |
| 结论 | 孤儿商品：活的空壳 | 完整复活 |

**同一操作、两个结果 —— 这才叫证明了改动有效。** 只看"接口返回 200"永远分不出差别（改前改后都是 200）。

---

## 6. 第 4 步：PUT 支持改 SKU —— 差分更新（40 分钟，今天的主课）

### 6.1 问题本质：三个集合，三种动作

```text
集合① 库里现有的 SKU（查出来）    = { A, B, C, D, E }
集合② 本次提交的 SKU（请求体）     = { B', C', F }        （带 id 的是改，没 id 的是新增）

按 id 对齐后：
  · 在①也在② 且 id 相同  → UPDATE   （B、C：改价格/库存/属性）
  · 在②但 id 是 null     → INSERT   （F：新加的规格）
  · 在①但不在②          → ?        （A、D、E：库里消失了）
```

最后那一行就是今天最需要想清楚的地方。

### 6.2 ★ 决策 C：靠什么"认出这一个是那一个"

| 认人方式 | 怎么判断 | 问题 |
|---|---|---|
| **`sku.id`（推荐）** | id 为 null → 新增；有 id → 改 | 客户端能伪造 id（但可以校验，见下） |
| `sku.sku_code` | 库里没这个 code → 新增 | ❌ **改 code 做不到**：改了 code 就被当成"新的"，而旧行还在、唯一约束冲突 |

用 `sku_code` 认人的死结：

```text
库里：sku_code = 'OLD-001'
客户端想改成：'NEW-001'

用 code 比对 → 认不出是同一行 → 当成"新增 NEW-001" + "旧的不见了要删"
  · INSERT 'NEW-001'  → 此时事务里 'OLD-001' 还没被删 → 唯一约束允许（不同值），OK
  · 但"旧的不见了要删"这一步，会去删掉仍然有库存的 SKU → 500
  · 就算删成功，这个 SKU 的 id 也变了 → inventories 里那行会指向一个不存在的 sku
```

> **一句话原则：主键（id）是"行的身份"，业务字段（sku_code）是"人的约定"。**
> **不要拿业务字段当身份用** —— 因为业务字段是**会被修改的**，而身份不能改。

**用 id 认人的代价：必须校验归属。** 这是今天最重要的安全点：

```text
客户端传：PUT /api/products/2     body: {"skus":[{"id": <商品1的SKU id>, "price": 0.01}]}

如果不校验：
  你只是想改商品 2，却把商品 1 的 SKU 价格改成了 0.01
  → 商品 1 在 C 端显示 1 分钱，可以被瞬间拍下  ← 真实世界里非常常见的经济损失漏洞
```

这类漏洞有个专有名字，叫 **IDOR（Insecure Direct Object Reference，越权访问）**：**你传什么 id 我就改什么，我只检查"你有没有权限"，不检查"这个 id 是不是你的"。**

**解法：改之前必须确认 `sku.productId == 路径里的 id`。**

### 6.3 ★ 决策：`null` / `[]` / 非空 —— 三种语义

这是 §1.4 里那个"库里 5 个、本次只传 3 个"的问题，必须给一个**明确、可预期**的答案：

| `skus` 的值 | 含义 | 为什么 |
|---|---|---|
| `null`（JSON 里根本不写这个 key） | **不动** SKU | "这次只想改标题"是最常见的请求 |
| `[]`（空数组） | **清空**该商品全部 SKU | 显式写了空数组 = 显式表达"一个都不要" |
| 非空数组 | **以本次为准做对齐**（新增/修改/软删） | 表意明确：我提交的就是完整列表 |

**为什么不用"永远全量覆盖"（严格 PUT 语义）？**

因为那是**灾难性**的：客户端只想把商品下架，发 `{"status": 0}`，如果按"全量覆盖"理解 → `skus` 没传 = 删光所有 SKU。**一次下架操作清空了商品的全部规格。**

> 这里必须指出一个**已存在的设计矛盾**：
>
> ```text
> 现在 updateProduct 的 name 是"局部更新"语义（不传就不改）—— 靠 MP 的 NOT_NULL 更新策略。
> 而 name 上却挂着 @NotBlank —— 那"只改 status 不传 name"就会 400。
> ```
>
> 也就是说：**当前这个接口一边说"局部更新"，一边强制你必须传 name。** 这就是 Day 07 留下的思考题 #1。
>
> **今天拍板：这个 PUT 是"局部更新"语义（类 PATCH）。** 因此 `name` 上的 `@NotBlank` 必须摘掉（§6.5）。

### 6.4 新增 `SkuUpdateDTO`

它和 `SkuCreateDTO` 的唯一区别就是**多一个 `id`**。

> 为什么不直接复用 `SkuCreateDTO`？
> 新增时 id 必须为 null（服务端会填），修改时 id 必须有值 —— **两者对 id 的要求正好相反**。
> 一个类没法同时表达这两种要求，硬用会让人以为"新增也能传 id"。

```java
package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

import java.math.BigDecimal;
import java.util.Map;

/**
 * 修改商品时随商品一起提交的一个 SKU。
 * <p>
 * 与 {@link SkuCreateDTO} 的唯一区别：多一个 {@code id}。
 * <ul>
 *   <li>{@code id == null} → 这是个新 SKU，执行 INSERT</li>
 *   <li>{@code id != null} → 改库里已有的那一行，执行 UPDATE（★ 必须先校验它属于本商品）</li>
 * </ul>
 */
@Data
public class SkuUpdateDTO {

    /** null = 新增 */
    private Long id;

    @NotBlank(message = "SKU 编码不能为空")
    private String skuCode;

    private String name;

    @NotNull(message = "SKU 价格不能为空")
    @Positive(message = "SKU 价格必须大于 0")
    private BigDecimal price;

    private BigDecimal originalPrice;

    private Map<String, Object> attributes;

    private String image;

    private Integer status;
}
```

### 6.5 改 `ProductUpdateDTO`

```java
package com.mallx.product.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

/**
 * 修改商品 —— 局部更新语义：没传的字段 = 不动。
 * <p>
 * 三个集合类字段的语义统一为：
 * <ul>
 *   <li>{@code null} → 不动</li>
 *   <li>空数组 {@code []} → 清空</li>
 *   <li>非空数组 → 以本次为准做对齐</li>
 * </ul>
 */
@Data
public class ProductUpdateDTO {

    // ★ 摘掉了 @NotBlank：局部更新时"没传 name"是合法的，
    //   而 @NotBlank 对 null 和空串都报错，分不清这两种情况。
    //   空串的拦截挪到 Service 里显式做（见 updateProduct）。
    @Size(max = 100, message = "商品名称不能超过 100 字")
    private String name;

    private String subtitle;

    private String description;

    private String mainImage;

    /** 1=上架 0=下架 */
    private Integer status;

    /** 图集：null=不动，[]=清空，非空=按数组顺序重建 */
    private List<String> images;

    /** SKU 列表：null=不动，[]=清空，非空=对齐。@Valid 必须写在字段上才级联 */
    @Valid
    private List<SkuUpdateDTO> skus;
}
```

### 6.6 重写 `updateProduct`

**结构先看清楚（三段式）：**

```text
① 主表：照旧（BeanUtils + updateById），外加 name 空串的显式拦截
② SKU：分三段 —— 查出现有 → 遍历提交的（判 insert / update）→ 剩下的就是要删的
③ 图集：全删再插（下一节讲）
```

**★ 第 ② 段的骨架，几个关键处留给你填：**

```java
@Override
@Transactional(rollbackFor = Exception.class)
public void updateProduct(Long id, ProductUpdateDTO productUpdateDTO) {
    // ---------- ① 主表 ----------
    if (this.getById(id) == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
    }
    // 局部更新下，"没传 name"合法，但"传了空串"不合法 —— 这一层 @NotBlank 表达不了
    if (productUpdateDTO.getName() != null && productUpdateDTO.getName().isBlank()) {
        throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "商品名称不能为空");
    }
    Product update = new Product();
    BeanUtils.copyProperties(productUpdateDTO, update);
    update.setId(id);
    this.updateById(update);          // MP 的 NOT_NULL 策略：null 字段不拼进 SET

    // ---------- ② SKU 差分 ----------
    List<SkuUpdateDTO> skuDtos = productUpdateDTO.getSkus();
    if (skuDtos != null) {            // null = 不动，直接跳过
        // 2.1 先查库里现有的，装进一个以 id 为键的 Map
        List<ProductSku> existing = productSkuMapper.selectList(
                new LambdaQueryWrapper<ProductSku>().eq(ProductSku::getProductId, id));
        Map<Long, ProductSku> untouched = new HashMap<>();
        for (ProductSku s : existing) {
            untouched.put(s.getId(), s);
        }

        // 2.2 遍历本次提交的：有 id → 改；没 id → 增
        for (SkuUpdateDTO dto : skuDtos) {
            if (dto.getId() == null) {
                // ---- 新增 ----
                ProductSku sku = new ProductSku();
                BeanUtils.copyProperties(dto, sku);       // 注意：dto 的 id 是 null，正好
                sku.setProductId(________);               // ★ 服务端填，绝不用客户端的
                if (sku.getStatus() == null) {
                    sku.setStatus(1);
                }
                productSkuMapper.insert(sku);
            } else {
                // ---- 修改 ----
                ProductSku old = untouched.________(dto.getId());     // ★ 取出并「顺手标记为已处理」
                if (old == null) {
                    // 要么这个 id 不存在，要么它属于别的商品 —— 都当越权处理，一律拒绝
                    throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "SKU 不属于该商品");
                }
                ProductSku sku = new ProductSku();
                BeanUtils.copyProperties(dto, sku);
                sku.setId(________);                      // ★ 改谁
                sku.setProductId(________);               // ★ 不能改归属，钉死
                productSkuMapper.updateById(sku);
            }
        }

        // 2.3 Map 里剩下的 = 库里存在但本次没提交的 → 软删
        for (ProductSku orphan : untouched.________()) {          // ★ 拿到全部剩余
            productSkuMapper.deleteById(orphan.getId());          // 被 @TableLogic 改成 UPDATE
        }
    }

    // ---------- ③ 图集 ---------- （见 §7）
}
```

**★ 这里有个很值得学的技巧（2.3 那段）：**

> `untouched` 这个 Map 一开始装的是"库里全部现有 SKU"。
> 每处理一个提交项，就用 `remove(id)` 把对应条目**摘掉**，表示"这个已经处理过了"。
> 等遍历结束，**Map 里剩下的自然就是"从未被提到过的"** —— 也就是要删的。
>
> 好处：**不需要写两层嵌套循环去挨个比对**，一次遍历搞定。这叫"标记 + 收集残余"。
>
> 而且 `remove()` 的返回值正好就是"取出的那个对象"，所以**取值和打标记是同一步操作**，不会漏。

**⚠️ 2.3 里 `deleteById` 走的是软删除（`UPDATE SET is_deleted=1`），不是真删。** 因为 `product_skus` 被 `inventories` 指着 —— 又是 §4.3 那条规则。

### 6.7 第 4 步实测记录（本节全部为真机跑出来的结果）

测试数据：`id1=19 差分验证机`（SKU `D09U-A`=22 / `D09U-B`=23）+ `id2=20 IDOR受害商品`（SKU `D09V-V`=24）。

| # | 场景 | 请求 | 库内实测 | 判定 |
|---|---|---|---|---|
| 1 | 建验证机 | `POST` | `1 \| 2 \| 2`（主表/ SKU / 图） | ✅ |
| 2 | 改已有 SKU：A 价 100→88.88 + 改 subtitle | `PUT` 带 `A.id`、`B.id` | `subtitle=改价+改副标题`、`A.price=88.88`、`alive=2 dead=0` | ✅ |
| 3 | 新增 SKU：多传一个无 id 的 C | `PUT` | `alive=3`，`C.id=25` | ✅ |
| 4 | 局部更新：只传 `{"status":0}` | `PUT` | `status=0`，`name`/`subtitle` 原样、`alive_sku=3`、`img=2` | ✅ 不传就不动 |
| 5 | 软删 SKU：提交里去掉 B | `PUT` | `alive=2 dead=1 行数仍=3`，`B.is_deleted=1` | ✅ 是软删不是物理删 |
| 6 | ★ IDOR：用商品 19 的路径改商品 20 的 SKU | `PUT /19` + `V.id` | `code=400 SKU 不属于该商品`；**受害方 `9999.00 / D09V-V / 活跃SKU=1` 一行没动** | ✅ |
| 7 | ★ 事务回滚：上面那个请求带 `name` 改写 | 同上 | 攻击方主表 `name` **仍是 Day09-差分验证机**、`alive_sku=2` | ✅ 主表那句 UPDATE 被回滚 |
| 8 | 已软删的 SKU 传回来 | `PUT` 带 `B.id` | `code=400`；`alive=2 dead=1` 未被破坏 | ✅ 软删行不在池子里 |
| 9 | 清空语义 `{"skus":[]}` | `PUT` | `alive=0 dead=3` | ✅ 零额外代码 |
| 10 | 回归 | 匿名 / demo / GET 列表 / 不存在的 id / name 空串 | `401` / `403` / `200 total=6` / `code=404` / `code=400 商品名称不能为空` | ✅ |
| 11 | `@Valid` 级联 | SKU `price:-1` / `skuCode:""` | `code=400 SKU 价格必须大于 0` / `SKU 编码不能为空` | ✅ 证明 `@Valid` 在**字段**上真级联 |
| 12 | 收尾 | 清理 | 基线回 `5 \| 7 \| 4 \| 7 \| 0 \| 0`，残留 `0\|0\|0\|0` | ✅ |

**★ 抓到的真实 SQL（这三条就是差分更新的全部动作）：**

```sql
-- 改 A 的价（① 主表 + ② 修改分支）
UPDATE products     SET subtitle=?, updated_at=? WHERE id=? AND is_deleted=0
UPDATE product_skus SET product_id=?, sku_code=?, name=?, price=?, updated_at=? WHERE id=? AND is_deleted=0

-- 软删 B（② 的 2.3 段）
UPDATE product_skus SET updated_at=?, is_deleted=1 WHERE id=? AND is_deleted=0
```

**三个"不报错但要知道"的现象（都实测到了）：**

| # | 现象 | 说明 |
|---|---|---|
| 1 | **每次 PUT 都会有一条 `UPDATE products`**，哪怕 body 里什么都没改 | 因为 `MyMetaObjectHandler` 在 update 时自动填 `updated_at` —— NOT_NULL 策略挡不住"被自动填充的字段"。所以"不传 = 不动"只对**业务字段**成立，`updated_at` 永远会动 |
| 2 | **图集这次没被处理** | `PUT {"images":[...]}` → `code=200` 但 `product_images` 仍 2 行。这是第 5 步（§7）要补的缺口，**不是缺陷** —— 也再次印证 `copyProperties` 对"实体没有的字段"是静默跳过的 |
| 3 | **业务码 400 的响应，HTTP 状态仍是 200** | `BusinessException` 由 `@ExceptionHandler` 直接返回 `Result`，没加 `@ResponseStatus`。**判断成功与否必须看 body 的 `code`，不能看 HTTP 状态码** —— 只看 HTTP 会把"越权被拒"当成"改成功了" |

---

## 7. 第 5 步：PUT 支持改图集（15 分钟）

### 7.1 图集为什么可以"全删再插"

`product_images` 的行长这样，**没有任何业务语义**：

```text
id | product_id | image_url        | sort_order
 7 |          1 | https://...a.jpg |          0
 8 |          1 | https://...b.jpg |          1
```

它只是"一个商品有哪几张图，按什么顺序"。没有价格、没有库存、不会被别的表引用。

所以最省事、也最不容易出错的写法是：

```text
DELETE FROM product_images WHERE product_id = 1   → 全部删掉
再按新数组的下标插一遍                          → sort_order = i
```

**这里可以放心物理删，因为她前面那条规则说得清清楚楚：没有任何表引用 `product_images`。**

> 对比一下就更清楚了：
> ```text
> product_images → 无人引用   → 物理删，全删再插，最简单
> product_skus   → 2 张表引用 → 只能软删，得一个个算差分
> products       → 3 张表引用 → 只能软删
> ```
> **复杂度不是凭空来的，是被"谁引用它"决定的。**

### 7.2 代码

接在 §6.6 的 `updateProduct` 末尾：

```java
    // ---------- ③ 图集：全删再插 ----------
    List<String> images = productUpdateDTO.getImages();
    if (images != null) {                      // null = 不动
        // 3.1 先清空（product_images 无人引用，物理删安全）
        productImageMapper.delete(new LambdaQueryWrapper<ProductImage>()
                .eq(ProductImage::getProductId, id));

        // 3.2 按数组下标重建，下标就是 sort_order
        for (int i = 0; i < images.size(); i++) {
            String url = images.get(i);
            if (url == null || url.isBlank()) {
                continue;                      // 短路求值，顺带防 NPE
            }
            ProductImage img = new ProductImage();
            img.setProductId(id);
            img.setImageUrl(url);
            img.setSortOrder(i);
            productImageMapper.insert(img);
        }
    }
```

> 注意 3.1 和 3.2 必须在**同一个事务**里 —— 中间断了就会出现"图全没了，新图没插上"。
> `updateProduct` 上有 `@Transactional(rollbackFor = Exception.class)` ✅

**一个可以课后想的问题：** "全删再插"的代价是 `product_images.id` 会一直涨（删 4 张插 4 张 → id 从 7-10 变成 11-14）。因为没人引用它，所以无害。
但如果哪天有个"商品图片审核记录表"引用了 `image_id`，这个写法就立刻不能用了 —— **那时候就得给它也加 `is_deleted`，老老实实算差分。** 方案的复杂度永远跟着引用关系走。

### 7.3 实测结果　✅ 2026-09-18 已跑完

改完代码 → `mvn -o install -DskipTests`（25 个源文件重编译）→ 重启应用（`learning/day09/start-app.bat`）。
跑之前基准：`product_images` 全表 5 行（商品 1 = id 16/17/18，url 为 u1/u2/u3；商品 2 = id 1；商品 3 = id 4）。

| # | 请求 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `PUT /api/products/1` + `"images":["u1","u2","u3"]` | `code=200`；商品 1 变 **id 16/17/18，sort 0/1/2**；旧 id 2、3 消失；全表 4→**5 行** | ✅ |
| 2 | 同请求但**不带 `images` 键** | `code=200`；全表仍 **5 行**、商品 1 仍 3 张 → **图集一条 SQL 都没发**，`null` = 不动 | ✅ |
| 3 | `PUT` + `"images":[]` | `code=200`；商品 1 的图**全部消失**，全表 **5→2 行** → `[]` = 清空 | ✅ |
| 4 | 把原来 3 个 url PUT 回去 | `code=200`；商品 1 变为 **id 49/50/51，sort 0/1/2**，全表回 **5 行** | ✅ |
| 5 | `GET /api/products/1` | `images:["u1","u2","u3"]` 顺序正确（`sort_order` 升序读出来的就是提交顺序） | ✅ |
| 6 | 回归：无 token PUT | `HTTP=401` `"未登录或登录已过期"` | ✅ |
| 7 | 回归：`PUT /api/products/999` | `code=404` `"商品不存在"`（HTTP 200 —— 业务码约定） | ✅ |
| 8 | 回归：`/api/hello`、`GET /api/products/1` | 均 `code=200`，SKU 三个规格原样返回 | ✅ |

**最终基线**：`5\|7\|5\|7\|0\|0`，软删行 `p_deleted=0 / s_deleted=0`。
（`product_images` 是 **5** 不是 4：第 1 项把商品 1 的**两张**种子图换成了三张 u1/u2/u3，验证时按"恢复成提交的那 3 个 url"收尾。
要回到严格的 4 行，把商品 1 的图 PUT 回 `iphone17pro-1/2.jpg` 两个 url 即可。）

> **`id` 涨得比预想快**：种子最大 id=4，跑完已经到 **51**（因为复原动作重复了多轮，每轮删 3 插 3）。
> 这正好印证上面的课后问题 —— 自增序列不回收，只要没人引用就无害。

### 7.4 观测到的 SQL（`log-impl` 开着时最有价值的一眼）

| 段 | 生成的 SQL |
|---|---|
| ② SKU 段 | 清一色 `UPDATE product_skus SET ... is_deleted=1 ...` 或普通 `UPDATE ... SET price=?` |
| **③ 图集段** | **`DELETE FROM product_images WHERE (product_id = ?)`** + N 条 `INSERT INTO product_images ...` |

**这是 Day 09 全程唯一一条真正的 `DELETE` 语句。** 同一个方法里两种删除并存不是 bug：
`ProductImage` 没挂 `@TableLogic`（所以是真删），`ProductSku` 挂了（所以被改写成 UPDATE）。
一旦给 `ProductImage` 也加上 `@TableLogic`，第 1 项那条 DELETE 就会退化成 UPDATE，本节写法随即失效 —— 所以**别顺手加**。

---

## 8. 第 6 步：构建、启动与验收（40 分钟）

### 8.1 构建

```powershell
$env:MAVEN_OPTS="-Xmx1024m"
Set-Location D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o install -DskipTests
```

必须 `install` 而不是 `compile` —— 否则 `spring-boot:run` 会报兄弟模块 missing（jar 没装进本地仓库）。

**改动前先杀旧进程**（Maven 父进程 + fork 的 java 子进程都要杀），否则 jar 被覆盖后行为会错乱。

### 8.2 启动

```powershell
Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
    Where-Object { $_.CommandLine -match 'mall|spring-boot' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
Set-Location D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o spring-boot:run -pl mall-server `
    "-Dspring-boot.run.arguments=--server.port=8080" 2>&1 |
    Out-File D:\MallX\learning\day09\app.log -Encoding utf8
```

启动日志必查两行：

```text
INFO  Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl
      ↑ 必须有（漏洞 A 的验收点）
WARN  Found 2 UserDetailsService beans ...      ← 出现这行就是踩坑了
```

### 8.3 十四项验收

**写脚本跑，别手敲**（`curl.exe` 必须加 `--noproxy "*"`，POST JSON 一律 `-o` 落盘再 `Get-Content -Raw -Encoding utf8` 读）。

#### A 组：软删除（7 项）　✅ 2026-09-18 已跑完，实测结果见 **§5.4**

| # | 项 | 操作 | 期望 |
|---|---|---|---|
| 1 | 复现旧问题 | 改之前 `DELETE /api/products/1` | body `code=500`，日志 `fk_inventory_sku` |
| 2 | ★ 修复生效 | 改之后 `DELETE /api/products/1` | HTTP 200 + body `code=200` |
| 3 | ★ 是"逻辑删"不是"物理删" | `SELECT id,name,is_deleted FROM products WHERE id=1` | **行还在**，`is_deleted=1` |
| 4 | 子表一行没少 | 查三张表 | `product_skus` 仍 3 行、`product_images` 仍 2 行、`inventories` 仍 3 行 |
| 5 | 详情自动 404 | `GET /api/products/1` | body `code=404` |
| 6 | 列表自动过滤 | `GET /api/products` | 列表不含 id=1，`total` 从 5 变 4 |
| 7 | ★ 恢复无损 | `UPDATE products SET is_deleted=0 WHERE id=1` 后再查详情 | 又能拿到，`skus` 仍 3 个、`images` 仍 2 张 |

#### B 组：差分更新（6 项）

先建一个测试商品（2 个 SKU + 2 张图），记下两个 SKU 的 id。

| # | 项 | 操作 | 期望 |
|---|---|---|---|
| 8 | 改已有 SKU | PUT，skus 里带其中一个 sku 的 `id`，价格改成新值 | DB 里那个 SKU 价格真的变了（**必须查库**，不能只看返回 200） |
| 9 | 新增 SKU | PUT，skus 里加一个**不带 id** 的 | `product_skus` +1，`product_id` 正确，`is_deleted=0` |
| 10 | 去掉 SKU | PUT，skus 里**不出现**某个已有 id | 那个 SKU 的 `is_deleted=1`（★ 不是被物理删），详情里少一个 |
| 11 | ★★ 越权 | PUT `/{商品A}`，skus 里带**商品B 的** sku id | body `code=400` 拒绝，且**商品B 的 SKU 未被改动**（查库确认） |
| 12 | 改图集 | PUT，images 传 3 个新 url | `product_images` 该商品的图按新下标重建，`sort_order` = 0/1/2 |
| 13 | 局部更新 | PUT，body 只有 `{"status":0}` | HTTP 200 + `code=200`，且 **name / skus / images 都没被动**（★ `@NotBlank` 已摘，这条以前会 400） |

#### C 组：回归（1 项）

| # | 项 | 操作 | 期望 |
|---|---|---|---|
| 14 | 鉴权没被破坏 | 匿名 / demo token 打 PUT | **401 / 403**；`GET /api/products` 匿名仍 200（白名单未破） |

#### 收尾：验证完必须做的事

```text
① 删掉 application.yml 里的 log-impl（SQL 日志太吵）
② 把测试商品删掉（软删，然后 SQL 物理清掉它和它的子表）—— 恢复基线 5|7|4|7
③ 商品 1 的 is_deleted 必须是 0（验收 [7] 已经改回来了，再确认一次）
```

> ⚠️ 清测试数据时注意：测试商品的 SKU 被软删后**行还在**，`inventories` 里可能也留了行。
> 想彻底清干净，顺序是：`inventories` → `cart_items` → `product_skus` → `product_images` → `products`。

---

## 9. 常见卡点速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 删商品还是 500，日志 `fk_inventory_sku` | `deleteProduct` 里那两行子表 DELETE 没删掉 | 见 §5.1，子表一行都不能删 |
| 实体加了 `@TableLogic` 但已删商品还能查到 | 忘了重启应用（jar 没更新）；或那条查询走的是手写 SQL | 杀进程 → 重新 `install` → 重启；检查有没有 XML/`@Select` |
| SQL 日志里看不到 `AND is_deleted=0` | `log-impl` 没配或位置写错 | 放在 `mybatis-plus.configuration` 下（见 §4.4） |
| 删商品时 SQL 变成 `UPDATE ... SET is_deleted=?` 但报列不存在 | 数据库 ALTER 没执行 / 列名拼错 | 见 §3.3，先 `\d products` 确认列在 |
| `updateById` 返回成功但数据没变 | 目标行 `is_deleted=1`，MP 自动加了 `AND is_deleted=0` | 边界 3（§4.5），先判存在再改 |
| PUT 改 SKU 报唯一约束冲突 | 尝试复用了一个已软删 SKU 的 `sku_code` | 见 §5.3，这是设计使然；要复用就上 partial index |
| 客户端传了别的商品的 sku id 且真的改成功了 | ❌ 缺归属校验 → IDOR 漏洞 | 见 §6.2，必须校验 `productId` 相等 |
| 只传 `{"status":0}` 却 400 | `name` 上的 `@NotBlank` 还在 | 见 §6.5，摘掉它 |
| PUT 里 skus 传了空数组，SKU 全没了 | 这是**预期行为**（§6.3 表） | 想"不动"就别传这个 key |
| PS 里 `$pid` 循环不执行 | `$PID` 是 PowerShell 只读自动变量 | 换名，如 `$gid` |
| PS 里 localhost 请求报 502 | 没加 `--noproxy "*"`，走了系统代理 | 所有 `curl.exe` 都加 |

---

## 10. 本日成果自检清单

**数据库**　（第 1 步 ✅ 已完成）

- [x] `01-schema.sql`：`products` / `product_skus` 的 `CREATE TABLE` 里都有 `is_deleted`
- [x] `01-schema.sql`：末尾有"十二、软删除列"幂等 ALTER 段
- [x] 线上库两列都已存在，老数据 `is_deleted` 全为 0（幂等已验证：连跑两遍零报错）

**实体 / DTO**　（第 2 步 ✅ 已完成）

- [x] `Product` 加了 `@TableLogic private Integer isDeleted;`
- [x] `ProductSku` 同上（★ 别忘了它，被 2 张表指着）
- [x] `ProductImage` **没加**（无人引用，可以物理删）
- [x] `SkuUpdateDTO` 新建，比 `SkuCreateDTO` 多一个 `id`
- [x] `ProductUpdateDTO` 加了 `images` + `skus`（`@Valid` 在**字段**上 —— 实测级联生效）
- [x] `ProductUpdateDTO.name` 的 `@NotBlank` 已摘，改成 Service 里判空串

**Service**　（第 3 步 ✅ 已完成）

- [x] `deleteProduct` 只剩 `getById` 判存在 + `removeById`，**两行子表 DELETE 已删**（Javadoc 已同步重写）
- [x] `updateProduct` 加了 `@Transactional(rollbackFor = Exception.class)`
- [x] SKU 差分：null 不动 / [] 清空 / 非空对齐（§6.7 第 1–5、8、9 项）
- [x] ★ 改 SKU 前校验 `productId` 归属（IDOR 防线，§6.7 第 6 项）
- [x] 新增 SKU 时 `productId` 由**服务端**填
- [x] **图集：null 不动 / 非空全删再插，`sort_order` = 下标**　← 第 5 步（§7）✅ 2026-09-18 实测全绿，见 §7.3

**验收**　（第 4 步 ✅ 12 项 + 4 项补测全绿，详见 §6.7）

- [x] [1]–[9] 接口与库内状态全部吻合
- [x] ★ IDOR：伪造别人的 sku id 被拒绝（`code=400`），且**受害商品一行没动**
- [x] ★ 事务回滚：IDOR 请求里连主表那句 UPDATE 也一起回滚了
- [x] ★ `[]` 清空语义零额外代码生效（`alive=0 dead=3`）
- [x] 回归：匿名 `401` / demo `403` / 列表 `200` / 不存在 `404` / name 空串 `400` / `@Valid` 级联 `400`
- [x] 收尾：`log-impl` 已关（第 6 步 ✅ 2026-09-18）、测试数据已清（基线 `5|7|5|7|0|0`）

**可选进阶（不强制）**

- [ ] 再加一列 `deleted_at`，删除时记下时间
- [ ] 把 `UNIQUE(sku_code)` 改成 partial index（`WHERE is_deleted = 0`）
- [ ] 做一个"回收站"接口：手写 SQL 查 `is_deleted = 1` 的商品（手写 SQL 不走 `@TableLogic`）

---

## 11. 做完之后

今天之后，你手上多了三样**通用**能力：

```text
① 软删除          → 任何"被别的表引用过"的数据都只能用这一招
                   用户、订单、优惠券、收货地址…… 全都要
② 差分更新        → 任何"一对多"的编辑场景
                   订单明细、购物车、权限分配、文章配图
③ IDOR 防范意识   → 任何"客户端传 id，服务端按 id 改"的接口
                   这是真实世界里最高频的漏洞类型之一
```

**一个判断"该不该软删"的口诀：**

```text
问：这张表被别的表用外键指着吗？
  指着 → 软删（+ @TableLogic）
  没指着 → 物理删也行，但先想清楚"删了会不会后悔"

问：这张表会被别的表引用吗？（将来会不会）
  会 → 现在就加 is_deleted，别等到撞了再加
```

**Day 10 的几个方向：**

```text
· 库存模块（mall-inventory）  → inventories 已有 7 行，但没有一个接口。
                              今天已经摸到边了：SKU 被库存引用 → 库存该谁建？建商品时同步建？
                              正好练"跨模块调用与事务边界"
· 购物车（mall-cart）         → cart_items 0 行，第一次让数据挂到 user_id 上
                              （@AuthenticationPrincipal 终于要派上用场）
· 商品的查询增强              → 现在列表只按分类/关键词过滤；再加排序、价格区间、品牌筛选
                              顺便引入 Redis 缓存商品详情
· 回收站 / 恢复接口           → 今天验证了 SQL 恢复可行，把它做成接口
```

> **今天最该带走的一句话**：
> **删除不是"把数据抹掉"，而是"让数据从业务视野里消失"。**
> 唯一能真正抹掉数据的时机，是这张表**还没被任何人引用过**的时候。

---

## 附：今日术语表

| 术语 | 一句话解释 |
|---|---|
| 软删除 / 逻辑删除 | 不 DELETE，改成一个标记位；数据还在，但对业务不可见 |
| 物理删除 | 真的 `DELETE FROM`，行从磁盘上消失 |
| 逻辑删除字段 | 承载"是否已删"的那一列，如 `is_deleted` |
| `@TableLogic` | MyBatis-Plus 注解：自动给查询加条件、把删除改写成 UPDATE |
| `logicDeleteValue` | 全局配置，"已删"用什么值表示（MP 默认 `1`） |
| `logicNotDeleteValue` | 全局配置，"未删"用什么值表示（MP 默认 `0`） |
| 差分更新（diff update） | 把"库里的状态"和"客户端想要的状态"对齐：该插的插、该改的改、该删的删 |
| 全量覆盖 vs 局部更新 | 前者"没传的就算删掉"，后者"没传的就是不动"。本项目的 PUT 是局部更新（类 PATCH） |
| 归属校验 | 改一行数据前，先确认这行确实属于路径里的那个父对象 |
| IDOR（越权访问） | 客户端传什么 id 就改什么 id，只查权限不查归属 —— 高频安全漏洞 |
| 部分唯一索引（partial index） | 只对满足条件的行要求唯一，如 `WHERE is_deleted = 0`；PG 独有 |
| 迁移脚本（migration） | 可重复执行的、有序的表结构变更脚本（Flyway / Liquibase 专管这个） |
| 幂等（idempotent） | 同一段 SQL 跑一次和跑十次，结果一样（`IF NOT EXISTS` 就是在做这件事） |
