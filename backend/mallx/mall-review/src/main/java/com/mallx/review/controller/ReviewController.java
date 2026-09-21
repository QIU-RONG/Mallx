package com.mallx.review.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.review.dto.ReviewCreateDTO;
import com.mallx.review.service.ReviewService;
import com.mallx.review.vo.ReviewPageVO;
import com.mallx.review.vo.ReviewVO;
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
 * 商品评价接口（Day 16）—— <b>骨架</b>，三个方法体由你写。
 *
 * <p>★★ <b>为什么类级只映射到 {@code /api}，而不是 {@code /api/reviews}：</b>
 * 因为三个端点的前缀<b>不一样</b>，而且这不是随便起的名字 ——
 * 是 {@code SecurityConfig} 的白名单<b>逼出来</b>的：
 * <pre>
 *   POST   /api/reviews                      需登录   （不在白名单 → 被 anyRequest().authenticated() 兜住）
 *   GET    /api/reviews/my                   需登录   （同上）
 *   GET    /api/products/{productId}/reviews  ★公开   （落在 GET /api/products/** 白名单里，游客可看）
 * </pre>
 *
 * <p>★ 商品维度的列表<b>必须</b>挂在 {@code /api/products/&#123;id&#125;/reviews}：
 * <ul>
 *   <li>写成 {@code GET /api/reviews?productId=x} → 被 {@code anyRequest()}
 *       兜住 → <b>游客看不了评价</b>（而逛商品详情页时看到评价正是电商的实情）；</li>
 *   <li>把它加进白名单又会连 {@code /api/reviews/my} 一起公开 ——
 *       白名单只认<b>路径 + 方法</b>，<b>不认</b>「同一个 Controller 里的不同方法」。</li>
 * </ul>
 * ★ 代价是类级只能到 {@code /api}，三个方法各写完整路径。
 * 这<b>不是</b> hack：Spring 允许多个模块映射同一个路径前缀（这里 {@code /api/products}
 * 已被 {@code ProductController} 占着），只要<b>完整路径</b>不重复即可。
 *
 * <p>★ 一个「不写」的决定：<b>本日不改 {@code SecurityConfig}</b> —— 现有白名单已经够用，
 * 动安全配置的收益是 0。
 *
 * <p>★★ 三个端点<b>都不接收 {@code userId} 参数</b> —— 用户是谁只从 token 来
 * （与 {@code PaymentController} 同一条铁律）。取当前用户只能写
 * {@code (Long) authentication.getPrincipal()}：过滤器塞进 SecurityContext 的
 * principal 就是 {@code Long userId}，<b>不是 LoginUser</b>（那是管理端的形态）。
 *
 * <p>★ 本类<b>刻意不挂 {@code @PreAuthorize}</b>：评价是 C 端动作，而 C 端 token 的
 * 权限集是空的（payload 里没有 perms claim，Day 15 已实测）—— 一挂就必然 403。
 * 管理端审核评价是 V2.0 的事（V1.0 连管理端页面都没有）。
 *
 * <p>★ {@code GET /api/reviews/my} 的 {@code page} 参数对外用 {@code page}（不是 MP 内部的
 * {@code current}），与 {@code PaymentController} 的列表接口保持一致的叫法；
 * 且必须写 {@code defaultValue}，否则不传参时 Spring 对基本类型 {@code long} 会直接抛 400。
 */
@Tag(name = "商品评价")
@RestController
@RequestMapping("/api")
public class ReviewController {

    private final ReviewService reviewService;

    public ReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    /**
     * 发表评价。
     * <p>★ 要 {@code Authentication}（取 userId）；★ <b>不挂</b> {@code @PreAuthorize}。
     * <p>★ 请求体只有 orderItemId / rating / content 三个字段，服务端做三重派生。
     */
    @Operation(summary = "发表评价（只能评自己的、已完成的订单明细；一条明细只能评一次）")
    @PostMapping("/reviews")
    public Result<ReviewVO> create(Authentication authentication,
                                   @Valid @RequestBody ReviewCreateDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(reviewService.create(userId, dto));
    }

    /**
     * 商品评价列表（<b>公开</b>）。
     * <p>★★ 方法参数里<b>不能</b>有 {@code Authentication} —— 匿名访问时它是 null，
     * 而且这个接口本来就该允许游客；一旦写了又在里面解引用，游客直接 500。
     * <p>★ 路径必须带 {@code /products/&#123;productId&#125;} 前缀才落在白名单里。
     */
    @Operation(summary = "商品评价列表（公开，游客可看；带评分聚合）")
    @GetMapping("/products/{productId}/reviews")
    public Result<ReviewPageVO> listByProduct(@PathVariable Long productId,
                                              @RequestParam(defaultValue = "1") long page,
                                              @RequestParam(defaultValue = "10") long size) {
        return Result.ok(reviewService.pageByProduct(productId, page, size));
    }

    /**
     * 我的评价列表（需登录）。
     * <p>★ 要 {@code Authentication}；归属过滤在 SQL 里，这里不传 userId 给「查谁」用。
     */
    @Operation(summary = "我的评价（分页，size 上限 100）")
    @GetMapping("/reviews/my")
    public Result<PageResult<ReviewVO>> listMine(Authentication authentication,
                                                 @RequestParam(defaultValue = "1") long page,
                                                 @RequestParam(defaultValue = "10") long size) {
        return Result.ok(reviewService.pageMine((Long) authentication.getPrincipal(), page, size));
    }
}
