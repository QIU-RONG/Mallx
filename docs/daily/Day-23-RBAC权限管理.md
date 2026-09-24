# Day 23：RBAC 权限管理 —— 管理员 / 角色 / 权限（§5.6，收口 M2）

> 方向：**§5.6 权限管理**。Day 22 把 §5.1 Dashboard 与 §5.2 用户管理做完后，
> **M2（Day 22 = 后端 API 完整含搜索/管理端数据）的最后一格就是本日**。
> 陪练模式：本文档 + 结构改动 + 骨架由我出，**实现你亲手写**（说一句「直接写好」我也代写）。

---

## 一、开工前拍定的四条决策

| # | 决策 | 取值 | 理由 / 代价 |
|---|---|---|---|
| 1 | 写操作覆盖到哪 | 管理员 + 角色**可写**；权限**只读** | 权限码是**代码资产** —— 每个 `@PreAuthorize` 都要引用它。界面造出来的码没有对应端点 ⇒ 死权限 |
| 2 | 权限码粒度 | 每实体 5 码 + 2 个分配码 | 与项目「一个端点一个码」的既有约定一致（`12-day22-permissions.sql` §一 已写明这条约定是**刻意**的） |
| 3 | 防自锁护栏 | 加 3 条硬护栏 | 见 §五。自锁是 RBAC 唯一的「不可逆事故」—— 代码全对、数据库没坏，但**谁也进不来了** |
| 4 | token 快照 | 路线①：认下「改完要重新登录」 | `application.yml:34` → `expire-minutes: 120` ⇒ 窗口最长 **2 小时**；零代码改动，只需写进文档 |

### ★ 订正一处算术（定范围时我说错了）

定范围时我把权限码数报成「**12** 个（id 26–37）」，实际是
5（admin）+ 5（role）+ 1（`permission:list`）+ 2（两个分配码）= **13 个，id 26–38**。

⇒ 与 `12-day22-permissions.sql` §4.3 那条教训**是同一个动作**：
那条注释里写着「首次落地时这一格被写成 3，脚本当场报 FAIL —— 数据是对的，错的是心算」，
并总结出「**凡『合计』类期望值，都要能从别的格子复算出来，别凭印象填**」。
本次是这条教训的第 2 次现形（同一个坑，从 SQL 期望值漂到了范围估算上）。
**已实测核对**：`12-day22-permissions.sql` §4.4 自检期望 `permissions_total = 25`，现 max(id) = 25。

---

## 二、开工前 recon：三条非显然事实（全部实证）

### ★★ ① `roles.status` 是「死的」—— 停用角色只挡角色码，不挡权限

`mall-admin/src/main/resources/mapper/AdminMapper.xml` 两条装载 SQL 对 `status` 的判法**不对称**：

| 语句 | 判 `p.status` | 判 `r.status` |
|---|---|---|
| `selectPermissionCodesByAdminId`（`:7-14`） | ✅ `AND p.status = 1` | ❌ **没有** |
| `selectRoleCodesByAdminId`（`:16-22`） | —（不查权限表） | ✅ `AND r.status = 1` |

**后果**：把角色 2（PRODUCT_ADMIN）的 `status` 改成 0 之后，该管理员

- **丢掉** `ROLE_PRODUCT_ADMIN` 这个权限位 ✅（`hasRole` 会拒）
- 但**照旧拿到 `product:*` 全部权限码** ❌ ⇒ `@PreAuthorize("hasAuthority('product:create')")` **依然放行**

也就是说：**「停用角色」这件事在现有代码里只生效了一半**，而
**没有任何断言看得见** —— 库里 3 个角色全是 `status = 1`，这条路径从来没被走过
（同 L1「样本量陷阱」、L5「停止条件下沉到数据里」：**差异必须在数据里造出来才可断言**）。

**本日必须一起修**：给 `selectPermissionCodesByAdminId` 补 `AND r.status = 1`。

> ⚠️ **这条 SQL 在登录链路上** —— 管理端登录被 `day14-e2e-walk` / `day15-ship-confirm` /
> `day16-review-e2e` 三条 E2E 用到（它们都要 admin token 去发货/审评价）
> ⇒ **改完必须重跑 `day17-m1-regression.py`（198/198）**。

### ② `permissions.parent_id` 从未被使用

`01-schema.sql:345` 有这一列，但**种子数据全部为 NULL**
（`03-data.sql:131-143` 的 8 条 + 05/07/08/10/12 补发的 17 条，无一填写），
且全项目**没有任何代码读它**。

