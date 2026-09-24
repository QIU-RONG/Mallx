# MallX 技术债与遗留补漏清单

> 建立于 Day 20（优惠券阶段一地基之后）。此前这些遗留分散在 `docs/daily/Day-18-*.md §6.6`
> 与 `docs/daily/Day-19-*.md §遗留` 里，本文件把它们收拢成**可执行**的条目：
> 每条都能回答「改哪个文件的哪一行 / 改完怎么证明确实改好了 / 会不会碰坏别的链路」。
>
> **状态图例**：⬜ 未开工 · 🔄 进行中 · ✅ 已完成 · ⏸️ 明确不做（附理由）

## 〇、一览

| 编号 | 条目 | 影响面 | 改动量 | 风险 | 状态 |
|---|---|---|---|---|---|
| L1 | C 端商品列表无分页夹紧 | 接口健壮性 | 2 行 | 低 | ✅ 已修（33/33） |
| L2 | C 端商品详情不判上架（★ 有耦合） | 数据可见性 | 拆方法 | 低 | ✅ 已修（33/33） |
| L3 | 搜索的中文兜底漏了 `description` | 召回完整性 | 1 行 SQL（★ 连带改断言） | 中 | ✅ 已修（day19 58/58） |
| L4 | 搜索的 `categoryId` 不展开子分类 | 两入口口径不一 | 改签名 + XML | 中 | ✅ 已修（day19 58/58） |
| L5 | `brands` 零接口 | 缺字典查询入口 | 新模块级 | 低 | ✅ ① 已做（brand 24/24）；② CRUD 未做（★ 权限码改从 **39** 起，22–25/26–38 已被 Day 22/23 占掉） |
| L6 | 不存在的路径被兜底吞成 200+code=500 | 可观测性 | 1 个 handler | 低 | ✅ 已修（L5 验收顺带挖出） |
| L7 | 订单详情/列表看不到优惠额 | 信息完整性 | VO 2 字段 + 装配 2 行 | 极低 | ✅ 已修（**Day 22**，提交 `8248b59`；day17-b 的键集合回归盲区同批补上） |
| D21-A | `discount_rate` 三份口径对打（DTO `99.99` / 测试 `88.0` / 设计 `(0,1]`） | 金额正确性 | DTO 1 行 + 断言 +2 | 低 | ✅ 已修（决策 A；day20 **82/82**） |
| T1 | `MAX_PAGE_SIZE` 已复制 **6** 份 | 可维护性 | 跨模块重构 | 中 | ⏸️ ★ **触发条件已达成**（第 6 份在 `AdminUserServiceImpl.pageUsers`），是否抽待拍板 |
| T2 | `day17-a` / `day17-b` 不在 M1 名单里 | 回归盲区 | 改 M1 脚本名单 | 低 | ⬜ 未开工（Day 22 实证：L7 加字段后它的「键集合相等」断言会静默失败） |

**关键前提（已核实）**：M1 回归三个脚本（`day14-e2e-walk.py` / `day15-ship-confirm.py` /
`day16-review-e2e.py`）对 `/api/products` 的**全部访问只有 `/api/products/{id}/reviews`**
（grep 实证），**不打 C 端商品列表、也不打商品详情**
⇒ L1 / L2 的改动**不在 M1 覆盖率内，回归零风险**；L3 / L4 必须改脚本断言（见各条）。

**L6 是收尾时【新挖出来】的**（原清单没有）：写 L5 验收脚本时给「不存在的路径」断言 404，
结果实测拿到 **HTTP 200 + body.code=500 + message="fail"**。日志定位到
`NoResourceFoundException`（Spring 6.1+ 对无 handler 匹配的请求抛这个），
被 `GlobalExceptionHandler` 的 `Exception.class` 兜底先吃掉 —— 与 Day 18 修的
「405 被吞成 200+500」**是同一个坑的两个出口**。按项目自己的判据
（405 与 401/403 同类，都是框架层拒绝 ⇒ 给真实 HTTP 码）补了专用 handler。

---

## ✅ 已完成记录

### L1 + L2（Day 20 当天完成）

