# Day 07：商品写接口 + RBAC 权限

> 项目：MallX 企业级电商系统
> 学习方式：**你自己动手写代码**。本文档给出每一步要做什么 + 完整代码模板，你先独立尝试，卡住再对照或提问。
> 前置：Day 06 已就绪（登录鉴权跑通，8 项验收全绿）。
> 技术栈新增：`@EnableMethodSecurity` + `@PreAuthorize`（Spring Security 7.1.1 自带的**方法级鉴权**）。

---

## 0. 今日目标

Day 06 让系统学会了问「**你是谁？**」。今天要让它进一步回答「**你能干什么？**」

具体三件事：

1. **加上商品写接口** —— `POST` 新增、`PUT` 修改、`DELETE` 删除。Day 05 只做了只读，商品永远只有那 5 条。
2. **让"登录"这件事真正有用** —— 写接口必须登录才能调；同时**不能**把匿名用户的读接口（`GET /api/products`）误伤。
3. **接上 RBAC** —— 用 Day 03 就建好的 `admins` / `roles` / `permissions` / `admin_roles` / `role_permissions` 五张表，实现"**只有商品管理员能改商品**"。

**本日验收标准（做完自检）：**

- [ ] 用 `admin / admin123` 登录能拿到 token
- [ ] 带 token 能 `POST /api/products` 新建商品成功（返回新 id）
- [ ] **不带 token** 调写接口 → 401（Day 06 的机制自然生效）
- [ ] 带 token 但**用 C 端用户 `demo` 的 token** 调写接口 → **403**（登录了，但没权限）
- [ ] 参数不合法（如商品名为空）→ 400 + 明确的中文提示，不是 500
- [ ] 改一个不存在的商品 id → 404（`商品不存在`）
- [ ] 匿名 `GET /api/products` **仍然 200**（白名单没被今天的改动破坏）
- [ ] 理解并口述：认证 vs 授权的区别、方法级鉴权是怎么"拦截"的、`hasAuthority` 里的字符串从哪来

**今天刻意不做（留给后面）：**

- 商品的图片上传、SKU 批量维护（只做商品主表 + 简单字段）
- 完整的管理员 CRUD（今天只做认证时读取角色，不做后台管理界面）
- 刷新 token、操作日志审计（`permissions` 表已预留，Day 08+ 再说）

---

## 1. 今日思路：先看清三件容易混的事

### 1.1 「两套人」——这是今天最容易翻车的点

Day 03 建表时埋了一个**关键设计**，今天必须正面处理：

```text
users  表  ← C 端顾客（demo）。买东西、看订单、加购物车
admins 表  ← 后台管理员（admin）。上架商品、发货、处理售后
```

它们是**两套完全独立的账号体系**，`admin_roles.admin_id` 关联的是 `admins(id)`，**不是 `users(id)`**。

| | C 端用户 | 管理员 |
|---|---|---|
| 表 | `users` | `admins` |
| 种子账号 | `demo / demo123` | `admin / admin123` |
| 能干什么 | 浏览、下单、管理自己的数据 | 上架商品、改价、发货 |
| 有角色吗 | 没有（`roles` 表跟它无关） | 有（SUPER_ADMIN / PRODUCT_ADMIN / ORDER_ADMIN） |

> ⚠️ **别偷懒把 admin 也塞进 `users` 表**。两套体系分开是电商的标准做法，理由很实在：顾客数量百万级、管理员十几个人，塞一张表会让权限逻辑和索引都变复杂。今天先把管理员这条线打通，C 端用户的权限后面用 `user_addresses` 那套类比扩展。

### 1.2 认证 vs 授权 —— 今天的分界线

```text
认证 Authentication  —— 你是谁？    ← Day 06 已完成（验 token）
授权 Authorization   —— 你能干什么？ ← 今天做（查角色/权限）
```

Day 06 结束时，**任何**带了合法 token 的人都能访问 `/api/users`——不管他是 admin 还是 demo。因为 `SecurityConfig` 里只写了 `.anyRequest().authenticated()`，含义是"登录就行，不挑人"。

今天要加一层：**登录 + 有对应权限**。

### 1.3 权限从哪来？—— 一句话讲通 RBAC

```text
admins ──(admin_roles)──> roles ──(role_permissions)──> permissions
  1 条 admin     中间表      1~N 个角色      中间表        1~N 个权限
                      例如 PRODUCT_ADMIN        例如 product:create
```

最终给 Security 用的是一个**字符串集合**，比如：

```text
admin  →  ROLE_SUPER_ADMIN, product:list, product:create, product:update, ...（全部 8 个）
```

控制器上写 `@PreAuthorize("hasAuthority('product:create')")`，Security 就检查当前登录人的集合里有没有这个字符串。**就这么简单**——后面第 6 步会把这个集合装配出来。

### 1.4 今天的完整流程图

```text
① admin 登录  POST /api/auth/admin/login  {username:"admin", password:"admin123"}
        ↓
② 查 admins 表 + 5 张 RBAC 表，算出权限集合
        ↓
③ 签发 token（adminId + username + type=ADMIN + ★perms 权限码数组）
        ↓
④ 调写接口  POST /api/products  Header: Authorization: Bearer <token>
        ↓
⑤ JwtAuthenticationFilter 验签 → 从 token 的 perms 还原权限 → 登记进 SecurityContext
        ↓
⑥ @PreAuthorize("hasAuthority('product:create')") 检查权限 → 通过/拒绝
        ↓
⑦ 通过 → 执行业务；不通过 → AccessDeniedHandler 返回 403 统一 JSON
```

> **★ 权限为什么放进 token？** 因为这样**完全无状态**：过滤器验完签，权限就齐了，不用查库。
> 代价是**权限在 token 有效期内被冻结**——给管理员加了权限，他得重新登录才生效。
> 本项目 token 有效期 2 小时、权限变更频率低，这个代价可接受。
>
> **另一条路（本次不采用）**：token 只放身份，过滤器每请求现查一次权限。好处是权限**立即生效**，
> 代价是每请求一次库查询（要加缓存）。等以后真需要"改权限立即生效"，只需改
> `JwtAuthenticationFilter` 一处即可切换——所以现在选哪条都不会锁死后面。
>
> ⚠️ **这一步是整个 Day 07 的枢纽**：`@PreAuthorize` 检查的是 `Authentication#getAuthorities()`，
> 而这个集合**只有两个来源**——要么 token 里带，要么过滤器现查。**少了这一步，所有人都是 403。**

### 1.5 今天要新增/改动的文件一览

| 模块 | 文件 | 动作 | 干什么 |
|---|---|---|---|
| mall-common | `security/RestAccessDeniedHandler.java` | **新建** | 没权限时返回统一 403 JSON |
| mall-common | `config/SecurityConfig.java` | **改** | 挂 `AccessDeniedHandler` + 开方法级鉴权 |
| mall-common | `security/JwtUtil.java` | **改** | 加 `generateForAdmin`（token 带 `type=ADMIN` + **`perms` 权限数组**）；`generate` 补 `type=USER` |
| mall-common | `security/JwtAuthenticationFilter.java` | **改** | ★ **从 token 的 `perms` claim 还原权限到 `authorities`**（不改这里，`@PreAuthorize` 永远 403） |
| mall-admin | `entity/Admin.java` / `Role.java` / `Permission.java` | **新建** | RBAC 实体 |
| mall-admin | `mapper/AdminMapper.java`（含自定义 SQL） | **新建** | 三个 Mapper + 联查权限 |
| mall-admin | `mapper/AdminMapper.xml` | **新建** | 一条 SQL 联查权限 |
| mall-admin | `security/AdminLoginUser.java` | **新建** | 管理员身份载体（含权限集合） |
| mall-admin | `security/AdminAccountService.java` | **新建** | 查 admins + 拼权限集合。**⚠️ 不实现 `UserDetailsService`**（原因见 6.3） |
| mall-admin | `controller/AdminAuthController.java` | **新建** | `POST /api/auth/admin/login` |

