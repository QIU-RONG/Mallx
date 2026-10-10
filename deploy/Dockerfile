# ==============================================================================
# MallX 应用镜像（mall-server）
# ------------------------------------------------------------------------------
# ★ 本镜像【不负责编译】—— 它把宿主/CI 已经打好的 fat jar 拆成分层，再装进运行时镜像。
#
#   为什么不是「多阶段：镜像内跑 mvn」？
#     ① 本项目的构建依赖本机 Maven 本地仓库（`mvn -o` 离线构建），
#        在镜像里重新拉一遍全部依赖既慢又需要公网；
#     ② 真相只有一份：CI/本地打出的 jar 与镜像里的 jar 是【同一个文件】，
#        不会出现「镜像里编出来的东西跟验收过的不是一回事」。
#
#   ★ V1.4 · D42：为什么还要在镜像里再拆一次层？
#     拆之前，`COPY app.jar` 是**一层 51 MB**：改一行业务代码 = 整层失效 =
#     重新上传 51 MB。按 Spring Boot 官方分层（`-Djarmode=tools extract --layers --launcher`）
#     拆开后，各层的【变更频率】才算分开（实测值，见 docs/daily/Day-42）：
#         dependencies           51   MB   仅第三方依赖变化时重建
#         spring-boot-loader     637  KB   仅 Spring Boot 升版时重建
#         snapshot-dependencies  0         本项目无 SNAPSHOT 第三方依赖
#         application            467  KB   ← 每次改代码只有这一层变
#
#   构建两步（在仓库根目录执行）：
#     mvn -o -f backend/mallx/pom.xml install -DskipTests        # ① 打 jar
#     docker build -f deploy/Dockerfile -t mallx-server:local .  # ② 拆层 + 装镜像
#   或者直接交给 compose：`docker compose -f deploy/docker-compose.app.yml up -d --build`
#
# ★ 本文件刻意【不写】`# syntax=docker/dockerfile:1` 那行：
#   它会让构建器先去拉一个 frontend 镜像（docker/dockerfile:1）——
#   在没有外网/凭据助手缺失的机器上，报错会出现在「解析 frontend」这一步，
#   而错误信息长得像「基础镜像拉不下来」，排查方向整个跑偏（本项目实测踩过）。
#   本文件只用到最基础的 COPY/ENV/HEALTHCHECK，内置 frontend 完全够。
# ==============================================================================

# ---------- 阶段 1：把 fat jar 拆成层（中间产物，不进最终镜像） ----------
FROM eclipse-temurin:21-jre-alpine AS layers

WORKDIR /build
COPY backend/mallx/mall-server/target/mall-server-0.0.1-SNAPSHOT.jar /build/app.jar

# ★★ `--launcher` 不能省。不加它的话 spring-boot-loader 层会抽出【空目录】，
#    最终镜像里就没有任何东西能把应用拉起来（org.springframework.boot.loader.launch.JarLauncher
#    正属于这一层）。这是本机实测出来的，不是照文档抄的。
RUN java -Djarmode=tools -jar /build/app.jar extract --layers --launcher --destination /build/out \
 && rm -f /build/app.jar

# ---------- 阶段 2：运行时 ----------
FROM eclipse-temurin:21-jre-alpine

LABEL org.opencontainers.image.title="MallX server" \
      org.opencontainers.image.description="MallX 企业级电商后端（模块化单体，Spring Boot 4 + MyBatis-Plus + PostgreSQL）" \
      org.opencontainers.image.version="0.0.1-SNAPSHOT"

# ★ 非 root 运行：容器里跑的进程不该有 root 权限（逃逸面小一个数量级）
RUN addgroup -S mallx && adduser -S -G mallx mallx

WORKDIR /app

# ★ 这四行 COPY 的【顺序不能调】：越靠上的层越稳定。
#   Docker 的层缓存按「指令 + 内容」命中，把稳定的放前面，
#   改一行业务代码时才不会连累 51 MB 的依赖层（这正是分层的目的）。
COPY --from=layers --chown=mallx:mallx /build/out/dependencies/          ./
COPY --from=layers --chown=mallx:mallx /build/out/spring-boot-loader/    ./
COPY --from=layers --chown=mallx:mallx /build/out/snapshot-dependencies/ ./
COPY --from=layers --chown=mallx:mallx /build/out/application/           ./

USER mallx

# ★ V1.4：JVM 参数改成【容器感知】。原来写死 `-Xmx512m` 的问题是双向的：
#   容器限额调到 1G 它还是只用 512m（浪费一半），调到 256m 它又会被 OOMKill ——
#   两种错都不会有人主动发现。`-XX:MaxRAMPercentage` 让 JVM 按 cgroup 限额自己算堆上限
#   （75% 是官方推荐起点），容器限额一变，堆就跟着变。
#   仍然走 JAVA_OPTS 环境变量，方便 `docker run -e JAVA_OPTS=...` 覆盖而不必改镜像。
# ★ SerialGC + C1-only 编译（TieredStopAtLevel=1）：本服务是 IO 密集的 CRUD，
#   分层编译换来的峰值吞吐收益远小于它的启动/预热成本 —— 而本项目的验收脚本经常重启应用。
ENV JAVA_OPTS="-XX:MaxRAMPercentage=75 -XX:MaxMetaspaceSize=192m -XX:+UseSerialGC -XX:TieredStopAtLevel=1"

# ★ exec 不能省：否则 PID 1 是 sh，SIGTERM 收不到 → `docker stop` 只能等超时再 kill
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS org.springframework.boot.loader.launch.JarLauncher"]

EXPOSE 8080

# ★ V1.4：健康检查从 `/api/hello` 换成 actuator 的 **readiness** 探针。这个区别是真实的：
#   `/api/hello` 只要 Tomcat 起来了就 200 —— **数据库断了它照样报健康**，
#   compose 里的 `depends_on: condition: service_healthy` 会被它骗过去。
#   readiness 走 HealthEndpoint：DB 不可用 ⇒ HTTP 503 ⇒ 容器真的变 unhealthy。
#   ⚠️ 探针路径必须与 SecurityConfig 的白名单【逐字符一致】，否则健康检查拿到 401
#      会永远 unhealthy（本项目 Day 25 踩过同款：白名单里漏了 /error）。
#   ⚠️ 刻意用 readiness 而不是 liveness：compose 的 service_healthy 语义是「能接流量」，
#      对应 readiness；liveness 的语义是「进程该不该被重启」，留给会区分这两种动作的编排层。
HEALTHCHECK --interval=10s --timeout=3s --start-period=45s --retries=12 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/actuator/health/readiness || exit 1
