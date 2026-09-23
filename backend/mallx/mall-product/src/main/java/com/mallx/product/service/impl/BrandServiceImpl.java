package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.product.entity.Brand;
import com.mallx.product.mapper.BrandMapper;
import com.mallx.product.service.BrandService;
import com.mallx.product.vo.BrandVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 品牌字典实现（L5，Day 20 补漏）。
 * <p>
 * ★ 不加 {@code @Transactional}：只读单条 SELECT，自身即一致性快照
 * （判据是「写点个数」，不是「方法重不重要」—— 同 {@code ProductServiceImpl.searchProducts}）。
 * <p>
 * ★ 不加 {@code @TableLogic} 相关处理：{@code brands} 表<b>没有 is_deleted 列</b>
 * （见 01-schema.sql 的 brands DDL），所以这里 {@code this.list(...)} 不会被自动加软删条件，
 * 也不存在「手写 XML 要自己补 is_deleted」的那个坑。删品牌靠的是外键
 * {@code fk_product_brand}（NO ACTION）拦着 —— 那是 L5 第②步（管理端 CRUD）要处理的。
 */
@Service
public class BrandServiceImpl extends ServiceImpl<BrandMapper, Brand> implements BrandService {

    @Override
    public List<BrandVO> listEnabled() {
        return listByStatus(1);
    }

    @Override
    public List<BrandVO> listAll() {
        return listByStatus(null);
    }

    /**
     * 唯一的实现体 —— 两个口径靠 {@code status} 是否传值区分。
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