| 文件 | 改动 |
|---|---|
| `ProductServiceImpl.java` | `pageProducts` 加两行夹紧（`:82-83`）；类头 `MAX_PAGE_SIZE` 注释订正（原文写「C 端没有夹紧、属已知遗留」已过时） |
| `ProductServiceImpl.java` | `getDetail` 收紧为 C 端口径（加 `status != 1` → 伪装 404）；抽出 `getAdminDetail`；装配逻辑下沉到私有 `assembleDetail(Product)` 共用 |
| `ProductService.java` | 新增 `getAdminDetail(Long)` 声明 |
| `AdminProductController.java` | `detail` 改调 `getAdminDetail`（原来误调 C 端的 `getDetail`） |
| `day20-l1l2-verify.py`（新建） | **33 条断言**，含造数 + 高水位线清理；报告 `day20-l1l2-verify-report.txt` |

**验收结果**：`day20-l1l2-verify.py` **33 / 33 全绿**；`day17-m1-regression.py` **198 / 198**
＋ `BASELINE RESTORED: YES`。

**★ 本次最值钱的一条实测教训**：`size=-1` 夹紧后返回 **1 条**，不是 100 条。
夹紧公式 `min(max(size, 1), 100)` 把**负数夹到【下限 1】**（与 Day 18/19 那三处同一个公式）。
我第一版断言写的是「负数 → 上限 100」，**脚本错了、代码没错** ——
按铁律「断言对着【设计】写，脚本与设计打架时改脚本」修的是脚本。
⇒ 两个方向要分别钉：`size=-1 → 1`（下限）、`size=1000 → 100`（上限）。

**★ 可复用的方法论**：验证「夹紧/上限」这类改动时，**样本量必须超过上限才有区分度**。
库里只有 5 条商品，`size=-1` 夹紧前后都是 5 条 —— **用现有数据根本区分不出来**。
所以验收脚本里临时造了 150 条（`name` 前缀 `L1-TEMP-` 隔离 + 高水位线清理），
造到 155 条之后「`size<0` = 不限量」这个洞才暴露得出来。
（`size=0` 是意外好用的免费判据：夹紧后 1 条、未夹紧 0 条，不需要造数据就能区分。）

---

### L3 / L4 / L5① / L6（Day 20 收尾「先清支线」一轮做完）

| 文件 | 改动 |
|---|---|
| `ProductMapper.xml` | `searchProducts` 召回加 `OR p.description ILIKE ...`（L3）；`categoryId` 等值 → `IN` + `<foreach>`（L4） |
| `ProductMapper.java` | `@Param("categoryId") Long` → `@Param("categoryIds") Collection<Long>`（L4）+ import `java.util.Collection` |
| `ProductServiceImpl.java` | `searchProducts` 传 `expandCategoryIds(categoryId)` 的集合（L4）；清掉「骨架，方法体由你写」的过期 javadoc |
| `BrandVO / BrandService / BrandServiceImpl / BrandController / AdminBrandController`（新建 5 个） | L5①：`GET /api/brands`（公开，仅 status=1）+ `GET /api/admin/brands`（brand:list，含停用） |
| `SecurityConfig.java` | 白名单加**精确路径** `GET /api/brands` |
| `sql/10-brand-permissions.sql`（新建） | `brand:list` = id **21**，发 role 1 + role 2，role 3 刻意不给；含序列校准与三段自检 |
| `GlobalExceptionHandler.java` | L6：加 `NoResourceFoundException` 专用 handler → 真实 HTTP **404**（原先被兜底吞成 200+code=500） |
| `day19-search-verify.py` | 48 → **58** 断言：B10 改口径 + B11 新增（纯 fts 替代证据）、E 组 6→8、新增 I 组 7 条（categoryId 同口径） |
| `day20-l5-brand-verify.py`（新建） | **24** 断言：C 端字典 / 白名单三态 / 权限矩阵 / 两端口径差异 / 清理回基线 |
| `day20-l5-perm-apply.py`（新建） | 权限落地 + 幂等（照 `day18-perm-apply.py` 模板） |
| `day14-reconcile.py` | `[4]` 段那行 `VERDICT:` 改标签为 `[4] BYPASS-AUDIT (expected false):`（见附一①） |

**验收结果**（同一轮内跑完，应用只起一次）：

| 脚本 | 结果 |
|---|---|
| `day19-search-verify.py` | **58 / 58**（含 L3 的 E3「笔记本 0→2」、L4 的 I1/I2「父分类与列表同答案」） |
| `day20-l5-brand-verify.py` | **24 / 24** |
| `day20-l5-perm-apply.py` | **VERDICT: OK** —— 幂等成立，`1/1/1/0` 四列全中 |
| `day14-reconcile.py` | **27 / 27**（定性见附一①） |
| `day17-m1-regression.py` | **198 / 198** + `BASELINE RESTORED: YES` |
| `day19-xml-check.py` | XML 良构 **3/3**、Java↔XML 双向一致、SQL 停在 TODO **0** 条 |

