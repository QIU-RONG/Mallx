# Day 42 · V1.4 云部署（前半段）

> 版本规划里 V1.4 = 「云部署：镜像瘦身、配置外置、可观测性」。
> 本次做**本地就能验证完**的那三条；**远端托管**（CI/CD、域名、HTTPS、日志采集）需要云端账号，
> 留在 V1.4 后半段 —— 「容器化」（V1.3 已完成）与「云部署」是两件事，别混。

---

## 一、先量后改：基线 vs 结果

| 指标 | 改前 | 改后 |
|---|---|---|
| 镜像体积 | 434 MB | **393 MB** |
| 层数 | 9 | 11 |
| ★ 改一行业务代码要重建的层 | **51.1 MB**（整个 fat jar 一层） | **549 KB**（`application` 层） |
| 容器内堆上限 | 写死 `-Xmx512m`（**无视**容器限额） | 按 cgroup 限额 ×75% = **288 MB** |
| 容器健康检查 | `/api/hello`（**DB 断了照样报健康**） | `/actuator/health/readiness`（DB 不可用 ⇒ 503） |
| prod 缺 `DB_PASSWORD` | **静默启动成功**（8.5s 后 Started） | **exit=1 启动中止** |
| 容器内启动耗时 | — | 8.6 s |

> ⚠️ 434 → 393 MB 这 41 MB **不能全记在分层头上**：基底镜像
> `eclipse-temurin:21-jre-alpine` 同期也升过版（现在是 JDK 21.0.12 + Alpine 3.24）。
> 真正可归因于本次改动的是**层粒度**那一行 —— 它是「改一行代码要重传多少」的直接答案。

---

## 二、镜像分层：拆的是「变更频率」，不是「体积」

`COPY app.jar` 原来是一整层 51 MB。用 Spring Boot 官方分层拆开（`-Djarmode=tools extract --layers --launcher`）
之后，各层的变更频率才真正分开：

| 层 | 实测大小 | 什么时候会变 |
|---|---|---|
| `dependencies` | 55.4 MB | 只有第三方依赖变 |
| `spring-boot-loader` | 696 KB | 只有 Spring Boot 升版 |
| `snapshot-dependencies` | 4.1 KB | 本项目没有 SNAPSHOT 第三方依赖 |
| `application` | **549 KB** | **每次改代码** |

**实测**（改一个资源文件 → 重新打 jar → `docker build --progress=plain`）：

```text
#11 [stage-1 4/7] COPY .../dependencies/            ./   → CACHED
#12 [stage-1 5/7] COPY .../spring-boot-loader/      ./   → CACHED
#13 [stage-1 6/7] COPY .../snapshot-dependencies/   ./   → CACHED
#14 [stage-1 7/7] COPY .../application/             ./   → （重建）
```

★ **`--launcher` 不能省**（本机实测）：不加它，`spring-boot-loader` 层会抽出**空目录**，
镜像里就没有 `org.springframework.boot.loader.launch.JarLauncher` 能把应用拉起来。
★ 抽取布局在 Boot 4 与老文档里的 `layertools` 不同：`--launcher` 模式下得到的是
`dependencies/`、`spring-boot-loader/`、`snapshot-dependencies/`、`application/` 四个目录，
启动方式改为 `java org.springframework.boot.loader.launch.JarLauncher`（不再是 `-jar`）。

---

## 三、容器感知 JVM（带对照组）

`-Xmx512m` 的问题是**双向**的：容器限额调到 1G 它还是只用 512m（浪费一半）；
调到 256m 它又会被 OOMKill。两种错都没人会主动发现。改成 `-XX:MaxRAMPercentage=75` 后，
堆上限跟着 cgroup 限额走。`docker-compose.app.yml` 里给了 `mem_limit: 384m`，于是这件事**可验证**：

| `-XX:MaxRAMPercentage` | `MaxHeapSize` | 换算 |
|---|---|---|
| **75**（新默认） | 301989888 | **288 MB** = 384 MiB × 0.75 |
| 25（JVM 自带默认） | 132120576 | 126 MB |

同一容器、只改百分比 ⇒ **对照组**。两边都落在 384 MiB 量级内，说明 JVM 读的是
**cgroup 限额**而不是宿主机内存（若读宿主内存，25% 会算出几个 GB）。

