package com.mallx.user.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 管理端改用户状态（{@code PUT /api/admin/users/{id}/status}）。
 *
 * <p>★ 只留 {@code status} 一个字段：这是<b>定点操作</b>，不是「编辑用户」——
 * 好处是即使将来加了 {@code UserUpdateDTO}，这个端点也不会意外改到别的列。
 *
 * <p>⚠️ 用 {@code Integer} 而非 {@code int}（同 {@code AdminProductController} 的
 * {@code status} 参数）：{@code int} 的默认值 {@code 0} 会把「不传」静默判成「禁用」。
 * 这里靠 {@code @NotNull} 把「不传」挡在 400，再用 {@code @Min/@Max} 把 0/1 之外的值挡掉。
 *
 * <p>★ <b>校验在前、授权在后</b>（{@code @Valid} 跑在 {@code @PreAuthorize} 之前）——
 * 所以断权限时必须给<b>合法载荷</b>，否则永远先撞 400、与有没有权限无关。
 */
@Data
public class UserStatusUpdateDTO {

    /** 1 = 启用，0 = 禁用 */
    @NotNull(message = "status 不能为空（1=启用 0=禁用）")
    @Min(value = 0, message = "status 只能是 0（禁用）或 1（启用）")
    @Max(value = 1, message = "status 只能是 0（禁用）或 1（启用）")
    private Integer status;
}