> ℹ️ 原计划里的 `config/AdminSecurityConfig.java`（具名 Bean 绕开冲突）**已取消**——
> 经字节码核实那条路走不通，改用 6.3 的方案，因此这个文件不需要了。
| mall-product | `dto/ProductCreateDTO.java` / `ProductUpdateDTO.java` | **新建** | 写接口入参 + 校验注解 |
| mall-product | `service/ProductService.java` + `impl` | **改** | 新增 create/update/delete |
| mall-product | `controller/ProductController.java` | **改** | 三个写接口 + `@PreAuthorize` |

> ⚠️ **注意 `mall-admin` 模块**：原以为 Day 02 建骨架时没建这个模块。
> **2026-09-16 实测：已经存在**（只有 `pom.xml`，无 Java 源码），父 POM `<modules>`、
> `dependencyManagement`、`mall-server` 依赖**都已含它**，`@MapperScan("com.mallx.**.mapper")` 也能扫到。
> **所以「第 2 步补建模块」和「第 4 步建模块骨架」都免做**，直接从第 3 步开始。

---

## 2. 第 0 步：前置检查（15 分钟）

### 2.1 起环境

```powershell
# 1) Docker Desktop 要运行 + 容器 healthy
& "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" ps --filter name=mallx-postgres

# 2) 起应用（必须显式指定端口，本机 SERVER__PORT 有污染）
cd D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o spring-boot:run -pl mall-server "-Dspring-boot.run.arguments=--server.port=8080"
```

### 2.2 确认 RBAC 数据已经就位

```powershell
& "C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe" exec -e PGCLIENTENCODING=UTF8 mallx-postgres `
  psql -U mallx -d mallx -c "SELECT r.code AS role, p.code AS perm FROM roles r JOIN role_permissions rp ON rp.role_id=r.id JOIN permissions p ON p.id=rp.permission_id ORDER BY r.id, p.id;"
```

**预期看到**（Day 03 已种好）：

| role | perm |
|---|---|
| SUPER_ADMIN | product:list / product:detail / product:create / product:update / product:delete / order:list / order:ship / user:list |
| PRODUCT_ADMIN | product:list / product:detail / product:create / product:update / product:delete |
| ORDER_ADMIN | order:list / order:ship |

以及管理员账号：

```powershell
& "..." exec -e PGCLIENTENCODING=UTF8 mallx-postgres psql -U mallx -d mallx -c "SELECT a.id, a.username, a.password, r.code FROM admins a LEFT JOIN admin_roles ar ON ar.admin_id=a.id LEFT JOIN roles r ON r.id=ar.role_id;"
```

**预期**：`1 | admin | {noop}admin123 | SUPER_ADMIN`

> 如果这里查出来是空的，说明 Day 03 的 `03-data.sql` 没跑全，回头补跑 RBAC 那一段（第 118~171 行）。

### 2.3 记下改动前的基线

```powershell
# 这个今天必须保持 200（白名单，不能被误伤）
$c = & curl.exe -s -o "$env:TEMP\b.txt" -w "%{http_code}" "http://localhost:8080/api/products"
Write-Host "GET /api/products => $c"
```

> ⚠️ **PowerShell 传 JSON 必须用文件 + `--data-binary "@file"`**（Day 06 踩过的坑：直接 `-d '{"a":1}'` 会被 PowerShell 剥掉引号，服务端解析失败 → 莫名 500）。今天所有写接口验收都这么做。

### 2.4 确认 `mall-admin` 模块是否存在

```powershell
Get-ChildItem "D:\MallX\backend\mallx" -Directory | Select-Object Name
```

**预期看到**：mall-common / mall-user / mall-product / mall-server / **mall-admin**（可能缺）。

> 缺了就在第 4 步补建，别硬塞进 mall-user——管理员和用户是两套体系，模块也该分开。

---

## 3. 第 1 步：新增 `RestAccessDeniedHandler`（10 分钟）

### 3.1 为什么要它

Day 06 建了 `RestAuthenticationEntryPoint`，负责"**没登录**"时返回 401。今天需要它的孪生兄弟，负责"**登录了但没权限**"时返回 403。

| 场景 | 异常 | 谁来处理 | 返回 |
|---|---|---|---|
| 没带 / token 无效 | `AuthenticationException` | `AuthenticationEntryPoint` | 401 |
| 登录了但权限不够 | `AccessDeniedException` | `AccessDeniedHandler` | 403 |

**不配 `AccessDeniedHandler` 会怎样？** Spring 默认返回 HTML 错误页（Whitelabel Error Page）——前后端分离下前端拿到 HTML，解析 JSON 会炸。

### 3.2 照着 `RestAuthenticationEntryPoint` 写

**文件**：`mall-common/src/main/java/com/mallx/common/security/RestAccessDeniedHandler.java`

```java
package com.mallx.common.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 已登录但权限不足 → 统一 403 JSON。
 * <p>
 * 与 RestAuthenticationEntryPoint 的分工：
 *   - 没登录 / token 无效 → AuthenticationException → EntryPoint → 401
 *   - 登录了但没权限       → AccessDeniedException   → 本类    → 403
 */
@Component
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);       // 403
        response.setContentType("application/json;charset=UTF-8");
        Result<Void> body = Result.error(ResultCode.FORBIDDEN);      // 复用 Day 04 预留的枚举
        response.getWriter().write(objectMapper.writeValueAsString(body));
    }
}
```

> **`ResultCode.FORBIDDEN`** 是 Day 04 就定义好的 `(403, "没有权限访问")`，直接用，别新建。
>
> **关于 `ObjectMapper` 的选型**：Boot 4 是 Jackson 双栈（Jackson 3 = `tools.jackson.*` 是 Spring 默认；Jackson 2 = `com.fasterxml.jackson.*` 仍在）。这里**跟 Day 06 的 `RestAuthenticationEntryPoint` 保持一致，用 `com.fasterxml.jackson.databind.ObjectMapper`**，避免踩双栈的坑。`writeValueAsString` 在两套里签名相同。

### 3.3 挂到 SecurityConfig

**文件**：`mall-common/src/main/java/com/mallx/common/config/SecurityConfig.java`

三处改动：

```java
// ① 类上加注解，开启方法级鉴权
@Configuration
@EnableWebSecurity
@EnableMethodSecurity                       // ← 新增：让 @PreAuthorize 生效
public class SecurityConfig {
```

```java
// ② 构造器多注入一个
private final RestAccessDeniedHandler restAccessDeniedHandler;

public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter,
                      RestAuthenticationEntryPoint restAuthenticationEntryPoint,
                      RestAccessDeniedHandler restAccessDeniedHandler) {   // ← 新增
    this.jwtAuthenticationFilter = jwtAuthenticationFilter;
    this.restAuthenticationEntryPoint = restAuthenticationEntryPoint;
    this.restAccessDeniedHandler = restAccessDeniedHandler;                // ← 新增
}
```

```java
// ③ exceptionHandling 里补上 accessDeniedHandler，白名单加 admin 登录入口
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/auth/login", "/api/auth/admin/login", "/api/hello", "/error").permitAll()
    .requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
    .anyRequest().authenticated()
)
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(restAuthenticationEntryPoint)     // 401
    .accessDeniedHandler(restAccessDeniedHandler))              // ← 新增：403
