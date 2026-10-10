package com.mallx.marketing.service.impl;

import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.marketing.common.CouponType;
import com.mallx.marketing.common.UserCouponStatus;
import com.mallx.marketing.dto.CouponCreateDTO;
import com.mallx.marketing.entity.Coupon;
import com.mallx.marketing.mapper.UserCouponMapper;
import com.mallx.marketing.vo.CouponUseSourceVO;
import com.mallx.marketing.vo.CouponUseVO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ★★★ {@code CouponServiceImpl#calcDiscount} 的单元测试（Day 44 · L2）。
 *
 * <p>★ 为什么这一块值得单独写单测：它是<b>全项目唯一「算钱」的纯函数</b>。
 * 端到端的 M1 脚本（434 条）要起 DB + Redis + MQ + 应用才能跑到它，
 * 而它本身的对错只取决于传入的 {@link CouponUseSourceVO} ——
 * 把 Mapper 打桩就能在<b>毫秒级</b>内把分支跑遍。
 * ★ 这是 B17 那类「改两版才修好」的问题的正面解药：定位从「重跑全套」变成「跑一个方法」。
 *
 * <p>★★ <b>边界：本测试类不启 Spring、不连库、不发 HTTP</b>。
 * 只 mock 一个 {@link UserCouponMapper} —— 因为 {@code calcDiscount} 唯一
 * 的外部依赖就是 {@code selectForUse}（javadoc 明确写了：本方法不加
 * {@code @Transactional}，整个是只读的，写操作在 {@code useCoupon} 那边）。
 * ★ 这条也是 CI 能真跑 {@code mvn test} 的前提：CI 里这一步跑在起 postgres <b>之前</b>。
 *
 * <p>★★ <b>控制组要求（写新断言时必须照做）</b>：
 * 每一条断言都要能用「故意写坏实现」验证它<b>会红</b>。本类的自检记录：
 * <pre>
 *   把 setScale 的 HALF_UP 改成 HALF_EVEN   → {@@literal @}Test 舍入… 必须红（13 → 12）
 *   删掉「封顶」那三行                       → 满200减300 必须红（返回 300.00）
 *   删掉 rate 区间校验                       → rate=80 必须红（返回负抵扣额）
 *   CouponType.FIXED.equals 写成 ==          → FIXED 分支必须红（落到「类型非法」）
 * </pre>
 *
 * <p>⚠️ 素材构造集中在 {@link #src(Consumer)}：默认值是<b>一张能用的满减券</b>，
 * 每个用例只覆写它要测的那一个字段。★ 别在每个用例里手抄一整套字段 ——
 * 那样「新增一条判据」时要改十几个地方，而且容易漏改导致假绿。
 */
@ExtendWith(MockitoExtension.class)
class CouponServiceImplTest {

    @Mock
    private UserCouponMapper userCouponMapper;

    @InjectMocks
    private CouponServiceImpl service;

    private static final Long USER_ID = 1L;
    private static final Long UC_ID = 100L;

    // ================================================================
    // ① 「取素材」这一层的两种结果
    // ================================================================

    @Test
    @DisplayName("取不到素材 → 404「优惠券不存在」（IDOR 伪装 404，不区分不存在/不是你的）")
    void calcDiscount_whenSourceIsNull_throws404() {
        when(userCouponMapper.selectForUse(USER_ID, UC_ID)).thenReturn(null);

        BusinessException ex = assertThrows(BusinessException.class,
                () -> service.calcDiscount(USER_ID, UC_ID, money("100.00")));

        assertEquals(ResultCode.NOT_FOUND.getCode(), ex.getCode());
        assertTrue(ex.getMessage().contains("优惠券不存在"), ex.getMessage());
    }

    @Test
    @DisplayName("★ 归属由 SQL 保证：本方法把 userId 原样传给 selectForUse，绝不接收请求参数")
    void calcDiscount_passesUserIdFromPrincipal_notFromRequest() {
        when(userCouponMapper.selectForUse(77L, UC_ID)).thenReturn(src(s -> { }));

        service.calcDiscount(77L, UC_ID, money("100.00"));

        // ★ 桩只对 (77, 100) 生效：若实现把 userId 换成别处来的值，这里会因取不到素材而抛 404
        verify(userCouponMapper).selectForUse(77L, UC_ID);
    }

    // ================================================================
    // ② 五条判据（顺序不能换 —— 先判最根本的原因，消息才说得清）
    // ================================================================

    @Nested
    @DisplayName("五条判据：任一不满足 → 400 + 人话")
    class Guards {

        @Test
        @DisplayName("判据1 status=USED → 「已使用」")
        void usedStatus() {
            assertRejected(s -> s.setStatus(UserCouponStatus.USED), "已使用");
        }

        @Test
        @DisplayName("判据2 expired=TRUE → 「已过期」")
        void expired() {
            assertRejected(s -> s.setExpired(Boolean.TRUE), "已过期");
        }

        @Test
        @DisplayName("判据2 的对照组：expired=FALSE 不拦（★ Boolean 包装类型，别写成自动拆箱）")
        void notExpiredIsAccepted() {
            CouponUseVO vo = assertAccepted(s -> {
                s.setExpired(Boolean.FALSE);
                s.setEndTime(LocalDateTime.now().plusDays(1));
            }, money("100.00"));
            assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("判据3 startTime 在未来 → 「尚未开始」")
        void notStarted() {
            assertRejected(s -> s.setStartTime(LocalDateTime.now().plusDays(1)), "尚未开始");
        }

        @Test
        @DisplayName("判据3 的对照组：startTime 为 null = 无起始限制（★ 不能 NPE）")
        void nullStartTimeIsAccepted() {
            CouponUseVO vo = assertAccepted(s -> s.setStartTime(null), money("100.00"));
            assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("判据4 couponStatus=0 → 「已下架」（这是 coupons.status，不是 uc.status）")
        void couponOffShelf() {
            assertRejected(s -> s.setCouponStatus(0), "已下架");
        }

        @Test
        @DisplayName("判据4 的对照组：couponStatus 为 null 也拦（券面取不到 = 不敢放行）")
        void nullCouponStatusIsRejected() {
            assertRejected(s -> s.setCouponStatus(null), "已下架");
        }

        @Test
        @DisplayName("判据5 金额低于门槛 → 400 且消息里带上门槛值")
        void belowMinAmount() {
            when(userCouponMapper.selectForUse(USER_ID, UC_ID))
                    .thenReturn(src(s -> s.setMinAmount(money("100.00"))));

            BusinessException ex = assertThrows(BusinessException.class,
                    () -> service.calcDiscount(USER_ID, UC_ID, money("99.99")));

            assertEquals(ResultCode.VALIDATE_FAILED.getCode(), ex.getCode());
            assertTrue(ex.getMessage().contains("100.00"), "消息里必须给出门槛值，实际：" + ex.getMessage());
        }

        @Test
        @DisplayName("判据5 的对照组：金额【恰好等于】门槛 → 放行（>= 不是 >）")
        void equalToMinAmountIsAccepted() {
            CouponUseVO vo = assertAccepted(s -> s.setMinAmount(money("100.00")), money("100.00"));
            assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("minAmount 为 null = 无门槛 → 放行")
        void nullMinAmountIsAccepted() {
            // ★ 订单金额必须 ≥ 面额：否则会被「封顶」那条收口压成 1.00，
            //   本用例要测的是「无门槛时不拦」，不是封顶（封顶有单独一条）
            CouponUseVO vo = assertAccepted(s -> s.setMinAmount(null), money("100.00"));
            assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
        }
    }

    // ================================================================
    // ③ 按类型算钱：两条公式 + 两个「券配错了」的兜底
    // ================================================================

    @Nested
    @DisplayName("算钱：FIXED / DISCOUNT 两条公式，出口同一个 BigDecimal")
    class Formulas {

        @Test
        @DisplayName("FIXED：抵扣额 = 券面面额（与订单金额无关）")
        void fixedEqualsFaceValue() {
            CouponUseVO vo = assertAccepted(s -> {
                s.setType(CouponType.FIXED);
                s.setDiscountAmount(money("20.00"));
            }, money("100.00"));

            assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
            assertEquals(2, vo.getDeductionAmount().scale(), "必须定标到 2 位");
        }

        @Test
        @DisplayName("FIXED 但面额缺失 → 400「面额缺失」（★ 不是 NPE/500：券配错 ≠ 服务崩了）")
        void fixedWithoutFaceValue() {
            assertRejected(s -> {
                s.setType(CouponType.FIXED);
                s.setDiscountAmount(null);
            }, "面额缺失");
        }

        @Test
        @DisplayName("DISCOUNT：rate=0.80（应付比例）→ 100 元订单抵扣 20.00")
        void discountRateIsPayableRatio() {
            CouponUseVO vo = assertAccepted(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(money("0.80"));
                s.setDiscountAmount(null);
            }, money("100.00"));

            // ★★ 这是全项目最容易读反的一条约定：0.80 = 打 8 折 = 付 80% = 减 20%
            assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("★★ DISCOUNT rate=80（种子里那颗雷）→ 400，绝不许算出负抵扣额")
        void discountRateOutOfRangeIsRejected() {
            assertRejected(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(money("80"));
            }, "折扣率取值必须是 0 到 1 之间");
        }

        @Test
        @DisplayName("DISCOUNT rate=0 → 400（区间是 (0,1]，不含 0）")
        void discountRateZeroIsRejected() {
            assertRejected(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(BigDecimal.ZERO);
            }, "折扣率取值必须是 0 到 1 之间");
        }

        @Test
        @DisplayName("DISCOUNT rate=null → 400（★ 不是 NPE）")
        void discountRateNullIsRejected() {
            assertRejected(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(null);
            }, "折扣率取值必须是 0 到 1 之间");
        }

        @Test
        @DisplayName("DISCOUNT rate=1.00（不打折）→ 抵扣 0.00，★ 照常返回不抛异常")
        void discountRateOneGivesZeroAndIsReturned() {
            CouponUseVO vo = assertAccepted(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(BigDecimal.ONE);
            }, money("100.00"));

            assertEquals(0, money("0.00").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("类型既非 FIXED 也非 DISCOUNT → 400「类型非法」")
        void illegalType() {
            assertRejected(s -> s.setType("GIFT"), "类型非法");
        }

        @Test
        @DisplayName("★ 券面原件不被写回：算完抵扣后素材仍是原值")
        void sourceIsNeverMutated() {
            CouponUseSourceVO material = src(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(money("0.80"));
                s.setDiscountAmount(null);
            });
            when(userCouponMapper.selectForUse(USER_ID, UC_ID)).thenReturn(material);

            service.calcDiscount(USER_ID, UC_ID, money("100.00"));

            // ★ 抵扣额 20.00 若被写回 discount_amount，素材就变成「减 20」的满减券了
            assertEquals(0, money("0.80").compareTo(material.getDiscountRate()));
            assertNull(material.getDiscountAmount());
        }
    }

    // ================================================================
    // ④ 收口：封顶 + 舍入
    // ================================================================

    @Nested
    @DisplayName("收口：抵扣额封顶 + HALF_UP 定标")
    class Rounding {

        @Test
        @DisplayName("★ 满 200 减 300 → 抵扣【封顶】为 200.00（运营配错了券，但不该让用户下单失败）")
        void deductionIsCappedAtTotalAmount() {
            CouponUseVO vo = assertAccepted(s -> {
                s.setType(CouponType.FIXED);
                s.setDiscountAmount(money("300.00"));
            }, money("200.00"));

            assertEquals(0, money("200.00").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("★ x.xx5 边界必须 HALF_UP：1.125 → 1.13（默认 HALF_EVEN 会给 1.12）")
        void roundingIsHalfUpNotHalfEven() {
            // 100.00 × (1 - 0.98875) = 1.1250 —— 正好落在「半个最小单位」上，
            // 这一条是 HALF_UP 与 HALF_EVEN 唯一会给出不同答案的地方
            CouponUseVO vo = assertAccepted(s -> {
                s.setType(CouponType.DISCOUNT);
                s.setDiscountRate(money("0.98875"));
            }, money("100.00"));

            assertEquals(0, money("1.13").compareTo(vo.getDeductionAmount()));
        }

        @Test
        @DisplayName("0 元券 → 抵扣 0.00 照常返回（orders.discount_amount=0 正是「用了 0 元券」的证据）")
        void zeroDeductionIsReturnedNotRejected() {
            CouponUseVO vo = assertAccepted(s -> {
                s.setType(CouponType.FIXED);
                s.setDiscountAmount(BigDecimal.ZERO);
            }, money("100.00"));

            assertEquals(0, money("0.00").compareTo(vo.getDeductionAmount()));
        }
    }

    // ================================================================
    // ⑤ 出参装填
    // ================================================================

    @Test
    @DisplayName("出参把 userCouponId / couponId / couponName 原样带回（下游拿 userCouponId 去核销）")
    void resultCarriesIdentifyingFields() {
        when(userCouponMapper.selectForUse(USER_ID, UC_ID)).thenReturn(src(s -> { }));

        CouponUseVO vo = service.calcDiscount(USER_ID, UC_ID, money("100.00"));

        assertEquals(UC_ID, vo.getUserCouponId());
        assertEquals(Long.valueOf(10L), vo.getCouponId());
        assertEquals("满100减20", vo.getCouponName());
        assertEquals(0, money("20.00").compareTo(vo.getDeductionAmount()));
    }

    // ================================================================
    // ⑥ 建券：两条「字段之间」的关系校验（@Valid 表达不了，只能在 Service 守）
    // ================================================================

    @Nested
    @DisplayName("createCoupon：类型 ↔ 金额字段必须配对，且时间窗不能反过来")
    class CreateCoupon {

        @Test
        @DisplayName("endTime 不晚于 startTime → 400（反过来的时间窗会让券永远领不到，且不报错）")
        void endTimeNotAfterStartTime() {
            assertCreateRejected(d -> d.setEndTime(d.getStartTime()), "结束时间必须晚于开始时间");
        }

        @Test
        @DisplayName("FIXED 缺 discountAmount → 400")
        void fixedWithoutAmount() {
            assertCreateRejected(d -> {
                d.setType(CouponType.FIXED);
                d.setDiscountAmount(null);
            }, "满减券（FIXED）必须填写 discountAmount");
        }

        @Test
        @DisplayName("★ FIXED 同时填 discountRate → 400（一张券又是「减20」又是「打8折」= 歧义）")
        void fixedWithBothFields() {
            assertCreateRejected(d -> {
                d.setType(CouponType.FIXED);
                d.setDiscountAmount(money("20.00"));
                d.setDiscountRate(money("0.80"));
            }, "满减券（FIXED）不能同时填写 discountRate");
        }

        @Test
        @DisplayName("DISCOUNT 缺 discountRate → 400")
        void discountWithoutRate() {
            assertCreateRejected(d -> {
                d.setType(CouponType.DISCOUNT);
                d.setDiscountRate(null);
            }, "折扣券（DISCOUNT）必须填写 discountRate");
        }

        @Test
        @DisplayName("DISCOUNT 同时填 discountAmount → 400")
        void discountWithBothFields() {
            assertCreateRejected(d -> {
                d.setType(CouponType.DISCOUNT);
                d.setDiscountRate(money("0.80"));
                d.setDiscountAmount(money("20.00"));
            }, "折扣券（DISCOUNT）不能同时填写 discountAmount");
        }

        @Test
        @DisplayName("类型非法 → 400（DTO 的 @Pattern 之外，这里是「绕过参数层」的兜底）")
        void illegalType() {
            assertCreateRejected(d -> d.setType("GIFT"), "券类型只能是 FIXED 或 DISCOUNT");
        }

        @Test
        @DisplayName("★ 放行路径：status=1 / receivedCount=0 必须显式写，不能留给 DB 默认值")
        void createPersistsExplicitInitialState() {
            CouponCreateDTO dto = dto(d -> { });
            CouponServiceImpl spy = spy(service);
            // ★ 用 Answer 模拟「MP save 之后自增主键回填到实体」—— 这正是实现里取 id 的依据
            doAnswer(inv -> {
                inv.<Coupon>getArgument(0).setId(99L);
                return true;
            }).when(spy).save(any(Coupon.class));

            Long id = spy.createCoupon(dto);

            assertEquals(Long.valueOf(99L), id);
            ArgumentCaptor<Coupon> cap = ArgumentCaptor.forClass(Coupon.class);
            verify(spy).save(cap.capture());
            assertEquals(Integer.valueOf(1), cap.getValue().getStatus(), "status 必须显式写 1（可领）");
            assertEquals(Integer.valueOf(0), cap.getValue().getReceivedCount(), "receivedCount 必须显式写 0，别留 null");
            assertEquals("满100减20", cap.getValue().getName());
        }
    }

    // ================================================================
    // 工具
    // ================================================================

    /** 「被拒绝」的通用断言：400 + 消息包含关键字。★ 每条判据都该用它，别各写一份 */
    private void assertRejected(Consumer<CouponUseSourceVO> tweak, String expectedKeyword) {
        when(userCouponMapper.selectForUse(USER_ID, UC_ID)).thenReturn(src(tweak));

        BusinessException ex = assertThrows(BusinessException.class,
                () -> service.calcDiscount(USER_ID, UC_ID, money("100.00")));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), ex.getCode());
        assertTrue(ex.getMessage().contains(expectedKeyword),
                "消息应包含「" + expectedKeyword + "」，实际：" + ex.getMessage());
    }

    /** 建券被拒的通用断言：400 + 消息包含关键字 */
    private void assertCreateRejected(Consumer<CouponCreateDTO> tweak, String expectedKeyword) {
        CouponCreateDTO dto = dto(tweak);

        BusinessException ex = assertThrows(BusinessException.class, () -> service.createCoupon(dto));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), ex.getCode());
        assertTrue(ex.getMessage().contains(expectedKeyword),
                "消息应包含「" + expectedKeyword + "」，实际：" + ex.getMessage());
    }

    /** 一张【合法的满减券】请求体；用例只覆写自己关心的字段 */
    private static CouponCreateDTO dto(Consumer<CouponCreateDTO> tweak) {
        CouponCreateDTO d = new CouponCreateDTO();
        d.setName("满100减20");
        d.setType(CouponType.FIXED);
        d.setDiscountAmount(money("20.00"));
        d.setDiscountRate(null);
        d.setMinAmount(null);
        d.setTotalCount(100);
        d.setStartTime(LocalDateTime.now().minusDays(1));
        d.setEndTime(LocalDateTime.now().plusDays(1));
        tweak.accept(d);
        return d;
    }

    /** 「被放行」的通用断言：不抛异常，返回非 null 的 VO */
    private CouponUseVO assertAccepted(Consumer<CouponUseSourceVO> tweak, BigDecimal totalAmount) {
        when(userCouponMapper.selectForUse(USER_ID, UC_ID)).thenReturn(src(tweak));

        CouponUseVO vo = service.calcDiscount(USER_ID, UC_ID, totalAmount);

        assertTrue(vo != null && vo.getDeductionAmount() != null, "放行路径必须返回带抵扣额的 VO");
        return vo;
    }

    /** 一张【能用的满减券】；用例只覆写自己关心的字段 */
    private static CouponUseSourceVO src(Consumer<CouponUseSourceVO> tweak) {
        CouponUseSourceVO s = new CouponUseSourceVO();
        s.setUserCouponId(UC_ID);
        s.setCouponId(10L);
        s.setCouponName("满100减20");
        s.setType(CouponType.FIXED);
        s.setDiscountAmount(money("20.00"));
        s.setDiscountRate(null);
        s.setMinAmount(null);
        s.setStatus(UserCouponStatus.UNUSED);
        s.setCouponStatus(1);
        s.setStartTime(LocalDateTime.now().minusDays(1));
        s.setEndTime(LocalDateTime.now().plusDays(1));
        s.setExpired(Boolean.FALSE);
        tweak.accept(s);
        return s;
    }

    private static BigDecimal money(String v) {
        return new BigDecimal(v);
    }
}
