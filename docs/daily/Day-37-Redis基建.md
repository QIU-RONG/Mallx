# Day 37 · V1.1 开工 —— Redis 基建（compose / pom / yaml / 冒烟四件套）

> 前提修正（Day 27 结论的落实）：超时关单与库存预占/释放**早已实现**
> （`OrderTimeoutTask` @Scheduled 扫描 + `releaseLocked` CAS、三条取消边统一回补）
> ⇒ RabbitMQ 的增量只剩秒级关单；Redis 才是真正从零到一的部分。
> 用户定版：**Redis + RabbitMQ 全做**，六步节奏 D37→D42。

## 一、端口决策：6380（本日最重要的工程决策）

本机已有一个**带密码的 redis7 容器**（用户其它项目的）占着宿主 6379。取舍：

| 方案 | 问题 |
|---|---|
| mallx-redis 用 6379 | 本地起不来（端口冲突）或被迫去连别人的 redis7 |
| 本地连 redis7 | 密码未知 + 依赖一个不属于本项目的容器 |
| **6380:6379 ✅** | 本地 compose / CI / application.yml 默认值三方一致，互不干扰 |

⇒ `application.yml` 用 `REDIS_HOST/REDIS_PORT` env（默认 `localhost:6380`），与 DB env 同风格。

## 二、四件套

1. **compose**：`mallx-redis`（redis:7-alpine + healthcheck 同 postgres 节奏）；
   纯缓存**不挂持久卷**——重启丢缓存 = 天然全量失效。
2. **mall-server pom**：`spring-boot-starter-data-redis` 只声明在启动模块
   （RedisAutoConfiguration 应用层生效；业务模块编译期要用时各自声明）。
3. **application.yml**：`spring.data.redis`；懒连接——Redis 挂了不影响启动（D40 补降级）。
4. **`GET /api/redis-check`**（白名单精确放行）：真实 `set/get + 10s 过期`，不是裸 PING；
   失败 200 + body.code，与 db-check 同哲学。

## 三、两个新坑（都已进 REF §8.10）

- **docker 凭据坑二段**：`docker-credential-desktop not found` 且 PATH 前置无效时，
  临时 `DOCKER_CONFIG=<空 auths 目录>` 可绕过 pull；**但 compose 插件也按 DOCKER_CONFIG
  目录发现 cli-plugins ⇒ 会「unknown command」——拉完镜像立刻还原**。
- **改 yml 默认值后必须重打包**：第一轮冒烟报 NOAUTH——jar 里还是旧默认 6379，
  连到了用户的 redis7。冒烟失败先查包里的旧默认值。

## 四、验证

- 离线补依赖（在线拉一次后 `-rf :mall-server` 续跑）BUILD SUCCESS。
- `mallx-redis` PONG；应用实测 `/api/redis-check` → **code 200, set/get=pong (ttl=10s)**。
- CI（57275b4，run 36231631396）**success** —— runner 上首次带 redis 拓扑全链绿。

## 五、下一步（D38）

商品详情 cache-aside：`GET /api/products/{id}` 读缓存 → miss 回源 → 回填（TTL+抖动）；
管理端 PUT/DELETE/POST 与库存 adjust 联动失效。**重点课题：详情含实时库存的脏读窗口怎么定**
（候选：库存字段不进缓存 / 库存单独短 TTL / adjust 时精准失效）。
