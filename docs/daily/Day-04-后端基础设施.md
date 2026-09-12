# Day 04：后端基础设施

> 项目：MallX 企业级电商系统
> 学习方式：**你自己动手写代码**。本文档给出每一步要做什么 + 完整代码模板，你先独立尝试，卡住再对照或提问。
> 前置：Day 01-03 已就绪（多模块骨架、Docker PostgreSQL `mallx` 库含 22 张表、users 表已有 1 条 demo 数据）。

---

## 0. 今日目标

把 mall-server 从「能启动的空壳」升级为「**带完整地基、能真实读写数据库**」的后端骨架。Day 04 是全项目唯一一次集中搭基础设施的时机，之后的业务模块都靠这套地基长出来。

**本日验收标准（做完自检）：**
- [ ] 编译通过（`bash backend/mallx/mvnw.sh package`）
- [ ] 应用能启动，`/api/hello` 仍返回正常
- [ ] 浏览器打开 `http://localhost:8080/swagger-ui.html` 能看到接口文档
- [ ] 对 `/api/users` 能真实地 增/删/改/查 Docker PG 里的 users 表
- [ ] 触发一次校验错误，返回的是统一格式 `{code,message,data}` 而非 500 堆栈

---

## 1. 术语：什么是「基础设施」？

业务代码（如"查询某个用户"）是**每张表都不一样**的。
基础设施是**所有业务都共享、但你不希望每个接口重复写**的部分。Day 04 覆盖 4 类：

```text
① 统一异常处理   —— 出错时保证响应格式始终一致，不让异常堆栈裸奔
② 统一返回体     —— 所有接口都返回 {code,message,data}，前端好解析
③ MyBatis-Plus  —— 让你不用写 SQL 就能 CRUD 数据库（分页/时间自动填充）
④ Swagger 文档  —— 自动把接口生成可视化文档，前端不用追着你要接口说明
```

用一个真实的业务模块（**用户**）把它们串起来验收，证明地基能用。

---

## 2. 第一步：补全统一返回码与分页返回体（mall-common）

**路径**：`mall-common/src/main/java/com/mallx/common/api/`

### 2.1 改 ResultCode —— 补几个状态码

现状只有 SUCCESS/FAIL/VALIDATE_FAILED/UNAUTHORIZED/FORBIDDEN。
在枚举里**追加**两个（末尾加逗号换行即可）：

```java
// 追加：
NOT_FOUND(404, "资源不存在"),
NOT_IMPLEMENTED(501, "接口未实现");
```

> 为什么需要？业务里查不到用户、或某接口还没写时，要用明确的状态码，而不是一律 500。

### 2.2 新增 PageResult —— 分页返回体

新建文件 `PageResult.java`（与 Result 同包）。分页接口的 data 不是一个列表，而是「列表 + 总条数 + 当前页 + 每页大小」的包装：

```java
package com.mallx.common.api;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 统一分页返回体
 * <p>data 里除了列表，还带上分页元信息，前端才好渲染「共 X 页」
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class PageResult<T> {

    private List<T> records;   // 当前页的数据
    private long total;        // 总条数
    private long current;      // 当前页码
    private long size;         // 每页大小

    /** 便捷方法：从 MyBatis-Plus 的 Page 转成我们的返回体 */
    public static <T> PageResult<T> of(com.baomidou.mybatisplus.extension.plugins.pagination.Page<T> page) {
        return new PageResult<>(page.getRecords(), page.getTotal(), page.getCurrent(), page.getSize());
    }
}
```

> 上面用了 `com.baomidou.mybatisplus.extension.plugins.pagination.Page<T>`，第 5 步的分页查询会返回它。
> 提示：为什么用 `Page.of(...)` 而不是手拼？因为分页插件执行后会自动把 `records/total` 填好，一行转换即可。

---

## 3. 第二步：业务异常 + 全局异常处理器（mall-common）

**路径**：`mall-common/src/main/java/com/mallx/common/`（api 之外新建两个子包）

### 3.1 BusinessException —— 业务主动抛出的异常

新建 `exception/BusinessException.java`：

```java
package com.mallx.common.exception;

import com.mallx.common.api.ResultCode;
import lombok.Getter;

/**
 * 业务异常：Service 里"主动"发现不满足业务规则时抛出
 * 例如：用户不存在、库存不足、订单已支付不可取消
 */
@Getter
public class BusinessException extends RuntimeException {

    private final Integer code;

    public BusinessException(String message) {
        super(message);
        this.code = ResultCode.FAIL.getCode();
    }

    public BusinessException(ResultCode resultCode) {
        super(resultCode.getMessage());
        this.code = resultCode.getCode();
    }

    public BusinessException(Integer code, String message) {
        super(message);
        this.code = code;
    }
}
```

