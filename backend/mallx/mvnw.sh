#!/usr/bin/env bash
# MallX 本地 Maven 启动脚本（Windows Git Bash 环境用）
# 背景：本机 mvn sh 脚本因 MAVEN_HOME 为 Windows 路径无法解析 classpath，
#       故直接通过 classworlds 启动器调用 Maven。
# 用法：bash mvnw.sh <maven goals...>  例如 bash mvnw.sh clean package
MAVEN_HOME_DIR="D:\\Maven\\apache-maven-3.9.15"
MVN_PROJECT_DIR="$(pwd)"

exec java \
  -cp "${MAVEN_HOME_DIR}\\boot\\plexus-classworlds-2.9.0.jar" \
  "-Dclassworlds.conf=${MAVEN_HOME_DIR}\\bin\\m2.conf" \
  "-Dmaven.home=${MAVEN_HOME_DIR}" \
  "-Dmaven.multiModuleProjectDirectory=${MVN_PROJECT_DIR}" \
  org.codehaus.plexus.classworlds.launcher.Launcher "$@"
