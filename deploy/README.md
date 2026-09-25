# MallX 部署说明（Docker）

本目录有**两套**编排，用途不同，**可以共存**（端口与 compose project 名都错开了）：

| 文件 | 起什么 | 什么时候用 |
|---|---|---|
| `docker-compose.yml` | 只有 PostgreSQL 16（宿主 **5434**） | 本地/IDEA 里跑应用，只要一个数据库 |
| `docker-compose.app.yml` | PostgreSQL 16 + mall-server 应用（宿主端口见 `APP_PORT`，默认 8080） | 一条命令起完整环境 / 给别人演示 / 验收 |

```bash
# 只要数据库
cd deploy && docker compose -f docker-compose.yml up -d

# 全栈（独立 project 名 mallx-stack，与开发库 `mallx-postgres` 不打架）
cd deploy && docker compose -f docker-compose.app.yml up -d --build
```

---

## 一、前置条件

| 需要 | 说明 |
|---|---|
| Docker Desktop | **引擎必须处于运行状态**。本机实测它偶尔会自己退出（见 §六 坑 0） |
| 宿主 JDK 21 + Maven | 只为了**打 jar** —— 应用镜像**不负责编译**（见 §八） |
| `deploy/.env` | 由 `.env.example` 复制而来，全栈编排缺它会**拒绝启动**（故意的） |

---

## 二、全栈三步

```bash
cd deploy
cp .env.example .env          # ① 然后【必须】改 JWT_SECRET 与 DB_PASSWORD
docker compose -f docker-compose.app.yml up -d --build
docker compose -f docker-compose.app.yml ps        # ② 等 app 变成 (healthy)
curl http://127.0.0.1:8080/api/hello               # ③ {"code":200,...}
```

打 jar（如果 `mall-server/target/*.jar` 还没有）：

```bash
cd backend/mallx
mvn -o install -DskipTests        # 依赖已缓存时用 -o；首次去掉 -o
```

启动顺序由编排保证：`depends_on: postgres: condition: service_healthy` ——
数据库 healthcheck 没过之前 app **不会**启动，这是避免「表还没建完应用就起来」的第一道闸。

---

## 三、环境变量（`deploy/.env`）

变量名与 `docker-compose.app.yml` 里的 `${...}` **逐字对应**；多一个空格就是另一个变量。

| 变量 | 默认 | 必须改 | 说明 |
|---|---|---|---|
| `DB_NAME` | `mallx` | — | initdb 建库名 |
| `DB_USERNAME` | `mallx` | — | |
| `DB_PASSWORD` | — | ★★ **必须** | 用 `:?` 语法，未设置直接拒绝启动 |
| `APP_PORT` | `8080` | 按需 | **宿主**端口；容器内固定 8080 |
| `JWT_SECRET` | — | ★★★ **必须** | 签名密钥泄露 ⇒ 任何人可自签带任意权限码的 token，RBAC 归零 |
| `JAVA_OPTS` | `-Xmx512m -XX:MaxMetaspaceSize=192m -XX:+UseSerialGC` | 按机器内存 | 容器内 JVM 参数 |

生成密钥：

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

---

## 四、常用操作

```bash
cd deploy
docker compose -f docker-compose.app.yml ps                       # 状态（含 health）
docker compose -f docker-compose.app.yml logs -f app              # 应用日志
docker compose -f docker-compose.app.yml logs postgres | head -80 # ★ initdb 的输出在这里
docker compose -f docker-compose.app.yml exec postgres psql -U mallx -d mallx
docker compose -f docker-compose.app.yml restart app              # 只重启应用
docker compose -f docker-compose.app.yml down                     # 停（保留数据卷）
docker compose -f docker-compose.app.yml down -v                  # ⚠️ 停并【删除数据】
```

数据库**不对外发布端口**，只有 app 能访问它 —— 要连就 `exec` 进去，或在开发库里用
`docker-compose.yml`（宿主 5434）。

---

## 五、验收这套编排

```bash
python backend/loadtest/day25-compose-verify.py 8081
```

12 条断言，分四组：