⇒ V1.0 **明确不启用**，并写下理由：权限树是**前端菜单元数据**，与鉴权无关
（`@PreAuthorize` 只认 `code`）。真要做得先定层级语义（谁是根、跨域怎么挂），属 Day 24+ 的事。
**不写下来，下一个人会以为它是「还没接上的功能」。**

### ③ `admins` 没有软删列，且密码种子是 `{noop}`

| 事实 | 出处 | 后果 |
|---|---|---|
| `admins` 无 `is_deleted` 列 | `:316-324` | 删管理员 = **物理删** ⇒ 必须**同事务**先删 `admin_roles`（FK 是 NO ACTION） |
| `password` 种子 = `{noop}admin123` | `03-data.sql:149` | **新建管理员必须走 `PasswordEncoder.encode()`**；照抄 `{noop}` = 明文入库 |
| `username` UNIQUE | `:318` | 物理删之后**同名可以重建**（若改成软删反而会永久占坑） |
| 角色是**多对多**（`admin_roles` 复合主键） | `:352-358` | 「分配角色」是**集合操作**，不是改一个 `role_id` 列 |

另外两个**已有资产**（本日可直接复用，不必重造）：

- `AdminAccountService.findByUsername`（`security/` 包）已经把「管理员 → 角色 → 权限码」
  的拼装写好了 —— 本日的分配接口只要保证**写进表里的关系**正确，登录侧自动受益。
- `AdminMapper.selectPermissionCodesByAdminId` / `selectRoleCodesByAdminId` 同理。

---

## 三、权限码表（13 条，id 26–38）

文件 `backend/sql/13-day23-permissions.sql`（**第 7 次**做这件事，模板照 `12-day22-permissions.sql`）。

| id | code | path | method | 发给谁 |
|---|---|---|---|---|
| 26 | `admin:list` | `/api/admin/admins` | GET | 只超管 |
| 27 | `admin:detail` | `/api/admin/admins/*` | GET | 只超管 |
| 28 | `admin:create` | `/api/admin/admins` | POST | 只超管 |
| 29 | `admin:update` | `/api/admin/admins/*` | PUT | 只超管 |
| 30 | `admin:delete` | `/api/admin/admins/*` | DELETE | 只超管 |
| 31 | `admin:assign-role` | `/api/admin/admins/*/roles` | PUT | 只超管 |
| 32 | `role:list` | `/api/admin/roles` | GET | 只超管 |
| 33 | `role:detail` | `/api/admin/roles/*` | GET | 只超管 |
| 34 | `role:create` | `/api/admin/roles` | POST | 只超管 |
| 35 | `role:update` | `/api/admin/roles/*` | PUT | 只超管 |
| 36 | `role:delete` | `/api/admin/roles/*` | DELETE | 只超管 |
| 37 | `role:assign-permission` | `/api/admin/roles/*/permissions` | PUT | 只超管 |
| 38 | `permission:list` | `/api/admin/permissions` | GET | 只超管 |

**★★ 这 13 条全部只发给 role 1（SUPER_ADMIN），一条都不给 role 2 / role 3 —— 这是本日最重要的一条权限安排。**

理由不是「超管本来就该什么都有」，而是一条**硬性推理**：

> `role:assign-permission` 与 `admin:create` / `admin:assign-role` 合起来 = **完整的自我提权通道**。
> 拿到 `role:assign-permission` 的人，可以给自己所属的角色**补满任意权限**；
> 拿到 `admin:create` + `admin:assign-role` 的人，可以**造一个新超管账号**。
> ⇒ 这三个域的码**只要漏给任何一个非超管角色，RBAC 的门就形同虚设**。

于是验收里的**反向对照**（Day 17 夹具 `op_product` / `op_order` 不用白不用）：

| 账号 | 期望 |
|---|---|
| `op_product`（PRODUCT_ADMIN，有 `dashboard:*` + `product:*`） | 打 `/api/admin/roles` → **403** |
| `op_order`（ORDER_ADMIN，有 `dashboard:*` + `user:list/detail`） | 打 `/api/admin/admins` → **403** |

★ 只用全权 admin 测 = 什么都证明不了 —— 这是 `06-day17-fixtures.sql` 里那两个账号存在的全部意义。

