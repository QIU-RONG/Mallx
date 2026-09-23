package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.product.service.BrandService;
import com.mallx.product.vo.BrandVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 管理端品牌字典（L5，Day 20 补漏）。
 * <p>
 * ⚠️ 路径必须走 {@code /api/admin/**} —— 防线是权限码 {@code brand:list}。
 * <b>绝不能</b>挂到 {@code /api/brands/**} 下：那个前缀的 GET 在白名单里，会被静默公开
 * （同 {@link AdminProductController} / {@link AdminCategoryController} 的注释）。
 * <p>
 * ★★ 与 C 端 {@link BrandController#list()} <b>刻意不同源</b>：
 * 这里返回<b>含已停用</b>的全部品牌。管理员要重新启用一个停用品牌，
 * 就必须先能看见它 —— 如果两个接口返回同一份数据，这个接口就是多余的。
 * 这与 {@code getDetail} / {@code getAdminDetail} 拆路是同一条教训（L2）。
 * <p>
 * ★ 返回 <b>void 之外</b>的普通查询，一行转发即可（无「两句式」问题，
 * 那是 {@code updateXxx} / {@code deleteXxx} 返回 void 才有的）。
 */
@Tag(name = "管理端-品牌")
@RestController
@RequestMapping("/api/admin/brands")
public class AdminBrandController {

    private final BrandService brandService;

    public AdminBrandController(BrandService brandService) {
        this.brandService = brandService;
    }

    @Operation(summary = "品牌字典（管理端，含停用品牌，需 brand:list）")
    @GetMapping
    @PreAuthorize("hasAuthority('brand:list')")
    public Result<List<BrandVO>> list() {
        return Result.ok(brandService.listAll());
    }
}
