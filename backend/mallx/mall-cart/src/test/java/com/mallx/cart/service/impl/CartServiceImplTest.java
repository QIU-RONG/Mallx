package com.mallx.cart.service.impl;

import com.mallx.cart.dto.CartAddDTO;
import com.mallx.cart.entity.CartItem;
import com.mallx.cart.mapper.CartItemMapper;
import com.mallx.cart.vo.CartItemVO;
import com.mallx.cart.vo.CartVO;
import com.mallx.cart.vo.SkuForCartVO;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ★ 购物车域单元测试（Day 48）。
 *
 * <hr>
 *
 * <p><b>为什么挑购物车</b>：{@code CartServiceImpl} 只依赖 <b>1 个</b>协作者
 * （{@code CartItemMapper}），是全部 12 个 Service 里依赖最少的一个 ——
 * 单测的成本与「要 mock 几个协作者」正相关。
 *
 * <p><b>本文件最值钱的三条</b>：
 * <ol>
 *   <li><b>G2「失效项即使勾选也不计入金额」</b> ——
 *       「用户不会为买不到的东西付钱」，这条错了会直接收错钱。</li>
 *   <li><b>G3「失效判定四选一，顺序即优先级」</b> ——
 *       一条数据同时满足两个失效原因时，显示的理由必须是<b>更根本的那一个</b>；
 *       这是纯判定逻辑，端到端只能看到「它失效了」，看不到「理由对不对」。</li>
 *   <li><b>H1「别人的购物车项 → 404 而不是 403」</b> ——
 *       403 等于告诉对方「这个 id 存在，只是不属于你」。
 *       这条是安全判定，必须有确定性测试锁住。</li>
 * </ol>
 *
 * <p>不启 Spring、不连库、不连 Redis：只 mock 一个 Mapper。
 */
@ExtendWith(MockitoExtension.class)
class CartServiceImplTest {

    @Mock
    private CartItemMapper cartItemMapper;

    @InjectMocks
    private CartServiceImpl service;

    private static final Long USER = 5L;
    private static final Long OTHER_USER = 999L;
    private static final Long SKU = 7L;

    // ==================================================================
    // 工具
    // ==================================================================

    /** 造一个「一切正常」的 SKU 快照 —— 各条测试在此基础上改一格。 */
    private SkuForCartVO okSku(int stock) {
        SkuForCartVO s = new SkuForCartVO();
        s.setSkuId(SKU);
        s.setSkuName("黑色 256GB");
        s.setPrice(new BigDecimal("100.00"));
        s.setSkuDeleted(0);          // 0 = 未删除（product_skus.is_deleted）
        s.setProductDeleted(0);      // 0 = 未删除（products.is_deleted）
        s.setProductStatus(1);       // 1 = 上架（products.status）
        s.setAvailableStock(stock);
        return s;
    }

    private CartAddDTO dto(int quantity) {
        CartAddDTO d = new CartAddDTO();
        d.setSkuId(SKU);
        d.setQuantity(quantity);
        return d;
    }

    /** 造一行购物车视图数据（getCart 的输入）。 */
    private CartItemVO item(int quantity, int stock, String price, boolean selected) {
        CartItemVO it = new CartItemVO();
        it.setId(1L);
        it.setSkuId(SKU);
        it.setProductId(3L);
        it.setProductName("测试商品");
        it.setQuantity(quantity);
        it.setSelected(selected);
        it.setAvailableStock(stock);
        it.setPrice(new BigDecimal(price));
        // 默认「未失效」三格
        it.setSkuDeleted(0);
        it.setProductDeleted(0);
        it.setProductStatus(1);
        return it;
    }

    /** 造一行「属于某个用户」的购物车行（requireOwn 的输入）。 */
    private CartItem ownedItem(Long userId, int quantity) {
        CartItem c = new CartItem();
        c.setId(42L);
        c.setUserId(userId);
        c.setSkuId(SKU);
        c.setQuantity(quantity);
        c.setSelected(true);
        return c;
    }

    // ==================================================================
    // [A] addToCart · 四个守卫（★ 顺序即优先级，别只测「能不能加」）
    // ==================================================================

