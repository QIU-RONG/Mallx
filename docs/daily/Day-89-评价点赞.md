# Day 89 · 商品评价「有用」点赞

- 新表 eview_likes（review_id + user_id 唯一，一人一条评价点一次）；
- 接口：
  - POST /api/reviews/{id}/like：点赞 / 取消点赞（同一接口切换，需登录；评价不存在或已隐藏 → 404）；
  - 商品评价列表在登录态下返回 likeCount 与 liked（游客也能看计数，liked 恒 false）。
- 计数与「我是否点过」用**一次 IN 查询**批量补齐，不做 N+1；
- 商品详情每条评价下加「有用」按钮：未登录点击提示登录，已点过显示品牌橙。

## 验证

- demo 点赞 → {liked:true, likeCount:1}；再点 → {liked:false, likeCount:0}；第三次 → true/1；
- 带 token 的列表 liked=true；游客点赞 → 401；
- 页面截图：两条评价一条「有用 1」、一条「有用」；
- 主链路 e2e 40/40。
