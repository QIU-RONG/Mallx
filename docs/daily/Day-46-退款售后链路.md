# Day 46 · 退款 / 售后链路（仅退款 + 退货退款 + 负向支付流水）

> 一句话：**业务闭环上最后一个洞补上了。** 此前系统只能顺着走
> （下单 → 支付 → 发货 → 收货 → 评价），付出去的钱没有任何路径能要回来。

---

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 新增模块 | `mall-aftersale`（依赖图叶子：依赖 order/payment/inventory/marketing，无人依赖它） |
| 新增表 | `refunds`（全项目**第 25 张**）+ `orders.refunded_at` 补丁 |
| 新增权限 | 5 条（id 42–46），给 role 1 与 **role 3**，**故意不给 role 2** |
| 端到端验收 | `day46-refund-verify.py` **82 / 82** |
| 单元测试 | `RefundServiceImplTest` **10 条**（补 `mall-aftersale/pom.xml` 的 test 依赖） |
| 控制组 | 端到端 1 次（删索引 → 红）+ 单测 1 次（去 catch → 红 2 条，零误伤） |
| 回归 | M1 **434 / 434**；day19–24、day38–40、day44 全绿 |

---

## 1. 类型 ↔ 订单状态：本模块最硬的一条业务规则

```
REFUND_ONLY    仅退款    货【没】发出去 ⇒ 没有实物要寄回 ⇒ 订单必须是 PAID
RETURN_REFUND  退货退款  货【已】发出去 ⇒ 必须真的退回来  ⇒ 订单必须是 SHIPPED / COMPLETED
```

★ 为什么必须按订单状态卡死，不能让用户自己选：

- 「没收到货却选退货退款」⇒ 买家拿不到物流单号可填 ⇒ 卡在 `APPROVED` 变成僵尸单；
- 「货已发出却选仅退款」⇒ **钱退了、货还在买家手里** = 白送，而且账面看不出来
  （库存 `sold` 那格还挂着这批货）。

⚠️ 这条是**跨对象的关系校验**（要读订单状态才能判），`@Valid` 表达不了，
只能写在 `RefundServiceImpl#apply`（与 `CouponServiceImpl#createCoupon` 两条关系校验同源）。

状态机（两条路径共用一套常量，中间两段只有「有实物要寄回」时才会发生）：

```
APPLIED → APPROVED ────────────────────→ SUCCESS      （仅退款）
                  ↘ REJECTED
APPLIED → APPROVED → RETURNING → REFUNDING → SUCCESS  （退货退款）
        ↘ CANCELLED      ↘ REJECTED
```

---

## 2. 「执行退款」是全项目唯一动钱的动作 —— 五个写点

| # | 表 | 写什么 | 为什么 |
|---|---|---|---|
| 1 | `refunds` | → `SUCCESS` + `refunded_at` | ★ **必须第一步**：CAS 抢资格，抢不到就没资格动后面的 |
| 2 | `orders` | → `REFUNDED`（CAS） | `REFUNDED` 不在它的起点集合里 ⇒ 退不了第二次 |
| 3 | `inventories` | `sold → available` | **第 5 个库存写点**，记 `REFUND_RETURN` 流水 |
| 4 | `user_coupons` | 退这一单用掉的券 | 0 行 = 没用券，正常 |
| 5 | `payments` | 一笔**负数**流水 | 对账退化成 `SUM(amount) == 0` |

★★ 为什么回补走 `REFUND_RETURN` 而不是 `CANCEL_RELEASE`：
分岔点是**付没付过钱** —— 付过钱 ⇒ 货在 `sold` 格；没付过 ⇒ 货在 `locked` 格。
用错类型，流水账就会说「这批货是取消释放的」，而它明明是被退回来的。

---

## 3. 并发不变式只能由数据库守（`uk_refunds_active_order`）

```sql
CREATE UNIQUE INDEX uk_refunds_active_order ON refunds (order_id)
 WHERE status IN ('APPLIED','APPROVED','RETURNING','REFUNDING');
```

`apply` 里那条 `countActiveByOrder > 0` 的 SELECT **只是给人话报错用的**，
它挡不住并发（TOCTOU：连点两次，两个请求都查到「没有进行中的单」，然后各插一条）。

## 4. ★★ 本日最值钱的三件事

### ① 「控制组没红」本身就是发现

第一次做控制组时，我删掉 `uk_refunds_active_order` 后重跑 —— **82 条照样全绿**。
一开始以为是索引没删掉，查了才明白：

> 单线程下重复申请是被 `countActiveByOrder` 那条 SELECT 拦的，
> 索引压根没被触发 ⇒ 删它对可观测行为零影响。

于是补了两层：

