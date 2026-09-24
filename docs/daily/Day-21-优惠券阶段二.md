# Day 21：优惠券（阶段二）—— 下单抵扣 + 核销 + 取消退券

> 方向：**A 优惠券 · 阶段二**（★ 本日**要动下单链路**）。陪练模式：本文档 + 结构改动 + 骨架由我出，**实现你亲手写**。
> 阶段一（建模块 + 发券 + 领券）已于 Day 20 验收（80/80），昨日收尾清掉了 L3/L4/L5①/L6 四条支线。

> 🔄 **状态：骨架已交付（2026-09-24），等你填 6 处 + 接 2 根线**
> - 结构改动已落：DDL 已入库、pom 已加依赖、DTO/实体已加字段、VO/常量/Mapper 声明/XML 骨架已在。
> - `mvn -o install -DskipTests` → **12/12 BUILD SUCCESS**。
> - `day20-xml-check.py` → XML 良构 **5/5**、Java↔XML **双向一致 0 差异**、
>   **空实现 3 条**（正是留空的 3 条 XML）、**Java 骨架占位 3 处**（正是 3 个 TODO）。
>   ★ `EXIT=1` 是**骨架期的正确长相**，不是脚本坏了 —— 它的护栏就是这个意思。

---

## 一、为什么是这一块

| 事实 | 依据 |
|---|---|
| Day 20 的文档自己写着「阶段二留 Day 21」 | `Day-20-优惠券.md:4`、§十 的分界表 |
| 券的**产生与获取**已完成；**使用**是零 | 6 个端点全是发券/领券/我的券，没有一个会改 `status` |
| V1.0 业务闭环真的就缺这一环 | 商品 → 购物车 → 下单 → 支付 → 库存 → 评价 **+ 券** |
| 下单链路上已经躺着一个「为今天准备」的注释 | `OrderServiceImpl.java:148` → `order.setPayAmount(totalAmount); // V1.0 无优惠` |

**★★ 本日的主风险是 M1 回归（198 条）**，而不是新功能写不出来。
M1 跑的就是**真实下单链路**（`day14-e2e-walk` / `day15-ship-confirm` / `day16-review-e2e`）。
⇒ 本日的兼容约束只有一条，但它是硬的：**不传券时必须完全走原路，一个字节都不变。**

---

## 二、开工前核查（逐条查过，不凭记忆）

| # | 事实 | 影响 |
|---|---|---|
| ① | `orders` 表**没有** `discount_amount`、也**没有** `user_coupon_id` 列（`01-schema.sql:175-192`，只有 `total_amount` + `pay_amount`） | 需要补 DDL；且**不需要**在 orders 上加券的外键 |
| ② | `user_coupons` 已有 `status` / `order_id` / `used_at` 三列（`01-schema.sql:282+`） | ★ **退券能按 `order_id` 反查** —— 这是「取消时怎么找回那张券」的答案，不用给 orders 加列 |
| ③ | `mall-order/pom.xml` 目前只依赖 `mall-common` + `mall-inventory`（**没有** marketing） | 需要加**1 处**依赖。父 POM 的 `<modules>:31` 与 `<dependencyManagement>:91` 在 Day 20 已含 `mall-marketing` ⇒ **不适用**「新建模块改 3 处 POM」 |
| ④ | `OrderCreateDTO` 只有 `addressId` **一个**字段 | 要加 `userCouponId`（可空） |
| ⑤ | `mall-marketing` 只依赖 `mall-common`，**不依赖** `mall-order` | ⇒ `order → marketing` **无环**，可以放心直连 |
| ⑥ | `OrderCancelExecutor.cancelOne` 是取消的**唯一收敛点**（用户取消 / 超时任务 / 管理员取消三条边都走它） | 退券只需接在**一个**地方，不用改三处 |

---

## 三、开工前定的四条设计决策（本日的「定性」）