**补发授权要照 `12-day22-permissions.sql` 的写法**：`WHERE NOT EXISTS` 幂等 + **序列校准**（`setval`）
+ 四段自检（其中 `role2_*` / `role3_*` 两格的期望值是 **0**，必须写进注释）。

---

## 四、端点清单（13 个，全部零 POM 改动）

**归放位置**：全部落在 `mall-admin`（RBAC 是管理端独有的域；`Admin` / `Role` / `Permission`
三个实体和对应 Mapper **早已存在**）⇒ **不碰任何 `pom.xml`**。

### 管理员 `/api/admin/admins` → `AdminAccountController`

> ★ 命名说明：`security` 包里已有一个 `AdminAccountService`（登录用）。
> 为避免撞名，本日的业务 Service 命名为 `AdminAccountManageService`，注释里写明分工。

| # | 方法 路径 | 权限码 | 语义与要点 |
|---|---|---|---|
| 1 | `GET /api/admin/admins?current&size&keyword&status` | `admin:list` | 分页；★ keyword 三列（`username` / `nickname`）必须 `.and(w -> …)` **包括号**（同 Day 22 的 `pageUsers`）；夹紧写在 `new Page<>()` **之前** |
| 2 | `GET /api/admin/admins/{id}` | `admin:detail` | 返回 `AdminDetailVO`（**不含 password**）+ 该管理员的角色列表 |
| 3 | `POST /api/admin/admins` | `admin:create` | ★ 密码走 `PasswordEncoder.encode()`（不能 `{noop}`）；`username` 撞 UNIQUE → **400**（不是 500） |
| 4 | `PUT /api/admin/admins/{id}` | `admin:update` | 改 `nickname` / `status`；★ **护栏③**（不许停用自己） |
| 5 | `DELETE /api/admin/admins/{id}` | `admin:delete` | **物理删** + 同事务删 `admin_roles`；★ **护栏③**（不许删自己） |
| 6 | `PUT /api/admin/admins/{id}/roles` | `admin:assign-role` | **全量替换** `admin_roles`；★ **护栏③**（不许清空自己的角色） |

### 角色 `/api/admin/roles` → `AdminRoleController`

| # | 方法 路径 | 权限码 | 语义与要点 |
|---|---|---|---|
| 7 | `GET /api/admin/roles?current&size&keyword` | `role:list` | 分页 |
| 8 | `GET /api/admin/roles/{id}` | `role:detail` | 含 `permissionIds` + `permissionCodes` |
| 9 | `POST /api/admin/roles` | `role:create` | `code` 撞 UNIQUE → 400 |
| 10 | `PUT /api/admin/roles/{id}` | `role:update` | 改 `name` / `description` / `status`；★ **护栏①**（不许停用 SUPER_ADMIN） |
| 11 | `DELETE /api/admin/roles/{id}` | `role:delete` | ★ 先删 `role_permissions` + `admin_roles`（FK NO ACTION）；★ **护栏①**（不许删 SUPER_ADMIN） |
| 12 | `PUT /api/admin/roles/{id}/permissions` | `role:assign-permission` | **全量替换** `role_permissions`；★ **护栏②**（SUPER_ADMIN 只许增不许减） |

### 权限 `/api/admin/permissions` → `AdminPermissionController`

| # | 方法 路径 | 权限码 | 语义与要点 |
|---|---|---|---|
| 13 | `GET /api/admin/permissions?type&keyword` | `permission:list` | ★ **不分页**，字典式（参照 L5① 的 `GET /api/admin/brands`）：全表才 38 行，前端要拿它渲染勾选框，分页反而难用。★ 若将来权限过千，这条要改回分页并同步改断言 |

**`status` 落在 `role:update` 而不是单开 `role:status`** —— 与 Day 22 给 `user:status` 单开一码的做法**不同**，
理由要说清楚：`user:status` 单开是因为「订单管理员能看用户但不能禁用」需要**两个人不同粒度**；
而本日这三域的 13 条码**全部只发给超管**，没有第二个角色需要区分粒度
⇒ 再拆一码是纯粹的码数量膨胀。（这类差异要诚实写下来，别让后来者以为是漏了。）

---

## 五、三条硬护栏

自锁是 RBAC 唯一的**不可逆**事故：代码全对、库没坏、日志干净，但**任何人也进不来了**。

