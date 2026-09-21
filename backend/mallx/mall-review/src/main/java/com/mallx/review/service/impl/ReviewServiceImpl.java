package com.mallx.review.service.impl;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.order.api.OrderItemBuyContext;
import com.mallx.order.common.OrderStatus;
import com.mallx.order.service.OrderService;
import com.mallx.review.dto.ReviewCreateDTO;
import com.mallx.review.entity.Review;
import com.mallx.review.mapper.ReviewMapper;
import com.mallx.review.service.ReviewService;
import com.mallx.review.vo.ReviewPageVO;
import com.mallx.review.vo.ReviewVO;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.springframework.stereotype.Service;

/**
 * ★★★ 商品评价服务实现 —— <b>骨架</b>，三个方法体与 {@code ReviewMapper.xml} 的 SQL 由你写。
 *
 * <p>★ 类注释里已把该用的 import 一并备好（{@code OrderItemBuyContext} / {@code OrderStatus} /
 * {@code Review}），写方法体时直接用；若某个没用上，IDE 会灰显提示，删掉即可。
 *
 * <p>⚠️ 三个方法的返回类型不同，注意别混：
 * <pre>
 *   create         → ReviewVO        （单条）
 *   pageByProduct  → ReviewPageVO    （分页 + 聚合，★ 本模块自己的壳）
 *   pageMine       → PageResult&lt;ReviewVO&gt;（分页，复用公共壳）
 * </pre>
 */
@Service
public class ReviewServiceImpl implements ReviewService {

    /**
     * 分页上限：单页最多 100 条 —— 与 {@code OrderServiceImpl.MAX_PAGE_SIZE} /
     * {@code PaymentServiceImpl.MAX_PAGE_SIZE} 同一个值、同一套夹紧规则。
     *
     * <p>★ 不抽到 {@code mall-common} 做成公共常量：那是一次跨模块重构，
     * 与本步无关。三处各留一份、注释互相指明，等真有需要时再抽。
     */
    private static final long MAX_PAGE_SIZE = 100;

    private final ReviewMapper reviewMapper;      // 本模块
    private final OrderService orderService;      // mall-order 的只读门面（getBuyContext）

    public ReviewServiceImpl(ReviewMapper reviewMapper, OrderService orderService) {
        this.reviewMapper = reviewMapper;
        this.orderService = orderService;
    }

