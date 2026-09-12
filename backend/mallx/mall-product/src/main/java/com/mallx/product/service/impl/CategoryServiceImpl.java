package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.product.entity.Category;
import com.mallx.product.mapper.CategoryMapper;
import com.mallx.product.service.CategoryService;
import com.mallx.product.vo.CategoryVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

  @Service
public class CategoryServiceImpl extends ServiceImpl<CategoryMapper, Category> implements CategoryService {

    @Override
    public List<CategoryVO> tree() {
        //查询
        List<Category> all = this.list(new LambdaQueryWrapper<Category>()
                .orderByAsc(Category::getSortOrder)
                .orderByAsc(Category::getId));

        //转换为VO
        List<CategoryVO> vos = new ArrayList<>();
        for (Category c : all) {
            CategoryVO vo = new CategoryVO();
            BeanUtils.copyProperties(c, vo);
            vos.add(vo);
        }

        //按parentId分组
        Map<Long, List<CategoryVO>> groupByParentId = vos.stream()
                .collect(Collectors.groupingBy(v -> v.getParentId() == null ? -1L : v.getParentId()));

        for (CategoryVO vo : vos)
            vo.setChildren(groupByParentId.getOrDefault(vo.getId(),List.of()));

        return groupByParentId.getOrDefault(-1L,List.of());
    }
}
