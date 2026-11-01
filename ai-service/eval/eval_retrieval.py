"""RAG 检索评测（Day 109）。

不依赖大模型：对每个问题取 top-4 切片，看是否命中期望关键词，
输出 hit@1 / hit@4 与逐题明细；可复跑、可进 CI。

用法：cd ai-service && .venv/Scripts/python.exe eval/eval_retrieval.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kb_lib import store  # noqa: E402

CASES = [
    {"q": "满多少免运费", "expect": ["99", "运费"]},
    {"q": "怎么申请七天无理由退货", "expect": ["7 天", "退货", "无理由"]},
    {"q": "退款多久到账", "expect": ["1-3", "退款"]},
    {"q": "多店铺的商品怎么发货", "expect": ["拆", "发货"]},
    {"q": "优惠券过期还能用吗", "expect": ["过期", "券"]},
    {"q": "发票怎么开", "expect": ["发票"]},
    {"q": "待支付订单可以取消吗", "expect": ["取消", "待支付"]},
    {"q": "库存为零还能买吗", "expect": ["库存"]},
    {"q": "售后类型有哪些", "expect": ["退款", "退货"]},
    {"q": "手机号验证码多久有效", "expect": ["5 分钟", "验证码"]},
    {"q": "拆单后运费怎么算", "expect": ["运费", "拆单"]},
    {"q": "评价可以传图片吗", "expect": ["3 张", "评价"]},
    {"q": "怎么查物流", "expect": ["物流", "订单详情"]},
    {"q": "质量问题退货运费谁出", "expect": ["商家", "运费"]},
    {"q": "合并支付怎么操作", "expect": ["合并支付", "拆单"]},
]


def main() -> int:
    hit1 = hit4 = 0
    details = []
    for case in CASES:
        rows = store.search(case["q"], k=4)
        texts = [f"{r['source']} {r['heading']} {r['content']}" for r in rows]
        top1_hit = bool(texts) and all(k in texts[0] for k in case["expect"])
        any_hit = any(all(k in t for k in case["expect"]) for t in texts)
        hit1 += 1 if top1_hit else 0
        hit4 += 1 if any_hit else 0
        details.append({
            "q": case["q"],
            "hit@1": top1_hit,
            "hit@4": any_hit,
            "top": rows[0] if rows else None,
        })
    n = len(CASES)
    report = {
        "cases": n,
        "hit@1": f"{hit1}/{n}",
        "hit@4": f"{hit4}/{n}",
        "hit@4_rate": round(hit4 / n, 3),
        "details": details,
    }
    out_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(out_dir, "eval-retrieval-report.json")
    json.dump(report, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("cases", "hit@1", "hit@4", "hit@4_rate")}, ensure_ascii=False))
    print("report:", path)
    return 0 if hit4 == n else 1


if __name__ == "__main__":
    sys.exit(main())
