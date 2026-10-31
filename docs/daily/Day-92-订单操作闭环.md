# Day 92 · 订单详情操作闭环

- 订单详情页新增：
  - 「取消订单」：仅 PENDING_PAYMENT 且具备 order:cancel 时显示，二次确认后调用 POST /api/admin/orders/{id}/cancel；
  - 「该用户售后」：跳转 /refunds?userId=xxx，售后列表挂载时读 oute.query.userId 作为初始筛选；
- 发货按钮原本就有（order:ship），现在三种状态动作在同一个详情页收口。

## 验证

- lint / build 通过；
- 取消接口规则由后端 CAS 保证（仅待支付可取消，0 行即 400）；
- 不新增接口，e2e 40/40 基线不受影响。