**★★ 本轮最值钱的三条**

1. **断言必须对着「设计」写，但「设计」要先确认** —— L5 脚本初版给「不存在的路径」断言 404，
   实测却是 **200 + code=500**。这里正确的做法不是「照实测改脚本」（那会把一个缺陷写进
   验收基线），而是先查日志（`NoResourceFoundException`）确认这是**兜底的漏网**，
   再按项目自己的判据（405 与 401/403 同类 ⇒ 给真实 HTTP 码）补 handler。
   **实测值 ≠ 设计，两者不一致时先定性，再决定改哪边。**
2. **L3 的「副作用」比 L3 本身更值得记** —— 补一列 ILIKE 把 Day 19 那条
   「纯全文召回」的证据链打断了。改召回范围前要先问：**还有哪些断言是靠
   『这条路径命不中』成立的？** 替代证据（B11：直接对 DB 断言 `ts_rank` 值）已经补上。
3. **「停止条件下沉到数据里」能省掉一整套反向对照** —— L5 只要造 **1 条 status=0 的品牌**，
   就让「C 端看不见 / 管理端看得见」变成可断言的差异（D1/D2/D3）；
   库里 7 条品牌全是 status=1 时，这条断言**恒真**，等于没验（同 L1 的「样本量陷阱」）。

---

### D21-A · `discount_rate` 三份口径对打（Day 21 实现时挖出，同日收口）

**怎么发现的**：写 `calcDiscount`（券抵扣计算）时拿 `CouponCreateDTO` 的上限当参照，
发现**同一件事有三份口径在互相打架**：

| 出处 | 口径 | 性质 |
|---|---|---|
| `CouponCreateDTO` | `@DecimalMax("99.99")` | 理由只写了「列 `NUMERIC(5,2)` 整数部分最多 3 位」—— 把**存储容量**当成了**业务约束** |
| `day20-coupon-verify.py` I3 | `rate=88.0` 当合法值 | 顺着 DTO 写出来的 ⇒ 典型的「照着实现写断言」产物 |
| `Day-21-*.md` / `calcDiscount` / `CouponUseVO` | **应付比例系数 `(0,1]`** | 本日设计 |

⇒ 后果：一张 `rate=88` 的券**建得出来、永远用不了**（`calcDiscount` 会拒它）。
★ 阶段一没有任何断言看得见 —— **那时还不算钱**；等到算钱那天才现形。

**决策 A（取「系数」口径）落地**

| 文件 | 改动 |
|---|---|
| `CouponCreateDTO.java` | `@DecimalMax` `99.99` → **`1.00`**；消息改「折扣率不能大于 1（0.80 表示打 8 折）」；类注释把「列宽」理由换成业务理由，并记下这次订正 |
| `day20-coupon-verify.py` | I3 数据 `88.0 → 0.88`；**新增 I3b**（`1.01` → 400）/ **I3c**（`1.00` → 200）；`EXPECTED` 80 → **82** |

**为什么取系数而不是百分数**：① 与 `BigDecimal` 直接相乘，公式里不出现 `100` 这个魔法数；
② `(0,1]` 之下 `88.0` 这种错值**一眼就是错的**，而百分数口径下 `0.88`
（那是 0.88% 折扣）看起来完全正常 —— **口径本身要能自证对错**。

**验收结果**：`day20-coupon-verify.py` **82 / 82** `VERDICT: OK 全绿`（I3b/I3c 两条新断言实测 PASS）；
`day17-m1-regression.py` **198 / 198** + `BASELINE RESTORED: YES`；`mvn -o install` **12 / 12**。

**★ 两条通用教训**

1. **「钉死约定」不能只在用它的那一端钉** —— 要顺着字段把**写入口**（DTO / 建券接口）
   与**读出口**（`calcDiscount`）一起改。这与 L4（`categoryId` 两入口口径不一）、
   Day-21 §九 第 11 条（窗口判据只判一半）是**同一个动作**：
   *同一个业务概念，两端口径必须同源*。
2. **改了校验上限就必须留断言** —— 不加 I3b/I3c，`99.99 → 1.00` 这个改动
   **没有任何东西覆盖**，等于把同一个漂移换个方向再犯一次。
   ★ 顺带实证：`EXPECTED` 常量没同步时，脚本护栏**第一次跑就报出来**
   （「断言总数与 EXPECTED 不符」）—— 这道护栏值得一直留着。

