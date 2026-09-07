# Day 02：系统架构与项目初始化

> 今日目标：确定项目「怎么组织」，并创建可以运行的 Spring Boot 项目。

---

# 1. 今日目标

- [ ] 确定系统总体架构
- [ ] 确定后端模块
- [ ] 确定模块职责
- [ ] 确定后端分层
- [ ] 确定前端结构
- [ ] 确定 API 规范
- [ ] 创建 Spring Boot 项目
- [ ] 连接 PostgreSQL
- [ ] 完成第一个测试接口

---

# 2. 系统总体架构

MallX V1.0：

```text
                用户
                 │
          ┌──────┴──────┐
          ↓             ↓
       mall-web     mall-admin
         Vue3          Vue3
          │             │
          └──────┬──────┘
                 ↓
               Nginx
                 ↓
            Spring Boot
                 ↓
          模块化单体应用
                 │
       ┌─────────┼─────────┐
       ↓         ↓         ↓
      用户       商品       订单
       ↓         ↓         ↓
      购物车     库存       支付
       │         │         │
       └─────────┼─────────┘
                 ↓
             PostgreSQL
```

---

# 3. 为什么使用模块化单体？

第一版不直接做微服务。

原因：

1. 降低项目复杂度
2. 方便快速开发
3. 方便调试
4. 先把业务做完整
5. 为以后拆分微服务做准备

最终：

```text
模块化单体
    ↓
业务稳定
    ↓
Redis / RabbitMQ
    ↓
高并发优化
    ↓
微服务
```

---

# 4. 后端模块

```text
mall-server
mall-common
mall-user
mall-product
mall-cart
mall-inventory
mall-order
mall-payment
mall-marketing
mall-admin
```

---

# 5. 模块职责

| 模块 | 负责内容 |
|---|---|
| mall-common | 公共代码 |
| mall-user | 用户、地址 |
| mall-product | 商品、分类、品牌、SKU |
| mall-cart | 购物车 |
| mall-inventory | 库存 |
| mall-order | 订单 |
| mall-payment | 支付 |
| mall-marketing | 优惠券 |
| mall-admin | 管理后台、RBAC |
| mall-server | Spring Boot 启动 |

---

# 6. 后端分层

每个业务模块统一：

```text
Controller
     ↓
Service
     ↓
Mapper
     ↓
PostgreSQL
```

例如：

```text
ProductController
       ↓
ProductService
       ↓
ProductMapper
       ↓
PostgreSQL
```

---

# 7. Controller

负责：

- 接收 HTTP 请求
- 参数校验
- 调用 Service
- 返回结果

不负责复杂业务逻辑。

---

# 8. Service

负责：

- 业务逻辑
- 事务
- 模块之间的业务协调

例如创建订单：

```text
检查商品
   ↓
检查库存
   ↓
锁定库存
   ↓
创建订单
   ↓
创建订单明细
   ↓
清理购物车
```

---

# 9. Mapper

负责：

- 数据库查询
- 数据库新增
- 数据库修改
- 数据库删除

不负责业务逻辑。

---

# 10. Entity / DTO / VO

三者分开。

```text
DTO
 ↓
接收前端请求

Entity
 ↓
数据库对象

VO
 ↓
返回前端
```

例如：

```text
前端
 ↓
ProductCreateDTO
 ↓
ProductService
 ↓
ProductEntity
 ↓
PostgreSQL
```

查询：

```text
PostgreSQL
 ↓
ProductEntity
 ↓
ProductVO
 ↓
前端
```

---

# 11. 后端项目结构

```text
backend/
└── mallx/
    ├── pom.xml
    │
    ├── mall-common/
    ├── mall-user/
    ├── mall-product/
    ├── mall-cart/
    ├── mall-inventory/
    ├── mall-order/
    ├── mall-payment/
    ├── mall-marketing/
    ├── mall-admin/
    └── mall-server/
```

---

# 12. 业务模块内部结构

以 `mall-product` 为例：

```text
mall-product/
└── src/
    └── main/
        └── java/
            └── com/
                └── mallx/
                    └── product/
                        ├── controller/
                        ├── service/
                        │   └── impl/
                        ├── mapper/
                        ├── entity/
                        ├── dto/
                        └── vo/
```

---

# 13. 前端结构

```text
frontend/
├── mall-web/
└── mall-admin/
```

用户端：

```text
mall-web/
└── src/
    ├── api/
    ├── assets/
    ├── components/
    ├── router/
    ├── store/
    ├── utils/
    └── views/
```

管理端：

```text
mall-admin/
└── src/
    ├── api/
    ├── assets/
    ├── components/
    ├── router/
    ├── store/
    ├── utils/
    └── views/
```

---

# 14. API 规范

统一使用：

```text
/api
```

用户端：

```text
/api/auth/*
/api/user/*
/api/products/*
/api/cart/*
/api/orders/*
/api/payment/*
```

管理端：

```text
/api/admin/users/*
/api/admin/products/*
/api/admin/orders/*
/api/admin/inventory/*
/api/admin/roles/*
/api/admin/permissions/*
```

---

# 15. 项目目录初始化

最终目录：

```text
MallX/
│
├── backend/
│
├── frontend/
│
├── docs/
│
└── deploy/
```

---

# 16. Git 初始化

```bash
git init
```

主要分支：

```text
main
develop
```

功能分支：

```text
feature/*
```

例如：

```text
feature/user
feature/product
feature/order
```

---

# 17. 创建 Spring Boot 项目

## 基本配置

```text
Group:
com.mallx

Artifact:
mallx

Java:
17+
```

---

## 依赖

第一阶段加入：

```text
Spring Web
Validation
Lombok
PostgreSQL Driver
MyBatis-Plus
```

后续再加入：

```text
Spring Security
JWT
Swagger
Redis
RabbitMQ
```

---

# 18. PostgreSQL 配置

配置文件：

```text
application.yml
```

示例：

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mallx
    username: postgres
    password: your_password
    driver-class-name: org.postgresql.Driver
```

---

# 19. 第一个测试接口

创建：

```text
GET /api/hello
```

返回：

```json
{
  "code": 200,
  "message": "success",
  "data": "Hello MallX"
}
```

---

# 20. Day 2 验收

必须能够做到：

- [ ] Spring Boot 正常启动
- [ ] Maven 正常构建
- [ ] PostgreSQL 正常连接
- [ ] 第一个 API 可以访问
- [ ] 项目模块结构建立
- [ ] Git 初始化完成
- [ ] Swagger/API 文档准备完成

最终：

```text
浏览器
   ↓
GET /api/hello
   ↓
Spring Boot
   ↓
Hello MallX
```

---

# 21. Day 2 最终目录

```text
MallX/
│
├── backend/
│   └── mallx/
│       ├── mall-common/
│       ├── mall-user/
│       ├── mall-product/
│       ├── mall-cart/
│       ├── mall-inventory/
│       ├── mall-order/
│       ├── mall-payment/
│       ├── mall-marketing/
│       ├── mall-admin/
│       └── mall-server/
│
├── frontend/
│   ├── mall-web/
│   └── mall-admin/
│
├── docs/
│
└── deploy/
```

---

# 22. Day 2 完成标准

今天结束后：

```text
需求
 ↓
系统架构
 ↓
模块设计
 ↓
项目骨架
 ↓
Spring Boot
 ↓
PostgreSQL
```

**Day 2 完成。**

下一天进入：

> **Day 3：PostgreSQL 数据库设计**