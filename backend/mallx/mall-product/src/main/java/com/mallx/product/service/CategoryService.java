package com.mallx.product.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.entity.Category;
import com.mallx.product.vo.CategoryVO;

import java.util.List;

public interface CategoryService extends IService<Category> {

    //分类树，用于商品分类
    List<CategoryVO> tree();
}
