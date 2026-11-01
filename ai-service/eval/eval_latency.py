"""首字延迟（TTFT）测量（Day 123）。

经 Java /api/ai/chat/stream 发起流式对话，记录从请求发出到第一个 delta 事件的时间。
注意：当前架构是「先算完整答案再切片推送」，所以这个值≈完整生成耗时（含工具轮），
不是模型 token 级 TTFT —— 报告中已标明口径。

用法：python eval/eval_latency.py --base http://127.0.0.1:8081
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.request

QUESTIONS = [
    "满多少免运费",
    "七天无理由怎么申请",
    "退款多久到账",
    "优惠券过期还能用吗",
    "怎么开发票",
]


def first_delta_ms(base: str, message: str) -> int:
    req = urllib.request.Request(
        base.rstrip("/") + "/api/ai/chat/stream",
        data=json.dumps({"message": message}).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    started = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        buf = ""
        while True:
            chunk = r.read(256)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "replace")
            if "event:delta" in buf:
                return int((time.time() - started) * 1000)
    return -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8081")
    args = ap.parse_args()

    samples = []
    for q in QUESTIONS:
        ms = first_delta_ms(args.base, q)
        samples.append({"q": q, "firstDeltaMs": ms})
        print(ms, "ms", q)

    valid = [s["firstDeltaMs"] for s in samples if s["firstDeltaMs"] >= 0]
    report = {
        "base": args.base,
        "note": "端到端首字延迟（架构为整段生成后切片推送，非模型 token 级 TTFT）",
        "samples": samples,
        "p50_ms": int(statistics.median(valid)) if valid else None,
        "avg_ms": int(statistics.mean(valid)) if valid else None,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval-latency-report.json")
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("p50", report["p50_ms"], "avg", report["avg_ms"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