    /**
     * ★★★ 发表评价 —— 四步顺序不能换（详见接口上的 Javadoc）：
     * <pre>
     *   ① orderService.getBuyContext(userId, dto.getOrderItemId())
     *  ② null → BusinessException(404, "订单明细不存在")
     *  ③ !OrderStatus.COMPLETED.equals(ctx.getOrderStatus())
     *        → BusinessException(400, "只有已完成的订单才能评价")
     *  ④ 组装 Review 实体（user_id 取参数 userId；order_id / product_id 取 ctx；
     *        rating / content 取 dto；★ 注意 insertReview 的 SQL 里 status 写死 1，
     *        但实体该有的字段都要 set 上，回查与日志都用得着）
     *        → reviewMapper.insertReview(review)
     *        → rows == 0 → BusinessException(400, "该商品已评价过")
     *        → 回查 reviewMapper.selectByOrderItemId(ctx.getOrderItemId()) 并返回
     * </pre>
     *
     * <p>⚠️ 两条 404 消息必须是<b>同一句</b>（「明细不存在」与「不是你的」不可区分）；
     * ⚠️ 报错用 {@code ResultCode.NOT_FOUND} / {@code ResultCode.VALIDATE_FAILED}，
     * 别自己写数字 —— HTTP 一律是 200，业务码在 body 里。
     * ⚠️ <b>不要加 {@code @Transactional}</b>：单条 INSERT + ON CONFLICT 自身即原子。
     * ⚠️ 因为 {@code ON CONFLICT} 存在，这里<b>不需要</b> try/catch DuplicateKeyException。
     */
    @Override
    public ReviewVO create(Long userId, ReviewCreateDTO dto) {
        OrderItemBuyContext ctx = orderService.getBuyContext(userId, dto.getOrderItemId());
        if (ctx == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "订单明细不存在");
        }
        if (!OrderStatus.COMPLETED.equals(ctx.getOrderStatus())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "只有已完成的订单才能评价");
        }
        Review review = new Review();
        review.setUserId(userId);
        review.setOrderItemId(ctx.getOrderItemId());
        review.setOrderId(ctx.getOrderId());
        review.setProductId(ctx.getProductId());
        review.setRating(dto.getRating());
        review.setContent(dto.getContent());
        review.setStatus(1);
        int rows = reviewMapper.insertReview(review);
        if (rows == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该商品已评价过");
        }
        return reviewMapper.selectByOrderItemId(ctx.getOrderItemId());
    }

    /**
     * ★★ 商品评价列表（公开，游客可看）。步骤：
     * <pre>
     *   ① 夹紧分页（★ 必须在 new Page 之前，与另外两个模块同款）：
     *        long safePage = Math.max(page, 1);
     *        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
     *      ⚠️ size 那一行是救命的：size = -1 在 MP 里表示「不执行分页 = 查全表」，
     *         size = 0 会返回空列表但 total 正常（用户以为没数据，比报错更难发现）；
     *         size = 999 不被截断就会一次拖走整张表。page 那行只是防御性规范化。
     *   ② IPage&lt;ReviewVO&gt; result =
     *        reviewMapper.selectProductReviews(new Page<>(safePage, safeSize), productId);
     *      ★ 首参必须传 IPage，否则插件不改写 SQL（不报错，静默查全表）
     *   ③ 聚合：reviewMapper.selectProductAvgRating(productId) / selectProductReviewCount(productId)
     *   ④ 组装 ReviewPageVO：records / total / current / size 从 result 取，
     *      avgRating / reviewCount 从 ③ 取，然后 Result.ok(...) 由 Controller 负责
     * </pre>
     * ★ 本方法<b>不能</b>有 Authentication 参数（匿名访问，见接口 Javadoc）。
     * ★ 需要 import: com.baomidou.mybatisplus.core.metadata.IPage、
     *   com.baomidou.mybatisplus.extension.plugins.pagination.Page
     */
    @Override
    public ReviewPageVO pageByProduct(Long productId, long page, long size) {
        // ① 夹紧分页 —— ★ 必须在 new Page 之前，构造进去的值就是最终发给 DB 的值
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        // ② 首参必须传 IPage，否则分页插件不改写 SQL（不报错，静默查全表）
        IPage<ReviewVO> result =
                reviewMapper.selectProductReviews(new Page<>(safePage, safeSize), productId);

        // ③④ 组装：分页四件套取自 result，两个聚合取自评价域的独立查询
        ReviewPageVO vo = new ReviewPageVO();
        vo.setRecords(result.getRecords());
        vo.setTotal(result.getTotal());
        vo.setCurrent(result.getCurrent());
        vo.setSize(result.getSize());
        vo.setAvgRating(reviewMapper.selectProductAvgRating(productId));
        vo.setReviewCount(reviewMapper.selectProductReviewCount(productId));
        return vo;
    }

    /**
     * ★ 我的评价列表（需登录）。步骤与 pageByProduct 类似，差别有三：
     * <pre>
     *   ① 夹紧规则完全相同
     *   ② reviewMapper.selectMyReviews(new Page<>(safePage, safeSize), userId)
     *   ③ ★ 没有聚合，直接 PageResult.of(result) 返回
     * </pre>
     */
    @Override
    public PageResult<ReviewVO> pageMine(Long userId, long page, long size) {
        // ① 夹紧规则与 pageByProduct 完全相同
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        // ② 归属条件在 SQL 里写死；这里只是把当前用户传下去
        IPage<ReviewVO> result =
                reviewMapper.selectMyReviews(new Page<>(safePage, safeSize), userId);

        // ③ 没有聚合，字段集正好是分页四件套 —— 直接复用公共壳
        return PageResult.of(result);
    }
}
