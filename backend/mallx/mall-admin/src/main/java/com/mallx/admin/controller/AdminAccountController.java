package com.mallx.admin.controller;

import com.mallx.admin.dto.AdminCreateDTO;
import com.mallx.admin.dto.AdminUpdateDTO;
import com.mallx.admin.dto.AssignRolesDTO;
import com.mallx.admin.service.AdminAccountManageService;
import com.mallx.admin.vo.AdminDetailVO;
import com.mallx.admin.vo.AdminVO;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 管理端 - 管理员账号（Day 23，§5.6 RBAC 第一块）。
 *
 * <p>★ <b>路径红线</b>：全部落在 {@code /api/admin/admins} ——
 * 管理端<b>本来就不在白名单里</b>（白名单只有两个 login + {@code /error} +
 * springdoc + C 端几个 GET）⇒ 什么都不用改。
 * ⚠️ 若为图省事往白名单加一条 {@code /api/admin/**}，等于把整个管理端
 * <b>静默公开</b>（Day 20 的 {@code /api/coupons} 就是这个坑）。
 *
 * <p>★★ <b>六个端点的权限码全部只发给 SUPER_ADMIN</b>（{@code 13-day23-permissions.sql}）。
 * 理由不是「超管本来就什么都有」，而是一条硬性推理：
 * {@code admin:create} + {@code admin:assign-role} 合起来 = <b>造一个新超管账号</b>；
 * {@code admin:delete} / {@code admin:update} 能删掉或停用别人。
 * ⇒ 这几条码<b>漏给任何一个非超管角色，管理端的门就形同虚设</b>。
 *
 * <p>★ <b>「当前操作人」怎么取</b>：{@code (Long) authentication.getPrincipal()} ——
 * 与 C 端<b>完全同一写法</b>，因为过滤器（{@code JwtAuthenticationFilter}）对两个端
 * 用同一段代码登记身份，{@code type} claim（{@code ADMIN} / {@code USER}）只区分
 * <b>签发来源</b>，不影响 principal 的类型。
 * <p>★ 这个 id 只用于<b>护栏③</b>（不许对自己执行破坏性操作），<b>不</b>用于归属过滤
 * ——管理端看的是全部数据，防线是权限码。
 */
@Tag(name = "管理端-管理员账号")
@RestController
@RequestMapping("/api/admin/admins")
public class AdminAccountController {

    private final AdminAccountManageService adminAccountManageService;

    public AdminAccountController(AdminAccountManageService adminAccountManageService) {
        this.adminAccountManageService = adminAccountManageService;
    }

    /**
     * 管理员分页。
     *
     * @param status 可选：1=启用 0=已禁用；<b>不传 = 两者都要</b>
     *               ★ 用 {@code Integer} 而非 {@code int} —— 只有 null 能表达「不过滤」
     *               （同 Day 22 {@code AdminUserController#page}）。
     */
    @Operation(summary = "管理员分页（含已禁用，keyword 匹配 username/nickname）")
    @GetMapping
    @PreAuthorize("hasAuthority('admin:list')")
    public Result<PageResult<AdminVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status) {

        return Result.ok(PageResult.of(adminAccountManageService.pageAdmins(current, size, keyword, status)));
    }

    /**
     * 管理员详情（含角色）。
     * <p>★ 响应里<b>没有</b> {@code password} 键 —— 这一点由验收 D/B 组按「键不存在」断言
     * （不是 {@code "password": null}）。
     */
    @Operation(summary = "管理员详情（含角色 id 与角色码；不含 password）")
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('admin:detail')")
    public Result<AdminDetailVO> detail(@PathVariable Long id) {
        return Result.ok(adminAccountManageService.getDetail(id));
    }

    /**
     * 新建管理员。
     * <p>★ 密码在 Service 里走 {@code PasswordEncoder.encode()}；
     * ★ {@code username} 撞 UNIQUE → <b>400</b>（不是 500）。
     */
    @Operation(summary = "新建管理员（密码走 BCrypt 编码；用户名重复返回 400）")
    @PostMapping
    @PreAuthorize("hasAuthority('admin:create')")
    public Result<Long> create(@RequestBody @Valid AdminCreateDTO dto) {
        return Result.ok(adminAccountManageService.create(dto));
    }

    /**
     * 编辑管理员（昵称 / 状态）。
     * <p>★ <b>护栏③</b>：不许把自己停用（Service 里判，需要 currentAdminId）。
     */
    @Operation(summary = "编辑管理员（昵称/状态；不许停用自己）")
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('admin:update')")
    public Result<Void> update(@PathVariable Long id,
                               @RequestBody @Valid AdminUpdateDTO dto,
                               Authentication authentication) {
        // ★ void 方法必须拆成「调用一句 + return Result.ok()」两句 ——
        //   Java 不允许把 void 方法的调用当实参（同 AdminUserController 的注释）。
        adminAccountManageService.update(id, dto, (Long) authentication.getPrincipal());
        return Result.ok();
    }

    /**
     * 物理删除管理员（含先清 {@code admin_roles}）。
     * <p>★ <b>护栏③</b>：不许删自己。
     */
    @Operation(summary = "删除管理员（物理删，含清理角色关联；不许删自己）")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('admin:delete')")
    public Result<Void> delete(@PathVariable Long id, Authentication authentication) {
        adminAccountManageService.delete(id, (Long) authentication.getPrincipal());
        return Result.ok();
    }

    /**
     * 给管理员<b>全量替换</b>角色。
     * <p>★ 用 {@code PUT /{id}/roles}（子资源整体替换）而不是 {@code POST /{id}/roles}
     * （追加）—— 界面上是多选框，提交的是<b>结果集合</b>而不是增量。
     * <p>★ <b>护栏③</b>：不许清空自己的角色（空集合 + 目标是自己 ⇒ 400）。
     */
    @Operation(summary = "给管理员分配角色（全量替换；不许清空自己的角色）")
    @PutMapping("/{id}/roles")
    @PreAuthorize("hasAuthority('admin:assign-role')")
    public Result<Void> assignRoles(@PathVariable Long id,
                                    @RequestBody @Valid AssignRolesDTO dto,
                                    Authentication authentication) {
        adminAccountManageService.assignRoles(id, dto.getRoleIds(), (Long) authentication.getPrincipal());
        return Result.ok();
    }
}
