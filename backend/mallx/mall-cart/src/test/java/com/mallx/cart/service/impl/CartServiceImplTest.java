package com.mallx.cart.service.impl;

import com.mallx.cart.dto.CartAddDTO;
import com.mallx.cart.entity.CartItem;
import com.mallx.cart.mapper.CartItemMapper;
import com.mallx.cart.vo.CartItemVO;
import com.mallx.cart.vo.CartVO;
import com.mallx.cart.vo.SkuForCartVO;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import org.junit.jupiter.api.Disabled;
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
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ★ 购物车域单元测试（Day 48）—— 【骨架】，方法体由你写。
 *
 * <hr>
 *
 * <p><b>为什么挑购物车当第一块</b>：{@code CartServiceImpl} 只依赖 <b>1 个</b>协作者
 * （{@code CartItemMapper}），是全部 12 个 Service 里依赖最少的一个 ——
 * 单测的成本与「要 mock 几个协作者」正相关，先挑便宜的练手。
 *
 * <p><b>填之前先看这三处源码</b>（骨架写不出断言，是因为还没读实现）：
 * <ol>
 *   <li>{@code CartServiceImpl#addToCart} —— 四个守卫的<b>顺序</b>就是优先级</li>
 *   <li>{@code CartServiceImpl#getCart} —— 失效判定 + 三个合计口径</li>
 *   <li>{@code CartServiceImpl#requireOwn} —— 私有方法，但它的判定是本项目 IDOR 防线的样板</li>
 * </ol>
 *
 * <p>★ <b>本文件最值钱的三条</b>（其余都是配角）：
 * <ol>
 *   <li><b>G2「失效项即使勾选也不计入金额」</b> ——
 *       「用户不会为买不到的东西付钱」，这条错了会直接收错钱，而端到端
 *       要造一个「失效 + 已勾选」的组合才看得见。</li>
 *   <li><b>G3「失效判定四选一，顺序即优先级」</b> ——
 *       一条数据同时满足两个失效原因时，显示的理由必须是<b>更根本的那一个</b>；
 *       这是纯判定逻辑，端到端只能看到"它失效了"，看不到"理由对不对"。</li>
 *   <li><b>H1「别人的购物车项 → 404 而不是 403」</b> ——
 *       403 等于告诉对方「这个 id 存在，只是不属于你」。
 *       这条是安全判定，<b>必须有确定性测试锁住</b>，不能只靠端到端。</li>
 * </ol>
 *
 * <p>⚠️ 骨架期这 12 条<b>全是红的</b>（{@code UnsupportedOperationException}）——
 * 那是「正确长相」。判定标准不是「编译通过」，是<b>每一条都能说出它拦住了什么</b>。
 * 填完一条就跑一次，别攒着。
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
    // [A] addToCart · 四个守卫（★ 顺序即优先级，别只测「能不能加」）
    // ==================================================================

    /** 造一个「一切正常」的 SKU 快照 —— 各条测试在此基础上改一格。
     *  ★ 先去 {@code SkuForCartVO} 里确认 setter 名（skuDeleted / productDeleted /
     *    productStatus / availableStock），骨架里故意没写死，逼你去读一眼实体。 */
    private SkuForCartVO okSku(int stock) {
        SkuForCartVO s = new SkuForCartVO();
        // TODO: 你来写 —— 置 productStatus = 1、skuDeleted = 0、productDeleted = 0、availableStock = stock
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.okSku");
    }

    private CartAddDTO dto(int quantity) {
        CartAddDTO d = new CartAddDTO();
        d.setSkuId(SKU);
        d.setQuantity(quantity);
        return d;
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("A1 SKU 不存在 → 404（★ 不是 400：查无此物是「没找到」，不是「你填错了」）")
    void addToCart_skuNotFound_is404() {
        // TODO: 你来写 —— stub selectSkuForCart 返回 null；
        //       断言抛 BusinessException 且 code == ResultCode.NOT_FOUND.getCode()；
        //       再断言【没有发生任何写】（verify(cartItemMapper, never()).insert(any())）
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_skuNotFound_is404");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("A2 规格已下架 → 400，且不写库")
    void addToCart_skuDeleted_is400() {
        // TODO: 你来写 —— okSku 里把 skuDeleted 置 1
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_skuDeleted_is400");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("A3 商品已删除 → 400")
    void addToCart_productDeleted_is400() {
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_productDeleted_is400");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("A4 商品已下架（status != 1）→ 400")
    void addToCart_productOffline_is400() {
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_productOffline_is400");
    }

    // ==================================================================
    // [B] addToCart · 合并与库存（★ 累加后超库存才是真陷阱）
    // ==================================================================

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("B1 ★ 车里已有 2 件、再加 3 件 → 合并成 5 件（走 update 而不是 insert，不能出现两行）")
    void addToCart_existingItem_mergesQuantity() {
        // TODO: 你来写 —— stub selectOne 返回已有 CartItem(quantity=2)；
        //       调用后：verify(cartItemMapper).updateById(captor.capture()) 断言 quantity == 5；
        //       并且 verify(cartItemMapper, never()).insert(any())
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_existingItem_mergesQuantity");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("B2 ★★ 车里已有 3 件、库存只剩 4、再加 2 → 【合并后 5 > 4】必须被拒（★ 只看本次 quantity 会漏）")
    void addToCart_mergedExceedsStock_rejected() {
        // TODO: 你来写 —— 这条是 B1 的反面：守卫比的是 merged 而不是 dto.getQuantity()。
        //       断言 400 且既没 insert 也没 updateById
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_mergedExceedsStock_rejected");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("B3 新加入的项默认【已勾选】（selected = true）—— 否则用户加完还得手动勾一次")
    void addToCart_newItemDefaultsSelected() {
        // TODO: 你来写 —— 用 ArgumentCaptor<CartItem> 抓 insert 的参数断言 selected == true
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.addToCart_newItemDefaultsSelected");
    }

    // ==================================================================
    // [C] updateQuantity / removeItem · 归属与边界
    // ==================================================================

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("C1 改数量超过实时库存 → 400（库存可能已被别人买走，所以必须【现查现比】）")
    void updateQuantity_exceedsStock_rejected() {
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.updateQuantity_exceedsStock_rejected");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("C2 重复删同一项第二次 → 404（cart_items 没有 is_deleted，是真 DELETE）")
    void removeItem_twice_secondIs404() {
        // TODO: 你来写 —— 第一次 stub 有值、第二次 stub 返回 null（用 when(...).thenReturn(a, null) 或两次 when）
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.removeItem_twice_secondIs404");
    }

    // ==================================================================
    // [D] requireOwn · IDOR 防线（★ 本文件的安全底线）
    // ==================================================================

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("H1 ★★ 改【别人】的购物车项 → 404，且绝不能是 403（403 会泄露「这个 id 存在」）")
    void updateQuantity_otherUsersItem_is404Not403() {
        // TODO: 你来写 —— stub selectById 返回一个 userId = OTHER_USER 的 CartItem；
        //       断言 code == ResultCode.NOT_FOUND.getCode()；
        //       ★ 再断言【没有发生任何写】：verify(cartItemMapper, never()).updateById(any())
        //         这一步才是「越权没成功」的证据 —— 光看异常码，被改了也看不出来
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.updateQuantity_otherUsersItem_is404Not403");
    }

    // ==================================================================
    // [E] getCart · 失效判定与合计口径（★ 本文件最值钱的两条）
    // ==================================================================

    /** 造一行购物车视图数据。★ 先去 {@code CartItemVO} 确认字段与 setter。 */
    private CartItemVO item(int quantity, int stock, String price, boolean selected) {
        // TODO: 你来写 —— 置 quantity / availableStock / price / selected，
        //       并把「未失效」的三格置为正常（skuDeleted=0、productDeleted=0、productStatus=1）
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.item");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("G2 ★★★ 失效项【即使勾选了】也不计入 selectedQuantity / selectedAmount —— 用户不会为买不到的东西付钱")
    void getCart_invalidItem_excludedFromSelectedTotals() {
        // TODO: 你来写 —— 两行：一行有效（qty=2, price=10, selected=true）、
        //       一行失效且 selected=true（qty=3, price=10, stock=0 → 库存不足）；
        //       断言 selectedQuantity == 2（不含 3）、selectedAmount == 20.00（不含 30）；
        //       ★ 同时断言 totalQuantity == 5（总量【包含】失效项）—— 这一对才完整：
        //         只断言 selected 会漏掉「总量口径被误改成不含失效项」
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.getCart_invalidItem_excludedFromSelectedTotals");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("G3 ★★ 失效判定四选一：同时满足两个原因时，显示的理由是【更根本的那一个】（顺序即优先级）")
    void getCart_invalidReasonPicksMostFundamental() {
        // TODO: 你来写 —— 造一行同时 productDeleted=1 且 productStatus=0 的数据；
        //       断言 invalidReason 是「商品已删除」而不是「商品已下架」
        //       （删除比下架更根本；反过来就等于把优先级写反了）
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.getCart_invalidReasonPicksMostFundamental");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("G4 小计 = 【实时价 × 数量】，服务端算（★ 客户端传什么都不算数）")
    void getCart_subtotalComputedServerSide() {
        // TODO: 你来写 —— stub selectCartView 返回一行（price=12.5, quantity=3）；
        //       断言该行的 subtotal == 37.50（用 BigDecimal 的 compareTo，别用 equals —— 标度不同会假红）
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.getCart_subtotalComputedServerSide");
    }

    @Disabled("TODO: 骨架 —— 填完这个方法就删掉这一行")
    @Test
    @DisplayName("G5 空购物车：三个合计都是 0 / 空列表（★ 断言「不炸」比断言数值更重要）")
    void getCart_emptyCart_returnsZeroTotals() {
        // TODO: 你来写 —— stub 返回空列表；断言 totalQuantity==0、selectedQuantity==0、
        //       selectedAmount 与 BigDecimal.ZERO 相等（compareTo == 0）
        throw new UnsupportedOperationException("TODO: CartServiceImplTest.getCart_emptyCart_returnsZeroTotals");
    }
}
