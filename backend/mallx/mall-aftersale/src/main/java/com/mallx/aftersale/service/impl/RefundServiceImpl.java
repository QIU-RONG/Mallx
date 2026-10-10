package com.mallx.aftersale.service.impl;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.aftersale.common.RefundStatus;
import com.mallx.aftersale.common.RefundType;
import com.mallx.aftersale.dto.RefundApplyDTO;
import com.mallx.aftersale.dto.RefundShipDTO;
import com.mallx.aftersale.entity.Refund;
import com.mallx.aftersale.mapper.RefundMapper;
import com.mallx.aftersale.service.RefundService;
import com.mallx.aftersale.vo.AdminRefundVO;
import com.mallx.aftersale.vo.RefundVO;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.marketing.service.CouponService;
import com.mallx.order.service.OrderService;
import com.mallx.order.vo.OrderRefundContext;
import com.mallx.order.vo.OrderRefundItem;
import com.mallx.payment.service.PaymentService;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

/**
 * ★★★ 售后/退款服务实现（Day 46）。
 *
 * <p>★★ <b>本类的依赖图位置</b>：{@code mall-aftersale} 是依赖图的【叶子】——
 * 它依赖 order / payment / inventory / marketing，而它们<b>都不依赖它</b>。
 * 之所以必须独立成模块：退款既要读订单状态、又要写负向支付流水，
 * 若塞进 {@code mall-order} 就会形成 {@code order → payment} 的循环依赖
 * （{@code payment → order} 早就存在），构建直接失败。
 * ★ 这是「循环依赖会逼你把模块切对」的一个实例。
 *
 * <p>★★★ <b>本类唯一会动钱的方法是 {@link #executeRefund}</b>。
 * 其余六个方法（申请 / 撤销 / 寄出 / 审核通过 / 审核拒绝 / 确认收货）
 * 全都<b>只改退款单自己的状态</b>，不动订单、不动库存、不动钱。
 * ★ 这条边界是刻意划的：把「动钱」收敛到一个方法里，
 * 审计时只需要读一处；出问题时也只有一处可疑。
 */
@Service
public class RefundServiceImpl implements RefundService {

    /** 分页上限 —— 与其余模块同一个值、同一套夹紧规则（本项目第 7 份拷贝） */
    private static final long MAX_PAGE_SIZE = 100;

    private final RefundMapper refundMapper;
    private final OrderService orderService;
    private final PaymentService paymentService;
    private final InventoryService inventoryService;
    private final CouponService couponService;

    public RefundServiceImpl(RefundMapper refundMapper,
                             OrderService orderService,
                             PaymentService paymentService,
                             InventoryService inventoryService,
                             CouponService couponService) {
        this.refundMapper = refundMapper;
        this.orderService = orderService;
        this.paymentService = paymentService;
        this.inventoryService = inventoryService;
        this.couponService = couponService;
    }

    // ================================================================
    // C 端
    // ================================================================

    @Override
    public Long apply(Long userId, RefundApplyDTO dto) {
        // ① 取订单事实 —— 归属过滤写死在 SQL 里 ⇒ null 同时表示「不存在」与「不是你的」
        OrderRefundContext ctx = orderService.getRefundContext(userId, dto.getOrderId());
        if (ctx == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "订单不存在");
        }

