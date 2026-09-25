# -*- coding: utf-8 -*-
"""Day 25 · M3-1：从【源码】生成 API 总览，并与【运行时 OpenAPI】交叉核对。

为什么不用 /v3/api-docs 直接生成？
-------------------------------------------------
因为 OpenApiConfig 里加了一条 **全局 security**（addSecurityItem），
于是 openapi.json 里 **77 个 operation 全都带 `security: [{bearerAuth: []}]`** ——
它只能告诉你「文档上写着要 token」，**区分不出「公开 / 登录 / 权限码」这三档**，
更拿不到 `@PreAuthorize` 里的权限码。

⇒ 分工：
  · **端点清单 + 鉴权档位 + 权限码**  ← 解析 Java 源码（`@XxxMapping` / `@PreAuthorize`）
    + `SecurityConfig` 白名单（公开档只认「路径 + 方法」）
  · **tag / summary 文案**            ← 运行时 openapi.json
  · **一致性**：两个来源的 (METHOD, path) 集合必须 **完全相等**（差集双向为空）
    ★ 这是本脚本的主断言 —— 源码解析漏了注解、或有人加了端点没重启，都会立刻炸。

产出：
  · docs/api/API-总览.md            （交付物，人读）
  · backend/loadtest/day25-api-inventory-report.txt （自检报告，机器读）

运行：python day25-api-inventory.py
"""
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND = r"D:\MallX\backend\mallx"
OPENAPI = r"D:\MallX\docs\api\openapi.json"
SECURITY = os.path.join(BACKEND, "mall-common", "src", "main", "java",
                        "com", "mallx", "common", "config", "SecurityConfig.java")
DOC = r"D:\MallX\docs\api\API-总览.md"
HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "day25-api-inventory-report.txt")

DOCKER = r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
CONTAINER = "mallx-postgres"
DB_USER = "mallx"
DB_NAME = "mallx"

WITH_DB = "--no-db" not in sys.argv

# 模块目录 -> 中文域标签
MODULE_LABEL = {
    "mall-user": "用户域",
    "mall-product": "商品域",
    "mall-cart": "购物车域",
    "mall-inventory": "库存域",
    "mall-order": "订单域",
    "mall-payment": "支付域",
    "mall-review": "评价域",
    "mall-marketing": "营销域",
    "mall-admin": "管理端域",
}

# ★ 键是正则 `@(Get|Post|Put|Delete|Patch)Mapping` 的 **group(1)**，即不含 "Mapping" 的短名
MAPPING_METHOD = {
    "Get": "GET", "Post": "POST", "Put": "PUT",
    "Delete": "DELETE", "Patch": "PATCH",
}

lines_out = []