```

> **`@EnableMethodSecurity` 是必须的**。不加这个注解，`@PreAuthorize` 会被**静默忽略**——不报错、不生效，权限形同虚设。这是今天最容易埋雷的地方。
>
> **导入路径**（已用 javap 核实 Security 7.1.1）：
> - `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`
> - `org.springframework.security.config.annotation.web.configuration.EnableWebSecurity`

---

## 4. 第 2 步：补建 `mall-admin` 模块（20 分钟）

> 如果 `mall-admin` 已存在，只做 4.2。

### 4.1 建模块骨架

**`mall-admin/pom.xml`**（照抄 mall-user 的 pom，改 artifactId）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.mallx</groupId>
        <artifactId>mallx</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </parent>

    <artifactId>mall-admin</artifactId>
    <name>mall-admin</name>
    <description>后台管理模块：管理员账号 + RBAC 权限</description>

    <dependencies>
        <dependency>
            <groupId>com.mallx</groupId>
            <artifactId>mall-common</artifactId>
            <version>0.0.1-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>com.baomidou</groupId>
            <artifactId>mybatis-plus-spring-boot4-starter</artifactId>
        </dependency>
    </dependencies>
</project>
```

> **注意版本号**：`mybatis-plus-spring-boot4-starter` 的版本应由父 POM 的 `<dependencyManagement>` 托管（Day 04 已配），所以这里**不写 `<version>`**。如果报 `version is missing`，就去父 POM 补托管。

在**父 POM 的 `<modules>`** 里加：

```xml
<module>mall-admin</module>
```

在 **`mall-server/pom.xml`** 里加依赖（否则启动扫描不到这个模块的 Bean）：

```xml
<dependency>
    <groupId>com.mallx</groupId>
    <artifactId>mall-admin</artifactId>
    <version>0.0.1-SNAPSHOT</version>
</dependency>
```

### 4.2 确认包扫描能覆盖到

看 `mall-server` 的启动类：

```java
@SpringBootApplication
@MapperScan("com.mallx.**.mapper")     // ← 必须能扫到 com.mallx.admin.mapper
public class MallXApplication { ... }
```

> 如果写的是具体包名（如 `com.mallx.product.mapper`），要补上 admin。用通配 `com.mallx.**.mapper` 最省事。

---

## 5. 第 3 步：RBAC 实体 + Mapper（40 分钟）

### 5.1 三个实体

**`mall-admin/src/main/java/com/mallx/admin/entity/Admin.java`**

```java
package com.mallx.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("admins")
public class Admin {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String username;
    private String password;
    private String nickname;
    private Integer status;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
```

**`Role.java`**（`roles` 表）：

```java
package com.mallx.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("roles")
public class Role {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String name;
    private String code;          // SUPER_ADMIN / PRODUCT_ADMIN / ORDER_ADMIN
    private String description;
    private Integer status;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
```

**`Permission.java`**（`permissions` 表）：

```java
package com.mallx.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("permissions")
public class Permission {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String name;
    private String code;          // product:create / product:update ...
    private String type;          // API / MENU / BUTTON
    private String path;
    private String method;
    private Long parentId;
    private Integer status;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
```

> **表名一律复数**（`admins` / `roles` / `permissions`），写错单数会运行时 `relation "xxx" does not exist`。Day 03 的约定。

### 5.2 Mapper 接口 + 关键 SQL

**`mall-admin/src/main/java/com/mallx/admin/mapper/AdminMapper.java`**

```java
package com.mallx.admin.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.admin.entity.Admin;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface AdminMapper extends BaseMapper<Admin> {

    /** 查一个管理员拥有的所有权限编码 */
    List<String> selectPermissionCodesByAdminId(@Param("adminId") Long adminId);

    /** 查一个管理员的角色编码 */
    List<String> selectRoleCodesByAdminId(@Param("adminId") Long adminId);
}
```

`RoleMapper`、`PermissionMapper` 都只要 `extends BaseMapper<Role>` / `<Permission>` + `@Mapper`。

**对应 XML** —— 文件：`mall-admin/src/main/resources/mapper/AdminMapper.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
        "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="com.mallx.admin.mapper.AdminMapper">

    <!-- 管理员 → 角色 → 权限，两张中间表穿过去 -->
    <select id="selectPermissionCodesByAdminId" resultType="java.lang.String">
        SELECT DISTINCT p.code
        FROM admin_roles ar
                 JOIN role_permissions rp ON rp.role_id = ar.role_id
                 JOIN permissions p        ON p.id = rp.permission_id
        WHERE ar.admin_id = #{adminId}
          AND p.status = 1
    </select>

    <select id="selectRoleCodesByAdminId" resultType="java.lang.String">
        SELECT r.code
        FROM admin_roles ar
                 JOIN roles r ON r.id = ar.role_id
        WHERE ar.admin_id = #{adminId}
          AND r.status = 1
    </select>

</mapper>
```

> **为什么不用 `selectList` + Java 循环？** 那是 3 次网络往返 + 内存拼装。一条 join SQL 一次拿全，是最常见的做法。顺带理解 `DISTINCT`：多个角色权限重叠时去重。
>
> **确认 XML 能被扫到**：`application.yml` 里应有
> ```yaml
> mybatis-plus:
>   mapper-locations: classpath*:mapper/**/*.xml
> ```
> 注意 `classpath*:`（带星号）——单模块 `classpath:` 扫不到兄弟模块 jar 里的 XML。

---

## 6. 第 4 步：管理员认证（40 分钟）

### 6.1 `AdminLoginUser` —— 关键在 `getAuthorities()`

**文件**：`mall-admin/src/main/java/com/mallx/admin/security/AdminLoginUser.java`

这是 Day 06 `LoginUser` 的孪生版本，**核心区别是 `getAuthorities()` 不再返回空集合**——权限真正生效就在这里。

```java
package com.mallx.admin.security;

import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;

@Getter
public class AdminLoginUser implements UserDetails {

    private final Long adminId;
    private final String username;
    private final String password;
    private final Integer status;

    /** 权限集合：形如 [ROLE_SUPER_ADMIN, product:create, product:update, ...] */
    private final List<String> permissions;

    public AdminLoginUser(Long adminId, String username, String password,
                          Integer status, List<String> permissions) {
        this.adminId = adminId;
        this.username = username;
        this.password = password;
        this.status = status;
        this.permissions = permissions;
    }

    /**
     * ★ 今天最重要的一个方法 ★
     * 把字符串权限集合翻译成 Security 认识的 GrantedAuthority。
     * 这里返回什么，@PreAuthorize("hasAuthority('xxx')") 就能匹配什么。
     */
    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return permissions.stream()
                .map(SimpleGrantedAuthority::new)
                .toList();
    }

    @Override
    public String getPassword() {
        return password;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        return true;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }

    @Override
    public boolean isEnabled() {
        return status != null && status == 1;
    }
}
```

> ⚠️ **`ROLE_` 前缀的坑（必读）**：
> - `hasAuthority('product:create')` —— **精确匹配**，字符串必须一模一样
> - `hasRole('SUPER_ADMIN')` —— 会**自动加 `ROLE_` 前缀**，实际找的是 `ROLE_SUPER_ADMIN`
>
> 所以同一个字符串 `ROLE_SUPER_ADMIN`，`hasAuthority("ROLE_SUPER_ADMIN")` 能匹配，`hasRole("SUPER_ADMIN")` 也能匹配。混着写极易"明明有权限却 403"。
> **本项目约定：统一用 `hasAuthority` + 完整字符串，不碰 `hasRole`。**