| # | 护栏 | 落在哪 | 判据 |
|---|---|---|---|
| ① | **SUPER_ADMIN 角色不可删、不可停用** | `role:delete` / `role:update` | `role.code == "SUPER_ADMIN"` → 400 |
| ② | **SUPER_ADMIN 角色的权限只许增、不许减** | `role:assign-permission` | 目标集合必须 **⊇** 现有集合，否则 400 |
| ③ | **不许对自己执行破坏性操作** | `admin:delete` / `admin:update`(status→0) / `admin:assign-role`(集合为空) | `targetId.equals(currentAdminId)` → 400 |

**护栏② 为什么允许「增」而不是完全冻结**：将来新增权限（比如本日这 13 条）时，
可以在界面上给超管补授，不必去改 SQL。冻结反而会逼人绕过接口直接改库 —— 那更糟。

### ★★ 护栏③ 用「禁止对自己」就足以防自锁 —— 这条推理要能自证

> 执行这三个动作**必须持有 `admin:*` 权限码** ⇒ **操作人必然是超管**。
> 于是「①超管角色不可删/停用」+「③不能删自己 / 不能停自己 / 不能清空自己的角色」
> 四条合起来 ⇒ **任何时刻系统里至少剩下操作人这一个超管** ⇒ **结构上不可能自锁**。

**为什么不采用「统计剩余超管数 < 2 就拒绝」**：

1. 需要额外 `count` 查询（每条写操作多一次往返）；
2. 有**并发竞态** —— 两个超管同时删对方，各自读到的都是「还有 2 个」⇒ 两个都放行 ⇒ **真的锁死**；
3. 「禁止对自己」是**结构性**的，**没有竞态**（同项目反复出现的偏好：条件 UPDATE / CAS /
   `requireOwn` 先判 null 再判归属 —— 让**结构**承担语义，而不是让**检查**承担）。

---

## 六、骨架交付清单

### 新建（22 个）

| 目录 | 文件 |
|---|---|
| `dto/`（6） | `AdminCreateDTO` / `AdminUpdateDTO` / `RoleCreateDTO` / `RoleUpdateDTO` / `AssignRolesDTO` / `AssignPermissionsDTO` |
| `vo/`（5） | `AdminVO`（★ **不含 password**）/ `AdminDetailVO`（含 roles）/ `RoleVO` / `RoleDetailVO`（含 permissionIds）/ `PermissionVO` |
| `service/`（6） | `AdminAccountManageService` + `Impl` / `RoleManageService` + `Impl` / `PermissionQueryService` + `Impl` |
| `controller/`（3） | `AdminAccountController` / `AdminRoleController` / `AdminPermissionController` |
| `mapper/`（2） | `AdminRbacMapper`（Java）+ `resources/mapper/AdminRbacMapper.xml` |

### 修改（1 个 —— 只有这一个）

| 文件 | 改动 |
|---|---|
| `resources/mapper/AdminMapper.xml` | `selectPermissionCodesByAdminId` 补 **`AND r.status = 1`**（§二① 的缺陷修复） |

### 关联产出

- `backend/sql/13-day23-permissions.sql`（13 条码 + 只发超管 + 序列校准 + 四段自检）
- `backend/loadtest/day23-rbac-verify.py`（验收，A–G 组）
- `backend/loadtest/day23-perm-apply.py`（权限落地 + 幂等）

### `AdminRbacMapper` 需要的 6 条语句（两条关联表**不建实体**）

`admin_roles` / `role_permissions` 是**复合主键**的纯关联表，MyBatis-Plus 对复合主键支持别扭
（要硬指定一个 `@TableId`）。⇒ 照项目惯例**手写 XML**：

```text
selectRoleIdsByAdminId(adminId)             List<Long>
selectPermissionIdsByRoleId(roleId)         List<Long>
deleteAdminRolesByAdminId(adminId)          int
deleteRolePermissionsByRoleId(roleId)       int
insertAdminRoles(adminId, roleIds)          int    ← <foreach> 批量
insertRolePermissions(roleId, permissionIds) int   ← <foreach> 批量
```

★ **「全量替换」的原子性**：`deleteXxxByYyyId` + `insertXxx` 必须在**同一个 `@Transactional` 里**。
只在事务中间才会出现「权限瞬时为空」的短暂窗口 —— 事务把它吃掉。
⚠️ 这是本项目**少数几处「两条语句」必须加事务**的地方（判据同 `InventoryService:119`）。

---

## 七、验收计划（`day23-rbac-verify.py`）

