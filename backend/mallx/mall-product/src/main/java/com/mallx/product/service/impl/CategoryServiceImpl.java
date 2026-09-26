package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.dto.CategoryCreateDTO;
import com.mallx.product.dto.CategoryUpdateDTO;
import com.mallx.product.entity.Category;
import com.mallx.product.mapper.CategoryMapper;
import com.mallx.product.mapper.ProductMapper;
import com.mallx.product.cache.CatalogCache;
import com.mallx.product.service.CategoryService;
import com.mallx.product.vo.CategoryVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class CategoryServiceImpl extends ServiceImpl<CategoryMapper, Category> implements CategoryService {

    /**
     * ★ 删分类前要问「还有商品挂在这儿吗」。
     * <p>
     * 必须用 {@code countByCategoryId}（手写 XML，绕过 @TableLogic），
     * <b>不能</b>用 {@code productMapper.selectCount} —— 后者会被 MP 自动追加
     * {@code is_deleted = 0}，漏算已软删的商品，校验放行后物理删分类就撞外键报 500。
     * 详见 {@code resources/mapper/ProductMapper.xml} 里的说明。
     */
    private final ProductMapper productMapper;
    private final CatalogCache catalogCache;

    public CategoryServiceImpl(ProductMapper productMapper, CatalogCache catalogCache) {
        this.productMapper = productMapper;
        this.catalogCache = catalogCache;
    }

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

    // ==========================================================================
    // Day 18 管理端新增
    // --------------------------------------------------------------------------
    // 【三个方法共用的两条规则】
    //   ① 「两级」约束：父分类自身必须是顶级（parentId == null），否则就成了三级。
    //      这与 C 端 ProductServiceImpl.expandCategoryIds 的「两层单层扫描」假设一致 ——
    //      约束写在这里，等于把那个隐含假设显式钉住。
    //   ② 每个方法都带 @Transactional：存在性/引用「检查」与「写入」之间不能被插队
    //      （否则就是「先查后改」的 TOCTOU：用陈旧的检查结果去执行删除）。
    // ==========================================================================

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createCategory(CategoryCreateDTO dto) {
        // ① 两级校验（只有传了 parentId 才需要查父分类；null = 新建顶级分类）
        if (dto.getParentId() != null) {
            Category parent = this.getById(dto.getParentId());
            if (parent == null) {
                throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "父分类不存在");
            }
            if (parent.getParentId() != null) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "只支持两级分类");
            }
        }

        // ② 拷字段 → ③ 保存（★ 自增 id 在 save 之后才回填到 c.getId()）
        //    status 不管：DTO 里没有它，null 不会被拼进 INSERT，走 DDL 默认值 1。
        Category c = new Category();
        BeanUtils.copyProperties(dto, c);
        this.save(c);
        // 目录缓存失效（V1.1 · D38）：分类树与详情内嵌的 categoryName 都会变
        catalogCache.bump();
        return c.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateCategory(Long id, CategoryUpdateDTO dto) {
        // ① 存在性：不检查的话 updateById 会「静默成功」（影响 0 行，接口照样 200）
        Category existing = this.getById(id);
        if (existing == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "分类不存在");
        }

        // ② 空串检查：DTO 上只有 @Size 管长度，空串要 Service 显式挡
        //    （与商品 updateProduct 同一写法）
        if (dto.getName() != null && dto.getName().isBlank()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "分类名称不能为空");
        }

        // ③ parentId 真的要改时才校验 —— 本日约定 parentId == null 一律按「不动」处理
        Long newParentId = dto.getParentId();
        if (newParentId != null && !newParentId.equals(existing.getParentId())) {
            if (newParentId.equals(id)) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "不能把自己设为父分类");
            }
            Category parent = this.getById(newParentId);
            if (parent == null) {
                throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "父分类不存在");
            }
            if (parent.getParentId() != null) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "只支持两级分类");
            }
            // ★ 我自己还有子分类，就不许被挂到别人下面 ——
            //   两级约束下这一条就等价于「不成环」（否则层级会被拉成三层）
            long childCount = this.count(new LambdaQueryWrapper<Category>().eq(Category::getParentId, id));
            if (childCount > 0) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该分类下有子分类，不能移动");
            }
        }

        // ④ 局部更新：copyProperties 之后 null 字段不会被拼进 SET，天然就是「没传 = 不动」
        Category u = new Category();
        BeanUtils.copyProperties(dto, u);
        u.setId(id);
        this.updateById(u);
        // 目录缓存失效（V1.1 · D38）：改名会脏掉详情内嵌的 categoryName
        catalogCache.bump();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteCategory(Long id) {
        // ① 存在性
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "分类不存在");
        }

        // ② 有子分类 → 拒
        long childCount = this.count(new LambdaQueryWrapper<Category>().eq(Category::getParentId, id));
        if (childCount > 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该分类下有子分类，请先删除子分类");
        }

        // ③ ★ 有商品引用吗 —— 必须用 countByCategoryId（含已软删商品），
        //     用 selectCount 会漏算已软删的，放行物理删后撞 fk_product_category → 500
        if (productMapper.countByCategoryId(id) > 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该分类下有商品，不能删除");
        }

        // ④ 真删（本表没有 @TableLogic，removeById 不会被改写成 UPDATE）
        this.removeById(id);
        // 目录缓存失效（V1.1 · D38）
        catalogCache.bump();
    }
}
