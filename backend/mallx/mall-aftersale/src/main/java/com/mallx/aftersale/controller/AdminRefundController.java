package com.mallx.aftersale.controller;

import com.mallx.aftersale.service.RefundService;
import com.mallx.aftersale.vo.AdminRefundVO;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端售后接口（Day 46）—— 全部挂在 {@code /api/admin/**} 下。
 *
 * <p>★★ <b>为什么必须是 {@code /api/admin/**} 前缀</b>（沿用 AdminOrderController 的推理）：
 * {@code SecurityConfig} 的白名单里有一条
 * {@code GET /api/products/** , /api/categories/**} 的 {@code permitAll}，
 * 而白名单是<b>先匹配先赢</b>的 —— 管理端接口若图省事挂在 C 端前缀下，
 * 会<b>静默变成匿名可访问</b>。
 * {@code /api/admin/**} 不在白名单 ⇒ 默认要登录 ⇒ {@code @PreAuthorize} 再收紧到权限码，
 * <b>两级都到位</b>。
 *
 * <p>★★★ <b>本类每一个方法都必须挂 {@code @PreAuthorize}</b>：
 * 漏挂一个的直接后果，是那个接口从「只有管理员能用」退化成「任何登录用户都能用」——
 * 而本类里有<b>动钱</b>的端点（{@code refund}），那不是数据泄露，是<b>直接的经济损失</b>。
 *
 * <p>★ 四个写端点各配一个权限码（{@code refund:approve / reject / receive / refund}），
 * 而不是共用一个 {@code refund:audit}：
 * 「审核」与「执行退款」是<b>两个不同的动作</b> ——
 * 前者是判断，后者是把钱打出去。合码等于让任何能审核的人都能直接放款，
 * 那正是内控里最典型的「不相容职务未分离」。
 *
 * <p>★ 本类<b>都不接收 {@code Authentication}</b>：
 * 管理端售后接口不需要知道「当前用户是谁」（权限码已经说明了身份）。
 * ★★ ⚠️ 更硬的一条：{@code JwtAuthenticationFilter} 只把 token 的 {@code sub} 转成
 * {@code Long} 当 principal —— 管理端 admin 与 C 端用户的 {@code sub} 可能撞成同一个数值
 * （Day 44 之前这是真的漏洞）。拿它当「谁审的」是错的。
 * 真要审计「谁审的」，得先让过滤器能区分两种 token（Day 44 已能区分，但 principal 仍是裸 Long）。
 */
@Tag(name = "管理端-售后")
@RestController
@RequestMapping("/api/admin/refunds")
public class AdminRefundController {

    private final RefundService refundService;

    public AdminRefundController(RefundService refundService) {
        this.refundService = refundService;
    }

    @Operation(summary = "售后单列表（全站，可按状态/买家筛）")
    @PreAuthorize("hasAuthority('refund:list')")
    @GetMapping
    public Result<PageResult<AdminRefundVO>> list(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Long userId,
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long size) {
        return Result.ok(refundService.listAll(status, userId, page, size));
    }

    @Operation(summary = "审核通过（仅退款 → 可执行退款；退货退款 → 等买家寄回）")
    @PreAuthorize("hasAuthority('refund:approve')")
    @PostMapping("/{id}/approve")
    public Result<Void> approve(@PathVariable Long id,
                                @RequestParam(required = false) String remark) {
        refundService.approve(id, remark);
        return Result.ok();
    }

    @Operation(summary = "审核拒绝（终态，一分钱没动；remark 会展示给买家）")
    @PreAuthorize("hasAuthority('refund:reject')")
    @PostMapping("/{id}/reject")
    public Result<Void> reject(@PathVariable Long id,
                               @RequestParam(required = false) String remark) {
        refundService.reject(id, remark);
        return Result.ok();
    }

    @Operation(summary = "退货确认收货（已寄出 → 可执行退款）")
    @PreAuthorize("hasAuthority('refund:receive')")
    @PostMapping("/{id}/receive")
    public Result<Void> receive(@PathVariable Long id) {
        refundService.receive(id);
        return Result.ok();
    }

    /**
     * ★★★ 执行退款 —— <b>全项目唯一会动钱的售后端点</b>。
     *
     * <p>五个写点在同一事务里：退款单 → SUCCESS、订单 → REFUNDED、
     * 库存 sold → available（写 {@code REFUND_RETURN} 流水）、退券、
     * 写一笔<b>负向</b>支付流水。
     */
    @Operation(summary = "执行退款（退款单→SUCCESS、订单→REFUNDED、库存回补、退券、写负向流水）")
    @PreAuthorize("hasAuthority('refund:refund')")
    @PostMapping("/{id}/refund")
    public Result<Void> refund(@PathVariable Long id) {
        refundService.executeRefund(id);
        return Result.ok();
    }
}
