package com.mallx.marketing.service;

import com.mallx.common.api.PageResult;
import com.mallx.marketing.dto.CouponCreateDTO;
import com.mallx.marketing.vo.CouponUseVO;
import com.mallx.marketing.vo.CouponVO;
import com.mallx.marketing.vo.UserCouponVO;

import java.math.BigDecimal;

/**
 * 优惠券服务 —— 六个方法，分成三组。
 *
 * <p>★ <b>管理端组</b>（需要 {@code coupon:*} 权限码，Controller 上把门）：
 * <pre>
 *   pageCoupons   —— 券列表，status 可选过滤（不传 = 全都要，含下架）
 *   createCoupon  —— 发券，返回新 id
 *   deleteCoupon  —— 删券，★ 有守卫：被领取过的券删不掉
 * </pre>
 *
 * <p>★ <b>C 端组</b>（登录即可，<b>不挂</b> {@code @PreAuthorize} —— C 端 token 没有 perms claim）：
 * <pre>
 *   listAvailable —— 可领券列表（★ 公开接口，匿名可访问）
 *   receive       —— ★★ 领券，本日核心
 *   listMine      —— 我的券
 * </pre>
 *
 * <p>★★ <b>两组在「归属」上的口径完全相反</b>，这是本项目 Day 17 定型的规矩：
 * <pre>
 *   C 端   ：WHERE user_id = #{userId} 写在 SQL 里   → 隔离靠 SQL
 *   管理端 ：不过滤，能看所有人的数据               → 隔离靠权限码
 * </pre>
 * 所以 {@code receive} / {@code listMine} 必须接 {@code userId}，
 * 而 {@code pageCoupons} / {@code createCoupon} / {@code deleteCoupon} <b>不该</b>接任何 userId ——
 * 「管理端签名里出现 userId」本身就是一条可以断言的反向检查（Day 17 已立此规矩）。
 */
public interface CouponService {

    /**
     * 管理端：券列表（分页）。
     *
     * @param status 可选过滤：1 = 只看可领 / 0 = 只看下架 / <b>null = 全都要</b>
     *               ★ 用 {@code Integer} 而不是 {@code int} —— 只有 null 表达得出「不过滤」
     *               （与 {@code ProductServiceImpl.pageAdminProducts} 同一个取舍）
     */
    PageResult<CouponVO> pageCoupons(Integer status, long page, long size);

    /** 管理端：发券。返回新券 id（前端要拿它跳详情） */
    Long createCoupon(CouponCreateDTO dto);

    /** 管理端：删券。★ 被 {@code user_coupons} 引用过就拒 —— 见实现里的守卫说明 */
    void deleteCoupon(Long id);

    /** C 端：可领券列表（<b>公开</b>，无 userId 参数 —— 匿名也要能看） */
    PageResult<CouponVO> listAvailable(long page, long size);

    /**
     * ★★★ C 端：领券（本日核心）。
     *
     * <p>三步，顺序不能换（详见实现）：
     * <pre>
     *   ① 占名额：CAS 更新 coupons.received_count     → 0 行 = 领不到
     *   ② 发到手：INSERT user_coupons ON CONFLICT     → 0 行 = 已领过
     *   ③ 诊断  ：仅当 ① 失败时再查一次券，为了把错误消息说清楚
     * </pre>
     * <b>两条写操作必须同一事务</b> —— 否则「占了名额但没发到手」会永久占掉一个配额。
     *
     * @param userId ★ 来自 token 的 principal，<b>不是</b>请求参数
     * @param couponId 券 id
     */
    void receive(Long userId, Long couponId);

    /** C 端：我的券（分页）。归属过滤在 SQL 里，{@code userId} 来自 token */
    PageResult<UserCouponVO> listMine(Long userId, long page, long size);

