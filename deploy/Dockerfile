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
#     拆开后，各层的【变更频率】才算分开（实测值）：
#         dependencies           55.4 MB   仅第三方依赖变化时重建
#         spring-boot-loader     696  KB   仅 Spring Boot 升版时重建
#         snapshot-dependencies  4.1  KB   本项目无 SNAPSHOT 第三方依赖
#         application            549  KB   ← 每次改代码只有这一层变
#
#   ★ D43：基底从 `eclipse-temurin:21-jre-alpine`（287 MB）换成
#     「jlink 最小运行时 + 纯 alpine」。两个杠杆，都有实测支撑：
#       ① 那个基底里 JDK 本体只有 158 MB，另有 **约 129 MB 是构建期工具留下的杂物**
#          （`gnupg` / `font-dejavu` / `fontconfig` / `sqlite` / `coreutils` …）——
#          跑一个 headless 服务根本用不上；
#       ② JDK 目录 158 MB 里大部分是本项目用不到的模块。`jdeps` 算出真实只需要
#          15 个模块，`jlink` 产出的运行时 **62 MB**。
#     `ldd` 实测 java / libjvm **只依赖 musl 与 libjli**（不需要 libstdc++、freetype），
#     所以运行时可以落在纯 alpine 上。
#     ⚠️ 运行时基底用 `alpine:3.24` 与构建镜像的 alpine 版本【对齐】：jlink 的产物链接的是
#        构建镜像里那份 musl，跨大版本混用有 ABI 风险，省下的那几 MB 不值当。
#
#   构建两步（在仓库根目录执行）：
#     mvn -o -f backend/mallx/pom.xml install -DskipTests        # ① 打 jar
#     docker build -f deploy/Dockerfile -t mallx-server:local .  # ② 拆层 + jlink + 装镜像
#   或者直接交给 compose：`docker compose -f deploy/docker-compose.app.yml up -d --build`
#
# ★ 本文件刻意【不写】`# syntax=docker/dockerfile:1` 那行：
#   它会让构建器先去拉一个 frontend 镜像（docker/dockerfile:1）——
#   在没有外网/凭据助手缺失的机器上，报错会出现在「解析 frontend」这一步，
#   而错误信息长得像「基础镜像拉不下来」，排查方向整个跑偏（本项目实测踩过）。
#   本文件只用到最基础的 COPY/ENV/HEALTHCHECK，内置 frontend 完全够。
# ==============================================================================

# ---------- 阶段 1：拆层（产物只给下面 COPY，不进最终镜像） ----------
FROM eclipse-temurin:21-jdk-alpine AS layers

WORKDIR /build
COPY backend/mallx/mall-server/target/mall-server-0.0.1-SNAPSHOT.jar /build/app.jar

# ★★ `--launcher` 不能省。不加它 spring-boot-loader 层会抽出【空目录】，
#    最终镜像里就没有 org.springframework.boot.loader.launch.JarLauncher 能把应用拉起来。
#    （本机实测：少了它 `docker build` 仍然报成功，但镜像根本跑不起来。）
RUN java -Djarmode=tools -jar /build/app.jar extract --layers --launcher --destination /build/out \
 && rm -f /build/app.jar

# ---------- 阶段 2：用 jdeps 算模块清单，jlink 产最小运行时 ----------
FROM eclipse-temurin:21-jdk-alpine AS jre

COPY --from=layers /build/out /build/out

# ★ 模块清单【在构建时算】，不是抄一份常量：依赖变了它会自己跟上。
#   `--ignore-missing-deps`：fat jar 里有些可选依赖探测不到，不忽略会直接报错退出。
#   算完把结果打进构建日志（将来清单漂移时，日志里看得见）。
# ★ 额外补两个 jdeps 静态分析看不到的：
#     jdk.crypto.ec —— TLS 的椭圆曲线套件（HTTPS / PostgreSQL sslmode=require 会用到）
#     jdk.zipfs    —— 部分库按 zip 文件系统读资源
#   这是「编译期查不出、运行时才炸」的典型，宁可多带几 MB。
RUN set -eux; \
    CP="$(find /build/out -name '*.jar' | tr '\n' ':')"; \
    MODS="$(jdeps --print-module-deps --ignore-missing-deps --multi-release 21 \
              --class-path "$CP" /build/out/application/BOOT-INF/classes)"; \
    echo "jdeps modules: $MODS"; \
    jlink --add-modules "$MODS,jdk.crypto.ec,jdk.zipfs" \
          --strip-debug --no-man-pages --no-header-files --compress=zip-6 \
          --output /opt/jre; \
    du -sh /opt/jre; \
    /opt/jre/bin/java -version

# ---------- 阶段 3：运行时（纯 alpine + 最小 JRE） ----------
# alpine:3.24 与构建镜像同版本（见文件头 ⚠️）
FROM alpine:3.24

LABEL org.opencontainers.image.title="MallX server" \
      org.opencontainers.image.description="MallX 企业级电商后端（模块化单体，Spring Boot 4 + MyBatis-Plus + PostgreSQL）" \
      org.opencontainers.image.version="0.0.1-SNAPSHOT"

# tzdata：时区（日志时间戳）
# ca-certificates：出网 TLS 校验
RUN apk add --no-cache tzdata ca-certificates \
 && addgroup -S mallx && adduser -S -G mallx mallx

COPY --from=jre /opt/jre /opt/jre
ENV JAVA_HOME=/opt/jre \
    PATH=/opt/jre/bin:$PATH

WORKDIR /app

# ★ 这四行 COPY 的【顺序不能调】：越靠上的层越稳定。
#   Docker 的层缓存按「指令 + 内容」命中，把稳定的放前面，
#   改一行业务代码时才不会连累 55 MB 的依赖层（这正是分层的目的）。
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
#   ★ wget 用基础镜像自带 busybox 的（不额外装包），且容器非 root，探针也以 mallx 身份跑。
HEALTHCHECK --interval=10s --timeout=3s --start-period=45s --retries=12 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/actuator/health/readiness || exit 1