### 3.2 GlobalExceptionHandler —— 统一拦截异常

新建 `exception/GlobalExceptionHandler.java`。这是 Day 04 **最核心**的一个类，作用：只要任何 Controller/Service 抛异常，都由它兜住，转成统一 JSON。

```java
package com.mallx.common.exception;

import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 全局异常处理器：任何异常最终都转为统一返回体 {code,message,data}
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /** 业务异常：预期内的错误，code 按异常携带 */
    @ExceptionHandler(BusinessException.class)
    public Result<Void> handleBusiness(BusinessException e) {
        log.warn("业务异常: {}", e.getMessage());
        return Result.error(e.getCode(), e.getMessage());
    }

    /** 参数校验异常：@Valid 注解校验不通过时触发 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result<Void> handleValid(MethodArgumentNotValidException e) {
        FieldError fieldError = e.getBindingResult().getFieldError();
        String msg = fieldError == null ? "参数错误" : fieldError.getDefaultMessage();
        return Result.error(ResultCode.VALIDATE_FAILED.getCode(), msg);
    }

    /** 兜底异常：预期外的错误，返回 500，但只回显友好提示，不把堆栈暴露给前端 */
    @ExceptionHandler(Exception.class)
    public Result<Void> handleException(Exception e) {
        log.error("系统异常", e);
        return Result.error(ResultCode.FAIL.getCode(), "系统繁忙，请稍后重试");
    }
}
```

> 三个关键注解解释：
> - `@RestControllerAdvice` = 全局的 Controller 增强，能拦截所有接口的异常
> - `@ExceptionHandler(Xxx.class)` = 当抛出 Xxx 类型异常时，走这个方法
> - `@Slf4j` = Lombok 生成的日志对象，`log.warn/error` 打印到控制台

---

## 4. 第三步：MyBatis-Plus 配置（mall-server）

**路径**：`mall-server/src/main/java/com/mallx/config/`（新建 config 包）

### 4.1 分页插件

MyBatis-Plus 默认**不支持物理分页**，要装分页拦截器。新建 `config/MybatisPlusConfig.java`：

```java
package com.mallx.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MyBatis-Plus 配置：注册分页插件
 */
@Configuration
public class MybatisPlusConfig {

    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        // 指定数据库为 PostgreSQL（分页方言按 PG 生成 limit/offset）
        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.POSTGRE_SQL));
        return interceptor;
    }
}
```

> 坑提醒：`DbType` 一定是 `POSTGRE_SQL`，如果错写成 `MYSQL`，分页 SQL 会是 `LIMIT` 但 PG 语法不完全一致，可能报错。

### 4.2 时间自动填充（可选但推荐）

Day 03 的表都有 `created_at`/`updated_at`，默认值数据库已给。为了让**更新时自动改 updated_at**，加一个自动填充。新建 `config/MyMetaObjectHandler.java`：

```java
package com.mallx.config;

import com.baomidou.mybatisplus.core.handlers.MetaObjectHandler;
import org.apache.ibatis.reflection.MetaObject;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

/**
 * 字段自动填充：insert 时填 created_at/updated_at，update 时只刷 updated_at
 * 需要实体字段上配合 @TableField(fill = ...)
 */
@Component
public class MyMetaObjectHandler implements MetaObjectHandler {

    @Override
    public void insertFill(MetaObject metaObject) {
        this.strictInsertFill(metaObject, "createdAt", LocalDateTime.class, LocalDateTime.now());
        this.strictInsertFill(metaObject, "updatedAt", LocalDateTime.class, LocalDateTime.now());
    }

    @Override
    public void updateFill(MetaObject metaObject) {
        this.strictUpdateFill(metaObject, "updatedAt", LocalDateTime.class, LocalDateTime.now());
    }
}
```

### 4.3 启动类加 Mapper 扫描

编辑 `MallXApplication.java`，在类上**追加** `@MapperScan` 注解，让 Spring 能发现所有模块的 Mapper 接口：

```java
package com.mallx;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.mallx.**.mapper")   // 扫描所有业务模块的 mapper 子包
public class MallXApplication {
    // main 方法不变
}
```

> 注意 import：`org.mybatis.spring.annotation.MapperScan`（不是 com.baomidou 的）。

---

## 5. 第四步：Swagger 文档（POM + config）

### 5.1 加依赖

**编辑父 POM** `backend/mallx/pom.xml`：

在 `<properties>` 里（`<mybatis-plus.version>` 下一行）加：

```xml
<springdoc.version>3.1.1</springdoc.version>
```

在 `<dependencyManagement>` 里加一条（让子模块可用）：

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

