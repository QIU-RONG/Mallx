package com.mallx.inventory.service;

/**
 * 库存服务
 *
 * <p>三个写点构成完整闭环，恒等式 {@code total = available + locked + sold} 全程不变：
 * <pre>
 *   Day 12  deductForOrder      available → locked   （下单）
 *   Day 13  moveLockedToSold    locked    → sold     （支付）
 *   Day 14  releaseLocked       locked    → available（取消 / 超时关单）
 * </pre>
 *
 * <p>★ {@code available_stock} 一生只被改两次：下单时减、取消时加。
 * 支付（{@code moveLockedToSold}）绝不碰它 —— 碰了就等于把同一件货扣两遍。
 *
 * <p>★ 三个方法的「0 行」含义各不相同，判错就会把用户错误报成系统故障（或反之）：
 * {@code deductForOrder} 的 0 行是「库存不足」（400），
 * 另外两个的 0 行是「订单与库存对不上账」（500）—— 详见各自 Javadoc。
 *
 * <hr>
 *
 * <p>★★ Day 14 起三个方法各写一条 {@code inventory_logs} 流水，
 * 且都在自己的 {@code @Transactional} 里（更新库存 + 写流水两条语句必须同生共死）。
 * 事务边界仍由调用方持有 —— 本服务用的是默认传播行为 {@code REQUIRED}（有事务就加入），
 * 所以「改订单状态 + 改 N 个 SKU 库存 + 写 N 条流水」依旧共处一个事务。
 * ⚠️ <b>绝不能改成 {@code REQUIRES_NEW}</b>：那样本方法会自己提交，
 * 调用方后续失败时库存就回不来了。
 *
 * <p>★★ {@code orderId} 参数只有后两个方法有，{@code deductForOrder} 没有 —— 这是
 * <b>流程顺序</b>决定的，不是漏写：下单是「先扣库存（⑤）、后插订单（⑥）」，
 * 走到扣库存时订单还不存在，没有 id 可记，所以 {@code ORDER_LOCK} 流水的
 * {@code reference_id} 写 NULL。
 */
public interface InventoryService {

    /**
     * 下单扣减：把 {@code quantity} 个从可售挪进锁定。
     *
     * <p>库存不足时抛业务异常（HTTP 200 + body.code=400，本项目约定 —— 判成功看 code）。
     *
     * <p>★ 本方法写一条 {@code ORDER_LOCK} 流水，{@code reference_id} 为 NULL（见类注释）。
     *
     * @param skuId    SKU 主键
     * @param quantity 扣减数量（必须 &gt; 0）
     */
    void deductForOrder(Long skuId, int quantity);

    /**
     * 支付成功：把 {@code quantity} 个从锁定挪进已售。
     *
     * <p>★ 只动 {@code locked_stock} 和 {@code sold_stock}，<b>{@code available_stock} 不变</b>。
     * 调用方（支付服务）持有的订单必须仍处于「待支付」—— 这是「一单只付一次」在库存侧的对偶保证。
     *
     * <p>返回 0 行意味着锁定库存不够（订单与库存对不上账），属服务端异常态，
     * 抛业务异常让整笔支付事务回滚。
     *
     * <p>★ 本方法写一条 {@code PAY_SOLD} 流水。因为 {@code available} 不动，
     * 这条流水的 {@code change_quantity} <b>恒为 0</b>、{@code before == after} ——
     * 这是可自动断言的铁律，不是「没记到东西」。
     *
     * @param skuId    SKU 主键
     * @param quantity 转移数量（必须 &gt; 0）
     * @param orderId  关联订单 id（写入流水 {@code reference_id}）
     */
    void moveLockedToSold(Long skuId, int quantity, Long orderId);

    /**
     * 取消订单 / 超时关单：把 {@code quantity} 个从锁定退回可售。
     *
     * <p>★ 与 {@link #deductForOrder} 是<b>严格逆操作</b>：
     * {@code deductForOrder} 做 {@code available → locked}，本方法做 {@code locked → available}。
     * 两处合起来保证「下单锁的货，取消后一件不少地回到可售池」。
     *
     * <p>★ 守卫是 {@code locked_stock >= quantity}（不是 {@code available_stock}）——
     * 要动的那一格是 {@code locked}，就判 {@code locked}。
     *
     * <p>★ 0 行 = 账目不一致（订单说锁着 3 件、库存说只有 1 件），属服务端异常态，
     * 抛业务异常让整笔取消事务回滚 —— 与 {@link #moveLockedToSold} 的 0 行同类，
     * 而与 {@link #deductForOrder} 的 0 行（库存不足 = 用户可理解的结果）不同。
     *
     * <p>★ 本方法写一条 {@code CANCEL_RELEASE} 流水，{@code change_quantity = +quantity}。
     *
     * @param skuId    SKU 主键
     * @param quantity 退还数量（必须 &gt; 0）
     * @param orderId  关联订单 id（写入流水 {@code reference_id}）
     */
    void releaseLocked(Long skuId, int quantity, Long orderId);
}