| 决策 | 选定 | 理由 / 代价 |
|---|---|---|
| **核销时机** | **下单即核销**（`createFromCart` 里就改 `USED`），取消退券 | 与 Day 20 的 `received_count` CAS **逐字同构**，状态机只有两态。代价：下单到付款之间券被占用，取消/超时才退回。若改成「支付成功才核销」，要多一个 `LOCKED` 态，取消 / 超时 / 支付三条边都要处理锁 —— V1.0 不值当 |
| **优惠额落库** | **`orders` 加 `discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0`** | 三个金额里知道两个能反推第三个，但「能反推」≠「该反推」：① 分不清「没用券」与「用了 0 元券」；② 对账/退款都要自己再算一遍，规则一变口径就漂。快照是**事实** |
| **今日范围** | **核销 + 退券 + 验收，一次做完** | 退券与 `releaseLocked` 同构，放一起做能一次把「正向/逆向」两条边都验掉；拆开会多付一遍编译+起应用的成本 |
| **窗口判据对齐** | **`calcDiscount` 增判「尚未开始」**（`start_time` 在未来 → 400） | ★ 第 4 条是 2026-09-24 写 `selectForUse` 时**补出来的**：领券侧的 CAS（`CouponMapper.xml:44-45`）**早就守了窗口两端**（`start_time <=` / `end_time >=`），而 `calcDiscount` 原稿只判「已过期」，`startTime` 取回来却无人消费（**死列**）⇒ 定性是**补口径漂移**，不是加新功能 —— 与 L4（`categoryId` 两端口径不一）**同一族**。★ 库里现有券 `start_time` **全在过去** ⇒ 缺这条永远不现形（**样本量陷阱**，同 L1 / L5①） |

★ 第三条的**代价**要认下来：本日会是 Day 12 之后第一次「改动已验收的下单链路」，
所以验收里 M1 198/198 与 `BASELINE RESTORED: YES` 是**必跑项**，不是可选项。

---

## 四、数据层：`orders.discount_amount`

**已落库**（`backend/sql/11-order-discount.sql`，幂等，可重复执行）。实测输出：

```
column_name     | data_type | precision | scale | is_nullable | column_default
discount_amount | numeric   |        12 |     2 | NO          | 0

total_rows | zero_rows | nonzero_rows        inconsistent
         8 |         8 |            0                   0
```

★ 「8 条历史订单全部为 0」不是「应该如此」，而是**查出来的**：
存量行的 `pay_amount` 本就等于 `total_amount`（Day 12 的 `// V1.0 无优惠`），
所以 `discount = 0` 与之自洽，**不需要任何回填 UPDATE**。

★★ **本日之后要一直成立的恒等式**（验收直接复用它，比另写断言更省事，因为它管的是**整张表**）：

```sql
pay_amount = total_amount - discount_amount        -- 全表 0 行不满足
```

DDL 的 3.4 段还留了一个**零痕迹功能验证**（`BEGIN ... ROLLBACK`）：
把某行改成 `12.34` 再读回来 —— 读出的 `still_consistent = f`，
正是「上面那条全表断言**有意义**」的反向证明（只改一列必然破坏恒等式）。
★ 这个手法是 Day 20 验唯一约束时那条教训的复用：**光验「存在」不能证明「在拦」。**

---

## 五、接口：三个新方法，排布就是调用顺序

```
（C 端）POST /api/orders  { addressId, userCouponId? }
        │
        ▼
OrderServiceImpl.createFromCart(userId, dto)                    @Transactional
  ① 校验收货地址归属（IDOR）
  ② 读购物车已勾选项
  ③ 逐项失效判定
  ④ 算总额                    totalAmount = Σ(price × quantity)
  ④.5 ★ 算抵扣（只读）        couponService.calcDiscount(userId, userCouponId, totalAmount)
                              └─ 校验：归属 / 状态 / 已过期 / 尚未开始 / 券下架 / 门槛
                              └─ 算钱：FIXED → 面额；DISCOUNT → total × (1 − rate)
                              └─ 收口：封顶 totalAmount + setScale(2, HALF_UP)
         payAmount = totalAmount − deductionAmount
  ⑤ 扣库存（按 skuId 升序，条件 UPDATE）
  ⑥ 插订单 + 插明细           pay_amount = payAmount，discount_amount = deductionAmount
  ⑥.5 ★ 核销（写）            couponService.useCoupon(userId, userCouponId, order.getId())
                              └─ 必须在 insert 之后 —— 要写的是【落库后的真实 order_id】
  ⑦ 清掉已勾选的购物车项
        │
        ▼
（取消时）OrderCancelExecutor.cancelOne(orderId)                 @Transactional
  ① CAS 改订单状态 PENDING_PAYMENT → CANCELLED（0 行 = 已被别人改过，返回 false）
  ② 逐 SKU releaseLocked（按 skuId 升序，与扣减同序）
  ③ ★ couponService.releaseByOrder(orderId)   ← 退券，与 ② 同一事务
```

★★ **为什么是 `calcDiscount` + `useCoupon` 两步，而不是合成一个 `useCoupon(userId, userCouponId, totalAmount)`**：

