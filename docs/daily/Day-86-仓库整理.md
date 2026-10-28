# Day 86 · 仓库文件整理

## 删掉的（34 + 16 个文件）

- 仓库根目录按项目过程留下的一次性排查产物：
  _build.txt、_err.txt、_sql.txt、_run.log、_rf-*.txt、uild-check.*、
  javap-out.txt、.tmp-zen-models.json 等 28 个；
- ackend/mallx/_mvn-ai.txt、_mvn55.txt；
- 5 份早期失败/乱码的 loadtest 报告（day44 / day46 / day47 ×2 / _probe_domain）；
- 16 份 JVM 崩溃日志 hs_err_pid*.log（OOM 调试产物，共 0.4MB）。

> ackend/mallx/uploads/ **没有删**：里面是评价晒图的真实文件，删了会 404；
> 改成进 .gitignore（运行数据不入库）。

## .gitignore 补充

`gitignore
/backend/mallx/uploads/
/uploads/
hs_err_pid*.log
replay_pid*.log
/_*.log
`

## 新增 docs/README.md

- 目录结构说明（api / daily / superpowers / backlog）；
- 每日记录怎么读（Day-NN 命名、结构、数字会过期）；
- 常用入口表（跑起来 / 某天改动 / 接口 / 验收脚本 / 计划）；
- 工程约定摘要（验证可复跑、SQL 只追加、常量护栏、主题色两端同源）。

## 整理结果

- git status 只剩本次整理本身的改动；
- 审计：无被跟踪的 *.log、无被跟踪的 hs_err；
- 仓库最大被跟踪文件 0.16MB（package-lock.json），没有二进制垃圾；
- rontend/ 568MB、ackend/ 63MB 是 
ode_modules / 	arget，均已被忽略。
