#!/usr/bin/env bash
# ==============================================================================
# MallX 远端一键部署（带健康检查与失败回滚）
# ------------------------------------------------------------------------------
# 用法（工作目录 = deploy/）：
#     ./deploy.sh 1.4.0        # 部署指定版本
#     ./deploy.sh              # 用 .env 里的 IMAGE_TAG
#
# ★★ 为什么必须有【健康检查 + 自动回滚】两步：
#   `docker compose up -d` 的退出码只代表「容器被创建成功」，不代表「应用能用」。
#   典型翻车：新版本配置写错 ⇒ 容器起来 3 秒后退出 ⇒ compose 依然 exit 0
#   ⇒ 你以为发布成功，实际线上已经 502 了。
#   ⇒ 判据必须是【应用自报的健康】，而且失败要自动退回到上一个版本。
#
# 其它几条纪律（都是踩出来的）：
#   · 镜像 tag 必须具体（禁止 latest），否则「回滚」= 回滚到你正在修的坏版本；
#   · 更新前先 pull，不要在 up 里隐式拉（那样失败点不清晰）；
#   · 数据卷一律【不删】—— down -v 是删库，永远不该出现在部署脚本里。
# ==============================================================================
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
APP_CONTAINER="mallx-app"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m   %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 前置检查
command -v docker >/dev/null || die "docker 不可用"
[ -f "$COMPOSE_FILE" ] || die "找不到 $COMPOSE_FILE（当前目录应为 deploy/）"
[ -f .env ] || die "缺少 .env：先 cp .env.prod.example .env 并逐项填写"

NEW_TAG="${1:-}"
if [ -z "$NEW_TAG" ]; then
  NEW_TAG="$(grep -E '^IMAGE_TAG=' .env 2>/dev/null | cut -d= -f2- || true)"
fi
[ -n "$NEW_TAG" ] || die "未指定版本：./deploy.sh <tag>，或在 .env 里写 IMAGE_TAG"
case "$NEW_TAG" in
  latest|"") die "镜像 tag 禁止使用 latest（无法回滚、无法回答『线上是哪一版』）" ;;
esac
export IMAGE_TAG="$NEW_TAG"

# ★ 回滚点 = **当前真正在跑**的那个镜像，不是 .env 里写的那个
#   （.env 可能已经被改过但还没发布 —— 拿它当回滚点会退到错误的版本）
OLD_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$APP_CONTAINER" 2>/dev/null || true)"
OLD_TAG="${OLD_IMAGE##*:}"

log "目标版本：$NEW_TAG"
[ -n "$OLD_TAG" ] && [ "$OLD_TAG" != "$NEW_TAG" ] && log "回滚点：$OLD_TAG" || true

# ---------------------------------------------------------------- 1) pull
log "拉取镜像 ${IMAGE_REGISTRY:-ghcr.io/qiu-rong/mallx-server}:$NEW_TAG"
if ! docker compose -f "$COMPOSE_FILE" pull app; then
  die "pull 失败 —— 网络问题，或该 tag 在 registry 里不存在（release 流水线跑完了吗？）"
fi

# ---------------------------------------------------------------- 2) up -d
log "滚动更新（compose 会先起新容器，再停旧的）"
docker compose -f "$COMPOSE_FILE" up -d --no-build app

# ---------------------------------------------------------------- 3) 等健康
# ★ 判据用容器的 health status —— 它来自 Dockerfile 里那条
#   actuator readiness 探针（DB 连不上就 DOWN），比 curl /api/hello 有意义得多。
log "等待应用健康（最多 ${WAIT_SECONDS}s，探针 = /actuator/health/readiness）"
deadline=$(( $(date +%s) + WAIT_SECONDS ))
status=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$APP_CONTAINER" 2>/dev/null || echo missing)"
  case "$status" in
    healthy) break ;;
    exited|dead) break ;;
  esac
  sleep 3
done

if [ "$status" = "healthy" ]; then
  log "✅ 部署完成：$NEW_TAG"
  docker inspect -f '  镜像   {{.Config.Image}}' "$APP_CONTAINER"
  docker inspect -f '  运行者 {{.Config.User}}（应为非 root）' "$APP_CONTAINER"
  exit 0
fi

# ---------------------------------------------------------------- 4) 失败回滚
warn "应用未进入 healthy（状态=$status），开始回滚"
echo "---- 应用日志尾部 ----"
docker compose -f "$COMPOSE_FILE" logs --tail=40 app || true
echo "----------------------"

if [ -n "${OLD_TAG:-}" ] && [ "$OLD_TAG" != "$NEW_TAG" ]; then
  warn "回滚到 $OLD_TAG"
  IMAGE_TAG="$OLD_TAG" docker compose -f "$COMPOSE_FILE" up -d --no-build app
  sleep 5
  back="$(docker inspect -f '{{.State.Health.Status}}' "$APP_CONTAINER" 2>/dev/null || echo missing)"
  [ "$back" = "healthy" ] && warn "已回滚到 $OLD_TAG（healthy）" || warn "回滚后仍不健康（$back）—— 需要人工介入"
else
  warn "没有可用的回滚点（首次部署），保持现状由人工处理"
fi

die "部署失败：${NEW_TAG}"