```
① 算钱   发生在【插订单之前】—— 因为 pay_amount / discount_amount 是订单的字段
② 记下用在哪  发生在【插订单之后】—— 因为要写的是真实 order_id，插之前它还不存在
```

顺序上天然分开，硬合成一步就只能传一个「待回填」的占位 id，那是自找的麻烦。
★ 两次调用之间的时间缝**不是** TOCTOU：它们都在同一个事务里，
而真正决定成败的是 `markUsed` 的 CAS（`calcDiscount` 只是「把错误消息说人话」的慢路径，
与 `createFromCart` ③ 那句「库存不足」提前提示**同一个角色** —— 快路径负责对，慢路径负责好懂）。

★ `userId` **不来自请求参数**：它由 `OrderController` 从 token 的 principal 取出、
在 `createFromCart` 里逐层透传进来。C 端的「查谁的」只能由登录态决定（Day 11 起的规矩）。

---

## 六、今天留给你的 6 处

| # | 位置 | 内容 | 难度 |
|---|---|---|---|
| 1 | `UserCouponMapper.xml#selectForUse` | 两表 JOIN + **两个 `status` 分别起别名** + 现算 `expired` | ⭐⭐ |
| 2 | `UserCouponMapper.xml#markUsed` | CAS：三列同时改 + 两条守卫（归属、状态） | ⭐⭐ |
| 3 | `UserCouponMapper.xml#releaseByOrder` | **逆向** CAS：三样都要还原（含 `order_id`/`used_at` 清空） | ⭐⭐⭐ |
| 4 | `CouponServiceImpl#calcDiscount` | 五条判据 + 两条公式 + 封顶 + 定小数位 | ⭐⭐⭐ |
| 5 | `CouponServiceImpl#useCoupon` | 一行 CAS + **必须抛异常**（否则订单不回滚） | ⭐ |
| 6 | `CouponServiceImpl#releaseByOrder` | 一行，但**0 行不许当失败** | ⭐ |

★ 每处的「要什么」都写在对应方法/statement 的注释里，**连坑一起写了**，不用回去翻本文档。
★ 填充口诀照旧：**整段替换那行 `TODO` 与紧跟的 `throw`，只删你正在填的那一个**。
（本类现在有 3 个长得一样的 `throw`，删错就编译不过 —— 这是 Day 20 立下的规矩。）

---

## 七、还要你接的 2 根线（order 侧，我没动）

★ 这两处**我刻意没动**，因为它们是本日「状态机正向 + 逆向」的真正练习；
但**必须由你写**，写错任何一处 M1 当场红：

**1. `OrderServiceImpl.java` —— 注入 + 两段接线**

| 位置 | 要做的 |
|---|---|
| `:61-69` 构造器 | 加 `CouponService couponService` 字段与形参（与 `inventoryService` 同样式） |
| `:123-127` 之后 | 声明 `BigDecimal discountAmount = BigDecimal.ZERO;` / `CouponUseVO use = null;`；**仅当 `dto.getUserCouponId() != null`** 才调 `calcDiscount`，并把结果记下来 |
| `:148` | `order.setPayAmount(payAmount)`（= total − deduction，不是 total）＋ `order.setDiscountAmount(discountAmount)` |
| `:155` 之后、`:157` 循环之前 | **仅当前面真的用了券**才调 `useCoupon(userId, dto.getUserCouponId(), order.getId())` |

★ **三个「别」**：
- 别把 `calcDiscount` 提到 `④` 之前 —— 它要 `totalAmount` 当入参。
- 别在 ④.5 就把券改成 `USED` —— 那时候还没有 `order_id`，而 `NOT NULL`？不，它是可空的，
  但先置 `USED` 再回填 `order_id` 就变成了**两次写**，中间失败会留下「已核销但没订单」的券。
- 别把 ⑥.5 挪到 ⑦ 之后还「顺手」检查一下 —— **⑦ 之后方法就结束了**，
  而 `@Transactional` 只对**抛出去的异常**回滚。

**2. `OrderCancelExecutor.java` —— 加一行退券**

| 位置 | 要做的 |
|---|---|
| `:24-28` 构造器 | 加 `CouponService` |
| `:47-50` 的 `for` 循环之后 | `couponService.releaseByOrder(orderId);` |

★ **不要**把它的返回值当失败条件 —— 0 行 = 这一单没用券，是常态。
★ **不要**放在 `cancelOrder` 返回 0（`return false`）之前：那条路径上订单根本没被取消，
券也不该退。

