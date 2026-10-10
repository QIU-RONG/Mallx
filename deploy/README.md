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
| `SPRING_PROFILES_ACTIVE` | `prod` | 按需 | ★ V1.4：默认走**生产 profile**（关键项无默认值 + 关掉 swagger-ui）。想让它像开发机一样跑就设 `dev` |
| `REDIS_HOST` / `REDIS_PORT` | `redis` / `6379` | 按需 | 可选依赖，连不上走降级（缓存读回源） |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | `rabbitmq` / `5672` | 按需 | 可选依赖，连不上走 2 分钟扫描兜底 |

> ★★ **`JAVA_OPTS` 已不在本表**（V1.4 变更）：JVM 参数的**单一来源是镜像的 `ENV`**
> （容器感知的 `-XX:MaxRAMPercentage=75 ...`，见 §八④）。
> 原来 compose 里写了 `JAVA_OPTS: ${JAVA_OPTS:-默认值}`，会**永远覆盖**镜像 ENV ——
> 于是「改了 Dockerfile 里的参数却毫无效果」。要覆盖请用 `docker run -e JAVA_OPTS=...`。
> `.env` 里若还留着 `JAVA_OPTS=` 那一行，它现在**不再被引用**，可以删掉。

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

**手工核对可观测性（V1.4）**：容器健康检查已从 `/api/hello` 换成 actuator 的 readiness 探针，
因为 `/api/hello` 只要 Tomcat 起着就 200 —— **数据库断了它照样报健康**。

```bash
docker compose -f docker-compose.app.yml exec app wget -qO- http://127.0.0.1:8080/actuator/health
# {"groups":["liveness","readiness"],"status":"UP"}     ← 注意：没有组件明细（show-details: never）
```

匿名访问 `/actuator/metrics`、`/actuator/env`、`/actuator/heapdump` **必须不是 200** ——
它们既没被 `exposure.include` 暴露，也**没有**被白名单放行（白名单是精确路径，不是 `/actuator/**`）。

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

## 八、五个刻意的设计决定

**① 镜像不负责编译。** `deploy/Dockerfile` 只把**宿主已打好的 jar** 装进运行时镜像，
不做「多阶段：容器内跑 mvn」。原因：

1. 本项目依赖本机 Maven 本地仓库（`mvn -o` 离线构建），在镜像里重拉一遍全部依赖既慢又要公网；
2. 真相只有一份 —— CI/本地打出的 jar 与镜像里的 jar 是**同一个文件**，
   不会出现「镜像里编出来的东西跟验收过的不是一回事」。

**② 数据库不发布端口、容器非 root。** 数据库只有 app 需要它，`expose` 就够；
应用容器用 `adduser -S mallx` 建的非特权用户运行，逃逸面小一个数量级。

**③ 镜像内再拆一次层（V1.4）。** 镜像里多跑一步
`java -Djarmode=tools -jar app.jar extract --layers --launcher`，把 fat jar 拆成四层分别 COPY：

| 层 | 大小 | 什么时候变 |
|---|---|---|
| `dependencies` | 55.4 MB | 只有第三方依赖变 |
| `spring-boot-loader` | 696 KB | 只有 Spring Boot 升版 |
| `snapshot-dependencies` | 4.1 KB | 本项目没有 SNAPSHOT 第三方依赖 |
| `application` | 549 KB | **每次改代码** |

拆之前 `COPY app.jar` 是**一整层 51 MB** —— 改一行业务代码就要重传 51 MB。实测（`--progress=plain`）：
改一个资源文件后重建，前三个 COPY 全部 `CACHED`，**只有 `application` 层重建**。

> ⚠️ `--launcher` 不能省：不加它 `spring-boot-loader` 层会是**空目录**，
> 镜像里就没有 `org.springframework.boot.loader.launch.JarLauncher` 能把应用拉起来（本机实测）。

