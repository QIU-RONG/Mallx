#!/usr/bin/env bash
# Day 14 / Step 4 —— 最小验证：MyBatis 能不能接住 PostgreSQL 的 UPDATE ... RETURNING
#
# 为什么要有这个脚本：
#   inventory_logs 流水表要记 before_stock / after_stock，而「更新后的库存」
#   只有 RETURNING 能一次拿到。文档把「RETURNING 在 MyBatis 里能不能用」标成
#   「需要实测确认」—— 这是第 4 步唯一可能推翻整体设计的地方，所以先单独验掉。
#
# 零副作用：
#   全程跑在【一个不提交的事务】里，结尾 rollback。数据库账目零改动。
#   （已验证：跑完 inventories 的 total = available + locked + sold 不变。）
#
# 用法：
#   bash backend/loadtest/day14-returning-probe/run.sh
#   依赖 jar 路径可用环境变量覆盖：MB_JAR / PG_JAR / SLF_JAR / JAVA_BIN / JAVAC_BIN
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"

# ★ 坑：Git Bash 会把 /d/MallX/... 这类 POSIX 路径「自动转换」成 \d\MallX\...
#   （转换失败）再交给 Windows 版 javac/java，于是报「找不到文件」。
#   所以凡是传给 JVM 的路径，一律先转成 Windows 形式（D:/MallX/...）。
if command -v cygpath >/dev/null 2>&1; then
    HERE_WIN="$(cygpath -m "$HERE")"
else
    HERE_WIN="$HERE"
fi
CLASSDIR="$HERE_WIN/classes"
SRCDIR="$HERE_WIN/src/mbprobe"
RESDIR="$HERE_WIN/res"

MB="${MB_JAR:-C:/Users/TIE/.m2/repository/org/mybatis/mybatis/3.5.19/mybatis-3.5.19.jar}"
PG="${PG_JAR:-C:/Users/TIE/.m2/repository/org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar}"
SLF="${SLF_JAR:-C:/Users/TIE/.m2/repository/org/slf4j/slf4j-api/1.7.36/slf4j-api-1.7.36.jar}"
JAVA_BIN="${JAVA_BIN:-/d/java/bin/java}"
JAVAC_BIN="${JAVAC_BIN:-/d/java/bin/javac}"

CP="$MB;$PG;$SLF"

rm -rf "$HERE/classes"
mkdir -p "$HERE/classes"

"$JAVAC_BIN" -encoding UTF-8 -cp "$CP" -d "$CLASSDIR" \
    "$SRCDIR/ProbeMapper.java" \
    "$SRCDIR/Probe.java" || exit 1

# MyBatis 通过 classpath 找 mybatis-config.xml / ProbeMapper.xml
cp "$HERE"/res/*.xml "$HERE/classes/"

"$JAVA_BIN" -Dfile.encoding=UTF-8 -cp "$CLASSDIR;$CP" mbprobe.Probe
