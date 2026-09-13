package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.entity.Brand;
import com.mallx.product.entity.Category;
import com.mallx.product.entity.Product;
import com.mallx.product.entity.ProductImage;
import com.mallx.product.entity.ProductSku;
import com.mallx.product.mapper.BrandMapper;
import com.mallx.product.mapper.CategoryMapper;
import com.mallx.product.mapper.ProductImageMapper;
import com.mallx.product.mapper.ProductMapper;
import com.mallx.product.mapper.ProductSkuMapper;
import com.mallx.product.service.ProductService;
import com.mallx.product.vo.ProductDetailVO;
import com.mallx.product.vo.ProductVO;
import com.mallx.product.vo.SkuVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class ProductServiceImpl extends ServiceImpl<ProductMapper, Product> implements ProductService {

    /** 关联表无业务规则，直接注入 Mapper */
    private final CategoryMapper categoryMapper;
    private final BrandMapper brandMapper;
    private final ProductSkuMapper productSkuMapper;
    private final ProductImageMapper productImageMapper;

    public ProductServiceImpl(CategoryMapper categoryMapper, BrandMapper brandMapper,
                              ProductSkuMapper productSkuMapper, ProductImageMapper productImageMapper) {
        this.categoryMapper = categoryMapper;
        this.brandMapper = brandMapper;
        this.productSkuMapper = productSkuMapper;
        this.productImageMapper = productImageMapper;
    }

    @Override
    public Page<ProductVO> pageProducts(long current, long size, Long categoryId, String keyword) {
        LambdaQueryWrapper<Product> wrapper = new LambdaQueryWrapper<Product>()
                .eq(Product::getStatus, 1)                                    // C 端只看上架
                // 条件为 false 时不拼进 SQL；为 true 时用「自己 + 直接子分类」的 id 集合做 IN 查询
                .in(categoryId != null, Product::getCategoryId, expandCategoryIds(categoryId))
                .like(keyword != null && !keyword.isBlank(), Product::getName, keyword)
                .orderByDesc(Product::getId);

        Page<Product> page = this.page(new Page<>(current, size), wrapper);

        List<Product> records = page.getRecords();
        List<ProductVO> voList = new ArrayList<>();
        for (Product p : records) {
            ProductVO vo = new ProductVO();
            BeanUtils.copyProperties(p, vo);
            voList.add(vo);
        }
        fillNames(voList, records);

        // 换壳：total/current/size 必须搬到新 Page 上，否则前端看到 total=0
        Page<ProductVO> voPage = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        voPage.setRecords(voList);
        return voPage;
    }

    /**
     * 进阶：把 categoryId 展开成「它自己 + 它所有直接子分类」的 id 集合。
     * 分类量很小（7 条），全量查一次在内存里配对即可 —— selectList(null) 表示无过滤条件（全表）。
     * <p>
     * ⚠️ null 必须在方法内部挡掉：Java 是实参先求值，
     * 外层 {@code .in(categoryId != null, ...)} 的布尔只决定「条件要不要拼进 SQL」，
     * 并不阻止 expandCategoryIds(null) 被调用，内部不挡就会 NPE。
     * <p>
     * 两层分类单层扫描足够；若将来出现三级分类，再改成用 ArrayDeque 逐层下钻。
     */
    private Set<Long> expandCategoryIds(Long categoryId) {
        Set<Long> ids = new HashSet<>();
        if (categoryId == null) {
            return ids;                                    // ① 挡 null
        }
        ids.add(categoryId);                               // ② 自己也算（父分类下直接挂的商品要能查到）
        for (Category c : categoryMapper.selectList(null)) {
            if (categoryId.equals(c.getParentId())) {       // ③ 认亲：parentId == 我 → 是我的直接子分类
                ids.add(c.getId());
            }
        }
        return ids;
    }

    /** 批量补齐 categoryName / brandName，避免 N+1 */
    private void fillNames(List<ProductVO> voList, List<Product> records) {
        if (records.isEmpty()) {
            return;
        }
        // 1. 收集本页出现过的 id（去重）；brand_id 可空要挡
        Set<Long> categoryIds = new HashSet<>();
        Set<Long> brandIds = new HashSet<>();
        for (Product p : records) {
            categoryIds.add(p.getCategoryId());
            if (p.getBrandId() != null) {
                brandIds.add(p.getBrandId());
            }
        }

        // 2. 各查一次：WHERE id IN (...)
        Map<Long, String> categoryNames = new HashMap<>();
        for (Category c : categoryMapper.selectByIds(categoryIds)) {
            categoryNames.put(c.getId(), c.getName());
        }
        Map<Long, String> brandNames = new HashMap<>();
        if (!brandIds.isEmpty()) {
            for (Brand b : brandMapper.selectByIds(brandIds)) {
                brandNames.put(b.getId(), b.getName());
            }
        }

        // 3. 内存配对（voList 与 records 下标一一对应）
        for (int i = 0; i < records.size(); i++) {
            Product p = records.get(i);
            voList.get(i).setCategoryName(categoryNames.get(p.getCategoryId()));
            voList.get(i).setBrandName(brandNames.get(p.getBrandId()));
        }
    }

    @Override
    public ProductDetailVO getDetail(Long id) {
        Product product = this.getById(id);
        if (product == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }

        ProductDetailVO vo = new ProductDetailVO();
        BeanUtils.copyProperties(product, vo);

        Category category = categoryMapper.selectById(product.getCategoryId());
        if (category != null) {
            vo.setCategoryName(category.getName());
        }

        if (product.getBrandId() != null) {
            Brand brand = brandMapper.selectById(product.getBrandId());
            if (brand != null) {
                vo.setBrandName(brand.getName());
            }
        }

        List<ProductSku> skus = productSkuMapper.selectList(new LambdaQueryWrapper<ProductSku>()
                .eq(ProductSku::getProductId, id)
                .orderByAsc(ProductSku::getId));
        List<SkuVO> skuVos = new ArrayList<>();
        for (ProductSku sku : skus) {
            SkuVO sv = new SkuVO();
            BeanUtils.copyProperties(sku, sv);
            skuVos.add(sv);
        }
        vo.setSkus(skuVos);

        List<ProductImage> images = productImageMapper.selectList(new LambdaQueryWrapper<ProductImage>()
                .eq(ProductImage::getProductId, id)
                .orderByAsc(ProductImage::getSortOrder));
        vo.setImages(images.stream().map(ProductImage::getImageUrl).toList());

        return vo;
    }
}
