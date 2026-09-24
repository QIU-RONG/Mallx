package com.mallx.product.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 修改品牌（Day 24 · L5②）—— 局部更新语义（类 PATCH）：没传的字段 = 不动。
 * <p>
 * ★ <b>为什么 name 上不挂 {@code @NotBlank}</b>（与 {@link CategoryUpdateDTO} /
 * {@code ProductUpdateDTO} 同一道理）：只想改 logo 时不该被迫带上名字。
 * 但「没传」（null）与「传了空串」（""）必须区分开 —— {@code @NotBlank}
 * 一视同仁地报错，分不清这两者，于是「只改 logo」会被 400 拦住。
 * ⇒ 长度用 {@code @Size}（管长度），空串的拦截挪到 Service 里显式做。
 * <p>
 * ⚠️ <b>本 DTO 也表达不了「把 logo / description 清空」</b>：null 一律按「不动」处理
 * （与 {@code CategoryUpdateDTO.parentId} 完全同一个取舍）。想清空只能传空串 ——
 * 空串对 {@code logo} / {@code description} 是「不动」还是「清空」，
 * 由 Service 显式决定，<b>不在 DTO 层猜</b>。
 * <p>
 * ★ {@code status} 在这里是<b>可选的</b>，但语义特殊：它只接受 0 / 1 两个值，
 * 且<ul>
 *   <li>传 0 = 停用（C 端字典里随即消失，管理端仍可见）；</li>
 *   <li>传 null = 不动（不是「停用」！）—— 这正是局部更新语义的价值：
 *       修 logo 不会顺手把品牌停掉。</li>
 * </ul>
 * 这也是本 DTO <b>不能</b>复用 {@code BrandCreateDTO} 的原因：创建时 status 缺省 = 1（启用），
 * 而更新时缺省 = 不动。同一个 null，两处含义相反。
 */
@Data
public class BrandUpdateDTO {

    @Size(max = 100, message = "品牌名称不能超过 100 字")
    private String name;

    @Size(max = 500, message = "品牌 logo 地址不能超过 500 字")
    private String logo;

    /** 品牌简介（TEXT，无长度上限） */
    private String description;

    /** 1 = 启用，0 = 停用；null = 不动（★ 不是「停用」） */
    @Min(value = 0, message = "status 只能是 0 或 1")
    @Max(value = 1, message = "status 只能是 0 或 1")
    private Integer status;
}