---

## L1 · C 端商品列表无分页夹紧

**现状（实证）**

| 位置 | 代码 | 有无夹紧 |
|---|---|---|
| `ProductServiceImpl.java:78`（C 端 `pageProducts`） | `this.page(new Page<>(current, size), wrapper)` | ❌ **无** |
| `ProductServiceImpl.java:105-106`（管理端 `pageAdminProducts`） | `long safePage = Math.max(current, 1); long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);` | ✅ 有 |

**影响**
`GET /api/products?size=-1` 撞 MyBatis-Plus 的 `size < 0` 语义 —— **不限量、查全表**。
现在只有 5 条商品看不出来，数据长起来就是「一次请求全表扫描 + 全量序列化」，
可以被拿来当廉价的 DB 打点。`size=0` 更迷惑：返回空列表但 `total` 正常，看着像接口坏了。

**修法**
把 `:105-106` 那两行抄进 `pageProducts`，`new Page<>(safePage, safeSize)`。
★ **夹紧必须写在 `new Page<>()` 之前**（写进构造参数里就晚了）。

**⚠️ 不要顺手改别的**
`pageProducts` 里那三行 `eq/in/like` 是 Day 09–11 的口径，其中 `like`（大小写敏感）
是 Day 19 链路 B 的**对照组前提**（`GET /api/products?keyword=iphone` 期望 **0 条**，
用来反衬 `/api/products/search` 的全文召回）。只加夹紧，不碰过滤。

**验收断言**（★ 前两条在本节初稿里都写错了，以「已完成记录」的实测为准）
1. `GET /api/products?current=1&size=-1` → `records` **恰好 1 条**（负数被夹到下限 1），
   `total` 与真实行数一致；★ **未夹紧时这里会返回全表**，这才是要堵的洞；
2. `GET /api/products?current=1&size=0` → `records` **恰好 1 条**（`Math.max(0,1)=1`），
   `total` 仍为真实值（夹紧不改过滤口径）；
3. 上限方向：临时造到 155 条后 `size=1000` → `records` 恰好 100 条；
4. 回归：`day19-search-verify.py` 链路 B 仍 0 条（证明确实没动 `like`）。

---

## L2 · C 端商品详情不判上架（★ 不是一行能改的）

**现状（实证）**
`ProductServiceImpl.getDetail:233-237` 只判 `null`，**不看 `status`**：

```java
Product product = this.getById(id);
if (product == null) { throw new BusinessException(...); }
```

**★★ 隐藏耦合（本清单新挖出来的）**：这**同一个方法**被两个入口共用 ——
`ProductController.java:56`（C 端，白名单公开）与
`AdminProductController.java:90`（管理端，语义注释明确写着「**下架商品也能看**」）。

⇒ 直接在 `getDetail` 里加 `status != 1` 判断，会**同时砸掉管理端**：
管理员将再也打不开下架商品的详情页 —— 而这恰恰是他要改价、要重新上架的对象。

**影响**
下架商品只是从列表消失，**直达链接 `GET /api/products/{id}` 照样返回完整详情 + SKU + 图集**。
现在库里 5 条全上架，所以现象为零；一旦有下架商品就是「下架=没下架」。

**修法（必须拆路，二选一）**

| 方案 | 做法 | 评价 |
|---|---|---|
| (a) 加参数 | `getDetail(Long id, boolean forAdmin)` | 签名变，调用方都要传布尔 —— 可读性差 |
| **(b) 拆方法** ★推荐 | 保留 `getDetail` 收紧为 C 端口径；新增 `getAdminDetail(id)` 给管理端 | 两个语义各自独立、**可分别断言**；C 端那条是「加判断」，改动最小 |

无论哪种，**伪装 404** 要与项目惯例一致：C 端拿到下架商品时抛 `NOT_FOUND`
（「伪装 404」，不是 403 —— 不泄露「这个 id 存在但下架了」）。

**验收断言（反向对照是核心）**
1. 取一条商品 PUT 成 `status=0`；
2. C 端 `GET /api/products/{id}`（匿名）→ `code = 404`；
3. 管理端 `GET /api/admin/products/{id}`（带 `product:detail`）→ `code = 0` 且 `skus`/`images` 完整；
4. ★ **同一 id、同一时刻，两个接口结果必须不同** —— 这一步才证明「拆路」真的拆开了
   （如果两边都 200，说明改成了共用方法；都 404，说明砸了管理端）；