### 6.2 `AdminAccountService`

**文件**：`mall-admin/src/main/java/com/mallx/admin/security/AdminAccountService.java`

```java
package com.mallx.admin.security;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.admin.entity.Admin;
import com.mallx.admin.mapper.AdminMapper;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 管理员账号查询 + 权限拼装。
 * ⚠️ 刻意【不实现】UserDetailsService —— 原因见 6.3（这是今天的核心陷阱）。
 */
@Service
public class AdminAccountService {

    private final AdminMapper adminMapper;

    public AdminAccountService(AdminMapper adminMapper) {
        this.adminMapper = adminMapper;
    }

    public AdminLoginUser findByUsername(String username) {
        // ① 查 admins 表
        Admin admin = adminMapper.selectOne(new LambdaQueryWrapper<Admin>()
                .eq(Admin::getUsername, username));
        if (admin == null) {
            throw new UsernameNotFoundException("管理员不存在: " + username);
        }

        // ② 拼权限集合：权限码 + 角色码（角色加 ROLE_ 前缀）
        List<String> permissions = new ArrayList<>(
                adminMapper.selectPermissionCodesByAdminId(admin.getId()));
        for (String roleCode : adminMapper.selectRoleCodesByAdminId(admin.getId())) {
            permissions.add("ROLE_" + roleCode);        // SUPER_ADMIN → ROLE_SUPER_ADMIN
        }

        return new AdminLoginUser(admin.getId(), admin.getUsername(),
                admin.getPassword(), admin.getStatus(), permissions);
    }
}
```

**和 Day 06 的 `UserDetailsServiceImpl` 对照着看，差别就两处**：

| | `UserDetailsServiceImpl`（mall-user） | `AdminAccountService`（mall-admin） |
|---|---|---|
| 实现接口 | `implements UserDetailsService` | **不实现**（就一个普通业务类） |
| 方法 | `loadUserByUsername`（`@Override`，被 Security 回调） | `findByUsername`（**被我们自己调用**） |
| 查的表 | `users` | `admins` |
| 权限 | 返回空集合 | **联查 5 张 RBAC 表拼出真实权限** |
| 谁调用它 | Spring Security 的 `DaoAuthenticationProvider` | `AdminAuthController` 自己 |

> **为什么权限不在 `AdminLoginUser.getAuthorities()` 里现查？** 因为查询是 `AdminAccountService` 的职责——
> `AdminLoginUser` 只是个**数据载体**，构造时就拿到了拼好的权限集合，`getAuthorities()` 只做"字符串 → `GrantedAuthority`"的翻译。职责分明。

> ⚠️ **原来这里叫 `AdminUserDetailsService` 并实现 `UserDetailsService`，那条路已验证走不通**——
> 见下一节 6.3，那里有字节码级的证据。


### 6.3 ⚠️ 为什么 admin 的类**不能**实现 `UserDetailsService`（今天最隐蔽的陷阱）

这是今天**最容易走错、而且错得最隐蔽**的一步。我把 Spring Security 7.1.1 的字节码
反编译出来看过，`InitializeUserDetailsBeanManagerConfigurer` 的逻辑是这样的：

```java
String[] beans = context.getBeanNamesForType(UserDetailsService.class);
if (auth.isConfigured()) { ...warn...; return; }
if (beans.length == 0) return;
if (beans.length > 1) {
    log.warn("Found %s UserDetailsService beans, with names %s. Global Authentication Manager"
           + " will not use a UserDetailsService for username/password login."
           + " Consider publishing a single UserDetailsService bean.");
    return;                                   // ← 直接返回，什么都不注册
}
// ★ 只有「恰好 1 个」才走到这里
auth.authenticationProvider(new DaoAuthenticationProvider(uds));
log.info("Global AuthenticationManager configured with UserDetailsService bean with name %s");
```

**三个要命的事实**：

| 事实 | 说明 |
|---|---|
| 判据是 `getBeanNamesForType`（**按类型数**） | 不看你 Bean 叫什么名字，只看容器里有几个 `UserDetailsService` **类型**的 Bean |
| `@Primary` **救不了** | 那段代码用的是 `getBeanNamesForType`，不是 `getBeanProvider(...).getIfUnique()`，`@Primary` 在这里**不参与判断** |
| 具名 `@Bean` **也救不了** | 换汤不换药——类 `implements UserDetailsService`，它**按类型仍然是第二个** |

**错误做法的后果**：

```text
容器里有 2 个 UserDetailsService（UserDetailsServiceImpl + 你的 admin 那个）
      ↓
configure() 走 beans.length > 1 分支 → 打一条 WARN 后 return
      ↓
全局 AuthenticationManager 【没有】配上 DaoAuthenticationProvider
      ↓
Day 06 的 /api/auth/login 认证失效 ❌（ProviderNotFoundException / NPE）
```

**正确做法**：让 admin 那个类**根本不实现 `UserDetailsService`**（就是 6.2 的 `AdminAccountService`）：

```text
容器里只有 1 个 UserDetailsService（mall-user 的 UserDetailsServiceImpl）
      ↓
自动装配正常工作
      ↓
INFO: Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl
      ↓
Day 06 的 /api/auth/login 照常 ✅
```

> **不实现那个接口会损失什么吗？不会。**
> `UserDetailsService` 的唯一用途是"**被 `DaoAuthenticationProvider` 回调**"。
> 而 admin 登录（第 5 步）是**手动流程**：自己查人 → 自己 `passwordEncoder.matches` 比密码 → 自己签 token。
> 既然从不经过 provider，实现这个接口就是**白担风险**。
>
> **怎么验证做对了？** 第 7 步启动应用，日志里必须出现这一行（INFO 级别，不是 WARN）：
> ```text
> Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl
> ```
> 如果这一行**消失了**、换成 `Found 2 UserDetailsService beans...` 的 WARN，就是踩了这个坑。

> ℹ️ 因此 `config/AdminSecurityConfig.java`（原先用来注册"具名 Bean"）**不需要建了**——
> 那条路已验证走不通，`AdminAccountService` 直接 `@Service` 即可。


---

## 7. 第 5 步：admin 登录入口（40 分钟）

### 7.1 思路：另开接口，别改 Day 06 的

Day 06 的 `POST /api/auth/login` 走 Security 自动装配的 `AuthenticationManager`，它绑死 `users` 那条链路。**硬改会让两个体系纠缠**。

**干净的做法**：新开 `POST /api/auth/admin/login`，内部手动查人 + 比密码 + 签 token。

**先给 `JwtUtil` 加个带 `perms` 的重载**（`mall-common`）：

```java
/** 给管理员签发 token：带 type=ADMIN 标记 + ★权限码数组 */
public String generateForAdmin(Long adminId, String username, List<String> permissions) {
    Date now = new Date();
    Date expiration = new Date(now.getTime() + props.getExpireMinutes() * 60_000L);
    return Jwts.builder()
            .subject(String.valueOf(adminId))
            .claim("username", username)
            .claim("type", "ADMIN")             // ← 区分身份来源
            .claim("perms", permissions)        // ★ 关键：权限跟着 token 走
            .issuedAt(now).notBefore(now).expiration(expiration)
            .signWith(key)
            .compact();
}
```

需要新增的 import：`import java.util.List;`

> 同时给 Day 06 的 `generate` 补一行 `.claim("type", "USER")`，两套身份就分得清了。
> C 端用户**不带 `perms`**，还原出来就是空权限集合——**行为与 Day 06 完全一致，不会影响已有功能**。

