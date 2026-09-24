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
import org.springframework.security.access.prepost.PreAuthorize;
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
 * <p>★ 本类<b>默认</b>不挂 {@code @PreAuthorize}：C 端 token 的权限集是空的，一挂就 403。
 * 「登录才能用」由 {@code anyRequest().authenticated()} 兜住（/api/orders 不在白名单里）。
 *
 * <p>★★ <b>唯独 {@link #ship(Long)} 例外</b> —— 发货是<b>管理端动作</b>，
 * 它挂 {@code @PreAuthorize("hasAuthority('order:ship')")}。
 * 权限种子把这条权限的路径定死为「订单发货」那个 POST 端点，
 * 所以它与 C 端接口同处一个类、共用 {@code /api/orders} 前缀，
 * 只是那一个方法多了一道方法级 RBAC。
 * → 同一个类里出现<b>两种鉴权模型是有意为之</b>，不是漏改。
 *
 * <p>★ 所有接口都【不接收 userId 参数】—— 用户是谁只从 token 来。
 * 这是越权防线的最上游：客户端连表达「查别人的 / 改别人的」的机会都没有。
 * （发货更进一步：它连 token 里的身份都不读，见下。）
 *
 * <p>⚠️⚠️ <b>不要把 principal 当「发货人」</b>：
 * {@code JwtAuthenticationFilter} 只把 token 的 {@code sub} 转成 {@code Long} 当 principal，
 * <b>完全无视</b> {@code JwtUtil} 签进去的 {@code type:"ADMIN"} claim ——
 * 管理端 admin 与 C 端 demo 的 {@code sub} 都是 {@code "1"}，
 * 于是两者的 principal <b>数值相同、类型相同，无法区分</b>。
 * 所以 {@code ship} 方法<b>既不接收也不读取</b> principal：
 * 发货端点只需要「有没有 order:ship 权限」这一个信息。
 * （真要审计「谁发的货」，得先让过滤器能区分 user/admin token —— 那是独立的一步。）
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
     * 取消订单。
     *
     * <p>★ 用 {@code POST} 而不是 {@code PUT}/{@code PATCH}：
     * <ol>
     *   <li>本项目的写接口只有 {@code POST}（见本类与 CartController / AddressController）；</li>
     *   <li>{@code PUT} 的语义是<b>幂等</b>（同样的请求做多少次结果都一样），
     *       而取消<b>不幂等</b> —— 第二次调用会得到 {@code 400 订单状态不允许取消}。
     *       用 PUT 会让调用方误以为可以安全重试。</li>
     * </ol>
     *
     * <p>★ 返回 {@code Result<Void>}（data 为 null）：取消没有需要回传给前端的新对象，
     * 前端拿到 200 后重新拉一次详情即可。
     *
     * <p>★ 「只能取消自己的订单」由 Service 的归属分流保证：非本人订单返回 404，
     * 且与「订单不存在」的响应<b>逐字节相同</b>（不可区分）。
     */
    @Operation(summary = "取消订单（仅待支付可取消；非本人订单返回 404）")
    @PostMapping("/{id}/cancel")
    public Result<Void> cancel(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        orderService.cancel(userId, id);
        return Result.ok();
    }

    /**
     * ★★★ 发货（管理端动作）—— 本项目<b>第一个真正使用 RBAC 的业务端点</b>。
     *
     * <p>与上面三个 C 端接口的三处不同：
     * <ol>
     *   <li><b>挂 {@code @PreAuthorize}</b>：只有带 {@code order:ship} 权限的 token 能过。
     *       C 端 token 权限集为空 → <b>真 HTTP 403</b>；
     *       匿名 → <b>真 HTTP 401</b>（由 {@code anyRequest().authenticated()} +
     *       {@code AuthenticationEntryPoint} 在过滤器层拦下）。
     *       ★ 这两个响应<b>不经过</b> {@code @RestControllerAdvice}，所以是真实状态码，
     *       与业务异常的「HTTP 200 + body.code」不是一回事。</li>
     *   <li><b>不要 {@code Authentication} 参数</b>：发货不关心「谁发的」——
     *       见类注释里 principal 撞号那段。</li>
     *   <li>路径尾段是 {@code /ship}，与权限种子里的 URL 模式逐字符对应。</li>
     * </ol>
     *
     * <p>★ 返回 {@code Result<Void>}：发货没有新对象要回传。
     * 0 行（订单不存在 / 状态不是 PAID）统一由 Service 翻成
     * {@code 400 订单状态不允许发货}。
     */
    @Operation(summary = "发货（管理端，需 order:ship 权限；仅已支付订单可发货）")
    @PreAuthorize("hasAuthority('order:ship')")
    @PostMapping("/{id}/ship")
    public Result<Void> ship(@PathVariable Long id) {
        orderService.ship(id);
        return Result.ok();
    }

    /**
     * 确认收货（C 端动作）。
     *
     * <p>★ 与 {@code ship} 是<b>三处相反</b>的孪生：
     * <b>不挂</b> {@code @PreAuthorize}（C 端 token 权限集为空，一挂必 403）、
     * <b>要</b> {@code Authentication} 参数、Service 层<b>带 userId</b> 做归属分流。
     *
     * <p>★ 「只能确认自己的订单」由 Service 的归属分流保证：非本人订单返回 404，
     * 且与「订单不存在」的响应<b>逐字节相同</b>（不可区分）。
     *
     * <p>★ 用 {@code POST} 不用 {@code PUT}：确认收货<b>不幂等</b>，
     * 第二次调用会得到 {@code 400 订单状态不允许确认收货}。
     */
    @Operation(summary = "确认收货（仅已发货订单可确认；非本人订单返回 404）")
    @PostMapping("/{id}/confirm")
    public Result<Void> confirm(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        orderService.confirm(userId, id);
        return Result.ok();
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
