package com.mallx.product.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

/**
 * 修改商品 —— 局部更新语义（类 PATCH）：没传的字段 = 不动。
 * <p>
 * 【为什么 name 上不再挂 @NotBlank】
 * 这个接口是"局部更新"：只改 status 而不传 name 是合法请求。
 * 而 @NotBlank 对 null 和空串一视同仁地报错，分不清"没传"和"传了空值"，
 * 于是"只想下架商品"会被 400 拦住。
 * 所以约束降级为 @Size（只管长度），空串的拦截挪到 Service 里显式做。
 * <p>
 * 【集合类字段的语义统一为三种】
 * <ul>
 *   <li>{@code null}（JSON 里根本不写这个 key）→ 不动</li>
 *   <li>空数组 {@code []} → 清空</li>
 *   <li>非空数组 → 以本次为准做对齐（新增 / 修改 / 软删）</li>
 * </ul>
 * 不能采用"严格 PUT 全量覆盖"：客户端发 {@code {"status":0}} 下架商品时没带 skus，
 * 全量覆盖就会把该商品的规格全部清空 —— 一次下架操作清空全部 SKU。
 */
@Data
public class ProductUpdateDTO {

    @Size(max = 100, message = "商品名称不能超过 100 字")
    private String name;

    private String subtitle;

    private String description;

    private String mainImage;

    /** 1=上架 0=下架 */
    private Integer status;

    /** 图集：null=不动，[]=清空，非空=按数组顺序重建 */
    private List<String> images;

    /**
     * SKU 列表：null=不动，[]=清空，非空=对齐。
     * <p>
     * ★ {@code @Valid} 必须写在字段上才会级联校验 {@link SkuUpdateDTO} 内部的约束，
     * 写到别处（方法参数、类上）都不生效，且静默失效、不报错。
     */
    @Valid
    private List<SkuUpdateDTO> skus;
}
