package com.mallx.admin.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.util.List;

/**
 * 给管理员分配角色（{@code PUT /api/admin/admins/{id}/roles}，Day 23）。
 *
 * <p>★★ <b>「空数组」与「null」的语义必须分开</b>（本项目的成文规矩，Day-23 文档 §八 坑 5）：
 * <table border="1">
 *   <tr><th>请求体</th><th>语义</th><th>结果</th></tr>
 *   <tr><td>{@code {"roleIds": []}}</td><td>显式清空（这个人不再有任何角色）</td><td>200</td></tr>
 *   <tr><td>{@code {}}</td><td>没有表达任何意图</td><td><b>400</b>（被 {@code @NotNull} 挡下）</td></tr>
 * </table>
 * ★ 若不加 {@code @NotNull}，「前端漏传了这个字段」会被实现侧当成 {@code []} 处理
 * ⇒ <b>静默把人的角色清空</b>。这与 Day 22 里「{@code size<0} 查全表」是同一族事故：
 * 一个缺省的入参被解释成了最激进的动作。把 null 挡在 400 是唯一的结构性解法。
 *
 * <p>★ 这是<b>全量替换</b>语义（不是「追加」）：实现侧 `DELETE` 该管理员的全部
 * {@code admin_roles} 再批量 `INSERT`。理由：追加式接口无法表达「取消某个角色」，
 * 而界面上就是一个多选框 —— 多选框提交的是<b>结果集合</b>，不是增量。
 * <p>⚠️ DELETE + INSERT 是<b>两条语句</b> ⇒ 按 {@code InventoryService:119} 的判据
 * 必须 {@code @Transactional}（否则事务中间有一瞬「无角色」窗口）。
 */
@Data
public class AssignRolesDTO {

    /**
     * 目标角色 id 集合。
     * <p>★ 空数组 = 清空；null = 400。
     * <p>★ 传了不存在的 id → 实现侧必须 <b>400</b> 而不是让 FK 抛 23503 变 500
     * （预校验 {@code SELECT count(*)}，而不是靠异常做控制流）。
     */
    @NotNull(message = "roleIds 不能为空（清空请传空数组 []，而不是省略该字段）")
    private List<Long> roleIds;
}
