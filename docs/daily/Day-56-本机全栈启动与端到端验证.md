# Day 56 · 本机起全栈 + 端到端验证（不依赖 Docker）

> 需求原话：**「先启动项目，进行测试」**。
> 本机实况：Docker Desktop 装了但**引擎没起**、PostgreSQL 18 服务在跑但**口令未知**、
> 8080 被**另一个项目**（InterviewGuide）占用。
> ⇒ 本日的重点不是写功能，而是**在没有 Docker 的机器上真的把 MallX 跑起来并验一遍**。

---

## 0. 结论速览

| 项 | 结果 |
|---|---|
| 数据库 | 临时 PG 集群（`%TEMP%\mallx-pg`，127.0.0.1:5434，trust 认证） |
| 迁移 | `backend/sql/01→19` **全部按序跑通**，permissions = **48** |
| 后端 | `mall-server.jar --server.port=8081`（8080 让给别的项目），health = UP |
| 前端 | admin-app `:5174`、mall-app `:5173`，均 200；代理指向 8081 |
| 端到端 | `day56-local-e2e.py` **40 / 40 通过**（管理端接口面 / C 端主链路 / 评价审核 / 写接口冒烟 / 越权面） |
| 新增能力 | `VITE_API_TARGET` 环境变量（两个前端的 dev 代理后端地址可覆盖） |

---

## 1. 怎么在没有 Docker 的机器上跑起来

四条本机约束，逐条绕开（都是环境问题，不是代码问题）：

| 约束 | 绕法 |
|---|---|
| 没有 Docker 引擎 ⇒ 老的 `docker exec mallx-postgres psql` 全部不可用 | 用 `D:\PSQL\bin` 的 PG 18 二进制 `initdb` 出一个**临时集群**，端口 5434（与应用默认值一致） |
| 已有 PG 服务（5432）但**不知道口令** | 不碰它。临时集群用 `--auth=trust`，不设口令、只监听本机 |
| 8080 被 InterviewGuide 占用 | MallX 用 `--server.port=8081`；前端代理加 `VITE_API_TARGET` 指过去 |
| 应用默认连 5434 的 `mallx` 库 | 临时集群建同名库 + 同名用户，一次 `01→19` 初始化 |

复现命令（本机）：

```powershell
# 1) 临时 PG
$bin='D:\PSQL\bin'; $data="$env:TEMP\mallx-pg"
& "$bin\initdb.exe" -D $data -U mallx --auth=trust -E UTF8 --locale=C
& "$bin\pg_ctl.exe" -D $data -l "$data\pg.log" -o "-p 5434" start
& "$bin\createdb.exe" -h 127.0.0.1 -p 5434 -U mallx mallx

# 2) 迁移（必须按文件名序，01→19）
Get-ChildItem D:\MallX\backend\sql\*.sql | Sort-Object Name |
  ForEach-Object { & "$bin\psql.exe" -h 127.0.0.1 -p 5434 -U mallx -d mallx -v ON_ERROR_STOP=1 -f $_.FullName }

# 3) 后端
$env:DB_PORT='5434'; $env:DB_HOST='127.0.0.1'; $env:DB_PASSWORD='mallx123'
java -jar backend\mallx\mall-server\target\mall-server-0.0.1-SNAPSHOT.jar --server.port=8081

# 4) 前端（两个终端）
$env:VITE_API_TARGET='http://127.0.0.1:8081'; npm run dev   # admin-app → 5174 / mall-app → 5173

# 5) 端到端
$env:MALLX_BASE='http://127.0.0.1:8081'; $env:MALLX_PSQL='D:\PSQL\bin\psql.exe'
python backend\loadtest\day56-local-e2e.py
```

★ 迁移一次跑通（19/19、permissions=48）顺带验证了 Day 55 的 19 号权限补丁：
**它没有把 initdb 掐断**，`review:list` / `review:status` 都在库里。

---

## 2. `VITE_API_TARGET`：一个环境变量，而不是改死代理

原来两个 `vite.config.ts` 都把代理目标写死 `http://127.0.0.1:8080`。
本机 8080 被占用时，前端能起、**但所有接口打到别的项目上** —— 现象是「登录一直失败、后端像没起」。