**★★ M1 兼容性的判据**（写完立刻能自查）：不传 `userCouponId` 时，
`discountAmount` 恒为 `BigDecimal.ZERO`、`payAmount == totalAmount`、
且**一次 `couponService` 调用都不发生** —— 老行为逐字节不变。

---

## 八、验收计划（`day21-coupon-use-verify.py`，等你填完 6 处我再照 Day 20 的规格落地）

仍是**一条 Python 单脚本**（模板 `day17-f-*`）：一次执行内 hold token/id、
`subprocess` 调 `docker exec psql` 对账（**不信接口自报**）、可重跑、高水位线清理。

**A 组 · 不用券原路（兼容，本日最高优先级）**
1. 不带 `userCouponId` 下单 → `code=0`，DB 里 `discount_amount = 0` 且 `pay == total`；
2. 同一单的金额与 Day 12 口径一致（`total == Σ price×qty`，逐行对账）；
3. `user_coupons` 无任何行被改动（`count(status='USED')` 与调用前相等）——★ 证明「没碰券」。

**B 组 · 满减券（FIXED）**
4. 造一张 `FIXED` 券（面额 20、门槛 100、`total_count` 足够）+ 造一张订单总额 ≥ 100 的购物车；
5. 下单 → `code=0`；DB：`orders.discount_amount = 20.00`、`pay_amount = total − 20`、
   **恒等式成立**；
6. `user_coupons` 那一行：`status='USED'` **且** `order_id` = 新订单 id **且** `used_at` 非空
   （★ 三样都要断，只断 status 不算验过）；
7. 同一张券**再用一次** → `code=400`（已被 `markUsed` 的 CAS 挡下）；
8. ★ **恒等式全表断言**：`pay_amount <> total_amount - discount_amount` 的行数为 **0**。

**C 组 · 折扣券（DISCOUNT）与边界**
9. `rate=0.80` + 总额 100 → 抵扣 **20.00**（不是 80）；
10. 封顶：面额 300、总额 200 → 抵扣 **200.00**、`pay_amount = 0`（不为负）；
11. 小数位：总额 33.33、`rate=0.90` → 抵扣 `3.333` → **3.33**（`HALF_UP`）；
12. ★ **`rate=80` 的脏券** → **400**「折扣率取值必须是 0 到 1 之间」（★ 不许算出负数）。
    ⚠️ 2026-09-24 起（决策 A）**走接口已造不出这种券** —— `CouponCreateDTO` 的
    `@DecimalMax` 收到 `1.00`，day20 的 I3b 断的就是这个 400。所以本条的靶子
    **必须用 SQL 直接写库造**（`INSERT INTO coupons …`），这正是两道防线的分工实证：
    **DTO 挡「配置期的输入错误」，`calcDiscount` 挡「绕过接口写进来的历史/脏数据」**；
13. 门槛：总额 99.99、`min_amount=100` → **400**（差一分也不能用）。

**D 组 · 归属与状态（IDOR + 反向对照）**
14. 拿**别人**的 `userCouponId` 下单（B 的 token 用 A 的券）→ **404**，
    且 ★ 去 DB 核「那张券**原封不动**」（`status`/`order_id`/`used_at` 一个都没变）——
    **光看状态码证明不了任何事**；
14b. ★★ 拿一个**根本不存在**的 `userCouponId`（如 999999）下单 → 也必须是 **404**，
     且响应体与 14 的响应**逐字节相同** —— 这才是「伪装 404」的判据：
     只要两者在码 / 文案 / 长度上有一丝差异，IDOR 防线就有裂缝（同 Day 20 的 IDOR 断言法）。
     ★ **2026-09-24 订正**：本条原写「400/404」含糊两可，现定死 **404**。
     依据 = 项目 IDOR 成文口径 `AddressServiceImpl#requireOwn:160-166`
     （`addr == null || !addr.getUserId().equals(userId)` 合并成**同一个码 + 同一句文案**）。
     ⇒ `calcDiscount` 里 `src == null` 必须用 `ResultCode.NOT_FOUND`，**不是** `VALIDATE_FAILED`；
15. 已使用的券再用 → 400；已过期的券 → 400；**尚未开始的券** → 400；下架的券 → 400；
    ★ 「尚未开始」必须**造一张 `start_time` 在未来的券**才验得到 ——
      库里现有券的 `start_time` 全在过去，不造数据这条断言**恒真、等于没验**（样本量陷阱）。
