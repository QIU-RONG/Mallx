# Day 25 — M3 工程化收口（API 总览 / README / 部署 / 压测报告）

> 本日**没有改一行 Java、没有动一个 DDL**。做的全是「把已经验收过的东西变成别人能接手的东西」，
> 以及修掉一个**只在部署形态下才会暴露**的 SQL 缺陷。
>
> 一句话结论：**后端功能在 Day 24 就完成了；Day 25 让它「换个环境也能起来」，并且证明了这件事。**

---

## 一、本日五件

| # | 交付 | 产出 | 怎么验的 |
|---|---|---|---|
| 1 | **API 总览** | `backend/loadtest/day25-api-inventory.py` → 生成 `docs/api/API-总览.md`（**77 端点**）+ `docs/api/openapi.json` 运行时快照 | 脚本自带 **9 条护栏**，含**三方交叉核对** |
| 2 | **README 重写** | `README.md` 从 Day-10 状态改到现状 | `day25-readme-quickstart-check.py` **16/16**（每条命令实测） |
| 3 | **部署产物** | `deploy/Dockerfile` · `docker-compose.app.yml` · `.env.example` · **`deploy/README.md`** · `.dockerignore` | 镜像**构建成功**；全栈 **healthy**；`day25-compose-verify.py` **12/12** |
| 4 | **压测与验收汇总** | **`docs/perf-report.md`**（新建） | 全部数字取自既有 `*-report.txt`，不凭记忆 |
| 5 | **SQL 补丁严格模式护栏** | `backend/loadtest/day25-sql-strict-check.py` | **16/16**，并做了**控制组**（见 §七） |

外加一处收尾：`.gitignore` 补 `/deploy/.env` 与 `/dsh-*`（见 §八）。

---

## 二、M3-1：API 总览为什么必须「生成」而不是「手写」

手写清单必然过期 —— 本项目已经吃过一次同类账：`docs/api/users-api.md` 停在 Day 06，
**把 Day 22 已修掉的越权漏洞写成了「预期行为」**（T3，Day 24 已订正）。

所以总览由脚本生成，并且在生成时做**三方交叉核对**：

```text
① 解析 Java 源码      → (方法, 路径, 权限码, 所在模块)     ← 权限码只在这里，OpenAPI 里没有
② POST /v3/api-docs   → (方法, 路径)                       ← 运行时真实路由
③ psql 查 permissions → 源码用到的每个权限码是否【存在】且【至少被一个角色持有】
```

| 护栏 | 判据 |
|---|---|
| 两来源端点集合**完全相等** | ① 与 ② 互为子集 ⇒ 少一个方向都说明「有接口没被扫到」或「有路由没写进源码解析」 |
| 管理端端点**全部有权限码** | 没有「裸奔」的 `/api/admin/**` |
| 管理端端点**全部在 `/api/admin/**` 下** | 否则白名单可能命中它（`GET /api/products/**` 是先匹配先赢的） |
| 非管理端 API **不挂 `@PreAuthorize`** | ★ C 端 token **不带权限码**，挂了必然 403 |
| 源码权限码 ↔ 数据库 | 每条都在 `permissions` 里，且**至少一个角色持有** |

> ### ★ 第 4 条护栏「报警」了，而它是对的
>
> 首跑时它指出 `POST /api/orders/{id}/ship` 挂了 `order:ship` 却在 `/api/orders/**` 下。
> 查证结果：**这是 Day 15 的遗留路径，且是刻意的**（当时管理端发货接口还没有 `/api/admin/orders` 可挂）。
> ⇒ 护栏的前提写得**过宽**。修的不是代码，是**判据**：
> 从「非管理端一律不许挂权限码」收窄为**精确不变量**
> ——「`@PreAuthorize` 的端点必须能通过 `SecurityConfig` 的白名单之外路径到达」。
>
> ★ 判据：**护栏报警时先问「是对象错了还是判据错了」**；顺手把判据改宽以便变绿，
> 与把对象改坏以便变绿，是同一个错误的两个方向。

生成物：`docs/api/API-总览.md` 按**公开 / 管理端 / C 端 / Tag** 四个视角各列一遍，
每条都带**鉴权档位**与**权限码**。

---

## 三、M3-2：README 重写

原 README 停在 Day-10（10 个模块、`bash mvnw.sh package`、Day 10 状态），
与现状（**11 模块**、离线 Maven 构建、77 端点、41 权限码、245 断言回归）差得太远。

