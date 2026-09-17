package com.mallx.product.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Data
public class ProductCreateDTO {
    @NotNull(message = "分类不能为null")
    private Long categoryId;
    private Long brandId;

    @NotBlank(message = "名称不能为空")
    @Size(max = 100,message = "商品名称不能超过100字")
    private String name;

    @Size(max = 200,message = "副标题不能超过200字")
    private String subtitle;

    private String description;

    private String mainImage;

    private Integer status;

    // ---------------- 以下为 Day 08 新增 ----------------

    /** 商品图集（按数组顺序入库为 sort_order）。可为空 —— 兼容 Day 07 的老请求体 */
    private List<String> images;

    /**
     * SKU 列表。可为空。
     * <p>
     * ⚠️ 字段上的 {@code @Valid} 是<b>级联校验</b>的开关：没有它，SkuCreateDTO 里的
     * {@code @NotBlank}/{@code @Positive} 全部不会执行，等于白写。
     * <p>
     * 与 Controller 参数上的 {@code @Valid} 分工不同：
     * 参数上的管"这个 DTO 自己的字段"，字段上的管"集合里每个元素"的字段。
     */
    @Valid
    private List<SkuCreateDTO> skus;
}
