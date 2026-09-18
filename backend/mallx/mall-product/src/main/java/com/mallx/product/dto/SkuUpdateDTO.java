package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

import java.math.BigDecimal;
import java.util.Map;

/**
 * 修改商品时随商品一起提交的一个 SKU。
 * <p>
 * 【与 {@link SkuCreateDTO} 的唯一区别：多一个 {@code id}】
 * <ul>
 *   <li>{@code id == null} → 这是个新 SKU，服务端执行 INSERT；</li>
 *   <li>{@code id != null} → 改库里已有的那一行，执行 UPDATE
 *       （★ Service 必须先校验它确实属于路径里的那个商品，否则是 IDOR 越权）。</li>
 * </ul>
 * 【为什么不直接复用 SkuCreateDTO】
 * 新增时 id 必须为 null（由服务端填），修改时 id 必须有值 ——
 * 两者对 id 的要求正好相反，一个类表达不了这两种契约。硬用会让人以为"新增也能传 id"。
 * <p>
 * ⚠️ 本类里的约束注解只有在 {@code ProductUpdateDTO} 的 {@code List<SkuUpdateDTO>} 字段
 * 上写了 {@code @Valid} 时才会执行（级联校验），否则全部静默失效。
 */
@Data
public class SkuUpdateDTO {

    /** null = 新增；有值 = 改库里那一行（★ 必须先校验它属于本商品） */
    private Long id;

    @NotBlank(message = "SKU 编码不能为空")
    private String skuCode;

    private String name;

    @NotNull(message = "SKU 价格不能为空")
    @Positive(message = "SKU 价格必须大于 0")
    private BigDecimal price;

    private BigDecimal originalPrice;

    /** 动态规格，落库是 jsonb，出参是 JSON 对象：{"color":"黑","storage":"128G"} */
    private Map<String, Object> attributes;

    private String image;

    private Integer status;
}