> **`perms` 里装什么？** 就是 `AdminLoginUser` 那串权限码 + `ROLE_` 开头的角色码，**和 `getAuthorities()` 是同一份数据**。
> 顺带理解一件事：JWT 的 Payload 只是 **Base64 编码，不是加密**——任何人拿到 token 都能解出权限列表。
> 这没关系：**权限列表不是秘密，签名才是防线**。改一个字符，验签就失败。


**`mall-admin/src/main/java/com/mallx/admin/controller/AdminAuthController.java`**

```java
package com.mallx.admin.controller;

import com.mallx.admin.security.AdminAccountService;
import com.mallx.admin.security.AdminLoginUser;
import com.mallx.common.api.Result;
import com.mallx.common.dto.LoginDTO;
import com.mallx.common.security.JwtProperties;
import com.mallx.common.security.JwtUtil;
import com.mallx.common.vo.LoginVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "管理员认证")
@RestController
@RequestMapping("/api/auth/admin")
public class AdminAuthController {

    private final AdminAccountService adminAccountService;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final JwtProperties jwtProperties;

    public AdminAuthController(AdminAccountService adminAccountService,
                               PasswordEncoder passwordEncoder,
                               JwtUtil jwtUtil,
                               JwtProperties jwtProperties) {
        this.adminAccountService = adminAccountService;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtil = jwtUtil;
        this.jwtProperties = jwtProperties;
    }

    @Operation(summary = "管理员登录")
    @PostMapping("/login")
    public Result<LoginVO> adminLogin(@RequestBody @Valid LoginDTO dto) {
        // ① 查人（查不到 → 统一提示，不泄露"这个账号不存在"）
        AdminLoginUser admin;
        try {
            admin = adminAccountService.findByUsername(dto.getUsername());
        } catch (UsernameNotFoundException e) {
            throw new BadCredentialsException("用户名或密码错误");
        }

        // ② 比密码（DelegatingPasswordEncoder 按 {noop}/{bcrypt} 前缀自动选算法）
        if (!passwordEncoder.matches(dto.getPassword(), admin.getPassword())) {
            throw new BadCredentialsException("用户名或密码错误");
        }

        // ③ ★ 必须手动检查启用状态 —— 漏了这行，被禁用的管理员照样能登录
        if (!admin.isEnabled()) {
            throw new BadCredentialsException("账号已被禁用");
        }

        // ④ 签发 token：把权限集合一起装进去，过滤器第 5 步才有东西可还原
        String token = jwtUtil.generateForAdmin(
                admin.getAdminId(), admin.getUsername(), admin.getPermissions());

        return Result.ok(new LoginVO(token, "Bearer",
                jwtProperties.getExpireMinutes() * 60,
                admin.getAdminId(), admin.getUsername(), "管理员"));
    }
}
```

> ⚠️ **第 ③ 步的 `isEnabled()` 不是可选项。**
> Day 06 走的是 Security 的 `DaoAuthenticationProvider`，它会**自动**调用 `isEnabled()` / `isAccountNonLocked()`
> 等四个方法检查账号状态，所以你什么都不用写。
> 但 admin 今天是**手动流程、绕开了 provider**——**状态检查得自己来**。
> 漏了这一行，`status = 0`（已禁用）的管理员照样能登录成功。
> **这就是"不走标准链路"必须自己补的账。**

> **`LoginDTO` / `LoginVO` 在 `mall-user` 里**，所以 `mall-admin` 的 pom **要么加 `mall-user` 依赖**，要么把这两个类挪到 `mall-common`。
> **推荐挪到 `mall-common`**（它们是与业务无关的通用结构），这样 `mall-admin`、`mall-user` 都能用，也不用让 admin 依赖 user。
> 挪的时候记得**同步改 `mall-user` 里的 import**（`com.mallx.user.dto.LoginDTO` → `com.mallx.common.dto.LoginDTO`）。

> **`BadCredentialsException`** 是 `AuthenticationException` 的子类，Day 06 的 `GlobalExceptionHandler` 已经能接住它 → 返回 401。**不用自己再写异常处理。**

### 7.2 ★ 改 `JwtAuthenticationFilter`：把 token 里的权限**还原**出来

**文件**：`mall-common/src/main/java/com/mallx/common/security/JwtAuthenticationFilter.java`

**这一步不做，前面所有工作都白费**——`@PreAuthorize` 检查的是 `Authentication#getAuthorities()`，
而现在过滤器塞进去的是 `List.of()`（**空集合**，Day 06 第 57 行，注释里写着"Day 07 再接 RBAC"）。
空集合的后果就是：**所有人、所有写接口，一律 403**。

**只改中间那几行**（其余保持 Day 06 原样）：

```java
// ① 解析 token
Claims claims = jwtUtil.parse(token);
Long userId = Long.valueOf(claims.getSubject());
String username = claims.get("username", String.class);

// ② ★ 新增：把 token 里的 perms 还原成 Security 认识的 GrantedAuthority
List<GrantedAuthority> authorities = new ArrayList<>();
List<?> perms = claims.get("perms", List.class);
if (perms != null) {
    for (Object p : perms) {
        authorities.add(new SimpleGrantedAuthority(String.valueOf(p)));
    }
}

// ③ 登记身份：第三位从 List.of() 换成 authorities
//    ⚠️ 三参数构造器 = 已认证状态，别误用两参数那个
UsernamePasswordAuthenticationToken authentication =
        new UsernamePasswordAuthenticationToken(userId, null, authorities);
```

**新增 import**：

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import java.util.ArrayList;
```

> **为什么 C 端用户不受影响？** C 端的 token 里**没有 `perms`**，`claims.get("perms", List.class)`
> 返回 `null` → `authorities` 是空列表 → 和 Day 06 的 `List.of()` 效果**完全一样**。**零回归风险。**
>
> **验证会连带验到**（第 7 步验收）：`demo` 的 token 调写接口 → **403**（空权限，正确）；
> `admin` 的 token → **200**（有 `product:create`，正确）。两个结果不同，才说明权限真的传进来了。

### 7.3 白名单已在 3.3 步加好

确认 `SecurityConfig` 里有 `"/api/auth/admin/login"`。

---

## 8. 第 6 步：商品写接口（60 分钟）

### 8.1 两个 DTO

**`ProductCreateDTO.java`**：

```java
package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ProductCreateDTO {

    @NotNull(message = "分类不能为空")
    private Long categoryId;

    private Long brandId;

    @NotBlank(message = "商品名称不能为空")
    @Size(max = 100, message = "商品名称不能超过 100 字")
    private String name;

    @Size(max = 200, message = "副标题不能超过 200 字")
    private String subtitle;

    private String description;

    private String mainImage;

    /** 1=上架 0=下架；不传默认上架 */
    private Integer status;
}
```

**`ProductUpdateDTO.java`**：

```java
package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ProductUpdateDTO {

    @NotBlank(message = "商品名称不能为空")
    @Size(max = 100, message = "商品名称不能超过 100 字")
    private String name;

    private String subtitle;

    private String description;

    private String mainImage;

    /** 1=上架 0=下架 */
    private Integer status;
}
```

> `@NotBlank` / `@NotNull` / `@Size` 来自 **`jakarta.validation.constraints`**（不是 javax！Spring Boot 3+ 已迁到 jakarta）。Day 04 已通过 `spring-boot-starter-validation` 引入。

### 8.2 Service 加三个方法

**`ProductService`** 接口追加：

```java
/** 新增商品，返回新 id */
Long createProduct(ProductCreateDTO dto);

/** 修改商品（不存在则抛 404） */
void updateProduct(Long id, ProductUpdateDTO dto);

