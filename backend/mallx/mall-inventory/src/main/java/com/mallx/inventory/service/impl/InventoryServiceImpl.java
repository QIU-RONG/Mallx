package com.mallx.inventory.service.impl;

import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.common.InventoryLogType;
import com.mallx.inventory.entity.InventoryLog;
import com.mallx.inventory.mapper.InventoryLogMapper;
import com.mallx.inventory.mapper.InventoryMapper;
import com.mallx.inventory.service.InventoryService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 库存服务实现
 *
 * <hr>
 *
 * <p>★★ Day 14 起，三个方法【都加了 {@code @Transactional}】——
 * 这里要说明清楚为什么<b>理由变了</b>，否则容易照着旧注释把注解删掉：
 * <pre>
 *   Day 12 / 13 的旧理由：「整段逻辑只有一条 UPDATE，它自身就是原子动作，无需再包一层事务」
 *   Day 14 起失效：    现在每条路径都是【两条语句】—— 先 UPDATE 库存，再 INSERT 流水
 * </pre>
 * 两条语句之间一旦没有事务兜底，就会出现「库存改了、流水没写」这种账本与现值的静默分叉，
 * 而这正是 {@code inventory_logs} 要防的事。<b>加了流水，就必须有事务。</b>
 *
 * <p>★ 传播行为用默认的 {@code REQUIRED}（有事务就加入、没有就新开）：
 * 调用方（{@code OrderServiceImpl} / {@code PaymentServiceImpl} / {@code OrderCancelExecutor}）
 * 都持有事务，所以「改订单状态 + 改 N 个 SKU 库存 + 写 N 条流水」共处一个事务，
 * 任何一步失败整笔回滚 —— 第 2 步的实验里已经实测过这个行为（一个 HTTP 请求写三张表是一个事务）。
 *
 * <p>⚠️ <b>绝不能改成 {@code REQUIRES_NEW}</b>：那样本方法会自己提交，
 * 调用方后续失败时库存就回不来了 —— 这是绝不能碰的线。
 */
@Service
public class InventoryServiceImpl implements InventoryService {

    private final InventoryMapper inventoryMapper;
    private final InventoryLogMapper inventoryLogMapper;

    public InventoryServiceImpl(InventoryMapper inventoryMapper,
                                InventoryLogMapper inventoryLogMapper) {
        this.inventoryMapper = inventoryMapper;
        this.inventoryLogMapper = inventoryLogMapper;
    }

    /**
     * 下单扣减：{@code available → locked}，并写一条 {@code ORDER_LOCK} 流水。
     *
     * <p>★ {@code reference_id} 写 NULL：下单是「先扣库存（⑤）、后插订单（⑥）」，
     * 走到这里时订单还不存在。这是流程顺序决定的，不是漏写。
     */
    @Override
    @Transactional
    public void deductForOrder(Long skuId, int quantity) {
        Integer after = inventoryMapper.deductStock(skuId, quantity);
        if (after == null) {
            // 返回 null = 影响 0 行，有两种可能：SKU 没有库存行，或 available_stock < quantity。
            // 对客户端而言都是「买不到」，统一报同一个错，不泄露内部结构。
            // ★ 此刻还没有写流水，抛异常让整个事务回滚，不会留下孤儿流水。
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "库存不足");
        }
        // available 减少了 quantity，所以 change = -quantity
        writeLog(skuId, InventoryLogType.ORDER_LOCK, -quantity, after, null);
    }

    /**
     * 支付成功：{@code locked → sold}，并写一条 {@code PAY_SOLD} 流水。
     *
     * <p>★ 0 行是【服务端异常态】，不是用户错误：订单说「我锁定着 3 件」，库存说「我只锁着 1 件」。
     * 这种账对不上不可能靠重试解决，必须整笔回滚，所以用 {@code FAIL(500)} 而不是 {@code 400}。
     * （对比 {@code deductForOrder} 的 0 行 = 「库存不足」，那是正常的用户可理解结果。）
     *
     * <p>★★ 本方法写出的流水 {@code change_quantity} <b>恒为 0</b>（{@code before == after}）：
     * 因为 {@code moveLockedToSold} 压根不碰 {@code available_stock}。
     * 这不是「没记到东西」—— 它恰恰是 Day 13 那条铁律的可审计化：
     * <b>「PAY_SOLD 的 change 必须是 0」，一旦不为 0，就说明支付动了 available，
     * 也就是同一件货被扣了两遍。</b>
     */
    @Override
    @Transactional
    public void moveLockedToSold(Long skuId, int quantity, Long orderId) {
        Integer after = inventoryMapper.moveLockedToSold(skuId, quantity);
        if (after == null) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，支付已回滚");
        }
        // available 一动不动，所以 change = 0（RETURNING 出来的值就是转移前的值）
        writeLog(skuId, InventoryLogType.PAY_SOLD, 0, after, orderId);
    }

    /**
     * 取消订单 / 超时关单：{@code locked → available}（{@code deductForOrder} 的逆操作），
     * 并写一条 {@code CANCEL_RELEASE} 流水。
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
    @Transactional
    public void releaseLocked(Long skuId, int quantity, Long orderId) {
        Integer after = inventoryMapper.releaseLocked(skuId, quantity);
        if (after == null) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，取消已回滚");
        }
        // available 增加了 quantity，所以 change = +quantity
        writeLog(skuId, InventoryLogType.CANCEL_RELEASE, quantity, after, orderId);
    }

    // ============================ 私有工具 ============================

    /**
     * 追加一条库存流水。
     *
     * <p>★★ 注意 {@code beforeStock} 是<b>算出来的</b>（{@code after - change}），不是单独查出来的。
     * 这样写有两个好处：
     * <ol>
     *   <li>恒等式 {@code change == after - before} <b>由构造保证</b>，不可能写歪 ——
     *       如果改成让调用方分别传 before 和 after，就有机会传成自相矛盾的一对值；</li>
     *   <li>不需要为了拿 before 而多一次 SELECT（那正是 Day 14 §六 否掉的方案 A/B）。</li>
     * </ol>
     *
     * <p>★ {@code createdAt} 故意留 null：MyBatis-Plus 插入策略默认 {@code NOT_NULL}
     * （null 字段不进 INSERT），于是走建表时的 {@code DEFAULT CURRENT_TIMESTAMP}，
     * 让流水时间与数据库时钟同一条时间轴。
     *
     * @param skuId      被改的 SKU
     * @param type       流水类型，只用 {@link InventoryLogType} 的常量
     * @param change     带符号的变化量（ORDER_LOCK 为负、PAY_SOLD 为 0、CANCEL_RELEASE 为正）
     * @param after      UPDATE ... RETURNING 拿到的更新后 available_stock
     * @param referenceId 关联订单 id，可为 null
     */
    private void writeLog(Long skuId, String type, int change, int after, Long referenceId) {
        InventoryLog log = new InventoryLog();
        log.setSkuId(skuId);
        log.setType(type);
        log.setChangeQuantity(change);
        log.setAfterStock(after);
        log.setBeforeStock(after - change);
        log.setReferenceId(referenceId);
        inventoryLogMapper.insert(log);
    }
}
