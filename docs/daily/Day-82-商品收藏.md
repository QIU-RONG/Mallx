# Day 82 · 商品收藏

## 做了什么

- 新表 user_favorites（user_id + product_id 唯一，一人一商品一行）；
- 接口（全部需登录）：
  - GET /api/favorites 分页列出收藏；
  - GET /api/favorites/{productId}/exists；
  - POST /api/favorites/{productId}（幂等，重复收藏不报错）；
  - DELETE /api/favorites/{productId}（幂等）。
- 收藏列表不冗余存商品信息：按 productId 批量回查商品 + 一次价格聚合，
  **商品改价后收藏列表自动跟着变**；
- C 端商品详情加「收藏 / 已收藏」按钮（未登录点击提示并跳登录）；
- 个人中心新增「我的收藏」页（卡片网格 + 取消收藏 + 分页）。

## 验证

- 游客访问 GET /api/favorites → 401；
- demo 收藏 1/3/5 → 列表 3 件（含价格 9999/6499/8999）；
- 重复收藏 → 200（幂等）；取消后 exists=false；
- 收藏不存在的商品 → 404；
- 页面截图：3 张卡片、价格、取消收藏、分页正常；
- 主链路 e2e 40/40。

## 环境

临时 PG 集群（5434）再次因机器闲置停止；pg_ctl -D %TEMP%\\mallx-pg -o \"-p 5434\" start 拉起后正常，
后端无需重启（Hikari 自动重连）。
