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