/** 删除商品（不存在则抛 404） */
void deleteProduct(Long id);
```

**`ProductServiceImpl`** 实现：

```java
@Override
public Long createProduct(ProductCreateDTO dto) {
    // ① 提前校验分类（否则要等 DB 外键约束才炸，错误信息也难看）
    if (categoryMapper.selectById(dto.getCategoryId()) == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "分类不存在");
    }

    Product product = new Product();
    BeanUtils.copyProperties(dto, product);
    if (product.getStatus() == null) {
        product.setStatus(1);                       // 默认上架
    }
    // ② createdAt/updatedAt 由 MyMetaObjectHandler 自动填，不用手写
    this.save(product);
    return product.getId();                         // ★ save 后 id 会回填到实体
}

@Override
public void updateProduct(Long id, ProductUpdateDTO dto) {
    Product exist = this.getById(id);
    if (exist == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
    }
    Product update = new Product();
    BeanUtils.copyProperties(dto, update);
    update.setId(id);                               // 必须带 id，否则 updateById 不知道改谁
    this.updateById(update);
}

@Override
public void deleteProduct(Long id) {
    if (this.getById(id) == null) {
        throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
    }
    this.removeById(id);
}
```

> ⭐ **`this.save(product)` 之后 `product.getId()` 有值**——MyBatis-Plus 把数据库生成的自增主键**回填**到实体了。必须体会这个（可以打个 log 看它是不是 null）。
>
> **为什么不用写 `setCreatedAt`？** 因为 Day 04 配了 `MyMetaObjectHandler`，`@TableField(fill = FieldFill.INSERT)` 的字段会自动填。

> **课下思考题**：`BeanUtils.copyProperties(dto, update)` 会把 dto 的 `null` 字段也拷进去吗？如果用户只想改状态、不传 name 会怎样？（提示：目前 `@NotBlank` 强制 name 必填，所以不出问题——但以后放宽了，这就是个 bug。）

### 8.3 Controller 加三个写接口

**`ProductController`** 追加：

```java
@Operation(summary = "新增商品（需 product:create 权限）")
@PostMapping
@PreAuthorize("hasAuthority('product:create')")
public Result<Long> create(@RequestBody @Valid ProductCreateDTO dto) {
    return Result.ok(productService.createProduct(dto));
}

@Operation(summary = "修改商品（需 product:update 权限）")
@PutMapping("/{id}")
@PreAuthorize("hasAuthority('product:update')")
public Result<Void> update(@PathVariable Long id, @RequestBody @Valid ProductUpdateDTO dto) {
    productService.updateProduct(id, dto);
    return Result.ok();
}

@Operation(summary = "删除商品（需 product:delete 权限）")
@DeleteMapping("/{id}")
@PreAuthorize("hasAuthority('product:delete')")
public Result<Void> delete(@PathVariable Long id) {
    productService.deleteProduct(id);
    return Result.ok();
}
```

需要的 import：

```java
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.RequestBody;
```

> ⚠️ **白名单会误伤吗？** 看 Day 06 这行：
> ```java
> .requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
> ```
> 它**限定了 `HttpMethod.GET`**，所以 `POST`/`PUT`/`DELETE` 不受影响，会正常落到 `anyRequest().authenticated()`。**这就是 Day 06 特意写 `HttpMethod.GET` 的用意。**
> 课后验证：把 `HttpMethod.GET` 去掉会怎样？（`GET` 也要登录，C 端页面全挂）

### 8.4 用 `@AuthenticationPrincipal` 拿当前用户（了解即可）

今天不需要，但顺手看一眼——这正是 Day 06 埋的钩子：

```java
@PostMapping
@PreAuthorize("hasAuthority('product:create')")
public Result<Long> create(@RequestBody @Valid ProductCreateDTO dto,
                           @AuthenticationPrincipal Long userId) {   // ← principal 就是 filter 里塞的 userId
    return Result.ok(productService.createProduct(dto));
}
```

> **能直接注入 `Long`**，因为 `JwtAuthenticationFilter` 里 `new UsernamePasswordAuthenticationToken(userId, null, List.of())` —— 第一个参数就是 principal。**Token 的链路到这里闭环了。**
>
> ⚠️ import 用 **`org.springframework.security.web.bind.annotation.AuthenticationPrincipal`**（web 那个）。`core` 包下有个同名注解，是给别处用的，别导错。

---

## 9. 第 7 步：构建、启动与验收（40 分钟）

### 9.1 构建

```powershell
cd D:\MallX\backend\mallx
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o install -DskipTests
```

> ⚠️ **新增了 mall-admin 模块，必须 `install`**，`spring-boot:run` 才能找到它。
> ⚠️ **改了代码要重启**。先杀掉旧进程（Maven 父进程 + fork 的 java 子进程都要杀），否则旧 class 还在跑。

### 9.2 启动

```powershell
& "D:\Maven\apache-maven-3.9.15\bin\mvn.cmd" -o spring-boot:run -pl mall-server "-Dspring-boot.run.arguments=--server.port=8080"
```

**启动日志里必须看到这一行（INFO）**：

```
Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl
```

> ⚠️ **这是漏洞 A 的验收点**。如果这行**消失了**，换成：
> ```
> WARN  Found 2 UserDetailsService beans, with names [...]. Global Authentication Manager
>       will not use a UserDetailsService for username/password login. Consider publishing
>       a single UserDetailsService bean.
> ```
> 说明有**两个** `UserDetailsService` 类型的 Bean → 全局 `AuthenticationManager` 没配上 provider
> → **Day 06 的 `/api/auth/login` 会挂**。对照 6.3 检查 `AdminAccountService` 是不是误加了 `implements UserDetailsService`。


### 9.3 八项验收

**准备 JSON 文件**（避开 PowerShell 引号坑）：

```powershell
$dir = "$env:TEMP\mallx-day07"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$enc = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText("$dir\admin-login.json", '{"username":"admin","password":"admin123"}', $enc)
[System.IO.File]::WriteAllText("$dir\demo-login.json",  '{"username":"demo","password":"demo123"}', $enc)
[System.IO.File]::WriteAllText("$dir\create.json",      '{"categoryId":1,"name":"Day07测试商品","subtitle":"验证写接口","status":1}', $enc)
[System.IO.File]::WriteAllText("$dir\update.json",      '{"name":"Day07测试商品-已改名","status":0}', $enc)
[System.IO.File]::WriteAllText("$dir\bad.json",         '{"categoryId":1,"name":""}', $enc)
```

**验收脚本**：

```powershell
$B = "http://localhost:8080"
$dir = "$env:TEMP\mallx-day07"
$out = @()

# ---- 准备 token ----
$adminRaw = & curl.exe -s -X POST "$B/api/auth/admin/login" -H "Content-Type: application/json" --data-binary "@$dir\admin-login.json"
$ADMIN_TOKEN = ($adminRaw | ConvertFrom-Json).data.token
$out += "[准备] admin token = $ADMIN_TOKEN"

$demoRaw = & curl.exe -s -X POST "$B/api/auth/login" -H "Content-Type: application/json" --data-binary "@$dir\demo-login.json"
$DEMO_TOKEN = ($demoRaw | ConvertFrom-Json).data.token
$out += "[准备] demo  token 段数 = $((([string]$DEMO_TOKEN).Split('.')).Count) (期望 3)"

# ---- [1] 匿名写 → 401 ----
$c = & curl.exe -s -o "$dir\o1.json" -w "%{http_code}" -X POST "$B/api/products" -H "Content-Type: application/json" --data-binary "@$dir\create.json"
$out += "[1] 匿名 POST /api/products         => $c (期望 401)"