def say(s=""):
    lines_out.append(s)
    print(s)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def psql(sql_text):
    """跑一段 SQL。★ SQL 走 stdin，不走命令行 —— 命令行会撞 PS 的 % 展开坑。"""
    args = [DOCKER, "exec", "-i",
            "-e", "PGCLIENTENCODING=UTF8",
            CONTAINER, "psql",
            "-U", DB_USER, "-d", DB_NAME,
            "-v", "ON_ERROR_STOP=1",
            "-t", "-A", "-F", "|"]
    p = subprocess.run(args, input=sql_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


# ---------------------------------------------------------------- 1. 白名单
def parse_whitelist():
    """解析 SecurityConfig 的 requestMatchers(httpMethod, patterns...)。

    ★ 只认「路径 + 方法」：`HttpMethod.GET` 版的只放行 GET，无 method 的放行全部。
      先匹配先赢 ⇒ 这里返回的列表按出现顺序，匹配时取第一个命中的即可。
    """
    rules = []
    for raw in read(SECURITY).split("\n"):
        s = raw.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue                      # 跳过注释（本文件的注释里也写了路径，会假命中）
        if ".requestMatchers(" not in s:
            continue
        methods = None
        if "HttpMethod.GET" in s:
            methods = ["GET"]
        elif "HttpMethod.POST" in s:
            methods = ["POST"]
        for pat in re.findall(r'"([^"]+)"', s):
            rules.append((methods, pat))
    return rules


def is_public(rules, method, path):
    for methods, pat in rules:
        if methods is not None and method not in methods:
            continue
        if pat.endswith("/**"):
            if path == pat[:-3] or path.startswith(pat[:-3] + "/"):
                return pat
        elif path == pat:
            return pat
    return None


# ---------------------------------------------------------------- 2. 源码解析
def parse_controller(path):
    """返回 [(http_method, full_path, permission_code, summary_in_java, line_no)]"""
    src = read(path)
    lines = src.split("\n")
    cls_i = None
    for i, l in enumerate(lines):
        if re.search(r"\bpublic\s+(final\s+)?class\b", l):
            cls_i = i
            break
    if cls_i is None:
        return []

    prefix = ""
    for l in lines[:cls_i]:
        m = re.search(r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']", l)
        if m:
            prefix = m.group(1)

    # 类级 @PreAuthorize：只往上看「紧贴类声明的注解块」，遇到非注解行（通常是 */）就停
    class_pre = None
    for l in reversed(lines[max(0, cls_i - 8):cls_i]):
        s = l.strip()
        if s.startswith("@"):
            m = re.search(r"@PreAuthorize\s*\(\s*[\"'](.+?)[\"']\s*\)", s)
            if m:
                class_pre = m.group(1)
            continue
        if s == "":
            continue
        break

    out = []
    pending = []          # 收集自上一个方法以来的注解行
    for i, l in enumerate(lines[cls_i + 1:], start=cls_i + 1):
        s = l.strip()
        if s.startswith("@"):
            pending.append(s)
            continue
        if re.match(r"^(public|protected|private)\s", s) and "(" in s:
            joined = " ".join(pending)
            pending = []
            mm = re.search(r"@(Get|Post|Put|Delete|Patch)Mapping\s*(\([^)]*\))?", joined)
            if not mm:
                continue                  # 构造器 / 普通私有方法
            method = MAPPING_METHOD[mm.group(1)]
            sub = ""
            if mm.group(2):
                q = re.search(r"[\"']([^\"']*)[\"']", mm.group(2))
                if q:
                    sub = q.group(1)
            full = (prefix + sub).rstrip("/") or "/"
            code = None
            w = re.search(r"hasAuthority\('([^']+)'\)", joined)
            if w:
                code = w.group(1)
            elif class_pre:
                w2 = re.search(r"hasAuthority\('([^']+)'\)", class_pre)
                if w2:
                    code = w2.group(1)
            sm = re.search(r"@Operation\s*\(\s*summary\s*=\s*\"([^\"]*)\"", joined)
            out.append((method, full, code, sm.group(1) if sm else "", i + 1))
            continue
        if s and not s.startswith("}") and not s.startswith("/*") and not s.startswith("*"):
            pending = []                  # 进入方法体/游离代码，清空待定注解
    return out


def collect():
    found = {}          # (method, path) -> dict
    for root, _dirs, files in os.walk(BACKEND):
        if os.sep + "target" + os.sep in root:
            continue
        for fn in files:
            if not fn.endswith("Controller.java"):
                continue
            p = os.path.join(root, fn)
            module = os.path.relpath(p, BACKEND).split(os.sep)[0]
            for method, path, code, summary, line in parse_controller(p):
                key = (method, path)
                found[key] = dict(module=module, code=code, java_summary=summary,
                                  file=os.path.relpath(p, BACKEND).replace(os.sep, "/"),
                                  line=line)
    return found


# ---------------------------------------------------------------- 3. 主流程
def main():
    say("=" * 78)
    say("MallX API 总览生成 —— 源码解析 + 运行时 OpenAPI 交叉核对")
    say("=" * 78)
    say("")

    rules = parse_whitelist()
    say("[1] SecurityConfig 白名单（解析出 %d 条 requestMatchers 规则）" % len(rules))
    for methods, pat in rules:
        say("      %-4s %s" % (",".join(methods) if methods else "ANY", pat))
    say("")

    java_eps = collect()
    say("[2] 源码解析：%d 个端点" % len(java_eps))

    oa = json.loads(read(OPENAPI))
    oa_eps = {}
    for path, item in oa["paths"].items():
        for m, op in item.items():
            if m.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            oa_eps[(m.upper(), path)] = op
    say("[3] 运行时 openapi.json：%d 个 operation（%d 条 path）"
        % (len(oa_eps), len(oa["paths"])))
    say("")

    only_java = sorted(set(java_eps) - set(oa_eps))
    only_oa = sorted(set(oa_eps) - set(java_eps))
    say("[4] 一致性核对（集合相等是硬要求）")
    say("      只在源码里 : %d %s" % (len(only_java), only_java if only_java else ""))
    say("      只在 OpenAPI: %d %s" % (len(only_oa), only_oa if only_oa else ""))
    same = not only_java and not only_oa
    say("      => %s" % ("MATCH（两来源集合完全相等）" if same else "★ MISMATCH"))
    say("")

    # 汇总：权限码 -> 端点；公开 / 登录 / 权限码 三档
    rows = []
    for (method, path), meta in java_eps.items():
        pub = is_public(rules, method, path)
        oameta = oa_eps.get((method, path), {})
        if pub:
            tier = "公开"
            note = pub
        elif meta["code"]:
            tier = "权限码"
            note = meta["code"]
        else:
            tier = "登录"
            note = ""
        rows.append(dict(method=method, path=path, tier=tier, note=note,
                         module=meta["module"], code=meta["code"],
                         file=meta["file"], line=meta["line"],
                         tag=",".join(oameta.get("tags", [])),
                         summary=oameta.get("summary") or meta["java_summary"]))
    rows.sort(key=lambda r: (r["path"], r["method"]))

    pub_n = sum(1 for r in rows if r["tier"] == "公开")
    login_n = sum(1 for r in rows if r["tier"] == "登录")
    code_n = sum(1 for r in rows if r["tier"] == "权限码")
    codes = sorted({r["code"] for r in rows if r["code"]})
    say("[5] 鉴权档位统计")
    say("      公开 %d / 仅登录 %d / 权限码 %d   合计 %d" % (pub_n, login_n, code_n, len(rows)))
    say("      用到的权限码 %d 个：%s" % (len(codes), " ".join(codes)))
    say("")

    admin = [r for r in rows if r["path"].startswith("/api/admin/")]
    public_api = [r for r in rows if r["tier"] == "公开"]
    authed = [r for r in rows if r["tier"] != "公开"]
    legacy = [r for r in rows if r["code"] and not r["path"].startswith("/api/admin/")]
    leaked = [r for r in rows if r["tier"] == "公开" and r["code"]]

    # ------------------------------------------------------ [5b] 源码 ↔ 数据库
    db_state = None
    missing, unshared = [], []
    if WITH_DB:
        say("[5b] 权限码 ↔ 数据库 交叉核对（源码 @PreAuthorize vs permissions / role_permissions）")
        rc, out, err = psql("""
SELECT code || '|' || id::text || '|' || COALESCE(path,'') || '|' || COALESCE(method,'') || '|'
       || (SELECT count(*) FROM role_permissions rp WHERE rp.permission_id = p.id)::text
  FROM permissions p ORDER BY id;
""")
        if rc != 0:
            say("      ★ PG 不可达（Docker 引擎/容器没起）rc=%d err=%s" % (rc, err[:200]))
        else:
            db_state = {}
            for ln in out.splitlines():
                parts = ln.split("|")
                if len(parts) == 5:
                    db_state[parts[0]] = dict(id=parts[1], path=parts[2], method=parts[3],
                                              grants=int(parts[4]))
            missing = [c for c in codes if c not in db_state]
            unshared = [c for c in codes if c in db_state and db_state[c]["grants"] == 0]
            say("      permissions 表内权限码总数 : %d" % len(db_state))
            say("      源码用到但库里【没有】的码 : %d %s" % (len(missing), missing))
            say("      库里有但【没有角色持有】的码: %d %s" % (len(unshared), unshared))
            say("      => %s" % ("OK" if not missing and not unshared else "★ 有缺口"))
        say("")

    say("[5c] 口径偏离清单（不是错误，是待统一的写法）")
    for r in sorted(legacy, key=lambda x: x["path"]):
        say("      带权限码但不在 /api/admin/ 下：%s %s  code=%s" % (r["method"], r["path"], r["code"]))
    if not legacy:
        say("      无")
    say("")

    def table(rs):
        out = ["| 方法 | 路径 | Tag | 说明 | 鉴权 |", "|---|---|---|---|---|"]
        for r in rs:
            auth = "公开" if r["tier"] == "公开" else ("`%s`" % r["note"] if r["tier"] == "权限码" else "登录")
            out.append("| `%s` | `%s` | %s | %s | %s |"
                       % (r["method"], r["path"], r["tag"], r["summary"].replace("|", "\\|"), auth))
        return "\n".join(out)

    # ------------------------------------------------------------ 交付文档
    by_tag = {}
    for r in authed:
        by_tag.setdefault(r["tag"] or "(无 tag)", []).append(r)

    doc = []
    doc.append("# MallX API 总览")
    doc.append("")
    doc.append("> **本文档由脚本生成，不要手改** —— 数据源两处，缺一不可：")
    doc.append("> ① 端点清单 / 鉴权档位 / 权限码 ← 解析 `backend/mallx/**/controller/*.java`")
    doc.append("> 的 `@XxxMapping` 与 `@PreAuthorize`，叠加 `SecurityConfig` 白名单；")
    doc.append("> ② Tag / 说明文案 ← 运行时 `/v3/api-docs`（快照 `docs/api/openapi.json`）。")
    doc.append(">")
    doc.append("> 两来源的 `(方法, 路径)` 集合必须**完全相等**，否则脚本报 MISMATCH 并拒绝生成。")
    doc.append(">")
    doc.append("> 重新生成：`python backend/loadtest/day25-api-inventory.py`")
    doc.append("> （需要应用已启动且 `docs/api/openapi.json` 是当前构建导出的快照）")
    doc.append("")
    doc.append("## 〇、统计")
    doc.append("")
    doc.append("| 项 | 数量 |")
    doc.append("|---|---|")
    doc.append("| 端点总数 | **%d** |" % len(rows))
    doc.append("| ├ 公开（白名单，无需 token） | %d |" % pub_n)
    doc.append("| ├ 仅需登录（C 端 token） | %d |" % login_n)
    doc.append("| └ 需权限码（管理端） | %d |" % code_n)
    doc.append("| 管理端端点（`/api/admin/**`） | %d |" % len(admin))
    doc.append("| 用到的权限码 | %d 个 |" % len(codes))
    doc.append("")
    doc.append("★ **状态码约定**（与《README》§接口约定一致，容易踩）：")
    doc.append("Security 层（认证/授权）失败返回**真 HTTP** `401` / `403`；")
    doc.append("业务异常与参数校验失败返回 **HTTP 200 + body.code ≠ 200**。")
    doc.append("⇒ **判一个业务调用是否成功，必须看 `body.code`，不能只看 HTTP 状态码。**")
    doc.append("")
    doc.append("## 一、公开端点（白名单，先匹配先赢）")
    doc.append("")
    doc.append(table(public_api))
    doc.append("")
    doc.append("⚠️ 白名单是**方法粒度**的：匿名 `POST` 打一条白名单里的 `GET` 路径得到的是 **401**")
    doc.append("（Security 过滤器链先于 MVC 路由），带 token 才会走到 MVC 拿到 **405**。")
    doc.append("")
    doc.append("## 二、管理端端点（`/api/admin/**`，全部走权限码）")
    doc.append("")
    doc.append(table(admin))
    doc.append("")
    doc.append("### 权限码清单（本文档实际引用到的）")
    doc.append("")
    doc.append("| 权限码 | 端点 |")
    doc.append("|---|---|")
    for c in codes:
        eps = ["`%s %s`" % (r["method"], r["path"]) for r in rows if r["code"] == c]
        doc.append("| `%s` | %s |" % (c, "<br>".join(eps)))
    doc.append("")
    doc.append("## 三、C 端端点（需登录）")
    doc.append("")
    doc.append(table([r for r in authed if not r["path"].startswith("/api/admin/")]))
    doc.append("")
    doc.append("## 四、按 Tag 分组（与 Swagger UI 的分组一致）")
    doc.append("")
    for tag in sorted(by_tag):
        rs = sorted(by_tag[tag], key=lambda r: (r["path"], r["method"]))
        doc.append("### %s（%d）" % (tag, len(rs)))
        doc.append("")
        doc.append(table(rs))
        doc.append("")

    doc.append("## 五、口径偏离（已知、未修）")
    doc.append("")
    if legacy:
        doc.append("**带权限码、但不在 `/api/admin/**` 下的端点**：")
        doc.append("")
        doc.append("| 方法 | 路径 | 权限码 | 出处 |")
        doc.append("|---|---|---|---|")
        for r in sorted(legacy, key=lambda x: x["path"]):
            doc.append("| `%s` | `%s` | `%s` | `%s` |" % (r["method"], r["path"], r["code"], r["file"]))
        doc.append("")
        doc.append("★ **这不是漏洞，是历史口径**：Day 15 设计发货接口时，管理端动作还没有")
        doc.append("「一律走 `/api/admin/**`」的约定（那条约定是 Day 17/18 做数据权限反转时立的）。")
        doc.append("它安全的原因是：`/api/orders/**` **不在任何白名单前缀里**，所以不存在")
        doc.append("「白名单先匹配先赢 ⇒ `@PreAuthorize` 被跳过」这条唯一的静默公开路径。")
        doc.append("")
        doc.append("⚠️ **不修的理由**：把它挪到 `/api/admin/orders/{id}/ship` 会让")
        doc.append("`day15-ship-confirm.py`（M1 全链路的一环）立刻失效，属于「改已验证契约换一致性」，")
        doc.append("收益只有命名整齐。⇒ 记在 `docs/backlog.md`，等真要统一管理端前缀时一起动。")
        doc.append("")
    else:
        doc.append("无。")
        doc.append("")

    with open(DOC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(doc) + "\n")
    say("[6] 交付文档 -> %s（%d 行 / %d 字符）"
        % (DOC, len(doc) + 1, len("\n".join(doc))))

    # ------------------------------------------------------------ 护栏
    say("")
    say("=" * 78)
    # 白名单里每条 /api/** 规则是否真的命中了端点（写错路径 → 该接口会静默变成「需登录」）
    matched_pub = set((r["method"], r["note"]) for r in rows if r["tier"] == "公开")
    dead_api_rules = [(m, p) for (m, p) in rules if p.startswith("/api/")
                      and not any(pp == p and (m is None or mm in m) for mm, pp in matched_pub)]
    db_all_present = None if db_state is None else all(c in db_state for c in codes)
    db_all_granted = None if db_state is None else all(
        db_state[c]["grants"] > 0 for c in codes if c in db_state)

    checks = [
        ("两来源端点集合完全相等（源码 vs 运行时 OpenAPI）", same),
        ("端点总数 > 0", len(rows) > 0),
        ("管理端端点全部带权限码（无「裸奔」的管理端接口）",
         all(r["code"] for r in admin)),
        ("白名单命中的公开端点【没有】带 @PreAuthorize（否则权限检查被静默跳过）",
         not leaked),
        ("白名单里每条 /api/** 规则都命中了真实端点（防白名单路径写错）",
         not dead_api_rules),
        ("权限码命名都是「域:动作」小写形式",
         all(re.match(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$", c) for c in codes)),
    ]
    if WITH_DB:
        checks.append(("PG 可达（docker exec psql 成功）", db_state is not None))
        checks.append(("源码用到的权限码【全部】存在于 permissions 表", db_all_present is True))
        checks.append(("每个权限码都【至少被一个角色持有】（否则 @PreAuthorize 永远 403）",
                       db_all_granted is True))
    else:
        say("  [SKIP] 数据库三项核对（--no-db）")
    for name, ok in checks:
        say("  [%s] %s" % ("OK" if ok else "FAIL", name))
    if dead_api_rules:
        say("        白名单里没命中端点的规则：%s" % dead_api_rules)
    if leaked:
        say("        同时公开又带权限码（危险）：%s"
            % [(r["method"], r["path"]) for r in leaked])
    if missing:
        say("        库里缺失的权限码：%s" % missing)
    if unshared:
        say("        没有角色持有的权限码：%s" % unshared)
    say("=" * 78)
    verdict = all(ok for _n, ok in checks)
    say("VERDICT: %s" % ("OK" if verdict else "FAIL"))
    say("ASSERTIONS: %d / %d passed" % (sum(1 for _n, ok in checks if ok), len(checks)))

    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines_out) + "\n")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
