package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.dto.ProductCreateDTO;
import com.mallx.product.dto.ProductUpdateDTO;
import com.mallx.product.dto.SkuCreateDTO;
import com.mallx.product.dto.SkuUpdateDTO;
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
import com.mallx.product.vo.ProductSearchVO;
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

    /**
     * 分页上限：单页最多 100 条 —— 与 {@code OrderServiceImpl} / {@code InventoryServiceImpl} /
     * {@code ReviewServiceImpl} 同一个值、同一套夹紧规则（本处是第 5 份拷贝）。
     *
     * <p>★ 仍不抽到 {@code mall-common}：那是一次跨模块重构，与本步无关；
     * 各处留一份、注释互相指明，等真有需要时再抽。
     *
     * <p>★ 夹紧对本类的<b>三个</b>分页方法都生效：{@code pageProducts}（Day 20 补漏 L1）、
     * {@code pageAdminProducts}（Day 18）、{@code searchProducts}（Day 19 起就有）。
     * <p>★ 历史：C 端 {@code pageProducts} 从 Day 09 到 Day 19 一直<b>没有夹紧</b>
     * （{@code size=-1} 会查全表），Day 20 补上 —— 它不在 M1 回归的覆盖范围内
     * （M1 三个脚本只打 {@code /api/products/{id}/reviews}），所以补漏零回归风险。
     */
    private static final long MAX_PAGE_SIZE = 100;

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

        // ★ L1（Day 20 补漏）：夹紧必须在 new Page<>(...) 之前 —— 写进构造参数里就晚了。
        //   不夹的话 size=-1 会撞 MP 的「负数=不限量」语义，直接查全表。
        long safePage = Math.max(current, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        Page<Product> page = this.page(new Page<>(safePage, safeSize), wrapper);

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

    @Override
    public Page<ProductVO> pageAdminProducts(long current, long size, Long categoryId,
                                             String keyword, Integer status) {
        // 与 C 端 pageProducts 的【唯一差别】就是 status 的过滤口径：
        //   C 端  ：.eq(Product::getStatus, 1)                      // 写死：只看上架
        //   管理端：.eq(status != null, Product::getStatus, status) // 条件：不传就全都要（含下架）
        // ★ status 用 Integer 而非 int —— 只有 null 才表达得出「不过滤」；
        //   写成 int，方法签名会强制调用方给值，「不传」这条路直接被堵死。
        // ★ 夹紧只在【本方法】生效：C 端 pageProducts（Day 09-11）没有夹紧，属已知遗留，本日不动。
        // ★ 不用为管理端新建 VO：ProductVO 里已有 status 字段。
        long safePage = Math.max(current, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        LambdaQueryWrapper<Product> wrapper = new LambdaQueryWrapper<Product>()
                .eq(status != null, Product::getStatus, status)
                .in(categoryId != null, Product::getCategoryId, expandCategoryIds(categoryId))
                .like(keyword != null && !keyword.isBlank(), Product::getName, keyword)
                .orderByDesc(Product::getId);
        Page<Product> page = this.page(new Page<>(safePage, safeSize), wrapper);
        List<Product> records = page.getRecords();
        List<ProductVO> voList = new ArrayList<>();
        for (Product p : records) {
            ProductVO vo = new ProductVO();
            BeanUtils.copyProperties(p, vo);
            voList.add(vo);
        }
        fillNames(voList, records);
        Page<ProductVO> voPage = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        voPage.setRecords(voList);
        // ★ 返回 voPage 而不是 page：后者是 Page<Product>，类型不对，也没补 categoryName/brandName
        return voPage;
    }

    /**
     * ★★★ C 端商品搜索（Day 19）—— <b>骨架</b>，方法体由你写（本日唯一的核心实现）。
     *
     * <p>三步，顺序不能换：
     * <pre>
     *   ① 归一化 keyword：
     *        keyword = (keyword == null) ? "" : keyword.trim();
     *      ★ 归一化必须在这里做完 —— SQL 侧不接受 null，
     *        理由见 ProductService#searchProducts 的「PG 类型推断」段落。
     *   ② 成对校验：
     *        attrKey / attrValue 只有一个非空 →
     *            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
     *                                        "attrKey 与 attrValue 必须成对出现");
     *      ★ 两个都为空是【合法】的（= 不做属性筛选），别写成「必须都有值」。
     *   ③ 夹紧 + 调用（★ 夹紧必须在 new Page 之前）：
     *        long safePage = Math.max(current, 1);
     *        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
     *        return baseMapper.searchProducts(new Page&lt;&gt;(safePage, safeSize),
     *                                         keyword, categoryId, attrKey, attrValue);
     * </pre>
     *
     * <p>★ <b>本方法不需要换壳</b>：与上面两个分页方法不同 ——
     * 它们要 {@code Page<Product>} → {@code Page<ProductVO>}（{@code this.page()} 只能吐实体）；
     * 本方法的 XML <b>直接查出 ProductSearchVO</b>，返回的 IPage 拿来就能用。
     *
     * <p>★ 不加 {@code @Transactional}：只读单条 SELECT 自身即一致性快照
     * （判据是「写点个数」，不是「方法重不重要」）。
     *
     * <p>★ 不在此处打日志：查询失败由全局异常处理器统一记，同两个分页方法。
     */
    @Override
    public IPage<ProductSearchVO> searchProducts(long current, long size, String keyword,
                                                 Long categoryId, String attrKey, String attrValue) {
        String kw = (keyword == null || keyword.trim().isEmpty()) ? "" : keyword.trim();
        String key = (attrKey == null || attrKey.isBlank()) ? null : attrKey;
        String val = (attrValue == null || attrValue.isBlank()) ? null : attrValue;
        if((key == null) != (val == null)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "attrKey 与 attrValue 必须成对出现");
        }
        long safePage = Math.max(current, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        return baseMapper.searchProducts(new Page<>(safePage, safeSize),
                kw, categoryId, key, val);
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

    /**
     * C 端商品详情 —— <b>只看上架</b>。
     *
     * <p>★★ L2（Day 20 补漏）：本方法与原 {@code getAdminDetail} 共用装配逻辑，
     * 但<b>必须分开</b> —— 从 Day 05 到 Day 19，两者其实是同一个方法，
     * 管理端的「下架商品也能看」是靠<b>碰巧没人加 status 判断</b>维持的。
     * 谁要给 C 端加上架校验，就会顺手把管理端砸掉（管理员再也打不开自己下架的商品）。
     *
     * <p>★ 下架一律<b>伪装 404</b>：既不返回 403，也不说「存在但已下架」——
     * 后者等于把「这个 id 有效、只是下架了」告诉任何人（同 {@code requireOwn} 的口径）。
     */
    @Override
    public ProductDetailVO getDetail(Long id) {
        Product product = this.getById(id);
        if (product == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        if (product.getStatus() == null || product.getStatus() != 1) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        return assembleDetail(product);
    }

    /**
     * 管理端商品详情 —— <b>下架商品也要能看</b>（Day 20 补漏时从 {@code getDetail} 拆出来）。
     *
     * <p>★ 这里<b>不判 status</b>：下架商品正是管理员要改价、要重新上架的对象。
     * 唯一判空：软删商品连行都查不到（{@code @TableLogic} 已过滤），那才是真 404。
     */
    @Override
    public ProductDetailVO getAdminDetail(Long id) {
        Product product = this.getById(id);
        if (product == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        return assembleDetail(product);
    }

    /**
     * 详情装配（分类名 / 品牌名 / SKU / 图集）——
     * 两条路唯一差别就在 status 判断，装配逻辑必须共用，否则字段会漂。
     */
    private ProductDetailVO assembleDetail(Product product) {
        Long id = product.getId();
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

    /**
     * 修改商品 —— 局部更新语义（类 PATCH），三段式：主表 → SKU 差分 → 图集。
     * <p>
     * 【为什么整段在一个事务里】三张表的写操作必须同生共死：SKU 差分到一半失败
     * （比如某个 id 不属于本商品而抛异常），主表那句 UPDATE 也要跟着回滚，
     * 否则会出现"标题改了、规格没改"的半成品状态。
     * <p>
     * 【集合字段的三种语义】null=不动；[]=清空；非空=以本次为准对齐。
     */
    @Transactional(rollbackFor = Exception.class)
    @Override
    public void updateProduct(Long id, ProductUpdateDTO productUpdateDTO) {
        // ==================== ① 主表 ====================
        // 先确认存在，否则 updateById 会"静默成功"（影响行数 0，但接口返回 200）
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        // 局部更新下，"没传 name"合法、"传了空串"不合法 —— 这个区别 @NotBlank 表达不了
        if (productUpdateDTO.getName() != null && productUpdateDTO.getName().isBlank()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "商品名称不能为空");
        }
        // copyProperties 是"无脑全拷"：dto 里没传的字段会被拷成 null，但这不会清空 DB ——
        // MyBatis-Plus 默认 NOT_NULL 更新策略，null 字段不拼进 SET。
        // 另：images / skus 会被静默跳过（Product 实体没有这两个字段），不报错也不警告，
        // 这正是下面手工处理它们的原因。
        Product update = new Product();
        BeanUtils.copyProperties(productUpdateDTO, update);
        update.setId(id);
        this.updateById(update);

        // ==================== ② SKU 差分 ====================
        // 注意这里用 if 包住而不是提前 return —— 第 ③ 段还要往下走。
        List<SkuUpdateDTO> skuDtos = productUpdateDTO.getSkus();
        if (skuDtos != null) {
            // 2.1 查出现有的并装进 Map<id, 行>，作为"还被提到过"的候选池
            //     ★ @TableLogic 让这条 selectList 自动带上 AND is_deleted=0，
            //       所以已软删的 SKU 不在池子里 —— PUT 不负责复活数据（那是回收站的事）
            List<ProductSku> existing = productSkuMapper.selectList(
                    new LambdaQueryWrapper<ProductSku>().eq(ProductSku::getProductId, id));
            Map<Long, ProductSku> untouched = new HashMap<>();
            for (ProductSku s : existing) {
                untouched.put(s.getId(), s);
            }

            // 2.2 遍历本次提交的：没 id → 新增；有 id → 修改
            for (SkuUpdateDTO dto : skuDtos) {
                if (dto.getId() == null) {
                    // ---- 新增规格 ----
                    ProductSku sku = new ProductSku();
                    BeanUtils.copyProperties(dto, sku);     // dto.id 本来就是 null，正好
                    sku.setProductId(id);                   // ★ 归属只能服务端填，客户端传的不信
                    if (sku.getStatus() == null) {
                        sku.setStatus(1);
                    }
                    // 唯一约束冲突（sku_code 撞库）就在这里抛 → 整个事务回滚
                    productSkuMapper.insert(sku);
                } else {
                    // ---- 修改规格 ----
                    // ★ remove 而非 get：取值与"打标记为已处理"是同一步操作。
                    //   若用 get 不删，2.3 就会把这一行也当成"没提到"而误删。
                    ProductSku old = untouched.remove(dto.getId());
                    if (old == null) {
                        // 两种可能：这个 id 根本不存在，或它属于别的商品。
                        // 一律当越权处理并拒绝 —— 这是 IDOR 防线，绝不能静默 continue：
                        // 不校验的话，PUT /api/products/2 + 商品1的 skuId 就能改掉商品1的价格。
                        throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                                "SKU 不属于该商品");
                    }
                    ProductSku sku = new ProductSku();
                    BeanUtils.copyProperties(dto, sku);
                    sku.setId(dto.getId());                 // 改哪一行
                    sku.setProductId(id);                   // ★ 归属钉死，不许客户端把 SKU 挪走
                    // 与主表同理：dto 里没传的字段是 null，不会被拼进 SET
                    productSkuMapper.updateById(sku);
                }
            }

            // 2.3 Map 里剩下的 = 库里存在、本次没提到的 → 软删
            //     遍历结束后的"残余"天然就是要删的，不需要两层嵌套循环去比对。
            //     传 [] 时 2.2 一次都不进，这里就把全部 SKU 软删 —— 清空语义是白送的。
            for (ProductSku orphan : untouched.values()) {
                // ★ deleteById 不是物理删：@TableLogic 会改写成
                //   UPDATE product_skus SET is_deleted=1 WHERE id=? AND is_deleted=0
                //   物理删会撞 fk_inventory_sku / fk_cart_sku（都是 NO ACTION）
                productSkuMapper.deleteById(orphan.getId());
            }
        }

        // ==================== ③ 图集 ==================== （第 5 步）
        List<String> images = productUpdateDTO.getImages();
        if(images != null){

            productImageMapper.delete(new LambdaQueryWrapper<ProductImage>().eq(ProductImage::getProductId, id));
            for (int i = 0; i < images.size(); i++){
                String url = images.get(i);
                if(url == null || url.isBlank()) continue;
                ProductImage img = new ProductImage();
                img.setProductId(id);
                img.setImageUrl(url);
                img.setSortOrder(i);
                productImageMapper.insert(img);
            }
        }
    }

    /**
     * 删除商品：软删除主表一行，子表一行不动。
     * <p>
     * 【为什么不再删子表】子表的唯一入口是 product_id，主表被 is_deleted=1 过滤掉之后
     * 整棵子树都不可达，不需要连锁标记。反过来做反而会制造"孤儿商品"：
     * 商品恢复了，被标记删的 SKU 和物理删掉的图集却回不来。
     * <p>
     * 【为什么外键不再是问题】@TableLogic 把 removeById 改写成了
     * UPDATE products SET is_deleted=1 WHERE id=? AND is_deleted=0 ——
     * 全程没有 DELETE 语句，fk_sku_product / fk_inventory_sku / fk_review_product
     * 这些 NO ACTION 外键根本不会被触发。
     * <p>
     * 【为什么保留 @Transactional】单条 UPDATE 自身是原子的，但 getById 判存在 +
     * removeById 是一对"检查—再操作"，且删商品在真实项目里总会陆续加上写日志、
     * 清缓存、发通知等语句。留着事务边界成本≈0，省得将来补。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteProduct(Long id) {
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        this.removeById(id);
    }
}
