package com.mallx.user.controller;

import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.user.dto.UserStatusUpdateDTO;
import com.mallx.user.service.AdminUserService;
import com.mallx.user.vo.UserVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端用户管理（Day 22）。
 *
 * <p>【本类与 C 端 {@code UserController} 的关系：数据权限反转第三批】
 * <pre>
 *   C 端 /api/users/me          ：只有「我的资料 / 改我的昵称」，归属靠 Authentication 拿
 *   管理端 /api/admin/users     ：看全部 + 改状态，防线是权限码
 * </pre>
 *
 * <p>⚠️ <b>路径红线</b>：本类绝不能挂到 {@code /api/users/**} 上 —— 而且反过来，
 * {@code /api/users} 那个前缀本日<b>被收口了</b>：从前的 {@code GET /api/users}（全站列表）
 * 与 {@code GET /api/users/{id}}（任意人详情）已删除，因为它们既无归属过滤、
 * 又无 {@code @PreAuthorize}，实测能让任何登录用户拉走全站口令哈希
 * （详见 {@code day22-sec-probe.py} 的 16 条断言）。
 *
 * <p>★ <b>为什么放在 {@code mall-user} 模块而不是 {@code mall-admin}</b>：
 * 与 {@code AdminProductController} 放 mall-product、{@code AdminOrderController}
 * 放 mall-order、{@code AdminInventoryController} 放 mall-inventory <b>完全一致</b> ——
 * 「管理端」是<b>路径前缀 + 权限码</b>定义的语义，不是模块划分的依据。
 * 这样本类零 POM 改动（mall-user 已有的 UserMapper/UserService 就在手边）。
 *
 * <p>【分发权限的既定事实（{@code sql/12-day22-permissions.sql}）】<b>每个端点一个权限码</b>：
 * <ul>
 *   <li>{@code user:list}（id 8，已有）→ 超管 + 订单管理员；</li>
 *   <li>{@code user:detail}（id 22，新）→ 超管 + 订单管理员；</li>
 *   <li>{@code user:status}（id 23，新）→ <b>只给超管</b>（禁用账号是治理动作）。</li>
 * </ul>
 */
@Tag(name = "管理端-用户")
@RestController
@RequestMapping("/api/admin/users")
public class AdminUserController {

    private final AdminUserService adminUserService;

    public AdminUserController(AdminUserService adminUserService) {
        this.adminUserService = adminUserService;
    }

    /**
     * 用户分页（管理端：含已禁用）。
     *
     * @param status 可选：1=正常 0=已禁用；<b>不传 = 两者都要</b>
     *               ★ 用 {@code Integer} 而非 {@code int} —— 只有 null 才表达得出「不过滤」
     */
    @Operation(summary = "用户分页（管理端：含已禁用，keyword 匹配 username/nickname/phone）")
    @GetMapping
    @PreAuthorize("hasAuthority('user:list')")
    public Result<PageResult<UserVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status) {

        return Result.ok(PageResult.of(adminUserService.pageUsers(current, size, keyword, status)));
    }

    @Operation(summary = "用户详情（管理端：已禁用的也能看）")
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('user:detail')")
    public Result<UserVO> detail(@PathVariable Long id) {
        return Result.ok(adminUserService.getDetail(id));
    }

    /**
     * 改用户状态。
     * <p>
     * ★ 用 {@code PUT /{id}/status} 而不是 {@code PUT /{id}}：与 {@code AdminProductController}
     * 的做法刻意<b>相反</b> —— 商品那边「编辑」的语义本来就包含上下架，所以并进 PUT 全字段；
     * 而用户这里<b>没有</b>「编辑用户」这个需求（§5.2 只要列表/详情/状态），
     * 所以只开一个定点端点，避免将来出现「改状态时顺手把昵称也覆盖了」。
     */
    @Operation(summary = "改用户状态（1=启用 0=禁用）")
    @PutMapping("/{id}/status")
    @PreAuthorize("hasAuthority('user:status')")
    public Result<Void> updateStatus(@PathVariable Long id,
                                     @RequestBody @Valid UserStatusUpdateDTO dto) {
        // ★ void 方法必须拆成「调用一句 + return Result.ok()」两句 ——
        //   Java 不允许把 void 方法的调用当实参（同 AdminProductController 的注释）。
        adminUserService.updateStatus(id, dto.getStatus());
        return Result.ok();
    }
}
