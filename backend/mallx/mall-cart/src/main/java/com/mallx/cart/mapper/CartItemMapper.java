package com.mallx.cart.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.cart.vo.CartItemVO;
import com.mallx.cart.vo.SkuForCartVO;
import org.apache.ibatis.annotations.Param;
import com.mallx.cart.entity.CartItem;

import java.util.List;

/**
 * 购物车 Mapper
 *
 * <p>{@link BaseMapper} 提供全套单表 CRUD；跨模块查询走 XML。
 *
 * <p>⚠️ 铁律：这里声明的每个方法，{@code CartItemMapper.xml} 里必须有同名
 * {@code <select id="...">}，否则 MyBatis 启动时不报错、一调用就
 * {@code Invalid bound statement}。
 * 现有两个（都在 XML 里）：
 * {@code selectSkuForCart}（加购前校验 SKU 可买性与库存）、
 * {@code selectCartView}（购物车列表，一条 LEFT JOIN 出全部展示字段）。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包
 * （与 ProductMapper 保持一致）。
 */
public interface CartItemMapper extends BaseMapper<CartItem> {

    /** 加购前校验：SKU 是否存在/可买、实时库存 */
    SkuForCartVO selectSkuForCart(@Param("skuId") Long skuId);

    /** 购物车列表：跨模块 reads product_skus / products / inventories */
    List<CartItemVO> selectCartView(@Param("userId") Long userId);
}
