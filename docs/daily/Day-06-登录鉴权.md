# Day 06：登录鉴权（Spring Security 7 + JWT）

> 项目：MallX 企业级电商系统
> 学习方式：**你自己动手写代码**。本文档给出每一步要做什么 + 完整代码模板，你先独立尝试，卡住再对照或提问。
> 前置：Day 05 已就绪（商品模块可跑通；代码已推送到 `https://github.com/QIU-RONG/Mallx`）。
> 技术栈新增：Spring Security **7.1.1**（由 Boot 4.1.1 托管）、jjwt **0.13.0**。

---

## 0. 今日目标

让系统第一次能回答一个问题：**「你是谁？」**

Day 05 做的全是只读接口，谁都能调。今天之后：
- 用户能**登录**（用户名 + 密码换一个 token）
- 后续请求**带上 token**，服务端就能认出"这是用户 1（demo）"
- 没登录的人访问受保护接口 → 统一返回 `401 {code:401,message:"未登录或登录已过期"}`

**本日验收标准（做完自检）：**
- [ ] `POST /api/auth/login` 用 `demo/demo123` 能拿到 token
- [ ] 密码错误返回 401，不是 500 堆栈
- [ ] 不带 token 访问 `/api/users` → 401；带上正确 token → 200
- [ ] 篡改 / 伪造 / 过期 token → 401（不是 200，也不是 500）
- [ ] `/api/hello`、Swagger 页面仍能匿名访问（白名单生效）
- [ ] 响应里**没有 `Set-Cookie: JSESSIONID`**（证明是"无状态"）
- [ ] 理解并口述三件事：JWT 是什么/为什么无状态、Security 过滤器链怎么走、密码为什么要加密

**今天刻意不做（留给后面）：**
- 角色权限细分（`@PreAuthorize`、RBAC 表已建但不用）——Day 07+
- 刷新 token、登出黑名单、验证码、第三方登录
- 前端页面（Day 06 只做后端，用 curl / Swagger 验收）

---

## 1. 今日思路：三个词先分清

初学者最容易把这三个混成一坨，先钉死：

```text
认证 (Authentication)  —— 你是谁？         ← 今天做这个（登录）
授权 (Authorization)   —— 你能干什么？      ← Day 07+（RBAC 角色）
会话 (Session)         —— 你怎么证明"我还是刚才那个人"？  ← 今天用 JWT 解决
```

### 1.1 传统 Session 和 JWT 的区别（一句话）

| | Session 方案 | JWT 方案（今天用） |
|---|---|---|
| 状态存哪 | **服务端**内存/Redis 存一份 | **客户端**自己拿着，服务端不存 |
| 怎么证明 | 浏览器自动带 Cookie，服务端查表 | 请求头带 token，服务端**验签名**即可 |
| 扩展性 | 多台服务器要共享 Session | 天生无状态，加机器不用同步 |

> JWT = JSON Web Token，长得像 `xxxxx.yyyyy.zzzzz` 三段，中间用点分隔。
> **签名**是关键：服务端用自己的密钥给内容盖章，别人改一个字，章就对不上。

### 1.2 今天的完整流程图（心里要有这张图）

```text
① 前端 POST /api/auth/login  {username, password}
        ↓
② Security 用 UserDetailsService 去 users 表查人 + 校验密码
        ↓
③ 校验通过 → JwtUtil 用密钥签发 token（内含 userId、username、过期时间）
        ↓
④ 前端保存 token（localStorage / 内存）
        ↓
⑤ 之后每次请求带 header：Authorization: Bearer <token>
        ↓
⑥ 服务端的 JwtAuthenticationFilter 拦下 → 验签名 → 把"你是谁"放进 SecurityContext
        ↓
⑦ Controller / Service 里随时能拿到当前用户
```

### 1.3 今天要新建的文件一览（先有全局观）

| 模块 | 文件 | 干什么 |
|---|---|---|
| mall-common | `security/JwtProperties.java` | 读配置（密钥、过期时间） |
| mall-common | `security/JwtUtil.java` | **签发**和**解析** token |
| mall-common | `security/RestAuthenticationEntryPoint.java` | 没登录时返回统一 401 JSON |
| mall-common | `security/JwtAuthenticationFilter.java` | 从请求头验 token，塞进上下文 |
| mall-common | `config/SecurityConfig.java` | 安全总开关：白名单、无状态、过滤器挂载 |
| mall-user | `security/LoginUser.java` | 把 users 表的一行"翻译"成 Security 认识的对象 |
| mall-user | `security/UserDetailsServiceImpl.java` | Security 的"查人接口"实现 |
| mall-user | `dto/LoginDTO.java` / `vo/LoginVO.java` | 登录入参 / 出参 |
| mall-user | `controller/AuthController.java` | 登录接口 |

> 为什么安全配置放 `mall-common`？因为"所有模块的接口都要被保护"，这是**基础设施**（Day 04 定义过）。而 `mall-common` 被所有模块依赖，放这里一次生效。

---

## 2. 第 0 步：前置检查（10 分钟）

### 2.1 先起数据库

**Docker Desktop 现在没在运行**，先启动它（需要提权），等 `mallx-postgres` 变 healthy。

```bash
"C:/Users/TIE/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe" ps --filter name=mallx-postgres
```

### 2.2 确认 users 表里的密码长什么样

```bash
"C:/Users/TIE/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe" exec mallx-postgres psql -U mallx -d mallx -c "SELECT id, username, password, status FROM users ORDER BY id;"
```

预期看到 demo 用户是 **`{noop}demo123`** —— 注意那对花括号，它是个**前缀标记**，含义是"这个密码没加密，直接明文比"。这是 Day 03 种的种子数据，注释里就写了"后续 Day 实现认证时处理"。