5. 收尾把该商品改回 `status=1`，并确认 `day19-skeleton-smoke.py` 的 `GET /api/products/1` 仍 200。

---

## L3 · 搜索的中文兜底漏了 `description`（★ 会连带削弱一条证据）

**现状（实证）**
`ProductMapper.xml:91-94` 的召回条件是：

```
p.search_vector @@ plainto_tsquery('simple', #{keyword})
OR p.name     ILIKE '%' || #{keyword} || '%'
OR p.subtitle ILIKE '%' || #{keyword} || '%'
```

而 `search_vector` 由触发器按 **name(A) + subtitle(B) + description(C)** 三列维护
（Day 19 用 `to_tsvector` 实测过权重可见）。
⇒ **两侧列范围不对称**：全文看三列，ILIKE 只看两列。

**影响 —— 造出「搜索黑洞」**
`description` 里的**中文词**：全文匹配不了（`simple` 字典不切中文，整段成 token）、
ILIKE 又不看 description ⇒ **永远搜不到**。
实测活例：`keyword=笔记本` → **0 条**，因为「笔记本」只出现在商品 4/5 的 `description`
（逐列矩阵实证：`in_name|in_subtitle|in_desc` = f/f/t）。

**修法**
加一行 `OR p.description ILIKE '%' || #{keyword} || '%'`。
代价：description 是 TEXT，扫更多 —— 但这条查询**本来就是全表扫**
（前导 `%` 废掉索引），**不改变复杂度**，只是把已有的扫扩大一列。

**★★ 必须同时改断言：这会削弱 Day 19 的一条证据链**
`promotion` 之所以是「纯全文召回」的干净证据，**前提正是 description 不在 ILIKE 范围内** ——
它只存在于 `description`，两条 ILIKE 都命不中，所以「接口返回 1 条且 `searchRank > 0`」
不可能是 ILIKE 侥幸。补上 description 之后：
- `promotion` 会被 ILIKE 命中 ⇒ **它不再是纯全文证据**；
- 更根本地：ILIKE 的列范围 = 全文的列范围（且 ILIKE 只会更宽）
  ⇒ **在 C 端搜索接口上，「纯全文召回」这类证据再也造不出来了**。

替代验证路径（改 `day19-search-verify.py` 时用）：
1. 直接对 DB 打 fts 查询，断言 `search_vector @@ plainto_tsquery(...)` 为真且 `ts_rank > 0`；
2. 保留**相关性排序**那条（`pro`：商品 1 命中 name(A)+subtitle(B)、商品 2 只在 name(A)
   ⇒ `0.668720 > 0.607927`，降序可断言）—— 它验的是 fts 的 `ts_rank` 列本身，不受 ILIKE 影响；
3. 断 `search_rank` 字段值本身（ILIKE 命中不会让 `ts_rank` 变大）。

**验收断言**
1. `keyword=笔记本` → **2 条**（id 4、5）；
2. `keyword=promotion` → 仍 1 条，但**断言口径改成「能被 ILIKE 命中」**，不再声称纯全文；
3. `keyword=轻薄` → 仍 ≥1 条（Day 19 链路 E 用词，改前 fts=0 / ILIKE subtitle=1）；
4. 回归 `day19-search-verify.py` **全绿（改过的版本）**。

---

## L4 · 搜索的 `categoryId` 不展开子分类

**现状（实证）**
- C 端列表：`ProductServiceImpl.expandCategoryIds:183-195` → 「自己 + 直接子分类」集合，
  配 `.in(categoryId != null, Product::getCategoryId, ids)`；
- C 端搜索：`ProductMapper.xml:102` → `AND p.category_id = #{categoryId}` **精确等值**。

**影响**
**同一个 C 端、同一个诉求，两个入口给不同答案**：
`GET /api/products?categoryId=1` 查得到二级分类 11 下的商品，
`GET /api/products/search?categoryId=1` 查不到。这类「口径不一致」不报错、不 500，
是最难被发现的一类缺陷（Day 19 已经因为同类问题付出过一次代价）。

**修法（推荐 b）**

| 方案 | 做法 | 评价 |
|---|---|---|
| (a) SQL 内展开 | XML 里写递归 CTE / 子查询 | 逻辑两处实现，与 `expandCategoryIds` 必然漂移 |
| **(b) Service 层复用** ★ | `searchProducts` 调 `expandCategoryIds(categoryId)` 得到 `Set<Long>`；XML 收 `Collection<Long>` 走 `<foreach>` | 与列表**完全同源**，口径不可能再漂 |