| 组 | 验什么 |
|---|---|
| A | 容器层：app / postgres 都 `healthy`；app 以**非 root**（`mallx`）运行 |
| B | **initdb 链路**：22 张表建齐、`permissions` 恰好 41 行、最后一份补丁（`brand:*`）授权到位、`orders.discount_amount` 存在 |
| C | 端到端：`/api/hello`、匿名 `/api/products`、管理员登录拿 token |
| D | ★ 权限经**新库**真的生效：带超管 token 打 `/api/admin/roles` → 200；同一端点匿名 → **401** |

> B 组与 D 组是这套脚本存在的理由（见 §六 坑 1）。

---

## 六、★★ 三个必须知道的坑（都有实测事故）

### 坑 0 · 引擎自己退出了，报错却长得很像「编排文件写错了」

现象：

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running
```

**这不是 compose 的错，命令、文件、端口全都没问题 —— 是 Docker Desktop 没在运行。**
先把引擎起来再重试。

### 坑 1 · initdb 只在**数据卷为空**时跑一次；而且它用的是 `ON_ERROR_STOP=1`

两件事要分开说：

**（a）只跑一次。** `docker-entrypoint-initdb.d` 里的脚本仅在**首次**初始化（数据卷为空）时按
文件名字典序执行。数据卷一旦存在，**新增或修改的 SQL 补丁不会自动应用**。
现象：改了补丁、`up -d --build`，进容器一查还是旧数据。

**（b）任一文件报错就掐断后面全部。** postgres 官方 entrypoint 是以
`psql -v ON_ERROR_STOP=1` 逐个执行的 —— **任何一个文件报错，整个初始化当场停止，
排在它后面的文件全部静默跳过**。

> #### 真实事故（2026-09-25，本项目实测）
>
> `09-user-coupons-unique.sql` 的第三节有一段**自检**，做法是「故意插两次同一行、
> 期望第二次撞唯一约束」。这在**交互式 psql** 里很正常；但在 initdb 里，
> 那条**故意**的 `duplicate key` 直接把初始化掐断在 09 ⇒ **10/11/12/13/14 号补丁全部没跑**。
>
> 现场长这样（很容易误判方向）：
>
> | 看到的 | 实际含义 |
> |---|---|
> | `docker compose ps` 全绿、app `(healthy)` | 只证明**进程活着** |
> | 容器内 `permissions` 只有 **20** 行 | 应 41 ⇒ 补丁 10–14 没跑 |
> | 品牌 CRUD 的 `39/40/41` 不存在 | 最后一份补丁丢了 |
> | `GET /api/admin/roles` 带超管 token 也 **403** | 权限行不在，`@PreAuthorize` 必然拒绝 |
> | `logs postgres` 里只有一句 FATAL | 不细看像「基础镜像拉不下来」，排查方向整个跑偏 |
>
> **修法（已落地）**：把「期望失败」的语句包进 plpgsql 的 `EXCEPTION` 块，
> 让异常在**数据库内部**被接住、翻译成 `NOTICE` —— psql 看到的退出码是 0，验证却仍在。
> 判据也从「人看 stderr 里那句话对不对」改成**看退出码**。
>
> **⇒ 写 SQL 补丁的硬规矩**：文件要同时满足「交互跑」与「批处理跑」两种用法，
> **「故意报错」必须被内部消化，绝不能漏到 psql 层。**

**补救 / 正确姿势**：补丁要显式应用（幂等，可重复跑）。

```bash
cd deploy
docker compose -f docker-compose.app.yml exec -T postgres \
  psql -U mallx -d mallx -v ON_ERROR_STOP=1 < ../backend/sql/14-brand-crud-permissions.sql
```

改完补丁想从零验证，就重建数据卷（**⚠️ 会删数据**，见 §七）。

### 坑 2 · 构建报「凭据助手找不到」

现象：`docker build` 在拉基础镜像或解析 frontend 时报
`error getting credentials - err: exec: "docker-credential-desktop": executable file not found`。

原因：Docker CLI 与 `docker-credential-desktop.exe` 不在同一个目录里被找到。
把 `...\DockerDesktop\resources\bin` 加进 `PATH` 即可：

```powershell
$env:PATH = "C:\Users\<你>\AppData\Local\Programs\DockerDesktop\resources\bin;$env:PATH"
```

**另外，`deploy/Dockerfile` 顶部刻意不写 `# syntax=docker/dockerfile:1`** ——
那行会让构建器先去拉一个 frontend 镜像，在没有外网/凭据助手缺失的机器上，
报错出现在「解析 frontend」这一步，而信息长得像「基础镜像拉不下来」。
本文件只用到最基础的 `COPY/ENV/HEALTHCHECK`，内置 frontend 完全够。

