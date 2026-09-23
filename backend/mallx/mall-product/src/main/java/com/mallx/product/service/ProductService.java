package com.mallx.product.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.product.dto.ProductCreateDTO;
import com.mallx.product.dto.ProductUpdateDTO;
import com.mallx.product.entity.Product;
import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.vo.ProductDetailVO;
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