### ★★ 本日断言写法的总纲（路线①的直接后果）

> **权限是签进 token 的。所以所有「改了权限之后应该生效」的断言，
> 都必须【重新登录】拿一个新 token 再打 —— 用旧 token 打，只会得到「权限还在」的假象。**

这条不只是写法约定，它本身**就是要被验收的对象**：
「用旧 token 仍有权限 / 用新 token 权限已消失」这一对**并行断言**，才是路线①的完整证据。
反过来说：若新旧 token 表现**相同**，那说明要么权限根本没改到库里，要么路线①的前提被推翻了。

| 组 | 内容 | 条数（初拟） |
|---|---|---|
| A | **权限落地**：13 条码存在 + path/method 逐字对齐 + 只发超管 + `op_product`/`op_order` 打 RBAC 端点 **403** | ~18 |
| B | **管理员 CRUD**：列表分页/夹紧/keyword 括号（★ 造一个「昵称命中但 status=0」的靶子）/ 详情**响应里没有 password 键** / create 后**新密码能登录**（证 encoder 生效）/ username 撞 → 400 / **物理删后 `admin_roles` 也没了** | ~16 |
| C | **角色 CRUD**：列表 / 详情含 permissionIds / code 撞 → 400 / 删除后 `role_permissions` 与 `admin_roles` 都清了 / **护栏①**（删与停用 SUPER_ADMIN 都 400） | ~12 |
| D | **两个分配**：全量替换**幂等**（重复提交两次结果相同）/ 空数组 = 清空 / **不存在的 id → 400 而不是 500** / **护栏②**（减 SUPER_ADMIN 权限 → 400）/ **护栏③**（清空自己的角色 → 400） | ~14 |
| E | ★ **`roles.status` 修复证明**：停用角色 → **重新登录** → 该角色的权限码消失；**旧 token 不变**（路线①的正面证据） | ~6 |
| F | **权限只读**：列表不分页、`type` 过滤、POST/PUT/DELETE 全 **405** | ~6 |
| G | **老链路存活**：`day17-m1-regression.py` **198/198** + `BASELINE RESTORED: YES` | — |

**预计 `EXPECTED` ≈ 72**（★ 写成常量并在首次跑后按报告 REAL 校准 —— 这道护栏在 Day 21 已经
实证过「第一次跑就报出总数不符」，值得一直留着）。

### 几条方法学要点（都是项目踩过的）

1. ★ **断言权限必须给合法载荷** —— `@Valid` 跑在 `@PreAuthorize` **之前**（Day 07 的坑）：
   非法请求永远先撞 400，与有没有权限无关 ⇒ 想验 403 就得给一个**能通过校验**的 body。
2. ★ **「密码不外泄」不能只看响应体读起来干净** —— 要断言**键不存在**（不是 `"password": null`）。
   Day 22 的 `UserVO` 就是这么设计的（字段压根不在 VO 里）。
3. ★ **物理删要同时断两张表** —— 只断 `admins` 少了 1 行，会漏掉「`admin_roles` 留下孤儿行」；
   而孤儿行的危害是：将来某个新管理员拿到**相同的 id**（序列回退/手工插入）会**凭空继承旧角色**。
4. ★ **幂等断言必须对「首次」和「重复」都成立**（Day 20 的教训：`净新增 +1` 只在首次成立 → 假失败）。
5. ★ **满额断言写死常量**（`EXPECTED`），跑完核对「断言总数 == EXPECTED」—— 防静默跳过。
6. ★ **造数 + 高水位线清理**：本日造的管理员/角色用固定前缀（如 `D23-TEMP-` / `d23_tmp_`）隔离，
   跑完按高水位线删干净，最后**复查 `permissions` 之外的 5 张表都回到基线**。

---

## 八、坑（照旧逐条写清判据）

