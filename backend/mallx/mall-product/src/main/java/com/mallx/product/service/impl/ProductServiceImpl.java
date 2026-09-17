package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.dto.ProductCreateDTO;
import com.mallx.product.dto.ProductUpdateDTO;
import com.mallx.product.dto.SkuCreateDTO;
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
import org.springframework.transaction.annotation.Transactional;

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

    /**
     * 新建商品：商品主表 + N 个 SKU + M 张图集，三张表同一个事务。
     * <p>
     * 【为什么必须 @Transactional】
     * 这三张表是「1 主 + 2 子」的关系，缺任何一半都是解释不通的脏数据：
     * 只有商品没有 SKU → 用户点进去无货可买；只有 SKU 没有商品 → 外键直接拒绝。
     * 任一步失败都必须整体撤销，否则库里会留下半成品。
     * <p>
     * 【rollbackFor 为什么写 Exception.class】
     * 默认只对 RuntimeException / Error 回滚，抛受检异常时会静默不回滚。
     * 显式写全，避免将来加进来一个受检异常就出漏洞。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createProduct(ProductCreateDTO productCreateDTO) {
        // ① 校验分类存在 —— 不是给外键兜底，是为了给出人能看懂的提示
        if (categoryMapper.selectById(productCreateDTO.getCategoryId()) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "分类不存在");
        }

        // ② 商品主表
        Product product = new Product();
        BeanUtils.copyProperties(productCreateDTO, product);
        if (product.getStatus() == null) {
            product.setStatus(1);
        }
        this.save(product);
        // 主表落库后才有自增 id，下面两张子表的外键全靠它
        Long productId = product.getId();

        // ③ 图集：数组下标 i 就是 sort_order
        List<String> images = productCreateDTO.getImages();
        if (images != null && !images.isEmpty()) {
            for (int i = 0; i < images.size(); i++) {
                String url = images.get(i);
                // 短路求值：url == null 时右边不求值，顺带挡掉 null.isBlank() 的 NPE
                if (url == null || url.isBlank()) {
                    continue;
                }
                ProductImage img = new ProductImage();
                img.setProductId(productId);
                img.setImageUrl(url);
                img.setSortOrder(i);
                productImageMapper.insert(img);
            }
        }

        // ④ SKU：productId 必须由服务端填，绝不能用客户端传的
        //    attributes 是 jsonb，靠 ProductSku 上的 JsonbMapTypeHandler 写进去
        List<SkuCreateDTO> skus = productCreateDTO.getSkus();
        if (skus != null && !skus.isEmpty()) {
            for (SkuCreateDTO s : skus) {
                ProductSku sku = new ProductSku();
                BeanUtils.copyProperties(s, sku);
                sku.setProductId(productId);
                if (sku.getStatus() == null) {
                    sku.setStatus(1);
                }
                // ★ 唯一约束冲突就发生在这一行 → 异常穿出代理 → 整个事务回滚
                productSkuMapper.insert(sku);
            }
        }

        return productId;
    }

    @Override
    public void updateProduct(Long id, ProductUpdateDTO productUpdateDTO) {
        // ① 先确认存在，否则 updateById 会"静默成功"（影响行数 0，但接口返回 200）
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        // ② copyProperties 是"无脑全拷"：dto 里没传的字段会被拷成 null
        //    但这不会清空 DB —— MyBatis-Plus 默认 NOT_NULL 更新策略，null 字段不拼进 SET
        Product update = new Product();
        BeanUtils.copyProperties(productUpdateDTO, update);
        // ③ 必须带 id，否则 updateById 不知道改哪一行
        update.setId(id);
        this.updateById(update);
    }

    /**
     * 删除商品：必须先清子表，再删主表 —— 顺序与新增时**正好相反**。
     * <p>
     * 【为什么不能只 removeById(products)】
     * product_skus / product_images 上都有指向 products(id) 的外键，且都是默认的
     * NO ACTION（confdeltype='a'）：只要子表还有引用行，PG 就会直接拒绝并报
     * "update or delete on table products violates foreign key constraint ..."。
     * <p>
     * 【为什么也要 @Transactional】
     * 这三次删除是一个整体：子表删完而主表删失败 → 商品还在、规格却没了；
     * 子表删一半就断 → 留下半清理状态。要么全删干净，要么都别动。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteProduct(Long id) {
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        // ★ 顺序不能反：先子后主
        productSkuMapper.delete(new LambdaQueryWrapper<ProductSku>()
                .eq(ProductSku::getProductId, id));
        productImageMapper.delete(new LambdaQueryWrapper<ProductImage>()
                .eq(ProductImage::getProductId, id));
        this.removeById(id);
    }
}