重写后新增的几块：**模块职责表**、**URL 前缀与状态码约定**、**鉴权三档**、
**种子账号（含互为反向对照的受限账号）**、**测试与回归**、**性能与正确性证据**、**版本规划**。

★ 关键动作：**README 里的每条命令都实测过**。为此写了
`day25-readme-quickstart-check.py`（**16 条断言**），包括「匿名访问受保护端点应该是 401」这类**反例**。

> 顺带修了两处数字失真：头条「验收脚本 60 份」实际 **61 份**；
> 「各域验收 400+ 条」实际 **948 条**（全量合计 **1193**）。
> ★ 数字也是文档的一部分，**没有取证的数字等于没有数字**。

---

## 四、M3-3：部署产物与两个刻意的取舍

### 1. 应用镜像**不负责编译**

`deploy/Dockerfile` 只把**宿主已打好的 jar** 装进运行时镜像，不做「多阶段：容器内跑 mvn」。

1. 本项目依赖本机 Maven 本地仓库（`mvn -o` 离线构建），在镜像里重拉一遍依赖既慢又要公网；
2. **真相只有一份** —— 本地/CI 打出的 jar 与镜像里的 jar 是**同一个文件**，
   不会出现「镜像里编出来的东西跟验收过的不是一回事」。

### 2. 数据库不发布端口、容器非 root

数据库只有 app 需要它，用 `expose` 就够；应用容器跑在 `mallx` 非特权用户下。

### 3. 构建路径上的两个坑（本日实测，都写进了 `deploy/README.md`）

| 现象 | 真因 | 处理 |
|---|---|---|
| `error getting credentials ... docker-credential-desktop not found` | CLI 与凭据助手不在同一目录被找到 | 把 `...\DockerDesktop\resources\bin` 加进 `PATH` |
| 构建报错出现在「解析 frontend」 | Dockerfile 顶部写了 `# syntax=docker/dockerfile:1` ⇒ 先去拉 `docker/dockerfile:1` frontend 镜像 | **删掉那行**；本文件只用最基础的 `COPY/ENV/HEALTHCHECK`，内置 frontend 够用 |

★ 第二条的教训：**报错发生的位置 ≠ 原因所在的位置**。
那条 `# syntax=` 让失败点前移到「拉 frontend」，而错误信息长得像「基础镜像拉不下来」，
排查方向整个跑偏。

---

## 五、M3-4：`docs/perf-report.md`

把散落在 50+ 份报告里的证据收成一份：并发正确性（**含对照组**）、台账对账、
M1 回归矩阵、各域验收矩阵、搜索与索引、**已知边界与限额**。

★ 全部数字**逐条从 `*-report.txt` 取出**，不凭记忆。几处关键：

| 场景 | 主组（CAS / 条件 UPDATE） | 对照组（先查后改） |
|---|---|---|
| 20 线程抢 10 件库存 | 成功**恰好 10**，`available 10→0`，**从未为负**，0.53s | **20 单全部成交**，实际只扣 2 件 ⇒ **超卖 10 件**（2.81s） |
| 20 线程付同一单 | 成交**恰好 1 次**（`payments` 1 行） | `payments` **+12 行 = 233,964.00**（该订单只应收 19,497） |

★★ 报告里单独强调了一条：**对照组超卖时 `total = available + locked + sold` 依然成立**（`8 + 2 = 10`）
⇒ **恒等式只能证明「账目不矛盾」，不能证明「卖出的没超过库存」**。
光跑恒等式会给出**假的安全感**。

---

## 六、★★★ 本日核心事件：initdb 被 09 号补丁的「自检」掐断

这是本日唯一一处**真缺陷**，也是最有价值的一段。

### 6.1 现象：全套「看起来都是绿的」

| 看到的 | 实际含义 |
|---|---|
| `docker compose ps` **全绿** | 只证明进程起来了 |
| `app` 容器 **(healthy)** | 只证明 `/api/hello` 能回 —— 它**不碰数据库** |
| `day25-compose-verify.py` **8/12 FAIL** | 才把问题暴露出来 |

FAIL 的具体项：容器内 `permissions` 只有 **20** 行（应 41）、品牌 CRUD 的 `39/40/41` **不存在**、
`GET /api/admin/roles` 带**超管 token 也 403**。

### 6.2 根因

`09-user-coupons-unique.sql` 第三节的自检做法是「**故意**插两次同一行、期望第二次撞唯一约束」。
- 在**交互式 psql** 里：完全正常，而且是好实践（证明约束真在拦）。
- 在 **`docker-entrypoint-initdb.d`** 里：postgres 官方 entrypoint 用
  **`psql -v ON_ERROR_STOP=1`** 逐文件执行，整个 entrypoint 处在 `set -e` 之下
  ⇒ 那条**故意的**错误**当场掐断整个初始化** ⇒ **10/11/12/13/14 号补丁全部静默跳过**。