# ---- [2] demo token 写 → 403 ----
$c = & curl.exe -s -o "$dir\o2.json" -w "%{http_code}" -X POST "$B/api/products" -H "Content-Type: application/json" -H "Authorization: Bearer $DEMO_TOKEN" --data-binary "@$dir\create.json"
$out += "[2] demo-token POST                => $c (期望 403)"
$out += "    响应 = $(Get-Content "$dir\o2.json" -Raw -Encoding utf8)"

# ---- [3] admin token 新建 → 200 + 新 id ----
$r3 = & curl.exe -s -X POST "$B/api/products" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" --data-binary "@$dir\create.json"
$out += "[3] admin-token POST               => $r3 (期望 code=200)"
$NEW_ID = ($r3 | ConvertFrom-Json).data
$out += "    新商品 id = $NEW_ID"

# ---- [4] 参数非法 → 400 ----
$c = & curl.exe -s -o "$dir\o4.json" -w "%{http_code}" -X POST "$B/api/products" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" --data-binary "@$dir\bad.json"
$out += "[4] 空名字 POST                    => $c (期望 400)"
$out += "    响应 = $(Get-Content "$dir\o4.json" -Raw -Encoding utf8)"

# ---- [5] 改不存在 id → 404 ----
$c = & curl.exe -s -o "$dir\o5.json" -w "%{http_code}" -X PUT "$B/api/products/999999" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" --data-binary "@$dir\update.json"
$out += "[5] PUT 不存在 id                  => $c (期望 404)"
$out += "    响应 = $(Get-Content "$dir\o5.json" -Raw -Encoding utf8)"

# ---- [6] 正常修改 ----
$r6 = & curl.exe -s -X PUT "$B/api/products/$NEW_ID" -H "Content-Type: application/json" -H "Authorization: Bearer $ADMIN_TOKEN" --data-binary "@$dir\update.json"
$out += "[6] PUT $NEW_ID                    => $r6 (期望 code=200)"

# ---- [7] 匿名读 → 仍 200（白名单未被破坏）----
$c = & curl.exe -s -o "$dir\o7.json" -w "%{http_code}" "$B/api/products"
$out += "[7] 匿名 GET /api/products         => $c (期望 200)"

# ---- [8] 删除 ----
$r8 = & curl.exe -s -X DELETE "$B/api/products/$NEW_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
$out += "[8] DELETE $NEW_ID                 => $r8 (期望 code=200)"

