package com.mallx.aftersale.service.impl;

import com.mallx.aftersale.common.RefundStatus;
import com.mallx.aftersale.common.RefundType;
import com.mallx.aftersale.dto.RefundApplyDTO;
import com.mallx.aftersale.entity.Refund;
import com.mallx.aftersale.mapper.RefundMapper;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import com.mallx.marketing.service.CouponService;
import com.mallx.order.common.OrderStatus;
import com.mallx.order.service.OrderService;
import com.mallx.order.vo.OrderRefundContext;
import com.mallx.payment.service.PaymentService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ★ 售后域第一批单元测试（Day 46）—— 只测 {@code apply} 这一条入口的【判定】部分。
 *
 * <p>★★★ 本文件存在的<b>唯一理由</b>是第一条测试：
 * <pre>
 *   重复申请在单线程下由 countActiveByOrder 这条 SELECT 挡住，
 *   但它在【并发】下必然失效（TOCTOU）—— 真正守住不变式的是
 *   数据库那条部分唯一索引 uk_refunds_active_order。
 *   于是「撞索引」这条路径在端到端测试里是【概率性】的：
 *   8 个线程跑十次可能一次都撞不上（本机实测 8 线程全是 SELECT 拦下的 400）。
 *   ⇒ 概率性路径只能用单测【确定地】覆盖：直接让 insert 抛异常，
 *     断言它被翻译成业务失败 400，而不是冒泡成 500。
 * </pre>
 * ★ 这就是「单测与端到端互补」的实例：端到端证明链路通，单测证明分支对。
 *
 * <p>不启 Spring、不连库、不连 Redis：只 mock 五个协作者里的两个（读订单 + 写退款单）。
 */
@ExtendWith(MockitoExtension.class)
class RefundServiceImplTest {

    @Mock
    private RefundMapper refundMapper;
    @Mock
    private OrderService orderService;
    @Mock
    private PaymentService paymentService;
    @Mock
    private InventoryService inventoryService;
    @Mock
    private CouponService couponService;

    @InjectMocks
    private RefundServiceImpl service;

    private static final Long USER = 77L;
    private static final Long ORDER = 900L;

    // ================================================================
    // 工具
    // ================================================================

    private static OrderRefundContext ctx(String status, String payAmount) {
        OrderRefundContext c = new OrderRefundContext();
        c.setId(ORDER);
        c.setUserId(USER);
        c.setStatus(status);
        c.setPayAmount(new BigDecimal(payAmount));
        return c;
    }

    private static RefundApplyDTO dto(String type) {
        RefundApplyDTO d = new RefundApplyDTO();
        d.setOrderId(ORDER);
        d.setType(type);
        d.setReason("不想要了");
        return d;
    }

    /** ★ 服务端算出的实付快照 —— 客户端【传不进来】，只能从这里取 */
    private void givenOrder(String status, String payAmount) {
        when(orderService.getRefundContext(USER, ORDER)).thenReturn(ctx(status, payAmount));
    }

    // ================================================================
    // ① ★★ 并发兜底：唯一冲突必须翻译成业务失败
    // ================================================================