而 initdb 日志里只留一句话，粗看像「基础镜像拉不下来」之类的问题。

### 6.3 修法：不删探针，而是**让异常在库内被接住**

把「期望失败」的那条 `INSERT` 包进 plpgsql 的 `EXCEPTION` 块：

```sql
DO $$
DECLARE v_rejected boolean := false; v_err text;
BEGIN
    BEGIN
        INSERT INTO user_coupons (user_id, coupon_id) VALUES (1, 999999);  -- 期望抛错
    EXCEPTION
        WHEN unique_violation THEN v_rejected := true; v_err := SQLERRM;
        WHEN others THEN
            RAISE EXCEPTION 'SELF-CHECK INVALID：期望唯一约束冲突，实得 %（%）', SQLSTATE, SQLERRM;
    END;
    IF NOT v_rejected THEN
        RAISE EXCEPTION 'SELF-CHECK FAILED：重复领取被接受了 ⇒ 约束没起作用';
    END IF;
    RAISE NOTICE 'SELF-CHECK OK：重复领取已被唯一约束拒绝（%）', v_err;
END $$;
```

**验证一点没少，psql 的退出码回到 0**。判据同时从「人看 stderr 里那句话对不对」
升级为**看退出码**。

零痕迹也复核过：`coupons` 里 `id=999999` 恒为 0 行、`user_coupons` 为空。

> ### ★★ 两条一般化判据（已写进项目判据体系）
>
> **① 一个 SQL 文件要同时满足「交互跑」与「批处理跑」两种用法时，
> 「故意报错」必须被内部消化，绝不能漏到 psql 层。**
>
> **② 容器 / 进程 `healthy` 只证明「它活着」，不证明「业务可用」。**
> 验收必须打到**真实业务端点**上，并且**直查数据库对账**。
> （这与 README 里那条「判成功必须看 `body.code`」是同一个精神的两个面。）

---

## 七、★★ 新护栏 `day25-sql-strict-check.py`，以及它的**控制组**

修完只说明「这次好了」，不说明「下次不会再犯」。所以把「全新库 + 按序 + `ON_ERROR_STOP=1`」
做成**常驻护栏**：

- 在运行中的 Postgres 里建一个**临时库** `mallx_strict_probe`，把 **01→14** 按序灌进去；
- 逐文件核对 `rc`；随后核对硬事实（`permissions == 41`、`max(id) == 41`、
  `orders.discount_amount` 在、`uk_user_coupons_user_coupon` 在、超管持有 4 条 `brand:*`、
  表数 ≥ 22）；再核对**探针零痕迹**；最后删库。
- **不碰开发库的任何数据**。

### 7.1 ★ 控制组逼出了护栏自己的一个盲区

「护栏全绿」本身只是「一个会通过的东西」。所以拿**仓库里那份有缺陷的旧版 09** 放回去跑了一遍。

**第一版护栏的表现是错误的**：它逐文件**独立**调用 psql，前一个失败**不阻止**后面的
⇒ 旧版下 `10/11/12/13/14` 全部显示 `rc=0`，连「`permissions` 只有 20 行」都**没复现出来**
⇒ 它只是「14 个独立的语法检查」，**没有模拟 initdb 的熔断语义**。

改成**第一个失败即 SKIP 其后全部**之后再跑旧版，护栏把事故现场**逐项复现**：

| 判据 | 旧版（缺陷） | 新版（已修） |
|---|---|---|
| 09 号 | `rc=3` + `duplicate key ... uk_user_coupons_user_coupon` | `rc=0` + NOTICE `SELF-CHECK OK` |
| 10–14 号 | **SKIP（initdb 里执行不到）** | 全部 `rc=0` |
| `permissions` 行数 | **20** ← 与容器里实测到的数字**完全一致** | **41** |
| `orders.discount_amount` | 缺失 | 存在 |
| 14 号补丁的授权 | 0 条 | 4 条 |
| 判定 | **9 / 16 FAIL** | **16 / 16 OK** |

★ **这一步（控制组）不是可选项**：「装置能发现问题」与「装置说没问题」是两件事，
只有前者被证明过，后者的绿才有意义。这与 Day 12/13 压测的「主组 + 对照组」是同一个方法论。

