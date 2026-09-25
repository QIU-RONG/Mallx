# ==============================================================================
# MallX 应用镜像（mall-server）
# ------------------------------------------------------------------------------
# ★ 本镜像【不负责编译】—— 它只把已经打好的 fat jar 装进运行时镜像。
#
#   为什么不是「多阶段：镜像内跑 mvn」？
#     ① 本项目的构建依赖本机 Maven 本地仓库（`mvn -o` 离线构建），
#        在镜像里重新拉一遍全部依赖既慢又需要公网；
#     ② 真相只有一份：CI/本地打出的 jar 与镜像里的 jar 是【同一个文件】，
#        不会出现「镜像里编出来的东西跟验收过的不是一回事」。
#
#   构建两步（在仓库根目录执行）：
#     mvn -o -f backend/mallx/pom.xml install -DskipTests      # ① 打 jar
#     docker build -f deploy/Dockerfile -t mallx-server:local .  # ② 装进镜像
#   或者直接交给 compose：`docker compose -f deploy/docker-compose.app.yml up -d --build`
#
# ★ 本文件刻意【不写】`# syntax=docker/dockerfile:1` 那行：
#   它会让构建器先去拉一个 frontend 镜像（docker/dockerfile:1）——
#   在没有外网/凭据助手缺失的机器上，报错会出现在「解析 frontend」这一步，
#   而错误信息长得像「基础镜像拉不下来」，排查方向整个跑偏（本项目实测踩过）。
#   本文件只用到最基础的 COPY/ENV/HEALTHCHECK，内置 frontend 完全够。
# ==============================================================================

FROM eclipse-temurin:21-jre-alpine

LABEL org.opencontainers.image.title="MallX server" \
      org.opencontainers.image.description="MallX 企业级电商后端（模块化单体，Spring Boot 4 + MyBatis-Plus + PostgreSQL）" \
      org.opencontainers.image.version="0.0.1-SNAPSHOT"

# ★ 非 root 运行：容器里跑的进程不该有 root 权限（逃逸面小一个数量级）
RUN addgroup -S mallx && adduser -S -G mallx mallx

WORKDIR /app

# jar 由宿主的 `mvn install` 产出；路径相对【构建上下文 = 仓库根】
COPY backend/mallx/mall-server/target/mall-server-0.0.1-SNAPSHOT.jar /app/app.jar
RUN chown -R mallx:mallx /app
USER mallx

# 内存参数走 JAVA_OPTS，方便 `docker run -e JAVA_OPTS=...` 覆盖而不改镜像
ENV JAVA_OPTS="-Xmx512m -XX:MaxMetaspaceSize=192m -XX:+UseSerialGC"

# ★ exec 不能省：否则 PID 1 是 sh，SIGTERM 收不到 → `docker stop` 只能等超时再 kill
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/app.jar"]

EXPOSE 8080

# /api/hello 在 SecurityConfig 白名单里 ⇒ 探测不需要 token
# （换个受保护端点做健康检查，会让健康检查拿到 401 而永远 unhealthy）
HEALTHCHECK --interval=10s --timeout=3s --start-period=45s --retries=12 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/api/hello || exit 1
