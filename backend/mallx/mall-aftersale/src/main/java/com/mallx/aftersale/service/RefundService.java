package com.mallx.aftersale.service;

import com.mallx.aftersale.dto.RefundApplyDTO;
import com.mallx.aftersale.dto.RefundShipDTO;
import com.mallx.aftersale.vo.AdminRefundVO;
import com.mallx.aftersale.vo.RefundVO;
import com.mallx.common.api.PageResult;

/**
 * 售后/退款服务（Day 46）
 */
public interface RefundService {

    // ================== C 端 ==================

    /**
     * 申请退款 / 售后。
     *
     * <p>★ 三步：
     * <pre>
     *   ① 取订单事实（归属过滤在 SQL 里）→ null = 404（「不存在」与「不是你的」不可区分）
     *   ② 关系校验：type 与订单状态是否匹配（★ 本模块最重要的一条业务规则）
     *   ③ 插一张 APPLIED 的退款单（退款额 = 订单实付快照）
     * </pre>
     *
     * <p>★★ <b>并发重复申请由【数据库】兜底</b>：{@code uk_refunds_active_order}
     * 是一条<b>部分唯一索引</b>（只对「进行中」的行生效）。
     * ⚠️ Service 侧那个 {@code countActiveByOrder} 只负责给出人话错误，
     *   它不是防线 —— 只靠「先查有没有再插」是 TOCTOU，连点两次会各插一张。
     *
     * @param userId 来自 token（不接受客户端传参）
     * @return 新退款单 id
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在
     * @throws com.mallx.common.exception.BusinessException code=400 状态不支持 / 类型不匹配 / 已有进行中的售后单
     */
    Long apply(Long userId, RefundApplyDTO dto);

    /** 我的售后单（分页，按 id 倒序） */
    PageResult<RefundVO> listMine(Long userId, long page, long size);

    /**
     * 我的某一张售后单。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 不存在<b>或</b>不是你的
     */
    RefundVO detailMine(Long userId, Long refundId);

    /** 撤销申请（仅 APPLIED 可撤，且只能撤自己的） */
    void cancel(Long userId, Long refundId);

    /** 退货寄出：填物流单号（仅 RETURN_REFUND 的 APPROVED 状态可走） */
    void ship(Long userId, Long refundId, RefundShipDTO dto);

    // ================== 管理端 ==================

    /** 全站售后单列表（分页，可按 status / userId 筛） */
    PageResult<AdminRefundVO> listAll(String status, Long userId, long page, long size);

    /** 审核通过：APPLIED → APPROVED */
    void approve(Long refundId, String remark);

    /** 审核拒绝：APPLIED → REJECTED（终态，一分钱没动） */
    void reject(Long refundId, String remark);

    /** 确认收货：RETURNING → REFUNDING */
    void receive(Long refundId);

    /**
     * ★★★ 执行退款 —— <b>全模块唯一会动钱的那个方法</b>。
     *
     * <p>五个写点，<b>必须同一事务</b>：
     * <pre>
     *   ① CAS 退款单 → SUCCESS（★ 抢资格，抢不到就什么都不做）
     *   ② CAS 订单   → REFUNDED
     *   ③ 逐 SKU 回补库存（sold → available，写 REFUND_RETURN 流水）
     *   ④ 退这一单用掉的券（0 行 = 没用过券，正常）
     *   ⑤ 写一笔【负向】支付流水
     * </pre>
     *
     * <p>★★ 顺序是<b>承重</b>的：① 必须先于其余四个 ——
     * 它是「抢资格」的那一步。放到最后就会出现
     * 「两个客服同时点，两人都把钱退了、库存补了两遍，最后才有一个人发现状态不对」
     * （那时副作用已经发出去了，回滚也来不及 —— 因为另一条已经提交）。
     */
    void executeRefund(Long refundId);
}
