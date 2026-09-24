package com.mallx.admin.controller;

import com.mallx.admin.dto.AssignPermissionsDTO;
import com.mallx.admin.dto.RoleCreateDTO;
import com.mallx.admin.dto.RoleUpdateDTO;
import com.mallx.admin.service.RoleManageService;
import com.mallx.admin.vo.RoleDetailVO;
import com.mallx.admin.vo.RoleVO;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
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
 * 管理端 - 角色（Day 23，§5.6 RBAC 第二块）。
 *
 * <p>★★ <b>本类是护栏①② 的对外出口</b>：
 * ① 不许删 / 停用 {@code SUPER_ADMIN} 角色；
 * ② 不许减少 {@code SUPER_ADMIN} 角色的权限（只许增）。
 * 两条都在 Service 实现里落，本层的职责是<b>给出准确的权限码</b>
 * （六个端点六个码，全部只发超管）。
 *
 * <p>★ 为什么 {@code status} 并进 {@code PUT /{id}} 而<b>不</b>单开 {@code role:status}
 * （与 Day 22 给 {@code user:status} 单开一码的做法<b>不同</b>）：
 * {@code user:status} 单开是因为「订单管理员能看用户、但不该禁用」——
 * 存在<b>两个人需要不同粒度</b>的真实需求；
 * 而本日这三域的 13 条码<b>全部只发给超管</b>，没有第二个角色需要区分粒度
 * ⇒ 再拆一码是纯粹的码数量膨胀。
 * ⚠️ 这类「与既有做法不一致」的地方必须诚实写下来，别让后来者以为是漏了。
 *
 * <p>★ 本类<b>不需要</b> {@code Authentication}：角色是全局资产，
 * 不存在「我的角色」；护栏①② 保护的是角色本身，与「谁在操作」无关。
 */
@Tag(name = "管理端-角色")
@RestController
@RequestMapping("/api/admin/roles")
public class AdminRoleController {

    private final RoleManageService roleManageService;

    public AdminRoleController(RoleManageService roleManageService) {
        this.roleManageService = roleManageService;
    }

    @Operation(summary = "角色分页（含已停用，keyword 匹配 name/code）")
    @GetMapping
    @PreAuthorize("hasAuthority('role:list')")
    public Result<PageResult<RoleVO>> page(
            @RequestParam(defaultValue = "1") long current,
            @RequestParam(defaultValue = "10") long size,
            @RequestParam(required = false) String keyword) {

        return Result.ok(PageResult.of(roleManageService.pageRoles(current, size, keyword)));
    }

    /** 角色详情（含 permissionIds + permissionCodes —— 护栏② 的「现有集合」就从这里读）。 */
    @Operation(summary = "角色详情（含权限 id 与权限码）")
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('role:detail')")
    public Result<RoleDetailVO> detail(@PathVariable Long id) {
        return Result.ok(roleManageService.getDetail(id));
    }

    /** 新建角色（{@code code} 撞 UNIQUE → 400）。 */
    @Operation(summary = "新建角色（code 重复返回 400）")
    @PostMapping
    @PreAuthorize("hasAuthority('role:create')")
    public Result<Long> create(@RequestBody @Valid RoleCreateDTO dto) {
        return Result.ok(roleManageService.create(dto));
    }

    /**
     * 编辑角色（名称 / 说明 / 状态）。
     * <p>★ <b>护栏①</b>：不许停用 {@code SUPER_ADMIN}。
     * <p>★ 不能改 {@code code}（{@code RoleUpdateDTO} 就没给这个字段）——
     * 它已经以 {@code ROLE_xxx} 的形式签进了所有存量 token（路线①）。
     */
    @Operation(summary = "编辑角色（名称/说明/状态；不许停用 SUPER_ADMIN）")
    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('role:update')")
    public Result<Void> update(@PathVariable Long id,
                               @RequestBody @Valid RoleUpdateDTO dto) {
        roleManageService.update(id, dto);
        return Result.ok();
    }

    /**
     * 删除角色。
     * <p>★ <b>护栏①</b>：不许删 {@code SUPER_ADMIN}。
     * <p>★ Service 里会先清 {@code role_permissions} 与 {@code admin_roles}
     * （FK 是 NO ACTION，不清就 23503）。
     */
    @Operation(summary = "删除角色（含清理权限与账号关联；不许删 SUPER_ADMIN）")
    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('role:delete')")
    public Result<Void> delete(@PathVariable Long id) {
        roleManageService.delete(id);
        return Result.ok();
    }

    /**
     * 给角色<b>全量替换</b>权限。
     * <p>★ <b>护栏②</b>：若目标是 {@code SUPER_ADMIN}，目标集合必须<b>包含</b>现有集合
     * （只许增、不许减），否则 400。
     * <p>⚠️ 操作的是 {@code role_permissions} <b>关联表</b>，
     * <b>不是</b> {@code permissions} 表 —— 权限码本身只读（没有 CRUD 接口）。
     */
    @Operation(summary = "给角色分配权限（全量替换；SUPER_ADMIN 只许增不许减）")
    @PutMapping("/{id}/permissions")
    @PreAuthorize("hasAuthority('role:assign-permission')")
    public Result<Void> assignPermissions(@PathVariable Long id,
                                          @RequestBody @Valid AssignPermissionsDTO dto) {
        roleManageService.assignPermissions(id, dto.getPermissionIds());
        return Result.ok();
    }
}