| # | 坑 | 判据 / 做法 |
|---|---|---|
| 1 | ★★ `AdminMapper.xml` 那条修复在**登录链路**上 | 改完**必须**重跑 `day17-m1-regression.py`；M1 三条 E2E 都要 admin token |
| 2 | ★ **新建管理员的密码必须 encode** | 照抄种子里的 `{noop}` = 明文入库。正确写法 `passwordEncoder.encode(raw)` ⇒ 库里是 `$2a$…`；断言「新密码能登录」才算真证明 |
| 3 | ★ `admins` 是**物理删**，FK 是 NO ACTION | 同事务先删 `admin_roles`，否则 `23503` 现场 500（同 L5 品牌那条教训：**谁引用我，决定我能否物理删**） |
| 4 | ★ **全量替换必须在事务里** | `DELETE` + 批量 `INSERT` 之间有一个「权限瞬时为空」的窗口；**两条语句** ⇒ 按 `InventoryService:119` 的判据加 `@Transactional` |
| 5 | ★ **空数组 ≠ null 的语义要写明** | `PUT .../roles` 传 `[]` = **清空**（显式意图）；不传该字段（`null`）→ **400**。不写清就等着前端传 null 把角色清空 |
| 6 | ★ 三个 UNIQUE 列撞车 → 要转 **400** 不是 500 | `admins.username` / `roles.code` / `permissions.code`；`23505` 必须被捕获成友好响应 |
| 7 | ★★ 权限码**自指**：13 条**只发超管** | 漏发一条给非超管 = 开了一条自我提权通道（§三 的推理） |
| 8 | ★ 新增权限必须**补发 `role_permissions`** | 第 7 次做这件事。漏了的现象是「权限行进表了，但 `@PreAuthorize` **永远 403**」，长得像「权限码拼错了」 |
| 9 | XML 五铁律照旧 | 注释禁连续两减号 / SQL 里 `<` 写 `&lt;` / 别名用**下划线** / 放 `resources/mapper/` / 方法名与 `id` 逐字符一致 |
| 10 | ★ **零 POM 改动** | RBAC 全在 `mall-admin` 内，实体与 Mapper 早已存在（`Admin`/`Role`/`Permission` + 三个 Mapper）⇒ 本次**不该动任何 `pom.xml`**；若发现必须动，说明放错模块了 |
| 11 | ★ 用 `hasAuthority` 不用 `hasRole` | 项目安全配置统一 `hasAuthority`（Day 07 定型）；`hasRole` 会自作主张加 `ROLE_` 前缀，两套前缀混用会静默不匹配 |
| 12 | ★ 不要动 `/api/admin/**` 的白名单 | 管理端**本来就不在白名单**里（白名单只有两个 login + `/error` + springdoc + C 端几个 GET）⇒ **什么都不用改**；★ 若为图省事加一条 `/api/admin/**`，等于把整个管理端**静默公开**（Day 20 的 `/api/coupons` 就是这个坑） |

---

## 九、与 Day 24 的分界

| | 本日（Day 23） | 之后 |
|---|---|---|
| §5.6 权限管理 | ✅ 管理员 / 角色 / 权限 全落地 | — |
| **M2 收口** | ✅ **本日做完即 M2 完整**（§5.1–§5.6 全绿，售后属 V2.0） | — |
| §5.3 品牌 CRUD（L5②） | 未做 | 半天量，**权限码从 26 起已不可用 → 改为 39 起**（本日占掉 26–38） |
| T2 回归名单扩围 | 未做 | 把 `day17-a` / `day17-b` 纳入 M1（消除键集合断言盲区） |
| token 路线②③ | 路线①已定 | 版本号 / 每次回查 —— 留给「V2.0 想学机制」时 |
| M3（Day 30：前端 + 部署） | — | ★ 本日之后**约剩 6 天**；开工前建议先补 Swagger 的 Authorize 按钮（`OpenApiConfig` 无 `SecurityScheme`），否则前端联调只能手贴 token |

---

## 十、顺带要处理的两处「记录不准」（Day 23 开工前先办）

1. ★★ **`docs/api/users-api.md` 是 Day 06 的练手版，等于给已修掉的漏洞留了份说明书** ——
   `:132` 出参里明写 `"password": "demo123"`（注「学习阶段暂时返回」）、
   `:210` 的 `DELETE /api/users/{id}`、`:232` 的 `PUT /api/users/{id}/nickname`
   ⇒ **这三个端点现已全部不存在**（Day 22 收口成 `/api/users/me`）。
   ⇒ 处理方式二选一：**改成现状**（推荐，因为它躺在 `docs/api/` 而不是 `docs/daily/`，属「活文档」）
   或**在文件头明确标注「Day 06 历史快照，已失效」**。
2. ⚠️ **`docs/backlog.md` 的 L7 仍标「⬜ 未开工」** —— 实际 Day 22 已完成并验收（`8248b59`）；
   同时 L5 一节的「CRUD = id 22/23/24」编号已被 Day 22 占用，需改成 39+。