**④ JVM 参数容器感知，且只有一处默认值（V1.4）。**
`-Xmx512m` 的问题是两个方向的：容器限额 1G 它只用 512m（浪费一半），限额 256m 它被 OOMKill ——
**两种错都没人会主动发现**。改成 `-XX:MaxRAMPercentage=75`，堆上限跟着 cgroup 限额走。
`docker-compose.app.yml` 里给了 `mem_limit: 384m`，所以这个「感知」是可验证的：
容器内 `MaxHeapSize` = 384MB × 75% = **288 MB**（把百分比改成 25% 就变 96MB —— 对照组）。
★ 参数的**单一来源是镜像 `ENV JAVA_OPTS`**；compose 里刻意不再写同名的键，
否则它会永远覆盖镜像值（这正是 v1.4 之前的状态：改了 Dockerfile 却毫无效果）。

**⑤ 基底是 jlink 生成的最小运行时，不是现成的 JRE 镜像（D43）。**
`eclipse-temurin:21-jre-alpine` 有 **287 MB**，其中 JDK 目录只占 158 MB，
另 **约 129 MB 是构建期工具留下的杂物**（`gnupg` / `font-dejavu` / `fontconfig` / `sqlite` …），
跑 headless 服务用不上。所以：

```text
阶段 1  JDK 镜像里拆层（--layers --launcher）
阶段 2  jdeps 算出真实模块 → jlink 生成 /opt/jre（62 MB）
阶段 3  纯 alpine:3.24 + /opt/jre + apk add tzdata ca-certificates
```

| | 改前 | 改后 |
|---|---|---|
| `docker images` | 393 MB | **229 MB** |
| `docker history` 各层之和 | 269 MB | **≈ 133 MB** |
| 其中的 JRE | JDK 目录 158 MB + 杂物 129 MB | jlink 运行时 **62 MB** + alpine 9 MB |

三个要点：
- **模块清单在构建时算**（`jdeps --print-module-deps`），不抄常量 —— 依赖变了它自己跟上；
  结果会 `echo` 进构建日志，将来漂移时看得见。
- **额外补 `jdk.crypto.ec` 与 `jdk.zipfs`**：静态分析看不到反射用法，
  这是「编译期查不出、运行时才炸」的典型，宁可多带几 MB。
- **运行时基底与构建镜像的 alpine 版本对齐（3.24）**：jlink 产物链接的是构建镜像那份 musl。

> ⚠️ 换基底最容易悄悄弄丢的是「镜像还能不能跑」。本项目为此把 **M1 全链 + 各域套件
> 都跑在镜像上**（不是只冒烟）—— 判据见 `docs/daily/Day-43-镜像再瘦身.md` §四。

---

## 九、缺配置必须启动失败（配置外置的判据）

**判据不是「你有没有设环境变量」，而是「没设的时候服务会不会照样起来」。**

`application-prod.yml` 把 `DB_*` 与 `JWT_SECRET` 写成 `${X}`（**没有** `:兜底`），
但**光这样不够** —— 本机实测踩到过：

```text
docker run -e SPRING_PROFILES_ACTIVE=prod -e DB_HOST=... （故意不给 DB_PASSWORD）
  ⇒ state=running  exit=0  Started MallXApplication in 8.5s     ← 静默起来了！
```

原因：**Spring 的占位符是懒解析的**。Hikari 连接池懒初始化、MyBatis-Plus 启动期不碰库，
于是「没人读 `spring.datasource.password` ⇒ 没人发现它缺 ⇒ 应用带着空密码起来了」，
直到第一次查库才炸。**这恰好是最危险的一类故障：服务看起来是好的。**

⇒ 补了 `ProdConfigGuard`（`mallx-server` 的 `com.mallx.server.config`，只在 `prod` profile 生效）：
启动时**主动读一遍**必填项，任何一项缺失/为空就抛异常 ⇒ 上下文启动失败 ⇒ 进程非零退出。

验证（三条，最后一条是**正向对照**，否则你不知道是不是「什么配置都起不来」）：

