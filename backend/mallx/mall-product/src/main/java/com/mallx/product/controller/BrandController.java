package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.product.service.BrandService;
import com.mallx.product.vo.BrandVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * C 端品牌字典（L5，Day 20 补漏）。
 * <p>
 * ★★ <b>白名单粒度：只放行精确路径 {@code GET /api/brands}</b>。
 * <pre>
 *   SecurityConfig 里写 .requestMatchers(HttpMethod.GET, "/api/brands").permitAll()   ← 对
 *   绝不能写               .requestMatchers(HttpMethod.GET, "/api/brands/**").permitAll() ← 错
 * </pre>
 * 理由（Day 20 实测过同一坑）：白名单只认「路径 + 方法」，<b>不认「同一个 Controller 里的
 * 不同方法」</b>。写成 {@code /**} 之后，将来在这个前缀下加任何私有接口
 * （比如 {@code /api/brands/my}）都会被<b>静默公开</b> —— 不报错、不 403，就是公开了。
 * 先例：{@code /api/coupons}（故意公开）vs {@code /api/coupons/my}（必须带 token）。
 * <p>
 * ★ 本类<b>只有只读一条</b>：品牌的管理端 CRUD（create / update / delete）是 L5 第②步，
 * 会走 {@code /api/admin/brands/**} + 独立权限码，不挂在这里。
 */
@Tag(name = "品牌")
@RestController
@RequestMapping("/api/brands")
public class BrandController {

    private final BrandService brandService;

    public BrandController(BrandService brandService) {
        this.brandService = brandService;
    }

    @Operation(summary = "品牌字典（C 端，仅启用品牌）")
    @GetMapping
    public Result<List<BrandVO>> list() {
        return Result.ok(brandService.listEnabled());
    }
}
