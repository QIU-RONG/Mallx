# Day 43（续）· 镜像再瘦身：jlink 最小运行时 + 纯 alpine 基底

> 承接 Day 42 的 V1.4 前半段。那次把镜像拆了层（改代码只重建 549 KB），
> 这一轮动的是**基底**：`393 MB → 229 MB`（同一个测量口径，见 §五）。

---

## 一、先量：393 MB 花在哪

| 块 | 大小 | 说明 |
|---|---|---|
| 基底 `eclipse-temurin:21-jre-alpine` | **287 MB** | 其中 JDK 目录只占 **158 MB** |
| └ 基底里的其它包 | **≈ 129 MB** | `gnupg` / `font-dejavu` / `fontconfig` / `sqlite` / `coreutils` / `openssl` … |
| `dependencies` 层 | 55.4 MB | 第三方依赖（拆层后的热层搭档） |
| 其它三层 | 1.3 MB | loader 696 KB + application 549 KB + snapshot 4.1 KB |

**两个杠杆，都有实测支撑（不是照搬博客）：**

1. **那 129 MB 是构建期工具留下的杂物** —— 官方镜像用 `gnupg` 验签名、用 `font-dejavu/fontconfig`
   撑 AWT，验完/装完都没删。跑一个 headless 服务完全用不上。
2. **JDK 目录 158 MB 里大部分模块本项目不用** —— `jdeps` 算出真实只需要 **15 个模块**。

**关键的一条实测（决定第 3 阶段能不能成立）：**

```text
ldd /opt/java/openjdk/bin/java  → 只依赖  libc.musl-x86_64.so.1 + libjli.so
ldd .../lib/server/libjvm.so    → 只依赖  libc.musl-x86_64.so.1
```

⇒ **不需要 libstdc++、freetype、fontconfig** ⇒ 运行时可以直接落在纯 `alpine` 上。

---

## 二、手法：三阶段 Dockerfile

```text
阶段 1  layers  eclipse-temurin:21-jdk-alpine
        拆层：extract --layers --launcher        （D42 已做，产物只给下面 COPY）

阶段 2  jre     eclipse-temurin:21-jdk-alpine
        CP=$(find /build/out -name '*.jar' | tr '\n' ':')
        MODS=$(jdeps --print-module-deps --ignore-missing-deps --multi-release 21 \
                 --class-path "$CP" /build/out/application/BOOT-INF/classes)
        jlink --add-modules "$MODS,jdk.crypto.ec,jdk.zipfs" \
              --strip-debug --no-man-pages --no-header-files --compress=zip-6 --output /opt/jre

阶段 3  runtime alpine:3.24
        apk add tzdata ca-certificates + 建非 root 用户
        COPY --from=jre /opt/jre /opt/jre
        COPY --from=layers 四层（依赖层在前，稳定优先）
```

三个刻意的决定：

1. **模块清单在构建时算，不抄常量。** 依赖变了它自己跟上；算完 `echo` 进构建日志，
   将来清单漂移时日志里看得见。（抄一份常量进 Dockerfile 的做法，会在半年后变成
   「镜像跑不起来但没人知道为什么」。）
2. **额外补两个 jdeps 看不到的模块**：`jdk.crypto.ec`（TLS 椭圆曲线，HTTPS /
   PostgreSQL `sslmode=require` 会用到）、`jdk.zipfs`（按 zip 文件系统读资源）。
   静态分析看不见反射用法，这是「编译期查不出、运行时才炸」的典型 —— 宁可多带几 MB。
3. **运行时基底用 `alpine:3.24`，与构建镜像的 alpine 版本对齐**：jlink 产物链接的是
   构建镜像里那份 musl，跨大版本混用有 ABI 风险，省下的几 MB 不值当。

---

## 三、结果

| 指标 | 改前 | 改后 |
|---|---|---|
| `docker images` 体积 | 393 MB | **229 MB**（−42%） |
| `docker history` 各层之和 | 269 MB | **≈ 133 MB**（−51%） |
| 基底构成 | JDK 目录 158 MB + 杂物 129 MB | jlink 运行时 **61.6 MB** + alpine 9.1 MB + apk 2.9 MB |
| `dependencies` 层（改代码时的搭档） | 55.4 MB | 55.4 MB（不变） |
| 镜像层数 | 11 | 11 |
| 容器内启动 | 8.9 s | 9.2 s |
| 容器内 JVM 参数 | `MaxRAMPercentage=75` | 同（未受影响） |
| 非 root | `mallx` | 同 |

---

## 四、验证：不能只看「体积小了」，要证「功能没坏」