> ⚠️ 如果这里还有 Day 04 验收时手工造的测试用户（alice / bob / carol / dave），它们的密码是**纯明文**（没有 `{noop}` 前缀）。这些用户登录时会报 `There is no PasswordEncoder mapped for the id "null"`（第 7 步会讲怎么处理，先记着）。

### 2.3 记下"加安全之前的基线"

加 Spring Security 后，**所有接口默认全部被拦**。先跑一遍确认现在一切正常，等会儿好对比：

```bash
curl http://localhost:8080/api/hello          # 200
curl http://localhost:8080/api/products       # 200，total=5
curl http://localhost:8080/api/users          # 200，能看到用户列表
```

> 这一步不是形式主义：改完之后如果 `/api/hello` 也变成 401，你就知道是**白名单**配错了，而不是业务写错了。

**实测基线（2026-09-13 11:37，加 Security 之前）**

| 接口 | 结果 |
|---|---|
| `GET /api/hello` | HTTP 200 |
| `GET /api/products` | HTTP 200，total = 5 |
| `GET /api/categories/tree` | HTTP 200，3 个根节点 |
| `GET /api/products/1` | HTTP 200 |
| `GET /api/users` | HTTP 200，total = 3（**顺带暴露了 password 字段，Day 06/07 要脱敏**） |
| `GET /v3/api-docs` | HTTP 200 |
| `GET /swagger-ui/index.html` | HTTP 200 |

> 加完 Security 后重跑这张表：**白名单里的应全部保持 200，`/api/users` 应变成 401**。凡是白名单接口变 401 的，都是白名单配错。

---

## 3. 第 1 步：加依赖

### 3.1 父 POM：加 jjwt 版本号 + BOM

**文件**：`backend/mallx/pom.xml`

在 `<properties>` 里加一行（和 `springdoc.version` 放一起）：

```xml
<jjwt.version>0.13.0</jjwt.version>
```

在 `<dependencyManagement>` → `<dependencies>` 里加 **BOM**（用 BOM 可以一次锁住 jjwt 三个构件的版本，不用写三遍）：

```xml
<!-- JWT 三件套统一版本（BOM） -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-bom</artifactId>
    <version>${jjwt.version}</version>
    <type>pom</type>
    <scope>import</scope>
</dependency>

<!--
  必修项：覆盖 jackson-databind 版本
  原因：jjwt-root（jjwt-jackson 的父 POM）在自己 POM 的 dependencyManagement 里
  把 jackson-databind 钉在 2.12.7.1。这个 pin 会盖过 Boot 经 <scope>import</scope>
  引入的 jackson-bom(2.21.5)，导致 databind 2.12.7.1 与 jackson-core 2.21.5 版本错位，
  而 jackson-dataformat-yaml 2.21.5 等都在调 2.21.x 的 databind API → 启动即
  NoSuchMethodError 的风险。
  解法：在「我们自己的」dependencyManagement 里用「直接条目」覆盖
  （直接条目优先于传递依赖 POM 的 dependencyManagement），与 Boot 托管的 Jackson 2 对齐。
-->
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>${jackson-2-bom.version}</version>
</dependency>
```

> **验证方法**（改完必跑）：
> ```bash
> bash mvnw.sh dependency:tree -pl mall-common | grep -iE "jjwt|jackson|spring-security"
> ```
> 期望看到：`spring-security-*:7.1.1`、`jjwt-*:0.13.0`、以及 **`jackson-databind:2.21.5`（不是 2.12.7.1）**。

### 3.2 mall-common：加 Security 与 jjwt 依赖

**文件**：`backend/mallx/mall-common/pom.xml`

在 `<dependencies>` 里加 4 个（**不写版本号**，由 Boot BOM 和 jjwt BOM 决定）：

```xml
<!-- Spring Security（安全框架本体） -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>

<!-- JWT：api 编译期用，impl/jackson 运行期才需要 -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-api</artifactId>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-impl</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-jackson</artifactId>
    <scope>runtime</scope>
</dependency>
```

### 3.3 ✅ 编译检查点

```bash
cd /d/MallX/backend/mallx
bash mvnw.sh compile -pl mall-common -am
```

首次会联网下载 Security 7.1.1（本地只有 7.0.3）和 jjwt 0.13.0（本地只有 0.12.3），走阿里云镜像，正常几十秒。

> **版本坑提醒**：不要自己去 `<version>` 里填 Spring Security 的版本。Boot 4.1.1 已经**托管**了配套的 7.1.1，手写版本反而容易和 Boot 对不上。同理，`springdoc` 用 3.1.1 也是查证过的搭配。

---

## 4. 第 2 步：配置项

**文件**：`mall-server/src/main/resources/application.yml`

追加一段（和 `springdoc` 平级）：

```yaml
# JWT 配置
mallx:
  jwt:
    # ⚠️ 生产环境必须通过环境变量 JWT_SECRET 注入，绝不能把真密钥提交进 Git
    # HS256 算法要求密钥 ≥ 32 字节（256 位），短了会抛 WeakKeyException
    secret: ${JWT_SECRET:mallx-dev-secret-key-please-change-me-2026}
    expire-minutes: 120
```

**为什么这么写？**

- `${JWT_SECRET:默认值}` 是 Spring 的占位符语法：优先读环境变量 `JWT_SECRET`，读不到就用冒号后的默认值。这样**本地开发不配置也能跑，生产用环境变量覆盖**。
- 密钥写死进 Git 是真实事故的常见原因——别人拿到密钥就能伪造任意用户的 token。今天先养成习惯。

---

## 5. 第 3 步：JwtUtil —— 签发与解析（新知识点①）

