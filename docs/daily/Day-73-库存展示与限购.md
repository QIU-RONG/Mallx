# Day 73 · 商品详情显示库存 + 限购

- 新增公开接口 GET /api/inventory/stock?skuIds=1,2,3：一次 IN 查询返回 skuId → available_stock；
  只暴露可售一格，不返回 locked/sold/total；单次最多 100 个 SKU；Security 按**精确路径 + GET** 放行。
- 详情页价格区显示「库存 N 件」；库存为 0 显示「该规格暂时缺货」且按钮变「已售罄」不可点；
- 数量选择器上限 = min(99, 当前规格库存)，换规格时把已选数量拉回合法范围；
- 库存接口失败不阻塞页面（按「未显示库存」处理），但不会假装有货。

验证：/api/inventory/stock 实测返回 {1:80,2:78,3:60}；主链路 e2e 40/40；详情页截图正常。
