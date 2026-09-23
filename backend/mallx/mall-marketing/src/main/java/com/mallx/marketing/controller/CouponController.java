package com.mallx.marketing.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.marketing.service.CouponService;
import com.mallx.marketing.vo.CouponVO;
import com.mallx.marketing.vo.UserCouponVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * C 端优惠券接口（Day 20）—— <b>骨架</b>，三个方法体由你写。
 *
 * <p>★ <b>填实现时：整段替换下面那行 TODO 注释与紧跟的 {@code throw}</b>（含删掉 throw）。
 * 一个类里有好几处长得一样的 {@code throw}，<b>只删你正在填的那一个</b>。
 *
 * <p>★★ <b>为什么类级只映射到 {@code /api}，而不是 {@code /api/coupons}：</b>
 * 与 {@code ReviewController} 同一个理由 —— 三个端点的<b>可见性不一样</b>：
 * <pre>
 *   GET  /api/coupons                     ★ 公开   （落在白名单里，游客可看有哪些券）
 *   GET  /api/coupons/my                   需登录
 *   POST /api/coupons/{couponId}/receive   需登录
 * </pre>
 *
 * <p>★★ 本日的安全要点（与 Day 16 的差别就在 SecurityConfig 那一行）：
 * <pre>
 *   .requestMatchers(HttpMethod.GET, "/api/coupons").permitAll()
 *                                     ↑ 精确路径，不是 /**
 * </pre>
 * 若写成 {@code "/api/coupons/**"}，会连 {@code /api/coupons/my} 一起公开 ——
 * 白名单只认「路径 + 方法」，<b>不认</b>「同一个 Controller 里的不同方法」，
 * 于是「我的券」会<b>静默公开</b>（任何人能看别人的券，且不报错）。
 * ★ 验收会专门断言这一对：匿名打 {@code /api/coupons} → 200，
 * 匿名打 {@code /api/coupons/my} → <b>401</b>。这就是白名单粒度的证据。
 *
 * <p>★ 本类<b>刻意不挂</b> {@code @PreAuthorize}：C 端 token 的权限集是空的
 * （payload 里没有 perms claim，Day 15 实测）—— 一挂就必然 403。
 *
 * <p>★ {@code page} / {@code size} 对外用 {@code page}（不是 MP 内部的 {@code current}），
 * 且<b>必须写 {@code defaultValue}</b>，否则不传参时 Spring 对基本类型 {@code long} 直接抛 400。
 */
@Tag(name = "优惠券")
@RestController
@RequestMapping("/api")
public class CouponController {

    private final CouponService couponService;

    public CouponController(CouponService couponService) {
        this.couponService = couponService;
    }

    /**
     * ★★ 可领券列表（<b>公开</b>）。
     * <p>★★ 方法参数里<b>不能</b>有 {@code Authentication} —— 匿名访问时它是 null，
     * 而这个接口本来就该允许游客；一旦写了又在里面解引用，游客直接 500。
     * （与 {@code ReviewController#listByProduct} 同一条铁律。）
     * <p>★ 因为是公开的，拿不到 userId ⇒ 结果里<b>不含</b>「我是否已领」——
     * 那是 {@code /api/coupons/my} 的职责。
     */
    @Operation(summary = "可领券列表（公开，游客可看；只含在有效期内且有余额的券）")
    @GetMapping("/coupons")
    public Result<PageResult<CouponVO>> listAvailable(
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long size) {
        return Result.ok(couponService.listAvailable(page, size));
    }

    /**
     * ★★★ 领券（本日核心）。
     * <p>★ 要 {@code Authentication}（取 userId）；★ <b>不挂</b> {@code @PreAuthorize}。
     * <p>★ <b>无请求体</b> —— 券 id 在路径里、用户是谁在 token 里，
     * 没有任何「客户端可以提供的信息」可被伪造（最省心的接口形状）。
     * <p>★ 返回 {@code Result<Void>}，而 Service 的 {@code receive} 也返回 {@code void}
     * ⇒ 这里必须写「调用一句 + {@code return Result.ok();}」<b>两句</b>，
     * <b>不能</b>写成 {@code return Result.ok(couponService.receive(...))}（void 不能当参数）。
     * ★ 这个坑 Day 18 已经踩过（当时是 update / delete 两个方法）。
     * <p>★ 取当前用户只有一种写法：{@code (Long) authentication.getPrincipal()} ——
     * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}，
     * <b>不是</b> {@code LoginUser}（那是管理端的形态）。
     */
    @Operation(summary = "领取优惠券（限量，抢完为止；同一张券每人限领一张）")
    @PostMapping("/coupons/{couponId}/receive")
    public Result<Void> receive(Authentication authentication,
                                @PathVariable Long couponId) {
        // ★ 取当前用户只有这一种写法：过滤器塞进 SecurityContext 的 principal 就是 Long userId
        Long userId = (Long) authentication.getPrincipal();

        // ★ 两句式：Service 的 receive 返回 void，不能塞进 Result.ok(...)
        couponService.receive(userId, couponId);
        return Result.ok();
    }

    /**
     * 我的券（需登录）。
     * <p>★ 要 {@code Authentication}；归属过滤在 SQL 里，这里不传 userId 给「查谁」用。
     * <p>★ 过期是<b>算</b>出来的（{@code expired} 字段），不落库。
     */
    @Operation(summary = "我的优惠券（分页，含是否过期；size 上限 100）")
    @GetMapping("/coupons/my")
    public Result<PageResult<UserCouponVO>> listMine(
            Authentication authentication,
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long size) {
        return Result.ok(couponService.listMine((Long) authentication.getPrincipal(), page, size));
    }
}
