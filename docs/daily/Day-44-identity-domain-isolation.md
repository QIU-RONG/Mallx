# Day 44 · 身份域隔离：管理端 token 不能再顶替 C 端顾客

> 一句话：`users` 与 `admins` 是两张**各自从 1 起**的表，而 JWT 过滤器只把 token 的 `sub`
> （一个 `Long`）塞进 principal ⇒ 「超管 1」和「顾客 1」在 SecurityContext 里长得一模一样。
> 修复前，超管 token 打 `/api/users/me` 能直接拿到顾客 `demo` 的手机号 / 昵称 / 邮箱，
> 打 `/api/orders` 能拿到该顾客的全部 6 张订单。

---

## 1. 漏洞是怎么发现的

Day 43 收尾时留了一个「看起来无害」的遗留项：**管理端 token 打 C 端接口返回 200**。
它不是笔误，而是**漏登记的设计债**，所以先取证、再定性：

```
backend/loadtest/_probe_domain.py   → 只读取证脚本（不写库、不判定）
```

取证结论（修复前，本机实跑）：

| 用例 | 修复前 | 修复后 |
|------|--------|--------|
| `admin` token → `GET /api/users/me` | **200** + `email=demo@…` / 手机号 / 昵称 | **403** `data=null` |
| `admin` token → `GET /api/orders` | **200** + 顾客 6 张订单 | **403** |
| `admin` token → `GET /api/cart` | **200** | **403** |
| `admin` token → `GET /api/addresses` | **200** + 收货地址 | **403** |
| `admin` token → `GET /api/coupons/my` | **200** | **403** |
| `demo` token → `/api/admin/**` | 403（本来就对） | 403（仍是 403，但原因变成「域不符」） |

两个 token 的 payload 摆在一起，根因一目了然：

```
C 端 token  : sub='1' type='USER'   username='demo'
管理端 token: sub='1' type='ADMIN'  username='admin'
                 ↑ 同一个数值，两个完全不同的人
```

`JwtUtil` 签发时**写了** `type` claim，但 `JwtAuthenticationFilter` **从来没读过** ——
claim 写了不用，等于没写。

---

## 2. 修复

### ① `JwtAuthenticationFilter`：读 `type`，写域标记，且 **fail closed**

```java
String type = claims.get("type", String.class);
if (!"USER".equals(type) && !"ADMIN".equals(type)) {
    throw new IllegalArgumentException("缺少/未知的身份域 type=" + type);
}
authorities.add(new SimpleGrantedAuthority("ADMIN".equals(type) ? DOMAIN_ADMIN : DOMAIN_USER));
```

⚠️ **为什么必须 fail closed**：域不明时如果「猜是 C 端」，猜错一次就是**这个漏洞本身**。
抛 `IllegalArgumentException` 会被原来的 `catch (JwtException | IllegalArgumentException)` 接住，
语义与「token 解析失败 = 没登录」一致 ⇒ 401，绝不会冒成 500。

### ② `SecurityConfig`：按路径把关（放在 `anyRequest()` **之前**）

```java
.requestMatchers("/api/admin/**").hasAuthority(DOMAIN_ADMIN)
.requestMatchers(HttpMethod.POST, "/api/orders/*/ship").hasAuthority(DOMAIN_ADMIN)  // 例外
.anyRequest().hasAuthority(DOMAIN_USER)
```

- 跨域一律走 `AccessDeniedHandler` ⇒ **真 HTTP 403**（不是 200 + code 403）。
- **唯一的例外**是发货：`POST /api/orders/{id}/ship` 是管理端动作，却与 C 端接口同处
  `OrderController`、共用 `/api/orders` 前缀。漏这一行 ⇒ 发货立刻 403（M1 的 day15 会红）。
  ★ 将来新增「管理端动作挂在 C 端路径下」的接口，**必须同时在这里加一行**。

---

## 3. 验收 + 控制组（28 条断言）

