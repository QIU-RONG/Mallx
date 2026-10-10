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

**首跑结果**（run `37946806601`，全 success）：`ci` 3m52s；`frontend (mall-app)` 21s；
`frontend (admin-app)` 22s —— 前端两个 job 与后端并行，代价可以忽略。

**当时刻意不做**：前端 e2e 不进 CI —— 那需要后端 + 数据库 + 种子数据整套复制到 runner。
判据是「等前端出现过一次真实契约回归（改了接口而前端没跟上）再上，**不提前建**」。

**【Day 43 补记 —— 那个信号出现了，已经接上】**

Day 43 本机联调正好抓到那一次契约回归：**商品列表 VO 里根本没有 `price`**（价格挂在 SKU 上），
前端拿不到这个字段 —— **编译期查不出来**（后端接口本身是对的），只有经由 dev server 代理
打真实接口、再按前端自己的类型定义 `frontend/*/src/types/api.d.ts` 核对字段名才会现形。
⇒ 按承诺把它接进 CI：`ci` job 新增 `Frontend e2e` 步骤（`actions/setup-node` + 两个 `npm ci`
+ 两个 dev server + 跑 `day43-fe-full-stack-e2e.py`）。

**为什么放 `ci` job 而不是新开一个 job**：它复用的正是 `ci` job 已经起好的后端 + 数据库 +
M1 夹具数据 —— 上面第 1 点说「前端不需要 postgres/redis/应用」，但**e2e 需要**，
新开 job 等于把这套依赖再复制一遍。
**代价**：`ci` job 从 3m36s → **5m02s**（约 +1.5 min），在预估范围内。

**首跑核实**（run `38039700183`，三 job 全 success）—— 按「绿灯不等于在干活」逐条查了 runner 输出：

| 证据 | runner 上的原文 |
|---|---|
| `npm ci` 真跑了 | `##[group]npm ci mall-app` · `##[group]npm ci admin-app` |
| 探测胶水真等了 | `mall-app up after 6s` · `admin-app up after 3s` |
| 联调真跑通 | `结果：54 通过 / 0 失败   （期望断言数 54）` + `VERDICT: PASS` |

⚠️ **本机无法等价跑这段胶水的边界（诚实标注）**：`day43` 脚本本身（54/54）、两个 dev server
起在 5173/5174、「轮询到 curl 返回 200」这套判定（用 PowerShell 等价跑，3s 内两个都 200）、
两个 `npm ci` rc=0 —— 都在本机实跑过；但**这段 bash 胶水本机跑不了**：
Git Bash 里 `npm` 不可直接执行（node 目录下的 npm 是无扩展名脚本 + `.cmd` 配对，
`npm -v` 输出乱码 + null byte），而且 Bash 工具不能嵌套起 bash（`bash script` 直接 rc=1、零输出）。
若将来要改这段胶水，只能靠 CI 首跑核实。

### ★ 护栏自带对照组（不这么做，「通过」什么都说明不了）

新增一条门禁时必须能证明它**会失败**。做法：往 `mall-app/src/api/http.ts` 末尾注入一行类型错误，
跑**同一条命令**：

| 场景 | 结果 |
|---|---|
| 注入 `const __controlGroup: number = "not-a-number";` | `npm run build` **rc=2**，`error TS2322: Type 'string' is not assignable to type 'number'`（+ `TS6133`） |
| 复原后 | **rc=0**，`git status` 干净 |

⇒ 这条门禁**有区分度**：类型错误会让 CI 的 `Type check + Build` 步骤真的失败（该步骤跑的就是这条命令）。
对照组排除的是「步骤名字好看但没有牙齿」这类假绿 —— 本项目已有过反面实例
（健康检查的正则被贪婪 `.*` 匹配到另一处输出而误判通过）。

**runner 侧复核**：`frontend` job 的 `Assert build artifact exists` 打印 `dist ok: 1.5M`，
与本机等价验证的 1.5M 一致 —— 说明 runner 上**真的构建出了产物**，不是步骤被跳过。

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