在全局共享 `<dependencies>` 里（和 spring-boot-starter-validation 并列）加：

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
</dependency>
```

> 版本为什么是 3.1.1？**Spring Boot 4.x 必须配 springdoc v3.x**（v2.8.x 是给 Boot 3 的）。v3.1.1 是当前最新稳定版，这是已查证的正确搭配，别降级。

### 5.2 加 OpenAPI 元信息配置

新建 `mall-server/.../config/OpenApiConfig.java`：

```java
package com.mallx.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Swagger/OpenAPI 文档信息配置
 * 访问：http://localhost:8080/swagger-ui.html
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI mallxOpenAPI() {
        return new OpenAPI().info(new Info()
                .title("MallX 电商系统 API")
                .description("MallX 企业级电商系统后端接口文档")
                .version("0.0.1"));
    }
}
```

### 5.3 更新 application.yml（追加）

在 `mall-server/src/main/resources/application.yml` 末尾追加：

```yaml
# Swagger 文档路径与开关
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
```

---

## 6. 第五步：落地 mall-user 完整 CRUD 链路（核心！）

**目标**：从实体到接口，走通一层，能对 Docker PG 的 `users` 表真实增删查。
**目录**：`mall-user/src/main/java/com/mallx/user/`（目录 Day 02 已建好）

> 对照 Day 03 的 users 表：
> ```sql
> id BIGSERIAL | username VARCHAR(50) UNIQUE | password VARCHAR(255) | nickname | phone UNIQUE
> email UNIQUE | avatar | status SMALLINT | created_at | updated_at
> ```

### 6.1 实体 User

新建 `entity/User.java`：

```java
package com.mallx.user.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 用户实体，映射 users 表
 * 字段名默认驼峰↔下划线自动映射（application.yml 已开 map-underscore-to-camel-case）
 */
@Data
@TableName("users")
public class User {

    @TableId(type = IdType.AUTO)   // id 数据库自增（BIGSERIAL）
    private Long id;

    private String username;

    /** 实际开发存 BCrypt 密文，前端永远不返回 password */
    private String password;

    private String nickname;

    private String phone;

    private String email;

    private String avatar;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
```

### 6.2 Mapper

新建 `mapper/UserMapper.java`：

```java
package com.mallx.user.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.user.entity.User;

/**
 * 用户 Mapper：继承 BaseMapper 即获得单表 CRUD，无需写 SQL
 */
public interface UserMapper extends BaseMapper<User> {
}
```

> 上面**不用**加 `@Mapper` 注解，因为启动类已 `@MapperScan` 扫到了。

### 6.3 Service + 实现

新建 `service/UserService.java`：

```java
package com.mallx.user.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.user.entity.User;

/**
 * 用户服务接口
 */
public interface UserService extends IService<User> {
}
```

新建 `service/impl/UserServiceImpl.java`：

```java
package com.mallx.user.service.impl;

import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.user.entity.User;
import com.mallx.user.mapper.UserMapper;
import com.mallx.user.service.UserService;
import org.springframework.stereotype.Service;

/**
 * 用户服务实现
 */
@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {
}
```

> MyBatis-Plus 的 `ServiceImpl` 已内置 `save/removeById/getById/list/page` 等方法，所以我们暂时一行业务代码都不用写。
>
> ⚠️ **版本坑（MyBatis-Plus 3.5.16+）**：`IService` / `ServiceImpl` 的包路径已从 `com.baomidou.mybatisplus.extension.service(.impl)` **迁移到 `com.baomidou.mybatisplus.spring.service(.impl)`**。网上大量教程、老文档仍是 `extension.service` 写法，在 3.5.17 下会报"程序包不存在"。本项目用 3.5.17，**必须用上面的 `spring` 路径**。（分页插件 `PaginationInnerInterceptor` 等仍留在 `extension.plugins`，路径未变。）

### 6.4 Controller

新建 `controller/UserController.java` —— RESTful 风格，同时演示**校验注解**和**分页**：

```java
package com.mallx.user.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.common.exception.BusinessException;
import com.mallx.user.entity.User;
import com.mallx.user.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.*;

/**
 * 用户管理接口
 */
@Tag(name = "用户管理")
@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    /** 创建用户：@Validated 触发 username 非空校验 */
    @Operation(summary = "创建用户")
    @PostMapping
    public Result<Long> create(@RequestBody @NotBlank(message = "用户名不能为空") String username) {
        User user = new User();
        user.setUsername(username);
        userService.save(user);          // 走 MyBatis-Plus 内置 insert
        return Result.ok(user.getId());
    }

    /** 查询单个：演示业务异常——查不到抛 404 */
    @Operation(summary = "查询用户详情")
    @GetMapping("/{id}")
    public Result<User> detail(@PathVariable @Min(value = 1, message = "id 不合法") Long id) {
        User user = userService.getById(id);
        if (user == null) {
            throw new BusinessException(com.mallx.common.api.ResultCode.NOT_FOUND.getCode(), "用户不存在");
        }
        return Result.ok(user);
    }

