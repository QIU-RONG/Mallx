package com.mallx.inventory.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.inventory.dto.InventoryAdjustDTO;
import com.mallx.inventory.service.InventoryService;
import com.mallx.inventory.vo.InventoryLogVO;
import com.mallx.inventory.vo.InventoryVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端库存接口（Day 17）—— ★ 本模块的<b>第一个出口</b>。
 *
 * <p>★ 在本类出现之前，{@code mall-inventory} 是「服务层写好了但没出口」：
 * entity / mapper / service 三层齐全，一个 Controller 都没有 ——
 * 三个库存写点只能被其它模块（下单 / 支付 / 取消）调用。
 * 本类把第四个写点（人工调整）与两个只读视图接了出来。
 *
 * <p>★★ <b>为什么必须用 {@code /api/admin/**} 前缀</b>（与
 * {@code AdminOrderController} 同一条理由，这里再写一遍因为它更容易踩）：
 * {@code SecurityConfig} 的白名单里 {@code GET /api/products/**} 是<b>公开</b>的，
 * 而白名单<b>先匹配先赢</b>。库存接口天然容易挂到商品路径下
 * （比如「查商品库存」写成 {@code GET /api/products/{id}/stock}）——
 * 那样它会<b>静默变成匿名可访问</b>，{@code anyRequest().authenticated()} 根本轮不到。
 * <p>{@code /api/admin/**} 不在白名单里 → 默认要登录 → {@code @PreAuthorize} 再收紧到权限码。
 *
 * <p>★★ 三个方法<b>都必须挂 {@code @PreAuthorize}</b>：
 * {@code @EnableMethodSecurity} 已经打开，但<b>不挂注解就没有任何方法级检查</b>，
 * 而且不会有任何警告。漏挂的后果不是「多一个 403 的 bug」，
 * 而是<b>任何登录用户都能改全站库存</b> —— 这是本日最贵的一次失误。
 *
 * <p>★ 三个方法都<b>不接收 {@code Authentication}</b>：库存操作不需要知道「谁在操作」
 * （身份由权限码表达），而且 principal 在管理端与 C 端之间会撞号
 * （{@code JwtAuthenticationFilter} 只取 token 的 {@code sub}，无视 {@code type} claim）。
 * ⚠️ 因此本日的流水里<b>记不下「哪个管理员调的」</b>——
 * 这是已知缺口，已在规划里留档（要补得先让过滤器能区分两种 token）。
 *
 * <p>⚠️ 三种失败形态的同框（与订单侧一致，断言时必须分开写）：
 * <pre>
 *   匿名             → 真 HTTP 401
 *   登录但无权限     → 真 HTTP 403（★ 只有 inventory:* 的差异在这里体现）
 *   有权限但业务不成立 → HTTP 200 + body.code（如 400「调整后为负」）
 * </pre>
 */
@Tag(name = "管理端-库存")
@RestController
@RequestMapping("/api/admin/inventory")
public class AdminInventoryController {

    private final InventoryService inventoryService;

    public AdminInventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    /**
     * ★ 库存分页（四格数字 + SKU/商品名）。
     *
     * <p>骨架说明 —— 方法体只有一行：
     * <pre>
     *   return Result.ok(inventoryService.listSkus(page, size));
     * </pre>
     *
     * <p>⚠️ {@code page} / {@code size} 必须写 {@code defaultValue}
     * （不写的话不传参会 400）。
     * <p>★ 本接口<b>不需要任何过滤参数</b>：库存只有 7 行，
     * 而多一个可选条件就多一条「空串 vs null」的分支要测。
     */
    @Operation(summary = "管理端库存列表（分页，需 inventory:list 权限）")
    @PreAuthorize("hasAuthority('inventory:list')")
    @GetMapping("/skus")
    public Result<PageResult<InventoryVO>> listSkus(@RequestParam(defaultValue = "1") long page,
                                                    @RequestParam(defaultValue = "10") long size) {
        // TODO(你写): return Result.ok(inventoryService.listSkus(page, size));
        throw new UnsupportedOperationException("TODO: AdminInventoryController.listSkus");
    }

    /**
     * ★★★ 调整库存（★ 本日唯一的写端点，也是第四个库存写点）。
     *
     * <p>骨架说明 —— 方法体两行：
     * <pre>
     *   inventoryService.adjust(skuId, dto.getDelta(), dto.getReason());
     *   return Result.ok();
     * </pre>
     *
     * <p>★ {@code @RequestBody @Valid}：{@code @Valid} 放在<b>参数</b>上就能级联校验
     * {@code InventoryAdjustDTO} 内部的约束（{@code @NotNull} / {@code @NotBlank} / {@code @Size}）。
     * ⚠️ 若将来改成接收 {@code List<InventoryAdjustDTO>}，
     * {@code @Valid} 必须写到<b>字段/参数元素</b>上才级联 ——
     * 写在方法参数上对容器内部的元素<b>不生效</b>。
     *
     * <p>★ 业务校验 {@code delta != 0} <b>不在 DTO 上</b>，在 Service 里（理由见接口 Javadoc）。
     * <p>★ {@code reason} 本日只校验、不落库（流水表没有备注列）——
     * 显式取舍，见规划 §4.3。
     * <p>⚠️ 失败形态：{@code delta=0} → 400「调整量不能为 0」；
     * 调整后为负 → 400「调整后可用/总库存不能为负」；
     * SKU 不存在 → 同样是 400（0 行，守卫不成立）——
     * <b>本接口不区分「SKU 不存在」与「调成负的」</b>，两者都只是「这个调整不成立」。
     */
    @Operation(summary = "调整库存（delta 带符号：正=补货，负=报损；需 inventory:adjust 权限）")
    @PreAuthorize("hasAuthority('inventory:adjust')")
    @PostMapping("/skus/{skuId}/adjust")
    public Result<Void> adjust(@PathVariable Long skuId,
                              @RequestBody @Valid InventoryAdjustDTO dto) {
        // TODO(你写): inventoryService.adjust(skuId, dto.getDelta(), dto.getReason());
        //             return Result.ok();
        throw new UnsupportedOperationException("TODO: AdminInventoryController.adjust");
    }

    /**
     * ★ 库存流水分页（可按 {@code skuId} / {@code type} 过滤）。
     *
     * <p>骨架说明 —— 方法体只有一行：
     * <pre>
     *   return Result.ok(inventoryService.listLogs(skuId, type, page, size));
     * </pre>
     *
     * <p>★ 两个过滤参数都<b>可选</b>（不传 = 不筛）：
     * {@code skuId} 看某个 SKU 的来龙去脉；{@code type} 看某一类动作 ——
     * 只看 {@code ADMIN_ADJUST} 就是一份「人工调整审计」。
     * <p>⚠️ 它们同样是<b>筛选条件、不是权限边界</b>：能不能调只由那行 {@code @PreAuthorize} 决定。
     */
    @Operation(summary = "管理端库存流水（分页，可按 skuId / type 过滤；需 inventory:log 权限）")
    @PreAuthorize("hasAuthority('inventory:log')")
    @GetMapping("/logs")
    public Result<PageResult<InventoryLogVO>> listLogs(@RequestParam(required = false) Long skuId,
                                                       @RequestParam(required = false) String type,
                                                       @RequestParam(defaultValue = "1") long page,
                                                       @RequestParam(defaultValue = "10") long size) {
        // TODO(你写): return Result.ok(inventoryService.listLogs(skuId, type, page, size));
        throw new UnsupportedOperationException("TODO: AdminInventoryController.listLogs");
    }
}
