# Day 83 · 管理端评价审核展示晒图

- AdminReviewVO 增加 images；pageAdmin 按本页评价 id 一次查 eview_images 批量补齐（同 C 端口径）；
- 管理端「评价管理」新增「晒图」列：缩略图 + 点击 el-image 全屏预览；无图显示「无」；
- 隐藏/显示评价的逻辑一行没动（只加了读取）。

## 验证

- /api/admin/reviews 返回的 2 条带图评价（23/24）images 正确；
- 页面截图：晒图列显示缩略图，无图为「无」；
- 主链路 e2e 40/40。