16. 不存在的 `userCouponId`（如 `99999999`）→ 与 14 的响应**逐字节相同**
    （不能区分「不存在」与「不是你的」）。

**E 组 · 退券（逆向，本日含金量最高的一组）**
17. 用券下单 → 取消该订单 → DB：那一行 `status='UNUSED'`
    **且 `order_id IS NULL` 且 `used_at IS NULL`**（★ 三样，缺一不算）；
18. 退回来的券**能再次使用**（再下一单 → 成功，`order_id` 指向**新**订单）；
19. 没用券的订单取消 → 退券 0 行，**取消本身照样成功**（`code=0`）——★ 反向对照；
20. 同一张订单重复取消 → 第二次不再退（券不会被退两次）；
21. ★ **失败即回滚的证明**：让 `useCoupon` 一定失败（用一张已被核销的券绕过前置校验，
    或临时改数据制造缝隙），断言**订单没建、库存没扣、金额没变** ——
    这一步才证明「同事务」。

**F 组 · 回归（必跑）**
22. `day17-m1-regression.py` → **198 / 198** + `BASELINE RESTORED: YES`；
23. `day20-coupon-verify.py` → **80 / 80**（阶段一的 6 个端点一个都没被带坏）；
24. `day19-search-verify.py` → **58 / 58**；`day20-l5-brand-verify.py` → **24 / 24**。

★ 满额断言一律**写死常量**（如 `EXPECTED = 82`），并核对 `PASS + FAIL == EXPECTED`，
**不许有断言被静默跳过**（Day 20 的规矩）。

---

**★ 已完成的连带回归（2026-09-24，决策 A 落地时实测 —— 不是计划，是结果）**

| 项 | 结果 |
|---|---|
| `mvn -o install -DskipTests` | **12 / 12 BUILD SUCCESS** |
| `day20-coupon-verify.py` | **82 / 82** `VERDICT: OK 全绿`（80 → 82：新增 I3b / I3c） |
| `day17-m1-regression.py` | **198 / 198** + `BASELINE RESTORED: YES` + `M1 REGRESSION: OK` |

★ 两条新断言实测都 PASS：**I3b**（`rate=1.01` → 400，证明上限**真的**收到了 1.00，
旧值 `99.99` 会放它过去）与 **I3c**（`rate=1.00` → 200，证明上界是**闭区间**
—— 写成开区间会把「一分不减」的合法券误判成参数错）。

★ 校准 `EXPECTED` 常量时，脚本自带的护栏**当场报了**
「断言总数与 EXPECTED 不符 —— 有断言被静默跳过，或 EXPECTED 需要校准！」——
这正是它该有的表现：**改了断言却不同步常量，第一次跑就被抓住**，
而不是安静地少验两条。这条护栏（Day 20 立的规矩）本次第一次真正派上用场。

---

## 九、坑（本日专属，逐条都有翻车现场）

1. ★★★ **M1 是主风险，不是新功能**。`userCouponId == null` 必须完全走原路。
   M1 的 3 个 E2E 取消的订单**全都**没用券 —— 把退券的 0 行写成抛异常，M1 当场红，
   而且症状是「取消订单莫名 500」，跟券八竿子打不着。
2. ★★★ **`releaseByOrder` 要「擦干净」，不是「改状态」**。三样都要还原：
   `status='UNUSED'` + `order_id=NULL` + `used_at=NULL`。
   ★ 为什么 `MP` 的 `updateById` 做不到：它**跳过 null 字段** —— 「清空」和「不改」在它眼里一样。
   这就是这条必须手写 XML 的根本原因。
3. ★★ **两个 `status` 必须分别起别名**。`uc.status`（我用了没）与 `c.status`（券种下架没）
   若都写成 `AS status`，PG 会让后者盖掉前者，而且**不报错** ——
   于是「已核销的券」被判成可用，同一张券能用两次。这类错不会 500，只会让钱悄悄错掉。
4. ★★ **`used_at` 必须在 SQL 里手写 `CURRENT_TIMESTAMP`**：自定义 XML 的 UPDATE
   **不走** `MyMetaObjectHandler`（Day 13/16/20 都栽过）。而且 `used_at` 列**没有** DB 默认值，
   不写就是 null —— 留下「已核销但不知何时核销」的行，属于安静的错。