jlink 最危险的地方是**漏模块**：编译期查不出，跑起来才发现某个路径 `NoClassDefFoundError`。
所以跑的不是冒烟，而是**用新镜像接开发库、把 M1 全链 + 各域套件跑一遍**：

| 套件 | 结果 |
|---|---|
| M1 全链（67+56+75+26+21） | **245/245 PASS**，(a)(a2)(b)(c)(d) 全 YES |
| `day20-coupon-verify` | 82/82 |
| `day21-coupon-use-verify`（下单抵扣/核销） | 53/53 |
| `day23-rbac-verify` | 91/91 |
| `day19-search-verify`（pg_trgm / tsvector） | 58/58 |
| `day24-brand-crud-verify` | 43/43 |
| `day38/39/40`（Redis 缓存 / 树与品牌 / 负缓存护栏） | 全 rc=0 |

**V1.4 的两条防护也复核了没被改坏**（改基底最容易顺手弄丢的东西）：

| 复核项 | 结果 |
|---|---|
| `JarLauncher` 与 `BOOT-INF/lib` 真在镜像里 | ✅ |
| prod 缺 `DB_PASSWORD` | **exit=1**（闸门仍生效） |
| `/actuator/health/readiness` | 200（容器 `healthy`） |
| 匿名 `/actuator/metrics` | **401**（白名单没被放宽） |
| PID 1 参数 | `-XX:MaxRAMPercentage=75 … JarLauncher` |
| 非 root | `mallx` |

---

## 五、诚实说明：两个「体积」口径

`docker images` 报 229 MB，而 `docker history` 各层相加约 133 MB —— **两者差 96 MB**。
换基底前也一样（393 vs 269，差 124 MB）。这说明 `images` 的口径包含了父镜像链/未共享层，
**不是**本镜像独有的内容。

⇒ 本轮的结论**只用同口径对比**（都是 `docker images`：393 → 229；都是 `history`：269 → 133），
不去解释那个差额。**拿不同口径的数字对比，就成了「没有取证的数字」。**

---

## 六、★★ 中途的一次假红灯：库里的「无主锁定」

第一次跑功能回归，day14/15/16 三条链路全红，M1 的 `(a) every CHAIN link all-green: NO`，
而 day20/21/23 却全绿。**很容易顺势得出「jlink 漏了模块」的结论** —— 但那是错的。

真相在断言原文里：

```text
[FAIL] PATH A: locked returned to 0
[FAIL] ★ business conservation holds (locked) -- 0 drifting SKUs
库存全表： 4  total=150 avail=148 locked=1 sold=1
订单状态分布： PAID x 6          ← 没有任何 PENDING_PAYMENT 单
```

**sku4 上有 1 个「无主锁定」**：`locked_stock=1`，但没有任何挂起订单认领它。
`available+locked+sold = total` 恒等式仍然成立，所以它不是「超卖」那类错误，
而是**之前某次容器实验留下的残留**（最可能是 day41 那次短 TTL 实验中断时的残留）。

★ 而 day26 夹具**修不了它**：夹具判断「6 单在位」就整段 no-op，
**不会去对账 `locked_stock`**。于是这个漂移能一直藏着，直到某条链路断言把它翻出来。

**修掉（`UPDATE ... SET available=149, locked=0, sold=1`）后，同一镜像 M1 立刻 245/245 全绿**
⇒ 镜像自证清白。**先怀疑状态、再怀疑改动** —— 这次要是直接去改 Dockerfile，就会一路改错方向。

> 📌 两个待办（本轮只记录，不夹带修改）：
> 1. **day26 夹具缺一步库存对账**：`locked_stock` 应等于 `Σ PENDING_PAYMENT 明细数量`，
>    夹具应当把这条恒等式也拉回常态，而不是靠「6 单在位」短路。
> 2. **day41 的满额护栏对不上**：脚本 `EXPECTED=12`，实跑 13 条 —— 13 条全 OK，
>    但「实得 ≠ 期望」照样判 FAIL。说明有人加过断言没同步常量（或某条被跳过）。
>    它不在 CI 里，所以这处不一致一直没被发现。

---

## 七、下一步

- 还能再压吗？`dependencies` 55.4 MB 现在是最大的一块，`/opt/jre` 61.6 MB 次之。
  再往下就要动依赖本身（逐个 `jdeps` 找真没用的传递依赖），收益不确定、风险上升 —— **先不动**。
- 真正的下一步是 V1.4 后半段（远端托管）。届时镜像会被推到 registry，
  那时「229 MB 还是 133 MB」才直接影响推送时间；现在它主要影响的是磁盘占用。
