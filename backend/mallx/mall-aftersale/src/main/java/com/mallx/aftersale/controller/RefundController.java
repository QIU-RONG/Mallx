package com.mallx.aftersale.controller;

import com.mallx.aftersale.dto.RefundApplyDTO;
import com.mallx.aftersale.dto.RefundShipDTO;
import com.mallx.aftersale.service.RefundService;
import com.mallx.aftersale.vo.RefundVO;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 售后接口（C 端，全部需登录）—— Day 46。
 *
 * <p>★ 取当前用户只能写 {@code (Long) authentication.getPrincipal()} ——
 * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}。
 *
 * <p>★ 本类<b>一个都不挂</b> {@code @PreAuthorize}：C 端 token 的权限集是空的，
 * 一挂就 403。「登录才能用」由 {@code anyRequest().authenticated()} 兜住
 * （{@code /api/refunds} 不在白名单里）。
 *
 * <p>★★ <b>所有接口都不接收 userId 参数</b> —— 用户是谁只从 token 来。
 * 这是越权防线的最上游：客户端连表达「看别人的 / 改别人的」的机会都没有。
 * 「只能看自己的售后单」由 SQL 里的 {@code WHERE user_id = ?} 保证，
 * 查不到就伪装 404（与「不存在」逐字节相同）。
 *
 * <p>⚠️ 本类<b>没有</b>「执行退款」的端点 —— 那是<b>管理端动作</b>
 * （要动钱、要动库存），挂在 {@code AdminRefundController} 下并受 {@code refund:refund} 保护。
 * 让 C 端能自己把钱退给自己，等于没有售后审核。
 */
@Tag(name = "售后")
@RestController
@RequestMapping("/api/refunds")
public class RefundController {

    private final RefundService refundService;

    public RefundController(RefundService refundService) {
        this.refundService = refundService;
    }

    @Operation(summary = "申请退款/售后（仅退款 = 未发货；退货退款 = 已发货）")
    @PostMapping
    public Result<Long> apply(Authentication authentication, @RequestBody @Valid RefundApplyDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(refundService.apply(userId, dto));
    }

    @Operation(summary = "我的售后单列表")
    @GetMapping("/my")
    public Result<PageResult<RefundVO>> my(Authentication authentication,
                                           @RequestParam(defaultValue = "1") long page,
                                           @RequestParam(defaultValue = "10") long size) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(refundService.listMine(userId, page, size));
    }

    @Operation(summary = "售后单详情（非本人的返回 404，与「不存在」不可区分）")
    @GetMapping("/{id}")
    public Result<RefundVO> detail(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(refundService.detailMine(userId, id));
    }

    /**
     * ★ 用 {@code POST} 而不是 {@code DELETE}/{@code PUT}：
     * 撤销<b>不幂等</b>（第二次会得到 400），而且本项目的写接口一律是 POST。
     */
    @Operation(summary = "撤销售后申请（仅【待审核】可撤）")
    @PostMapping("/{id}/cancel")
    public Result<Void> cancel(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        refundService.cancel(userId, id);
        return Result.ok();
    }

    @Operation(summary = "退货寄出：填写物流单号（仅【退货退款】在【审核通过】后可用）")
    @PostMapping("/{id}/ship")
    public Result<Void> ship(Authentication authentication,
                             @PathVariable Long id,
                             @RequestBody @Valid RefundShipDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        refundService.ship(userId, id, dto);
        return Result.ok();
    }
}
