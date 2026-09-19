package com.mallx.order.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.order.dto.OrderCreateDTO;
import com.mallx.order.service.OrderService;
import com.mallx.order.vo.OrderDetailVO;
import com.mallx.order.vo.OrderVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 订单接口（全部需登录）
 *
 * <p>★ 取当前用户只能写 {@code (Long) authentication.getPrincipal()} ——
 * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}，不是 LoginUser。
 *
 * <p>★ 本类刻意不挂 {@code @PreAuthorize}：C 端 token 的权限集是空的，一挂就 403。
 * 「登录才能用」由 {@code anyRequest().authenticated()} 兜住（/api/orders 不在白名单里）。
 *
 * <p>★ 三个接口都【不接收 userId 参数】—— 用户是谁只从 token 来。
 * 这是越权防线的最上游：客户端连表达「查别人的」的机会都没有。
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

    /**
     * ★ 注意这里用的是 {@code @RequestParam defaultValue}，参数名 {@code page} 而不是 {@code current}
     * —— 对外接口的叫法以文档为准，内部的 MP {@code Page} 才叫 current。
     *
     * <p>⚠️ 不写 defaultValue 的话，不传参时 Spring 对基本类型 long 会直接抛异常（400）；
     * 写了 defaultValue 才是「可不传」。
     */
    @Operation(summary = "我的订单列表（分页，size 上限 100）")
    @GetMapping
    public Result<PageResult<OrderVO>> list(Authentication authentication,
                                            @RequestParam(defaultValue = "1") long page,
                                            @RequestParam(defaultValue = "10") long size) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(orderService.listMyOrders(userId, page, size));
    }

    /**
     * 订单详情。
     *
     * <p>⚠️ 路径变量类型是 {@code Long} —— 传 {@code /api/orders/abc} 时 Spring 抛
     * {@code MethodArgumentTypeMismatchException}，由 GlobalExceptionHandler 转成
     * 200 + code=400「参数 id 格式不正确」。
     */
    @Operation(summary = "订单详情（非本人订单返回 404）")
    @GetMapping("/{id}")
    public Result<OrderDetailVO> detail(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(orderService.detail(userId, id));
    }
}
