package com.mallx.product.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
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
}
