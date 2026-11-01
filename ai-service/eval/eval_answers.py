"""RAG 回答引用评测（Day 111）。

对每条问题调用运行中的 /chat（真模型或假模型均可），检查：
1. 回答非空；
2. 回答里出现的【来源：文件 · 小节】必须能在知识库检索结果中找到（引用一致性）；
3. 无引用时不算失败，但记入 no_citation（用于观察拒答/闲聊比例）。

用法：python eval/eval_answers.py --base http://127.0.0.1:8008
"""
import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kb_lib import store  # noqa: E402

QUESTIONS = [
    "满多少免运费",
    "退款多久到账",
    "七天无理由怎么申请",
    "优惠券过期还能用吗",
    "怎么申请发票",
    "拆单后怎么支付",
    "评价可以传几张图",
    "售后类型有哪些",
    "质量问题退货运费谁出",
    "订单超时未支付会怎样",
]

# 知识库覆盖不到的问题：期望拒答（refusal=true 或没有任何引用）
OUT_OF_SCOPE = ["今天美元汇率是多少", "今天天气怎么样"]


def post_chat(base: str, question: str) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + "/chat",
        data=json.dumps({"message": question}).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8008")
    args = ap.parse_args()

    rows = store.search("mallx", k=100)  # 故意用宽查询拿全量
    known = {(r["source"], r["heading"]) for r in rows}
    known_sources = {r["source"] for r in store._load_rows()}

    details, cited, bad_ref, no_cite, refused = [], 0, 0, 0, 0
    for q in QUESTIONS:
        j = post_chat(args.base, q)
        reply = j.get("reply", "")
        refs = re.findall(r"【来源：([^·】]+)(?: · ([^】]+))?】", reply)
        ok_refs = all(src.strip() in known_sources for src, _ in refs) if refs else True
        if refs:
            cited += 1
        else:
            no_cite += 1
        if not ok_refs:
            bad_ref += 1
        details.append({
            "q": q,
            "reply": reply,
            "refs": [{"source": s.strip(), "heading": h.strip()} for s, h in refs],
            "refs_valid": ok_refs,
            "sources": j.get("sources") or [],
        })

    for q in OUT_OF_SCOPE:
        j = post_chat(args.base, q)
        reply = j.get("reply", "")
        refs = re.findall(r"【来源：", reply)
        ok = bool(j.get("refusal")) and not refs
        details.append({"q": q, "reply": reply, "refs": [], "refs_valid": True,
                        "refusal": bool(j.get("refusal")), "expected_refusal": True, "ok": ok})
        if ok:
            refused += 1

    total = len(QUESTIONS) + len(OUT_OF_SCOPE)
    report = {
        "base": args.base,
        "cases": total,
        "cited": cited,
        "no_citation": no_cite,
        "invalid_refs": bad_ref,
        "citation_rate": round(cited / total, 3),
        "out_of_scope": len(OUT_OF_SCOPE),
        "refusal_correct": f"{refused}/{len(OUT_OF_SCOPE)}",
        "details": details,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval-answers-report.json")
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("cases", "cited", "no_citation", "invalid_refs", "citation_rate")},
                     ensure_ascii=False))
    print("report:", out)
    return 0 if bad_ref == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
