package com.mallx.admin.vo;

import lombok.Data;

/**
 * 权限项（{@code GET /api/admin/permissions}，Day 23）—— <b>只读</b>字典。
 *
 * <p>★★ <b>为什么 permissions 只读、不给 CRUD</b>（Day-23 文档 §一 决策 1）：
 * 权限码是<b>代码资产</b> —— 每一行 {@code code} 都必须有一个 {@code @PreAuthorize}
 * 在引用它，否则就是一条<b>死权限</b>（造出来也没人能用到，只会让权限界面变脏）。
 * 而「哪个端点该配哪个码」这件事只有改代码才能决定 ⇒ 界面不该有这个能力。
 * 反过来说：本接口的存在意义是<b>给角色分配权限时能勾选</b>
 * （前端拿它渲染勾选框，配合 {@code PUT /api/admin/roles/{id}/permissions}），
 * <b>不是</b>给权限做客理。
 *
 * <p>★ 含 {@code status}：停止使用的权限（{@code status = 0}）也返回 ——
 * 同 {@link RoleVO} 的理由（管理端要能看见、才能决定是否启用）。
 * ⚠️ 但注意：{@code status = 0} 的权限<b>不会</b>被 {@code AdminAccountService}
 * 装进任何人的权限集合（{@code selectPermissionCodesByAdminId} 有
 * {@code AND p.status = 1}）。显示与生效是两件事，别把它们混在一个断言里。
 *
 * <p>★ {@code type} 是权限分类（种子里目前全是 {@code 'API'}）。
 * <p>★ 本类<b>不含</b> {@code parentId}：{@code permissions.parent_id} 列存在但
 * 全库为 NULL 且零代码读它 —— V1.0 明确不启用（Day-23 文档 §二② 写了理由：
 * 权限树是前端菜单元数据，与鉴权无关，{@code @PreAuthorize} 只认 {@code code}）。
 * 不把它放进 VO，是为了不让人误以为「已经有层级了」。
 */
@Data
public class PermissionVO {

    private Long id;

    private String name;

    /** 权限码，例 {@code role:assign-permission}；每个码必须有一个 {@code @PreAuthorize} 引用 */
    private String code;

    /** 分类，例 {@code API}（也预留给将来的 MENU / BUTTON） */
    private String type;

    /** 元数据：这个权限<span>意图</span>保护哪个路径（例 {@code /api/admin/roles/*}） */
    private String path;

    /** 元数据：HTTP 方法（例 {@code PUT}） */
    private String method;

    /** 1 = 生效，0 = 已停用（停用的权限不会被装进任何人的权限集合） */
    private Integer status;
}
