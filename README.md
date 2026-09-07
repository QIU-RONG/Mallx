# MallX 企业级电商系统

前后端分离 + 模块化单体的企业级 B2C 电商系统，目标是使用 **PostgreSQL** 完成存储与商品搜索，第一版不引入 Elasticsearch / Nacos 等重组件。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Java 21 · Spring Boot 4.1.1 · MyBatis-Plus |
| 前端 | Vue 3 · Vue Router · Pinia · Element Plus · ECharts |
| 数据库 | PostgreSQL 16（Docker 运行） |
| 认证 | Spring Security + JWT |
| 搜索 | PostgreSQL Full-Text Search + pg_trgm + GIN + JSONB |

## 目录结构

```text
MallX/
├── backend/
│   ├── mallx/            # Maven 多模块后端（10 模块）
│   │   ├── mall-common   统一返回体 / 公共组件
│   │   ├── mall-user / mall-product / mall-cart / mall-inventory
│   │   ├── mall-order / mall-payment / mall-marketing / mall-admin
│   │   └── mall-server    启动模块
│   └── sql/              # 数据库脚本（Day 03）
│       ├── 01-schema.sql  建表（22 张核心表 + 全文搜索触发器）
│       ├── 02-index.sql   索引（含 JSONB GIN / 全文 GIN / pg_trgm）
│       └── 03-data.sql    初始化数据（分类/品牌/商品/RBAC）
├── frontend/             # Vue 3 前端
├── deploy/
│   └── docker-compose.yml # Docker PostgreSQL（宿主 5434 -> 容器 5432）
├── docs/
│   └── daily/            # Day-by-Day 学习规划文档
└── README.md
```

## 快速开始

### 1. 启动数据库

Docker Desktop 保持运行，启动 PostgreSQL：

```bash
docker compose -f deploy/docker-compose.yml up -d
```

连接参数：库 `mallx`，用户/密码 `mallx/mallx123`，宿主端口 **5434**。

### 2. 初始化数据库

```bash
cd backend/sql
# 依次执行（在 mallx 库中）
psql -h localhost -p 5434 -U mallx -d mallx -f 01-schema.sql
psql -h localhost -p 5434 -U mallx -d mallx -f 02-index.sql
psql -h localhost -p 5434 -U mallx -d mallx -f 03-data.sql
```

### 3. 启动后端

```bash
cd backend/mallx
bash mvnw.sh package        # 编译
java -jar mall-server/target/mall-server-*.jar --server.port=8080
```

验证：

```text
GET /api/hello      -> {code:200, data:"Hello MallX"}
GET /api/db-check   -> {code:200, data:"DB 连接成功: PostgreSQL 16.15 ..."}
```

## 版本规划

```text
V1.0 模块化单体        （进行中：数据库设计已完成）
V1.1 Redis + RabbitMQ
V1.2 性能优化
V1.3 Docker + 阿里云
V2.0 Spring Cloud Alibaba 微服务
```