        // ② ★★ 关系校验：这个售后类型与订单当前状态是否匹配
        //    （★ 这是本模块最重要的一条业务规则，@Valid 表达不了，只能在这里守）
        if (!RefundType.isValid(dto.getType())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "售后类型只能是 REFUND_ONLY（仅退款）或 RETURN_REFUND（退货退款）");
        }
        String suggested = RefundType.suggestFor(ctx.getStatus());
        if (suggested == null) {
            // 订单压根不在可退款的状态里（待支付 / 已取消 / 已退款）
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "订单当前状态（" + ctx.getStatus() + "）不支持申请售后");
        }
        if (!suggested.equals(dto.getType())) {
            // ★ 给一句人话，别只说「不允许」—— 用户要的是「那我该选哪个」
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    RefundType.REFUND_ONLY.equals(suggested)
                            ? "订单尚未发货，请申请【仅退款】"
                            : "订单已发货，请申请【退货退款】");
        }

        // ③ 人话提示（★ 不是防线 —— 真正的防线是 uk_refunds_active_order 那条部分唯一索引）
        if (refundMapper.countActiveByOrder(dto.getOrderId()) > 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该订单已有进行中的售后单，不能重复申请");
        }

        Refund refund = new Refund();
        refund.setRefundNo(generateRefundNo());
        refund.setOrderId(ctx.getId());
        refund.setUserId(userId);
        refund.setType(dto.getType());
        refund.setStatus(RefundStatus.APPLIED);
        // ★ 退款额 = 服务端读出的实付快照；V1.0 只支持全额退款
        refund.setAmount(ctx.getPayAmount());
        refund.setReason(dto.getReason());
        refund.setAppliedAt(LocalDateTime.now());   // 业务时间戳手写（不挂 fill）
        try {
            refundMapper.insert(refund);
        } catch (DataIntegrityViolationException e) {
            // ★★★ 这不是「防御性编程」，是③那条 SELECT 命中不了的那部分请求的唯一归宿。
            //     两个并发申请会同时通过 countActiveByOrder（TOCTOU），
            //     第二条的 INSERT 撞上 uk_refunds_active_order 抛出本异常。
            //     不接住它 ⇒ 冒泡到 GlobalExceptionHandler 的 Exception.class 兜底
            //     ⇒ 前端看到 HTTP 200 + code 500「系统异常」，而实际是「你已经申请过了」。
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该订单已有进行中的售后单，不能重复申请");
        }
        return refund.getId();
    }

    @Override
    public PageResult<RefundVO> listMine(Long userId, long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);   // ★ 夹紧必须在 new Page 之前
        Page<RefundVO> p = new Page<>(safePage, safeSize);
        return PageResult.of(refundMapper.selectMyRefunds(p, userId));
    }

    @Override
    public RefundVO detailMine(Long userId, Long refundId) {
        RefundVO vo = refundMapper.selectMyOne(userId, refundId);
        if (vo == null) {
            // ★ 「不存在」与「不是你的」合成同一句 —— IDOR 伪装 404
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "售后单不存在");
        }
        return vo;
    }

    @Override
    public void cancel(Long userId, Long refundId) {
        if (refundMapper.cancelByUser(userId, refundId) == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该售后单不存在、不是你的，或已不在「待审核」状态");
        }
    }

    @Override
    public void ship(Long userId, Long refundId, RefundShipDTO dto) {
        if (refundMapper.ship(userId, refundId, dto.getTrackingNo()) == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该售后单不能寄出：仅【退货退款】在【审核通过】后才能填写物流单号");
        }
    }

    // ================================================================
    // 管理端
    // ================================================================

    @Override
    public PageResult<AdminRefundVO> listAll(String status, Long userId, long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        Page<AdminRefundVO> p = new Page<>(safePage, safeSize);
        return PageResult.of(refundMapper.selectAdminRefunds(p, status, userId));
    }

    @Override
    public void approve(Long refundId, String remark) {
        if (refundMapper.approve(refundId, remark) == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该售后单不存在，或已不在「待审核」状态");
        }
    }

    @Override
    public void reject(Long refundId, String remark) {
        if (refundMapper.reject(refundId, remark) == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该售后单不存在，或已不在「待审核」状态");
        }
    }

    @Override
    public void receive(Long refundId) {
        if (refundMapper.receive(refundId) == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该售后单不存在，或尚未寄出（只有【已寄出】才能确认收货）");
        }
    }

    @Override
    @Transactional
    public void executeRefund(Long refundId) {
        Refund refund = refundMapper.selectById(refundId);
        if (refund == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "售后单不存在");
        }

        // ① ★★ 抢资格必须【第一步】：CAS 把退款单推进到 SUCCESS。
        //    0 行 = 已被别人退过 / 状态不对（退货退款还没收货） ⇒ 什么都不做就退出。
        if (refundMapper.markSuccess(refundId) == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该售后单当前状态不允许执行退款（仅退款需【审核通过】、退货退款需【已收货】）");
        }

        // ② 订单 → REFUNDED（CAS；REFUNDED 不在它的起点集合里 ⇒ 同一张单不可能退两次）
        orderService.markRefunded(refund.getOrderId());

        // ③ 逐 SKU 回补库存：sold → available（★ 不是 releaseLocked —— 那一条是「没付过钱」的路径）
        List<OrderRefundItem> items = orderService.listItemsForRefund(refund.getOrderId());
        if (items.isEmpty()) {
            // 与 OrderCancelExecutor 同口径：没有明细就无法回补，属账目不一致 → 500 整笔回滚
            throw new BusinessException(ResultCode.FAIL.getCode(), "订单明细缺失，退款已回滚");
        }
        for (OrderRefundItem item : items) {
            inventoryService.returnToStock(item.getSkuId(), item.getQuantity(), refund.getOrderId());
        }

        // ④ 退券：★ 0 行是【正常】的（这一单没用券），绝不当失败处理
        couponService.releaseByOrder(refund.getOrderId());

        // ⑤ 负向支付流水（金额存负数 ⇒ 对账退化成 SUM(amount)）
        paymentService.recordRefund(refund.getOrderId(), refund.getAmount());
    }

    // ================================================================
    // 工具
    // ================================================================

    /**
     * 退款单号：{@code AS + yyyyMMddHHmmssSSS + 4 位随机}，如 {@code AS202610102215301234567}。
     *
     * <p>★ 前缀 {@code AS}（After-Sale）<b>刻意与支付流水的 {@code PAY}/{@code RFD} 不同</b>：
     * 两张表各有一套号，一眼能分辨是「售后单号」还是「资金流水号」，
     * 排查问题时不用先猜这是哪个系统的号。
     */
    private String generateRefundNo() {
        return "AS"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS"))
                + String.format("%04d", ThreadLocalRandom.current().nextInt(10_000));
    }
}
