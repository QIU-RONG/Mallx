# Day 18 — 管理端商品与分类管理

> ★ **里程碑意义：数据权限反转第二批。** Day 17 反转的是「订单 + 库存」，本日反转「商品 + 分类」。
> 反转口径：C 端靠 `WHERE user_id = ?` 在 SQL 里过滤；管理端**不过滤**，防线前移到权限码（`/api/admin/**` + `@PreAuthorize`）。

## 一、本日范围（已拍板）

| 决策 | 结论 |
|---|---|
| 范围 | **商品 CRUD + 分类 CRUD**（不含 SKU/图集的独立管理端点，它们随商品一起走） |
| C 端写接口 | **迁移**：删掉 `POST/PUT/DELETE /api/products`，写能力收归 `/api/admin/products/**` |
| 上下架 | **不新增端点** —— `ProductUpdateDTO` 已含 `status`（`{"status":0}` 即下架），走 `PUT` |
| 前端 | 无，界面仍为 Swagger UI |

## 二、现状盘点（已探明，勿重查）

| 现状 | 位置 | 对本日的影响 |
|---|---|---|
| C 端 `/api/products` 已挂 3 个写接口（`POST` / `PUT {id}` / `DELETE {id}`），各带 `product:create/update/delete` | `ProductController.java:59-80` | **要迁走**：这三个方法整体移到 `AdminProductController`，`ProductService` 一行不用改 |
| `ProductService` 已实现 `pageProducts / getDetail / createProduct / updateProduct / deleteProduct` | `ProductServiceImpl.java` | 管理端**直接复用**，只新增一个「管理端分页」 |
| `pageProducts` 写死 `.eq(Product::getStatus, 1)`（C 端只看上架） | `ProductServiceImpl.java:57` | 管理端要看**全部**，status 变成「可选过滤条件」 |
| `CategoryController` 只有 `GET /tree`，**零写接口** | `CategoryController.java` | 分类写能力从零开始（Service 要新增 3 个方法） |
| `categories` 表：**无 `is_deleted`**，`parent_id` 可空，`status NOT NULL DEFAULT 1` | `01-schema.sql:57-65` | 分类**物理删**；删前必须查引用 |
| `products.category_id NOT NULL` + `fk_product_category`（NO ACTION） | `01-schema.sql:79-94` | **有商品的分类物理删不掉**（DB 会拒绝）→ 必须提前给出友好 400 |
| 权限种子：`product:*` 5 条（id 1–5，path 指向 **C 端**）+ `order:*` 2 条 + `user:list`；**无 `category:*`** | `03-data.sql:131-143` | 要订正 5 条 path、新增 4 条 `category:*`（id **14–17**，9–13 已被 Day 17 占用） |
| `product:*` 已授权给 role 2（PRODUCT_ADMIN）、超管天然全量 | `03-data.sql:159-166` | `category:*` 属**新增权限** → **必须补发 `role_permissions`**，否则 `@PreAuthorize` 永远 403 |
| 无任何脚本调用 C 端写接口（`loadtest/` 里 `/api/products` 全是 GET `/reviews`） | 已 grep 确认 | **迁移零破坏**，不会弄红既有验收脚本 |
| `CategoryController.java:9-10` 有重复的 `@RestController` import | 同上 | 顺手清理 |

## 三、接口设计

### 3.1 管理端商品（`AdminProductController` → `/api/admin/products`）

| 方法 | 路径 | 权限码 | 复用/新增 | 说明 |
|---|---|---|---|---|
| GET | `/api/admin/products` | `product:list` | **新增** `pageAdminProducts` | 分页**含下架**；`status` 为可选过滤 |
| GET | `/api/admin/products/{id}` | `product:detail` | 复用 `getDetail` | 含 SKU + 图集；下架商品也能看 |
| POST | `/api/admin/products` | `product:create` | 复用 `createProduct` | body = `ProductCreateDTO` |
| PUT | `/api/admin/products/{id}` | `product:update` | 复用 `updateProduct` | **上下架也走这里**（`{"status":0}`） |
| DELETE | `/api/admin/products/{id}` | `product:delete` | 复用 `deleteProduct` | 软删主表，子表不动 |