5. ★★ **`discount_rate` 的取值约定必须钉死并校验**：本日定为**应付比例 (0,1]**，
   `0.80` = 8 折 → 抵扣 `total × 0.20`。若不校验，种子里一个 `80`（想表达 8 折）
   会算出 **负的抵扣额**，实付金额一路变负、错到支付接口才炸。
   ⇒ `calcDiscount` 必须显式挡 `rate <= 0 || rate > 1` → 400 + 人话。
6. ★ **`setScale(2, RoundingMode.HALF_UP)` 要显式写**。BigDecimal 默认是
   `HALF_EVEN`（银行家舍入），它在 `x.xx5` 上给出的结果与直觉不同，
   而验收脚本是按直觉写的 —— 于是脚本和代码会各说各话。
7. ★ **抵扣额要封顶到 `totalAmount`**，否则「满 200 减 300」这类配错的券会让实付为负。
   V1.0 选**封顶**而不是报错：让这一单少付到 0 元比让用户下单失败更合理，
   而且封顶是幂等的、不会因重试而变化。（理由要写进代码注释。）
8. ★ **必须先落 DDL 再起应用**：`Order` 实体已加 `discountAmount`，
   MP 生成的列清单会带上 `discount_amount` → 列不存在时**直接报错**（不是静默忽略）。
   本日已落库并复核。
9. ★ **别在 `calcDiscount` 里写库**。它是「慢路径」（负责把消息说人话），
   唯一写操作在 `useCoupon` 的 CAS 里。在慢路径里写库 = 把 TOCTOU 请回来。
10. ★ **`calcDiscount` 里允许用查询快照，但 `markUsed` 的守卫一条都不能省**。
    尤其**归属条件**：不能因为前面查过一次就省掉它 —— 查与改之间有时间缝，
    而且「C 端防线写在 SQL 里」是本项目的一贯口径，不因调用链长短而变。
11. ★★ **补判据前先问「另一端有没有」**（2026-09-24 补进设计）。
    本日发现 `calcDiscount` 漏判「尚未开始」时，第一反应是「加一条新判据」；
    但查另一端后发现 **领券侧的 CAS 早就守了窗口两端**
    （`CouponMapper.xml#increaseReceivedCount` 的 `start_time <=` / `end_time >=`）。
    ⇒ 定性从「加功能」变成「**补口径漂移**」，改法与理由都不一样
      （要跟领券侧**同源**，而不是自己新立一套）—— 与 L4 的 `categoryId` 同一族。
    ★★ 同时暴露的隐患：`startTime` 被 `selectForUse` 取回来却无人消费，
      是一根**死列**（Day 20 的「死查询」同一类）。
    ⇒ 一般化：**凡「取回来的字段没有任何消费者」，要么补判据、要么删字段**，
      不许以「储备列」的名义留在 VO 里。
    ★ 附带认下的取舍：`markUsed` 的 CAS **不**重判窗口 —— 要判就得 JOIN `coupons`，
      把单表 CAS 变成跨表 CAS；漏的只是「券在事务内那几毫秒里过期」，
      **不可构造、不可断言**，V1.0 认下。若收紧，改 `markUsed` 的 WHERE 是唯一入口。

---

## 十、收尾铁律（每条做完都要做）

1. `day2N-xml-check.py`（XML 良构 + Java↔XML 双向对齐 + 空实现 + 骨架占位）；
2. 起应用跑本条的验收断言（**不信接口自报，逐条 `psql` 对账**）；
3. `day17-m1-regression.py` → **198 / 198** + `BASELINE RESTORED: YES`；
4. 另跑 `day20-coupon-verify.py` 80/80（阶段一不能被带坏）；
5. 主动提交 + 推送（`git status --short` → **先 `git reset`** → 按主题分批 commit → `push.py` + 三重验证）。
   ★ 未验收不提交；push 失败**不许默默算了**。

---

## 十一、与 Day 22 的分界（预告）

| | 本日 | 后续 |
|---|---|---|
| 券的完整生命周期 | ✅ 领取 → 核销 → 退回（**闭环**） | — |
| 尚未处理的 | 「下单未付款超时」退券已覆盖（走同一 `cancelOne`） | **支付后申请退款**要不要退券？—— 那是金额守恒的另一半，含金量更高 |
| 价格链 | 券只作用于**订单总额** | 单品级优惠 / 券与活动叠加的**优先级** |
| 状态机 | 两态双向（UNUSED ⇄ USED） | 若引入 `LOCKED`（支付成功才核销）就是**扩张状态机**，届时所有相关断言都要同步改 |
