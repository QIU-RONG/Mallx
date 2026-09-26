package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.dto.BrandCreateDTO;
import com.mallx.product.dto.BrandUpdateDTO;
import com.mallx.product.entity.Brand;
import com.mallx.product.mapper.BrandMapper;
import com.mallx.product.mapper.ProductMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.mallx.product.cache.CatalogCache;
import com.mallx.product.service.BrandService;
import com.mallx.product.vo.BrandVO;
import org.springframework.beans.BeanUtils;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;

/**
 * 品牌字典实现（L5①，Day 20 补漏；L5② CRUD 于 Day 24 补齐）。
 * <p>
 * ★ 读方法不加 {@code @Transactional}：只读单条 SELECT，自身即一致性快照
 * （判据是「写点个数」，不是「方法重不重要」—— 同 {@code ProductServiceImpl.searchProducts}）。
 * ★ 写方法加 {@code @Transactional}：存在性/引用检查与写入之间不能被插队。
 * <p>
 * ★ 不加 {@code @TableLogic} 相关处理：{@code brands} 表<b>没有 is_deleted 列</b>
 * （见 01-schema.sql:68-76 的 DDL），所以这里 {@code this.list(...)} 不会被自动加软删条件，
 * 也不存在「手写 XML 要自己补 is_deleted」的那个坑。删品牌靠的是外键
 * {@code fk_product_brand}（NO ACTION）拦着 —— 那是 {@link #deleteBrand} 要处理的。
 */
@Service
public class BrandServiceImpl extends ServiceImpl<BrandMapper, Brand> implements BrandService {

    /** 品牌列表缓存的反序列化目标（泛型擦除 ⇒ TypeReference） */
    private static final TypeReference<List<BrandVO>> BRAND_LIST_TYPE = new TypeReference<>() {
    };

    /**
     * 删品牌前要问「还有商品挂在这个品牌下吗」。
     * <p>
     * 必须用 {@code countByBrandId}（手写 XML，绕过 @TableLogic），
     * <b>不能</b>用 {@code productMapper.selectCount} —— 后者会被 MP 自动追加
     * {@code is_deleted = 0}，漏算已软删的商品，校验放行后物理删品牌就撞外键报 500。
     * 详见 {@code resources/mapper/ProductMapper.xml} 里两条 countBy* 的说明，
     * 以及 {@code CategoryServiceImpl} 里那张「同一个缺陷两个出口」的对照。
     */
    private final ProductMapper productMapper;
    private final CatalogCache catalogCache;

    public BrandServiceImpl(ProductMapper productMapper, CatalogCache catalogCache) {
        this.productMapper = productMapper;
        this.catalogCache = catalogCache;
    }

    @Override
    public List<BrandVO> listEnabled() {
        // ==== V1.1 · D39：cache-aside（仅 C 端口径；管理端 listAll 保持直查 —— 写少读多的
        //      是 C 端，管理端低频且要求绝对新鲜）。写点（品牌 3 写 + 商品写）已全部 bump。
        String gen = catalogCache.generation();
        String key = catalogCache.brandListKey(gen, 1);
        List<BrandVO> cached = catalogCache.readJson(key, BRAND_LIST_TYPE);
        if (cached != null) {
            return cached;
        }
        List<BrandVO> vos = listByStatus(1);
        catalogCache.writeJson(key, vos);
        return vos;
    }

    @Override
    public List<BrandVO> listAll() {
        return listByStatus(null);
    }

    // ==========================================================================
    // Day 24 · L5② 管理端写接口
    // --------------------------------------------------------------------------
    // 【与 CategoryServiceImpl 的三处刻意不同 —— 每一处都是本表自己的事实】
    //   ① categories.name 【没有】唯一约束 ⇒ 那边不查重；brands.name 【有】UNIQUE
    //      （01-schema.sql:70）⇒ 这边必须查重，且要把 23505 翻译成 400。
    //   ② categories 删前要查两件事（子分类 + 商品引用）；brands 【没有层级】
    //      ⇒ 只查一件（商品引用）。
    //   ③ categories 的 DTO 不带 status（没有消费方）；brands 的 DTO 带
    //      （C 端 listEnabled 过滤它）—— 见 BrandCreateDTO 的对照表。
    // ==========================================================================

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createBrand(BrandCreateDTO dto) {
        String name = dto.getName().trim();

        // ① 重名检查 —— 给出【人话】，而不是让 23505 冒到兜底 handler 变成 500
        //    ★ 这是「同一件事两处把关」的第一处（乐观提示）；第二处在下面的 catch，
        //      两处都需要：这里覆盖 99% 的串行场景且错误信息最友好，
        //      catch 覆盖「检查通过了、插入时被别人抢先」的并发窗口。
        if (nameExists(name, null)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "品牌名称已存在：" + name);
        }

