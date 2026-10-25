package com.mallx.product.controller;

import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.entity.Shop;
import com.mallx.product.mapper.ShopMapper;
import com.mallx.product.vo.ShopVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.BeanUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * C 端 - 店铺主页信息（Day 81）。
 *
 * <p>★ 只返回启用的店铺；停用/不存在的店统一 404 ——
 * 停用店铺的商品可能还在卖（Day 64 的取舍），但店铺主页不对外露出。
 */
@Tag(name = "C 端-店铺")
@RestController
@RequestMapping("/api/shops")
public class ShopPublicController {

    private final ShopMapper shopMapper;

    public ShopPublicController(ShopMapper shopMapper) {
        this.shopMapper = shopMapper;
    }

    @Operation(summary = "店铺信息（公开；停用店铺 404）")
    @GetMapping("/{id}")
    public Result<ShopVO> detail(@PathVariable Long id) {
        Shop shop = shopMapper.selectById(id);
        if (shop == null || shop.getStatus() == null || shop.getStatus() != 1) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "店铺不存在");
        }
        ShopVO vo = new ShopVO();
        BeanUtils.copyProperties(shop, vo);
        return Result.ok(vo);
    }
}