### 5.1 JWT 到底长什么样

```
eyJhbGciOiJIUzI1NiJ9 . eyJzdWIiOiIxIiwidXNlcm5hbWUiOiJkZW1vIn0 . 4mZ8k...
   ↑ Header（用什么算法签）      ↑ Payload（放了什么内容）         ↑ Signature（签名）
```

- Header/Payload 只是 **Base64 编码，不是加密**！任何人复制去解码都能看到内容。所以**绝不放密码、身份证号**。
- Signature 才是安全的关键：用密钥算出来的章，改了内容章就对不上。

Payload 里我们放三个东西：
- `sub`（subject）：用户 id（JWT 标准字段）
- `username`：用户名（自定义 claim）
- `exp`（expiration）：过期时间

### 5.2 JwtProperties —— 把 yml 配置变成 Java 对象

**路径**：`mall-common/src/main/java/com/mallx/common/security/JwtProperties.java`

```java
package com.mallx.common.security;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * JWT 配置项，对应 application.yml 里的 mallx.jwt.*
 */
@Data
@Component
@ConfigurationProperties(prefix = "mallx.jwt")
public class JwtProperties {

    /** 签名密钥（HS256 要求 ≥ 32 字节） */
    private String secret;

    /** token 有效期（分钟） */
    private long expireMinutes = 120;
}
```

> `@ConfigurationProperties(prefix = "...")` 会自动把 yml 里的 `mallx.jwt.secret` 绑到 `secret` 字段（**下划线和驼峰都能识别**）。加 `@Component` 就能被扫描成 Bean，不用再写 `@EnableConfigurationProperties`。

### 5.3 JwtUtil —— 你亲手写这两个方法

**路径**：`mall-common/src/main/java/com/mallx/common/security/JwtUtil.java`

```java
package com.mallx.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

/**
 * JWT 工具：签发 + 解析。
 * jjwt 0.12 起 API 大改（parserBuilder/parseClaimsJws 已弃用），本文档用的是新写法。
 */
@Component
public class JwtUtil {

    private final JwtProperties props;

    /** 密钥对象：构造一次复用，比每次现算便宜 */
    private final SecretKey key;

    public JwtUtil(JwtProperties props) {
        this.props = props;
        this.key = Keys.hmacShaKeyFor(props.getSecret().getBytes(StandardCharsets.UTF_8));
    }

    /** 签发 token */
    public String generate(Long userId, String username) {
        Date now = new Date();
        Date expiration = new Date(now.getTime() + props.getExpireMinutes() * 60_000L);

        // TODO ①：用 Jwts.builder() 造一个 token 并 compact() 成字符串
        //   需要设置的：subject = userId 的字符串形式
        //              claim("username", username)
        //              issuedAt(now) / expiration(expiration)
        //              signWith(key)
        return null;
    }

    /** 解析并验签；token 非法/过期会抛 JwtException（子类：ExpiredJwtException / SignatureException ...） */
    public Claims parse(String token) {
        // TODO ②：用 Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload()
        return null;
    }
}
```

**两个 TODO 的答案思路**（先自己写，写不出再看）：

<details>
<summary>展开参考实现</summary>

```java
public String generate(Long userId, String username) {
    Date now = new Date();
    Date expiration = new Date(now.getTime() + props.getExpireMinutes() * 60_000L);
    return Jwts.builder()
            .subject(String.valueOf(userId))
            .claim("username", username)
            .issuedAt(now)
            .expiration(expiration)
            .signWith(key)
            .compact();
}

public Claims parse(String token) {
    return Jwts.parser()
            .verifyWith(key)
            .build()
            .parseSignedClaims(token)
            .getPayload();
}
```
</details>

> **API 版本坑（2026-09-13 用 javap 对 0.13.0 jar 实测）**：网上大量教程还是老写法
> `Jwts.parser().setSigningKey(...).parseClaimsJws(...)`。实测结论：这些旧方法在 0.13.0 里
> **全部保留、但全部标记了 `@Deprecated`** → **能编译通过，只是 IDE 会划删除线、javac 会告警**，
> 并不会编译失败。之所以仍要用新写法，是因为废弃 API 会在将来大版本被真正移除。
> 新三件套：`parser()` → `verifyWith(key)` → `parseSignedClaims(token)`。
>
> **builder 侧同理**（本文档骨架用的就是新写法）：
>
> | 已废弃 | 改用 | 说明 |
> |---|---|---|
> | `setSubject(s)` | `subject(s)` | |
> | `setIssuedAt(d)` | `issuedAt(d)` | |
> | `setExpiration(d)` | `expiration(d)` | |
> | `setNotBefore(d)` | `notBefore(d)` | |
> | `setSigningKey(k)` | `verifyWith(k)` | parser 侧 |
> | `parseClaimsJws(s)` | `parseSignedClaims(s)` | parser 侧 |
>
> 命名规律：**新方法名 = claim 名，去掉 `set` 前缀**——因为这是 fluent builder（每个方法返回 `this`），
> 不是真正的 setter。
>
> `signWith(key)` 会自动根据密钥长度选算法（32 字节 → HS256）。想显式指定可写 `signWith(key, Jwts.SIG.HS256)`。

---

## 6. 第 4 步：让 Security 认识你的 users 表（新知识点②）

Spring Security **不认识**你的 `users` 表，它只认识一个接口：

```java
public interface UserDetailsService {
    UserDetails loadUserByUsername(String username) throws UsernameNotFoundException;
}
```

你要做的就是：**实现它，让它去查你的 users 表**。

### 6.1 LoginUser —— 把用户行翻译成 Security 的对象

**路径**：`mall-user/src/main/java/com/mallx/user/security/LoginUser.java`