★ 顺带修掉的一个**检查写法缺陷**：等待容器 healthy 时用了
`$s = (两个服务拼成一串); $s -match "app\|Up.*healthy"` ——
`.*` 是贪心的，**真正匹配上的是 postgres 那半截**。这类「可以因错误的原因通过」的检查，
在**反例**（本来该失败）面前才会现形。改用逐容器 `docker inspect -f '{{.State.Health.Status}}'`。

---

## 八、★ 一处「注释描述了一个不存在的机制」

`deploy/.env.example` 的文件头写着：

> `★ .env 已在 .gitignore 里排除，不要把真实密钥提交进仓库。`

而 `.gitignore` 里**当时并没有这条规则** —— 也就是说，一份**含真实 `JWT_SECRET` 的文件
一直处于可被提交的状态**，而注释让人以为保护已经就位。本日已补上：

```gitignore
/deploy/.env        # 真实密钥，不入库（.env.example 是模板，要入库）
/dsh-skin-v2/       # 与本项目无关的本地目录
/dsh-themes/
```

★ 这类漂移比「缺文档」更坏：**缺文档会让人去查，错误的文档会让人不再查。**

---

## 九、本日验收

| 项 | 结果 |
|---|---|
| `mvn -o install -DskipTests` | 未重编译（**本日零 Java 改动**，jar 仍是 Day 24 那个） |
| **`day25-sql-strict-check.py`** | **16 / 16 OK**（14 份补丁全新库按序跑通、09 输出 NOTICE、硬事实全对、零痕迹） |
| 上述护栏的**控制组**（旧版 09） | **9 / 16 FAIL**，且 **`permissions` 复现为 20**（与容器实测一致） |
| `docker compose up -d`（**全新数据卷**） | initdb **01→14 一次跑完**，日志含 `NOTICE SELF-CHECK OK`，`PostgreSQL init process complete` |
| **`day25-compose-verify.py 8081`** | **12 / 12 OK**（容器层 + initdb 链路 + 端到端 + 权限经新库生效） |
| **M1 全链路回归** | **245 / 245** —— 5 条（`day14` 67 · `day15` 56 · `day16` 75 · `day17-a` 26 · `day17-b` 21），全部标记 `this run`；`COVERAGE: 5/5`；**`BASELINE RESTORED: YES`** |
| `day20-coupon-verify.py` | **82 / 82 OK**（`user_coupons` 正是 09 号补丁约束的那张表） |
| `day21-coupon-use-verify.py` | **53 / 53 OK**（核销 / 退券 / 抵扣恒等式全表成立） |

★ 复跑时的一处**环境事实**（不是产品缺陷，但值得记）：
回归跑到**最后一步**（`day25-sql-strict-check.py`）时，后台长驻的应用进程被宿主回收，
日志**断在最后一个请求上、既无关闭行也无异常** —— 与本项目已记录的
「`run_in_background` 起的长驻进程会被回收」是同一个签名。
⇒ 当时已完成的 5 条链路 + 两份券域报告**全部有效**（报告里标着 `this run`）；
被中断的那一步不需要应用，**单独前台重跑即得 16/16**。
⇒ 同时确认它**留下了临时库** `mallx_strict_probe`（脚本被杀于中途的证据），
而脚本开头的 `DROP DATABASE IF EXISTS` 让重跑自动清干净 ⇒ 复核后库里只剩 `mallx`。

日 24 的各项回归不重复罗列（本日无 Java 改动）；`docs/perf-report.md` 里给的是
**全部 61 个脚本 / 合计 1193 条断言**的完整矩阵。

---

## 十、结论与下一步

**M3 四件交付完成，M1 真机复跑 245/245**。项目的三个里程碑至此全部收口：

```text
M1  全链路与域验收回归        ✅ 245/245（5 条链路，逐字节回基线）
M2  后端 API 完整            ✅ §5.1–§5.6 全绿，backlog 一览表归零
M3  工程化收口               ✅ API 总览 / README / 部署产物 / 压测报告
```

本日最值得留住的不是那四份文档，而是**两条判据**：

1. **「批处理跑的 SQL 里，故意报错必须被内部消化」** —— 这条只在**部署形态**下才会现形，
   开发库、交互式 psql、单元验证**全都测不到**。
2. **「容器 healthy ≠ 业务可用」** —— 反过来也成立：**验收脚本必须打到真实端点 + 直查数据库**，
   否则「全绿」只覆盖了「进程活着」。

以及一条方法论：**新写的护栏必须做控制组**。没有反例的护栏，无法区分
「装置没发现问题」与「装置没有能力发现问题」。
