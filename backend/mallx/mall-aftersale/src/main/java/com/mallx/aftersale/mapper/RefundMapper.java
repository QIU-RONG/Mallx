package com.mallx.aftersale.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.aftersale.entity.Refund;
import com.mallx.aftersale.vo.AdminRefundVO;
import com.mallx.aftersale.vo.RefundVO;
import org.apache.ibatis.annotations.Param;

/**
 * 退款单 Mapper（Day 46）
 *
 * <p><b>XML 三条铁律</b>（Day 05 起就没变过）：
 * <ol>
 *   <li>必须放 {@code src/main/resources/mapper/} —— 放在 {@code src/main/java} 下 Maven 不复制；</li>
 *   <li>{@code mapper-locations} 已配成 {@code classpath*:} + {@code mapper/} 通配
 *       （<b>星号不能省</b>，否则扫不到兄弟模块 jar 里的 XML）；</li>
 *   <li>方法名与 XML 的 {@code id} <b>逐字符一致</b> —— 差一个字母就在调用时报
 *       {@code Invalid bound statement (not found)}，<b>编译期不报错</b>。</li>
 * </ol>
 *
 * <p>★★ <b>本文件的六条推进语句全部是 CAS（条件 UPDATE）</b> —— 这是本模块最要紧的一条纪律：
 * <pre>
 *   审核通过 / 拒绝 / 撤销 / 寄出 / 收货 / 执行退款
 * </pre>
 * 每一条都可能被<b>两个人同时点</b>（两个客服审同一张单、买家连点两次）。
 * 「先查状态、确认可推进、再 UPDATE」在并发下会让两个请求都读到同一个旧状态，
 * 于是<b>退两次钱</b>。把状态判断压进 {@code WHERE}，由数据库做原子比较，
 * <b>只有第一个人能拿到 1 行</b>，其余拿 0 行 → 抛异常 → 整笔回滚。
 *
 * <p>★ {@code @Mapper} 不用写：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包。
 */
public interface RefundMapper extends BaseMapper<Refund> {

    // ================== 读 ==================

    /**
     * 我的售后单（分页）★ 归属过滤写死在 SQL 里。
     *
     * <p>★ {@code WHERE r.user_id = #{userId}} 是 C 端的唯一防线 ——
     * 没有它，任何登录用户都能拉到全站售后单（含别人的订单号与退款金额）。
     * 这与 {@code OrderMapper#selectAdminOrders}「故意没有归属条件」<b>正好相反</b>，
     * 差别写在两条独立的 SQL 文本里，不写在一个布尔开关里。
     *
     * @param page 分页参数（★ 首参必须是 IPage，否则分页插件不改 SQL → 静默查全表）
     */
    IPage<RefundVO> selectMyRefunds(IPage<RefundVO> page, @Param("userId") Long userId);

    /**
     * 管理端售后单列表（分页）<b>不带归属过滤</b> —— 防线是 Controller 的权限码。
     *
     * <p>★ 两个可选条件都是<b>筛选条件</b>，不是权限边界（与 {@code selectAdminOrders} 同口径）。
     */
    IPage<AdminRefundVO> selectAdminRefunds(IPage<AdminRefundVO> page,
                                            @Param("status") String status,
                                            @Param("userId") Long userId);

    /**
     * ★ 我的某一张售后单 —— 归属写死在 SQL，null = 「不存在」或「不是你的」。
     */
    RefundVO selectMyOne(@Param("userId") Long userId, @Param("refundId") Long refundId);

    /**
     * ★★ 「这张订单有没有【进行中】的售后单」—— 与部分唯一索引
     * {@code uk_refunds_active_order} 的 {@code WHERE} 子集逐字一致。
     *
     * <p>⚠️ 本方法只用来给出<b>人话错误</b>；真正拦住并发重复申请的是那条索引。
     * 只靠本方法（「先查有没有」+ 再插）是 TOCTOU：连点两次会各插一张。
     *
     * @return 进行中的条数（0 / 1）
     */
    int countActiveByOrder(@Param("orderId") Long orderId);

    // ================== CAS 推进（六条边） ==================

    /** APPLIED → APPROVED（审核通过）。0 行 = 已被别人处理过 / 状态不是 APPLIED */
    int approve(@Param("refundId") Long refundId, @Param("remark") String remark);

    /** APPLIED → REJECTED（审核拒绝）。0 行 = 同上 */
    int reject(@Param("refundId") Long refundId, @Param("remark") String remark);

    /** APPLIED → CANCELLED（买家撤销，★ 带 user_id 归属） */
    int cancelByUser(@Param("userId") Long userId, @Param("refundId") Long refundId);

    /**
     * APPROVED → RETURNING（买家填物流单号寄出）。
     * ★ WHERE 里带 {@code type = 'RETURN_REFUND'}：
     * 仅退款没有实物可寄，从结构上不可能走到这一步。
     */
    int ship(@Param("userId") Long userId, @Param("refundId") Long refundId,
             @Param("trackingNo") String trackingNo);

    /**
     * RETURNING → REFUNDING（卖家确认收货）。
     * ★ 起点只能是 RETURNING —— 没寄出就不可能收到货。
     */
    int receive(@Param("refundId") Long refundId);

    /**
     * ★★★ → SUCCESS（执行退款，<b>全模块唯一会动钱的那条边</b>）。
     *
     * <p>★ 起点有两条路（取决于类型），都写在这一个 {@code WHERE} 里：
     * <pre>
     *   REFUND_ONLY   : status = 'APPROVED'   （审核通过即可退，没有实物要等）
     *   RETURN_REFUND : status = 'REFUNDING'  （必须等卖家确认收货之后）
     * </pre>
     * ★★ 这样写就把「退货退款还没收到货就退钱」<b>堵死在 SQL 层</b> ——
     * 它不是一个 if 判断，是条件的一部分。
     */
    int markSuccess(@Param("refundId") Long refundId);
}
