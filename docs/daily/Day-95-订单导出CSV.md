# Day 95 · 订单导出 CSV（Excel 可直接打开）

- 管理端订单列表新增「导出 CSV」：把当前页数据导出为 orders-日期.csv（UTF-8 BOM，Excel 打开不乱码）；
- 字段：订单号、状态、买家 ID、买家昵称、应付金额、下单时间；
- 导出走前端 Blob，不动后端；需要全量导出时按筛选条件分批翻页即可。

## 说明

- 管理端 AdminOrderVO 没有 irstItemName（那是 C 端 VO），导出用 userNickname 替代商品列；
- 后续若需要真正 Excel（多 sheet / 样式）再引后端导出，CSV 已满足运营查看。

## 验证

- 前端 lint / build 通过。