```java
package com.mallx.user.security;

import lombok.Getter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.List;

/**
 * Security 眼里的"用户"。字段按需取，不必照搬实体。
 */
@Getter
public class LoginUser implements UserDetails {

    private final Long userId;
    private final String username;
    private final String password;
    private final Integer status;

    public LoginUser(Long userId, String username, String password, Integer status) {
        this.userId = userId;
        this.username = username;
        this.password = password;
        this.status = status;
    }

    /** 权限列表：今天先留空，Day 07 接 RBAC（roles/permissions 表）时再填 */
    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of();
    }

    @Override public boolean isAccountNonExpired()     { return true; }
    @Override public boolean isAccountNonLocked()      { return true; }
    @Override public boolean isCredentialsNonExpired() { return true; }

    /** status = 1 才算启用；这样被禁用的用户登录会直接失败 */
    @Override
    public boolean isEnabled() {
        return status != null && status == 1;
    }
}
```

> 注意 `getPassword()` / `getUsername()` 由 `@Getter` + 字段名自动满足接口要求（接口要的就是 `getPassword()`、`getUsername()`）。

### 6.2 UserDetailsServiceImpl —— 你要写的那段

**路径**：`mall-user/src/main/java/com/mallx/user/security/UserDetailsServiceImpl.java`

```java
package com.mallx.user.security;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.user.entity.User;
import com.mallx.user.mapper.UserMapper;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class UserDetailsServiceImpl implements UserDetailsService {

    private final UserMapper userMapper;

    public UserDetailsServiceImpl(UserMapper userMapper) {
        this.userMapper = userMapper;
    }

    @Override
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        // TODO ③：用 userMapper 按 username 查一条
        //   - 查不到 → throw new UsernameNotFoundException("用户不存在: " + username)
        //   - 查到   → return new LoginUser(它的 id, username, password, status)
        return null;
    }
}
```

<details>
<summary>展开参考实现</summary>

```java
@Override
public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
    User user = userMapper.selectOne(
            new LambdaQueryWrapper<User>().eq(User::getUsername, username));
    if (user == null) {
        throw new UsernameNotFoundException("用户不存在: " + username);
    }
    return new LoginUser(user.getId(), user.getUsername(), user.getPassword(), user.getStatus());
}
```
</details>

> **为什么查不到要抛 `UsernameNotFoundException` 而不是返回 null？**
> 因为 Security 靠异常判断认证失败。返回 null 会让它抛 `InternalAuthenticationServiceException`（500 级）。

---

## 7. 第 5 步：登录接口（POST /api/auth/login）

### 7.1 入参 DTO 与出参 VO

**路径**：`mall-user/src/main/java/com/mallx/user/dto/LoginDTO.java`

```java
package com.mallx.user.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.io.Serializable;

@Data
public class LoginDTO implements Serializable {

    @NotBlank(message = "用户名不能为空")
    private String username;

    @NotBlank(message = "密码不能为空")
    private String password;
}
```

**路径**：`mall-user/src/main/java/com/mallx/user/vo/LoginVO.java`

```java
package com.mallx.user.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class LoginVO {

    /** 令牌 */
    private String token;

    /** 固定 "Bearer"，配合前端拼 Authorization 头 */
    private String tokenType;

    /** 有效期（秒），方便前端做倒计时/提前刷新 */
    private long expiresIn;

    private Long userId;
    private String username;
    private String nickname;
}
```

> 注意：**VO 里绝对不能有 password**（Day 06 第一次真正体会 Day 05 讲的"VO 为什么要存在"）。

### 7.2 AuthController

**路径**：`mall-user/src/main/java/com/mallx/user/controller/AuthController.java`

```java
package com.mallx.user.controller;

import com.mallx.common.api.Result;
import com.mallx.common.security.JwtProperties;
import com.mallx.common.security.JwtUtil;
import com.mallx.user.dto.LoginDTO;
import com.mallx.user.entity.User;
import com.mallx.user.security.LoginUser;
import com.mallx.user.service.UserService;
import com.mallx.user.vo.LoginVO;
import jakarta.validation.Valid;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthenticationManager authenticationManager;
    private final JwtUtil jwtUtil;
    private final JwtProperties jwtProperties;
    private final UserService userService;

    // ⚠️ Security 7.1.1 起 getAuthenticationManager() **不再声明受检异常**（6.x 时是 throws Exception），
    //    所以这里**不需要** throws Exception。实测见下方 §7.4。
    public AuthController(AuthenticationConfiguration configuration,
                          JwtUtil jwtUtil,
                          JwtProperties jwtProperties,
                          UserService userService) {
        // ⚠️ AuthenticationManager 不要自己 new，从 AuthenticationConfiguration 里取
        this.authenticationManager = configuration.getAuthenticationManager();
        this.jwtUtil = jwtUtil;
        this.jwtProperties = jwtProperties;
        this.userService = userService;
    }

    @PostMapping("/login")
    public Result<LoginVO> login(@RequestBody @Valid LoginDTO dto) {
        // TODO ④：交给 Security 去认证
        //   authenticationManager.authenticate(
        //       new UsernamePasswordAuthenticationToken(dto.getUsername(), dto.getPassword()))
        //   认证失败会抛 AuthenticationException，由全局异常处理器统一转 401

        // TODO ⑤：认证成功后，从 Authentication 里取出 LoginUser，
        //   再调用 jwtUtil.generate(...) 签发 token，最后组装 LoginVO 返回
        return null;
    }
}
```

<details>
<summary>展开参考实现</summary>

