package com.mallx.marketing.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.marketing.entity.Coupon;
import com.mallx.marketing.vo.CouponVO;
import org.apache.ibatis.annotations.Param;

/**
 * 优惠券 Mapper。
 *
 * <p>★ 继承 {@code BaseMapper<Coupon>} 之后，管理端的列表/新建/删除<b>不用写 XML</b>
 * （{@code selectPage} / {@code insert} / {@code deleteById} 现成）。
 * 本类只声明<b>两条</b>必须手写 SQL 的方法 —— 它们都带并发或跨条件的语义，
 * MP 的 wrapper 表达不了。
 *
 * <p>⚠️ 不加 {@code @Mapper} 注解：项目在启动类上配了全局
 * {@code @MapperScan("com.mallx.**.mapper")}，本模块（第 9 个）自动被覆盖。
 * 加了也不报错，只是多余。
 */
public interface CouponMapper extends BaseMapper<Coupon> {

    /**
     * ★★★ <b>领券的核心：条件 UPDATE（CAS）</b> —— 本日唯一「让两个用户抢一张券」的地方。
     *
     * <p>要做的事：把 {@code received_count} 加 1，<b>但只有在四个条件同时成立时</b>才允许。
     * <b>返回影响行数</b>（{@code int}），它就是答案：
     * <pre>
     *   1 = 抢到了        0 = 一个条件都不满足（不存在 / 下架 / 未开始 / 已过期 / 已抢光）
     * </pre>
     *
     * <p>四条守卫（缺一条都会出事故，逐条想清楚为什么）：
     * <ol>
     *   <li>券存在且 <b>{@code status = 1}</b> —— 下架的券不该还能领；</li>
     *   <li><b>{@code start_time <= CURRENT_TIMESTAMP}</b> —— 未开始的不能领；</li>
     *   <li><b>{@code end_time >= CURRENT_TIMESTAMP}</b> —— 已过期的不能领；</li>
     *   <li><b>{@code received_count < total_count}</b> —— ★ 限量。这一条是「防超发」的全部。</li>
     * </ol>
     *
     * <p>★★ 三条铁律：
     * <ul>
     *   <li><b>加法必须由数据库做</b>：{@code SET received_count = received_count + 1}。
     *       <b>绝不</b>「先 SELECT 出当前值、在 Java 里 +1、再 UPDATE 回去」——
     *       那中间有一条时间缝，两个并发请求会读出同一个值，最后只加了 1 次（超发）。</li>
     *   <li><b>时间比较必须用 {@code CURRENT_TIMESTAMP}</b>，不能把 Java 的 {@code LocalDateTime.now()}
     *       当参数传进来 —— 应用服务器与 DB 的时钟不是同一个（本项目 Day 14 记过这条）。</li>
     *   <li><b>影响行数就是答案</b>，与 Day 17 的 {@code deductStock} 逐字同构：
     *       那边守卫是 {@code available_stock >= #{qty}}，这边是 {@code received_count < total_count}。</li>
     * </ul>
     *
     * <p>⚠️ 这条 SQL <b>不该</b>包 {@code RETURNING}。要的只是行数；
     * 包了就得写成 {@code <select>} 并加 {@code flushCache="true"}（Day 17 的坑）。
     * 用 {@code <update>} + {@code int} 最干净。
     *
     * @param couponId 券 id
     * @return 影响行数：1 = 领取成功；0 = 领不到
     */
    int increaseReceivedCount(@Param("couponId") Long couponId);

    /**
     * C 端可领券列表（公开接口，分页）。
     *
     * <p>要查的字段与 {@link CouponVO} 一致，别名一律<b>下划线</b>。
     *
     * <p>★★ 筛选条件与 {@link #increaseReceivedCount} 的四条守卫<b>逐字对应</b>：
     * <pre>
     *   status = 1  /  start_time &lt;= CURRENT_TIMESTAMP  /  end_time &gt;= CURRENT_TIMESTAMP
     *   /  received_count &lt; total_count
     * </pre>
     * ★ 这是本接口最重要的一条「口径一致」：<b>列表里展示得出来的，就是领得到的</b>。
     * 两边写岔了（比如列表漏了「已抢光」那条），用户会看到「列表里有、点进去说抢光了」——
     * 不报错、不 500，只是体验坏掉，属于最难被发现的一类缺陷。
     *
     * <p>★ 排序：{@code ORDER BY id DESC}（新券在前）。不带排序的分页 = 随机翻页。
     * <p>★ 分页由插件改写：<b>XML 里不写 LIMIT</b>，但首参必须是 {@code IPage}，
     * 否则插件<b>静默</b>不改写 → 查全表（不报错）。
     *
     * @param page 分页参数（首参必须是 IPage，MyBatis-Plus 靠它改写 SQL）
     */
    IPage<CouponVO> selectAvailableCoupons(IPage<CouponVO> page);
}
