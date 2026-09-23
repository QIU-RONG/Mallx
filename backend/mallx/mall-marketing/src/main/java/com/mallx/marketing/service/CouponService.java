package com.mallx.marketing.service;

import com.mallx.common.api.PageResult;
import com.mallx.marketing.dto.CouponCreateDTO;
import com.mallx.marketing.vo.CouponVO;
import com.mallx.marketing.vo.UserCouponVO;

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
}