> 25% 那一栏不是简单算出来的 96 MB —— JVM ergonomics 另有下限/取整规则，本次没有深究。
> 这里要证的只是「百分比这个旋钮真的作用在容器限额上」，不打算把公式逆出来。

★ **为什么必须改**：本次同时给容器加了 `mem_limit: 384m`。如果沿用写死的 `-Xmx512m`，
**堆上限比容器内存限额还大** ⇒ 迟早 OOMKill（而且是压测时才发现的偶发故障）。

---

## 四、配置外置：为什么「不给默认值」还不够

### 4.1 实测打脸

`application-prod.yml` 里把关键项写成 `${DB_PASSWORD}`（**没有** `:兜底`），本以为缺失就会启动失败。
实测：

```text
docker run -e SPRING_PROFILES_ACTIVE=prod -e DB_HOST=nope ...（故意不给 DB_PASSWORD）
  ⇒ state=running  exit=0  Started MallXApplication in 8.572 seconds
```

**原因**：Spring 的占位符是**懒解析**的 —— 只有真有人去读 `spring.datasource.password` 时才解析。
Hikari 连接池懒初始化、MyBatis-Plus 启动期不碰数据库 ⇒
「没人读 ⇒ 没人报错 ⇒ 应用带着空密码起来了」，直到第一次查库才炸。
**这恰好是最危险的一类故障：服务看起来是好的。**

> 对照：`mallx.jwt.secret` 由 `JwtUtil` 在**构造时**读取，所以它确实会快速失败
> （实测：密钥太短 → `Failed to instantiate JwtUtil` → exit=1）。

### 4.2 补上闸门

`ProdConfigGuard`（`com.mallx.server.config`，`@Profile("prod")`）在启动时**主动读一遍**必填项，
任何一项解析失败或为空 ⇒ 构造器抛异常 ⇒ 上下文启动失败 ⇒ 进程非零退出。
判据从「人去日志里找有没有那句话」变成**退出码**。

### 4.3 必填项的判据

> **错了会「静默地用错值」的才必填**（连错库、用公开密钥签 token）；
> **错了会明确报错或只是降级的，不算** —— 要求它们必填只会把「可降级」升级成「起不来」。

所以 `DB_*` 与 `JWT_SECRET` 必填，Redis / RabbitMQ 不填（D40/D41 已做降级）。

### 4.4 三条验证（第 ③ 条是正向对照，没有它就等于什么都没测）

| # | 场景 | 期望 | 实测 |
|---|---|---|---|
| ① | 缺 `DB_PASSWORD` | 起不来 | **exit=1**（修复前：exit=0 + 正常启动） |
| ② | `JWT_SECRET` 太短 | 起不来 | exit=1（`JwtUtil` 构造校验 ≥256 bit） |
| ③ | 全给齐、DB 连不上 | **应该活着** | `Started MallXApplication` ✅ |

---

## 五、可观测性：探针语义与白名单

- 新增 `spring-boot-starter-actuator`（只声明在 `mall-server`，它是**运行期**关注点）。
- **只暴露 `health` / `info`**，且 `show-details: never` ⇒ 匿名只看到 `UP`/`DOWN`，
  看不到「哪个组件挂了、报了什么错」。实测响应体：`{"groups":["liveness","readiness"],"status":"UP"}`。
- `probes.enabled: true` ⇒ 多出 `/actuator/health/liveness` 与 `/readiness`，**语义不同**：
  - `liveness` = 进程还活着吗 → 挂了**重启容器**
  - `readiness` = 现在能接流量吗 → 依赖没就绪就**摘掉**（不重启）
  容器里用的是 **readiness**（compose 的 `service_healthy` 语义正是「能接流量」）。
- **健康检查换成 readiness，这条改动本身就是在修一个真 bug**：`/api/hello` 只要
  Tomcat 起着就 200 —— 数据库断了它照报健康，compose 的 `depends_on: service_healthy` 会被骗过去。
- **Redis / RabbitMQ 不算进 health**：它们是可选依赖（有降级路径），算进去会把
  「服务其实可用」误报成 DOWN，于是编排层摘流量甚至重启容器 —— **把可控降级升级成不可用**。
- 白名单继续用**精确路径**：`/actuator/health`、`/liveness`、`/readiness`、`/info`。
  ⚠️ **绝不能写 `/actuator/**`** —— 那会把 `metrics` / `env` / `configprops` / `heapdump` 一起静默公开。

**匿名对照（实测）**：

