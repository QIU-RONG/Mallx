# 前端交付：FE1 → FE4

> 后端 Day 01–41 收口之后转向前端。四步：`mall-app` 骨架 → `mall-app` 交易链路 →
> `admin-app` → 接入 CI + 文档。提交 `9bf8058` / `0082bf8` / `95f5d0c` + 本次 FE4。

## 〇、一个决定：两个应用，不是单应用双角色

| 应用 | 端口 | 覆盖 |
|---|---|---|
| C 端 `mall-app` | 5173 | 登录 / 商品列表 / 详情 / 购物车 / 结算 / 下单支付 / 订单 / 我的券 |
| 管理端 `admin-app` | 5174 | 登录 / 布局 / 商品 CRUD / 订单 / 发货 / Dashboard |

C 端 token **不带权限码**、管理端 token 带 `perms`；两者的路由守卫、菜单、失败语义都不一样。
合进一个应用只能靠 `if (isAdmin)` 到处分叉 ⇒ 拆开。共享的只有「栈」和「接口契约」。

栈：Vue 3 + **TypeScript** + Vite 8 + Element Plus + Pinia + axios。
`vite.config.ts` 把 `/api` 反代到 `127.0.0.1:8080` —— 开发期免 CORS，生产期同 nginx 反导思路。

## 一、FE1 · 骨架（`9bf8058`）

- Vite 脚手架 + dev proxy + axios 封装 + Pinia auth（localStorage 持久化）+ 登录页 + 商品列表（分类/品牌过滤）+ 详情（多 SKU 选择）。
- ★ **axios 封装要消化的唯一后端怪癖**：Security 层拒绝 = 真实 HTTP **401/403**；
  业务失败 = **HTTP 200 + body.code**。所以 401 统一踢登录，`code != 200` 走「提示拒绝」而不是当网络错误重试。
- 实测：`vue-tsc` + `vite build` 过；经 5173 代理 登录 `code=200` / 详情 3 SKU / 列表 `total=5`。

**踩坑**
1. ★ **Vite 8 dev 只绑 localhost（IPv6）** ⇒ `curl 127.0.0.1:5173` 拿到 `000`，要用 `localhost`。
   一度被误读成「dev server 没起来」。
2. 沙箱拦 `npm install` 写 `node_modules`（**报拦截但实际装成功**）⇒ 先验完整性再决定是否重试。

## 二、FE2 · 交易链路（`0082bf8`）

购物车（**失效商品置灰、不计入结算**）/ 结算页（地址 + 可用券）/ 下单 → 支付 → `PAID` /
取消 → `CANCELLED` / 订单列表 + 详情（金额恒等式 `total − discount = pay`）/ 我的券与可领取。
全部经 5173 代理实测通，**后端零改动**。

**契约要点**（写进了 `api/index.ts` 注释，因为它反直觉）
- 下单入参**只有** `addressId` + 可选 `userCouponId`；
- 支付入参**没有 amount** —— 金额的唯一来源是 `orders.pay_amount`（客户端说了不算）；
- 券的 id 是 `user_coupons.id`，不是 `coupons.id`。

**踩坑**
1. ★★ **前端联调会在数据库里留下真实痕迹**（订单 / 支付 / 库存变动）—— 这是 day41 之后同款教训的
   第二次实证：跑完必须按 day26 常态还原（删 `orders`/`payments`、清 `inventory_logs`、
   PAID 单要 `available +1` 且 `sold −1`），否则 M1 收集器的 **(c) 数据库回基线** 必挂。
   ⇒ 结论：联调脚本应自带收尾清理。
2. 券表种子是 0 行 ⇒ 用管理端 `POST /admin/coupons` 造测试券补测（领券 200 / 重复领 400 一人一券 /
   我的券 `UNUSED`），测完按 FK 顺序清 `user_coupons` → `coupons`。

## 三、FE3 · 管理端（`95f5d0c`，29 文件 / 3756 行）

登录 / 布局 / 商品 CRUD / 订单列表·详情 / 发货 / Dashboard 六个页面。

**验收证据**（本机实跑，起 5174 经代理）
- 管理端 E2E **27 通过 / 0 失败**，其中含**权限码对照组**：`op_order` 打订单端点 `200`、
  打商品端点 **403（真 HTTP 状态码）** —— 「A 能 B 不能」才证明权限真的在把关。
