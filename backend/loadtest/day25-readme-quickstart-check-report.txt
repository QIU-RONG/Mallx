==============================================================================
MallX README「快速开始」逐条实测
==============================================================================

[A] 依赖服务
  [OK]   A1 PostgreSQL 可连（docker exec psql -> 1）   rc=0 out='1' err=''
  [OK]   A2 GET /api/hello -> 200 + data="Hello MallX"   http=200 code=200 data='Hello MallX'

[B] 文档站
  [OK]   B1 GET /v3/api-docs -> 200 且 JSON 里的 paths 非空   http=200 paths=57
  [OK]   B2 文档里含 securityScheme bearerAuth（Authorize 按钮据此渲染）
  [OK]   B3 GET /swagger-ui/index.html -> 200   http=200

[C] 种子账号（03-data.sql）
  [OK]   C1 C 端登录 demo/demo123 -> 200 + 有 token + tokenType=Bearer   code=200 tokenType=Bearer
  [OK]   C2 管理端登录 admin/admin123 -> 200 + 有 token   code=200
  [OK]   C3 demo token -> GET /api/users/me 200，且出参【不含 password】   code=200 keys=['createdAt', 'email', 'id', 'nickname', 'phone', 'status', 'username']
  [OK]   C4 admin token -> GET /api/admin/dashboard/overview 200   code=200

[D] 鉴权三档（README「状态码约定」的实证）
  [OK]   D1 匿名 GET /api/brands -> HTTP 200（公开档，白名单）   http=200 code=200
  [OK]   D2 匿名 GET /api/db-check -> HTTP 401（★ 不在白名单；README 旧版把它写成公开验证接口）   http=401 body={"code":401,"message":"未登录或登录已过期","data":null}
  [OK]   D3 匿名 GET /api/coupons/my -> HTTP 401（私有，白名单只放行精确的 /api/coupons）   http=401
  [OK]   D4 C 端 token 打管理端 -> HTTP 403（★ 真状态码，不是 200+code）   http=403
  [OK]   D5 op_order（ORDER_ADMIN）打商品域管理端 -> 403（反向对照，证明 403 不是『没登录』）   http=403

[E] 白名单是【方法粒度】的
  [OK]   E1 匿名 POST /api/coupons -> HTTP 401（★ 不是 405：过滤器链先于 MVC 路由）   http=401
  [OK]   E2 带 token 的 POST /api/coupons -> HTTP 405（这才走到 MVC，发现没有 POST handler）   http=405

==============================================================================
ASSERTIONS: 16 / 16 passed   (EXPECTED=16)
VERDICT: OK
==============================================================================
