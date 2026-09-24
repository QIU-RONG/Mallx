package com.mallx.admin.service;

import com.mallx.admin.vo.PermissionVO;

import java.util.List;

/**
 * 权限<b>只读</b>查询（Day 23，§5.6 RBAC）。
 *
 * <p>★★ <b>本接口刻意只有一个只读方法 —— 这不是「还没做」，是决策。</b>
 * （Day-23 文档 §一 决策 1）权限码是<b>代码资产</b>：每一行 {@code code} 都必须有
 * 一个 {@code @PreAuthorize} 在引用它。界面造出来的码没有对应端点 ⇒ <b>死权限</b>
 * （造出来也没人能用到，只会让权限界面变脏、让后来者以为「这功能还没接上」）。
 * 而「哪个端点配哪个码」只有改代码才能决定 ⇒ 界面不该有这个能力。
 *
 * <p>★ 那这个接口存在的意义是什么：<b>给角色分配权限时能勾选</b>
 * （前端拿它渲染勾选框，配合 {@code PUT /api/admin/roles/{id}/permissions}）。
 * ⇒ 所以它是<b>字典式</b>接口，<b>不分页</b>
 * （参照 L5① 的 {@code GET /api/admin/brands}：字典要一次给全，分页反而难用）。
 * <p>⚠️ 全表目前 38 行（8 条种子 + 05/07/08/10/12 补发 17 条 + 本日 13 条），
 * 一次返回毫无压力。★ 若将来权限过千，本接口要改回分页，
 * <b>并且同步改验收断言</b>（断言里写了「不分页」这条性质）。
 */
public interface PermissionQueryService {

    /**
     * 权限字典（含已停用）。
     *
     * @param type    可选；按分类过滤（种子里目前全是 {@code API}）。null / 空串 = 不过滤
     * @param keyword 可选；匹配 {@code name} 或 {@code code}。null / 空串 = 不过滤
     * @return 按 {@code id} 升序的全部权限（★ 不分页）
     *         <p>⚠️ 含 {@code status = 0} 的权限：管理端要能看见（同 {@code RoleVO} 的理由）。
     *         但显示与生效是两件事 —— {@code status = 0} 的权限<b>不会</b>被
     *         {@code AdminAccountService} 装进任何人的权限集合。
     */
    List<PermissionVO> list(String type, String keyword);
}
