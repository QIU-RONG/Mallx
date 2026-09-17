package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

import java.math.BigDecimal;
import java.util.Map;

/**
 * 新建商品时随商品一起提交的一个 SKU。
 * <p>
 * 【为什么不让接口直接收 ProductSku 实体】
 * <ol>
 *   <li>实体里有 id / createdAt / updatedAt —— 都是数据库生成的，不该由客户端指定；</li>
 *   <li>实体是"表的样子"，DTO 是"接口契约的样子"，两者需求会分叉
 *       （客户端传 attributes 对象，表里存 jsonb）；</li>
 *   <li>productId 在新增场景下必须由服务端填（商品还没建出来，哪来的 id），
 *       实体里有这个字段就容易被误传。</li>
 * </ol>
 * 一句话：DTO 描述"客户端能给我什么"，实体描述"数据库里长什么样"，中间由 Service 负责翻译。
 * <p>
 * ⚠️ 本类里的约束注解只有在 {@code ProductCreateDTO} 的 {@code List<SkuCreateDTO>} 字段
 * 上写了 {@code @Valid} 时才会执行（级联校验），否则全部静默失效。
 */
@Data
public class SkuCreateDTO {

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
