package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.product.dto.CategoryCreateDTO;
import com.mallx.product.dto.CategoryUpdateDTO;
import com.mallx.product.service.CategoryService;
import com.mallx.product.vo.CategoryVO;
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
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 管理端分类管理（Day 18）。
 * <p>
 * C 端 {@code /api/categories/tree} 是公开只读；写能力全部落在本类。
 * ⚠️ 同 {@link AdminProductController}：路径必须走 {@code /api/admin/**}，
 * 挂到 {@code /api/categories/**} 会被白名单静默放行。
 * <p>
 * 【本日的三条业务规则（都要在 Service 里守，Controller 只转发）】
 * <ol>
 *   <li><b>只允许两级</b>：新增子分类时，父分类自身必须是顶级（{@code parentId == null}）。
 *       这与 C 端 {@code expandCategoryIds} 的「两层单层扫描」假设一致。</li>
 *   <li><b>改 parentId 不成环</b>：两级约束下退化为「有子分类的分类不许被挂到别人下面」。</li>
 *   <li><b>删除三重校验</b>：① 有子分类 → 拒；② 有商品引用（★ 含已软删的商品）→ 拒；
 *       ③ 都没有才物理删（{@code categories} 表没有 {@code is_deleted}，是真删）。</li>
 * </ol>
 * <p>
 * 【骨架说明（★ 填实现时必读）】
 * 填实现时请<b>整段替换方法体，包括删掉最后那行 throw</b>；只加 return 不删 throw
 * 会得到 {@code [行,列] 无法访问的语句}。
 * ⚠️ 另外：本类有 4 处长得一模一样的 throw，<b>只删你正在填的那个方法的 throw</b>。
 */
@Tag(name = "管理端-分类")
@RestController
@RequestMapping("/api/admin/categories")
public class AdminCategoryController {

    private final CategoryService categoryService;

    public AdminCategoryController(CategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @Operation(summary = "分类树（管理端，含二级子分类）")
    @GetMapping("/tree")
    @PreAuthorize("hasAuthority('category:list')")
    public Result<List<CategoryVO>> tree() {
        // TODO(你写)：return Result.ok(categoryService.tree());
        //   ★ 直接复用 C 端那个 tree() —— 管理端的「看」与 C 端的「看」结构一致，
        //     差别只在【能不能不经鉴权看】：C 端公开，管理端要 category:list。
        throw new UnsupportedOperationException("TODO: AdminCategoryController.tree");
    }

    @Operation(summary = "新增分类（需 category:create）")
    @PostMapping
    @PreAuthorize("hasAuthority('category:create')")
    public Result<Long> create(@RequestBody @Valid CategoryCreateDTO dto) {
        // TODO(你写)：return Result.ok(categoryService.createCategory(dto));
        //   注意返回值是 Result<Long>（新建分类的 id）—— 与商品新增保持一致
        throw new UnsupportedOperationException("TODO: AdminCategoryController.create");
    }

    @Operation(summary = "修改分类（需 category:update，局部更新语义）")
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('category:update')")
    public Result<Void> update(@PathVariable Long id, @RequestBody @Valid CategoryUpdateDTO dto) {
        // TODO(你写)：categoryService.updateCategory(id, dto); return Result.ok();
        throw new UnsupportedOperationException("TODO: AdminCategoryController.update");
    }

    @Operation(summary = "删除分类（需 category:delete，物理删 + 三重校验）")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('category:delete')")
    public Result<Void> delete(@PathVariable Long id) {
        // TODO(你写)：categoryService.deleteCategory(id); return Result.ok();
        throw new UnsupportedOperationException("TODO: AdminCategoryController.delete");
    }
}