### 3.2 管理端分类（`AdminCategoryController` → `/api/admin/categories`）

| 方法 | 路径 | 权限码 | 说明 |
|---|---|---|---|
| GET | `/api/admin/categories/tree` | `category:list` | 复用 `tree()`（含全部二级） |
| POST | `/api/admin/categories` | `category:create` | body = `CategoryCreateDTO` |
| PUT | `/api/admin/categories/{id}` | `category:update` | body = `CategoryUpdateDTO`（局部更新语义） |
| DELETE | `/api/admin/categories/{id}` | `category:delete` | 三重校验后才物理删 |

### 3.3 路径红线（Day 17 学到的教训）

> ⚠️ 管理端 Controller **绝不能挂 `/api/products/**` 或 `/api/categories/**`** —— 这两条 `GET` 在白名单里（先匹配先赢），挂上去会**静默公开、绕过全部鉴权**。一律 `/api/admin/...`。

## 四、权限地基：`backend/sql/07-admin-permissions.sql`（幂等）

1. **订正** `product:*`（id 1–5）的 `path`：C 端 → 管理端（`/api/admin/products`、`/api/admin/products/*`）。
2. **新增** 4 条分类权限（id 14–17）：`category:list` / `category:create` / `category:update` / `category:delete`。
3. **补发 `role_permissions`**：把 `category:%` 授给 **role 1（超管）** 与 **role 2（PRODUCT_ADMIN）**。
4. 文件结尾打印自检表（权限总数 / 已授权数 / 订正结果），与 `05-admin-permissions.sql` 同构。
5. 落库脚本 `backend/loadtest/day18-perm-apply.py`（Python 读 UTF-8 → `docker exec -i psql`，幂等可重跑）。

⚠️ **`03-data.sql` 里那两条 `INSERT ... SELECT ... WHERE p.code LIKE 'product:%'` 只在首次种子跑过** —— 新权限不会自动落到角色上，这正是上面第 3 步存在的理由。

## 五、六条链路（沿用 Day 17 节奏：写 → 编译 → 起应用 → 验收 → M1 回归 → 提交推送）

| 链路 | 内容 | 验收脚本 |
|---|---|---|
| **A** | 权限地基（SQL 07 + 落库 + 自检 + 订正核对） | `day18-a-perm-verify.py` |
| **B** | 管理端商品读（分页含下架 + status 过滤 + 详情 + 权限 403） | `day18-b-admin-product-read-verify.py` |
| **C** | 管理端商品写 + **C 端写接口迁移**（新增/改/删/上下架 + 迁移证据） | `day18-c-admin-product-write-verify.py` |
| **D** | 管理端分类读（树 + 权限） | `day18-d-admin-category-read-verify.py` |
| **E** | 管理端分类写（新增/改/删 + 三重引用校验） | `day18-e-admin-category-write-verify.py` |
| **F** | 全量复跑 + M1 回归 198/198（含逐字节回基线） | `day17-m1-regression.py` |

## 六、本日几个「新概念」（值得单独记）

### 6.1 同一个 Service，两个相反的过滤口径

```
C 端 pageProducts     ：.eq(status, 1)                    ← 写死：只看上架
管理端 pageAdminProducts：.eq(status != null, status)      ← 条件：不传就全都要
```

不是写两份查询，而是**把「过滤」变成参数**。`fillNames`（补分类名/品牌名）这段逻辑两边共用 → 抽成私有方法。

### 6.2 ★★ `@TableLogic` 会污染「引用计数」—— 分类删除的头号陷阱

删分类前要问「还有商品挂在这个分类下吗」。直觉写法：

