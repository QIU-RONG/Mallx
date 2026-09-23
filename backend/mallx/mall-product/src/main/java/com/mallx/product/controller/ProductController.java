package com.mallx.product.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * C 端商品（★ Day 18 起：只剩只读）。
 * <p>
 * 写接口（{@code POST} / {@code PUT /{id}} / {@code DELETE /{id}}）已全部迁到
 * {@link AdminProductController}（{@code /api/admin/products/**}）——
 * 管理端的防线是权限码；而这里的两条 GET 在 Security 白名单里，写接口挂在这儿等于半公开。
 * <p>
 * ★ 迁移后的正面证据：{@code POST /api/products} 返回 <b>405</b>（路径还在、方法没了），
 * 而 {@code GET /api/products} 仍返回 200（白名单红线，不许变）。
 */
@Tag(name = "商品")
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @Operation(summary = "商品分页列表（上架中，可按分类/关键词过滤）")
    @GetMapping
    public Result<PageResult<ProductVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword) {
        Page<ProductVO> voPage = productService.pageProducts(current, size, categoryId, keyword);
        return Result.ok(PageResult.of(voPage));
    }

    @Operation(summary = "商品详情（分类/品牌名 + SKU + 图集）")
    @GetMapping("/{id}")
    public Result<ProductDetailVO> detail(@PathVariable Long id) {
        return Result.ok(productService.getDetail(id));
    }
}
