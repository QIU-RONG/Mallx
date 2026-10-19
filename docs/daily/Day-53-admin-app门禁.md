# Day 53 · admin-app 配齐前端门禁

> 起点：Day 48 只给 mall-app 配了 ESLint + Vitest，admin-app 那两步在 CI 里被
> `if: matrix.app == 'mall-app'` 挡着 —— 当时的原则是「**宁可没有，也不做假绿**」。
> 本日补齐，CI run `39182142909` 全绿，两个应用的 Lint / Unit / Build 六步全部 success。

---

## 一、为什么 admin-app 不能照抄 C 端的测试

**骨架相同、语义相反**。三个高危区里有两处的「正确行为」正好和 C 端倒过来：

| 场景 | C 端 | 管理端 |
|---|---|---|
| 业务失败 | 弹提示 | 弹提示（同） |
| **协议 403** | 只提示「没有权限」 | **同样只提示**，但**更严重** —— 见下 |
| **身份校验** | 只看 token 是否存在 | 还要 `type === 'ADMIN'`（拦 C 端 token 混进后台） |
| **perms** | C 端 token 里没有 | 不落 localStorage，**只能从 token 解** ⇒ 刷新必须 `restore()` |

### ★★ 管理端 403 是【常态】，不是异常

超管之外的账号本来就只被授予少数权限码，点到没授权的功能是**正常工作状态**。
如果把 403 也交给 `gotoLogin`（清登录态 + 跳登录页），后果是：

> 运营点错一个菜单 → 被踢回登录页 → 重新登录 → 再点错 → 再被踢
> **不报错、不告警、日志里也没有异常**，只会被当成「这系统老掉线」。

⇒ 这是 admin-app 那份 http 单测存在的第一理由（`★★ HTTP 403 → 只提示，不 logout、不跳登录`）。

---

## 二、21 条断言（3 个文件）

| 文件 | 条数 | 锁什么 |
|---|---|---|
| `src/api/http.spec.ts` | 8 | 业务 200 直通 / 业务 401 三件事 / 业务 400 只提示 / 协议 401 三件事 / **★ 协议 403 不 logout 不跳转** / 500 带码 / 断网文案 / 已在登录页不重复 push |
| `src/stores/auth.spec.ts` | 8 | **★ `type==='ADMIN'` 闸门**（C 端 token ⇒ perms 必须为空）/ 畸形 token 不抛 / 非 JSON payload 不抛 / `hasPerm` / logout 清 storage / **★ 刷新后 `restore()` 恢复 perms** / 无 token 时 restore 不炸 |
| `src/router/guard.spec.ts` | 5 | 未登录 → `/login` / 未登录访问 `/login` 放行 / 已登录访问 `/login` → `/` / 已登录放行 / **★ 每次导航都调 `restore()`** |

两条「不报错」的故障是重点：

- **刷新后所有按钮消失**：`perms` 只从 token 解，漏了 `restore()` 就永远空着。
  接口照样能用（后端认 token，不认前端显隐），所以**用户只会觉得「后台坏了」**。
- **C 端 token 混进后台**：`decodePerms` 里 `type !== 'ADMIN'` 那一行就是闸门。
  漏了它，前端会把「越权尝试」显示成一堆**空白按钮**，让排查方向完全跑偏。

---

## 三、控制组（都带，且都 PASS）

### `_d53_admin_fe_ctrl.py` —— ESLint 控制组（**参数化**）

```bash
python _d53_admin_fe_ctrl.py            # 默认 admin-app
python _d53_admin_fe_ctrl.py mall-app   # 也能回跑 C 端
```

探针一次带 4 种违规（`console.log` / `: any` / `debugger` / `v-html`），
结果：基线 rc=0 → 探针 rc=1 且 **4 条规则全命中** → 删除探针后恢复 rc=0。

⚠️ 探针里**不能**带 `eslint-disable` 注释、文件名**不能**落在任何豁免里
（Day 47/48 各栽过一次）。

### `_d53_admin_unit_ctrl.py` —— 单测控制组（7 组）

| # | 变异 | 必须红 |
|---|---|---|
| ① | `http.ts` 403 也走 `gotoLogin` | `HTTP 403` |
| ② | `http.ts` 业务 401 只提示、不踢登录 | `code=401` |
| ③ | `auth.ts` 去掉 `type === 'ADMIN'` 判断 | `type=USER` |
| ④ | `auth.ts` logout 漏清 localStorage | `清内存 + 清 localStorage` |
| ⑤ | `auth.ts` `restore()` 变空操作 | `只有 token 在 localStorage 时` |
| ⑥ | `router` 去掉 `auth.restore()` | `每次导航都调 restore` |
| ⑦ | `router` 未登录也放行 | `未登录访问受保护页` |

结果：**7/7 全部命中，还原干净，收尾回基线**（36 秒跑完，无需构建）。

---

## 四、途中三个坑

**① `npm install` 在线挂 20 分钟、零输出**
`registry.npmjs.org` 在这个网络下会卡住（与 git 的 9674 代理问题同源：直连可用，但默认配置指向坏通道）。
mall-app 装过同版本 ⇒ 缓存命中 ⇒

```bash
npm install -D --offline eslint@10.12.0 @vue/eslint-config-typescript@14.9.0 \
  vitest@5.0.4 @vue/test-utils@2.5.1 jsdom@30.1.2     # 180 包 / 14 秒
```

★ 判据：**20 分钟零输出 = 卡网络**，不是「包太大」。先 `npm cache ls <pkg>` 确认缓存，再 `--offline`，
并**钉死版本**与另一个应用对齐（否则两边版本会慢慢漂）。

**② mock 路由时 `push` 放错位置**
`http.ts` 写的是 `import router from '../router'` → `router.push(...)`。
第一版 mock 成 `{ default: { currentRoute }, push }`（具名导出）⇒
`TypeError: default.push is not a function`，两条 401 用例一起红。
⇒ **mock 的形状必须和调用方读的形状一致**：`push` 要挂在 `default` 对象上。

**③ `vite.config.ts` 的 `defineConfig` 必须从 `vitest/config` 导入**
Vite 自己的 `UserConfigExport` **不含 `test` 字段**，直接写 `test` 会让 `vue-tsc` 报 TS2769。
C 端 Day 48 就在 CI 上栽过这一次 —— 所以这次改完**必须把 build 也跑一遍**（lint + test 都发现不了）。

---

## 五、结果

| 项 | 值 |
|---|---|
| admin-app 单测 | **21 条**（2.5 秒） |
| 两个应用合计 | **36 条**（15 + 21） |
| 提交 | `477997d`（11 files，+3324/−98） |
| CI | run `39182142909` **全绿**；两个应用 Lint / Unit / Build **六步全 success** |
| 控制组 | ESLint 4 规则全命中 · 单测 7/7 命中 |

⇒ 前端如今**没有「无人值守的代码」了**：两个应用的公共出口（拦截器）、身份状态（store）、
路由守卫都被测试锁着，且这些测试都配了证明自己会红的控制组。
