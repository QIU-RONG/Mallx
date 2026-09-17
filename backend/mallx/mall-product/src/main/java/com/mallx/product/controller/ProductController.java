package com.mallx.product.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.product.dto.ProductCreateDTO;
import com.mallx.product.dto.ProductUpdateDTO;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

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

    // ------------------------------------------------------------------
    // 以下三个是写接口：白名单只放行了 HttpMethod.GET，所以
    // POST/PUT/DELETE 会落到 anyRequest().authenticated()，必须带 token；
    // 再经 @PreAuthorize 逐个比对 token 里带过来的权限码。
    // ------------------------------------------------------------------

    @Operation(summary = "新增商品（需 product:create 权限）")
    @PostMapping
    @PreAuthorize("hasAuthority('product:create')")
    public Result<Long> create(@RequestBody @Valid ProductCreateDTO dto) {
        return Result.ok(productService.createProduct(dto));
    }

    @Operation(summary = "修改商品（需 product:update 权限）")
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('product:update')")
    public Result<Void> update(@PathVariable Long id, @RequestBody @Valid ProductUpdateDTO dto) {
        productService.updateProduct(id, dto);
        return Result.ok();
    }

    @Operation(summary = "删除商品（需 product:delete 权限）")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('product:delete')")
    public Result<Void> delete(@PathVariable Long id) {
        productService.deleteProduct(id);
        return Result.ok();
    }
}
