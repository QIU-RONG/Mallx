# -*- coding: utf-8 -*-
"""Day 16 skeleton smoke test.

Purpose
-------
`day16-review-e2e.py` is the real acceptance standard - it asserts behaviour that
only exists once the business code is written. This script is the *earlier* gate:
it proves the SCAFFOLDING is correct, before a single line of logic is filled in.

What "correct scaffolding" means here, and how each item is proven:

  1. the two new mapper XMLs PARSE (a doubly-hyphenated XML comment is the classic
     trap: Maven copies the file happily, MyBatis only explodes at startup)
  2. `mall-review` is wired into `mall-server` at all - if the dependency is
     missing you get "compiles, boots, 404", the nastiest failure in this project
  3. the three review endpoints are ROUTED, and the security rules land where
     they were designed to:
        GET  /api/products/{id}/reviews   -> reachable WITHOUT a token
        POST /api/reviews                 -> real HTTP 401 without a token
        GET  /api/reviews/my              -> real HTTP 401 without a token
  4. bean validation on the DTO is live (rating range, content length), because
     the skeleton already carries the annotations
  5. the two DDL constraints from `../sql/04-review-constraints.sql` are in place

Why some assertions look lenient
--------------------------------
While the method bodies are `TODO`, business codes come back as 500
(UnsupportedOperationException -> GlobalExceptionHandler's catch-all). After the
user fills in the logic they become 200. So this script asserts only the parts
that are TRUE IN BOTH PHASES, and prints the observed code next to each one:

    phase = SKELETON  -> expect code=500 on the three "reachable" endpoints
    phase = DONE      -> expect code=200 there

Nothing here writes to the database, so there is no cleanup and it is trivially
re-runnable.

Usage:
    python day16-skeleton-smoke.py
"""
import json
import subprocess
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
import os
# ★ Portability (CI runs on Linux): MALLX_DOCKER overrides this path.
#   Unset locally => identical behaviour to before.
DOCKER = os.environ.get("MALLX_DOCKER") or r"C:\Users\TIE\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"

_lines = []


def say(s=""):
    _lines.append(s)


def api(method, path, token=None, body=None):
    """-> (http_status, raw_text). ★ 必须禁代理：system 代理会把 127.0.0.1 也拦下。"""
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                            # noqa: BLE001
        return -1, '{"transport_error": "%s"}' % repr(e)


def code_of(raw):
    """★ 项目约定：业务码在 body.code 里，HTTP 一律 200（Security 层的 401/403 是唯一例外）。"""
    try:
        return json.loads(raw).get("code")
    except ValueError:
        return None