```
backend/loadtest/day44-identity-domain-verify.py
```

正式验收：**28/28 通过**（正向控制组 8 条「本域照旧 200」+ 核心 10 条跨域 403
+ 反向 3 条 + 例外通道 2 条 + fail closed 2 条 + 登录取证 3 条）。

### ★ 控制组：同一套断言打在【修复前】的代码上 → 必须失败

做法：`git checkout HEAD --` 回退这两个文件 → 重建 → 起应用 → 跑同一个脚本。

```
验收结论：18/28 通过，失败 10
  ✗ 管理端 token → GET /api/users/me = HTTP 403 | http=200 code=200
      data={"createdAt": "...", "email": "demo@m...
  ✗ 管理端 token → GET /api/orders    = HTTP 403 | http=200 code=200
  ✗ 管理端 token → GET /api/cart      = HTTP 403 | http=200 code=200
  ✗ 管理端 token → GET /api/addresses = HTTP 403 | http=200 code=200
  ✗ 管理端 token → GET /api/coupons/my= HTTP 403 | http=200 code=200
```

⇒ 10 条断言红在数据泄露明细上，证明这套断言**确实抓得住这个 bug**，不是恒真的摆设。

### 回归（全套本机实跑）

| 套件 | 结果 |
|------|------|
| M1 回归（9 个链路脚本 + 收集器） | **434/434 PASS**，`database back at baseline: YES` |
| 扩展套件 day19–24（搜索 / 券 L1·L2 / 用券 / 用户管理+仪表盘 / RBAC / 品牌） | 6/6 rc=0 |
| 缓存 day38–40 | 3/3 rc=0 |
| Day 44 身份域 | 28/28 |

CI 已纳入 `day44-identity-domain-verify.py`（新步骤 «Identity domain isolation»）。

---

## 4. 本轮踩到的坑（值得单列）

### ★★ `Copy-Item` 会保留源文件的 mtime ⇒ Maven 增量编译**跳过** ⇒ 打进 fat jar 的是旧类

控制组跑完要把修复版代码恢复回来，我用的是：

```powershell
Copy-Item "$f.fixed" "$f" -Force      # ⚠️ 目标文件的 LastWriteTime = 源文件的旧时间
```

于是 `.java`(19:53) 比 `.class`(19:55) 还旧 ⇒ `maven-compiler-plugin` 判定「没改」⇒
`BUILD SUCCESS` 但**什么都没编译** ⇒ fat jar 里 `BOOT-INF/lib/mall-common-*.jar` 仍是旧类。
表象极具误导性：**源码是对的、构建是绿的、跑出来却是旧行为**。

- 判据：不要信 `BUILD SUCCESS`，去**解 jar 查字节**
  （`zipfile` 打开 `BOOT-INF/lib/mall-common-*.jar`，在 class 里搜 `DOMAIN_USER`）。
- 修法：`[System.IO.File]::SetLastWriteTime($f, (Get-Date))` 再构建；
  或直接用 `mvn -o clean install -pl <模块>`（本轮最终靠这个才把 jar 修对）。

### ★ 其它两条

- 正在运行的 jar 会被 `spring-boot:repackage` rename 失败（`Unable to rename … .original`）
  ⇒ 构建前先按命令行匹配精确 kill（`CommandLine -match "mall-server"`），别无脑杀 `java.exe`。
- `mvn -o install -pl mall-common,mall-server` 这种多模块列表在增量场景下不可靠（上面那条），
  涉及「已验证过的行为」时一律 `clean`。

---

## 5. 遗留 / 下一步

- ✅ 身份域隔离已完成并进 CI。
- ⬜ **V1.4 远端托管**（唯一剩下的 V1.x 项）。
- ⬜ V2.0 微服务。
- 💡 后续可考虑：把 `DOMAIN_*` 从 authority 升级为独立 claim / 独立 principal 类型，
  彻底消除「权限集合里混进域标记」这种语义混用（当前实现已足够安全，属可选加固）。
