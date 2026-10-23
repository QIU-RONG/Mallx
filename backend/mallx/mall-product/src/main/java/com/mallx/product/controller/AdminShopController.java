package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.product.dto.ShopCreateDTO;
import com.mallx.product.dto.ShopUpdateDTO;
import com.mallx.product.service.ShopService;
import com.mallx.product.vo.ShopVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 管理端 - 店铺（Day 64，展示层）。
 *
 * <p>★ 只有三个端点：列表 / 新建 / 编辑 —— <b>没有删除</b>。
 * 用「停用」代替删除：店铺下可能挂着商品，物理删会让历史订单/商品失去归属说明；
 * 与「不造永不调用的权限码」同一条取舍。
 *
 * <p>★ 路径必须在 {@code /api/admin/**} 下：{@code GET /api/products/**} 是白名单，
 * 店铺写接口挂到 C 端前缀会被静默公开。
 */
@Tag(name = "管理端-店铺")
@RestController
@RequestMapping("/api/admin/shops")
public class AdminShopController {

    private final ShopService shopService;

    public AdminShopController(ShopService shopService) {
        this.shopService = shopService;
    }

    @Operation(summary = "店铺列表（含停用，需 shop:list）")
    @GetMapping
    @PreAuthorize("hasAuthority('shop:list')")
    public Result<List<ShopVO>> list() {
        return Result.ok(shopService.listAll());
    }

    @Operation(summary = "新建店铺（需 shop:create；店名重复 400）")
    @PostMapping
    @PreAuthorize("hasAuthority('shop:create')")
    public Result<Long> create(@RequestBody @Valid ShopCreateDTO dto) {
        return Result.ok(shopService.create(dto));
    }

    @Operation(summary = "编辑店铺（需 shop:update；局部更新）")
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('shop:update')")
    public Result<Void> update(@PathVariable Long id, @RequestBody @Valid ShopUpdateDTO dto) {
        shopService.update(id, dto);
        return Result.ok();
    }
}
