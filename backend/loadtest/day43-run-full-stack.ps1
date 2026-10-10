# ==============================================================================
# Day 43 · 一条命令跑完整栈联调（本机便捷入口，非跨平台脚本）
# ------------------------------------------------------------------------------
# 干什么：
#   ① 探 Docker 引擎 + 起开发容器（postgres/redis/rabbitmq）并等 permissions=41
#   ② 等【后端 8080 + 两个 dev server 5173/5174】就绪
#   ③ day26 夹具（把库恢复成 M1 的 day26 常态）
#   ④ 跑 day43-fe-full-stack-e2e.py（54 条断言，含跨端权限对照）
#   ⑤ 复跑 M1 全链，证明联调没把基线搞脏（判据：(c) database back at baseline）
#
# ★ 前提：后端与两个 dev server 要【先起好】—— 长驻进程跨工具调用会被回收，
#   所以它们由调用方用后台任务起（见 docs/daily/Day-43-前端全栈联调.md §五 复现步骤）。
# ★ 本文件含本机绝对路径（docker.exe / python.exe / node 路径），只在这台机器上可用 ——
#   与 backend/mallx/mvnw.sh 同类，别当通用入口。
#
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File day43-run-full-stack.ps1
# 日志：$env:TEMP\fs-run.txt
# ==============================================================================
$ErrorActionPreference = "Continue"
$o = "$env:TEMP\fs-run.txt"
$dk = "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
$py = "C:\Users\TIE\.workbuddy\binaries\python\versions\3.13.12\python.exe"
function L($m) { $m | Out-File $o -Encoding utf8 -Append }
"" | Out-File $o -Encoding utf8
$env:PYTHONUTF8 = "1"

# ---------- 0) Docker 引擎 ----------
$v = & $dk version --format "{{.Server.Version}}" 2>$null
L "ENGINE=$v"
if (-not $v) { L "FATAL: 引擎不在（需 explorer.exe 脱沙箱启动 Docker Desktop）"; exit 2 }

# ---------- 1) 开发容器 ----------
& $dk start mallx-postgres mallx-redis mallx-rabbitmq 2>&1 | Out-Null
$pg = 0
foreach ($i in 1..30) {
  Start-Sleep 3
  $pg = & $dk exec mallx-postgres psql -U mallx -d mallx -tAc "SELECT count(*) FROM permissions" 2>$null
  if ("$pg".Trim() -eq "41") { break }
}
L "dev_pg permissions=$pg (期望 41)"

# ---------- 2) 三个服务就绪（★ 探活用 localhost：Vite 8 只绑 IPv6） ----------
$b = $false; $c = $false; $a = $false
foreach ($i in 1..40) {
  Start-Sleep 3
  if (-not $b) { $b = (& curl.exe -s -o NUL -w "%{http_code}" --noproxy "*" http://127.0.0.1:8080/api/hello) -eq "200" }
  if (-not $c) { $c = (& curl.exe -s -o NUL -w "%{http_code}" --noproxy "*" http://localhost:5173/) -eq "200" }
  if (-not $a) { $a = (& curl.exe -s -o NUL -w "%{http_code}" --noproxy "*" http://localhost:5174/) -eq "200" }
  if ($b -and $c -and $a) { break }
}
L "backend:8080=$b  dev:5173=$c  dev:5174=$a   (等了 $([int]($i*3))s)"
if (-not ($b -and $c -and $a)) {
  L "-- 后端日志尾 --"; (Get-Content "$env:TEMP\fs-app.log" -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -Last 8) | ForEach-Object { L ("  " + $_) }
  L "-- mall dev 日志尾 --"; (Get-Content "$env:TEMP\fs-mall.log" -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -Last 8) | ForEach-Object { L ("  " + $_) }
  L "-- admin dev 日志尾 --"; (Get-Content "$env:TEMP\fs-admin.log" -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -Last 8) | ForEach-Object { L ("  " + $_) }
  L "FATAL: 服务没齐，终止"; exit 3
}

# ---------- 3) 夹具 ----------
Set-Location D:\MallX\backend\loadtest
& $py day26-m1-fixture.py *>&1 | Out-File "$env:TEMP\fs-fixture.log" -Encoding utf8
L "day26-m1-fixture rc=$LASTEXITCODE"
L ("夹具后行数: " + (& $dk exec mallx-postgres psql -U mallx -d mallx -X -t -A -c "SELECT 'orders='||(SELECT count(*) FROM orders)||' payments='||(SELECT count(*) FROM payments)||' reviews='||(SELECT count(*) FROM reviews)||' logs='||(SELECT count(*) FROM inventory_logs);" 2>&1))

# ---------- 4) 全栈联调 ----------
& $py day43-fe-full-stack-e2e.py *>&1 | Out-File "$env:TEMP\fs-e2e.log" -Encoding utf8
L "day43-fe-full-stack-e2e rc=$LASTEXITCODE"
L "-- 联调报告（尾 30 行）--"
(Get-Content day43-fe-full-stack-report.txt -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -Last 30) | ForEach-Object { L $_ }

# ---------- 5) M1 收集器：证明 (c) 数据库回基线 ----------
& $py day17-m1-regression.py --baseline *>&1 | Out-File "$env:TEMP\fs-m1.txt" -Encoding utf8
foreach ($s in @("day14-e2e-walk.py", "day15-ship-confirm.py", "day16-review-e2e.py",
                 "day17-a-order-list-verify.py", "day17-b-order-detail-verify.py",
                 "day17-m1-regression.py")) {
  $out = & $py $s *>&1
  $out | Out-File "$env:TEMP\fs-$s.txt" -Encoding utf8
  L "  $s rc=$LASTEXITCODE"
}
L "-- M1 verdict --"
Select-String -Path day17-m1-regression-report.txt -Pattern "M1 REGRESSION|every CHAIN|every READ|all 5 listed|database back|invariants all zero" -Encoding utf8 |
  ForEach-Object { L ("  " + $_.Line.Trim()) }
L "DONE"
