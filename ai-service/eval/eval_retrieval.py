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
    {"q": '满多少免运费', "expect": ['99', '运费']},
    {"q": '不满 99 运费多少', "expect": ['8', '运费']},
    {"q": '几天内发货', "expect": ['48']},
    {"q": '偏远地区发货会延迟吗', "expect": ['偏远', '延迟']},
    {"q": '预售商品什么时候发货', "expect": ['预售']},
    {"q": '物流单号在哪里看', "expect": ['物流']},
    {"q": '确认收货后还能退货吗', "expect": ['确认收货', '7 天']},
    {"q": '拆单后运费怎么算', "expect": ['拆单', '运费']},
    {"q": '多个店铺的商品会一起发吗', "expect": ['店铺', '拆']},
    {"q": '包邮门槛是多少', "expect": ['99']},
    {"q": '怎么申请七天无理由', "expect": ['7 天', '无理由']},
    {"q": '七天无理由从哪天算', "expect": ['签收']},
    {"q": '哪些商品不支持七天无理由', "expect": ['定制', '食品']},
    {"q": '售后类型怎么选', "expect": ['仅退款', '退货退款']},
    {"q": '售后入口在哪里', "expect": ['个人中心', '申请售后']},
    {"q": '退款多久到账', "expect": ['1-3']},
    {"q": '退款退到哪里', "expect": ['原路']},
    {"q": '质量问题退货运费谁出', "expect": ['商家']},
    {"q": '七天无理由退货运费谁出', "expect": ['买家']},
    {"q": '退货要寄回什么', "expect": ['配件']},
    {"q": '支持哪些支付方式', "expect": ['余额', '第三方']},
    {"q": '跨店订单怎么付款', "expect": ['合并支付']},
    {"q": '优惠券有门槛吗', "expect": ['门槛']},
    {"q": '优惠券过期还能用吗', "expect": ['过期']},
    {"q": '拆单能用优惠券吗', "expect": ['拆单', '优惠券']},
    {"q": '怎么开发票', "expect": ['发票']},
    {"q": '发票类型是什么', "expect": ['电子']},
    {"q": '发票要填什么', "expect": ['税号']},
    {"q": '待支付订单怎么取消', "expect": ['取消']},
    {"q": '取消订单库存会释放吗', "expect": ['库存']},
    {"q": '商品价格和规格有关吗', "expect": ['规格', '价格']},
    {"q": '划线价是实际价格吗', "expect": ['划线价']},
    {"q": '库存为 0 怎么办', "expect": ['库存', '到货']},
    {"q": '怎么联系客服推荐商品', "expect": ['推荐']},
    {"q": '商品分自营和入驻店吗', "expect": ['自营', '入驻']},
    {"q": '同一订单多个店铺怎么处理', "expect": ['拆', '订单']},
    {"q": '商品详情显示什么价格', "expect": ['SKU']},
    {"q": '库存不足能加购物车吗', "expect": ['库存', '购物车']},
    {"q": '推荐手机要看什么', "expect": ['推荐']},
    {"q": '店铺发货是各自发吗', "expect": ['店铺', '发货']},
    {"q": '验证码多久有效', "expect": ['5 分钟']},
    {"q": '验证码多久能发一次', "expect": ['60 秒']},
    {"q": '怎么添加收货地址', "expect": ['地址']},
    {"q": '默认地址怎么设置', "expect": ['默认']},
    {"q": '收藏的商品在哪里看', "expect": ['收藏']},
    {"q": '浏览记录在哪里', "expect": ['浏览记录']},
    {"q": '评价可以传几张图', "expect": ['3 张']},
    {"q": '评价可以按星级筛选吗', "expect": ['星级']},
    {"q": '只看有图的评价怎么看', "expect": ['有图']},
    {"q": '评价能修改吗', "expect": ['评价']},
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
