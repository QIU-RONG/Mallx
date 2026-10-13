#!/usr/bin/env bash
# ==============================================================================
# 生产库备份（pg_dump + 保留最近 N 份）
# ------------------------------------------------------------------------------
# 用法（工作目录 = deploy/）：
#     ./backup-db.sh                # 备份到 ./backups/
#     KEEP=30 ./backup-db.sh        # 保留最近 30 份（默认 14）
#
# ★★ 为什么备份脚本要单独存在（而不是写在部署脚本里）：
#   它们触发时机完全不同 —— 备份要**定时**（cron），部署是**事件驱动**。
#   塞在一起的结果是：只有部署时才顺手备份，平时不备，而事故偏偏发生在不部署的日子。
#
# ★ 为什么用 pg_dump 的 custom 格式（-Fc）而不是纯 SQL：
#   custom 格式支持**选择性恢复**（只还原某一张表）。真出事时你要的几乎从不是
#   「整个库回到三天前」，而是「把 refunds 表里那几行捞回来」。
#
# ⚠️ 没验证过的备份 = 没有备份。定期跑一次 restore 到临时库（见文件末尾说明）。
# ==============================================================================
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
CONTAINER="mallx-postgres-prod"
DB_NAME="${DB_NAME:-mallx}"
DB_USER="${DB_USERNAME:-mallx}"
KEEP="${KEEP:-14}"
DIR="${BACKUP_DIR:-./backups}"

mkdir -p "$DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DIR/mallx-$STAMP.dump"

printf '[backup] 导出 %s -> %s\n' "$DB_NAME" "$OUT"

# ★ 走 `exec -T` 在容器里跑 pg_dump，再把流接到宿主文件：
#   不落一份在容器里，容器删了备份也没了。
docker compose -f "$COMPOSE_FILE" exec -T "$CONTAINER" \
  pg_dump -U "$DB_USER" -Fc -d "$DB_NAME" > "$OUT"

SIZE="$(du -h "$OUT" | cut -f1)"
printf '[backup] 完成：%s (%s)\n' "$OUT" "$SIZE"

# ★ 保留最近 KEEP 份：ls 按名字倒序（时间戳在名里 ⇒ 字典序=时间序），跳过前 KEEP 个
OLD="$(ls -1 "$DIR"/mallx-*.dump 2>/dev/null | sort -r | tail -n +$((KEEP + 1)) || true)"
if [ -n "$OLD" ]; then
  printf '%s\n' "$OLD" | while read -r f; do
    printf '[backup] 清理旧备份：%s\n' "$f"
    rm -f "$f"
  done
fi

cat <<'TIP'

[backup] 提醒：没验证过的备份 = 没有备份。建议每月做一次恢复演练：

    docker compose -f docker-compose.prod.yml exec -T postgres createdb -U mallx mallx_restore_test
    docker compose -f docker-compose.prod.yml exec -T postgres pg_restore -U mallx -d mallx_restore_test < backups/mallx-<时间戳>.dump
    docker compose -f docker-compose.prod.yml exec -T postgres psql -U mallx -d mallx_restore_test -c "SELECT count(*) FROM permissions"   # 期望 46
    docker compose -f docker-compose.prod.yml exec -T postgres dropdb -U mallx mallx_restore_test

TIP
