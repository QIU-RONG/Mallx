package com.mallx.marketing.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.marketing.entity.UserCoupon;
import com.mallx.marketing.vo.CouponUseSourceVO;
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
     * 取券面信息填充 {@link UserCouponVO}，并<b>现算一个东西</b>（全 VO 里唯一不在表里的列）：
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

    // ================================================================
    // ★★★ Day 21（阶段二）：算抵扣 / 核销 / 退券 —— 三条，全部手写 SQL
    //     前两条的难点在「并发下不能算错」，第三条的难点在「擦干净」。
    // ================================================================

    /**
     * ★★ <b>算抵扣前的「取素材」</b>：把【判据】与【面额】一次取回来。
     *
     * <p>要写：{@code user_coupons uc JOIN coupons c ON c.id = uc.coupon_id}，
     * 出参 {@link CouponUseSourceVO}。★ 别名一律下划线。
     *
     * <p>需要哪些列（对应 {@link CouponUseSourceVO} 的字段，一个都不能少）：
     * <pre>
     *   uc.id        AS user_coupon_id        uc.coupon_id AS coupon_id
     *   c.name       AS coupon_name           c.type
     *   c.discount_amount   c.discount_rate   c.min_amount
     *   uc.status    AS status        ← user_coupons.status（「我用了没」）
     *   c.status     AS coupon_status ← coupons.status（「这个券种下架没」）
     *   c.start_time   c.end_time
     *   (c.end_time &lt; CURRENT_TIMESTAMP) AS expired   ← 与 selectMyCoupons 同口径
     * </pre>
     *
     * <p>★★ <b>最容易写错的一处：两个 {@code status} 必须分别起别名。</b>
     * 若两条都不别名、或者都写成 {@code status}，PG 会让后一列盖掉前一列，而且
     * <b>不报错</b> —— {@code status} 字段会悄悄变成「券种的上下架标记」，
     * 于是「已核销的券」被判成「可用」，同一张券能被核销两次。
     * ★ 这类错不会 500、不会抛异常，只会让钱悄悄错掉。
     *
     * <p>★★ <b>归属条件写死在这里</b>：
     * <pre>
     *   WHERE uc.user_id = #{userId} AND uc.id = #{userCouponId}
     * </pre>
     * 这是 C 端口径（隔离靠 SQL，与 {@link #selectMyCoupons} 同一条规矩）。
     * 查不到返回 null，由 Service 统一翻成 404 —— <b>不能</b>区分
     * 「这个 id 不存在」与「这个 id 是别人的」，否则可以拿它探测别人有哪些券
     * （与 {@code AddressForOrderVO} 的 IDOR 口径完全一致）。
     *
     * <p>★ 主键等值查询最多一行，不需要 {@code ORDER BY}；
     * 加不加 {@code LIMIT 1} 由你定 —— 加了更能表达「我只要一行」的意图。
     *
     * @param userId       ★ 来自 token 的 principal，<b>不是</b>请求参数
     * @param userCouponId 要用的那张券（{@code user_coupons.id}）
     * @return 素材；查不到（不存在 / 不是你的 / 已删）返回 {@code null}
     */
    CouponUseSourceVO selectForUse(@Param("userId") Long userId,
                                   @Param("userCouponId") Long userCouponId);

    /**
     * ★★★ <b>核销：条件 UPDATE（CAS）</b> —— 阶段二唯一「同一张券可能被两次请求同时用掉」的地方。
     *
     * <p>要写三样（清单在 XML 的注释里）：
     * <pre>
     *   status   = 'USED'
     *   order_id = #{orderId}
     *   used_at  = ______      ← ★ 自定义 XML 的 UPDATE 不走填充器，时间戳必须手写
     * </pre>
     * <b>返回影响行数</b>：{@code 1 = 核销成功}；{@code 0 = 核销失败}。
     *
     * <p>两条守卫（缺一条都会出事故）：
     * <ol>
     *   <li>{@code user_id = #{userId}} —— ★ 归属。<b>不能因为前面 {@code selectForUse}
     *       已经查过一次就省掉它</b>：查与改之间有时间缝，而且「C 端防线写在 SQL 里」
     *       是本项目的一贯口径，不因调用链长短而变；</li>
     *   <li>★ <b>当前状态必须是 {@code 'UNUSED'}</b> —— 这一条是「防重复核销」的全部。
     *       与 {@code CouponMapper#increaseReceivedCount} 的
     *       {@code received_count < total_count} <b>逐字同构</b>：
     *       那边防「超发」，这边防「超用」。</li>
     * </ol>
     *
     * <p>★★ <b>为什么绝不写成「先 SELECT 查状态、确认 UNUSED 再 UPDATE」</b>：
     * 那是 TOCTOU —— 两个并发下单会在同一条时间缝里都读到 UNUSED，
     * 于是同一张券被核销两次、两单都享受了优惠。CAS 把「判断 + 修改」压成一次原子操作，
     * <b>影响行数就是答案</b>。
     *
     * <p>⚠️ {@code used_at} <b>没有</b> DB 默认值（列可空），不写就是 null ——
     * 那会留下「已核销但不知道何时核销」的行，属于安静的错。
     *
     * <p>⚠️ 不包 {@code RETURNING}（要的只是行数）→ 用 {@code <update>} + {@code int} 最干净。
     *
     * @return 影响行数：1 = 核销成功；0 = 券不属于该用户 / 已核销过 / 该行不存在
     */
    int markUsed(@Param("userId") Long userId,
                 @Param("userCouponId") Long userCouponId,
                 @Param("orderId") Long orderId);

    /**
     * ★★★ <b>退券：把某一单用掉的券退回</b> —— {@link #markUsed} 完全对称的<b>逆向</b>操作。
     *
     * <p>调用时机：订单取消（用户取消 / 超时未付 / 管理员取消 —— 三条边都收敛到
     * {@code OrderCancelExecutor#cancelOne}），所以条件里只能有 {@code order_id}。
     *
     * <p>★★ <b>「三样都要还原」，不是「只改状态」</b>。只把 {@code status} 改回
     * {@code 'UNUSED'} 是一个<b>安静的 bug</b>：
     * <pre>
     *   界面上看着对（我的券里又显示「未使用」），但 order_id 还指着那张已取消的订单。
     *   · 下次被新订单用掉时，markUsed 会把 order_id 覆盖成新订单 → 看着没事；
     *   · 但「按 order_id 反查这单用了哪张券」会同时命中两行，
     *     「这张券是哪单退回来的」直接给出错误答案。
     *   ⇒ 验收断言必须包含「order_id IS NULL AND used_at IS NULL」——
     *     只断 status 证明不了「擦干净了」。
     * </pre>
     *
     * <p>★ <b>条件里不写 {@code user_id}</b>：取消有三条边，其中超时任务与管理员取消
     * <b>拿不到</b> userId。{@code order_id} 本身就是「这张券归哪一单」的充分条件。
     * <br>★ 守卫要写「只退确实被这张单用掉的那张」—— 想一想该拿什么当条件，
     * 为什么不能省（提示：没有它，同一单重复取消会把退过的券再退一遍，
     * 而退的动作是「把 order_id 清成 NULL」…… 第二次就找不到它了）。
     *
     * <p>★ <b>影响行数为 0 是【正常】的</b>（这一单没用券）——
     * 调用方不许把 0 行当失败抛异常。<b>这与 {@code releaseLocked} 正好相反</b>：
     * 那边 0 行是真出事了（订单里明明有明细却退不掉），这边 0 行是常态。
     * ★ M1 回归里 day14/15/16 三个 E2E 取消的订单<b>全都</b>没用券 ——
     * 谁把 0 行写成抛异常，M1 当场红。
     *
     * @return 影响行数：1 = 退回了一张券；0 = 这一单没用券（正常）
     */
    int releaseByOrder(@Param("orderId") Long orderId);
}