```java
productMapper.selectCount(new LambdaQueryWrapper<Product>().eq(Product::getCategoryId, id))
```

看起来对，但 `Product` 上有 `@TableLogic` → MP **自动追加 `AND is_deleted = 0`** →
**已被软删的商品被漏算** → 校验通过 → 物理删分类 → **撞 `fk_product_category` 报 500**。

⇒ 必须用手写 SQL **绕开逻辑删除**（`SELECT count(*) FROM products WHERE category_id = ?`，**不带** `is_deleted` 条件）。
⇒ **判据：引用计数的口径必须与「外键的口径」一致 —— 外键不认识 `is_deleted`，计数就不能带它。**

### 6.3 迁移的「正面证据」是 405，不是 404

删掉 C 端写接口后，`POST /api/products` 的表现：

| 请求 | 预期 | 为什么 |
|---|---|---|
| 匿名 `POST /api/products` | **HTTP 401** | 不在白名单（白名单只放 `GET`）→ 先过认证关 |
| 带 C 端 token `POST` | **HTTP 405** | 已认证 → 进 DispatcherServlet → 该路径只剩 `GET` 映射 → 方法不允许 |
| 带管理员 token `POST` | **HTTP 405** | 写能力已迁走，管理员也得走 `/api/admin/products` |

★ 405 与 404 的区别就是「路径还在、方法没了」—— 这正是「迁移完成」的断言。

#### ★ 实测更正：405 差点出不来（2026-09-23 真实缺陷）

链路 C 第一次跑，三条迁移断言**全红**——`POST /api/products` 返回的是
**HTTP 200 + `{"code":500,"message":"fail"}`**，而不是 405。

原因在 `GlobalExceptionHandler`：

```java
@ExceptionHandler(Exception.class)          // ← 什么都接的兜底
public Result<Void> handleException(Exception e){
    log.error("系统异常", e);
    return Result.error(ResultCode.FAIL);   // ⇒ HTTP 200 + code=500
}
```

`HttpRequestMethodNotSupportedException` 也是 Exception 的子类，没有更具体的
handler，于是被这条兜底吃掉。后果有两个，都不轻：

1. **「调用方用错方法」被误报成「服务端故障」**，还白打一条 ERROR 堆栈，排障方向被带偏；
2. **405 与「路径根本不存在」无法区分** —— 实测 `POST /api/nonexistent` 同样是
   `200 + code=500`，迁移断言失去全部分辨力。

⇒ 修复（新增一个更具体的 handler，Spring 会优先选它）：

```java
@ExceptionHandler(HttpRequestMethodNotSupportedException.class)
@ResponseStatus(HttpStatus.METHOD_NOT_ALLOWED)
public Result<Void> handleMethodNotSupported(HttpRequestMethodNotSupportedException e){ ... }
```

修完实测：`http=405` + `{"code":405,"message":"请求方法不支持，支持的方法：[GET]"}`。

★ **判据（可复用）**：本项目「HTTP 200 + body.code」的约定只覆盖
**业务结果**（请求合法、业务不同意）。**协议层拒绝**（401/403/405）必须给真实状态码，
否则「客户端的错」与「服务端的错」在日志和响应里长得一模一样。
§6.5 的教训在这条上再来一次：**同一个 handler 的粒度，决定了两类错误的可见性**。

### 6.4 ★★ `@Valid` 跑在 `@PreAuthorize` 之前（Day 18 冒烟实测）

给 `POST /api/products` 发一个**缺 `name` 的 body**，再分别用 C 端 token / 管理员 token 去打，
两次都得到 **`code=400`「名称不能为空」** —— 而 `demo`（C 端 token，`perms` 是空集）
本该被 `@PreAuthorize('product:create')` 拦成 403。

原因：两者的执行层不同。