    @Test
    @DisplayName("A1 SKU 不存在 → 404（★ 不是 400：查无此物是「没找到」，不是「你填错了」）")
    void addToCart_skuNotFound_is404() {
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.addToCart(USER, dto(1)));

        assertEquals(ResultCode.NOT_FOUND.getCode(), e.getCode());
        // ★ 第三条才是重点：异常码只说明「拒了」，never() 才说明「什么都没留下」
        verify(cartItemMapper, never()).insert(any(CartItem.class));
    }

    @Test
    @DisplayName("A2 规格已下架 → 400，且不写库")
    void addToCart_skuDeleted_is400() {
        SkuForCartVO sku = okSku(10);
        sku.setSkuDeleted(1);
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(sku);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.addToCart(USER, dto(1)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        verify(cartItemMapper, never()).insert(any(CartItem.class));
    }

    @Test
    @DisplayName("A3 商品已删除 → 400")
    void addToCart_productDeleted_is400() {
        SkuForCartVO sku = okSku(10);
        sku.setProductDeleted(1);
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(sku);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.addToCart(USER, dto(1)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        verify(cartItemMapper, never()).insert(any(CartItem.class));
    }

    @Test
    @DisplayName("A4 商品已下架（status != 1）→ 400")
    void addToCart_productOffline_is400() {
        SkuForCartVO sku = okSku(10);
        sku.setProductStatus(0);
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(sku);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.addToCart(USER, dto(1)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        verify(cartItemMapper, never()).insert(any(CartItem.class));
    }

    // ==================================================================
    // [B] addToCart · 合并与库存（★ 累加后超库存才是真陷阱）
    // ==================================================================

    @Test
    @DisplayName("B1 ★ 车里已有 2 件、再加 3 件 → 合并成 5 件（走 update 而不是 insert，不能出现两行）")
    void addToCart_existingItem_mergesQuantity() {
        SkuForCartVO sku = okSku(10);
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(sku);
        CartItem existing = ownedItem(USER, 2);
        when(cartItemMapper.selectOne(any())).thenReturn(existing);
        when(cartItemMapper.updateById(any(CartItem.class))).thenReturn(1);

        service.addToCart(USER, dto(3));

        ArgumentCaptor<CartItem> c = ArgumentCaptor.forClass(CartItem.class);
        verify(cartItemMapper).updateById(c.capture());
        assertEquals(5, c.getValue().getQuantity());
        // ★ 走了 update 就绝不能再 insert —— 否则同一 SKU 在车里出现两行
        verify(cartItemMapper, never()).insert(any(CartItem.class));
    }

    @Test
    @DisplayName("B2 ★★ 车里已有 3 件、库存只剩 4、再加 2 → 【合并后 5 > 4】必须被拒（★ 只看本次 quantity 会漏）")
    void addToCart_mergedExceedsStock_rejected() {
        SkuForCartVO sku = okSku(4);
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(sku);
        CartItem existing = ownedItem(USER, 3);
        when(cartItemMapper.selectOne(any())).thenReturn(existing);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.addToCart(USER, dto(2)));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        // 既没插新的、也没改旧的 —— 一次被拒的请求不该在库里留下任何痕迹
        verify(cartItemMapper, never()).insert(any(CartItem.class));
        // ⚠️ 必须是 any(CartItem.class) 而不是 any()：BaseMapper 同时有
        //   updateById(T) 与 updateById(Collection<T>) 两个重载，裸 any() 编译器无法选定。
        verify(cartItemMapper, never()).updateById(any(CartItem.class));
    }

    @Test
    @DisplayName("B3 新加入的项默认【已勾选】（selected = true）—— 否则用户加完还得手动勾一次")
    void addToCart_newItemDefaultsSelected() {
        SkuForCartVO sku = okSku(10);
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(sku);
        when(cartItemMapper.selectOne(any())).thenReturn(null);   // 车里还没有这个 SKU

        service.addToCart(USER, dto(2));

        ArgumentCaptor<CartItem> c = ArgumentCaptor.forClass(CartItem.class);
        verify(cartItemMapper).insert(c.capture());
        assertTrue(c.getValue().getSelected(), "新加入的项必须默认勾选");
        assertEquals(2, c.getValue().getQuantity());
        assertEquals(USER, c.getValue().getUserId());
    }

    // ==================================================================
    // [C] updateQuantity / removeItem · 归属与边界
    // ==================================================================

    @Test
    @DisplayName("C1 改数量超过实时库存 → 400（库存可能已被别人买走，所以必须【现查现比】）")
    void updateQuantity_exceedsStock_rejected() {
        when(cartItemMapper.selectById(42L)).thenReturn(ownedItem(USER, 2));
        when(cartItemMapper.selectSkuForCart(SKU)).thenReturn(okSku(3));   // 只剩 3 件

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.updateQuantity(USER, 42L, 5));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        // ★ 400 之前不许落库：否则用户看到失败、数量却已经变了
        // ⚠️ 必须是 any(CartItem.class) 而不是 any()：BaseMapper 同时有
        //   updateById(T) 与 updateById(Collection<T>) 两个重载，裸 any() 编译器无法选定。
        verify(cartItemMapper, never()).updateById(any(CartItem.class));
    }

    @Test
    @DisplayName("C2 重复删同一项第二次 → 404（cart_items 没有 is_deleted，是真 DELETE）")
    void removeItem_twice_secondIs404() {
        CartItem owned = ownedItem(USER, 2);
        // 第一次有值，第二次查不到（已被真删）
        when(cartItemMapper.selectById(42L)).thenReturn(owned, null);

        service.removeItem(USER, 42L);                       // 第一次：正常删
        verify(cartItemMapper).deleteById(42L);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.removeItem(USER, 42L));        // 第二次：404
        assertEquals(ResultCode.NOT_FOUND.getCode(), e.getCode());
        // ★ 第二次【没有再删一次】—— 幂等性：重复调用的净效果与一次相同
        verify(cartItemMapper, times(1)).deleteById(42L);
    }

    // ==================================================================
    // [D] requireOwn · IDOR 防线（★ 本文件的安全底线）
    // ==================================================================

    @Test
    @DisplayName("H1 ★★ 改【别人】的购物车项 → 404，且绝不能是 403（403 会泄露「这个 id 存在」）")
    void updateQuantity_otherUsersItem_is404Not403() {
        when(cartItemMapper.selectById(42L)).thenReturn(ownedItem(OTHER_USER, 2));

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.updateQuantity(USER, 42L, 1));

        assertEquals(ResultCode.NOT_FOUND.getCode(), e.getCode(),
                "★ 必须是 404 而不是 403：403 等于告诉攻击者「这个 id 有效，只是不属于你」");
        // ★★ 这一步才是「越权没成功」的证据 —— 光看异常码，行被改了也看不出来
        // ⚠️ 必须是 any(CartItem.class) 而不是 any()：BaseMapper 同时有
        //   updateById(T) 与 updateById(Collection<T>) 两个重载，裸 any() 编译器无法选定。
        verify(cartItemMapper, never()).updateById(any(CartItem.class));
    }

    @Test
    @DisplayName("H2 ★★ 删【别人】的购物车项 → 404，且绝不能真删掉（requireOwn 的第二种用法）")
    void removeItem_otherUsersItem_is404AndNotDeleted() {
        when(cartItemMapper.selectById(42L)).thenReturn(ownedItem(OTHER_USER, 2));

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.removeItem(USER, 42L));

        assertEquals(ResultCode.NOT_FOUND.getCode(), e.getCode(),
                "★ 与 H1 同一条理由：404 而不是 403，不泄露「这个 id 存在」");
        // ★★ 删除是【不可逆】的：光看异常码不够，必须证明那行没被删掉
        verify(cartItemMapper, never()).deleteById(anyLong());
    }

    // ==================================================================
    // [E] getCart · 失效判定与合计口径（★ 本文件最值钱的两条）
    // ==================================================================

    @Test
    @DisplayName("G2 ★★★ 失效项【即使勾选了】也不计入 selectedQuantity / selectedAmount —— 用户不会为买不到的东西付钱")
    void getCart_invalidItem_excludedFromSelectedTotals() {
        CartItemVO valid = item(2, 10, "10", true);      // 有效 + 已勾选
        CartItemVO invalid = item(3, 0, "10", true);     // 库存不足 → 失效，但用户勾着它
        when(cartItemMapper.selectCartView(USER)).thenReturn(Arrays.asList(valid, invalid));

        CartVO vo = service.getCart(USER);

        // ★★ 这一对才完整：只断言 selected 会漏掉「总量口径被误改成不含失效项」
        assertEquals(5, vo.getTotalQuantity(), "总量【包含】失效项");
        assertEquals(2, vo.getSelectedQuantity(), "勾选量【不含】失效项（3 件买不到的不算）");
        assertEquals(0, vo.getSelectedAmount().compareTo(new BigDecimal("20.00")),
                "勾选金额只算有效的那 2 件（20.00），不含失效的 3 件（30.00）");
        assertTrue(invalid.isInvalid(), "库存不足的那行必须被标记为失效");
    }

    @Test
    @DisplayName("G3 ★★ 失效判定四选一：同时满足两个原因时，显示的理由是【更根本的那一个】（顺序即优先级）")
    void getCart_invalidReasonPicksMostFundamental() {
        CartItemVO both = item(1, 10, "10", false);
        both.setProductDeleted(1);     // 商品已删除
        both.setProductStatus(0);      // 同时「商品已下架」
        when(cartItemMapper.selectCartView(USER)).thenReturn(Collections.singletonList(both));

        CartVO vo = service.getCart(USER);

        assertEquals("商品已删除", vo.getItems().get(0).getInvalidReason(),
                "★ 删除比下架更根本 ⇒ 必须显示「商品已删除」；反过来就是把优先级写反了");
        // 失效项不计入任何勾选统计
        assertEquals(0, vo.getSelectedQuantity());
        assertEquals(1, vo.getTotalQuantity(), "失效项仍计入总量");
    }

    @Test
    @DisplayName("G4 小计 = 【实时价 × 数量】，服务端算（★ 客户端传什么都不算数）")
    void getCart_subtotalComputedServerSide() {
        CartItemVO it = item(3, 10, "12.5", true);
        when(cartItemMapper.selectCartView(USER)).thenReturn(Collections.singletonList(it));

        CartVO vo = service.getCart(USER);

        // ★ BigDecimal 用 compareTo 不用 equals —— 标度不同 equals 会假红
        assertEquals(0, vo.getItems().get(0).getSubtotal().compareTo(new BigDecimal("37.50")));
        assertEquals(0, vo.getSelectedAmount().compareTo(new BigDecimal("37.50")));
    }

    @Test
    @DisplayName("G5 空购物车：三个合计都是 0 / 空列表（★ 断言「不炸」比断言数值更重要）")
    void getCart_emptyCart_returnsZeroTotals() {
        when(cartItemMapper.selectCartView(USER)).thenReturn(Collections.emptyList());

        CartVO vo = service.getCart(USER);

        assertNotNull(vo);
        assertTrue(vo.getItems().isEmpty());
        assertEquals(0, vo.getTotalQuantity());
        assertEquals(0, vo.getSelectedQuantity());
        assertEquals(0, vo.getSelectedAmount().compareTo(BigDecimal.ZERO));
    }

    @Test
    @DisplayName("G6 未勾选的项计入总量、不计入勾选统计（★ 勾选是用户意图，不是失效 —— 两个独立判定）")
    void getCart_unselectedItem_countsInTotalOnly() {
        CartItemVO unselected = item(4, 10, "10", false);
        when(cartItemMapper.selectCartView(USER)).thenReturn(Collections.singletonList(unselected));

        CartVO vo = service.getCart(USER);

        assertFalse(unselected.isInvalid(), "没勾选 ≠ 失效 —— 这是两个独立的判定");
        assertEquals(4, vo.getTotalQuantity());
        assertEquals(0, vo.getSelectedQuantity());
        assertEquals(0, vo.getSelectedAmount().compareTo(BigDecimal.ZERO));
    }
}