---

## 七、重建数据卷（从零重跑 initdb）

```bash
cd deploy
docker compose -f docker-compose.app.yml down          # ⚠️ 不要加 -v，先确认里面没有要留的数据
docker volume rm mallx-stack_mallx-pgdata              # ★ 删掉数据卷 = 下次必跑 initdb
docker compose -f docker-compose.app.yml up -d --build
docker compose -f docker-compose.app.yml logs -f postgres   # 看着它把 01→14 跑完
```

卷名 = `<compose project 名>_<卷名>`，对应本文件里的 `name: mallx-stack` 与 `volumes: mallx-pgdata`。

---

## 八、两个刻意的设计决定

**① 镜像不负责编译。** `deploy/Dockerfile` 只把**宿主已打好的 jar** 装进运行时镜像，
不做「多阶段：容器内跑 mvn」。原因：

1. 本项目依赖本机 Maven 本地仓库（`mvn -o` 离线构建），在镜像里重拉一遍全部依赖既慢又要公网；
2. 真相只有一份 —— CI/本地打出的 jar 与镜像里的 jar 是**同一个文件**，
   不会出现「镜像里编出来的东西跟验收过的不是一回事」。

**② 数据库不发布端口、容器非 root。** 数据库只有 app 需要它，`expose` 就够；
应用容器用 `adduser -S mallx` 建的非特权用户运行，逃逸面小一个数量级。

---

## 九、排错速查

| 现象 | 最可能的原因 | 处理 |
|---|---|---|
| `failed to connect to the docker API ... npipe` | 引擎没运行 | 启动 Docker Desktop（§六 坑 0） |
| `dial tcp ... connectex` / 拉不动镜像 | 凭据助手或网络 | 修 `PATH`（§六 坑 2）；`docker pull eclipse-temurin:21-jre-alpine` 单独试 |
| `DB_PASSWORD 未设置（请检查 deploy/.env）` | 没复制 `.env` 或变量名拼错 | `cp .env.example .env`；变量名逐字核对 §三 |
| app 容器反复重启 | 数据库还没好 | 看 `logs app`；`depends_on` 的 healthcheck 已在，通常等 10–20s 自愈 |
| app 起来了但管理端接口 **403** | 权限行没进库（少数补丁丢了） | 查 `permissions` 行数是否为 41（§六 坑 1） |
| app healthy 但接口 500 / 表不存在 | initdb 中途失败 | 看 `logs postgres` 的 FATAL 行（§六 坑 1） |
| 改了 SQL 补丁但库没变 | initdb 只跑一次 | 手工应用补丁，或重建数据卷（§六(a) / §七） |
| `docker stop` 要等 10 秒才停 | `exec` 从 `ENTRYPOINT` 掉了 | 已修：`ENTRYPOINT ["sh","-c","exec java ..."]`，PID 1 才收得到 SIGTERM |

---

## 十、安全清单（上线前逐条核对）

- [ ] `JWT_SECRET` 换成随机长串（**不是**仓库里的默认值）
- [ ] `DB_PASSWORD` 换掉
- [ ] `deploy/.env` **没有**提交进仓库（已在 `.gitignore`）
- [ ] 数据库端口没有对公网发布
- [ ] 应用以非 root 运行（`docker inspect -f '{{.Config.User}}' mallx-stack-app-1` → `mallx`）
- [ ] `GET /api/admin/roles` 匿名访问返回 **401** 而不是 200
- [ ] 受限管理员账号（`op_order` / `op_product`）**没有**拿到超管权限
      —— `06-day17-fixtures.sql` 是**可选**的验收夹具，正式环境不要执行
