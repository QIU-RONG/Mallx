package com.mallx.order.controller;

import com.mallx.common.api.Result;
import com.mallx.order.dto.OrderCreateDTO;
import com.mallx.order.service.OrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 订单接口（全部需登录）
 *
 * <p>★ 取当前用户只能写 {@code (Long) authentication.getPrincipal()} ——
 * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}，不是 LoginUser。
 *
 * <p>★ 本类刻意不挂 {@code @PreAuthorize}：C 端 token 的权限集是空的，一挂就 403。
 * 「登录才能用」由 {@code anyRequest().authenticated()} 兜住（/api/orders 不在白名单里）。
 */
@Tag(name = "订单")
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(summary = "从购物车下单（结算已勾选的商品，返回订单 id）")
    @PostMapping
    public Result<Long> create(Authentication authentication, @RequestBody @Valid OrderCreateDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(orderService.createFromCart(userId, dto));
    }
}
