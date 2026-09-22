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

    public CategoryServiceImpl(ProductMapper productMapper) {
        this.productMapper = productMapper;
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
    // 以下三个为 Day 18 管理端新增（骨架：TODO 待填）
    // --------------------------------------------------------------------------
    // ★ 填实现时请【整段替换方法体，包括删掉最后那行 throw】——
    //   只加 return 不删 throw 会得到「[行,列] 无法访问的语句」，编译直接失败。
    // ★ 本类有三处长得一模一样的 throw，只删你正在填的那一个。
    // ==========================================================================

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createCategory(CategoryCreateDTO dto) {
        // TODO(你写) createCategory：
        //   ① 两级校验（parentId != null 才做）：
        //        Category parent = this.getById(dto.getParentId());
        //        · parent == null                         → new BusinessException(ResultCode.NOT_FOUND.getCode(), "父分类不存在")
        //        · parent.getParentId() != null            → new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "只支持两级分类")
        //      ★ 为什么要有第二条：C 端 ProductServiceImpl.expandCategoryIds 用的是
        //        「两层单层扫描」（自己 + 直接子分类），三级分类会让它的假设失效。
        //        约束写在这里，等于把那个隐含假设显式钉住。
        //   ② Category c = new Category(); BeanUtils.copyProperties(dto, c);
        //   ③ this.save(c);          ← 保存后 c.getId() 才有值（自增主键回填）
        //   ④ return c.getId();
        //   ★ status 不用管：DTO 里没有它，null 字段不会被拼进 INSERT，走 DDL 默认值 1。
        //   ⚠️ 本表没有 is_deleted，是真删表，所以不需要 @Transactional？
        //      —— 需要。理由与「存在性检查 + 删除」配对出现有关：检查与写入之间不能被插队。
        throw new UnsupportedOperationException("TODO: CategoryServiceImpl.createCategory");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateCategory(Long id, CategoryUpdateDTO dto) {
        // TODO(你写) updateCategory：
        //   ① 存在性检查：this.getById(id) == null → BusinessException(NOT_FOUND, "分类不存在")
        //      （不检查的话 updateById 会「静默成功」：影响 0 行，接口照样 200）
        //   ② 空串检查：dto.getName() != null && dto.getName().isBlank() → 400 "分类名称不能为空"
        //      （DTO 上只挂了 @Size，空串要靠 Service 显式挡 —— 与商品 updateProduct 同一写法）
        //   ③ parentId 真的要改才校验（dto.getParentId() != null 且不等于当前值）：
        //        · dto.getParentId().equals(id)            → 400 "不能把自己设为父分类"
        //        · 父分类不存在                             → 404 "父分类不存在"
        //        · 父分类自己不是顶级                       → 400 "只支持两级分类"
        //        · ★ 我自己还有子分类（本类 count 一下 parentId = id）→ 400 "该分类下有子分类，不能移动"
        //          （两级约束下，这一条就等价于「不成环」；否则会出现层级被拉成三层）
        //   ④ Category u = new Category(); BeanUtils.copyProperties(dto, u); u.setId(id);
        //      this.updateById(u);   ← null 字段不会被拼进 SET，天然就是局部更新
        //   ⚠️ 但 parentId 的 null 在本日约定为「不动」（见 CategoryUpdateDTO 类注释）。
        //      copyProperties 拷过去就是 null，MP 会跳过它 —— 恰好与我们想要的语义一致，白送。
        throw new UnsupportedOperationException("TODO: CategoryServiceImpl.updateCategory");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteCategory(Long id) {
        // TODO(你写) deleteCategory —— 三重校验，缺一不可：
        //   ① 存在性：this.getById(id) == null → 404 "分类不存在"
        //   ② 有子分类吗：this.count(new LambdaQueryWrapper<Category>().eq(Category::getParentId, id)) > 0
        //        → 400 "该分类下有子分类，请先删除子分类"
        //   ③ ★ 有商品引用吗：productMapper.countByCategoryId(id) > 0
        //        → 400 "该分类下有商品，不能删除"
        //      ★ 用 countByCategoryId（含已软删商品），不要用 selectCount —— 见字段上的注释。
        //        这一条是本日最容易写错、且报错最难看的一处：漏算了已软删商品，
        //        校验以为空着 → removeById 真删 → PG 抛
        //        「update or delete on table "categories" violates foreign key constraint
        //          fk_product_category on table "products"」→ 500。
        //   ④ this.removeById(id);    ← ★ 真删（本表无 @TableLogic，不会被改写成 UPDATE）
        //   ★ 为什么整个方法要 @Transactional：②③ 是「检查」，④ 是「写入」。
        //     检查与写入之间若被别的请求插进去（正好新建了一个商品），
        //     就会用陈旧的检查结果去执行删除 —— 这正是「先查后改」的 TOCTOU 形态。
        //     事务隔离把这三步包成一个原子观察窗口，让检查结果在删除时仍然成立。
        throw new UnsupportedOperationException("TODO: CategoryServiceImpl.deleteCategory");
    }
}
