package com.mallx.inventory.controller;

import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.service.InventoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * C 端 - 库存查询（Day 73）。
 *
 * <p>★ 只暴露「可售库存」这一格，不返回 locked / sold / total ——
 * 后三格是运营数据，没必要公开。
 *
 * <p>★ 路径在 {@code /api/inventory/stock}，SecurityConfig 里按<b>精确路径 + GET</b> 放行，
 * 不用 {@code /api/inventory/**}：管理端 {@code /api/admin/inventory/**} 不受影响，
 * 将来本模块新增的写接口也不会被静默公开。
 *
 * <p>★ 一次最多 100 个 SKU：参数是 query string，不设上限等于把 IN 列表交给调用方保管。
 */
@Tag(name = "C 端-库存查询")
@RestController
@RequestMapping("/api/inventory")
public class InventoryQueryController {

    private static final int MAX_SKU_IDS = 100;

    private final InventoryService inventoryService;

    public InventoryQueryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @Operation(summary = "批量查可售库存（公开；skuIds=1,2,3）")
    @GetMapping("/stock")
    public Result<Map<Long, Integer>> stock(@RequestParam(required = false) List<Long> skuIds) {
        if (skuIds == null || skuIds.isEmpty()) {
            return Result.ok(Map.of());
        }
        if (skuIds.size() > MAX_SKU_IDS) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "一次最多查询 " + MAX_SKU_IDS + " 个 SKU");
        }
        return Result.ok(inventoryService.availableStock(skuIds));
    }
}