    // ================================================================
    // ★★★ Day 21（阶段二）：给【下单链路】用的三个方法
    //
    //   ★ 它们的调用方不是 HTTP，而是 mall-order —— 这是本项目第一组
    //     「模块之间直接调用的业务接口」。因此多出两条规矩：
    //       ① userId 【必须】由调用方从自己的 token principal 透传进来，
    //          不能依赖「当前登录人」这类全局状态（那样谁调就变成谁，无法断言）；
    //       ② 事务边界由【调用方】决定 —— order 的 createFromCart 已经开了事务，
    //          这里靠默认的 REQUIRED 传播自然加入，不要自己另起一个。
    //
    //   ★ 三个方法的排布就是调用顺序：先算（只读）→ 再销（写）→ 失败/取消时退（写）。
    // ================================================================

    /**
     * ★★★ <b>算抵扣（只读，不写库）</b> —— 下单链路的第一个新步骤。
     *
     * <p>做三件事：<b>校验这张券能不能用</b> → <b>按券型算出抵扣额</b> → <b>封顶 + 定小数位</b>。
     *
     * <p>★★ 它<b>不接 userId 之外的身份信息，也不写任何库</b>，所以刻意<b>不加</b>
     * {@code @Transactional}：它扮演的是「快路径的预演」——
     * 真正决定成败的是后面 {@link #useCoupon} 的 CAS。这里的判据只负责
     * <b>把错误消息说人话</b>（与 {@code createFromCart} 里「库存不足」那句提前提示
     * 同一个角色）：<b>快路径负责对，慢路径负责好懂</b>。
     * ★ 所以这里的判据允许基于查询快照、不参与并发判断 —— 反过来做就是 TOCTOU。
     *
     * <p>⚠️ 它算出来的金额会<b>直接决定实付金额</b>，所以「算错」的代价是钱错，
     * 不是报错。实现时把每一条边界都想一遍（见实现类的注释）。
     *
     * @param userId       ★ 来自 token 的 principal（由 order 侧透传），<b>不是</b>请求参数
     * @param userCouponId 要用的那张券（{@code user_coupons.id}，不是 {@code coupons.id}）
     * @param totalAmount  订单商品总额 —— ★ 服务端算出来的，不是客户端传的
     * @return 抵扣结论（券 id + 抵扣额），供 order 侧写进 {@code orders.discount_amount}
     */
    CouponUseVO calcDiscount(Long userId, Long userCouponId, BigDecimal totalAmount);

    /**
     * ★★★ <b>核销（写库）</b>：把这张券置为已使用，并记下它被哪张订单用掉。
     *
     * <p>★★ 必须在 {@code orderMapper.insert(order)} <b>之后</b>调用 ——
     * 因为要写进 {@code user_coupons.order_id} 的是<b>落库后的真实订单 id</b>。
     * 这也是本方法被拆成「先 calcDiscount 再 useCoupon」而不是合成一步的根本原因：
     * 下单流程里「算钱」发生在插订单之前，「记下用在哪」发生在插订单之后。
     *
     * <p>★ 成败以 {@code markUsed} 的<b>影响行数</b>为准（1 = 成功 / 0 = 失败），
     * 失败必须抛异常 —— 调用方是 {@code @Transactional} 的，
     * 只有抛出去才会把「订单 + 库存 + 金额」一起回滚。
     *
     * @param orderId ★ 落库后的真实订单 id（{@code orders.id}）
     */
    void useCoupon(Long userId, Long userCouponId, Long orderId);

    /**
     * ★★ <b>退券（写库）</b>：把某一单用掉的券退回，供订单取消时调用。
     *
     * <p>★ 返回影响行数，而 <b>0 是正常的</b>（这一单没用券）——
     * 所以调用方<b>不要</b>把 0 当失败。返回值留给调用方决定要不要记日志。
     *
     * <p>★ 只有一条 UPDATE，自身即原子 → 不加 {@code @Transactional}；
     * 调用方 {@code OrderCancelExecutor#cancelOne} 自带事务，REQUIRED 会加入。
     *
     * @param orderId 被取消的订单 id
     * @return 影响行数：1 = 退回了一张；0 = 没券可退（正常）
     */
    int releaseByOrder(Long orderId);
}
