package com.mallx.product.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.product.entity.Product;
import com.mallx.product.vo.ProductSearchVO;
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

    /**
     * ★★★ C 端商品搜索（Day 19）—— <b>SQL 在 XML 里，由你写</b>。
     *
     * <p>【为什么不用 MP 的 Wrapper】
     * 本方法要用到的三样东西都没有 MP 的 Lambda 表达形式：
     * <ul>
     *   <li>{@code search_vector @@ plainto_tsquery('simple', ?)} —— tsvector 匹配</li>
     *   <li>{@code ts_rank(...)} —— 相关性得分</li>
     *   <li>{@code attributes @> jsonb_build_object(k, v)} —— JSONB 包含</li>
     * </ul>
     * {@code wrapper.apply("...")} 能把裸 SQL 塞进去，但那会退化成「用 Java 拼 SQL」，
     * 参数化与可读性都变差 ⇒ 放进 XML。
     *
     * <p>★★ <b>手写 XML 不受 {@code @TableLogic} 管辖</b>：
     * {@code Product} 实体上的 {@code @TableLogic} 只作用于 MP 自动生成的 SQL。
     * 本 statement 是手写的 ⇒ <b>必须自己写 {@code p.is_deleted = 0}</b>，
     * 漏了就会把已软删的商品搜出来，而且<b>整个过程不报错</b>。
     * <p>
     * ★ 与上面的 {@code countByCategoryId} 是一体两面：那条 SQL 要「含软删」，所以<b>故意</b>不写
     * {@code is_deleted}；这条要「只搜未删」，所以<b>手动</b>补上。
     * 判据：手写 XML 里 is_deleted 的取舍，由这条 SQL 的语义决定，<b>不由实体决定</b>。
     *
     * <p>【参数约定】
     * <ul>
     *   <li>{@code keyword}：★ 由 Service 归一化后传入，保证<b>非 null</b>；
     *       空串表示「不限关键词」。不要在 XML 里判 {@code #{keyword} IS NULL} ——
     *       MyBatis 对 null 参数用 {@code setNull(JdbcType.OTHER)}，
     *       PostgreSQL 无法推断类型会直接报 {@code could not determine data type of parameter}。</li>
     *   <li>{@code categoryId}：null 表示「不限分类」。</li>
     *   <li>{@code attrKey} / {@code attrValue}：★ 成对 —— Service 已保证
     *       「要么两个都有值、要么两个都是 null」，XML 里只需判其中一个。</li>
     *   <li>{@code page}：★ <b>首参必须是 IPage</b>，分页插件靠它决定是否改写 SQL 加 LIMIT/OFFSET，
     *       XML 里【不要写】LIMIT —— 写了就是双重分页。</li>
     * </ul>
     *
     * <p>实现要点七条（is_deleted / plainto_tsquery / search_rank 保留字 / 别名下划线 /
     * jsonb_build_object / EXISTS 而非 JOIN / 不写 LIMIT）见
     * {@code docs/daily/Day-19-商品搜索.md} §五。
     *
     * @return 分页结果（total 由分页插件自动 count）
     */
    IPage<ProductSearchVO> searchProducts(IPage<ProductSearchVO> page,
                                          @Param("keyword") String keyword,
                                          @Param("categoryId") Long categoryId,
                                          @Param("attrKey") String attrKey,
                                          @Param("attrValue") String attrValue);
}