| 路径 | 结果 | 说明 |
|---|---|---|
| `/actuator/health`（含 liveness/readiness/info） | 200 | 白名单精确放行 |
| `/actuator/metrics` | **401** | 未暴露 + 未放行 |
| `/actuator/env` | **401** | 同上 |
| `/api/cart`、`/api/admin/dashboard` | **401** | 业务端点鉴权未被削弱 |

> ★ 注意 `/actuator/metrics` 拿到的是 **401 而不是 404**：Security 过滤器链**先于** MVC 路由，
> 所以「路径根本没有 handler」也会先被鉴权拦下。这与本项目 Day 18/25 的结论同源
> （白名单是「路径 + 方法」粒度，而 405/404 这类协议层结果同样先过 Security）。

---

## 六、回归证据：跑在**镜像**上

没另起宿主 jar，而是**用构建出的镜像**起了一个实例（`SPRING_PROFILES_ACTIVE=prod`，
`DB_HOST=host.docker.internal` 接开发库 5434），端口 8080，然后跑 M1：

| 套件 | 结果 |
|---|---|
| M1 全链路回归 | **245/245，M1 REGRESSION: OK**（(a)(a2)(b)(c)(d) 全 YES，(c) 数据库回基线 YES） |
| `day23-rbac-verify.py` | **91/91 PASS** |
| `day20-coupon-verify.py` | **82/82 PASS** |

⇒ 改 `SecurityConfig`（加 actuator 白名单）**没有**削弱任何既有鉴权。

---

## 七、CI：把「镜像能不能构建」纳入门禁

`ci` job 末尾新增一步（复用上面 `mvn install` 已产出的 jar，不重复编译）：

1. `docker build` 分层镜像；
2. **断言启动器类真的在镜像里** —— 少 `--launcher` 时 `docker build` 仍然**成功**，
   但镜像根本起不来（构建成功 ≠ 能跑）；
3. **prod 缺 `DB_PASSWORD` 必须非零退出**（`timeout 90` 区分「失败」与「一直跑」：rc=124 视为失败）；
4. **正向对照**：必填项给齐必须能启动 —— 没有它，第 3 条的「通过」可能只是因为镜像本身是坏的。

四个命令都在本机原样跑过一遍再推（「CI 改动先在本地把命令实跑一遍」）。

---

## 八、本次踩到的坑

| 坑 | 现象 | 判据 / 解法 |
|---|---|---|
| ★★ **PS 5.1 读无 BOM 的 `.ps1` 会按 GBK 解码** | 脚本里只要**字符串**含中文就报 `字符串缺少终止符: "`，看起来像自己写错了引号 | 给 `.ps1` 加 UTF-8 **BOM**；只在注释里放中文会侥幸过关（误导性极强） |
| ★★ **Docker Desktop 被沙箱拦** | `C:\Users\TIE\.docker\daemon.json` 写被拒 ⇒ 引擎永远起不来 | 用 `explorer.exe <Docker Desktop.exe>` **脱沙箱**启动 |
| ★ **占位符懒解析** | 「不给默认值」≠「缺失即失败」 | 启动时主动读一遍（`ProdConfigGuard`）；判据看**退出码** |
| ★ **同一参数两处默认值** | `Dockerfile` 改了 `JAVA_OPTS`，容器里还是旧值 | compose 的 `environment` 会覆盖镜像 `ENV` ⇒ 删掉 compose 里那行，单一来源放镜像；核对 `/proc/1/cmdline` |
| bash 通道访问不到 Docker 命名管道 | `docker` 在 Bash 里报 `npipe ... cannot find the file`，PS 里正常 | Docker 相关一律走 PowerShell |
| 本机 `jcmd` 不在 JRE 镜像里 | 想看 PID 1 的堆参数却没有工具 | 退而求其次：`/proc/1/cmdline`（证明参数）+ 同容器内另起 JVM 用 `PrintFlagsFinal`（证明换算规则），并配对照组 |

---

## 九、下一步（V1.4 后半段）

- 远端托管：CI/CD 到云、域名 + HTTPS、日志采集与告警。
- 镜像进一步瘦身：目前 393 MB 里基底镜像占大头（约 212 MB），
  换更小的运行时（jlink 定制 JRE / distroless）前先量收益；
- `dependencies` 层 55.4 MB 仍是热层 —— 若要再压，考虑依赖瘦身而不是换基底。