走 (b) 要同步改三处：
1. `ProductMapper.java#searchProducts` 签名：`Long categoryId` → `Collection<Long> categoryIds`
   （★ 方法名与 XML `id` 逐字符一致这条铁律照旧）；
2. XML：`<if test="categoryIds != null and categoryIds.size() > 0"> AND p.category_id IN <foreach ...> </if>`
   （★ 空集合要挡掉，否则生成 `IN ()` 语法错）；
3. `ProductServiceImpl.searchProducts`：把 `categoryId` 换成展开后的集合再传
   （★ `expandCategoryIds` 内部已挡 null，与列表侧同一个方法，别复制逻辑）。

**验收断言**
1. `categoryId=1`（父分类）→ search 的 `total` **等于** `/api/products?categoryId=1` 的 `total`；
2. `categoryId=11`（子分类）→ 两端 `total` 也相等（★ 父子都验，只验一边证明不了「展开」）；
3. 不传 `categoryId` → 仍返回全部（空集合分支没被误触发）。

**依赖关系**：L3 与 L4 改的是**同一个 XML**，建议 L3 先做、L4 后做，一次只动一个变量。

---

## L5 · `brands` 零接口

**现状（实证）**

| 存在 | 缺失 |
|---|---|
| `entity/Brand.java`、`mapper/BrandMapper.java` | `BrandController` / `BrandService` |
| 6 条种子数据（`03-data.sql:33-44`：Apple / Huawei / Xiaomi / Samsung / Lenovo / DJI） | `brand:*` 权限码（★ 写这条时的 `permissions` max id = 20，**现为 38**） |
| 被 `ProductServiceImpl.fillNames` 用于补 `brandName`（只读） | C 端「品牌清单」入口 |

**影响**
商品列表 / 详情**都带 `brandName`**，所以业务上不缺能力；缺的是**「有哪些品牌」这个字典查询**——
前端做品牌筛选时没有任何可选值来源（只能靠遍历商品反推）。

**修法（建议分两步，别一次做满）**

| 步骤 | 内容 | 权限 |
|---|---|---|
| ①（建议先做） | `GET /api/brands`（公开，返回字典列表）+ `GET /api/admin/brands`（`brand:list`） | 补 `brand:list` = id **21** |
| ②（留给后续） | 管理端 CRUD：`create` / `update` / `delete` | ★ **id 改用 `39` / `40` / `41`** —— 本文档原文写的是 22/23/24，**已被占用**：Day 22 拿走 `user:detail(22)` / `user:status(23)` / `dashboard:overview(24)`，Day 23 的 RBAC 再拿走 26–38 ⇒ **现 max = 38**。按 Day 20 的 `08-marketing-permissions.sql` 那套幂等补发 |

★★ **白名单粒度照 Day 20 的教训办**：加 `GET /api/brands` 用**精确路径**，
**绝不能**写 `/api/brands/**` —— 否则以后在这个前缀下加任何私有接口都会被**静默公开**
（Day 20 的 `/api/coupons` vs `/api/coupons/my` 就是这个坑的实测版本）。

⚠️ **删除品牌要判引用**：`products.brand_id` 外键是 NO ACTION（谁引用我决定我能否物理删）。
判「该品牌下有没有商品」时**不能用 `selectCount`** —— `@TableLogic` 会自动追加
`is_deleted = 0`，漏算已软删商品 ⇒ 以为空着 → 物理删 → 撞 `fk_product_brand` 现场 500。
正确做法照 `ProductMapper.xml#countByCategoryId`：**手写 XML 绕开 `@TableLogic`**，
让计数口径与外键口径一致（Day 18 最值钱的一条教训）。

---

## L7 · 订单详情/列表看不到优惠额（Day 21 收尾时登记）

**现状（实证）**
Day 21 给 `orders` 加了 `discount_amount` 并在下单链路写入（`pay = total − discount`），
但两个出参 VO 都**没有这个字段**：

| 位置 | 有 | 缺 |
|---|---|---|
| `OrderDetailVO`（`GET /api/orders/{id}`） | `totalAmount` / `payAmount` | **`discountAmount`** |
| `OrderVO`（`GET /api/orders` 列表） | 同上 | **`discountAmount`** |

**影响**
用户看到「实付 80」，看不到「原价 100、省了 20」。券的**效果**在最该出现的界面上不可见 ——
业务上不算错（金额是对的），但「用了券」这件事从详情接口完全读不出来，
前端只能靠 `total − pay` 自己反推（Day 21 特意落库快照就是为了**不让下游反推**）。
★ 严重度低于本清单其他条目：**不影响正确性，只影响可读性**。

