# Day 26 — GitHub Actions CI + M1「从零复现」夹具

> 本日**没有改一行 Java、没有动一个 DDL**。做的是把「我已经跑绿过」变成
> 「**任何人、任何机器、push 一下就能跑绿**」。
>
> 一句话结论：**上 CI 之前先发现了一个真缺口 —— M1 的 245/245 从来不可从零复现。**
> 夹具把这个缺口补上，CI 才成立。

---

## 一、本日三件

| # | 交付 | 产出 | 怎么验的 |
|---|---|---|---|
| 1 | **验收脚本可移植化** | 新模块 `backend/loadtest/_paths.py`（`lp()` 单点定义）；49 个脚本改用 `MALLX_DOCKER` 环境变量 | 63 文件 / 317+ 行增 / 120− 行删；本机复跑报告逐条不变 |
| 2 | **M1 从零复现夹具** | `backend/loadtest/day26-m1-fixture.py`（幂等） | **31 / 31 passed**，报告 `day26-m1-fixture-report.txt` |
| 3 | **CI 流水线** | `.github/workflows/ci.yml`（单 job，116 行） | 本机按同一步序 **A9 全链复跑**（`down -v` 起）全绿 |

提交：`f8a0f76`（可移植化）→ `3c5759c`（CI + 夹具）→ `ca502f2`（README 对齐 CI 现状），均已推送。

---

## 二、★★★ 本日核心发现：M1 的 245/245 **从来不可从零复现**

### 2.1 现象

在**全新 initdb 库**（`docker compose down -v` 之后重建）上直接跑 M1，
**拿不到 245/245** —— 第一轮实测只有 **44 / 72**（脚本早退 ⇒ 断言总数也少）。

### 2.2 根因：M1 依赖一批「手工测试残留」

五个链路脚本各自带着一个**从未被写下来的起始态前提**：

| # | 隐藏前置 | 谁需要它 |
|---|---|---|
| 1 | 库里要有**足够多的历史订单**（page1 / page2 各满 3 行） | `day17-a` 分页断言 |
| 2 | 全库**无 `PENDING_PAYMENT` 订单**、`locked` 全 0 | `day14` 基线 |
| 3 | 全库 **0 张 `SHIPPED` / `COMPLETED`**（**绝对零**，不是相对基线） | `day15` / `day16` 清理后 |
| 4 | `inventory_logs` **必须为空** | `day14` 基线 |
| 5 | 存在 `intruder` 账号（`id=2`）与 `address_id=2` | `day14` 越权对照 / 下单 |

这些在 **dev 库里是 Day 12/13 手工测试留下的**，一直「正好成立」，
所以 245/245 是**真绿**，但它是**环境依赖的真绿**。

> ★★ **判据**：「在我这台机器上跑绿」与「从零能跑绿」是**两个命题**。
> 前者被验证过，不代表后者成立 —— 而 CI 只能建立在后者之上。
> 这与 Day 25 那条「容器 healthy ≠ 业务可用」是同一族：**绿色的适用范围，必须被明确说出来。**

### 2.3 修法：把前置**显式化**，而不是把脚本改宽松

夹具 `day26-m1-fixture.py` 复刻 dev 库的**历史形态**（「8 单 / 0 流水」的脚本化版本）：

```
[0] 应用就绪
[1] SQL 夹具：intruder → id=2 ；demo 地址 → id=2（显式 id 惯例 + 插后校准序列）
[2] 登录：demo / admin
[3] 归零「幽灵计数」：种子自带 sold/locked 残数却无订单可解释 ⇒ 全表归零、available=total
[4] 走真实业务路径建单：购物车 → 下单 → 支付，共 6 张 PAID
[5] 清空 inventory_logs（day14 基线要求 ledger 空）
[6] 一致性核查：6 个 SKU 的 total / available / locked / sold 逐条对账
```

**夹具形态不是拍脑袋定的，是由 M1 的四个「绝对判定」倒推出来的**：

