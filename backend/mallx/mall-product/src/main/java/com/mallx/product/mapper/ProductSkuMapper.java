package com.mallx.product.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.product.entity.ProductSku;
import com.mallx.product.vo.ProductPriceRangeVO;
import org.apache.ibatis.annotations.Param;

import java.util.Collection;
import java.util.List;

public interface ProductSkuMapper extends BaseMapper<ProductSku> {

    /**
     * ★ 批量取「一页商品」各自的价格区间（Day 48）。
     *
     * <p><b>为什么必须是批量 + 聚合，而不是循环里逐个查</b>：
     * 列表一页 12 条 —— 逐条查就是 12 次往返（典型的 N+1）。
     * 这里是<b>一次</b> GROUP BY 拿回整页，与 {@code fillNames} 的手法一致。
     *
     * <p><b>为什么手写 XML 而不是 MP 的 wrapper</b>：{@code MIN/MAX + GROUP BY}
     * 是聚合查询，{@code LambdaQueryWrapper} 表达不了。
     *
     * <p>★★ <b>过滤条件用 {@code is_deleted = 0 AND status = 1}，且必须自己写在 SQL 里</b>：
     * <ul>
     *   <li>手写 SQL <b>不受</b> {@code @TableLogic} 管 —— 少写 {@code is_deleted = 0}
     *       会把已删的 SKU 价格算进来（可能比原价还低，直接误导用户）；</li>
     *   <li>{@code status = 1}（在售）同理：把已停售的 SKU 算进去，
     *       列表上会显示一个<b>买不到的价格</b>。</li>
     * </ul>
     * 这两条都不会报错，只会安静地显示错数字。
     *
     * @param productIds 本页出现过的商品 id（调用方保证非空 —— 空集合会拼出
     *                   {@code IN ()} 语法错，所以由调用方先挡）
     * @return 每个商品一行；<b>没有任何在售 SKU 的商品不会出现在结果里</b>
     *         ⇒ 调用方要按「查不到就是 null」处理，不能假定每条都能配上
     */
    List<ProductPriceRangeVO> selectPriceRange(@Param("productIds") Collection<Long> productIds);
}