- 商品链路：局部改名不下发 skus、编辑后 SKU 仍在、删除（软删）。
- 发货链路：C 端下单 → 支付 → 管理端 `POST /api/orders/{id}/ship` → 状态 `SHIPPED` + 发货时间落库。
- M1 回归 **245/245 OK**（67+56+75+26+21），(a)(a2)(b)(c)(d) 全 YES。
- 基线还原：`orders=6 / payments=6 / inventory_logs=0 / products=5 / sku4=149/1`。
- 推送后 CI `37943572979` = **success（3m36s）**。

**踩坑（Docker 引擎掉线）**
容器类断言前先探 5434。本次首跑收集器 `COLLECTOR=1`，原因是**轮次边界上 Docker 引擎自己停了**
（psql 输出成空串 → 脚本崩在 `int('')`）；重新拉起容器后重跑即 OK。**这不是代码问题**，
但「空串当成数字」这个崩溃形态值得单独记一笔。

## 四、FE4 · 接入 CI + 文档（本次）

### CI：新增 `frontend` job（与后端 `ci` job **并行**）

```yaml
frontend:
  strategy: { fail-fast: false, matrix: { app: [mall-app, admin-app] } }
  # npm ci  →  npm run build（= vue-tsc -b && vite build）  →  断言 dist/index.html 存在
```

三个设计点，都不是「顺手加的」：
1. **独立 job 而非塞进 `ci`**：前端不需要 postgres / redis / 应用，塞进去只是白等约 8 分钟基础设施。
2. **`npm ci` 而非 `npm install`**：锁文件是提交进仓库的，CI 必须装出与本地**同一棵树**，
   否则「本地过、CI 挂」根本不可复现。
3. ★ **额外断言 `dist/index.html` 存在**：`vite build` 退出码为 0 也可能是空产物 ——
   只看退出码等于什么都没测（同「只测好的那一侧 = 什么都没测」）。

**本地等价验证（推之前必须做）**：本机按 CI 原命令跑两个应用 —— `npm ci` rc=0、`npm run build` rc=0、
`dist/` 各 1.5 M。**验证方式本身就是纪律**：CI 改动先在本地把命令实跑一遍，再推。

**刻意不做**：前端 e2e 不进 CI。那需要后端 + 数据库 + 种子数据整套复制到 runner；
等前端出现过一次真实契约回归（改了接口而前端没跟上）再上，**不提前建**。

### 推送事故：GCM 挂死（值得单独记）

`95f5d0c` 提交于 10-05，但**一直没推上去**：本次排查时 `push.py` 跑了 **44 分钟零输出**。

- 现象：`tasklist` 里 `git-credential-helper-sel`（GCM 的 UI 助手）卡住等人交互，后台进程给不了。
- **不是网络**：9674 OPEN、github.com:443 可达。
- ⚠️ **陷阱**：`git ls-remote` 是**通的** —— 但 `QIU-RONG/Mallx` 是**公开仓库**，读操作匿名就能过。
  **读通 ≠ 写凭据可用**。
- ✅ 解法：绕开 GCM，改用 `gh` 自带凭据助手
  `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push origin main`
  ⇒ `0082bf8..95f5d0c  main -> main`，remote SHA == local HEAD。
- ★ 附带一个坑：把 token 自行拼成 `https://x-access-token:<token>@github.com` 会拿到
  **401 + `WWW-Authenticate: Basic realm="GitHub"`** —— `gho_` 这类 user-to-server token
  **用户名要写真实账号登录名**（本机 = `QIU-RONG`）；只有 `github_pat_*` / App installation token
  才用 `x-access-token`。

> 这条已固化进用户级 skill `win-git-push`（新增 `scripts/push_via_gh.py` 与该失败模式的判据）。

## 五、下一步

- **V1.4 云部署**：镜像瘦身、配置外置、可观测性；远端托管（CI/CD、域名、HTTPS、日志采集）——
  「容器化」（V1.3 已完成）与「云部署」是两件事。
- V2.0 Spring Cloud Alibaba 微服务拆分（按现有模块边界）。
- 前端侧暂不排新需求：先把 FE4 的门禁跑绿，e2e 等真实回归信号。