**修法（极低风险，但要重跑 M1）**
1. `OrderDetailVO` / `OrderVO` 各加 `private BigDecimal discountAmount;`
2. `OrderServiceImpl.buildDetail` / `toOrderVO` 各加一行 `vo.setDiscountAmount(order.getDiscountAmount());`
   （`detail` 与 `detailByAdmin` 共用 `buildDetail` ⇒ 一处改两处受益）
3. ⚠️ 这两个 VO 都在 **M1 覆盖的代码**上（Day 14/15/16 三条 E2E 都会读订单详情）
   ⇒ 改完**必须重跑 `day17-m1-regression.py`**（198/198 + `BASELINE RESTORED: YES`）。

**为什么 Day 21 没顺手做**：本日验收已经跑完（53/53 + 82/82 + 198/198），
再加字段就要**重跑一整轮 M1**；而这条不在 Day 21 的设计范围里（§八 断言清单没有它）。
⇒ 留给下一次改动它周边代码时捎带（**与改动同批 + 同一次回归**，别再单独起一轮应用）。

**验收断言（建议 3 条）**
1. 用券下单后 `GET /api/orders/{id}` → `discountAmount = 20.00`、`payAmount = 80.00`、
   `totalAmount = 100.00`（**三值同时断，光断 discount 不排除 pay 算错**）；
2. 不用券下单 → `discountAmount = 0.00`（不是 `null` —— 与 DB 的 `NOT NULL DEFAULT 0` 对齐）；
3. 全表恒等式 `pay_amount = total_amount - discount_amount` 仍成立（Day 21 那一条照抄）。

---

## T1 · `MAX_PAGE_SIZE` 已复制 5 份 —— 明确不做

`ProductServiceImpl.java:53` 的注释自己写着「与 `OrderServiceImpl` / `InventoryServiceImpl` /
`ReviewServiceImpl` 同一个值、同一套夹紧规则（**本处是第 5 份拷贝**）」，
并说明「仍不抽到 `mall-common`：那是一次跨模块重构，与本步无关」。

⏸️ **维持不抽**。理由：抽常量要动 5 个模块的 POM 可见性与编译边界，
收益只是省 4 行，风险却是 5 条已验收链路同时受影响。
**触发条件**：等出现第 6 份拷贝、或规则本身要变（比如上限从 100 调成别的）时再抽。

---

## 附一、三条与清单相邻的提醒

**① 一份报告里的 `VERDICT: false`** —— ✅ **已定性：误读，不是问题**
扫描 `backend/loadtest/*-report.txt` 时看到 `day14-reconcile-report.txt` 里写着 `VERDICT: false`。
它与当前 `day17-m1-regression.py` **198/198** 的状态不一致。
两种可能：报告是 Day 14 当时的产物（**陈旧**），或该脚本现在仍会失败（**真问题**）。
⇒ 建议**复跑一次 `day14-reconcile.py`** 定性；在复跑之前不要改动它、也不要把它当结论引用。

**【复跑结果（Day 20 收尾）】** `python day14-reconcile.py` → **27 / 27 passed**（rc=0）。
那个 `false` 既不是陈旧产物也不是真问题，而是 **`[4]` 段故意制造出来的**：
脚本在一个会 ROLLBACK 的事务里先做一次合法变动给账本打底，再做一次**绕过服务的裸
`UPDATE inventories`**（只改库存、不留流水），然后断言审计**必须**报 `false` ——
这正是「账本能抓到绕过应用的写」的正面证据。**断言是 `"VERDICT: f" in raw`，
也就是说那行 false 是 PASS 的条件。**

真正的坑是**标签本身的措辞**：报告里孤零零一行 `VERDICT: false`，
`grep VERDICT` 的人（包括当年的我）会把它当脚本失败 —— 和脚本末尾
`ASSERTIONS: 27 / 27 passed` 直接矛盾，于是去找一个不存在的 bug。
⇒ **已改**：标签改为 `[4] BYPASS-AUDIT (expected false): false`（期望值写进标签、断言同步改），
并在报告末尾加了三行阅读提示。报告已重新生成。
★ 一般化：**凡是「故意失败」的演示，输出里必须自带「这是故意的」字样**，
否则它一定会被后来的自动化或人误判。同 Day 20 那个「空语句体假过」是同一类问题的镜像。

