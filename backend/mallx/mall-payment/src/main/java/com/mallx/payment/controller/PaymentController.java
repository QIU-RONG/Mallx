package com.mallx.payment.controller;

import com.mallx.common.api.Result;
import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.service.PaymentService;
import com.mallx.payment.vo.PaymentVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 支付接口（需登录）
 *
 * <p>★ 为什么接口在 payment 模块、而不是挂在 OrderController 上：
 * 「支付」必须写 {@code orders} 表 ⇒ 依赖方向是 {@code mall-payment → mall-order}。
 * 若把接口挂在 OrderController，就要求 {@code mall-order → mall-payment} ⇒
 * <b>循环依赖，Maven 直接构建失败</b>。
 * 所以路径是独立的 {@code POST /api/payments}，订单 id 走 body。
 *
 * <p>★ 取当前用户只能写 {@code (Long) authentication.getPrincipal()} ——
 * 过滤器塞进 SecurityContext 的 principal 就是 {@code Long userId}，<b>不是 LoginUser</b>
 * （LoginUser 是管理端的形态，见 AuthController）。
 *
 * <p>★ 本类刻意不挂 {@code @PreAuthorize}：C 端 token 的权限集是空的（没有 perms claim），
 * 一挂就 403。「登录才能用」由 {@code anyRequest().authenticated()} 兜住
 * ——{@code /api/payments} 不在白名单里。
 *
 * <p>★ 接口【不接收 userId 参数】—— 用户是谁只从 token 来。
 * 这是越权防线的最上游：客户端连表达「付别人的单」的机会都没有。
 */
@Tag(name = "支付")
@RestController
@RequestMapping("/api/payments")
public class PaymentController {

    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @Operation(summary = "支付订单（同一订单只能成功支付一次；重复支付返回 400）")
    @PostMapping
    public Result<PaymentVO> pay(Authentication authentication,
                                 @Valid @RequestBody PaymentCreateDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(paymentService.pay(userId, dto));
    }
}
