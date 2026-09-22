package com.mallx.order.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.order.service.OrderService;
import com.mallx.order.vo.AdminOrderVO;
import com.mallx.order.vo.OrderDetailVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端订单接口（Day 17）—— ★ 本项目<b>第一批「数据权限反转」的接口</b>。
 *
 * <p>★★ 为什么是独立的一个 Controller，而不是往 {@link OrderController} 里塞三个方法：
 * <ol>
 *   <li><b>路径前缀不同</b>：这里全部在 {@code /api/admin/**} 下，
 *       而 {@code OrderController} 挂在 {@code /api/orders}。
 *       两个 {@code @RequestMapping} 无法共存于一个类；</li>
 *   <li><b>鉴权模型整体不同</b>：{@code OrderController} 里 6 个 C 端端点
 *       <b>一个都不挂</b> {@code @PreAuthorize}（C 端 token 权限集为空，一挂必 403），
 *       只有 {@code ship} 例外；而本类的<b>每一个方法都必须挂</b>。
 *       把「多数不挂、个别挂」和「全部都挂」放进一个类，
 *       下一个人很容易照着邻居的方法抄出一个不带注解的端点。</li>
 * </ol>
 *
 * <p>★★ <b>为什么必须用 {@code /api/admin/**} 这个前缀</b>（本类是这条规则的第一个示范）：
 * {@code SecurityConfig} 的白名单里有一条
 * {@code .requestMatchers(HttpMethod.GET, "/api/products/**", "/api/categories/**").permitAll()}。
 * 白名单是<b>先匹配先赢</b>的 —— 若管理端接口图省事挂在 {@code /api/products/...} 下
 * （比如「查商品库存」写成 {@code GET /api/products/{id}/stock}），
 * 它会<b>静默变成匿名可访问</b>，{@code anyRequest().authenticated()} 根本轮不到。
 * <p>{@code /api/admin/**} 不在白名单里 → 默认要登录 → {@code @PreAuthorize} 再收紧到权限码。
 * <b>两级都到位。</b>
 *
 * <p>★★ 三个方法<b>都必须挂 {@code @PreAuthorize}</b>（本类最要紧的一条纪律）：
 * {@code SecurityConfig} 上的 {@code @EnableMethodSecurity} 已经打开，
 * 但<b>不挂注解就没有任何方法级检查，且不会有任何警告</b>。
 * 漏挂一个的直接后果：那个接口从「只有管理员能用」退化成「<b>任何登录用户</b>都能用」——
 * C 端 {@code demo} 的 token 权限集为空，照样能拉到全站订单。
 * 所以 §5.1 的权限矩阵是本日<b>压在最前面</b>的一组验收。
 *
 * <p>★ 三个方法<b>都不接收 {@code Authentication} 参数</b>：
 * 管理端订单接口不需要知道「当前用户是谁」（权限码已经说明了身份），
 * 而且 {@code JwtAuthenticationFilter} 只把 token 的 {@code sub} 转成 {@code Long} 当 principal，
 * <b>完全无视</b> token 里的 {@code type:"ADMIN"} claim ——
 * 管理端 admin 与 C 端 demo 的 {@code sub} 都可能是 {@code "1"}，两者principal
 * <b>数值相同、类型相同、无法区分</b>。真要审计「谁取消的」，得先让过滤器能区分两种 token，
 * 那是独立的一步。
 *
 * <p>⚠️ 三种失败形态在这里第一次同框，断言时必须分开写：
 * <pre>
 *   匿名（不带头）        → 真 HTTP 401（AuthenticationEntryPoint，过滤器层）
 *   登录但无权限（C 端）  → 真 HTTP 403（AccessDeniedHandler）
 *   有权限但业务不成立    → HTTP 200 + body.code（GlobalExceptionHandler）
 * </pre>
 * 前两者<b>不经过</b> {@code @RestControllerAdvice}，所以是真实状态码；
 * 只有第三种才是本项目「HTTP 一律 200、判成功看 code」的常规约定。
 */
@Tag(name = "管理端-订单")
@RestController
@RequestMapping("/api/admin/orders")
public class AdminOrderController {

    private final OrderService orderService;

    public AdminOrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    /**
     * ★★★ 全站订单分页（★ 本日第一个数据权限反转的端点）。
     *
     * <p>骨架说明 —— 方法体只有一行：
     * <pre>
     *   return Result.ok(orderService.listAllOrders(status, userId, page, size));
     * </pre>
     *
     * <p>★ 两个过滤参数<b>都是可选的筛选条件</b>（不传 = 不筛），
     * ⚠️ 但它们<b>不是</b>权限边界：能不能调这个接口只由上面那行 {@code @PreAuthorize} 决定。
     * 「加了 userId 就只能看某个人的单」是<b>筛选</b>，不是「没加 userId 就能看全部」的授权 ——
     * 授权与筛选是两件事，混一起就会出现「不传 userId 等于超级权限」这种设计事故。
     *
     * <p>⚠️ {@code page} / {@code size} 必须写 {@code defaultValue}：
     * 不写的话，不传参时 Spring 对基本类型 {@code long} 会直接抛异常（400）。
     */
    @Operation(summary = "管理端订单列表（全站分页，需 order:list 权限）")
    @PreAuthorize("hasAuthority('order:list')")
    @GetMapping
    public Result<PageResult<AdminOrderVO>> list(@RequestParam(required = false) String status,
                                                 @RequestParam(required = false) Long userId,
                                                 @RequestParam(defaultValue = "1") long page,
                                                 @RequestParam(defaultValue = "10") long size) {
        return Result.ok(orderService.listAllOrders(status, userId, page, size));
    }

    /**
     * ★★ 任意订单详情（★ 不做归属分流）。
     *
     * <p>骨架说明 —— 方法体只有一行：
     * <pre>
     *   return Result.ok(orderService.detailByAdmin(id));
     * </pre>
     *
     * <p>★ 「不存在」→ 业务 404（HTTP 200 + code=404）；
     * 路径变量是 {@code Long}，所以传 {@code /api/admin/orders/abc} 会被
     * {@code MethodArgumentTypeMismatchException} 转成 200 + code=400「参数 id 格式不正确」。
     * ⚠️ 这两条与权限无关 —— 无权限的请求在<b>过滤器层</b>就被 403 挡下了，
     * 根本走不到这个方法的参数解析。
     */
    @Operation(summary = "管理端订单详情（任意订单，需 order:detail 权限）")
    @PreAuthorize("hasAuthority('order:detail')")
    @GetMapping("/{id}")
    public Result<OrderDetailVO> detail(@PathVariable Long id) {
        return Result.ok(orderService.detailByAdmin(id));
    }

    /**
     * ★★★ 取消订单（管理端动作，★ 仅待支付；复用用户取消那条回补链路）。
     *
     * <p>骨架说明 —— 方法体两行：
     * <pre>
     *   orderService.cancelByAdmin(id);
     *   return Result.ok();
     * </pre>
     *
     * <p>★ 用 {@code POST} 不用 {@code PUT}：与 C 端取消同一个理由 ——
     * 取消<b>不幂等</b>（第二次会得到 400），而 {@code PUT} 的语义是幂等，
     * 会让调用方误以为可以安全重试。
     *
     * <p>★ 返回 {@code Result<Void>}：取消没有需要回传的新对象，前端拿到 200 重新拉列表即可。
     *
     * <p>⚠️ <b>不接收 {@code Authentication}</b>，也<b>不校验归属</b> ——
     * 管理端取消的是「任何人的待支付单」。这条能力的边界完全由
     * {@code @PreAuthorize("hasAuthority('order:cancel')")} 表达。
     * ⚠️ <b>本端点不能取消已支付订单</b>（那是退款，属售后域）：
     * PAID 单会被 Service 的 CAS 挡成 400。
     */
    @Operation(summary = "管理端取消订单（仅待支付，需 order:cancel 权限）")
    @PreAuthorize("hasAuthority('order:cancel')")
    @PostMapping("/{id}/cancel")
    public Result<Void> cancel(@PathVariable Long id) {
        // TODO(你写): orderService.cancelByAdmin(id); return Result.ok();
        throw new UnsupportedOperationException("TODO: AdminOrderController.cancel");
    }
}
