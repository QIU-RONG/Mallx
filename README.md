# MallX 企业级电商系统

[![CI](https://github.com/QIU-RONG/Mallx/actions/workflows/ci.yml/badge.svg)](https://github.com/QIU-RONG/Mallx/actions/workflows/ci.yml)

模块化单体的 B2C 电商**后端**。存储与商品搜索全部落在 **PostgreSQL**，
V1.0 不引入 Elasticsearch / Redis / 消息队列 —— 「用关系库把该做的事做完」是本项目的第一条约束。

```text
状态：V1.0 后端 API 已完成（Day 01–33）
端点 77 个   ·   权限码 41 个   ·   核心表 22 张   ·   模块 11 个
Java 185 文件 / 14.5k 行   ·   Controller 24 个   ·   Mapper XML 12 份   ·   SQL 脚本 14 份
回归基线：全链路 245 条断言 + 各域验收 979 条（合计 1224），每次改动必跑（见 §测试与回归；CI 每次 push 自动跑同一套）
```

第一次来？直接跳到 **[快速开始](#快速开始)**，或先看 **[接口文档](#接口文档)**。

---

## 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| 语言 / 运行时 | Java（Temurin） | 21 |
| 框架 | Spring Boot | 4.1.1 |
| 持久层 | MyBatis-Plus（`mybatis-plus-spring-boot4-starter`） | 3.5.17 |
| 认证授权 | Spring Security + JWT（JJWT） | 7.1.1（随 Boot） |
| 数据库 | PostgreSQL（Docker 运行） | 16（`16-alpine`） |
| 接口文档 | springdoc-openapi + Swagger UI | 3.1.1 |
| 搜索 | PostgreSQL 全文检索（`tsvector` + GIN）+ `pg_trgm` + `jsonb` GIN | — |
| 前端 | **V1.0 不做**，界面由 Swagger UI 承担 | — |

---

## 模块结构

依赖方向是**单向**的：所有业务模块 → `mall-common`，`mall-server` → 全部。业务模块之间不互相依赖。

| 模块 | 职责 | 代表接口前缀 |
|---|---|---|
| `mall-common` | 统一返回体 `Result`、全局异常处理、`SecurityConfig`、JWT 过滤器、分页夹紧 | — |
| `mall-user` | 用户 / 登录 / 收货地址 | `/api/auth`、`/api/users`、`/api/addresses` |
| `mall-product` | 商品 / SKU / 分类 / 品牌 / 搜索 | `/api/products`、`/api/categories`、`/api/brands` |
| `mall-cart` | 购物车 | `/api/cart` |
| `mall-inventory` | 库存（`available` / `locked` / `sold` 三段式）+ 库存流水 | （仅管理端） |
| `mall-order` | 下单 / 订单状态机 / 取消 | `/api/orders` |
| `mall-payment` | 支付 | `/api/payments` |
| `mall-review` | 商品评价（含评分聚合） | `/api/products/{id}/reviews` |
| `mall-marketing` | 优惠券（发放 / 领取 / 下单抵扣 / 核销退券） | `/api/coupons` |
| `mall-admin` | 管理端聚合：管理员账号 / 角色 / 权限 / 仪表盘 / 用户管理 | `/api/admin/**` |
| `mall-server` | 启动模块（唯一有 `main` 的模块） | — |

> ★ **双账号体系**：C 端用户（`users` 表，token **不带权限码**）与管理端（`admins` 表，token 带权限码）
> 是两条完全独立的认证链，各自有登录入口。

---

## 目录结构

```text
MallX/
├── backend/
│   ├── mallx/                     # Maven 多模块（11 模块 + 父 POM）
│   │   ├── mall-common/           #   ↑ 见上表
│   │   ├── mall-user/ … mall-admin/
│   │   ├── mall-server/           #   启动模块 + application.yml
│   │   ├── pom.xml                #   父 POM（依赖版本、11 个 module 登记）
│   │   └── mvnw.sh                #   本机 Git Bash 用的 Maven 包装（★ 内含本机绝对路径）
│   ├── sql/                       # 数据库脚本：01 建表 / 02 索引 / 03 种子 / 04–14 增量补丁
│   └── loadtest/                  # 验收与压测脚本（Python 标准库，无第三方依赖）+ 报告
├── deploy/                        # Docker：仅数据库 / 数据库+应用一键起
│   ├── docker-compose.yml         #   开发用 PostgreSQL（宿主 5434）
│   ├── docker-compose.app.yml     #   全栈（postgres + app），独立 compose project
│   ├── Dockerfile                 #   应用镜像（装宿主打好的 jar）
│   └── README.md                  #   部署说明与排错
├── docs/
│   ├── api/                       # ★ API-总览.md（自动生成）+ openapi.json 快照 + users-api.md
│   ├── daily/                     # Day 01–33 的学习/交付文档（含 Day 28 方案稿）
│   ├── perf-report.md             # 并发压测与全链路回归汇总
│   └── backlog.md                 # 缺陷与改进清单（当前一览表已归零）
└── README.md
```

---

## 快速开始

### 0. 环境要求

| 需要 | 说明 |
|---|---|
| JDK 21 | `java -version` 应输出 `21.x` |
| Maven 3.9+ | 首次构建需要公网拉依赖；已缓存后可 `-o` 离线构建 |
| Docker Desktop | 用来跑 PostgreSQL 16（本机引擎需处于运行状态） |

### 1. 启动数据库

```bash
docker compose -f deploy/docker-compose.yml up -d
```

连接参数：库 `mallx`，用户 / 密码 `mallx / mallx123`，宿主端口 **5434**（映射容器 5432）。

> ⚠️ 端口是 **5434** 不是默认的 5432 —— 本机可能已有别的 PostgreSQL 占着 5432。
> 只验证「通不通」用端口探测即可，不必先装 psql 客户端。

### 2. 初始化数据库

**空库首次初始化**，按文件名字典序执行（顺序有意义，别跳）：

```bash
cd backend/sql
psql -h localhost -p 5434 -U mallx -d mallx -f 01-schema.sql   # 22 张表 + 全文检索触发器
psql -h localhost -p 5434 -U mallx -d mallx -f 02-index.sql    # 索引（含 GIN / trgm / JSONB）
psql -h localhost -p 5434 -U mallx -d mallx -f 03-data.sql     # 种子数据 + 初始 RBAC
# 04–14 是后续每天的增量补丁，全部幂等（可重复执行）
for f in 04-review-constraints 05-admin-permissions 07-admin-permissions \
         08-marketing-permissions 09-user-coupons-unique 10-brand-permissions \
         11-order-discount 12-day22-permissions 13-day23-permissions 14-brand-crud-permissions; do
  psql -h localhost -p 5434 -U mallx -d mallx -f "$f.sql"
done
```

| 脚本 | 做什么 |
|---|---|
| `04-review-constraints.sql` | `reviews` 两处缺口（`order_item_id` 补 `NOT NULL` 等） |
| `05` / `07` / `08` / `10` / `12` / `13` / `14` | **权限补发**：新增权限码 + 授权给角色（Day 17/18/20/20/22/23/24） |
| `09-user-coupons-unique.sql` | `user_coupons` 的「一人一券」唯一约束（★ 补 `UNIQUE` 必须同时 `SET NOT NULL`） |
| `11-order-discount.sql` | `orders` 增加 `discount_amount`（优惠额快照） |
| `06-day17-fixtures.sql` | **可选**，仅开发/验收用：造 `op_order`、`op_product` 两个受限管理员 |

> ★★ **加了新的 `@PreAuthorize("hasAuthority('xxx'))` 就必须补发权限行**，
> 否则该接口对**所有人**（包括超管）稳定 **403**，而现象长得像「权限码拼错了」。
> 原理与判据见 `docs/daily/Day-17…` 与 `docs/backlog.md`。
>
> ★★★ **这些脚本被 Docker 批量执行时是「一个报错、后面全不跑」**：
> `docker-entrypoint-initdb.d` 用 `psql -v ON_ERROR_STOP=1` 逐文件执行，
> 任何一个文件报错都会**掐断整个初始化**，排在后面的补丁**静默跳过**
> （实测事故：容器里只有 20 条权限，而 `docker compose ps` 全绿、app healthy）。
> ⇒ 写补丁的硬规矩：**「故意报错」必须被内部消化**（包进 plpgsql `EXCEPTION` 块），
> 详见 [`deploy/README.md`](deploy/README.md) §六 坑 1。
> 跑 `python backend/loadtest/day25-sql-strict-check.py` 可随时复核这条链路。

### 3. 编译

```bash
cd backend/mallx
mvn install -DskipTests            # 首次（需联网）
mvn -o install -DskipTests         # 依赖已缓存后（离线，约 40s）
```

产出的可执行 jar：`backend/mallx/mall-server/target/mall-server-0.0.1-SNAPSHOT.jar`。

### 4. 启动

**方式 A：本地 java 起 jar**（最常用，内存可控）

```bash
cd backend/mallx/mall-server/target
java -Xmx384m -XX:MaxMetaspaceSize=160m -jar mall-server-0.0.1-SNAPSHOT.jar --server.port=8080
```

**方式 B：Docker Compose 一键起全栈**（数据库 + 应用，无需本机装 JDK）

```bash
cd deploy
cp .env.example .env               # 改掉 JWT_SECRET 与 DB_PASSWORD
docker compose -f docker-compose.app.yml up -d --build
docker compose -f docker-compose.app.yml ps      # 等 app 变成 (healthy)
```

详见 [`deploy/README.md`](deploy/README.md)（含常见坑与排错）。

> 方式 A 与 B 之外还有个 Git Bash 包装脚本 `backend/mallx/mvnw.sh` ——
> 它里面写死了本机的 Maven 安装路径，**只在这台机器上可用**，不要当通用入口。

### 5. 验证

```bash
curl http://127.0.0.1:8080/api/hello
# {"code":200,"message":"success","data":"Hello MallX"}
```

浏览器打开 **<http://127.0.0.1:8080/swagger-ui/index.html>**，右上角 **Authorize** 里粘 token 即可调受保护接口。

这套「快速开始」里的每条命令都有脚本实测：
`backend/loadtest/day25-readme-quickstart-check.py`（16 条断言，含「匿名访问应该是 401」这类反例）。

---

## 种子账号

| 身份 | 账号 / 密码 | 权限 |
|---|---|---|
| C 端用户 | `demo` / `demo123` | 登录后可用 C 端接口（token **不带**权限码） |
| 管理端超管 | `admin` / `admin123` | 全部 41 个权限码（`SUPER_ADMIN`） |
| 管理端受限 | `op_order` / `op123456` | 仅 `order:*`（**需先执行 `06-day17-fixtures.sql`**） |
| 管理端受限 | `op_product` / `prod123456` | 商品 / 库存域，**无** `order:*` |

两个受限账号互为**反向对照** —— 「A 能 B 不能」才是权限矩阵区分度的来源；
只用全权超管测，什么都证明不了。

---

## 接口约定

### URL 前缀

| 前缀 | 用途 | 鉴权 |
|---|---|---|
| `/api/**` | C 端（token 为 C 端用户） | 公开白名单 + 登录 |
| `/api/admin/**` | **管理端一律挂这里** | `@PreAuthorize` 权限码 |

> ⚠️ 管理端接口**绝不能**挂到 `/api/products/**` 或 `/api/categories/**` 下：
> 这两条前缀的 `GET` 在 `SecurityConfig` 白名单里，而白名单**先匹配先赢** ⇒
> 会绕过全部鉴权被**静默公开**。白名单的每条 `/**` 都要问一遍「这个前缀下还有没有私有接口」。

### 统一返回体

```json
{ "code": 200, "message": "success", "data": { } }
```

### ★★ 状态码约定（最容易踩的一条）

| 场景 | HTTP | body.code |
|---|---|---|
| 认证失败（匿名 / token 过期） | **401** | 401 |
| 授权失败（有 token 但无权限码） | **403** | 403 |
| **业务失败**（库存不足、状态不允许、重名…） | **200** | 400 / 404 / 500… |
| 参数校验失败（`@Valid`） | **200** | 400 |
| 路径不存在 | **404** | — |

⇒ **判一次业务调用是否成功，必须看 `body.code`，不能只看 HTTP 状态码。**
只有 Security 层的 401/403 与「路径不存在」的 404 是真 HTTP 状态码。

> 另有一条容易误解的：白名单是**方法粒度**的。匿名 `POST` 打一条白名单里的 `GET` 路径得到 **401**
> （Security 过滤器链先于 MVC 路由），**带 token** 才会走到 MVC 拿到 **405**。

### 分页

`current`（页码，从 1 起）+ `size`（每页条数，**上限 100**；`size <= 0` 会被夹紧成默认值）。
返回 `{ records, total, current, size }`。C 端商品列表对外用的是 `page` 参数名，内部才叫 `current`。

---

## 鉴权模型

三档，逐档收紧：

```text
① 公开（白名单，无需 token）      /api/hello · swagger · GET /api/products/** · GET /api/categories/**
                                  GET /api/brands · GET /api/coupons（精确路径）
② 登录（C 端 token，无权限码）    /api/cart/** · /api/orders/** · /api/users/me · /api/addresses/**
③ 权限码（管理端 token 携带）     /api/admin/**  →  @PreAuthorize("hasAuthority('域:动作')")
```

- 权限码形如 `product:update`、`order:ship`、`role:assign-permission`，共 **41** 个。
- 「谁能干什么」由 `roles` / `permissions` / `role_permissions` 决定，登录时**打成快照写进 token**。
  因此**改权限后需要重新登录**（当前 TTL 120 分钟）。
- 完整的「端点 → 权限码」对照表见 [`docs/api/API-总览.md`](docs/api/API-总览.md)。

---

## 接口文档

| 文档 | 说明 |
|---|---|
| [`docs/api/API-总览.md`](docs/api/API-总览.md) | **77 个端点的全量清单**：路径 / Tag / 说明 / 鉴权档位 / 权限码，按「公开 / 管理端 / C 端 / Tag」四个视角各列一遍。**由脚本生成** |
| [`docs/api/openapi.json`](docs/api/openapi.json) | 运行时 `/v3/api-docs` 的快照（机器可读，可直接喂 Postman/Insomnia/codegen） |
| [`docs/api/users-api.md`](docs/api/users-api.md) | 用户域接口的**逐条**说明（含历史与已下线端点） |
| Swagger UI | <http://127.0.0.1:8080/swagger-ui/index.html> |

重新生成 API 总览（需要应用已启动）：

```bash
curl -s http://127.0.0.1:8080/v3/api-docs -o docs/api/openapi.json
python backend/loadtest/day25-api-inventory.py
```

> 生成脚本同时做**三件事**：解析源码取权限码、与运行时 OpenAPI 做 `(方法, 路径)` **集合相等**核对、
> 与数据库 `permissions` 表交叉核对（源码用到的权限码必须存在且**至少被一个角色持有**）。
> 三者任一不成立就报 MISMATCH —— 文档不可能悄悄过期。

---

## 测试与回归

没有单元测试框架，取而代之的是 **69 个端到端验收脚本**：它们打真实 HTTP + 用 `docker exec psql` 直查数据库对账
（**不信接口自报**），跑完自动回滚到跑前状态。同一套流程已搬进 GitHub Actions（`.github/workflows/ci.yml`）：
每次 push 自动执行「构建 → 全新库 → SQL 严格检查 → 夹具 → M1 回归 → 各域验收」，判定全部来自脚本退出码。

```bash
cd backend/loadtest
python day26-m1-fixture.py                    # ⓪ 从零复现夹具：intruder 账号 + demo 地址 + 6 张 PAID 订单
python day17-m1-regression.py --baseline      # ① 记录基线（全表计数快照）
python day14-e2e-walk.py                      # ② 走全链路：下单→支付→发货→收货→评价
python day15-ship-confirm.py
python day16-review-e2e.py
python day17-a-order-list-verify.py           #    读侧
python day17-b-order-detail-verify.py
python day17-m1-regression.py                 # ③ 汇总 + 比对基线
```

> ★★ **为什么需要 ⓪**：M1 的五个脚本各自带着「干净起始态」的隐藏前置——
> 流水必须空、全库无挂起单、sold 与已付订单对账一致、读侧要有历史订单可读、
> 还要 `intruder` 账号和 `address_id=2`。这些在 dev 库里从来都是手工测试的残留，
> 全新 initdb 库直接跑 M1 只有 44/72（脚本早退 ⇒ 断言总数也从 245 掉到 72）。夹具把它们固化成脚本（幂等，可重复），
> **245/245 从此可以从零复现**——这也是 CI 能成立的前提。

| 脚本 | 覆盖 | 断言 |
|---|---|---|
| `day17-m1-regression.py` | **M1 全链路回归**（3 条链路 + 2 条读侧，含逐字节回基线） | **245** |
| `day23-rbac-verify.py` | 管理端 / 角色 / 权限 / 分配 + 权限装载链路 | 91 |
| `day20-coupon-verify.py` | 优惠券发放 / 领取 / 我的券 | 82 |
| `day22-admin-verify.py` | 用户管理 + 仪表盘口径 | 67 |
| `day19-search-verify.py` | 全文检索 / `pg_trgm` / JSONB / 中文边界 / 索引 | 58 |
| `day21-coupon-use-verify.py` | 下单抵扣 / 核销 / 取消退券 | 53 |
| `day24-brand-crud-verify.py` | 品牌 CRUD + 权限矩阵 | 43 |
| `day18-e-admin-category-write-verify.py` | 管理端分类写 | 40 |
| `day20-l1l2-verify.py` | 分页夹紧 + 下架商品可见性分流 | 33 |
| `day20-l5-brand-verify.py` | 品牌字典（C 端 / 管理端口径成对） | 24 |
| `day12/13-*` | 并发下单（不超卖）/ 并发支付（不重复扣款） | 见 `docs/perf-report.md` |
| `day25-sql-strict-check.py` | **SQL 补丁严格模式自检**：14 份补丁 × **全新临时库** × `ON_ERROR_STOP=1` | 16 |
| `day27-explain-audit.py` | **索引 EXPLAIN 审计**：临时库 + 3 万行 + `VACUUM (ANALYZE)`，13 条查询验「索引是否真被用上」 | 38 |
| `day28-search-rewrite-probe.py` | **搜索改法预研**：临时库对照 V0 现状 / V1 补 trgm 索引 / V2 拆 UNION / V3 只留全文（含中文黑洞与 `UNION ALL` 重复） | 24 |
| `day29-dashboard-explain-audit.py` | **管理端 / Dashboard 聚合审计**：临时库 A/B 对照「给 `payments` 加索引值不值」，含「加索引不能改数」判据 | 20 |
| `day31-index-drop-probe.py` | **DROP 实验**：把候选索引删掉再跑，验「删它安全」；**含对照组**证明装置有区分度 | 18 |
| `day32-pagination-index-probe.py` | **分页 + 排序的索引**：偏斜分布（1 个 power user 2 万单）下对照复合索引；含 **keyset vs OFFSET** 深分页探针 | 19 |
| `day33-coupon-status-probe.py` | **券侧索引收尾**：DROP 实验定性 `idx_coupons_status`（死）/ `idx_user_coupons_user_id`（冗余）；含**真实规模**对照 | 19 |
| `day26-m1-fixture.py` | **M1 从零复现夹具**（幂等）：intruder + 地址 + 6 张 PAID 单 + 归零幽灵计数 | 31 |
| `day25-api-inventory.py` | API 总览生成 + 源码↔运行时↔数据库 三方核对 | 9 |

写脚本的三条硬规矩（都来自踩过的坑）：

1. **断言对着「设计」写**，不对着「库的默认行为」写；脚本与设计打架时改脚本。
2. **样本必须落在判据的取值域里** —— 要测「重名」，那个名字得**先真实存在**。
3. **失败判据是 `body.code`，不是 HTTP 状态码**；且必须写死期望总数，防止「断言没被创建」导致假通过。

### 文档约定（活文档）

**活文档 = `README.md` + `docs/api/**` + `deploy/README.md`**（`docs/daily/**` 是历史存档，允许过期）。
**改动接口 / 权限 / 计数 / 清单时，同一批提交里必须更新所有引用方。**

> 为什么单列一条：这类漂移在本项目已发生 **3 次** ——
> `docs/api/users-api.md` 停在 Day 06（还把已修掉的越权漏洞写成「预期行为」）、
> `deploy/.env.example` 描述了一条**并不存在**的 `.gitignore` 规则、
> README 自身的 Day 范围三处不一致。
> 前两次都按**孤立事件**处理掉了 —— 三次说明缺的不是某一条修正，
> 而是**「改完顺手扫引用方」这个动作**。
> ★ 数字也是文档的一部分：**没有取证的数字等于没有数字**；
> 文档漂移比缺文档更坏（缺文档会让人去查，**错误的文档会让人不再查**）。

---

## 性能与正确性证据

并发下的「不会超卖 / 不会重复扣款」不是信仰，是压测出来的：

| 场景 | 正式实现（条件 UPDATE / CAS） | 对照组（先查后改） |
|---|---|---|
| 20 线程抢 10 件库存 | 成功 **恰好 10**，`available 10→0`，库存**从未为负**，0.53s | **20 单全部成功**，实际只扣了 2 件 → **超卖 10 件** |
| 20 线程并发支付同一订单 | 成交 **恰好 1 次**（`payments` 1 行） | 收钱 **12 次**（19,497 元的订单收了 233,964 元） |

完整数据、审计日志与复现步骤见 **[`docs/perf-report.md`](docs/perf-report.md)**。

**索引侧同样有实测（Day 27，临时库 + 3 万行 `EXPLAIN ANALYZE`）**：
12 条真实查询里有 **2 个索引在生产形状下用不上** ——
`idx_products_search` 被 `searchProducts` 的 `OR` 兜底挡住（同一条 SQL 去掉 `OR` 后
**1.3 ms vs 68.5 ms**），`idx_products_status` 是低选择性死索引。
⇒ **「建了索引」与「查询用得上索引」是两件事**，见 `docs/perf-report.md` §五。

---

## 文档导航

- **想了解每一步怎么做的** → [`docs/daily/`](docs/daily/)：Day 01–33，每天一份，含设计取舍、实测记录、踩坑与判据。
- **想知道还剩什么问题** → [`docs/backlog.md`](docs/backlog.md)：缺陷/改进清单（一览表已归零，遗留项与「刻意不做」的原因都写着）。
- **想直接调接口** → [`docs/api/API-总览.md`](docs/api/API-总览.md) 或 Swagger UI。

---

## 版本规划

```text
V1.0 模块化单体 · 后端 API          ✅ 完成（Day 01–33，77 端点；界面由 Swagger UI 承担）
V1.1 Redis + RabbitMQ                缓存与异步（订单超时关单、库存预占释放）
V1.2 性能优化                        读写分离、慢查询治理、索引复盘
V1.3 Docker 容器化                   ✅ 完成（Day 25：deploy/ 三件套，非 root + healthcheck + 一键全栈）
V1.4 云部署                          生产化：镜像瘦身、配置外置、可观测性
V2.0 Spring Cloud Alibaba            微服务拆分（按当前模块边界）
```

> ★ `deploy/` 已交付，但**远端托管（CI/CD、域名、HTTPS、日志采集）尚未做** ——
> 「容器化」与「云部署」是两件事，本清单拆开记，避免把已完成的当成待做（或反之）。
