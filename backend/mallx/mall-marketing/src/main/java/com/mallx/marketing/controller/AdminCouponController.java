package com.mallx.marketing.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.marketing.dto.CouponCreateDTO;
import com.mallx.marketing.service.CouponService;
import com.mallx.marketing.vo.CouponVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端优惠券管理（Day 20）—— 三个端点均已实现。
 *
 * <p>⚠️ 路径必须走 {@code /api/admin/coupons} —— 与 {@code AdminProductController} 同一条铁律：
 * 挂到 {@code /api/coupons/**} 会落进白名单里的 GET，<b>静默公开</b>。
 *
 * <p>★★ <b>为什么只有三个端点、没有「改券」</b>：
 * 券一旦发出去，改面额会与已领取用户的预期冲突（他领的是「满 100 减 20」，
 * 你把面额改成 10，他手里那张算什么？）。真实系统的做法是「作废旧券 + 新建一张」。
 * 所以 V1.0 就三件事：<b>列表 / 新建 / 删除</b>。
 * ★ 不造 {@code coupon:update} 权限码 —— 一条永远不会被调用的权限本身就是维护成本
 * （与 07-admin-permissions.sql 不给分类单独造「上下架」权限同一取舍）。
 *
 * <p>★ 三个端点各挂一个权限码，它们在 {@code 08-marketing-permissions.sql} 里
 * <b>只补发给了超管</b>（role 1）—— 商品管理员与订单管理员拿到的是 <b>403</b>。
 * 理由：营销在 V1.0 是独立岗位，种子里的三个角色没有 MARKETING_ADMIN，
 * 给商品管理员发券属于越权。★ 验收拿 {@code op_product} / {@code op_order} 做反向对照。
 *
 * <p>★ 三个方法都<b>不接收 userId</b>：管理端不按归属过滤，防线是上面的权限码。
 */
@Tag(name = "管理端-优惠券")
@RestController
@RequestMapping("/api/admin/coupons")
public class AdminCouponController {

    private final CouponService couponService;

    public AdminCouponController(CouponService couponService) {
        this.couponService = couponService;
    }

    /**
     * 券列表（分页）。
     * <p>★ {@code status} 可选：1 = 可领 / 0 = 下架 / 不传 = 全都要。
     * 用 {@code @RequestParam(required = false)} 且类型为 {@code Integer} ——
     * 写成 {@code int} 的话「不传」这条路直接被堵死（与 {@code pageAdminProducts} 同一取舍）。
     */
    @Operation(summary = "优惠券列表（需 coupon:list；status 不传则含下架券）")
    @GetMapping
    @PreAuthorize("hasAuthority('coupon:list')")
    public Result<PageResult<CouponVO>> list(
            @RequestParam(required = false) Integer status,
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long size) {
        return Result.ok(couponService.pageCoupons(status, page, size));
    }

    /**
     * 新建优惠券。
     * <p>★ {@code createCoupon} <b>有</b>返回值（新 id）→ 一行 {@code return Result.ok(...)} 即可。
     * <p>⚠️ {@code @Valid} 与 {@code @PreAuthorize} 的顺序：校验在参数解析期、
     * 授权在方法调用期 ⇒ <b>非法请求先撞 400</b>，与有没有权限无关。
     * ★ 所以验收权限矩阵时<b>必须给合法载荷</b>（Day 18 立下的判据）。
     */
    @Operation(summary = "新建优惠券（需 coupon:create）")
    @PostMapping
    @PreAuthorize("hasAuthority('coupon:create')")
    public Result<Long> create(@RequestBody @Valid CouponCreateDTO dto) {
        return Result.ok(couponService.createCoupon(dto));
    }

    /**
     * 删除优惠券。
     * <p>★ {@code deleteCoupon} 返回 <b>void</b> → 必须拆成
     * 「{@code couponService.deleteCoupon(id);} + {@code return Result.ok();}」<b>两句</b>。
     * <p>★ 有守卫：被 {@code user_coupons} 引用过的券<b>删不掉</b>（返回 400，
     * 而不是让外键抛异常变成 500）—— 这就是「谁引用我决定我能否物理删」（FK 全是 NO ACTION）。
     */
    @Operation(summary = "删除优惠券（需 coupon:delete；已被领取过的券删不掉）")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('coupon:delete')")
    public Result<Void> delete(@PathVariable Long id) {
        couponService.deleteCoupon(id);
        return Result.ok();
    }
}
