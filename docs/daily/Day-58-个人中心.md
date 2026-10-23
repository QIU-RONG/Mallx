# Day 58 · 个人中心（订单 / 售后 / 券 / 地址 / 资料）

> 需求原话：**「做一个个人中心，把订单售后优惠券等放进里面」**，
> 确认范围时选择把「收货地址管理」与「改昵称」一起做。

---

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 新页面 | 5 个：`Account`（壳）、`AccountHome`（概览）、`AccountAddresses`、`AccountProfile`；订单/售后/券复用现有页面 |
| 路由 | `/account` + 6 个子路由（overview / orders / refunds / coupons / addresses / profile） |
| 后端改动 | 1 处：C 端订单列表补上 `status` 过滤（同时修掉前端两个静默失效的参数） |
| 验证 | lint 0 · 15 单测 · build · `day56-local-e2e` **40/40** · 地址 CRUD / 昵称接口实测 200 |

---

## 1. 结构：一个壳 + 子路由，而不是复制三份页面

```
/account              Account.vue（左侧导航 + 问候 + 退出）
  /overview           AccountHome（四个数字 + 最近订单）
  /orders             OrderList（复用）
  /refunds            MyRefunds（复用）
  /coupons            Coupons（复用）
  /addresses          AccountAddresses（新）
  /profile            AccountProfile（新）
```

★ 复用的理由不是省事，而是**同一份数据只能有一个视图**：订单页改了状态标签，
个人中心里立刻一致；复制一份就要同步两处。

★ 复用带来的布局问题用**一处 CSS 中和**解决：三个旧页面自带 `max-width:1200` 与 20px 内边距，
放进个人中心会变成「页面里的页面」。`Account.vue` 里只中和 `.wrap` 的宽度/内边距与一级标题，
不动它们内部任何业务样式。

---

## 2. 顺手修掉两个「静默失效」

做概览的四个数字时发现：待付款 3、待收货 3 —— 但最近订单全是「已完成」。查下来是两处旧问题：

| 问题 | 真相 | 现象 |
|---|---|---|
| 前端传 `current` | 后端参数名是 `page` | 翻页永远停在第 1 页 |
| 前端传 `status` | 后端**根本没有这个参数** | 订单页的状态筛选点了没反应 |

两处都**不报错**：接口返回 200，只是返回了「没筛过的第 1 页」。
这类缺陷比 500 难发现得多 —— 页面看起来只是「数据少」，不会有人去查网络面板。

**修法（前后端各一半）**：

1. `OrderController#list` 加 `@RequestParam(required=false) String status`；
2. `OrderService#listMyOrders` 改成 4 参，SQL 侧用
   `.eq(safeStatus != null, Order::getStatus, safeStatus)`（空串归一成 null，与 `listAllOrders` 同口径）；
3. 前端 `orderList` 的参数名改回 `page`，调用方跟随；
4. 概览的四个数字直接用**分页接口的 total**（`size:1`），不在前端遍历 —— 订单多了会拖垮首屏。

★ 为什么非法状态值不抛 400：与 `listAllOrders` 保持一致 —— 「筛不到」和「状态写错」在用户侧
是同一种可接受结果，多一个分支只会多一处要维护的判定。

---

## 3. 各页要点

**概览**：按当前时间问候；四个数字（待付款 / 待收货 / 售后记录 / 我的优惠券）各是一张可点的卡；
最近 3 单直接给出状态与实付，点进订单详情。

**收货地址**：卡片式列表，默认地址有墨色描边 + 「默认」胶囊；
新增/编辑用同一张表单（省/市/区三列）；**默认地址互斥交给后端** `PUT /{id}/default`，
前端绝不遍历改 `isDefault`（两份真相，并发就是两个默认）。
删除确认用 `.then(() => true).catch(() => false)` —— 管理端 Day 54 修过的「取消=执行」不再重犯。

**资料设置**：用户名 / 手机号 / 邮箱 / 注册时间 / 账号状态只读，只有昵称可改；
保存成功后同步 `auth.setAuth`，顶栏问候立即更新（不同步的话页面像没生效）。
昵称前端先拦空串与 50 字上限，后端 `@NotBlank/@Size` 仍是最终防线。

---

## 4. 验证

| 项 | 结果 |
|---|---|
| `npm run lint` / `test` / `build` | 0 警告 / 15 通过 / 通过 |
| `day56-local-e2e.py` | **40 / 40**，VERDICT: OK |
| 订单状态过滤（实测） | `COMPLETED` → 3 条；`PENDING_PAYMENT` → 0；`SHIPPED` → 0 |
| 翻页（实测） | `page=2&size=2` → total=3、records=1 |
| 地址接口（实测） | create / update / setDefault / delete 全部 code=200 |
| 昵称接口（实测） | `PUT /api/users/me/nickname` code=200 |

截图（本机临时目录，未入库）：`account-home` / `account-orders` / `account-refunds` /
`account-coupons` / `account-addresses` / `account-profile`，用 Edge 无头 + CDP 注入登录态截取。

---

## 5. 没做的

1. **头像上传**：需要对象存储与上传接口，不是本轮范围；当前用昵称首字圆圈代替。
2. **手机号换绑**：涉及验证码与账号安全，单独设计。
3. **地址默认互斥的并发验证**：后端是单条 UPDATE，逻辑上原子；没有专门压测两个请求同时设默认。
4. **管理端未动**。
