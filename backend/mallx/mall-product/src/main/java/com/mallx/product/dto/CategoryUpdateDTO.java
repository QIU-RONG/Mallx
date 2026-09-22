package com.mallx.product.dto;

import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 修改分类（Day 18）—— 局部更新语义（类 PATCH）：没传的字段 = 不动。
 * <p>
 * ★ <b>为什么 name 上不挂 {@code @NotBlank}</b>（与 {@link ProductUpdateDTO} 同一道理）：
 * 只想改排序时不该被迫带上名字。但「没传」（null）与「传了空串」（""）必须区分开 ——
 * {@code @NotBlank} 一视同仁地报错，分不清这两者，于是「只改 sort_order」会被 400 拦住。
 * ⇒ 长度用 {@code @Size}（管长度），空串的拦截挪到 Service 里显式做。
 * <p>
 * ⚠️ {@code parentId} 传 null 有两种可能的语义冲突：「没传这个字段」与「改成顶级分类」。
 * 本 DTO 用 {@code @Data} 的包装类型 {@code Long} 表达，二者在 JSON 上是同一个东西（都是 null）
 * ⇒ <b>本日约定：{@code parentId == null} 一律按「不动」处理</b>（保守取值），
 * 想改成顶级分类只能删掉重建。这是有意识的简化，不是漏写 ——
 * 真要做「置空」语义，得引入 {@code Optional} 包装或另开一个端点。
 */
@Data
public class CategoryUpdateDTO {

    /** 父分类 id；本日约定 null = 不动（见类注释的取舍说明） */
    private Long parentId;

    @Size(max = 100, message = "分类名称不能超过 100 字")
    private String name;

    /** 排序值，越小越靠前 */
    private Integer sortOrder;
}
