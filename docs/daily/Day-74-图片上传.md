# Day 74 · 商品图片上传（本地存储）

- 新增 POST /api/admin/upload/image（multipart）：
  存本地磁盘（mallx.upload.dir，默认 ./uploads），返回 /uploads/yyyy/MM/uuid.ext；
  只收 jpg/png/webp/gif，≤2MB，扩展名由 Content-Type 推导（防路径穿越与可执行扩展名）；
  权限要求 product:create 或 product:update（demo token 实测 403）。
- 静态映射：UploadWebConfig 把 /uploads/** 映射到该目录；Security 按前缀 + GET 放行。
- 管理端新建商品：主图从「只填 URL」改为「缩略图 + 上传按钮 + 可粘贴 URL」。
- 两个前端的 vite proxy 都加了 /uploads，本地开发图片可直接显示。
- 顺手统一：商品列表「新建商品」按钮由绿色改为品牌橙（与查询/其他主按钮一致）。

验证：上传 1×1 PNG → 200 并返回 URL；静态访问 200 且 Content-Type 正确；demo token 403；管理端弹窗截图。
