# Day 90 · 管理端概览「今日」看板

GET /api/admin/dashboard/overview 从 4 个累计值扩成 8 个：

- 今日：	odaySalesAmount（payments SUCCESS 当天 sum）、	odayOrderCount（orders 当天 count）；
- 待办：pendingShipCount（orders.status=PAID）、pendingRefundCount（refunds.status=APPLIED，待审核）；
- 原有 4 个累计值不变，前端分成「今日 / 累计」两行。

同时把「待发货 / 待处理售后」做成可点卡片：
/orders?status=PAID、/refunds?status=APPLIED；
OrderList / RefundList 挂载时读取 oute.query.status 作为初始筛选，链接点进去就是筛好的列表。

## 验证

- overview 返回 	odayOrderCount=1, todaySalesAmount=9999, pendingShipCount=0, pendingRefundCount=0（e2e 后的真实值）；
- 管理端截图：今日/累计两行 + 趋势图正常；
- lint / build / e2e 40/40 通过。
