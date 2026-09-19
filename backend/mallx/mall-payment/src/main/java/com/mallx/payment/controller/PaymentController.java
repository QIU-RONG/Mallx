package com.mallx.payment.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.payment.dto.PaymentCreateDTO;
import com.mallx.payment.service.PaymentService;
import com.mallx.payment.vo.PaymentVO;
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
 * 支付接口（需登录）：发起支付 + 查支付记录
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
 * <p>★ 三个接口【都不接收 userId 参数】—— 用户是谁只从 token 来。
 * 这是越权防线的最上游：客户端连表达「查/付别人的」的机会都没有。
 *
 * <p>★ {@code POST /api/payments}（发起支付）与 {@code GET /api/payments}（我的支付记录）
 * 同路径不同方法，不冲突。
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

    /**
     * ★ 这里用的是 {@code @RequestParam defaultValue}，参数名 {@code page} 而不是 {@code current}
     * —— 对外接口的叫法以文档为准，内部的 MP {@code Page} 才叫 current。
     *
     * <p>⚠️ 不写 defaultValue 的话，不传参时 Spring 对基本类型 long 会直接抛异常（400）；
     * 写了 defaultValue 才是「可不传」。
     *
     * <p>★ 「只查自己的」不是在这里过滤的 —— 归属条件写在
     * {@code PaymentMapper.xml} 的 {@code WHERE o.user_id = #{userId}} 里
     * （{@code payments} 表没有 user_id，必须 JOIN {@code orders}）。
     */
    @Operation(summary = "我的支付记录（分页，size 上限 100；只返回本人订单的支付记录）")
    @GetMapping
    public Result<PageResult<PaymentVO>> list(Authentication authentication,
                                              @RequestParam(defaultValue = "1") long page,
                                              @RequestParam(defaultValue = "10") long size) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(paymentService.listMyPayments(userId, page, size));
    }

    /**
     * 支付记录详情。
     *
     * <p>⚠️ 路径变量类型是 {@code Long} —— 传 {@code /api/payments/abc} 时 Spring 抛
     * {@code MethodArgumentTypeMismatchException}，由 GlobalExceptionHandler 转成
     * 200 + code=400「参数 id 格式不正确」。
     */
    @Operation(summary = "支付记录详情（非本人记录返回 404）")
    @GetMapping("/{id}")
    public Result<PaymentVO> detail(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(paymentService.detailMyPayment(userId, id));
    }
}