$out -join "`r`n" | Out-File "D:\MallX\learning\verify-day07-result.txt" -Encoding utf8
Get-Content "D:\MallX\learning\verify-day07-result.txt"
```

**预期结果表**（右列是 2026-09-17 的实测值）：

| # | 验收项 | 期望 | 实测 |
|---|---|---|---|
| 1 | 匿名 `POST /api/products` | HTTP **401** | HTTP 401 + `{"code":401,"message":"未登录或登录已过期"}` ✅ |
| 2 | demo token POST | HTTP **403** + `没有权限访问` | HTTP 403 + `{"code":403,"message":"没有权限访问"}` ✅ |
| 3 | admin token POST | code=200 + 新 id | HTTP 200 + `{"code":200,"data":6}` ✅ |
| 4 | 空名字 POST | code=**400** + `名称不能为空` | HTTP **200** + `{"code":400,"message":"名称不能为空"}` ✅ |
| 5 | PUT 不存在 id | code=**404** + `商品不存在` | HTTP **200** + `{"code":404,"message":"商品不存在"}` ✅ |
| 6 | 正常 PUT | code=200 | HTTP 200 + `{"code":200,"data":null}` ✅ |
| 7 | 匿名 GET /api/products | HTTP **200** | HTTP 200 ✅ |
| 8 | DELETE | code=200 | HTTP 200 + `{"code":200,"data":null}` ✅ |

> ⚠️ **注意 [4] / [5] 的 HTTP 状态码是 200，不是 400/404** —— 这不是 bug，是**项目当前的既定约定**：
> 只有 Security 层的失败（`RestAuthenticationEntryPoint` / `RestAccessDeniedHandler`）才用真实 HTTP 状态码
> （401/403）；业务异常与参数校验走 `GlobalExceptionHandler`，而 `handleBusinessException` /
> `handleVaildException` **没有加 `@ResponseStatus`** → HTTP 200，业务码放在 body 的 `code` 字段里。
>
> 两种约定都常见，但**必须自洽**：要么全部"HTTP 200 + 业务码"，要么 HTTP 状态码与业务码一一对应。
> 现在是**混合**的。要不要统一？如果想让 [4]/[5] 也返回真实 400/404，只需给那两个 handler 各加一行：
> ```java
> @ResponseStatus(HttpStatus.BAD_REQUEST)   // 加在 handleVaildException 上
> @ResponseStatus(HttpStatus.NOT_FOUND)     // 加在 handleBusinessException 上 —— ⚠️ 但它对所有业务异常都生效
> ```
> 注意 `handleBusinessException` 是所有业务异常的公共出口（`BusinessException` 里带 code），
> 加死 `@ResponseStatus` 会把"分类不存在(404)"和"库存不足(409)"都压成同一个状态码。
> **今天先不动**，作为课后思考题。

---

## 10. 常见卡点速查

| 现象 | 原因 / 解法 |
|---|---|
| `@PreAuthorize` 完全不起作用，谁都能调 | ①**忘了 `@EnableMethodSecurity`**；②**过滤器没把权限还原进 `authorities`**（7.2 步）|
| **所有人调写接口都是 403**（连 admin 也是） | 最常见的错。`JwtAuthenticationFilter` 第三位传的是 `List.of()`，权限集合是空的。按 **7.2** 从 token 的 `perms` claim 还原出来 |
| 启动日志里 `Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl` **消失**，换成 `Found 2 UserDetailsService beans, ...` 的 **WARN** | 容器里有**两个** `UserDetailsService` **类型**的 Bean → 全局 `AuthenticationManager` 不装配 provider → **Day 06 的 `/api/auth/login` 会挂**。把 admin 那个类改成**不实现** `UserDetailsService`（6.2 / 6.3）；具名 `@Bean` 和 `@Primary` 都救不了 |
| 启动报 `NoUniqueBeanDefinitionException: UserDetailsService` | 同上，按 6.3 处理 |
| admin 登录成功，但调写接口 403 | ①`perms` claim 没塞进 token 或没还原（7.1 / 7.2）②`hasRole` 与 `hasAuthority` 混用、`ROLE_` 前缀问题 ③token 里的权限码与 DB 里的不一致（权限被改过？重新登录） |
| 被禁用的管理员（`status = 0`）照样能登录成功 | 手动流程绕开了 `DaoAuthenticationProvider`，它**不会自动调 `isEnabled()`** —— 必须自己判（7.1 第 ③ 步） |
| **`@PreAuthorize` 拒绝后返回 200 + `code=500`，而不是 403** | `GlobalExceptionHandler` 里的 `@ExceptionHandler(Exception.class)` 把 `AccessDeniedException`（`RuntimeException` 的子类）兜走了 → 403 出不来。解法：加 `@ExceptionHandler(AccessDeniedException.class)`（**更具体的类型优先，Spring 按异常继承深度选 handler**），在方法里**自己按"当前 Authentication 是否匿名"判定**：匿名 → 401，已认证 → 403。⚠️ 不要靠"原样再抛"去让 `ExceptionTranslationFilter` 接手 —— 那取决于 DispatcherServlet 会不会把异常放回过滤器链，多一层不确定；显式判定等价且稳 |
| 403 返回的是 HTML 错误页 | 没配 `AccessDeniedHandler`（第 3 步） |
| 403 返回的中文乱码 | `response.setContentType("application/json;charset=UTF-8")` 漏 charset |
| 400 校验失败但没提示信息 | `@Valid` 漏了，或 import 成 `javax.validation.*`（要用 `jakarta.validation.*`） |
| 新建商品后 `getId()` 是 null | 没配 `IdType.AUTO`，或 `@TableId` 写错 |
| **新建商品报 `duplicate key value violates unique constraint "products_pkey"`** | **种子数据的 id 序列没校准**。`03-data.sql` 用**显式 id**（1..5）插了数据，但 PostgreSQL 的序列不会因此前进，仍停在初始值 → 第一次业务 `INSERT` 时 `DEFAULT nextval(...)` 吐出 2，撞已有主键。修法：`SELECT setval(pg_get_serial_sequence('products','id'), COALESCE((SELECT MAX(id) FROM products),1));` —— 已补进 `03-data.sql` 第九节，8 张显式插 id 的表（categories/brands/products/product_skus/users/roles/permissions/admins）全量校准 |
| `relation "admin" does not exist` | 表名写单数了，`@TableName("admins")` |
| XML 里的 SQL 找不到（`Invalid bound statement (not found)`） | ①`mapper-locations` 写成 `classpath:`（必须 `classpath*:`，否则扫不到兄弟模块 jar）；②**XML 放进了 `src/main/java`**——Maven 只编译 `.java`，该目录下的 `.xml` 不会进 `target/classes`。**XML 必须放 `src/main/resources/mapper/`** |
| 接口声明了方法、XML 也有 `select`，仍报 `Invalid bound statement` | 接口方法名与 XML 的 `select id` **差一个字母都不行**（如单复数 `selectRoleCode` vs `selectRoleCodes`）。这是纯字符串匹配，IDE 不会提示 |
| 实体字段名与列名对不上（`column "xxx" does not exist`） | `map-underscore-to-camel-case` 只做**下划线↔驼峰**，不做**复数→单数**。DB 列 `method` 就写 `method`，别想当然写 `methods` |
| `install` 后仍然"找不到 mall-admin" | 父 POM `<modules>` 没加，或 `mall-server` 没加依赖 |
| 改完代码行为没变 | 旧进程还活着。杀掉 Maven 父进程 + java 子进程再重启 |
| PowerShell 调写接口报 500 / `Unexpected character` | JSON 被剥引号。用 `--data-binary "@file"`（Day 06 的坑） |

---

## 11. 本日成果自检清单

**已完成（2026-09-16 / 09-17 实测）**

- [x] `RestAccessDeniedHandler` 落位，403 返回统一 JSON
- [x] `SecurityConfig` 加了 `@EnableMethodSecurity` + `accessDeniedHandler` + admin 登录白名单
- [x] `mall-admin` 模块确认已存在 → 「补建模块」两步免做
- [x] 三个 RBAC 实体 + 三个 Mapper + `AdminMapper.xml`（放 `resources/mapper/`）落位；
      联查权限的 SQL 已用真实数据冒烟验证通过
- [x] `AdminLoginUser.getAuthorities()` 正确返回权限集合
- [x] `AdminAccountService` 落位，**刻意不实现 `UserDetailsService`**（否则会挂掉 Day 06 的登录，见 6.3）
- [x] `JwtUtil` 加 `generateForAdmin(adminId, username, permissions)`，token 带 `type=ADMIN` + `perms`
- [x] ★ `JwtAuthenticationFilter` 从 token 的 `perms` claim 还原权限（**7.2**，漏了这步全员 403）
- [x] `POST /api/auth/admin/login` 可用（2026-09-17 实测 200，token 含 `type=ADMIN` + 8 条 `perms`）
- [x] `LoginDTO` / `LoginVO` 挪到 `mall-common`（`mall-admin` 才引得到）
- [x] 启动日志出现 **INFO** `Global AuthenticationManager configured with UserDetailsService bean with name userDetailsServiceImpl`
- [x] C 端零回归：`demo`/`demo123` 登录 200、token 无 `perms`、`GET /api/products` 带/不带 token 均 200
- [x] ★ `GlobalExceptionHandler` 加 `@ExceptionHandler(AccessDeniedException.class)`，
      按"是否匿名"返回 401/403（否则 `@PreAuthorize` 的 403 会被兜成 500，见第 10 章速查表）
- [x] 两个 DTO：`ProductCreateDTO` / `ProductUpdateDTO`
- [x] `ProductService` 三个方法签名 + `ProductServiceImpl` 实现（`updateProduct` 用 `(Long id, ProductUpdateDTO)`）
- [x] 三个写接口 + `@PreAuthorize` 落位
- [x] 第 9 章 8 项验收全绿（2026-09-17 实测，见 §9.3 右列）
- [x] 补 `03-data.sql` 第九节：显式 id 种子的序列校准（否则首次 INSERT 必主键冲突）

**待完成（只剩"理解"这一层，没有代码了）**

- [ ] 理解并口述：认证 vs 授权 / `hasAuthority` 与 `hasRole` 的区别 / **权限放进 token 的代价是什么、另一条路怎么走**
- [ ] 课后思考题：`ProductUpdateDTO` 里 `@NotBlank` 该不该留？（决定"整体覆盖"还是"局部更新"）
- [ ] 课后思考题：HTTP 状态码与业务码要不要统一？（见 §9.3 的 ⚠️ 说明）
- [ ] Git：Day 07 提交；Day 06 的 `c78d907` 推送
- [ ] Git 提交（建议信息：`feat: Day 07 商品写接口 + RBAC 方法级鉴权`）


---

## 12. 做完之后

今天这套打通后，你已经有了一个**企业级的权限骨架**：

```text
Day 08+：把这套骨架撑开
  · 商品 SKU / 图片的多表写操作  → 学 @Transactional 事务
  · 购物车模块                    → 终于要挂 user_id 了，用 @AuthenticationPrincipal
  · 订单模块                      → 下单要扣库存、要事务、要状态机
  · 权限即时生效                  → 现在权限冻在 token 里，改角色要重登；改成"每请求现查 + Redis 缓存"
  · 操作日志                      → 谁在什么时候改了哪个商品（permissions 表可复用）
```

> **今天最该带走的一句话**：**认证解决"你是谁"，授权解决"你能干什么"，两者必须分开设计。** 混在一起写，是初学者最常见的架构债。

---

## 附：今日术语表

| 术语 | 一句话解释 |
|---|---|
| RBAC | Role-Based Access Control，基于角色的访问控制。用户→角色→权限，三层解耦 |
| `@PreAuthorize` | 方法级鉴权注解，在方法执行前用 SpEL 表达式判断能不能调 |
| `hasAuthority('x')` | 精确匹配权限字符串 `x` |
| `hasRole('x')` | 匹配 `ROLE_x`（自动加前缀，容易踩坑） |
| `GrantedAuthority` | Security 里"一个权限"的对象形式，本质是字符串的包装 |
| `AccessDeniedException` | 已登录但没权限时抛的异常（→ 403） |
| `AuthenticationException` | 认证失败时抛的异常（→ 401），`BadCredentialsException` 是它的子类 |
| 具名 Bean | 通过 `@Bean` 方法名确定 Bean 名字，绕开类型冲突 |
| 主键回填 | `save()` 后数据库生成的自增 id 自动写回实体对象 |
| `@Valid` | 触发 DTO 上的校验注解（`@NotBlank` 等） |
| `jakarta.validation` | Bean Validation 的包名（Boot 3+ 从 `javax` 迁过来的） |
