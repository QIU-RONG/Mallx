# Day 88 · 商品评价筛选（全部 / 有图 / 5 星 / 4 星）

- 商品评价接口增加两个可选参数：ating（精确星级）、withImage（只看有晒图的）；
  SELECT ... WHERE product_id AND status=1 后追加对应条件，聚合（平均分/总数）仍按全量口径；
- 商品详情评价区新增筛选胶囊：全部 / 有图 / 5 星 / 4 星；切换时从第 1 页重拉，
  空态文案区分「还没人评价」和「没有符合条件的评价」；
- 前端 productReviews 支持传 { rating, withImage }，不传行为不变。

## 验证

- /api/products/1/reviews：全部 total=1；?rating=5 total=1；?withImage=true total=0；
  ?rating=4&withImage=true total=0（均 code=200，聚合 count 保持全量 1）；
- 页面截图：筛选胶囊与选中态正常；
- 主链路 e2e 40/40。