| 环节 | 发生在 | 谁负责 |
|---|---|---|
| 参数绑定 + `@Valid` 校验 | **方法调用之前**（HandlerAdapter 解析参数） | Spring MVC |
| `@PreAuthorize` | **方法调用之时**（方法级 AOP 拦截） | Spring Security |

⇒ **校验层在授权层外边**，所以「非法请求」永远先撞 400，与调用者有没有权限无关。

两条推论（都写进了验收脚本的做法里）：

1. **断言权限必须给合法载荷** —— 否则你测到的是校验，不是权限（`day18-skeleton-smoke.py`
   第 2 节的 POST/PUT 都带完整合法 body，正是为此；只有第 4 节的迁移探测故意用非法载荷）。
2. **无权限的人也能看见校验消息** —— 所以 `@NotBlank(message=...)` 里别写敏感规则
   （本项目的消息都是「分类不能为空」这类中性文案，没有踩这个坑，但值得作为约定记住）。

### 6.5 ★ 探测「可能还活着的写接口」不能用合法载荷（一次真实事故）

`day18-skeleton-smoke.py` 的迁移探测栏最初用**合法 body + 管理员 token** 去打
`POST /api/products`「看看接口还在不在」，结果：

```
POST /api/products  admin(超管)  HTTP 200  {"code":200,"message":"success","data":22}
```

**它真的写进了一行商品**（id=22）—— 因为那个接口在 Day 09-11 就已经是完整实现，
而管理员确实带着 `product:create` 权限。

| 探测方式 | 迁移前 | 迁移后 | 副作用 |
|---|---|---|---|
| 合法载荷 | 200 写入 ❌ | 405 | **写库** |
| ★ 非法载荷（缺必填） | 400（`@Valid` 拦住） | 405 | 零写入 ✅ |

⇒ **判据：探测一个「可能还活着」的写接口，要让它死在更早的一层。**
只需保证「迁移前 vs 迁移后」的结果可区分即可，不必真的把它跑通。
事故残留用 `day18-cleanup-probe.py` 清理（先查子行引用，无引用才物理删；
本机实测 id=22 无任何子行，删后复查 0 行，种子 5 商品完好）。

### 6.6 夹紧放在哪一层：Service（本日订正了一处骨架缺陷）

骨架最初把「页码/页大小夹紧」写在 `AdminProductController.page` 的 TODO 里，并让它
「照抄 C 端 `page()` 的写法」—— 但 **C 端 `page()` 根本没有夹紧**（`ProductServiceImpl.pageProducts`
直接 `new Page<>(current, size)`）。照抄一个不存在的写法，只会让人来回找。

订正结果（与 Day 17 / mall-order / mall-inventory 同层）：

| 层 | 职责 | 依据 |
|---|---|---|
| `AdminProductController.page` | **一行转发** | 同 `AdminInventoryController`，Controller 只管转 |
| `ProductServiceImpl.pageAdminProducts` | 夹紧 + 条件查询 + 换壳 | `MAX_PAGE_SIZE = 100`，夹紧必须在 `new Page<>()` 之前 |

★ `MAX_PAGE_SIZE` 在本项目已是**第 5 份拷贝**（order / inventory×2 / review / product），
各处留注释互相指明，仍不抽 `mall-common`（那是一次跨模块重构，与本步无关）。

**顺带发现的两条既有遗留（本日只记录，不修）**：

1. C 端 `page()` / `pageProducts` **无夹紧** ⇒ `size<0` 会查全表、`size=0` 返空列表。
   属 Day 09-11 口径，被 M1 回归覆盖着，改它要单独评估影响面。
2. C 端 `getDetail` **不判 status** ⇒ 匿名也能读到「已下架」商品的详情，
   而 C 端列表却按 `status=1` 过滤 —— 同一个端的两条路口径不一致。
   本日管理端正好复用它（管理端本就要能看下架），但 C 端那条路建议排到后续 Day 处理。

### 6.7 ★★ 骨架门禁脚本必须有「骨架期护栏」（2026-09-23 事故）