改法：`target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8080'`。

- 默认值不变 ⇒ 日常开发、CI、生产反代**行为零变化**；
- 覆盖是**启动期**读取，所以写在 `npm run dev` 的同一环境里，改完要重启 dev server；
- ★ 不把它写进 `.env`：这是「这台机器端口冲突」的临时事实，不是项目配置。

---

## 3. 端到端验证（40 条）

`day56-local-e2e.py` 分五段，**读库用本地 psql**（`MALLX_PSQL` 覆盖路径），不依赖 Docker：

| 段 | 条数 | 验什么 |
|---|---|---|
| A · 管理端接口面 | 11 | 商品/分类/品牌/券/用户/角色/权限/评价/仪表盘 9 个列表全部 200；权限字典 **48** 条；`review:list`/`review:status` 在字典里 |
| B · C 端主链路 | 9 | 地址 → 加购 → 下单 → 支付 → 发货 → 确认收货 → 发表评价（**真实业务路径**，非 SQL 造数） |
| C · 评价审核 | 6 | 隐藏后 C 端评价数 -1、记录消失、平均分实时回退；管理端 `status=0` 仍可见；恢复后三处一起回来 |
| D · Day 54 写接口 | 9 | 分类建/改/删、品牌建/重名 400/删、券建/**双面额 400**/删 |
| E · 越权面 | 2 | 匿名打管理端 → 401；**C 端 token → 403** |

### ★ 一个被实测纠正的断言

E.1 的第一版写的是「C 端 token 打管理端接口 → 401」，实测是 **403**。
这不是 bug，是项目一贯的判据：

```text
匿名（过滤器层不知道你是谁）        → 401
已认证、但没有该权限码              → 403
```

⇒ **改的是断言，不是代码**（与 backlog 里 L5 那条「实测 ≠ 设计时先定性」同一条方法论）。

### 通过前端源站验证（不只是直连后端）

| 请求 | 结果 |
|---|---|
| `http://localhost:5174/api/auth/admin/login`（Vite 代理 → 8081） | code=200，token 1243 字符 |
| `http://localhost:5174/api/admin/reviews?current=1&size=5` | code=200，total=2 |
| `http://localhost:5173/api/products/1` | code=200，`Apple iPhone 17 Pro`，3 个 SKU |
| `http://localhost:5173/api/products/1/reviews` | code=200，count=2，avg=5.0 |

⇒ 三个进程（前端 5173/5174、后端 8081、库 5434）**在同一套请求链上真的通了**。

---

## 4. 当前怎么用

| 入口 | 地址 | 账号 |
|---|---|---|
| C 端商城 | http://localhost:5173 | `demo / demo123` |
| 管理后台 | http://localhost:5174 | `admin / admin123` |
| 后端 | http://127.0.0.1:8081（health: `/actuator/health`） | — |

⚠️ 三个进程都是**本次会话起的后台任务**；关掉会话/机器后需按 §1 重新起。
⚠️ 数据库是 `%TEMP%\mallx-pg` 的临时集群 —— 删除该目录即回到全新库。

---

## 5. 本日没验到的

1. **没有复跑 day14/15/16 的完整 M1（434 条）**：它们把读库写死成
   `docker exec mallx-postgres psql`，没有 Docker 引擎就跑不了。本日的 40 条覆盖了同一条主链路
   （地址→下单→支付→发货→收货→评价）**但断言密度远低于 M1**。
   ⇒ 下一步若要让老脚本也能在本机跑：给它们一个 `MALLX_PSQL` 直连模式（像本日脚本那样），
   或在有 Docker 的机器上跑一次 M1 作对照。
2. **没有浏览器级 UI 自动化**（本机没有 Playwright 之类的工具）：
   页面只验证到「HTTP 200 + 通过代理的真实接口」。视觉效果与交互仍需人工点一遍。
3. **没有启动 Redis / RabbitMQ**：两者都是可选依赖（缓存回源、关单扫描兜底），
   应用照常启动；因此**缓存与延迟关单路径本日未验证**。