1. `day17-a` 分页断言要 page1 / page2 各满 3 行 ⇒ **≥ 6 单**；
2. `day14` 基线要求全库无挂起单、`locked` 全 0；
3. `day15` / `day16` 清理后要求**全库** 0 张 `SHIPPED` / `COMPLETED`（绝对零）；
4. `day14` 基线要求 `inventory_logs` 空。

⇒ 于是：**6 张 PAID 单 + 幽灵计数归零 + 清空流水**，一条不多一条不少。

★ 两条设计约束：

- **必须幂等**（状态文件 `day26-m1-fixture-state.json` + DB 探测），CI 与本机重跑都安全；
- **夹具造的数据计入 baseline**，所以**不需要清理** —— 这一点与「验收脚本必须自清理」不冲突：
  夹具的产物是**起始态**，M1 的 `--baseline` 是在夹具**之后**拍的。

---

## 三、CI 拓扑：**复刻本机**，而不是另起一套

`.github/workflows/ci.yml` 是**单 job**，步序与本机验收完全同构：

```
checkout → setup-java 21(temurin, maven cache) → setup-python 3.12
  → mvn -B -ntp install -DskipTests           # ★ 在线，CI 没有本地离线仓库
  → docker compose down -v && up -d           # 复用 deploy/docker-compose.yml
  → 等 initdb（数据判据 permissions=41）
  → day25-sql-strict-check.py
  → 起应用（java -jar，/api/hello 探活）
  → day26-m1-fixture.py
  → M1：--baseline → 5 个链路脚本 → 收集器
  → 扩展域：day20 / day21 / day23 / day24
  → 失败时 dump 应用日志
```

四条设计原则（都写在文件头的注释里）：

| # | 原则 | 为什么 |
|---|---|---|
| 1 | **复用 `deploy/docker-compose.yml`**（同一容器名、同一 5434、同一套 initdb 01→14） | 63 个验收脚本**一行不改**即可在 runner 上跑；本机与 CI 的唯一差异只有两项：`mvn` 离线 vs 在线、Windows docker 绝对路径 vs `PATH` 里的 `docker` |
| 2 | **等库就绪用数据判据 `permissions=41`**，不用 `pg_isready` / 容器 `healthy` | initdb 是 `ON_ERROR_STOP=1` **熔断**语义 —— `healthy` 时补丁可能还没跑完（**Day 25 事故**）。这条直接把 Day 25 的教训固化成流水线判据 |
| 3 | **全部判定来自脚本退出码**，CI **不 grep 人类可读文本** | 脚本本就有正确退出码；grep 字面量会因措辞变化而**假绿/假红** |
| 4 | M1 按**收集器协议**执行（`--baseline` → 5 脚本 → 收集器），缺一不可 | 收集器靠报告 **mtime 戳**验证「本轮重新生成」；少跑一个环节就会报 `NO REPORT` |

`deploy/docker-compose.yml` 本日补挂 `../backend/sql` 到 initdb
（CI 与本机同构；**已存在的旧数据卷不受影响**）。

---

## 四、可移植化：CI 的前置条件

脚本里原本硬编码了 `D:\MallX\...` 与 Windows docker 绝对路径。改法：

| 项 | 做法 |
|---|---|
| docker 可执行 | `DOCKER = os.environ.get("MALLX_DOCKER") or <原 Windows 路径>`，**49 个脚本** |
| 文件路径 | 新模块 `_paths.py` 单点定义 `lp()`：剥前缀 + 对齐仓库根，**双态可用**；**71 处** `r"D:\MallX\..."` 包进 `lp(...)` |
| CI 侧 | `env: MALLX_DOCKER: docker` |

★★ **包裹必须正则匹配「完整字面量」并自带 `lp(...)` 的闭括号**。
第一版用裸前缀替换 `r"D:\...` → `lp(r"...`，把**外层调用的右括号**吃掉了
（`open(r"D:\...")` → `open(lp(r"D:\..."`）⇒ v2 才对。
★ 与 Day 19 那条「改召回范围前先问哪些断言靠『命不中』成立」同族：
**做批量文本替换前先问：这个前缀还出现在哪些别的语法位置？**