    /** 分页查询：page/size 走 Query 参数 */
    @Operation(summary = "分页查询用户")
    @GetMapping
    public Result<PageResult<User>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size) {
        Page<User> page = userService.page(new Page<>(current, size));
        return Result.ok(PageResult.of(page));
    }

    /** 删除 */
    @Operation(summary = "删除用户")
    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        userService.removeById(id);
        return Result.ok();
    }

    /** 改昵称 */
    @Operation(summary = "更新昵称")
    @PutMapping("/{id}/nickname")
    public Result<Void> updateNickname(@PathVariable Long id, @RequestBody String nickname) {
        User user = new User();
        user.setId(id);
        user.setNickname(nickname);
        userService.updateById(user);    // 只更新非 null 字段
        return Result.ok();
    }
}
```

> 上面的 DTO/VO 先不引入，保持最简便于你理解链路。实际项目会把请求体用 `@RequestBody UserCreateDTO` 封装，加完整校验——那是后续 Day 用户模块精化时再做。

---

## 7. 第六步：构建与验收

### 构建（本机 mvn 不可用，用脚本）
```bash
cd D:\MallX\backend\mallx
bash mvnw.sh package          # 全量编译打包
```

### 启动
```bash
cd mall-server
java -jar target/mall-server-0.0.1-SNAPSHOT.jar --server.port=8080
```

### 逐项验收
```bash
# 1) 旧接口不回归
curl http://localhost:8080/api/hello

# 2) Swagger 文档 JSON（浏览器开 /swagger-ui.html 看 UI）
curl http://localhost:8080/v3/api-docs | head

# 3) 创建用户（会真实 INSERT 到 Docker PG 的 users）
curl -X POST http://localhost:8080/api/users \
     -H "Content-Type: application/json" -d 'jack'

# 4) 查那个用户
curl http://localhost:8080/api/users/1

# 5) 分页
curl "http://localhost:8080/api/users?current=1&size=10"

# 6) 参数校验错误 → 应返回统一 JSON 而非 500 堆栈
curl -X POST http://localhost:8080/api/users \
     -H "Content-Type: application/json" -d ''

# 7) 查不存在的用户 → 应返回 code=404
curl http://localhost:8080/api/users/99999
```

**看数据库确认真的写进去了：**
```bash
docker exec -it mallx-postgres psql -U mallx -d mallx -c "SELECT id,username,created_at FROM users ORDER BY id;"
```

---

## 8. 常见卡点速查

| 现象 | 原因 / 解法 |
|---|---|
| 报 `Invalid bound statement` 或 mapper 没注入 | `@MapperScan` 没加 / 路径不对。确认在启动类上且是 `com.mallx.**.mapper` |
| `Page` 分页不生效（返回全量） | 没注册 `PaginationInnerInterceptor`，或 `DbType` 配错 |
| swagger-ui 打不开 404 | springdoc 版本用了 v2.x（Boot3 的）；确认父 POM 是 3.1.1，且依赖加在全局共享里 |
| `created_at` 插入为 null | 实体字段没加 `@TableField(fill=INSERT)`，或 `MyMetaObjectHandler` 没被扫描（它在 com.mallx.config，启动类在 com.mallx 能扫到） |
| `jakarta.validation` 报红 | 确认依赖 `spring-boot-starter-validation` 在父 POM 全局共享（已配） |
| 端口起不来 | 用 `--server.port=8080` 覆盖环境干扰；确认没有残留 java 进程占 8080 |

---

## 9. 本日成果自检清单

- [ ] mall-common：ResultCode 补了码；PageResult、BusinessException、GlobalExceptionHandler 建好
- [ ] mall-server：MybatisPlusConfig、MyMetaObjectHandler、OpenApiConfig 建好；启动类加了 @MapperScan；pom 加了 springdoc 3.1.1
- [ ] mall-user：User/UserMapper/UserService/UserServiceImpl/UserController 全建好
- [ ] 构建通过、启动成功、上述 curl 全部符合预期
- [ ] Git 提交（建议提交信息：`feat: Day 04 后端基础设施 - 统一异常/返回体/MyBatis-Plus/Swagger + 用户CRUD`）

> 完成后把 Day 04 文档归档为 docs/daily/Day-04-后端基础设施.md（如果你愿意，也可以把本文档直接保存为这一份）。

## 10. 做完之后

Day 04 的地基一旦验收通过，Day 05 起每个业务模块（商品/订单/购物车…）就是**复制 mall-user 这套「实体→Mapper→Service→Controller」模式**去填各自的表。到那时你已经完全掌握套路，写起来会很快。
