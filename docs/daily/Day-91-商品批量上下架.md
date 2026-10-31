# Day 91 · 管理端商品批量上下架

- 新接口 PUT /api/admin/products/batch-status：{ ids:[...], status:0|1 }，一次最多 100 个；
- DTO 校验：ids 非空、status 只允许 0/1；越界/为空 → 400（业务码在 body）；
- 商户账号调用时按 SHOP_SCOPE_{id} 过滤，**只能改自己店铺的商品**（跨店 id 静默跳过，返回实际影响行数）；
- 更新后 catalogCache.bump() 让 C 端商品详情/树缓存代次失效；
- 商品列表加勾选列 + 「批量上架 / 批量下架」按钮 + 已选数量提示。

## 验证

- PUT batch-status {ids:[1,2],status:0} → data=2；再置 1 → data=2；
- 空 ids → 校验失败（body code=400）；
- 前端 lint/build 通过；主链路 e2e 40/40。
