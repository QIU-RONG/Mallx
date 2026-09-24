package com.mallx.admin.service;

import com.mallx.admin.vo.DashboardOverviewVO;
import com.mallx.admin.vo.TrendPointVO;

import java.util.List;

/**
 * 管理端仪表盘（Day 22）。
 *
 * <p>只读聚合，无事务、无写点。
 */
public interface DashboardService {

    /** 4 个标量快照（用户数 / 商品数 / 订单数 / 销售额） */
    DashboardOverviewVO getOverview();

    /**
     * 最近 {@code days} 天的按天趋势（订单量 + 销售额，缺数据的日子补 0）。
     *
     * @param days 天数；★ 实现里必须夹紧到 1..90
     *             （用户可控的量都要夹紧，同族教训见 L1 的 {@code size=-1} 查全表）
     */
    List<TrendPointVO> getTrend(int days);
}
