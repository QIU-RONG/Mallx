package com.mallx.product.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductSearchVO;
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
 * <p>
 * ★ Day 19 在此新增第三条只读接口 {@code GET /api/products/search}（搜索），
 * 与 {@code GET /api/products/{id}} 存在<b>路径模式重叠</b>，见该方法的注释。
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

    /**
     * ★★★ C 端商品搜索（Day 19）—— <b>骨架</b>，方法体由你写。
     *
     * <p>★★ <b>路径冲突：{@code /api/products/search} 与 {@code /api/products/{id}} 都能匹配</b>
     * 这个 URL，谁赢？
     * Spring 的 {@code PathPattern} 规则是「<b>字面量优先于变量</b>」⇒ 应当命中本方法，
     * 而不是被当成 {@code id = "search"}。
     *
     * <p>★ 但必须<b>实测</b>，不能靠背规则。好在项目里已有现成的尺子
     * （{@code GlobalExceptionHandler} 里两个 handler 的出口不同）：
     * <pre>
     *   命中本方法（骨架期 throw）        → HTTP 200 + code = 500
     *   落到 {id}（"search" 转 Long 失败）→ HTTP 200 + code = 400 + "参数 id 格式不正确"
     * </pre>
     * ⇒ 骨架期打一次 {@code /api/products/search}：返回 <b>500</b> 就证明字面量优先，
     * 返回 400 说明要改路径。这就是链路 A 的断言（见 Day-19 文档 §七）。
     *
     * <p>★ 方法体只有一行转发（同 {@code AdminInventoryController}）：
     * 归一化 / 成对校验 / 夹紧全部在 Service —— <b>同一条规则只在一层表达</b>。
     * 本方法返回类型用 {@code IPage} 的 ProductSearchVO，Controller 侧只做 {@code PageResult.of(...)}。
     */
    @Operation(summary = "商品搜索（全文关键词 + 分类 + SKU 属性筛选）")
    @GetMapping("/search")
    public Result<PageResult<ProductSearchVO>> search(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String attrKey,
            @RequestParam(required = false) String attrValue) {
        return Result.ok(PageResult.of(productService.searchProducts(current, size, keyword, categoryId, attrKey, attrValue)));
    }
}
