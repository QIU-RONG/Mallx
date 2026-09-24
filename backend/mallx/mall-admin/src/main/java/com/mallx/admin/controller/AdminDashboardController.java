package com.mallx.admin.controller;

import com.mallx.admin.service.DashboardService;
import com.mallx.admin.vo.DashboardOverviewVO;
import com.mallx.admin.vo.TrendPointVO;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 管理端仪表盘（Day 22）。
 *
 * <p>★ 两个端点：{@code /overview}（4 个标量）+ {@code /trend}（按天序列）。
 * 分开的理由见 {@code DashboardOverviewVO} 的 javadoc（快照与时序的语义不同）。
 *
 * <p>★ 权限码 {@code dashboard:overview} / {@code dashboard:trend} 发给<b>三个角色全部</b>
 * （理由：只读汇总、不含任何个人敏感数据、也不含写操作；粒度太粗，无法反推具体订单/用户）。
 * ⚠️ 但<b>仍然每个端点一个权限码</b> —— 与项目约定一致（每个端点一个码），
 * 且将来真要差异化时不必改代码。
 *
 * <p>★ 本类放在 {@code mall-admin} 模块（它是唯一没有「自己业务表」的管理端功能，
 * 而 mall-admin 的模块职责恰好是「管理端 API + RBAC」）；取数走手写 XML 直查表，
 * 零 POM 改动 —— 理由见 {@code DashboardMapper} 的 javadoc。
 */
@Tag(name = "管理端-仪表盘")
@RestController
@RequestMapping("/api/admin/dashboard")
public class AdminDashboardController {

    private final DashboardService dashboardService;

    public AdminDashboardController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @Operation(summary = "仪表盘概览（用户数/商品数/订单数/销售额；销售额为支付流水口径）")
    @GetMapping("/overview")
    @PreAuthorize("hasAuthority('dashboard:overview')")
    public Result<DashboardOverviewVO> overview() {
        return Result.ok(dashboardService.getOverview());
    }

    /**
     * 按天趋势。
     *
     * @param days 回看天数，默认 7；服务端夹紧到 1..90
     *             ★ 不传时靠 {@code defaultValue} —— 不写的话 Spring 对基本类型 {@code int}
     *             会直接抛 400（同 {@code OrderController} 的注释）；
     *             ⚠️ 也不能写成 {@code Integer} 再在 Service 里判 null：
     *             那样「不传」与「传 0」就分不开了，而它们的期望行为不同。
     */
    @Operation(summary = "按天趋势（订单量 + 销售额，缺数据的日子补 0）")
    @GetMapping("/trend")
    @PreAuthorize("hasAuthority('dashboard:trend')")
    public Result<List<TrendPointVO>> trend(@RequestParam(defaultValue = "7") int days) {
        return Result.ok(dashboardService.getTrend(days));
    }
}