`day18-skeleton-smoke.py` 第 2 节会真的调用 `POST/PUT/DELETE`。
骨架期零写入，是因为方法体是 `throw`；**实现填完之后再跑它，它就变成破坏性脚本**：

```
实测（实现已填完时误跑一次）：
  POST   /api/admin/products     → data=31        ← 真新建了商品
  PUT    /api/admin/products/1   → 200            ← 改了种子商品 1
  DELETE /api/admin/products/1   → 200            ← 【软删了种子商品 1】
  POST   /api/admin/categories   → data=36 / 37   ← 真新建了分类
  PUT    /api/admin/categories/1 → 200            ← 把分类 1 的 sort_order 改成 99
```

修复分两步：① 数据层面按种子 SQL 逐字段还原（商品 1 的 `subtitle` 与
`is_deleted`、分类 1 的 `sort_order`，并物理删掉 id=31 / 36 / 37）；
② **给脚本加护栏** —— 开跑前扫描源码里还剩几处 `UnsupportedOperationException`，

```python
_throws = skeleton_remaining()
if _throws == 0:      # 骨架期已过 → 立刻停，一个写端点都不许打
    ...; raise SystemExit(0)
```

⇒ **判据：任何「靠异常/占位来保持无害」的探测脚本，都要把「前提是否还成立」
写成可执行检查。** 前提一旦消失，脚本的语义会翻转，而它自己不会告诉你。

## 七、验收清单（写脚本时逐条落成断言）

> 以下六条**已全部跑通**（2026-09-23），逐条落成了断言。

- [x] **A**：`07` 幂等；`category:*` 恰好 4 条；id 14–17 无空洞；role 1/2 均已授权；`product:*` 的 path 已订正为管理端。（`day18-perm-apply.py` → VERDICT OK）
- [x] **B**：管理员分页**能看到下架商品**（C 端看不到同一条）；`status=0` 过滤生效；`size<1` 夹紧到 1；`size>100` 夹到 100；下架商品详情仍可读；`op_order` 打 `product:list` → **403**；匿名 → **401**。（**51/51**）
- [x] **C**：新增 → 改 → 上下架 → 软删 全链路；`sku_code` 撞库回滚（主表不残留半成品）；删后 `is_deleted=1` 且 SKU 行原封不动；**迁移证据**（匿名 401 / C 端 token 405 / 超管 405，GET 仍 200）。（**42/42**）
- [x] **D**：树两层、`sort_order` 升序、无权限 403、匿名 401、`op_product` 与超管树**逐字节相同**、C 端树红线仍 200。（**16/16**）
- [x] **E**：新增顶级 + 二级；**三级被拒 400**；父不存在 → 404；改名生效；**`parentId=null` = 不动**；**有子分类 → 400**；**有商品 → 400**；★★ **商品已软删也拒绝**；无引用 → 物理删成功（DB 行数 0）。（**40/40**）
- [x] **F**：M1 回归 **198/198** + 逐字节回基线（`BASELINE RESTORED: YES`）；B/C/D/E 四脚本均可重复执行。

## 八、风险与注意

1. **数据权限反转的反面检查**：管理端 Controller 里**不允许出现 `requireOwn`**（可断言）。
2. **`@TableLogic` 漏算**（§6.2）是本次最容易写错、且报错在「运行期 + 500」的一处 —— 单靠编译和 M1 回归都拦不住。
3. **夹具**：分类写测试会**新增/删除真实分类行**，必须用高水位线清理；商品测试新增的商品要软删 + 清引用，避免污染库里既有的 5 个种子商品。
4. **权限补发漏了 = 永远 403**：`op_product` 夹具（PRODUCT_ADMIN）正好用来验证「有 `product:*` + 有 `category:*`、没有 `order:*`」。
5. 迁移只动 Controller，**不要顺手改 Service 的既有实现**（Day 09–11 的注释与设计仍然有效）。
