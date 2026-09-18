package com.mallx.cart.controller;

import com.mallx.cart.dto.CartAddDTO;
import com.mallx.cart.dto.CartQuantityDTO;
import com.mallx.cart.dto.CartSelectedDTO;
import com.mallx.cart.service.CartService;
import com.mallx.cart.vo.CartVO;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 购物车接口（全部需登录）
 *
 * <p>★ 取当前用户只能写 {@code (Long) authentication.getPrincipal()} ——
 * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}，不是 LoginUser。
 *
 * <p>★ 本类刻意不挂 {@code @PreAuthorize}：C 端 token 的权限集是空的，
 * 一挂就自己对不上也是 403。「登录才能用」由 anyRequest().authenticated() 兜住。
 */
@Tag(name = "购物车")
@RestController
@RequestMapping("/api/cart")
public class CartController {

    private final CartService cartService;

    public CartController(CartService cartService) {
        this.cartService = cartService;
    }

    @Operation(summary = "加入购物车（同 SKU 自动合并数量）")
    @PostMapping
    public Result<Long> add(Authentication authentication, @RequestBody @Valid CartAddDTO dto) {
        Long userId = (Long) authentication.getPrincipal();   // ← principal 就是那个 Long
        return Result.ok(cartService.addToCart(userId, dto));
    }

    @Operation(summary = "购物车列表（实时价/库存/失效标记/小计）")
    @GetMapping
    public Result<CartVO> list(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(cartService.getCart(userId));
    }

    @Operation(summary = "修改购物车项数量（不可超实时库存；非本人项返 404）")
    @PutMapping("/{id}")
    public Result<Void> updateQuantity(Authentication authentication,
                                       @PathVariable Long id,
                                       @RequestBody @Valid CartQuantityDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        cartService.updateQuantity(userId, id, dto.getQuantity());
        return Result.ok();
    }

    @Operation(summary = "勾选 / 取消勾选购物车项（非本人项返 404）")
    @PutMapping("/{id}/selected")
    public Result<Void> updateSelected(Authentication authentication,
                                       @PathVariable Long id,
                                       @RequestBody @Valid CartSelectedDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        cartService.updateSelected(userId, id, dto.getSelected());
        return Result.ok();
    }

    @Operation(summary = "删除购物车项（物理删除；非本人项返 404）")
    @DeleteMapping("/{id}")
    public Result<Void> remove(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        cartService.removeItem(userId, id);
        return Result.ok();
    }
}
