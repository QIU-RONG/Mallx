package com.mallx.inventory.service.impl;

import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.mapper.InventoryMapper;
import com.mallx.inventory.service.InventoryService;
import org.springframework.stereotype.Service;

/**
 * 库存服务实现
 */
@Service
public class InventoryServiceImpl implements InventoryService {

    private final InventoryMapper inventoryMapper;

    public InventoryServiceImpl(InventoryMapper inventoryMapper) {
        this.inventoryMapper = inventoryMapper;
    }

    /**
     * ★ 这里【故意不加】{@code @Transactional}，理由有三：
     * <ol>
     *   <li>整段逻辑只有一条 UPDATE，它自身就是原子动作，无需再包一层事务；</li>
     *   <li>本方法是给「下单」调用的，事务边界应当由调用方（OrderService.createOrder）持有 ——
     *       让「扣库存 + 插订单 + 清购物车」共处一个事务才有意义；</li>
     *   <li>即便将来加了 {@code @Transactional}，默认传播行为也是 REQUIRED
     *       （有事务就加入、没有就新开），行为与本注释描述一致。</li>
     * </ol>
     * ⚠️ 反过来说：如果本方法自己偷偷提交（比如内部又开了 REQUIRES_NEW），
     * 下单失败时库存就回不来了 —— 这是绝不能碰的线。
     */
    @Override
    public void deductForOrder(Long skuId, int quantity) {
        int rows = inventoryMapper.deductStock(skuId, quantity);
        if (rows == 0) {
            // 0 行有两种可能：SKU 没有库存行，或 available_stock < quantity。
            // 对客户端而言都是「买不到」，统一报同一个错，不泄露内部结构。
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "库存不足");
        }
    }

    /**
     * 支付成功：{@code locked → sold}。
     *
     * <p>同样【故意不加】{@code @Transactional}：单条 UPDATE 自身即原子，
     * 事务边界应由调用方（PaymentService.pay）持有 ——
     * 让「插支付单 + 改订单状态 + 改 N 个 SKU 库存」共处一个事务才有意义。
     *
     * <p>★ 0 行是【服务端异常态】，不是用户错误：订单说「我锁定着 3 件」，库存说「我只锁着 1 件」。
     * 这种账对不上不可能靠重试解决，必须整笔回滚，所以用 {@code FAIL(500)} 而不是 {@code 400}。
     * （对比 {@code deductForOrder} 的 0 行 = 「库存不足」，那是正常的用户可理解结果。）
     */
    @Override
    public void moveLockedToSold(Long skuId, int quantity) {
        int rows = inventoryMapper.moveLockedToSold(skuId, quantity);
        if (rows == 0) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，支付已回滚");
        }
    }

    /**
     * 取消订单 / 超时关单：{@code locked → available}（{@code deductForOrder} 的逆操作）。
     *
     * <p>同样【故意不加】{@code @Transactional}：单条 UPDATE 自身即原子，
     * 事务边界应由调用方（{@code OrderServiceImpl.cancel}）持有 ——
     * 让「改订单状态 + 改 N 个 SKU 库存」共处一个事务才有意义。
     *
     * <p>★ 0 行与 {@code moveLockedToSold} 同类，是【服务端异常态】：
     * 订单说「我锁定着 3 件」，库存说「我只锁着 1 件」。账对不上，重试无意义，必须整笔回滚，
     * 所以用 {@code FAIL(500)} 而不是 {@code 400}。
     * 与 {@code deductForOrder} 的 0 行形成三足对照：
     * <pre>
     *   deductForOrder   0 行 = 库存不足（用户能理解）      → 400
     *   moveLockedToSold 0 行 = 账目不一致（服务端错）      → 500
     *   releaseLocked    0 行 = 账目不一致（服务端错）      → 500
     * </pre>
     */
    @Override
    public void releaseLocked(Long skuId, int quantity) {
        int rows = inventoryMapper.releaseLocked(skuId, quantity);
        if (rows == 0) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，取消已回滚");
        }
    }
}