---

## 五、本轮踩的坑（全部自己抓到）

| # | 现象 | 真因 | 规则 |
|---|---|---|---|
| 1 | ★★ 同文件并行改多处，**静默丢了一条**（login 定义被丢、调用点却落盘 ⇒ `TypeError`） | 同文件并行 Edit 基于旧快照落盘 | **同一文件多处改动逐条串行**，每条后 `grep` 复验。（**第 2 次犯**） |
| 2 | ★ 包裹后语法错 | 裸前缀替换吃掉外层右括号 | 见 §四 |
| 3 | ★ 「残留 0」是**误报** | bash grep 里单 / 双反斜杠 pattern 匹配不到实际内容 | 转义形态不同的文本，**用 Python 脚本侦察才权威** |
| 4 | ★ 夹具第一版判定**全部反向** | 成功判据是 **`body.code == 200`**，不是 `0` | 项目 Result 约定：`code=200` 为成功（同 README「失败判据是 body.code」） |
| 5 | ★ `&&` 链莫名中断 | `grep -c` 零匹配时**退出码 1** | 零匹配预期时不要放进 `&&` 链 |
| 6 | ★★ 后台起的长驻应用**又被宿主回收**（本轮第 2 次） | 宿主回收长驻进程 | 把「起应用 + 跑回归」压进**单条命令窗口**；CI runner 无此问题（job 内跨 step 存活） |

---

## 六、本日验收（A9：从 `down -v` 起的全链复跑）

| 步 | 结果 |
|---|---|
| `docker compose down -v` → `up -d` | initdb 01→14 一次跑完，`permissions = 41` ✓ |
| `day25-sql-strict-check.py` | **16 / 16** |
| `day26-m1-fixture.py` | **31 / 31** |
| M1 回归（8 步） | 全部 `exit=0`；**245 / 245** + `BASELINE RESTORED: YES` |
| `day20-coupon-verify.py` | 82 / 82 |
| `day21-coupon-use-verify.py` | 53 / 53 |
| `day23-rbac-verify.py` | 91 / 91 |
| `day24-brand-crud-verify.py` | 43 / 43 |

★ 与 Day 25 的差异值得记：Day 25 的验收是在**已有数据卷**上做的，
本日是在**空卷**上从 initdb 开始 —— 这正是 CI 要复刻的那条路。

**待办（只能上 runner 才能验的项）**：CI 首跑要盯 runner 日志 ——
`mvn` 在线构建、JDK 21、ubuntu 上的 docker 均属本机无法覆盖的环境。

---

## 七、结论与下一步

Day 26 的产出不是「多了一个流水线」，而是**修好了一个一直存在的认知缺口**：

```text
上 CI 之前 ：「245/245 我跑过」            ← 依赖 dev 库的手工残留
上 CI 之后 ：「245/245 从空库起可复现」    ← 夹具显式化 + 每次 push 自动跑
```

两条留得住的判据：

1. ★★ **「在我机器上跑绿」≠「从零能跑绿」。** 把验收搬进 CI 的价值，
   一半在自动化，另一半在**逼出那些从没被写下来的前提**。
2. ★★ **护栏要跑在真实拓扑上。** CI 没有另起一套 compose，而是复用同一份
   —— 否则「CI 绿」与「本机绿」就变成了两套需要各自维护的真相。

**下一步（V1.0 之外，按建议优先级）**：
① CI 首跑盯日志 → ② V1.2 性能（`EXPLAIN ANALYZE` 复盘，`docs/perf-report.md §七` 已备好方法）
→ ③ V1.1 Redis + RabbitMQ（订单超时关单、库存预占释放 —— 唯一**功能上**的真实缺口）
→ ④ 前端界面（属**需求决策**：要不要改 V1.0 范围，不是技术缺口）。
