package com.mallx.ai.service;

import com.mallx.aftersale.service.RefundService;
import com.mallx.aftersale.vo.RefundVO;
import com.mallx.common.api.PageResult;
import com.mallx.order.service.OrderService;
import com.mallx.order.vo.OrderVO;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductSearchVO;
import com.baomidou.mybatisplus.core.metadata.IPage;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * 客服的【只读工具】（Day 59）。
 *
 * <p>★★ 三条规则，比实现本身重要：
 * <ol>
 *   <li><b>工具不接受 userId 参数</b>：用户身份只在服务端从 token 取，再传进来。
 *       让模型「决定查谁」等于把越权交给一个会被提示注入的组件。</li>
 *   <li><b>只读</b>：第一版不提供下单/退款/改地址工具。模型只能「查」和「引导」，
 *       写操作仍然必须由用户在页面上亲手完成。</li>
 *   <li><b>返回值是给人看的中文</b>：模型拿到的是可读文本，不是裸 JSON ——
 *       减少「把 id 当金额」这类误读，也让 mock 模式可以原样返回。</li>
 * </ol>
 */
@Component
public class AiTools {

    private final ProductService productService;
    private final OrderService orderService;
    private final RefundService refundService;

    public AiTools(ProductService productService, OrderService orderService, RefundService refundService) {
        this.productService = productService;
        this.orderService = orderService;
        this.refundService = refundService;
    }

    /** 售前：按关键词搜商品（复用 C 端搜索，包含中文兜底 ILIKE） */
    public String searchProducts(String keyword) {
        String kw = keyword == null ? "" : keyword.trim();
        if (kw.isEmpty()) {
            return "没有提供关键词，无法搜索商品。";
        }
        IPage<ProductSearchVO> page = productService.searchProducts(1, 5, kw, null, null, null);
        if (page.getRecords().isEmpty()) {
            return "没有搜到与「" + kw + "」相关的商品。可以换个说法，或看看分类导航。";
        }
        StringBuilder sb = new StringBuilder("搜到这些商品：\n");
        int i = 1;
        for (ProductSearchVO p : page.getRecords()) {
            sb.append(i++).append(". ").append(p.getName());
            if (p.getMinPrice() != null) {
                sb.append("（¥").append(money(p.getMinPrice())).append(" 起）");
            }
            if (p.getSubtitle() != null && !p.getSubtitle().isBlank()) {
                sb.append(" —— ").append(p.getSubtitle());
            }
            sb.append("\n");
        }
        sb.append("可以点商品名进详情页看规格与库存。");
        return sb.toString();
    }

    /** 售后查询：当前用户最近 5 张订单 */
    public String myOrders(Long userId, String status) {
        if (userId == null) {
            return "用户未登录，无法查询订单。请先登录后再问。";
        }
        String safe = (status == null || status.isBlank()) ? null : status.trim();
        PageResult<OrderVO> page = orderService.listMyOrders(userId, 1, 5, safe);
        if (page.getRecords().isEmpty()) {
            return "没有查到订单记录。你可以在「个人中心 → 我的订单」里看全部订单。";
        }
        StringBuilder sb = new StringBuilder("你最近的订单：\n");
        for (OrderVO o : page.getRecords()) {
            sb.append("· ").append(o.getOrderNo())
              .append("：").append(orderStatus(o.getStatus()))
              .append("，实付 ¥").append(money(o.getPayAmount()))
              .append("\n");
        }
        sb.append("要看详情或处理，去「个人中心 → 我的订单」。");
        return sb.toString();
    }

    /** 售后查询：当前用户最近 5 条售后单 */
    public String myRefunds(Long userId) {
        if (userId == null) {
            return "用户未登录，无法查询售后。请先登录后再问。";
        }
        PageResult<RefundVO> page = refundService.listMine(userId, 1, 5);
        if (page.getRecords().isEmpty()) {
            return "没有查到售后记录。需要退款时，在订单详情里点「申请售后」。";
        }
        StringBuilder sb = new StringBuilder("你最近的售后：\n");
        for (RefundVO r : page.getRecords()) {
            sb.append("· ").append(r.getRefundNo())
              .append("：").append(refundType(r.getType()))
              .append(" / ").append(refundStatus(r.getStatus()))
              .append("，金额 ¥").append(money(r.getAmount()))
              .append("\n");
        }
        sb.append("进度可以在「个人中心 → 我的售后」里查看。");
        return sb.toString();
    }

    private static String money(BigDecimal v) {
        if (v == null) {
            return "-";
        }
        return v.setScale(2, RoundingMode.HALF_UP).toPlainString();
    }

    private static String orderStatus(String s) {
        if (s == null) {
            return "未知";
        }
        return switch (s) {
            case "PENDING_PAYMENT" -> "待支付";
            case "PAID" -> "已支付（待发货）";
            case "SHIPPED" -> "已发货";
            case "COMPLETED" -> "已完成";
            case "CANCELLED" -> "已取消";
            default -> s;
        };
    }

    private static String refundType(String t) {
        return "RETURN_REFUND".equals(t) ? "退货退款" : "仅退款";
    }

    private static String refundStatus(String s) {
        if (s == null) {
            return "未知";
        }
        return switch (s) {
            case "APPLIED" -> "待审核";
            case "APPROVED" -> "审核通过";
            case "RETURNING" -> "买家已寄出";
            case "REFUNDING" -> "待打款";
            case "SUCCESS" -> "退款成功";
            case "REJECTED" -> "已拒绝";
            case "CANCELLED" -> "已撤销";
            default -> s;
        };
    }
}
