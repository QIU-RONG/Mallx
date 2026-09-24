package com.mallx.product.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.product.entity.Product;
import com.mallx.product.vo.ProductSearchVO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.Collection;


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
     * 统计某品牌下挂着多少个商品 —— ★ 绕开 @TableLogic，含【已软删】的商品。
     * <p>
     * 【为什么需要第二条同族 SQL（Day 24 · L5②）】
     * {@code countByCategoryId} 的注释已经把理由写透了，这里只补「为什么不复用」：
     * 两条 SQL 的<b>结构完全一样、只有列不同</b>（{@code category_id} / {@code brand_id}），
     * 但这<b>不能</b>合成一条带 {@code <if>} 的 SQL ——
     * 那样调用方就要传「按哪个列数」，而这个选择由<b>业务语义</b>决定（删分类 vs 删品牌），
     * 不是由数据决定。合成一条的结果是：调用方写错列名，编译期、运行期都不报错，
     * 只是「拿分类的计数去判品牌能不能删」—— 一个永远为 0 的检查（同族：Day 19 的
     * categoryId 两入口口径漂移）。
     * <p>
     * 【判据照抄】引用计数的口径必须与【外键的口径】一致：外键 {@code fk_product_brand}
     * 不认识 {@code is_deleted}，所以计数也不能带它。
     * <p>
     * 实现在 {@code resources/mapper/ProductMapper.xml}。
     *
     * @param brandId 品牌 id
     * @return 该品牌下的商品数（含已软删）
     */
    Long countByBrandId(@Param("brandId") Long brandId);

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
     *   <li>{@code categoryIds}：★ <b>L4（Day 20 补漏）</b>已由 {@code Long categoryId} 改成
     *       {@code Collection<Long>} —— View 层仍收单个 {@code categoryId}，
     *       由 Service 用 {@code expandCategoryIds} 展开成「自己 + 直接子分类」的集合再传进来，
     *       与 C 端列表 <b>完全同源</b>（同一个方法，不可能漂移）。
     *       ★ <b>空集合表示「不限分类」</b>，XML 用 {@code categoryIds.size() > 0} 挡掉 ——
     *       不挡会生成 {@code IN ()} 直接语法错。
     *       <b>改前是等值比较</b> ⇒ {@code /api/products/search?categoryId=1}（父分类）返回 0 条，
     *       而 {@code /api/products?categoryId=1} 返回该父分类下全部商品 —— 一个不报错、
     *       不 500 的口径漂移（本项目最难发现的一类缺陷）。</li>
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
                                          @Param("categoryIds") Collection<Long> categoryIds,
                                          @Param("attrKey") String attrKey,
                                          @Param("attrValue") String attrValue);
}
