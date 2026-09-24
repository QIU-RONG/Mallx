package com.mallx.admin.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 编辑管理员（{@code PUT /api/admin/admins/{id}}，Day 23）。
 *
 * <p>只开两个字段，<b>不含 username / password</b>：
 * <ul>
 *   <li>{@code username} 是登录名 —— 改了会让本人下次登不进来，且它参与
 *       UNIQUE 约束，属于「账号重建」而非「编辑」；V1.0 不给改；</li>
 *   <li>改密码走独立的「重置密码」动作（本日<b>不做</b>，见 Day-23 文档 §九），
 *       与 §5.2 用户管理里「没有改用户密码」同一条取舍。</li>
 * </ul>
 *
 * <p>★ 两个字段都<b>可选</b>（null = 不改），但<b>不能都为空</b>：
 * 「两个都是 null」是一次没有语义的请求 ⇒ 实现侧要判并抛 400。
 * 这正是 {@code AdminAccountManageServiceImpl#update} 里那条
 * {@code if (dto.getNickname() == null && dto.getStatus() == null)} 存在的理由。
 *
 * <p>★ {@code status} 用 {@code Integer} 而非 {@code int}（同
 * {@code UserStatusUpdateDTO} 的注释）：{@code int} 的默认值 0 会把
 * 「不传」静默判成「禁用」。
 *
 * <p>⚠️ <b>护栏③ 落在这个 DTO 上</b>：{@code status = 0} 且目标是自己 → 实现侧必须 400
 * （「不许停用自己」）。见 Day-23 文档 §五。
 */
@Data
public class AdminUpdateDTO {

    /** 显示名；null = 不改 */
    @Size(max = 32, message = "昵称最长 32 字符")
    private String nickname;

    /** 1 = 启用，0 = 禁用；null = 不改。★ status=0 且目标是自己 → 400（护栏③） */
    @Min(value = 0, message = "status 只能是 0（禁用）或 1（启用）")
    @Max(value = 1, message = "status 只能是 0（禁用）或 1（启用）")
    private Integer status;
}
