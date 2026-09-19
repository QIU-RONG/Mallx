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
}
