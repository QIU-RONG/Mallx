package com.mallx.marketing.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.marketing.entity.UserCoupon;
import com.mallx.marketing.vo.UserCouponVO;
import org.apache.ibatis.annotations.Param;

/**
 * 用户优惠券 Mapper（领取记录）。
 *
 * <p>★ 两条手写 SQL，各有各的「为什么不能交给 MP」：
 * <ul>
 *   <li>{@link #insertIgnore} —— 需要 {@code ON CONFLICT ... DO NOTHING}，wrapper 表达不了；</li>
 *   <li>{@link #selectMyCoupons} —— 要 JOIN {@code coupons} 取券面信息、
 *       还要现算 {@code expired} → 是跨表 + 计算列，不是单表查询。</li>
 * </ul>
 */
public interface UserCouponMapper extends BaseMapper<UserCoupon> {

    /**
     * ★★ <b>领券的第二步：写领取记录</b>。与 Day 16 评价的 {@code insertReview} <b>逐字同构</b>。
     *
     * <p>要写：{@code user_id} / {@code coupon_id} / {@code status='UNUSED'} / {@code received_at}。
     *
     * <p>★★ <b>结尾必须是 {@code ON CONFLICT (user_id, coupon_id) DO NOTHING}</b>：
     * <pre>
     *   返回值  1 = 插进去了（这次真领到）
     *          0 = 已经领过（并发或重复点击都会走到这里）
     * </pre>
     * 这一条把「并发重复领取」压成<b>一次原子操作</b>，不需要先 SELECT 去查
     * （「先查再插」在并发下会双写 = TOCTOU）。
     * <b>返回的影响行数就是 CAS 的结果</b>，与 {@code UPDATE ... WHERE status = ?} 完全同构。
     *
     * <p>⚠️⚠️ 它<b>硬依赖</b> {@code uk_user_coupons_user_coupon} 这个唯一约束：
     * <pre>
     *   约束没建 → 直接报 "there is no unique or exclusion constraint matching
     *              the ON CONFLICT specification"     ← 不是静默降级
     * </pre>
     * 该约束由 {@code backend/sql/09-user-coupons-unique.sql} 补上（01-schema.sql 里<b>没有</b>）。
     *
     * <p>⚠️ <b>{@code received_at} 必须在 SQL 里手写 {@code CURRENT_TIMESTAMP}</b> ——
     * 自定义 XML 的 INSERT <b>不走</b> {@code MyMetaObjectHandler}。
     * 虽然该列有 DB 默认值、不写也能落库，但显式写出来才不依赖「默认值还在不在」
     * （本项目 Day 13/16 都是在这上面栽过的）。
     *
     * <p>⚠️ {@code status} 写死字面量 {@code 'UNUSED'}，不用参数 —— 领到的券只有这一种状态。
     *
     * @return 影响行数：1 = 领到；0 = 已领过
     */
    int insertIgnore(@Param("userId") Long userId, @Param("couponId") Long couponId);

    /**
     * 我的券列表（需登录，分页）。
     *
     * <p>要做的：{@code user_coupons uc JOIN coupons c ON c.id = uc.coupon_id}，
     * 取券面信息填充 {@link UserCouponVO}，并<b>现算</b>两个东西：
     * <pre>
     *   expired = (c.end_time &lt; CURRENT_TIMESTAMP)     ← 惰性过期，不落库
     * </pre>
     * ★ 用 {@code LEFT JOIN} 还是 {@code INNER JOIN}？—— 想清楚再选：
     * {@code user_coupons.coupon_id} 有外键指向 {@code coupons}，理论上必有父行；
     * 但 {@code coupons} 是<b>物理删</b>的表（没有 {@code is_deleted}，删券是真删），
     * 若某天有人绕过守卫删了券，INNER JOIN 会让这条领取记录<b>凭空消失</b>——
     * 用户「我的券」里少一张，且没有任何提示。选哪个，把理由写进注释。
     *
     * <p>★ 归属条件 {@code WHERE uc.user_id = #{userId}} 写死在 SQL 里 ——
     * <b>这是 C 端隔离的唯一防线</b>（管理端才是「不过滤 + 权限码」那套，别搞混）。
     *
     * <p>★ 排序 {@code ORDER BY uc.id DESC}；★ 别名的下划线规矩同 {@link CouponMapper}。
     * <p>★ 分页不写 LIMIT，首参 {@code IPage}。
     *
     * @param page   分页参数（首参必须是 IPage）
     * @param userId 来自 token 的 principal，<b>不是</b>请求参数
     */
    IPage<UserCouponVO> selectMyCoupons(IPage<UserCouponVO> page, @Param("userId") Long userId);
}