**② 工作区残留目录**
仓库根有 `dsh-skin-v2/`、`dsh-themes/` 两个未跟踪目录，与本项目无关（未提交、未加 `.gitignore`）。
不影响 `git reset` / 分批提交的操作，但会让 `git status` 常驻噪声。

**③ ★★ `docs/api/users-api.md` 是【Day 06 的练手版】，等于给已修掉的漏洞留了份说明书**
（Day 23 开工前盘点时挖出）它躺在 `docs/api/`（**活文档**目录，不是 `docs/daily/` 的历史存档），
内容却停在 Day 06：

| 它现在写的 | 现实（Day 22 之后） |
|---|---|
| `GET /api/users/{id}`（`:105`），出参里明写 `"password": "demo123"`、注「学习阶段暂时返回」（`:132`） | 端点**不存在**；C 端已收口成 `GET /api/users/me`，返回 `UserVO`（**根本不含 password 字段**） |
| `PUT /api/users/{id}/nickname`（`:232`） | 端点**不存在**，改为 `PUT /api/users/me/nickname` |
| `DELETE /api/users/{id}`（`:210`） | 端点**不存在** |
| `GET /api/users` 分页（`:158`） | 端点**不存在**（管理端列表在 `/api/admin/users`） |

★ 危害两层：① 照着它调接口，全部 404；② **更糟的是它把那个越权漏洞写成了「预期行为」**
（`"password"`: 学习阶段暂时返回）—— 而 Day 22 已实证那是**全站口令哈希外泄**并修掉了。
⇒ 处理二选一：**改成现状**（推荐）或**在文件头明确标注「Day 06 历史快照，已失效」**。
⚠️ 这是 Day 22 收尾时**漏掉**的一步 —— 改了接口没同步 `docs/api/`，
正是项目一直在防的「同一个业务概念两处不同源」（与 L3 / L4 / D21-A 是同一个动作）。

---

## 附二、建议的执行顺序

```
L1（2 行，独立）─┐  ✅ 已完成
                 ├─→ 跑 M1 198/198 + day20-l1l2 33/33  ← 一次「纯增量」改动，已拿到干净基线
L2（拆方法）────┘  ✅ 已完成
                    ↓
L3（改 SQL）──→ 改 day19-search-verify.py 的 promotion 口径 ──→ 跑 day19 全绿
L4（改签名+XML）──→ 跑 day19 + day18-b（两端 total 对照）全绿
                    ↓
L5①（新端点 + 权限 id 21 + 精确白名单）──→ 门禁脚本照 Day 20 的 25 项模板再加 4 项
```

**实际执行记录（Day 20 收尾）**：上面这条链已全部走完，但有两处与计划不同，
写下来给下次参考 ——

| 计划 | 实际 | 为什么 |
|---|---|---|
| L3 → 单独跑一轮 → L4 → 再单独跑一轮 | **L3 + L4 一起改、一起跑** | 两者改的是**同一段 SQL**（`searchProducts` 的 `<where>`）。按原计划分两轮，编译与起应用的成本要付两遍，而收益（隔离变量）在本例里是假的 —— 真正需要隔离的是**断言**，不是 SQL：L3 打翻的是 B10/E1/E2/E3，L4 动的是新加的 I 组，两者在断言层面本来就分得开 |
| 「门禁脚本照模板再加 4 项」 | **新写 `day20-l5-brand-verify.py`（24 项）** | 原话指代不清（项目里没有一份 25 项的「门禁模板」）。实际做法：以 `day17-d-inventory-list-verify.py` 的权限矩阵 + `day20-coupon-verify.py` 的造数清理为底，按 L5 自己的语义设计 24 条 |

★ 另外**多出来一条 L6**（不在原清单）：L5 验收脚本要求「不存在的路径 → 404」，
实测却是 `200 + code=500`，顺着日志挖到了 `NoResourceFoundException` 被兜底吞掉。
**这是「写验收脚本」的额外收益**：为了让断言写对，必须先问清「设计上应该是什么」，
问的过程就撞出了一个真缺陷。写验收时不要顺着实测糊过去了事。

**每条做完都要做的三件事**（项目铁律，已固化在 `day1N-*` 脚本与记忆里）：
1. `dayNN-xml-check.py`（XML 良构 + Java↔XML 名字对齐）；
2. 起应用跑该条的验收断言（**不信接口自报，逐条 `psql` 对账**）；
3. `day17-m1-regression.py` **198/198** + `BASELINE RESTORED: YES`。
