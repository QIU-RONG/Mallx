package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.product.service.CategoryService;
import com.mallx.product.vo.CategoryVO;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.tags.Tag;

import java.util.List;

@Tag(name = "商品分类")
@RequestMapping("/api/categories")
@RestController
public class CategoryController {

    private CategoryService categoryService;

    public CategoryController(CategoryService categoryService){
        this.categoryService = categoryService;
    }

    @Operation(summary = "分类树(含二级子分类)")
    @GetMapping("/tree")
    public Result<List<CategoryVO>> tree(){
        return Result.ok(categoryService.tree());
    }
}
