package com.mallx.review.service;

import com.mallx.common.api.PageResult;
import com.mallx.review.dto.ReviewCreateDTO;
import com.mallx.review.vo.AdminReviewVO;
import com.mallx.review.vo.ReviewPageVO;
import com.mallx.review.vo.ReviewVO;

/**
 * 商品评价服务（Day 16）
 *
 * <p>★ 本模块依赖 {@code mall-common} + {@code mall-order} —— <b>刻意不依赖</b>
 * {@code mall-product}（{@code order_items} 已快照商品名 / 规格名 / 图片）。
 */
public interface ReviewService {

    /**
     * ★★★ 发表评价 —— 本日的核心方法。
     *
     * <p>★★ <b>三重派生</b>：调用方只有一件事说了算 —— {@code orderItemId}。
     * <pre>
     *   userId    ← token 的 principal（参数传进来）
     *   orderId   ← 由 orderItemId 反查 order_items
     *   productId ← 由 orderItemId 反查 order_items
     * </pre>
     * ★★ 为什么 {@code productId} 绝不能由客户端提供：{@code reviews} 对 {@code products}
     * 只有外键（「商品得存在」），<b>没有</b>「你得买过」的约束。客户端能指定
     * {@code product_id} 的话，攻击者拿自己一张合法订单就能给<b>任意商品</b>刷五星。
     *
     * <p>★★ <b>四步顺序不能换</b>（防御性检查由外向内，越靠外的越先跑）：
     * <pre>
     *   ① orderService.getBuyContext(userId, orderItemId)
     *        返回 null → 404「订单明细不存在」（★「不存在」与「不是你的」共用同一句，
     *        两种响应必须逐字节相同，否则可以枚举出「哪些明细真实存在」）
     *   ② 订单状态不是 COMPLETED → 400「只有已完成的订单才能评价」
     *        （PENDING_PAYMENT / PAID / SHIPPED 三种都不行）
     *   ③ reviewMapper.insertReview(...)   ← INSERT ... ON CONFLICT DO NOTHING
     *        影响行数 == 0 → 400「该商品已评价过」
     *   ④ 回查并返回 ReviewVO
     * </pre>
     *
     * <p>★ <b>不加 {@code @Transactional}</b>：单条 INSERT 自身即原子，
     * {@code ON CONFLICT} 已经把并发安全压进一条语句。第 ④ 步的回查单独走一次 SELECT
     * 也没关系 —— 刚插入的行拿得到就拿，拿不到也不影响正确性。
     *
     * <p>★ 与 {@code OrderServiceImpl.confirm} 是同一个结构：
     * 先归属分流（404）→ 再 CAS 抢资格（0 行 400）。
     *
     * @param userId 当前登录用户（来自 token，不接受客户端传参）
     * @throws com.mallx.common.exception.BusinessException code=404 订单明细不存在（含「不是你的」）
     * @throws com.mallx.common.exception.BusinessException code=400 订单未完成 / 该商品已评价过
     */
    ReviewVO create(Long userId, ReviewCreateDTO dto);

    /**
     * ★★ 商品维度的评价列表（分页 + 聚合）—— <b>公开，游客可看</b>。
     *
     * <p>★ 方法上<b>没有</b> {@code Authentication} 参数，也不挂 {@code @PreAuthorize}：
     * 这个接口必须允许匿名。能做到这一点是因为路径挂在 {@code /api/products/**} 下
     * —— {@code SecurityConfig} 的 {@code GET} 白名单天然覆盖（见规划 §4.1）。
     *
     * <p>★ 分页参数由本方法<b>夹紧</b>（与 {@code OrderServiceImpl} / {@code PaymentServiceImpl}
     * 完全同一套规则），夹紧必须写在 {@code new Page<>(...)} <b>之前</b>。
     *
     * @param productId 商品 id（不校验存在性：查不到就是空列表 + 0 分，与商品详情接口口径一致）
     * @param page      页码，从 1 开始
     * @param size      每页条数，最终落在 1..100
     */
    ReviewPageVO pageByProduct(Long productId, long page, long size);

    /**
     * ★ 我的评价列表（分页）—— <b>需登录</b>。
     *
     * <p>★ 归属条件 {@code WHERE user_id = #{userId}} 写在 XML 里，不接受客户端「查谁」参数。
     * ★ 没有聚合需求，所以<b>复用 {@code PageResult}</b>（对比 {@link #pageByProduct}）。
     *
     * @param userId 当前登录用户（来自 token）
     * @param page   页码，从 1 开始
     * @param size   每页条数，最终落在 1..100
     */
    PageResult<ReviewVO> pageMine(Long userId, long page, long size);

    /**
     * ★ 管理端评价列表（分页，<b>含已隐藏</b>）—— Day 55。
     *
     * <p>★★ 与 {@link #pageByProduct} 的口径差异是本方法存在的全部理由：
     * <pre>
     *   C 端    ：WHERE ... AND status = 1   （只看得到正常评价）
     *   管理端  ：status 不传 = 两者都要      （要能看见自己藏了什么、要能恢复）
     * </pre>
     * ⇒ <b>同一张表、同一个概念，两端口径必须同源且各自显式</b>；
     * 把管理端写成「C 端的复用 + 前端过滤」会让「隐藏」变成不可恢复的失明。
     *
     * <p>★ 三种过滤都可选（null = 不过滤），全部为空时就是「全站评价」。
     * 分页夹紧规则与 {@link #pageByProduct} 完全一致（★ 必须写在 {@code new Page<>} 之前）。
     *
     * @param productId 可选：只看某件商品的评价
     * @param rating    可选：按评分过滤（1..5）
     * @param status    可选：1=显示 0=已隐藏；null = 两者都要
     */
    PageResult<AdminReviewVO> pageAdmin(long page, long size, Long productId, Integer rating, Integer status);

    /**
     * ★ 显示 / 隐藏一条评价 —— Day 55。
     *
     * <p>★ 只改 {@code reviews.status}，<b>不删数据、不改内容</b>：
     * 平台可以「不展示」，但不该替用户改写他说过的话。
     *
     * <p>★★ 一次写入、四处生效（这是它值得单测而不是只做端到端的原因）：
     * C 端评价列表、平均分、评价总数、以及「我的评价」之外的所有公开读路径
     * 都带 {@code status = 1} ⇒ 置 0 后立刻从商品页消失、也不再计入聚合。
     * <b>没有第二个真相要同步</b>。
     *
     * @param status 1 = 显示，0 = 隐藏；越界取值 → 400（DTO 已经拦一次，这里是防绕过接口的兜底）
     * @throws com.mallx.common.exception.BusinessException code=404 评价不存在；code=400 status 非法
     */
    void updateStatus(Long id, Integer status);
}