def psql(sql):
    p = subprocess.run(
        [DOCKER, "exec", "-i", "-e", "PGCLIENTENCODING=UTF8",
         "mallx-postgres", "psql", "-U", "mallx", "-d", "mallx",
         "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True)
    out = p.stdout.decode("utf-8", "replace").strip()
    err = p.stderr.decode("utf-8", "replace").strip()
    if p.returncode != 0 or "ERROR" in err:
        raise RuntimeError("psql failed\nSQL: %s\nstderr: %s" % (sql, err))
    return out


def main():
    checks = []

    def chk(name, good):
        checks.append((name, bool(good)))

    say("=" * 78)
    say("Day 16 skeleton smoke test - is the scaffolding wired correctly?")
    say("target: %s" % BASE)
    say("=" * 78)

    # ------------------------------------------------------------ [1] app alive
    say("\n[1] the application answers at all")
    st, raw = api("GET", "/api/hello")
    say("  GET /api/hello -> http=%s" % st)
    chk("app is up", st == 200)
    if st != 200:
        say("\nABORT: the application is not running on 8080")
        _flush(checks)
        return 1

    # ------------------------------------------------------------ [2] logins
    say("\n[2] login (the token never touches disk)")
    st, raw = api("POST", "/api/auth/login", body={"username": "demo", "password": "demo123"})
    demo = ((json.loads(raw) or {}).get("data") or {}).get("token")
    say("  POST /api/auth/login -> http=%s code=%s token_len=%d"
        % (st, code_of(raw), len(demo or "")))
    chk("demo can log in", bool(demo))

    # ------------------------------------- [3] mall-review is reachable at all
    say("\n[3] ★ mall-review is wired into mall-server (missing jar dependency = 404 here)")
    st, raw = api("GET", "/api/products/1/reviews?page=1&size=10")
    c = code_of(raw)
    say("  GET /api/products/1/reviews   (NO token) -> http=%s code=%s" % (st, c))
    say("      phase SKELETON -> code=500 expected (body is UnsupportedOperationException)")
    say("      phase DONE     -> code=200 expected")
    chk("★ the public product-review endpoint is routed (no 404, no 401)", st == 200)
    chk("★★ it is reachable WITHOUT a token - the GET /api/products/** whitelist covers it",
        st == 200 and c != 401)
    chk("   body code is either 500 (skeleton) or 200 (implemented)", c in (200, 500))

    st2, raw2 = api("GET", "/api/products/999999/reviews?page=1&size=10")
    say("  GET /api/products/999999/reviews (NO token) -> http=%s code=%s"
        % (st2, code_of(raw2)))
    chk("★ the whitelist covers any product id, not just the ones that exist", st2 == 200)

    # ------------------------------------------------- [4] security boundaries
    say("\n[4] the two authenticated endpoints must reject anonymous callers")
    st3, raw3 = api("POST", "/api/reviews", body={"orderItemId": 1, "rating": 5})
    say("  POST /api/reviews   (NO token) -> http=%s %s"
        % (st3, raw3.replace("\n", " ")[:90]))
    chk("★ anonymous POST /api/reviews gets a REAL http 401 (not a body code)",
        st3 == 401)

    st4, raw4 = api("GET", "/api/reviews/my?page=1&size=10")
    say("  GET  /api/reviews/my (NO token) -> http=%s %s"
        % (st4, raw4.replace("\n", " ")[:90]))
    chk("★ anonymous GET /api/reviews/my gets a REAL http 401", st4 == 401)

    say("  ★ 说明：这两个 401 与白名单【无关】—— 它们在 anyRequest().authenticated() 的辖区内。")
    say("     商品列表那条才是白名单的功劳（同样匿名，却进得去）。")

    # --------------------------------------------- [5] routing with a real token
    say("\n[5] with a token, the two authenticated endpoints are routed")
    # orderItemId=1 does not exist -> a FINISHED implementation answers
    # 404 with the message "订单明细不存在". That 404 lives in body.code, so the
    # HTTP status stays 200 and this assertion must accept 404 as a PASS.
    # (Skeleton phase: 500 from UnsupportedOperationException. Finished: 400/404.)
    st5, raw5 = api("POST", "/api/reviews", token=demo,
                    body={"orderItemId": 1, "rating": 5, "content": "smoke"})
    say("  POST /api/reviews (demo token, bogus orderItemId) -> http=%s code=%s"
        % (st5, code_of(raw5)))
    say("      skeleton -> 500 (UnsupportedOperationException)")
    say("      finished -> 404 = \"订单明细不存在\"  <- the fake 404 rides in body.code")
    chk("★ authenticated POST /api/reviews is routed (not 401/403/404-as-HTTP)",
        st5 == 200 and code_of(raw5) in (200, 400, 404, 500))

    st6, raw6 = api("GET", "/api/reviews/my?page=1&size=10", token=demo)
    say("  GET  /api/reviews/my (demo token) -> http=%s code=%s" % (st6, code_of(raw6)))
    chk("★ authenticated GET /api/reviews/my is routed",
        st6 == 200 and code_of(raw6) in (200, 500))

    # ------------------------------------------------ [6] bean validation alive
    say("\n[6] ★ DTO validation is already live - it runs BEFORE the TODO body")
    for label, payload in [
            ("rating = 0   ", {"orderItemId": 1, "rating": 0}),
            ("rating = 6   ", {"orderItemId": 1, "rating": 6}),
            ("rating = null", {"orderItemId": 1, "rating": None}),
            ("content 501ch", {"orderItemId": 1, "rating": 5, "content": "测" * 501}),
            ("no orderItemId", {"rating": 5}),
    ]:
        stx, rawx = api("POST", "/api/reviews", token=demo, body=payload)
        say("  %-15s -> http=%s code=%s msg=%s"
            % (label, stx, code_of(rawx),
               (json.loads(rawx).get("message") if code_of(rawx) is not None else rawx)[:40]))
        chk("★ %s refused with code=400" % label.strip(), code_of(rawx) == 400)
    say("  ★ 这一组在业务代码还没写的时候就能过 —— 因为注解挂在 DTO 上，@Valid 先跑。")
    say("    这正说明：参数校验与业务逻辑是两层，谁都不该越位。")

    # ------------------------------------------------------ [7] DDL still armed
    say("\n[7] the two DDL constraints from 04-review-constraints.sql are in place")
    nullable = psql("SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_name='reviews' AND column_name='order_item_id'").strip()
    cons = psql("SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conrelid='reviews'::regclass AND conname='uk_reviews_order_item'").strip()
    rows = psql("SELECT count(*) FROM reviews").strip()
    say("  order_item_id.is_nullable = %s   (must be NO)" % nullable)
    say("  uk_reviews_order_item     = %s" % (cons or "(missing)"))
    say("  reviews rows              = %s" % rows)
    chk("★ order_item_id is NOT NULL (without it UNIQUE exempts NULL rows)",
        nullable == "NO")
    chk("★ UNIQUE (order_item_id) exists", "UNIQUE" in cons.upper())

    # ------------------------------------------------------------- summary
    _flush(checks)
    return 0


def _flush(checks):
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    say("\n" + "=" * 78)
    say("SKELETON CHECKS: %d / %d passed" % (passed, total))
    if passed != total:
        say("\nFAILED:")
        for name, ok in checks:
            if not ok:
                say("  [FAIL] %s" % name)
    say("=" * 78)
    with open("day16-skeleton-smoke-report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")
    print("\n".join(_lines[-8:]))
    print("report -> day16-skeleton-smoke-report.txt")


if __name__ == "__main__":
    raise SystemExit(main())
