# Day 75 · 商户后台（第 2 层：商品域数据隔离）

## 范围

- merchants 表：一个店铺一个账号（shop_id UNIQUE），种子 merchant / merchant123 → MallX 自营；
- 商户登录 POST /api/auth/merchant/login：token 与管理员同一套（type=ADMIN），
  但 perms 只有商品域：product:list / product:detail / product:create / product:update
  + 分类、品牌字典读 + 一条 **SHOP_SCOPE_<shopId>**；
- 数据隔离：ShopScope.currentShopId() 从 SecurityContext 读范围，
  商品后台接口按它过滤/校验：
  - 列表只返回自己店铺的商品（AND shop_id = ?）；
  - 详情/编辑/删除跨店 → **404**（不泄露「存在但不是你的」）；
  - 新建商品强制 shop_id = 当前店铺（请求体里的 shopId 被覆盖）；
  - 商户没有 product:delete，删除按钮不出现；
- 前端：登录页加「管理员 / 商户」切换；商户登录后菜单只剩「商品管理」，商品页隐藏店铺下拉。

## 验证（实测）

| 项 | 结果 |
|---|---|
| 商户登录 | 200，perms 含 SHOP_SCOPE_1 |
| 商品列表 | total=2，仅 shop 1 的 Lenovo / Huawei |
| 跨店详情 /admin/products/1 | 404「商品不存在」 |
| 新建商品（body 里 shopId=3） | 落库 shopId=1（被强制） |
| demo token 打管理端 | 403 |
| 管理端单测 / C 端主链路 e2e | 48 通过 / 40/40 |

## 不做的（第 2 层边界）

1. **订单/售后按店铺隔离**：orders 没有 shop_id，要按明细 join 反查，属下一层；
2. 商户自助改店铺信息、结算分账；
3. 一店多账号与细粒度权限（第 2 层固定一套 perms，写在控制器里而不是角色表）；
4. 商户端独立应用（当前复用 admin-app，用 perms 收菜单）。