        Brand b = new Brand();
        BeanUtils.copyProperties(dto, b);
        b.setName(name);
        // ★ status 不额外处理：DTO 里没传就是 null，null 不会被拼进 INSERT，
        //   走 DDL 的 DEFAULT 1（MyBatis-Plus 的 NOT_NULL 插入策略）。
        try {
            this.save(b);
        } catch (DuplicateKeyException e) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "品牌名称已存在：" + name);
        }

        // ★ 自增 id 在 save 之后才回填到 b.getId()
        // 目录缓存失效（V1.1 · D38）
        catalogCache.bump();
        return b.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateBrand(Long id, BrandUpdateDTO dto) {
        // ① 存在性：不检查的话 updateById 会「静默成功」（影响 0 行，接口照样 200）
        Brand existing = this.getById(id);
        if (existing == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "品牌不存在");
        }

        // ② name 传了就要合法：空串/空白串显式挡（DTO 上只有 @Size，管不到空串）
        String name = dto.getName();
        if (name != null) {
            name = name.trim();
            if (name.isEmpty()) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "品牌名称不能为空");
            }
            // ③ 改名到「别人的名字」上 → 400。传 null（不改名）或与自身同名都放行，
            //    所以查重要把自己排除掉（excludedId = id）。
            if (nameExists(name, id)) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "品牌名称已存在：" + name);
            }
        }

        // ④ 局部更新：copyProperties 之后 null 字段不会被拼进 SET，天然就是「没传 = 不动」
        Brand u = new Brand();
        BeanUtils.copyProperties(dto, u);
        u.setId(id);
        u.setName(name);   // null（没传）→ 不动；非 null → 用 trim 过的值
        try {
            this.updateById(u);
        } catch (DuplicateKeyException e) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "品牌名称已存在：" + name);
        }
        // 目录缓存失效（V1.1 · D38）：改名会脏掉详情内嵌的 brandName
        catalogCache.bump();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteBrand(Long id) {
        // ① 存在性
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "品牌不存在");
        }

        // ② ★ 有商品引用吗 —— 必须用 countByBrandId（含已软删商品），
        //     用 selectCount 会漏算已软删的，放行物理删后撞 fk_product_brand → 500
        if (productMapper.countByBrandId(id) > 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该品牌下有商品，不能删除（可改为停用）");
        }

        // ③ 真删（本表没有 @TableLogic，removeById 不会被改写成 UPDATE）
        this.removeById(id);
        // 目录缓存失效（V1.1 · D38）
        catalogCache.bump();
    }

    /**
     * 品牌名是否已被占用。
     *
     * @param excludedId 查重时排除的 id（更新场景传【自己】，否则「改成同名」会被误判为重名）；
     *                   新建场景传 null
     */
    private boolean nameExists(String name, Long excludedId) {
        return this.count(new LambdaQueryWrapper<Brand>()
                .eq(Brand::getName, name)
                .ne(excludedId != null, Brand::getId, excludedId)) > 0;
    }

    /**
     * 唯一的读实现体 —— 两个口径靠 {@code status} 是否传值区分。
     * <p>
     * ★ 用 MP 的「条件生效」重载 {@code eq(boolean, ...)}：{@code status == null} 时该条件
     * 整段不拼进 WHERE（而不是拼成 {@code status = null} 那种永远查不到东西的写法）。
     * <p>
     * ★ 排序固定 {@code id ASC}：brands 表没有 sort_order（对比 categories 有），
     * 不加 ORDER BY 时 PG 不保证稳定顺序，同一请求两次可能拿到不同序列 ——
     * 与 {@code searchProducts} 里「ORDER BY search_rank DESC, p.id ASC」同一个理由。
     */
    private List<BrandVO> listByStatus(Integer status) {
        LambdaQueryWrapper<Brand> wrapper = new LambdaQueryWrapper<Brand>()
                .eq(status != null, Brand::getStatus, status)
                .orderByAsc(Brand::getId);

        List<BrandVO> vos = new ArrayList<>();
        for (Brand b : this.list(wrapper)) {
            BrandVO vo = new BrandVO();
            BeanUtils.copyProperties(b, vo);
            vos.add(vo);
        }
        return vos;
    }
}
