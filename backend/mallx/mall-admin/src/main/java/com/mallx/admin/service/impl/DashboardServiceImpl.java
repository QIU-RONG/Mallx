package com.mallx.admin.service.impl;

import com.mallx.admin.mapper.DashboardMapper;
import com.mallx.admin.service.DashboardService;
import com.mallx.admin.vo.DashboardOverviewVO;
import com.mallx.admin.vo.TrendPointVO;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.util.List;

/**
 * 仪表盘实现（Day 22）。
 *
 * <p>★ 本类<b>只有一行有判断</b>（夹紧 days），其余都是转发 —— 这本身就是「薄 Service」的
 * 正确形态：业务规则在 SQL 里（补 0、口径），边界规则在 Service 里（夹紧）。
 *
 * <p>⚠️ 不加 {@code @Transactional}：4 个 count/sum 是<b>四次独立读</b>，没有「同生共死」的需求
 * （项目成文判据：看写点个数，读操作一律不加）。代价是四个数<b>不来自同一快照</b> ——
 * 极短窗口内下单会产生「订单数已加、销售额未加」的错觉。V1.0 认下：
 * 要消除它得开事务 + 提高隔离级别，为一个仪表盘不值当。
 */
@Service
public class DashboardServiceImpl implements DashboardService {

    /** 趋势最多回看 90 天。★ 同族：用户可控的量必须夹紧（L1 的 size=-1 会查全表）。 */
    private static final int MAX_TREND_DAYS = 90;

    private final DashboardMapper dashboardMapper;

    public DashboardServiceImpl(DashboardMapper dashboardMapper) {
        this.dashboardMapper = dashboardMapper;
    }

    /**
     * 4 个标量。
     *
     * <p>实现要点（4 次 Mapper 调用 + 组装，无逻辑）：
     * <ol>
     *   <li>{@code new DashboardOverviewVO()} 后逐个 setter（该 VO 只有 {@code @Data}，
     *       没有全参构造 ⇒ 不能 {@code new XxxVO(a,b,c,d)}，与 {@code CouponUseVO} 同一个坑）；</li>
     *   <li>{@code sumPaidAmount()} 返回 {@code BigDecimal}，SQL 已经 {@code coalesce} 过
     *       ⇒ 不会拿到 null；★ 但<b>不要</b>在这里再补一次 {@code == null ? ZERO : x}
     *       —— 那会让 SQL 里的 coalesce 显得可有可无，掩盖真正该修的地方。</li>
     * </ol>
     */
    @Override
    public DashboardOverviewVO getOverview() {
        // ★ 4 次独立读 + 组装，无业务逻辑 —— 薄 Service 的正确形态。
        //   ⚠️ 该 VO 只有 @Data，没有全参构造 ⇒ 只能 new + 逐个 setter
        //      （不能 new DashboardOverviewVO(a, b, c, d)）。
        DashboardOverviewVO vo = new DashboardOverviewVO();
        vo.setUserCount(dashboardMapper.countUsers());
        vo.setProductCount(dashboardMapper.countProducts());
        vo.setOrderCount(dashboardMapper.countOrders());
        // ★ SQL 里已经 coalesce 过 ⇒ 这里不会再拿到 null。
        //   刻意不补 == null ? ZERO : x —— 那会让 SQL 里的 coalesce 显得可有可无，
        //   掩盖真正该修的地方（空表时前端显示 "null" 的根因在 SQL）。
        vo.setSalesAmount(dashboardMapper.sumPaidAmount());
        return vo;
    }

    /**
     * 按天趋势。
     *
     * <p>实现要点：
     * <ol>
     *   <li>★ <b>先夹紧再算日期</b>：
     *       {@code int safeDays = (int) Math.min(Math.max(days, 1), MAX_TREND_DAYS);}
     *       —— 夹紧写在最前面，与「夹紧必须在 new Page&lt;&gt;() 之前」同一条纪律；
     *       ⚠️ {@code days = -1} 若直接进 SQL，{@code generate_series} 会返回空集
     *       ⇒ 接口返回空数组（不报错、看着像「最近没生意」）；{@code days = 100000}
     *       则让 PG 生成 10 万个日期行（廉价的 DB 打点，同 L1）；</li>
     *   <li>起始日期 = 今天往前推 {@code safeDays - 1} 天（含今天，所以是 {@code -1}）：
     *       {@code LocalDate.now().minusDays(safeDays - 1L).toString()}
     *       —— 用 {@code toString()} 得到 {@code yyyy-MM-dd}，直接喂给 Mapper；</li>
     *   <li>★ 用 {@code LocalDate.now()}（服务端时区）而不是 SQL 的 {@code CURRENT_DATE}：
     *       两者在<b>时区不同时会差一天</b>（「今天」的边界由谁定，必须只有一个答案）。
     *       V1.0 认下这个取舍：容器与 DB 同时区；真要严谨就统一把时区写进配置。</li>
     * </ol>
     */
    @Override
    public List<TrendPointVO> getTrend(int days) {
        // ★ 夹紧必须在最前面、且必须在算日期之前 —— 顺序本身就是语义：
        //   先夹紧，则 days=-1 得到 1 天、days=100000 得到 90 天；
        //   先算日期再夹紧，就会用未夹紧的值算出 startDate，然后返回错的区间。
        int safeDays = Math.min(Math.max(days, 1), MAX_TREND_DAYS);

        // 含今天 ⇒ 往前推 safeDays - 1 天。safeDays=1 ⇒ startDate=今天 ⇒ 恰好一个点。
        String startDate = LocalDate.now().minusDays(safeDays - 1L).toString();

        return dashboardMapper.selectDailyTrend(startDate);
    }
}
