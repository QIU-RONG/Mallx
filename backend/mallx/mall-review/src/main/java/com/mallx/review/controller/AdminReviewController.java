package com.mallx.review.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.review.dto.ReviewStatusUpdateDTO;
import com.mallx.review.service.ReviewService;
import com.mallx.review.vo.AdminReviewVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端 - 评价审核（Day 55）—— <b>两个端点：列表 / 显示或隐藏</b>。
 *
 * <p>★★ 本类补的是 Day 54 收尾时点名的那个缺口：C 端评价链路（Day 16）早就通了，
 * 但「评价被举报 / 广告语 / 辱骂」时平台<b>没有任何处理手段</b> —— 只能直接改库。
 *
 * <p>★★ <b>路径必须走 {@code /api/admin/**}</b>（与 AdminProductController / AdminRefundController
 * 同一条铁律）：{@code SecurityConfig} 的白名单里有 {@code GET /api/products/**}
 * 的 permitAll，管理端接口若挂到 C 端前缀下会<b>静默变成匿名可访问</b>。
 *
 * <p>★ <b>为什么不做「删除评价」</b>：平台删掉用户的话，那句话说没就没了；
 * 隐藏保留了数据（可恢复、可审计），也是本项目「软删优先」的一贯做法。
 * ★ 也<b>不做「编辑评价内容」</b>：改过的不再是用户的评价。
 *
 * <p>★ 两个端点两个权限码（{@code review:list} / {@code review:status}），
 * 且分发<b>刻意不同</b>：
 * <ul>
 *   <li>{@code review:list} → 超管 + <b>商品管理员</b>（评价挂在商品页，他得看得见）；</li>
 *   <li>{@code review:status} → <b>只给超管</b>。「隐藏一条评价」会直接影响商品页展示与评分，
 *       是以平台身份改写用户表达 —— 与 {@code user:status}（禁用账号）同级别的治理动作。</li>
 * </ul>
 * ⇒ 验收的反向断言正是：op_product 能列表、但改状态稳定 403。
 *
 * <p>★ 参数名用 {@code current}（管理端列表的通用叫法：users / roles 都是它），
 * 与 C 端 {@code /api/reviews/my} 的 {@code page} 不同 —— <b>照各自签名叫</b>，不要「统一」。
 */
@Tag(name = "管理端-评价")
@RestController
@RequestMapping("/api/admin/reviews")
public class AdminReviewController {

    private final ReviewService reviewService;

    public AdminReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    /**
     * 评价分页（管理端：<b>含已隐藏</b>）。
     *
     * @param status 可选：1=显示 0=已隐藏；<b>不传 = 两者都要</b>
     *               ★ 与 C 端正好相反 —— C 端恒为 {@code status = 1}，这正是「管理端要能看见
     *               自己藏了什么」的物理体现（同 L5 品牌「管理端含停用」的教训）。
     */
    @Operation(summary = "评价分页（含已隐藏；可按商品/评分/状态过滤）")
    @GetMapping
    @PreAuthorize("hasAuthority('review:list')")
    public Result<PageResult<AdminReviewVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) Long productId,
            @RequestParam(required = false) Integer rating,
            @RequestParam(required = false) Integer status) {

        return Result.ok(reviewService.pageAdmin(current, size, productId, rating, status));
    }

    /**
     * 显示 / 隐藏一条评价。
     *
     * <p>★★ 用 {@code PUT /{id}/status} 而不是 {@code DELETE}：隐藏是可逆的，
     * 接口形状要与「可逆」对上（同 {@code AdminUserController#updateStatus} 的取舍）。
     *
     * <p>⚠️ {@code @Valid} 跑在 {@code @PreAuthorize} 之前 ⇒ 非法 status 先撞 400，
     * 与有没有权限无关 —— 所以验收权限矩阵时必须给<b>合法载荷</b>
     * （Day 18 立下的判据，Day 22/23 都复用过）。
     */
    @Operation(summary = "显示/隐藏评价（1=显示 0=隐藏）")
    @PutMapping("/{id}/status")
    @PreAuthorize("hasAuthority('review:status')")
    public Result<Void> updateStatus(@PathVariable Long id,
                                     @RequestBody @Valid ReviewStatusUpdateDTO dto) {
        // ★ void 方法必须拆成「调用一句 + return Result.ok()」两句
        reviewService.updateStatus(id, dto.getStatus());
        return Result.ok();
    }
}
