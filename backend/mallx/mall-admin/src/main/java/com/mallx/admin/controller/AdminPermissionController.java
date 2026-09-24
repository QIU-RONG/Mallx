package com.mallx.admin.controller;

import com.mallx.admin.service.PermissionQueryService;
import com.mallx.admin.vo.PermissionVO;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 管理端 - 权限字典（Day 23，§5.6 RBAC 第三块）—— <b>只有 GET</b>。
 *
 * <p>★★ <b>本类只有一个方法，这是决策的结果而不是「还没做完」。</b>
 * 权限码是<b>代码资产</b>：每一行 {@code code} 都必须有一个 {@code @PreAuthorize}
 * 在引用它。界面造出来的码没有对应端点 ⇒ <b>死权限</b>（造出来也没人能用到，
 * 只会让权限界面变脏）。而「哪个端点配哪个码」只有改代码才能决定。
 * ⇒ 所以 {@code permissions} 表<b>没有</b> POST / PUT / DELETE。
 * <p>★ 这个决定的反面就是验收 F 组要断言的：
 * 对本路径打 POST / PUT / DELETE 必须得到 <b>405</b>（不是 404、不是 500）——
 * 「路径在、方法不支持」才是「只读」的准确表达，405 与 404 的区别见
 * {@code GlobalExceptionHandler#handleMethodNotSupported} 的注释。
 *
 * <p>★ 那这个接口存在的意义：<b>给角色分配权限时能勾选</b>
 * —— 前端拿它渲染勾选框，配合 {@code PUT /api/admin/roles/{id}/permissions}。
 * ⇒ 它是<b>字典式</b>接口，<b>不分页</b>（参照 L5① 的 {@code GET /api/admin/brands}：
 * 字典要一次给全，分页反而难用）。
 * ⚠️ 全表目前 38 行。★ 若将来权限过千，本接口要改回分页，
 * <b>并且同步改验收断言</b>（F 组断言了「返回条数 == 全表行数」这条性质）。
 */
@Tag(name = "管理端-权限字典")
@RestController
@RequestMapping("/api/admin/permissions")
public class AdminPermissionController {

    private final PermissionQueryService permissionQueryService;

    public AdminPermissionController(PermissionQueryService permissionQueryService) {
        this.permissionQueryService = permissionQueryService;
    }

    /**
     * 权限字典（不分页，含已停用）。
     *
     * @param type    可选：按分类过滤（目前全是 {@code API}）
     * @param keyword 可选：匹配 {@code name} 或 {@code code}
     *                ★ 两个参数都用 {@code required = false} + 实现侧判空，
     *                而不是 {@code defaultValue = ""} —— 因为「不传」与「传空串」
     *                在实现侧是同一个处理（都不过滤），没必要在签名上做区分。
     */
    @Operation(summary = "权限字典（不分页；给角色分配权限时用于渲染勾选框）")
    @GetMapping
    @PreAuthorize("hasAuthority('permission:list')")
    public Result<List<PermissionVO>> list(@RequestParam(required = false) String type,
                                           @RequestParam(required = false) String keyword) {
        return Result.ok(permissionQueryService.list(type, keyword));
    }
}
