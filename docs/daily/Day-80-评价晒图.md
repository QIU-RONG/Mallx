# Day 80 · 评价晒图

## 做了什么

- 新表 eview_images（review_id / image_url / sort，一张图一行；eviews.images 的 jsonb
  列因为 TypeHandler 读侧麻烦，没有使用）；
- POST /api/upload/image：**C 端登录用户**可传评价图（与管理端上传共用目录、同一套校验：
  jpg/png/webp/gif、≤2MB、扩展名按 Content-Type、路径 normalize、2MB 限制）；
  管理端入口保持独立、权限不变；
- 评价创建支持 images（最多 3 张，只接受 /uploads/ 或 http(s) 地址）；
  与评价写入**同一事务**；
- 商品详情评价区、我的评价都显示缩略图；
- 评价提交弹窗加「晒图」：最多 3 张、可删除、带上传中状态。

## 途中修的一个真 bug

第一次提交带图评价直接 500：eview_images.review_id 为 null。
原因：insertReview 是 XML 的 INSERT ... ON CONFLICT DO NOTHING，**不会回填自增 id**，
而代码拿 eview.getId()（null）去写图。
修复：插入后先 selectByOrderItemId 回查拿到真实 id，再写图片行 —— 并把这段放进事务，
避免「评价成功、图片失败」的半成品。

## 验证

- 上传：游客 401、登录 200，返回 /uploads/2026/10/...png；
- 带图评价：200，返回的 images 含该 URL；商品评价列表与「我的评价」都能读到；
- 商品详情截图：两条评价的缩略图正常显示；
- 主链路 e2e 40/40。

## 边界

1. 没有图片审核（管理端评价管理看不到图；违规图要靠人工删库）；
2. 没有图片压缩/多尺寸，原图直出；
3. 最多 3 张、单张 2MB（前端 + 后端双重限制）。
