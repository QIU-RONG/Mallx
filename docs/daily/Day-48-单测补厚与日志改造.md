# Day 48 · 单测补厚（第一批）+ 日志改造

> 两条线：① 单元测试 51 → 72 条（库存 21 条 + 购物车骨架 14 条）；
> ② **日志改造** —— 项目此前「日志几乎是空的」，这轮补上基础设施与关键业务路径。

---

## 一、为什么先修日志（而不是先加功能）

扫描结果（Grep 实测，不是印象）：

| 指标 | 结果 |
|---|---|
| `System.out.print` / `printStackTrace` | **0 处** |
| `@Transactional` 误用在 private 方法上 | **0 处** |
| 残留 TODO / 骨架 | **0 处** |
| **Logger** | **只有 5 个类在用** |

⇒ 代码本身很干净，**缺的是「出问题时能查到什么」**。

改造前的日志长这样（Spring Boot 默认 pattern）：

```
2026-10-14 15:40:01.123  WARN [nio-8080-exec-3] OrderServiceImpl : 业务异常：code=400,message=库存不足
```

**不知道是谁的哪一次请求。** 于是「用户投诉下单失败」的排查姿势是拿用户说的「大概几点几分」去数时间戳 ——
并发一高，同一毫秒十几条日志，根本对不上；同一次请求打的好几行也没有共同标识，
**无法证明它们属于同一次调用**。

---

## 二、方案：MDC + 统一 pattern（一次投入，全局受益）

### 2.1 `TraceIdFilter`（新增）

`OncePerRequestFilter` + `MDC`，把 `traceId` 和 `uri` 放进线程级上下文：

- **traceId 优先取请求头 `X-Trace-Id`**：给链路追踪留接入口（现在没有调用方，但口子先留着）
- **回写响应头**：用户报障时报这个 id，比报「大概几点」精确一万倍
- **`@Order(HIGHEST_PRECEDENCE)`**：Spring Security 的 FilterChain 顺序是 `-100`，
  默认注册的 `@Component` Filter 会排在它**后面**，那样 Security 层拒绝（401/403）的日志就带不上 traceId

### 2.2 `logback-spring.xml`（新增）

pattern 加 `%X{traceId}` 和 `%X{uri}`。改造后：

```
2026-10-14 16:00:16.977  WARN [io-8080-exec-10] [0cec49e5] [POST /api/admin/refunds/999999/approve]
    RefundServiceImpl : 售后审核被拒（通过）refundId=999999 remark=null
         ↑ traceId            ↑ method + uri
```

三要素齐了：**哪次请求 + 哪个业务 + 为什么**。

### 2.3 ★ `clearMdc()` 是必须的，不是洁癖

Tomcat 的 worker 线程是**池化复用**的。只 put 不 remove，下一个请求复用同一线程时
MDC 里残留的还是**上一个请求的 traceId** —— 两条毫不相干的日志被打上同一个标识，
**比没有标识更糟**（它会误导你往错的方向查）。

同理：**异步线程不继承 MDC**（MQ 消费者、定时任务拿不到 traceId）。
实测印证：定时任务的日志就是 `[scheduling-1] [] []`。这是预期行为 ——
异步场景本来就没有「一次请求」，靠业务日志里显式写的 orderId / refundNo 定位。

---

## 三、日志分级规范（本轮定下的判据）

| 级别 | 判据 | 例子 |
|---|---|---|
| **ERROR** | 账目不一致 / 数据被旁路改过 | `moveLockedToSold` 0 行、订单明细缺失 |
| **WARN** | 业务被拒绝（用户可见的失败） | 库存不足、地址不存在、审核被拒、CAS 抢不到资格 |
| **INFO** | 低频的状态跃迁 | 下单成功、支付成功、退款执行成功、审核通过/拒绝 |
| **DEBUG** | 高频成功路径 | ——（本项目刻意不用） |

**两条关键取舍：**

1. **库存扣减成功【刻意不记 INFO】** —— 每次下单都会调，记了会把日志淹掉，
   而且成功是常态、没有排障价值。想看库存变化，`inventory_logs` 本身就是账本。
2. **一处「想记而没记」也写明了理由** —— `OrderServiceImpl` 的库存不足提示是「提前提示」，
   并发下真正失败在 `InventoryServiceImpl` 的 UPDATE 之后，两处上下文**故意互补**：
   订单侧读得到 `availableStock`，库存侧读得到「CAS 影响 0 行」，
   但在库存侧再查一次 availableStock 会多一次往返 —— 写在注释里，免得下一个人「补全」它。

---

## 四、改了哪些文件

| 文件 | 加什么 |
|---|---|
| `mall-server/.../filter/TraceIdFilter.java` | **新增**：MDC 上下文 |
| `mall-server/src/main/resources/logback-spring.xml` | **新增**：pattern + 分级 |
| `OrderServiceImpl` | 地址不存在 / 库存不足 / 下单成功 / `markPaid` 被拒 |
| `PaymentServiceImpl` | 订单明细缺失（ERROR）/ CAS 抢不到资格 / 支付成功 |
| `InventoryServiceImpl` | 扣减失败（WARN）/ 两处账目不一致（ERROR） |
| `RefundServiceImpl` | 重复申请被索引兜住 / 申请成功 / 审核通过·拒绝 / 退款执行成功 |
| `PaymentServiceImpl`、`RefundServiceImpl`、`InventoryServiceImpl` | 补 `@Slf4j`（原本没有 logger） |

---

## 五、验收：不是「日志加了」，是「日志能回答为什么」

起应用后实测（同一轮内完成）：

| 场景 | 响应 | 日志 |
|---|---|---|
| 管理端查不存在的订单 | HTTP 200 + `code=404` | `[13030db9] [GET /api/admin/orders/999999] ... 业务异常：code=404,message=订单不存在` |
| 审核不存在的售后单 | 业务 400 | `[0cec49e5] [POST /api/admin/refunds/999999/approve] ... 售后审核被拒（通过）refundId=999999` |
| 匿名打管理端点 | HTTP **401** | 同样带 traceId ⇒ 证明 Filter 排在 Security 之前 |

★ **traceId 与响应头 `X-Trace-Id` 逐字符一致**（`fc1d296c`）——
用户报障时报这个 id，`grep` 一下就能拿到该次请求的全部日志。

`mvn -o test`：**72 条全绿**（Jwt 9 + Inventory 21 + Coupon 32 + Refund 10，购物车 14 条骨架 skipped）。

---

## 六、本轮翻车一次（记下来，因为它会复发）

**把 `com.mallx` 设成 `DEBUG`，当天就翻车。**

我原本的判断是「业务代码只有显式写的日志，DEBUG 不会刷屏」——
**错了**：MyBatis-Plus 的 SQL 日志用的 logger 名就是 mapper 的全类名
（`com.mallx.order.mapper.OrderMapper`），**也在 `com.mallx` 这棵树下**
⇒ 设成 DEBUG 等于把每条 SQL 连参数一起打出来，一次下单刷几十行，真正的业务日志被淹掉。

⇒ 已改为 `INFO`，并把这条写进 XML 注释。
★ 一般化：**「设个 DEBUG 看看」在带 ORM 的项目里从来不是免费的** ——
ORM 的日志挂在业务包的命名空间下，调级别时会一起被带出来。

---

## 七、下一步

🔴 里还剩两件：

1. **真实环境部署一次**（需要服务器 + 域名，卡在资源决策）
2. **单测继续补**：购物车骨架等用户填；之后是订单 + 支付（依赖最多、最容易被「顺手改一下」改坏）
