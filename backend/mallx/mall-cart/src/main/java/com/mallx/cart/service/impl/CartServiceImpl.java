package com.mallx.cart.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.cart.dto.CartAddDTO;
import com.mallx.cart.entity.CartItem;
import com.mallx.cart.mapper.CartItemMapper;
import com.mallx.cart.service.CartService;
import com.mallx.cart.vo.CartItemVO;
import com.mallx.cart.vo.CartVO;
import com.mallx.cart.vo.SkuForCartVO;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.List;

@Service
public class CartServiceImpl implements CartService {

    private final CartItemMapper cartItemMapper;

    public CartServiceImpl(CartItemMapper cartItemMapper) {
        this.cartItemMapper = cartItemMapper;
    }

    @Override
    public Long addToCart(Long userId, CartAddDTO dto) {

        // ① 校验 SKU 能不能买
       SkuForCartVO sku = cartItemMapper.selectSkuForCart(dto.getSkuId());
       if (sku == null)
           throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "SKU 不存在");
       if (Integer.valueOf(1).equals(sku.getSkuDeleted()))
           throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该规格已下架");
       if (Integer.valueOf(1).equals(sku.getProductDeleted()))
           throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "商品已删除");
       if (!Integer.valueOf(1).equals(sku.getProductStatus()))
           throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "商品已下架");

        // ② 查购物车里是否已有同一 SKU
       CartItem existing = cartItemMapper.selectOne(new LambdaQueryWrapper<CartItem>()
               .eq(CartItem::getUserId, userId)
               .eq(CartItem::getSkuId, dto.getSkuId()));

       int merged = dto.getQuantity() + (existing == null ? 0 : existing.getQuantity());
       if (merged > sku.getAvailableStock())
           throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                   "库存不足，仅剩 " + sku.getAvailableStock() + " 件");
        // ④ 有则累加，无则插入
        if(existing == null){
            CartItem item = new CartItem();
            item.setUserId(userId);
            item.setSkuId(dto.getSkuId());
            item.setQuantity(dto.getQuantity());
            item.setSelected(true);
            cartItemMapper.insert(item);
            return item.getId();
        }
        existing.setQuantity(merged);
        cartItemMapper.updateById(existing);
        return existing.getId();
    }

    @Override
    public CartVO getCart(Long userId) {

        // 一条 LEFT JOIN 查出全部展示字段（失效项也在，只是标记出来）
        List<CartItemVO> items = cartItemMapper.selectCartView(userId);

        int totalQuantity = 0;
        int selectedQuantity = 0;
        BigDecimal selectedAmount = BigDecimal.ZERO;

        for (CartItemVO it : items) {

            // ① 失效判定 —— 顺序即优先级：先判最"根本"的原因
            if (Integer.valueOf(1).equals(it.getSkuDeleted())) {
                it.setInvalid(true);
                it.setInvalidReason("规格已删除");
            } else if (Integer.valueOf(1).equals(it.getProductDeleted())) {
                it.setInvalid(true);
                it.setInvalidReason("商品已删除");
            } else if (!Integer.valueOf(1).equals(it.getProductStatus())) {
                it.setInvalid(true);
                it.setInvalidReason("商品已下架");
            } else if (it.getQuantity() > it.getAvailableStock()) {
                it.setInvalid(true);
                it.setInvalidReason("库存不足（仅剩 " + it.getAvailableStock() + " 件）");
            } else {
                it.setInvalid(false);
                it.setInvalidReason(null);
            }

            // ② 小计 = 实时价 × 数量（服务端算，禁止客户端算金额）
            BigDecimal price = (it.getPrice() == null) ? BigDecimal.ZERO : it.getPrice();
            it.setSubtotal(price.multiply(BigDecimal.valueOf(it.getQuantity())));

            // ③ 合计：总量含失效项；勾选量/勾选金额只认「有效 且 已勾选」
            //    失效项即使 selected=true 也不计入 —— 否则用户会为买不到的东西付钱
            totalQuantity += it.getQuantity();
            if (!it.isInvalid() && Boolean.TRUE.equals(it.getSelected())) {
                selectedQuantity += it.getQuantity();
                selectedAmount = selectedAmount.add(it.getSubtotal());
            }
        }

        CartVO vo = new CartVO();
        vo.setItems(items);
        vo.setTotalQuantity(totalQuantity);
        vo.setSelectedQuantity(selectedQuantity);
        vo.setSelectedAmount(selectedAmount);
        return vo;
    }

    @Override
    public void updateQuantity(Long userId, Long itemId, Integer quantity) {

        CartItem item = requireOwn(userId, itemId);

        // 实时库存比一次：改完不能超过可卖数（库存可能已被别人买走）
        SkuForCartVO sku = cartItemMapper.selectSkuForCart(item.getSkuId());
        int stock = (sku == null || sku.getAvailableStock() == null) ? 0 : sku.getAvailableStock();
        if (quantity > stock) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "库存不足，仅剩 " + stock + " 件");
        }

        // 刻意不在这里拦「商品已下架 / 规格已删除」：那是列表里 invalid 标记的职责，
        // 用户仍有权调整自己车里的数据；真正拦住下单的是结算环节。
        item.setQuantity(quantity);
        cartItemMapper.updateById(item);
    }

    @Override
    public void updateSelected(Long userId, Long itemId, Boolean selected) {
        CartItem item = requireOwn(userId, itemId);
        item.setSelected(selected);
        cartItemMapper.updateById(item);
    }

    @Override
    public void removeItem(Long userId, Long itemId) {
        CartItem item = requireOwn(userId, itemId);
        // cart_items 没有 is_deleted 列 → 真 DELETE；重复删第二次 selectById 返回 null → 404
        cartItemMapper.deleteById(item.getId());
    }

    /**
     * 验明正身：这行必须存在、且属于当前登录用户。
     *
     * <p>★ 两种失败都返回 <b>404「购物车项不存在」</b>，绝不返回 403 ——
     * 403 等于告诉攻击者「这个 id 是有效资源，只是不属于你」。
     * 对不属于自己的资源，统一伪装成「查无此物」。
     */
    private CartItem requireOwn(Long userId, Long itemId) {
        CartItem item = cartItemMapper.selectById(itemId);
        if (item == null || !item.getUserId().equals(userId)) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "购物车项不存在");
        }
        return item;
    }
}