```java
@PostMapping("/login")
public Result<LoginVO> login(@RequestBody @Valid LoginDTO dto) {
    Authentication authentication = authenticationManager.authenticate(
            new UsernamePasswordAuthenticationToken(dto.getUsername(), dto.getPassword()));

    LoginUser loginUser = (LoginUser) authentication.getPrincipal();
    String token = jwtUtil.generate(loginUser.getUserId(), loginUser.getUsername());

    User user = userService.getById(loginUser.getUserId());

    return Result.ok(new LoginVO(
            token,
            "Bearer",
            jwtProperties.getExpireMinutes() * 60,
            loginUser.getUserId(),
            loginUser.getUsername(),
            user != null ? user.getNickname() : null));
}
```
</details>

### 7.3 让登录失败也走统一格式

**文件**：`mall-common/src/main/java/com/mallx/common/exception/GlobalExceptionHandler.java`

追加一个 handler（**为什么必须有**：`AuthenticationException` 不是你的 `BusinessException`，不加这个就会被最底下的 `Exception` 兜底成 `500 fail`——验收标准明确要求登录失败是 401）：

```java
@ExceptionHandler(AuthenticationException.class)
@ResponseStatus(HttpStatus.UNAUTHORIZED)
public Result<Void> handleAuthenticationException(AuthenticationException e) {
    log.warn("认证失败：{}", e.getMessage());
    return Result.error(ResultCode.UNAUTHORIZED);
}
```

需要的 import：

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.bind.annotation.ResponseStatus;
```

> `@ResponseStatus(HttpStatus.UNAUTHORIZED)` 让 HTTP 状态码变成真 401（而不只是 body 里的 code=401）。前端拦截器靠 HTTP 状态码跳登录页，这样更规范。

### 7.4 两个实测澄清（2026-09-14 补）

**① `getAuthenticationManager()` 不需要 `throws Exception`**

用 `javap` 对 **Spring Security 7.1.1** 的 `spring-security-config-7.1.1.jar` 实测：

```
public org.springframework.security.authentication.AuthenticationManager getAuthenticationManager();
```

签名里**没有** `throws`。所以构造器写成下面这样是**对的、能编译**：

```java
public AuthController(AuthenticationConfiguration configuration, ...) {   // 不需要 throws Exception
    this.authenticationManager = configuration.getAuthenticationManager();
}
```

> ⚠️ 网上大量教程（Security 5.x / 6.x 时期）都带着 `throws Exception`，那是**旧版本**的签名。在 7.1.1 上加了也不报错（多余而已），但**不能反过来认为不写就编译不过**。

**② `LoginVO` 必须加 `@AllArgsConstructor`**

参考实现里是 `new LoginVO(token, "Bearer", ..., nickname)` 一次传 6 个参数。如果 `LoginVO` 上只有 `@Data`，**没有无参构造以外的构造器** → 编译报 "找不到符号"。所以类上要 `@Data` + `@AllArgsConstructor` 两个注解都写。

**③ `LoginVO.expiresIn` 用 `long` 而不是 `Long`**

配置项 `mallx.jwt.expire-minutes` 是 `long`（永远有值），VO 里也用基本类型 `long` 更合适。数据库主键那种"可能为 null"的场景才用 `Long`。

---

## 8. 第 6 步：JWT 过滤器 + SecurityConfig（新知识点③）

### 8.1 JwtAuthenticationFilter —— 每个请求的"安检口"

**路径**：`mall-common/src/main/java/com/mallx/common/security/JwtAuthenticationFilter.java`

```java
package com.mallx.common.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * 每个请求都过这里：带 token 就验、验过就"登记身份"。
 * OncePerRequestFilter = 保证一次请求只执行一次。
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String HEADER = "Authorization";
    private static final String PREFIX = "Bearer ";

    private final JwtUtil jwtUtil;

    public JwtAuthenticationFilter(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {

        String header = request.getHeader(HEADER);

        if (header != null && header.startsWith(PREFIX)) {
            String token = header.substring(PREFIX.length());
            try {
                // TODO ⑥：解析 token，取出 userId 和 username
                //   用 Claims claims = jwtUtil.parse(token);
                //     Long userId = Long.valueOf(claims.getSubject());
                //     String username = claims.get("username", String.class);

                // TODO ⑦：把身份登记到 SecurityContextHolder
                //   注意：Security 6/7 推荐先 createEmptyContext() 再 setContext(...)
                //   不要直接用 getContext().setAuthentication(...)
            } catch (JwtException | IllegalArgumentException e) {
                // 关键：这里【不能抛异常】！解析失败就当"没登录"，继续放行，
                // 由后面的 EntryPoint 统一返回 401。抛出去会变成 500。
                // ⚠️ 用字符串拼接，不要用 logger.debug("...{}", e.getMessage())
                //    因为 SLF4J 有 debug(String, Throwable) 重载，传 String 会报
                //    "String 无法转换为 Throwable"（2026-09-15 实测踩坑）
                logger.debug("JWT 解析失败：" + e.getMessage());
            }
        }

        chain.doFilter(request, response);
    }
}
```

<details>
<summary>展开 TODO ⑥⑦ 参考实现</summary>

```java
Claims claims = jwtUtil.parse(token);
Long userId = Long.valueOf(claims.getSubject());
String username = claims.get("username", String.class);

Authentication authentication =
        new UsernamePasswordAuthenticationToken(userId, null, List.of());
authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```
</details>

> **一个重要的设计选择**：这里我们**不去查数据库**，直接相信 token 里的 userId。
> 好处：每个请求零数据库开销，真正无状态。
> 代价：token 未过期前，改了用户状态/权限不会立即生效。
> 另一种写法是每次请求都 `userDetailsService.loadUserByUsername()` 查库（能实时反映，但每次请求一次 SQL）。Day 07 做 RBAC 时我们会回来讨论怎么权衡。

### 8.2 RestAuthenticationEntryPoint —— 未登录的统一 401

**路径**：`mall-common/src/main/java/com/mallx/common/security/RestAuthenticationEntryPoint.java`

```java
package com.mallx.common.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 未认证时的出口：返回与业务一致的 {code,message,data} JSON（而不是 Security 默认的 HTML 登录页）。
 */
