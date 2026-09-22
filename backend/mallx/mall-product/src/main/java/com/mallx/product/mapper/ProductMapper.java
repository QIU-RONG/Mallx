package com.mallx.product.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.product.entity.Product;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;


public interface ProductMapper extends BaseMapper<Product> {

    /**
     * 统计某分类下的商品数 —— ★ 绕开 @TableLogic，含【已软删】的商品。
     * <p>
     * 【为什么不能用 selectCount】
     * Product 实体上有 @TableLogic，MyBatis-Plus 会给 selectCount 自动追加 is_deleted = 0，
     * 于是已软删的商品被漏算。删除分类前的引用校验一旦漏算，就会放行物理删，
     * 紧接着撞 fk_product_category（NO ACTION）→ 现场 500。
     * <p>
     * 【判据】引用计数的口径必须与【外键的口径】一致：外键不认识 is_deleted，计数就不能带它。
     * <p>
     * 实现在 {@code resources/mapper/ProductMapper.xml}（骨架期该 statement 是占位实现）。
     *
     * @param categoryId 分类 id
     * @return 该分类下的商品数（含已软删）
     */
    Long countByCategoryId(@Param("categoryId") Long categoryId);
}
