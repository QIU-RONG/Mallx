package com.mallx.product.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.product.service.FavoriteService;
import com.mallx.product.vo.FavoriteVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 收藏（Day 82）—— C 端，全部需要登录。
 *
 * <p>★ 没有 @PreAuthorize：C 端 token 的 perms 是空集，挂权限码会全员 403；
 * 归属边界是「user_id 只从 token 取」+ SQL 里的 user_id 条件。
 */
@Tag(name = "收藏")
@RestController
@RequestMapping("/api/favorites")
public class FavoriteController {

    private final FavoriteService favoriteService;

    public FavoriteController(FavoriteService favoriteService) {
        this.favoriteService = favoriteService;
    }

    @Operation(summary = "我的收藏（分页）")
    @GetMapping
    public Result<PageResult<FavoriteVO>> page(Authentication authentication,
                                               @RequestParam(defaultValue = "1") long current,
                                               @RequestParam(defaultValue = "12") long size) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(favoriteService.page(userId, current, size));
    }

    @Operation(summary = "是否已收藏")
    @GetMapping("/{productId}/exists")
    public Result<Boolean> exists(Authentication authentication, @PathVariable Long productId) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(favoriteService.exists(userId, productId));
    }

    @Operation(summary = "收藏商品（幂等）")
    @PostMapping("/{productId}")
    public Result<Void> add(Authentication authentication, @PathVariable Long productId) {
        Long userId = (Long) authentication.getPrincipal();
        favoriteService.add(userId, productId);
        return Result.ok();
    }

    @Operation(summary = "取消收藏（幂等）")
    @DeleteMapping("/{productId}")
    public Result<Void> remove(Authentication authentication, @PathVariable Long productId) {
        Long userId = (Long) authentication.getPrincipal();
        favoriteService.remove(userId, productId);
        return Result.ok();
    }
}