```bash
# ① 缺 DB_PASSWORD  -> 必须失败（exit=1，日志含「启动中止」）
docker run --rm -e SPRING_PROFILES_ACTIVE=prod -e DB_HOST=nope -e DB_NAME=nope \
  -e DB_USERNAME=nope -e JWT_SECRET=<48字符> mallx-server:local
# ② 缺 JWT_SECRET / 密钥太短 -> 必须失败（JwtUtil 构造时校验 >=256bit）
# ③ 全部给齐 + DB 连不上 -> 进程【应该活着】（数据库懒连接），只是 readiness 为 DOWN
```

> ★ 顺带说明为什么 Redis / RabbitMQ **不算**必填：它们有降级路径（D40/D41），
> 要求必填只会把「可降级」升级成「起不来」。**必填项的判据是**
> 「错了会**静默地用错值**」（连错库、用公开密钥签 token），
> 而「连不上会明确报错或降级」的不算。

---

## 十、排错速查

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
| 容器 **unhealthy**，但 `/api/hello` 明明 200 | 健康检查已换成 actuator readiness | V1.4 起探针是 `/actuator/health/readiness`：**DB 不可用 ⇒ 503 ⇒ unhealthy**（这是故意的，`/api/hello` 探不出数据库故障）。先修 DB，或 `docker logs app` |
| 探针一直 **401** ⇒ 永远 unhealthy | 探针路径与 `SecurityConfig` 白名单不一致 | 两者的路径必须**逐字符**一致（`/actuator/health`、`/liveness`、`/readiness`、`/info`）。改路径要同时改 `SecurityConfig` 与 `Dockerfile` 的 HEALTHCHECK |
| 改了 `Dockerfile` 的 `JAVA_OPTS` 但容器里没变 | 被 `docker-compose.app.yml` 的 `environment` 覆盖 | V1.4 已删掉 compose 里那行；`/proc/1/cmdline` 可核对实际参数 |
| 改了代码但接口行为没变 | 镜像里的 jar 是旧的 | ★ 镜像**不负责编译**：先 `mvn install` 再 `up -d --build`（§八①） |
| 容器起来就 `NoClassDefFoundError` / `ClassNotFoundException` | jlink 最小运行时**漏了模块**（静态分析看不到反射用法） | 别手写模块清单 —— 回看 `docker build` 日志里的 `jdeps modules:` 行，把它与出错类所属的模块名对照，补进 §八⑤ 的 `--add-modules` |
| `docker build` 报 `error getting credentials - docker-credential-desktop not found` | BuildKit 要拉新基底时找不到 Windows 凭据助手 | 把 `...\DockerDesktop\resources\bin` 加进 `PATH`（§六 坑 2）；**或先把基底 `docker pull` 到本地**（本机实测：预拉之后构建不再需要凭据） |

---

## 十一、安全清单（上线前逐条核对）

- [ ] `JWT_SECRET` 换成随机长串（**不是**仓库里的默认值）
- [ ] `DB_PASSWORD` 换掉
- [ ] `deploy/.env` **没有**提交进仓库（已在 `.gitignore`）
- [ ] 数据库端口没有对公网发布
- [ ] 应用以非 root 运行（`docker inspect -f '{{.Config.User}}' mallx-stack-app-1` → `mallx`）
- [ ] `GET /api/admin/roles` 匿名访问返回 **401** 而不是 200
- [ ] 受限管理员账号（`op_order` / `op_product`）**没有**拿到超管权限
      —— `06-day17-fixtures.sql` 是**可选**的验收夹具，正式环境不要执行
- [ ] ★ V1.4：`SPRING_PROFILES_ACTIVE=prod`（关键项无默认值 + swagger-ui 关闭）
- [ ] ★ V1.4：`ProdConfigGuard` 真的在拦 —— 抽掉一个 `DB_PASSWORD` 试启一次，**必须起不来**（§九）
- [ ] ★ V1.4：actuator 只暴露 `health` / `info`，且 `/actuator/**` **没有**被整体放行：
      匿名打 `/actuator/env`、`/actuator/metrics`、`/actuator/heapdump` 都**不能**是 200
