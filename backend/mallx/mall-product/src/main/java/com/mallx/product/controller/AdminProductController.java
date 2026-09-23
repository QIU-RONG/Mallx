package com.mallx.product.controller;

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

/**
 * 管理端商品管理（Day 18）。
 * <p>
 * 【本类与 C 端 ProductController 的关系：数据权限反转第二批】
 * <ul>
 *   <li>C 端 {@code /api/products}：GET 公开（白名单），**写接口本日起全部迁走**；</li>
 *   <li>管理端 {@code /api/admin/products}：读写都在这里，防线是权限码。</li>
 * </ul>
 * ⚠️ <b>路径红线</b>：绝不能把这个类挂到 {@code /api/products/**} 上 ——
 * 那两条 GET 在白名单里（先匹配先赢），挂上去会<b>静默公开、绕过全部鉴权</b>。
 * <p>
 * 【与本项目 Day 17 管理端的两点同构】
 * <ol>
 *   <li>管理端<b>不做归属过滤</b>（这里没有任何 requireOwn）—— 管理员本来就有权看全部；</li>
 *   <li>每个端点一个权限码，且<b>读也要权限</b>（与 C 端「GET 公开」正好相反）。</li>
 * </ol>
 * <p>
 * 【骨架说明（★ 填实现时必读）】
 * 下面每个方法体都是 {@code throw new UnsupportedOperationException(...)}。
 * 填实现时请<b>整段替换方法体，包括删掉最后那行 throw</b> ——
 * 若只在 TODO 下面加 return 而把 throw 留在后面，会得到
 * {@code [行,列] 无法访问的语句}（unreachable statement，编译直接失败）。
 */
@Tag(name = "管理端-商品")
@RestController
@RequestMapping("/api/admin/products")
public class AdminProductController {

    private final ProductService productService;

    public AdminProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * 商品分页（管理端）。
     * <p>
     * 与 C 端 {@code GET /api/products} 的<b>唯一区别就在过滤口径</b>：
     * <pre>
     *   C 端 ：.eq(status, 1)                    // 写死：只看上架
     *   管理端：.eq(status != null, status)       // 条件：不传就全都要（含下架）
     * </pre>
     * ⚠️ {@code status} 是 {@code Integer} 而非 {@code int} —— 只有 null 才表达得出「不过滤」。
     *
     * @param current    页码，从 1 开始
     * @param size       每页条数（须夹紧到 1..100）
     * @param categoryId 可选：分类过滤（沿用「自己 + 直接子分类」的展开口径）
     * @param keyword    可选：名称模糊匹配
     * @param status     可选：1=上架 0=下架；不传 = 两者都要
     */
    @Operation(summary = "商品分页（管理端：含下架，status 可选过滤）")
    @GetMapping
    @PreAuthorize("hasAuthority('product:list')")
    public Result<PageResult<ProductVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status) {
        // TODO(你写)：一行转发即可 ——
        //   ★ 页码/页大小夹紧【不在这层】做：它在 Service（pageAdminProducts）里，
        //     与 Day 17 的 AdminInventoryController 同构 —— Controller 只管转，Service 管口径。
        //   return Result.ok(PageResult.of(
        //           productService.pageAdminProducts(current, size, categoryId, keyword, status)));
        throw new UnsupportedOperationException("TODO: AdminProductController.page");
    }

    @Operation(summary = "商品详情（管理端：下架商品也能看）")
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('product:detail')")
    public Result<ProductDetailVO> detail(@PathVariable Long id) {
        // TODO(你写)：直接复用 productService.getDetail(id) —— 它不判 status，天然满足管理端
        throw new UnsupportedOperationException("TODO: AdminProductController.detail");
    }

    @Operation(summary = "新增商品（需 product:create）")
    @PostMapping
    @PreAuthorize("hasAuthority('product:create')")
    public Result<Long> create(@RequestBody @Valid ProductCreateDTO dto) {
        // TODO(你写)：复用 productService.createProduct(dto)（它已含「分类存在」校验与三表事务）
        throw new UnsupportedOperationException("TODO: AdminProductController.create");
    }

    @Operation(summary = "修改商品（含上下架：{\"status\":0} 即下架）")
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('product:update')")
    public Result<Void> update(@PathVariable Long id, @RequestBody @Valid ProductUpdateDTO dto) {
        // TODO(你写)：复用 productService.updateProduct(id, dto)
        //   ★ 本日【不】为上下架单独开端点：ProductUpdateDTO 里已有 status，
        //     单字段更新走 PUT 语义上就是「编辑商品」。
        throw new UnsupportedOperationException("TODO: AdminProductController.update");
    }

    @Operation(summary = "删除商品（软删主表）")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('product:delete')")
    public Result<Void> delete(@PathVariable Long id) {
        // TODO(你写)：复用 productService.deleteProduct(id)
        throw new UnsupportedOperationException("TODO: AdminProductController.delete");
    }
}