    @Test
    @DisplayName("insert 撞上唯一索引 -> BusinessException 400，绝不能冒成 500")
    void duplicateActiveRefund_becomesBusiness400() {
        givenOrder(OrderStatus.PAID, "6999.00");
        when(refundMapper.countActiveByOrder(ORDER)).thenReturn(0);
        // ★ 并发场景的确定性复现：第二个请求也通过了 SELECT，插库时撞索引
        when(refundMapper.insert(any(Refund.class)))
                .thenThrow(new DataIntegrityViolationException(
                        "duplicate key value violates unique constraint \"uk_refunds_active_order\""));

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.REFUND_ONLY)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        assertTrue(e.getMessage().contains("不能重复申请"),
                "消息要说清原因，实际=" + e.getMessage());
    }

    /**
     * ★ 反向对照：另一类唯一冲突（refund_no 撞号）也会被同一句 catch 接住 ——
     *   本测试不区分冲突来源，是因为对买家而言结论一样：「申请没成功，再试一次」。
     *   ⚠️ 这也说明 catch 的粒度是「整张表的唯一约束」，不是只认那一条索引。
     */
    @Test
    @DisplayName("其他唯一冲突（refund_no 撞号）同样翻译成 400")
    void otherUniqueViolation_alsoBecomes400() {
        givenOrder(OrderStatus.PAID, "6999.00");
        when(refundMapper.countActiveByOrder(ORDER)).thenReturn(0);
        when(refundMapper.insert(any(Refund.class)))
                .thenThrow(new DataIntegrityViolationException(
                        "duplicate key value violates unique constraint \"refunds_refund_no_key\""));

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.REFUND_ONLY)));
        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
    }

    // ================================================================
    // ② 放行路径：落库的字段必须来自服务端，不是客户端
    // ================================================================

    @Test
    @DisplayName("正常申请：退款额 = 服务端实付快照，状态 APPLIED，业务时间戳已写")
    void applyHappyPath_writesServerSideFacts() {
        givenOrder(OrderStatus.PAID, "6999.00");
        when(refundMapper.countActiveByOrder(ORDER)).thenReturn(0);
        doAnswer(inv -> {
            Refund r = inv.getArgument(0);
            r.setId(555L);                       // 模拟 MP 回填自增主键
            return 1;
        }).when(refundMapper).insert(any(Refund.class));

        Long id = service.apply(USER, dto(RefundType.REFUND_ONLY));
        assertEquals(555L, id);

        ArgumentCaptor<Refund> cap = ArgumentCaptor.forClass(Refund.class);
        verify(refundMapper).insert(cap.capture());
        Refund saved = cap.getValue();

        assertEquals(0, new BigDecimal("6999.00").compareTo(saved.getAmount()),
                "★ 退款额必须取自服务端快照，不接受客户端传值");
        assertEquals(ORDER, saved.getOrderId());
        assertEquals(USER, saved.getUserId());
        assertEquals(RefundStatus.APPLIED, saved.getStatus());
        assertNotNull(saved.getAppliedAt(), "applied_at 是业务时间戳，必须手写");
        assertNotNull(saved.getRefundNo(), "退款单号不能为空（列上有 UNIQUE）");
    }

    // ================================================================
    // ③ 关系校验：类型 ↔ 订单状态（★ @Valid 表达不了的那条规则）
    // ================================================================

    @Test
    @DisplayName("未发货却申请退货退款 -> 400，且提示该选【仅退款】")
    void wrongType_notShipped() {
        givenOrder(OrderStatus.PAID, "6999.00");

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.RETURN_REFUND)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        assertTrue(e.getMessage().contains("仅退款"), "实际=" + e.getMessage());
        // ★ 判定失败就不该碰库
        verify(refundMapper, never()).insert(any(Refund.class));
    }

    @Test
    @DisplayName("已发货却申请仅退款 -> 400，且提示该选【退货退款】")
    void wrongType_alreadyShipped() {
        givenOrder(OrderStatus.SHIPPED, "6999.00");

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.REFUND_ONLY)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        assertTrue(e.getMessage().contains("退货退款"), "实际=" + e.getMessage());
        verify(refundMapper, never()).insert(any(Refund.class));
    }

    @Test
    @DisplayName("订单不在可退款状态（待支付）-> 400")
    void orderNotRefundable() {
        givenOrder(OrderStatus.PENDING_PAYMENT, "6999.00");

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.REFUND_ONLY)));
        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        assertTrue(e.getMessage().contains("不支持申请售后"), "实际=" + e.getMessage());
    }

    // ================================================================
    // ④ 归属（IDOR）+ 非法类型
    // ================================================================

    @Test
    @DisplayName("订单不存在 / 不是你的 -> 404（两种原因不可区分）")
    void orderNotFound_is404() {
        when(orderService.getRefundContext(USER, ORDER)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.REFUND_ONLY)));
        assertEquals(ResultCode.NOT_FOUND.getCode(), e.getCode());
        verify(refundMapper, never()).insert(any(Refund.class));
    }

    @Test
    @DisplayName("非法售后类型 -> 400（不依赖订单状态：先判类型再判关系）")
    void invalidType() {
        givenOrder(OrderStatus.PAID, "6999.00");

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto("REFUND_EVERYTHING")));
        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        assertTrue(e.getMessage().contains("售后类型只能是"), "实际=" + e.getMessage());
        verify(refundMapper, never()).insert(any(Refund.class));
    }

    /**
     * ★ 这条是「正向对照」：上面 6 条都在断言「不该成功」，
     *   如果实现把 throw 写成了无条件抛，6 条会全绿而功能全废。
     *   本条保证「合法输入确实能走通」，让绿灯有解释力。
     */
    @Test
    @DisplayName("★ 正向对照：已发货 + 退货退款 -> 放行")
    void returnRefundOnShippedOrder_isAccepted() {
        givenOrder(OrderStatus.SHIPPED, "6999.00");
        when(refundMapper.countActiveByOrder(ORDER)).thenReturn(0);
        doAnswer(inv -> {
            Refund r = inv.getArgument(0);
            r.setId(556L);
            return 1;
        }).when(refundMapper).insert(any(Refund.class));

        Long id = service.apply(USER, dto(RefundType.RETURN_REFUND));
        assertEquals(556L, id);

        ArgumentCaptor<Refund> cap = ArgumentCaptor.forClass(Refund.class);
        verify(refundMapper).insert(cap.capture());
        assertEquals(RefundType.RETURN_REFUND, cap.getValue().getType());
        assertEquals(RefundStatus.APPLIED, cap.getValue().getStatus());
    }

    /** ★ 断言「查进行中售后单」用的是【入参的 orderId】，不是别处来的值 */
    @Test
    @DisplayName("countActiveByOrder 收到的是入参里的 orderId")
    void checksActiveRefund_withGivenOrderId() {
        givenOrder(OrderStatus.PAID, "6999.00");
        when(refundMapper.countActiveByOrder(anyLong())).thenReturn(1);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.apply(USER, dto(RefundType.REFUND_ONLY)));
        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        verify(refundMapper).countActiveByOrder(ORDER);
        verify(refundMapper, never()).insert(any(Refund.class));
    }
}
