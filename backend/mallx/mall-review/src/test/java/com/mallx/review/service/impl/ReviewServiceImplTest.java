package com.mallx.review.service.impl;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.exception.BusinessException;
import com.mallx.order.service.OrderService;
import com.mallx.review.mapper.ReviewMapper;
import com.mallx.review.vo.AdminReviewVO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ★★ {@code ReviewServiceImpl} 管理端两方法的单测（Day 55）。
 *
 * <p><b>为什么这两块值得单测</b>：它们是「看不见的开关」——
 * <ul>
 *   <li>{@code pageAdmin} 的<b>分页夹紧</b>：漏了之后 {@code size=-1} 会退化成
 *       「不执行分页 = 查全表」（MyBatis-Plus 的语义），一次请求拖走全站评价；
 *       而它<b>不报错、不 500</b>，只有压力大时才现形。</li>
 *   <li>{@code updateStatus} 是<b>唯一能改 reviews.status 的地方</b>：
 *       置 0 会让这条评价同时从商品页列表、平均分、评价总数里消失
 *       —— 一次写入、四处生效，端到端要起全栈才能验，单测是毫秒级的第二道锁。</li>
 * </ul>
 *
 * <p>★★ <b>边界：本类不启 Spring、不连库、不发 HTTP</b>，只 mock {@link ReviewMapper}。
 * ★ 控制组（改坏实现必须红）见本日文档 §4：
 * <pre>
 *   去掉 safeSize 的 Math.min → 「size 上限」必须红
 *   updateStatus 不判 rows == 0 → 「不存在的 id」必须红
 *   把 (status != 0 &amp;&amp; status != 1) 判据删掉 → 「status=2」必须红
 * </pre>
 */
@ExtendWith(MockitoExtension.class)
class ReviewServiceImplTest {

    @Mock
    private ReviewMapper reviewMapper;

    /** 管理端两方法用不到它，但构造函数需要 —— 让 @InjectMocks 能建出对象 */
    @Mock
    private OrderService orderService;

    @InjectMocks
    private ReviewServiceImpl reviewService;

    /** 一页空结果（分页壳只关心四件套） */
    private static Page<AdminReviewVO> pageOf(long total) {
        Page<AdminReviewVO> p = new Page<>(1, 10);
        p.setRecords(List.of());
        p.setTotal(total);
        return p;
    }

    @Nested
    @DisplayName("pageAdmin · 分页夹紧（★ 夹紧必须发生在 new Page 之前）")
    class PageAdminClamp {

        @SuppressWarnings("unchecked")
        private IPage<AdminReviewVO> capturePage() {
            ArgumentCaptor<IPage<AdminReviewVO>> cap =
                    ArgumentCaptor.forClass((Class<IPage<AdminReviewVO>>) (Class<?>) IPage.class);
            verify(reviewMapper).selectAdminReviews(cap.capture(), any(), any(), any());
            return cap.getValue();
        }

        @Test
        @DisplayName("★★★★ size=9999 → 100（上限；漏了它 = 一次拖走整张表）")
        void sizeIsCappedAt100() {
            when(reviewMapper.selectAdminReviews(any(), isNull(), isNull(), isNull()))
                    .thenReturn(pageOf(0));

            reviewService.pageAdmin(1, 9999, null, null, null);

            assertEquals(100, capturePage().getSize(), "size 必须被夹到上限 100");
        }

        @Test
        @DisplayName("★★★ size=-1 → 1（★ MP 里 -1 表示「不执行分页 = 查全表」，负数被夹到【下限】）")
        void negativeSizeFallsToLowerBound() {
            when(reviewMapper.selectAdminReviews(any(), isNull(), isNull(), isNull()))
                    .thenReturn(pageOf(0));

            reviewService.pageAdmin(1, -1, null, null, null);

            assertEquals(1, capturePage().getSize(), "负数 size 必须夹到 1，而不是 100");
        }

        @Test
        @DisplayName("page=0 → 1（页码从 1 开始；不规范化会让 MP 算出不存在的页）")
        void pageZeroBecomesOne() {
            when(reviewMapper.selectAdminReviews(any(), isNull(), isNull(), isNull()))
                    .thenReturn(pageOf(0));

            reviewService.pageAdmin(0, 10, null, null, null);

            assertEquals(1, capturePage().getCurrent());
        }
    }

    @Nested
    @DisplayName("pageAdmin · 过滤与结果装配")
    class PageAdminFilters {

        @Test
        @DisplayName("★ 三个过滤原样透传（productId / rating / status=0），一个都不许丢")
        void filtersArePassedThrough() {
            when(reviewMapper.selectAdminReviews(any(), eq(7L), eq(5), eq(0))).thenReturn(pageOf(3));

            PageResult<AdminReviewVO> r = reviewService.pageAdmin(1, 10, 7L, 5, 0);

            assertEquals(3, r.getTotal());
            verify(reviewMapper).selectAdminReviews(any(), eq(7L), eq(5), eq(0));
        }

        @Test
        @DisplayName("★ 不传 status ⇒ 传 null（= 含已隐藏），不是偷偷塞 1")
        void nullStatusMeansIncludeHidden() {
            when(reviewMapper.selectAdminReviews(any(), isNull(), isNull(), isNull()))
                    .thenReturn(pageOf(0));

            reviewService.pageAdmin(1, 10, null, null, null);

            // ★ 若实现里把 null 改写成 1，管理端就再也看不见已隐藏的评价 ——
            //   这不是「默认值」，是功能反转。
            verify(reviewMapper).selectAdminReviews(any(), isNull(), isNull(), isNull());
        }
    }

    @Nested
    @DisplayName("updateStatus · 三层判据")
    class UpdateStatus {

        @Test
        @DisplayName("隐藏成功：调一次 UPDATE，参数透传（可逆操作，不删数据）")
        void hideSucceeds() {
            when(reviewMapper.updateReviewStatus(9L, 0)).thenReturn(1);

            reviewService.updateStatus(9L, 0);

            verify(reviewMapper).updateReviewStatus(9L, 0);
        }

        @Test
        @DisplayName("★★ 影响 0 行 → 404（不存在 ≠ 改成功了但没变化）")
        void notFoundThrows404() {
            when(reviewMapper.updateReviewStatus(999L, 1)).thenReturn(0);

            BusinessException ex = assertThrows(BusinessException.class,
                    () -> reviewService.updateStatus(999L, 1));

            assertEquals(404, ex.getCode(), "不存在的评价必须是 404，不能静默成功");
        }

        @Test
        @DisplayName("★★ status=2 → 400，且【不碰数据库】（DTO 之外的第二道锁）")
        void illegalStatusThrows400() {
            BusinessException ex = assertThrows(BusinessException.class,
                    () -> reviewService.updateStatus(9L, 2));

            assertEquals(400, ex.getCode());
            verify(reviewMapper, never()).updateReviewStatus(any(), any());
        }

        @Test
        @DisplayName("status=null → 400（防止「不传」被当成「隐藏」）")
        void nullStatusThrows400() {
            BusinessException ex = assertThrows(BusinessException.class,
                    () -> reviewService.updateStatus(9L, null));

            assertEquals(400, ex.getCode());
            verify(reviewMapper, never()).updateReviewStatus(any(), any());
        }
    }
}