- **端到端 [G] 段**（确定性）：直接对着数据库插 —— 第一张 `APPLIED` 可插、
  第二张被 `uk_refunds_active_order` 挡住（报错点名该索引）、`CANCELLED` 照样能插
  （证明是**部分**索引）。
- **单测**（确定性）：让 `insert` 直接抛 `DataIntegrityViolationException`，
  断言它被翻译成 400。

★ 方法论沉淀：**概率性路径不能当唯一证据**。并发那节只能证明「没炸」，
证明不了「是谁拦的」—— 必须补一条确定性的。

### ② 一个真 bug：唯一冲突会炸成 500

`apply` 原先没有 catch。`GlobalExceptionHandler` 尾部有 `Exception.class` 兜底 ⇒
真发生并发时，第二个请求拿到的是 **HTTP 200 + code 500「系统异常」**，
而真实语义是「你已经申请过了」。

修法（7 行）：

```java
try {
    refundMapper.insert(refund);
} catch (DataIntegrityViolationException e) {
    throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
            "该订单已有进行中的售后单，不能重复申请");
}
```

控制组：把 `throw new BusinessException(...)` 换回 `throw e` ⇒ 恰好红 2 条、零误伤。

### ③ cleanup 删订单会永久污染库存基线（实测事故）

首跑时订单 C 走到 `REJECTED`（钱没退、货没回补），cleanup 却直接
`DELETE FROM orders` ⇒ **那一格 `sold` 永远留在库里**（sku4 `sold=2` 但只有 1 张订单）。

后果：day15 / day16 的守恒式 `sold == SUM(PAID+SHIPPED+COMPLETED 的下单量)` **各红 2 条**。
第一次看到红灯时我误判成「订单 C 没退款所以库存回不去」，
只补了 C4（被拒后重新申请并退成）—— **症状治了，库里的 +1 没治**。

正确的两层修复：

1. 脚本 cleanup **自愈**：删单前扫描仍处于 `PAID/SHIPPED/COMPLETED` 的订单，
   先把货退回（`sold -= qty; available += qty`）再删 —— abort 时也挡得住；
2. 手工修库：`sku4 sold 2 → 1`、`available 148 → 149`（守恒式 6/6 重新对上）。

★★ 教训：**`DELETE FROM orders` 不是「清理」，它是「绕过所有业务不变量」**。
任何写侧脚本的 cleanup 都必须先问：**我删掉的这些行，有没有还没被逆向的副作用？**

---

## 5. 验收脚本设计要点（`day46-refund-verify.py`，82 条）

| 节 | 内容 |
|---|---|
| A | 仅退款全链路 + 选错类型 400 + 重复申请 400 + IDOR 404（与「不存在」不可区分）+ 五个写点 + 负向流水 + 重复退款 400 |
| B | 退货退款：`APPROVED` 时执行退款 400（货还没寄回）→ 寄出 `RETURNING` → 仍 400 → 确认收货 `REFUNDING` → 才放行 |
| C | 两条**不动钱**的终态：撤销 `CANCELLED` / 拒绝 `REJECTED`（拒绝原因要落库）+ 终态后可重新申请 |
| D | 并发：8 线程抢同一张单（只有 1 张成功、其余必须是 400 不是 500） |
| G | SQL 层直接验部分唯一索引（确定性证据） |
| 权限矩阵 | C 端 token → 403；op_order(role3) → 200；**op_product(role2) → 403**（反向对照） |
| E | cleanup + 库存逐格回到基线 + 三张表无残留 |

---

## 6. 文件清单

| 文件 | 说明 |
|---|---|
| `backend/sql/17-refunds.sql` | `refunds` 表 + `orders.refunded_at` + 部分唯一索引 |
| `backend/sql/18-refund-permissions.sql` | 5 条权限（42–46）+ 授权（role 1 / 3，不给 2） |
| `backend/mallx/mall-aftersale/**` | 新模块：entity / mapper / xml / service / controller（C 端 + 管理端） |
| `…/mall-inventory/…/InventoryLogType.java` | 第 5 个写点 `REFUND_RETURN` |
| `…/mall-inventory/…/InventoryServiceImpl.java` | `returnToStock(sku, qty, orderId)` |
| `…/mall-order/…/OrderStatus.java` | 新增 `REFUNDING` / `REFUNDED`；`OrderMapper#markRefunded` |
| `…/mall-payment/…/PaymentServiceImpl.java` | `writeRefundFlow`（负数流水） |
| `backend/loadtest/day46-refund-verify.py` | 82 条端到端验收 |
| `…/mall-aftersale/src/test/…/RefundServiceImplTest.java` | 10 条单测 |
| `.github/workflows/ci.yml` | 新增 Refund / aftersale 步骤 |
