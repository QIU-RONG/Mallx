package com.mallx.product.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.dto.CategoryCreateDTO;
import com.mallx.product.dto.CategoryUpdateDTO;
import com.mallx.product.entity.Category;
import com.mallx.product.vo.CategoryVO;

import java.util.List;

public interface CategoryService extends IService<Category> {

    //分类树，用于商品分类
    List<CategoryVO> tree();

    // ---------------- 以下三个为 Day 18 管理端新增 ----------------

    /**
     * 新增分类。
     * <p>
     * 业务规则：① 只允许两级（父分类自身必须是顶级）；
     * ② parentId 非 null 时父分类必须存在。
     *
     * @return 新建分类的 id
     */
    Long createCategory(CategoryCreateDTO dto);

    /**
     * 修改分类（局部更新语义：null 字段不动）。
     * <p>
     * 业务规则：有子分类的分类【不允许】被挂到别的分类下（两级约束下这等价于「不成环」）。
     */
    void updateCategory(Long id, CategoryUpdateDTO dto);

    /**
     * 删除分类（物理删 —— categories 表没有 is_deleted）。
     * <p>
     * 三重校验：① 有子分类 → 拒；② 有商品引用（★ 含已软删商品）→ 拒；③ 都没有才删。
     */
    void deleteCategory(Long id);
}