@Component
public class RestAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void commence(HttpServletRequest request,
                         HttpServletResponse response,
                         AuthenticationException authException) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);          // HTTP 401
        response.setContentType("application/json;charset=UTF-8");        // 不写 charset 中文会乱码
        Result<Void> body = Result.error(ResultCode.UNAUTHORIZED);
        response.getWriter().write(objectMapper.writeValueAsString(body));
    }
}
```

### 8.3 SecurityConfig —— 今天最关键的一个类

**路径**：`mall-common/src/main/java/com/mallx/common/config/SecurityConfig.java`

```java
package com.mallx.common.config;

import com.mallx.common.security.JwtAuthenticationFilter;
import com.mallx.common.security.RestAuthenticationEntryPoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final RestAuthenticationEntryPoint restAuthenticationEntryPoint;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter,
                          RestAuthenticationEntryPoint restAuthenticationEntryPoint) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.restAuthenticationEntryPoint = restAuthenticationEntryPoint;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            // ① 关闭 CSRF：我们是无状态 token 认证，不靠 Cookie，不怕 CSRF
            .csrf(AbstractHttpConfigurer::disable)
            // ② 关掉默认的登录页 / Basic 弹窗（前后端分离用不上）
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // ③ 不使用 Session：每个请求都靠 token 自证
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // ④ 白名单 + 其余全部要登录（顺序重要，见下方说明）
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/login", "/api/hello", "/error").permitAll()
                .requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()
                .anyRequest().authenticated()
            )
            // ⑤ 未登录时返回统一 JSON 401
            .exceptionHandling(ex -> ex.authenticationEntryPoint(restAuthenticationEntryPoint))
            // ⑥ 把 JWT 过滤器插在用户名密码过滤器之前
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    /** 密码编码器：交给 Security 管理，登录时会自动用它比对 */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
```

### 8.4 三个必须理解的点

**① 白名单的顺序 = 优先级，`anyRequest()` 必须放最后**

```java
.requestMatchers("/api/auth/login").permitAll()   // 先匹配先赢
...
.anyRequest().authenticated()                      // 兜底：剩下的都要登录
```
把 `anyRequest()` 写在中间，后面所有规则都会失效（Java 链式调用的顺序就是判定顺序）。

**② `/error` 一定要 permitAll**

请求出错时 Spring Boot 会内部转发到 `/error`。如果不放行，这个内部转发又会被要求登录，最终前端收到的是莫名的 401 而不是真正的错误信息。

**③ 为什么放行 `GET /api/products/**`？**

因为电商的**游客也要能逛商品**——没登录就看不到商品列表，这业务本身就说不通。这是"业务需求决定白名单"的典型例子：保护的是**用户数据**和**写操作**，而不是浏览。Day 07 做商品写接口（POST/PUT/DELETE）时，它们会自动落到 `anyRequest().authenticated()` 里被保护。

> 如果做出下面这个顺序，你会踩坑：
> ```java
> .requestMatchers(HttpMethod.GET, "/api/**").permitAll()   // ❌ 太宽，把 /api/users 也放行了
> ```
> 白名单宁窄勿宽。

### 8.5 ⚠️ Spring Security 7 破坏性变更（写错就编译不过）

Spring Security 7.0 是**大版本**，删掉了一批旧 API。网上 90% 的教程还是 6.x 写法，在你这里会直接编译报错：

| 6.x 老写法（在你这会报错） | 7.x 新写法 |
|---|---|
| `.csrf().disable().and()` | `.csrf(AbstractHttpConfigurer::disable)` |
| `.authorizeRequests()` | `.authorizeHttpRequests(...)` |
| 链式 `.and()` 串联所有配置块 | **只用 lambda**，`and()` 已被移除 |
| `AntPathRequestMatcher` / `MvcRequestMatcher` | `PathPatternRequestMatcher`（`requestMatchers(String)` 已默认用它） |
| `AuthorizationManager#check` | `AuthorizationManager#authorize` |

**一句话记法：Security 7 里没有 `.and()`，每个配置块都用 lambda 的写法并排写。**

---

## 9. 第 7 步：密码加密（为什么 `{noop}` 必须处理）

### 9.1 `{noop}` 是什么

`{noop}` 是 Spring Security `DelegatingPasswordEncoder` 的**编码前缀标记**：

| 存的值 | 含义 |
|---|---|
| `{noop}demo123` | 明文，直接比（**只该用于本地演示**） |
| `{bcrypt}$2a$10$....` | BCrypt 哈希（**生产标准**） |
| 没有任何前缀的 `abc123` | Security 会报 `There is no PasswordEncoder mapped for the id "null"` |

我们的 `PasswordEncoderFactories.createDelegatingPasswordEncoder()` 同时支持上面所有格式——**这正是它存在的意义：平滑迁移**。

### 9.2 今天的做法（推荐）

- **不改动** demo 的 `{noop}demo123`，先让它能登录跑通流程；
- **新注册/改密**的密码一律用 `passwordEncoder.encode(rawPassword)` 存，会自动带 `{bcrypt}` 前缀；
- Day 04 那些明文测试用户（alice/dave...）会登录失败，直接清理掉：
  ```sql
  DELETE FROM users WHERE username IN ('alice','bob','carol','dave');
  ```

### 9.3 有空再做：把 demo 也迁成 BCrypt

思路：用 `PasswordEncoder` 生成哈希，再 UPDATE 回数据库。最省事的做法是写一个临时的 Spring Boot 测试：

```java
@SpringBootTest
class PasswordHashTest {
    @Autowired PasswordEncoder encoder;

    @Test
    void printHash() {
        System.out.println(encoder.encode("demo123"));
        // 复制打印出来的 {bcrypt}$2a$10$... 执行：
        // UPDATE users SET password = '<粘贴这里>' WHERE username = 'demo';
    }
}
```

> 生产要求：数据库里**永远不该出现明文密码**。今天保留 `{noop}` 只是为了教学平滑，你自己心里要清楚这是"待还的技术债"。

---

## 10. 第 8 步：构建与验收

```bash
cd /d/MallX/backend/mallx
bash mvnw.sh install -DskipTests
bash mvnw.sh spring-boot:run -pl mall-server -Dspring-boot.run.arguments=--server.port=8080
```

> 端口坑复习：本机环境变量 `SERVER__PORT=51837` 会覆盖 yml 的 8080，**必须显式加 `--server.port=8080`**。

### 8 项验收（逐条跑）

```bash
# 1) 匿名访问受保护接口 → 期望 HTTP 401 且 body 是统一格式
curl -i http://localhost:8080/api/users

# 2) 登录（demo / demo123）→ 期望拿到 token
curl -s -X POST http://localhost:8080/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"demo","password":"demo123"}'

# 3) 密码错误 → 期望 401 + {"code":401,...}，不是 500
curl -s -X POST http://localhost:8080/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"demo","password":"wrong"}'

# 4) 带正确 token 访问 → 期望 200 且能拿到用户列表
TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"demo","password":"demo123"}' \
        | python -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")
curl -s http://localhost:8080/api/users -H "Authorization: Bearer $TOKEN"

# 5) 篡改 token（末尾加一个字）→ 期望 401
curl -i http://localhost:8080/api/users -H "Authorization: Bearer ${TOKEN}x"

# 6) 白名单回归 → /api/hello 与商品只读接口仍能匿名访问
curl -s http://localhost:8080/api/hello
curl -s "http://localhost:8080/api/products?current=1&size=3"

# 7) Swagger 仍可访问
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/swagger-ui/index.html

# 8) 无状态检查：响应头不应出现 Set-Cookie: JSESSIONID
curl -si http://localhost:8080/api/hello | grep -i "set-cookie" || echo "无 Cookie ✅（无状态）"
```

### Swagger 里带 token 调试（强烈建议做，5 分钟）

**文件**：`mall-server/src/main/java/com/mallx/server/config/OpenApiConfig.java`

在 `OpenAPI` 上追加 components + security：

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;

@Bean
public OpenAPI mallxOpenAPI() {
    return new OpenAPI()
            .info(new Info().title("MallX 电商系统 API").version("v0.0.1")
                    .description("MallX 后端接口文档"))
            // 新增：声明 Bearer token 认证方式
            .components(new Components().addSecuritySchemes("bearerAuth",
                    new SecurityScheme()
                            .type(SecurityScheme.Type.HTTP)
                            .scheme("bearer")
                            .bearerFormat("JWT")))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
}
```

配好之后，Swagger 页面右上角会出现 **Authorize** 按钮：把登录拿到的 token 粘进去，之后所有接口调试都会自动带上 `Authorization` 头。

### 本机实测记录（2026-09-15，8 项全绿）

| # | 验收项 | 实测 | 结论 |
|---|---|---|---|
| 1 | 匿名 `GET /api/users` | 401 | ✅ |
| 2 | 登录 `demo/demo123` | 200，token 三段、`{"alg":"HS256"}`、`sub:"1"` | ✅ |
| 3 | 密码错误 | 401（非 500） | ✅ |
| 4 | 带 token `GET /api/users` | 200，返回用户分页数据 | ✅ |
| 5 | 篡改签名 | 401 | ✅ |
| 5b | 伪造 payload、保留旧签名 | 401 | ✅ 证明验签真的生效 |
| 6 | `/api/hello`、`/api/products` 白名单 | 200 | ✅ |
| 7 | `/v3/api-docs`、`/swagger-ui.html` | 200 | ✅ |
| 8 | 登录响应无 `Set-Cookie` | 无 | ✅ 无状态 |

> ⚠️ **本机 PowerShell + curl.exe 两个环境坑（排查了半小时，务必记住）**
>
> **坑 1 —— PowerShell 会吃掉 JSON 里的双引号。**
> 把 `curl.exe ... -d '{"username":"demo"}'` 写在 `.ps1` 脚本里，PowerShell 传参时引号会被剥掉，
> 服务端收到的是 `username=demo`（首字符 `u`），直接抛
> `HttpMessageNotReadableException: Unexpected character ('u'): was expecting double-quote to start property name` → 表现为**登录莫名其妙的 500**，而手工在命令行敲同一条命令却 200。
> **解法**：JSON 写进临时文件，用 `--data-binary "@$bodyPath"` 传；或改用 `Invoke-RestMethod`。
>
> **坑 2 —— 终端/管道编码会伪造"乱码"。**
> psql 输出 `nickname` 显示 `婕旂ず鐢ㄦ埛`、curl 原始输出经管道也显示乱码，看起来像 Spring 返回了坏数据。
> 用 `encode(convert_to(nickname,'UTF8'),'hex')` 一验：`e6bc94e7a4bae794a8e688b7` = **正确的"演示用户"**。
> 真正的乱码只存在于 Windows 控制台/管道的显示环节，**数据库和 Spring 都是好的**。
> **结论**：遇到"中文乱码"先 hex 验证，别急着改代码；`curl.exe` 输出用 `-o 文件` + `Get-Content -Encoding utf8` 读，别直接吃管道。

---

## 11. 常见卡点速查

| 现象 | 原因 / 解法 |
|---|---|
| 编译报 `and()` 找不到 / `authorizeRequests` 不存在 | Security 7 已移除，改 lambda + `authorizeHttpRequests` |
| 启动报 `No qualifying bean of type 'AuthenticationManager'` | 别自己 new，从 `AuthenticationConfiguration#getAuthenticationManager()` 取 |
| 全站 401，连 `/api/hello`、Swagger 都进不去 | 白名单没配好：路径写错 / `anyRequest()` 位置太靠前 / 漏了 `/error` |
| 启动抛 `WeakKeyException: The specified key byte array is N bits` | `mallx.jwt.secret` 短于 32 字节（HS256 要求 256 位） |
| 登录报 `There is no PasswordEncoder mapped for the id "null"` | 密码既没有 `{noop}` 也没有 `{bcrypt}` 前缀（Day 04 造的明文测试用户）→ 删掉或重新编码 |
| 登录失败返回 500 而不是 401 | `GlobalExceptionHandler` 没加 `AuthenticationException` 的 handler |
| 脚本里调登录接口稳定 500、报 `Unexpected character ('u')` | **不是后端 bug**：PowerShell 剥掉了 JSON 双引号。改用 `--data-binary "@file"` 或 `Invoke-RestMethod` |
| 看到返回的中文是乱码 | 先用 `encode(convert_to(col,'UTF8'),'hex')` 验真身；多半只是 Windows 终端/管道显示问题 |
| token 明明带了却还是 401 | ①忘了 `Bearer ` 前缀和空格 ②过滤器没 `addFilterBefore` ③filter 里解析成功但忘了 `SecurityContextHolder.setContext` |
| 过滤器里抛异常导致 500 | 解析失败必须 catch 住（`JwtException`），当"未登录"处理 |
| 401 返回的中文是乱码 | `response.setContentType("application/json;charset=UTF-8")` 漏了 charset |
| 加了 Security 后 Swagger 空白/404 | 白名单漏 `/v3/api-docs/**` 与 `/swagger-ui/**` |
| 循环依赖（Config ↔ Filter） | 都用构造注入 + `@Component`，不要在 Config 里 `new` 过滤器 |
| `instanceof` / 强转 `LoginUser` 报 ClassCastException | 认证成功时 `getPrincipal()` 返回的就是你在 `UserDetailsService` 里返回的对象 |
| 前端跨域被拦 | 今天没配 CORS（无前端）。做前端时再加 `CorsConfigurationSource` Bean |

---

## 12. 本日成果自检清单

- [x] mall-common：`JwtProperties` / `JwtUtil` / `JwtAuthenticationFilter` / `RestAuthenticationEntryPoint` / `config/SecurityConfig` 全部落位
- [x] mall-user：`LoginUser` / `UserDetailsServiceImpl` / `LoginDTO` / `LoginVO` / `AuthController` 全部落位
- [x] 父 POM 加 jjwt BOM；mall-common 加 security + jjwt 三件套
- [x] `application.yml` 加 `mallx.jwt.*`
- [x] 编译通过、应用启动、第 10 章 8 项验收全绿（2026-09-15 实测）
- [x] 白名单覆盖 Swagger 与 `/error`
- [ ] 理解并口述：JWT 无状态原理 / 过滤器链顺序 / `{noop}` 与 BCrypt 的区别
- [ ] Git 提交（建议信息：`feat: Day 06 登录鉴权 - JWT 签发校验 + Spring Security 7 过滤器链`）

---

## 13. 做完之后

今天你只做了"**认人**"。接下来立刻能吃到红利：

```text
Day 07：商品写接口 + RBAC 授权   ← 详见 docs/daily/Day-07-商品写接口与RBAC.md
  POST   /api/products          新增商品   ← 现在能要求"必须登录 + 有 product:create 权限"
  PUT    /api/products/{id}     改价/上下架
  DELETE /api/products/{id}     删除
  顺手学会：@EnableMethodSecurity / @PreAuthorize 方法级鉴权；
            接上 Day 03 建好的 admins/roles/permissions（RBAC）；
            新增 mall-admin 模块承载管理员体系
```

> ⚠️ Day 07 会踩到一个坑：容器里**只允许存在 1 个 `UserDetailsService` Bean**，
> 第二个会让全局 `AuthenticationManager` **静默不注册**，直接把今天的登录打挂。
> 所以管理端**不实现该接口** —— 详见 Day 07 文档第 6.3 步。

再往后：购物车要挂 `user_id`、订单要记"谁下的单"——**它们现在终于有"人"可挂了**。

---

## 附：今日术语表

| 术语 | 一句话解释 |
|---|---|
| Authentication 认证 | 你是谁（登录） |
| Authorization 授权 | 你能干什么（角色/权限） |
| JWT | 三段式 token：头.内容.签名；内容可读、签名防篡改 |
| Claim | JWT 内容里的一个字段，如 `sub`、`username`、`exp` |
| `sub` | JWT 标准字段 subject，我们放 userId |
| 无状态 (Stateless) | 服务端不保存会话，每次请求自带凭证 |
| Bearer | 带 token 的 HTTP 头格式：`Authorization: Bearer <token>` |
| EntryPoint | 未认证时的出口，决定返回什么（我们返回 JSON 401） |
| Filter Chain | 请求进入 Controller 前经过的一串过滤器，Security 的核心 |
| `{noop}` / `{bcrypt}` | 密码编码前缀，告诉 Security 用哪种方式比对 |
| UserDetailsService | Security 的"查人接口"，你必须实现它接自己的用户表 |
