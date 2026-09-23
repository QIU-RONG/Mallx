package com.mallx.product.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.product.dto.ProductCreateDTO;
import com.mallx.product.dto.ProductUpdateDTO;
import com.mallx.product.entity.Product;
import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductSearchVO;
import com.mallx.product.vo.ProductVO;

public interface ProductService extends IService<Product> {
//    分页查商品
    Page<ProductVO> pageProducts(long current , long size , Long categoryId
    , String keyword);

    /**
     * 管理端商品分页（Day 18）—— 与 C 端【唯一的区别就是过滤口径】：
     * <pre>
     *   C 端  ：status 写死为 1（只看上架）
     *   管理端：status 是可选条件；不传 = 上架 + 下架都要
     * </pre>
     * ★ 所以不要另写一套查询实现，把「过滤」变成参数即可（实现里复用 fillNames 补名字）。
     * <p>
     * ★ <b>分页夹紧在本方法内完成</b>（同 {@code mall-order} / {@code mall-inventory} 的规矩）：
     * {@code current} 归一到 ≥1、{@code size} 落在 1..100，且<b>必须写在 {@code new Page<>(...)} 之前</b>。
     * Controller 只做转发，不重复夹紧 —— 同一条规则只在一层表达。
     *
     * @param status 1=上架 0=下架；★ 必须是包装类型 Integer —— 只有 null 才表达得出「不过滤」
     */
    Page<ProductVO> pageAdminProducts(long current, long size, Long categoryId,
                                      String keyword, Integer status);

    /**
     * ★★★ C 端商品搜索（Day 19）—— <b>骨架</b>，方法体由你写。
     *
     * <p>与 {@link #pageProducts} 是<b>两条独立的路</b>，不要合并：
     * 那条的 keyword 是 {@code LIKE '%kw%'}`（Day 09 口径，被 M1 回归 198 条逐字节守着），
     * 这条走全文检索 + JSONB 属性筛选。两条并存 ⇒ 同一关键词可以对照出差异，
     * 这正是本日最有力的证据（搜 {@code iphone}：旧路 0 条、新路 ≥1 条）。
     *
     * <p>实现三步（比 {@code pageAdminProducts} 多两步「归一化」）：
     * <pre>
     *   ① 归一化 keyword：null、或 trim 后为空 → 空串 ""
     *   ② 成对校验：attrKey / attrValue 只给一个 → BusinessException(VALIDATE_FAILED)
     *   ③ 夹紧（★ 必须在 new Page 之前）＋ 调 baseMapper.searchProducts(...)
     * </pre>
     *
     * <p>★★ <b>为什么归一化在 Java 侧做，而不是在 SQL 里判 {@code #{keyword} IS NULL}</b>：
     * MyBatis 给 null 参数会用 {@code setNull(JdbcType.OTHER)}，PostgreSQL
     * 无法推断该占位符的类型，直接报 {@code could not determine data type of parameter}。
     * 在 Java 侧把 null 消掉，SQL 里就只剩「空串 / 非空串」一种形态，少一个分支。
     *
     * <p>★ <b>为什么属性参数不成对要报错，而不是静默忽略</b>：
     * 静默忽略会造出「我明明传了筛选条件，却返回了全量」——这是最难查的一类 bug
     * （接口看着正常、数据看着合理，只是口径错了）。
     * 分界沿用 Day 18 的规矩：<b>格式类校验归 {@code @Valid}，业务类校验归 Service</b>。
     *
     * <p>★ 本接口<b>无需改 SecurityConfig</b>：C 端白名单里已有 {@code GET /api/products/**}，
     * {@code /**} 匹配任意深度，{@code /api/products/search} 自动公开。
     *
     * @param keyword   关键词；null / 空白 表示不限
     * @param attrKey   属性名（如 {@code color}）；★ 与 attrValue 必须成对
     * @param attrValue 属性值（如 {@code 黑色}）；值与 PG 的 JSONB 值按<b>字符串</b>比较
     * @return 分页结果（VO 由 XML 直接查出，<b>不需要换壳</b>）
     */
    IPage<ProductSearchVO> searchProducts(long current, long size, String keyword,
                                          Long categoryId, String attrKey, String attrValue);

//    商品详情
    ProductDetailVO getDetail(Long id);
    //    创建商品
    Long createProduct(ProductCreateDTO productCreateDTO);
    //    修改商品（id 走路径，body 只带这次要改的字段）
    void updateProduct(Long id, ProductUpdateDTO productUpdateDTO);
    //    删除商品
    void deleteProduct(Long id);
    //    批量删除商品
//    void deleteBatchProduct(Long[] ids);
}
