# Day 45 · 单元测试从零起步（189 源文件 / 0 测试 → 41 条）

> 体检结论：`src/test` 下 **0 个 Java 测试类**，CI 一直跑 `mvn -DskipTests`。
> 81 个 Python 脚本是**端到端**的 —— 能证明「链路通」，但都要起 DB + Redis + MQ + 应用，
> 且互相依赖夹具状态，**证明不了「某个方法单独是对的」**。
> 这就是 B17 那种「改两版才修好」的根因：没有能快速定位的最小反馈环。

## 一 交付

| 层 | 类 | 条数 | 依赖 | 耗时 |
|---|---|---|---|---|
| L1 纯逻辑 | `mall-common` · `JwtUtilTest` | 9 | 无 Spring / 无 DB / 无 mock | 1.3 s |
| L2 Mockito | `mall-marketing` · `CouponServiceImplTest` | 32 | 只 mock 一个 `UserCouponMapper` | 5.1 s |
| **合计** | | **41** | CI 里跑在起 postgres **之前** | ~6 s |

CI 已去掉 `-DskipTests`（Day 44 那次提交就改了），并在注释里钉了约束：
**能进 `src/test` 的必须不依赖 DB / Redis / MQ**。

## 二 分层原则（写之前先想清楚）

```
L1  纯逻辑     不启 Spring、不连库、不 mock  →  JwtUtil / ResultCode / 金额工具
L2  Service 层  mock 掉 Mapper              →  calcDiscount / createCoupon
L3  （暂不做）  @SpringBootTest + 真库       →  留给端到端脚本，别塞进 mvn test
```

判据只有一条：**这个测试能不能在没有 postgres 的机器（= CI 的构建步骤）上跑**。
跑不了的，就该是 Python 端到端脚本，不是 JUnit。

## 三 覆盖的分支

### `calcDiscount`（Day 21 的算钱核心，25 条）

| 组 | 断言要点 |
|---|---|
| 取素材 | null → **404**（IDOR 伪装 404，不区分「不存在」与「不是你的」）；★ `userId` 原样透传给 `selectForUse` |
| 五条判据 | 已使用 / 已过期 / 尚未开始 / 已下架 / 未满门槛 → 400；**每条都配了反向对照组**（expired=false、startTime=null、minAmount=null、金额恰好等于门槛） |
| 两条公式 | FIXED = 券面面额；DISCOUNT `rate=0.80` → 100 元减 **20.00**（★ 应付比例，不是减免比例）；面额缺失 → 400 不是 NPE |
| rate 区间 | `80` / `0` / `null` → 400「折扣率取值必须是 0 到 1 之间」；`1.00` → 抵扣 0.00 **照常返回** |
| 类型非法 | 落到 else → 400 |
| 收口 | 满 200 减 300 → **封顶 200.00**；x.xx5 → **HALF_UP 13**（HALF_EVEN 会给 12）；0 元券 → 0.00 |
| 不变量 | ★ 素材 `src` 全程只读，抵扣额不写回券面 |

### `createCoupon`（两条「字段之间」的关系校验，7 条）

`endTime` 不晚于 `startTime`、FIXED 缺/多填金额字段、DISCOUNT 缺/多填金额字段、类型非法 → 400；
放行路径用 **spy + `doAnswer`** 模拟 MP `save` 回填自增主键，断言 `status=1` / `receivedCount=0` 是**显式写**的。

## 四 控制组（必做，做了两次）

★ 绿灯本身什么也不证明 —— 必须拿「已知写坏的实现」回跑，脚本**必须失败**。

| 变异 | 期望红的条数 | 实际 |
|---|---|---|
| `HALF_UP` → `HALF_EVEN` | 1（舍入） | ✅ 红 |
| 删掉「封顶」三行 | 1（满200减300） | ✅ 红（返回 300.00） |
| 删掉 rate 区间守卫 | 3（80 / 0 / null） | ✅ 红，其中 `rate=null` 直接 **NPE** |
| 删掉「FIXED 不能同时填 discountRate」 | 1 | ✅ 红 |

四次变异**零误伤**：没有一条无关用例跟着红。

## 五 本轮的坑

### ① 父 pom 的 `dependencyManagement` 只是版本声明

`spring-boot-starter-test` 必须在**每个被测模块各自再引一次**（`test` scope）。
只在父 pom 里写 → 模块 `mvn test` 时 `org.junit` **根本不在 classpath 上**，
表现是「测试类编译都不报、直接 0 条」（更坏：静默跳过）。

### ② ★★ 单测抓不到 `==` 与 `equals` 的区别

`CouponType.FIXED.equals(src.getType())` 写成 `src.getType() == CouponType.FIXED` 是经典 bug
（DB 读出的 String 与常量引用不同）。
**但在单测里两者都成立** —— 因为测试素材是用同一个字符串字面量常量构造的，字面量被 intern 了。
⇒ 这类 bug 只有**端到端**（值真的来自 JDBC 反序列化）才抓得到。
**推论：单测与端到端是互补的，不是替代关系。**

### ③ 写测试数据前先问「会不会被别的收口拦」

`nullMinAmountIsAccepted` 第一次挂了：1 元订单 + 满减 20 → 抵扣被**封顶**成 1.00，
而我在断言里写死 20.00。
★ 这是**脚本与设计打架**，而设计（封顶）是对的 ⇒ **改脚本，不改实现**。
（项目老规矩：断言对着【设计】写，不对着库的默认行为写。）

### ④ spy + `doAnswer` 模拟「save 之后回填自增主键」

`createCoupon` 的放行路径要调 `this.save()`（走 `baseMapper`，单测里是 null）。
做法：`spy(service)` + `doAnswer(inv -> { inv.<Coupon>getArgument(0).setId(99L); return true; })`。
★ 别用 `when(spy.save(any()))` —— 那会**真的先执行一次** `save`。

### ⑤ `@Nested` 分组 + 共享 helper

五条判据、两条公式、建券三条线各自一个 `@Nested`，共用 `src(Consumer)` / `dto(Consumer)` 素材工厂
与 `assertRejected` / `assertAccepted` 断言助手。
★ 别在每个用例里手抄一整套字段 —— 那样「新增一条判据」时要改十几个地方，而且极易漏改造成假绿。

## 六 还剩什么（#86 未收口的部分）

- 金额守恒（订单 `pay_amount = total_amount - discount_amount`）的计算处
- 库存 CAS 的判定分支
- `OrderStatus` / `UserCouponStatus` 状态机迁移的合法性
- 分页夹紧（`MAX_PAGE_SIZE`，现在是第 6 份拷贝）—— 抽之前先测

⇒ 优先级：先给**算钱**和**状态机**补，那是错起来最贵的两块。
