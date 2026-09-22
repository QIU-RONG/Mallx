package com.mallx.inventory.service;

import com.mallx.common.api.PageResult;
import com.mallx.inventory.vo.InventoryLogVO;
import com.mallx.inventory.vo.InventoryVO;

/**
 * 库存服务
 *
 * <p>★★ 四个写点，恒等式 {@code total = available + locked + sold} 全程不变：
 * <pre>
 *   Day 12  deductForOrder      available → locked        （下单）
 *   Day 13  moveLockedToSold    locked    → sold          （支付）
 *   Day 14  releaseLocked       locked    → available     （取消 / 超时关单）
 *   Day 17  adjust              total ±d , available ±d   （管理端人工调整）★ 新增
 * </pre>
 * ★ 前三个改的都是「货归哪一格」（总量不变），只有第四个改的是「一共有多少货」——
 * 它动 {@code total}，却仍然不破坏恒等式，因为 {@code available} 跟着动了同样的量。
 * 「改格子」与「改总量」是两件完全不同的事，混起来就是本日最容易犯的错。
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

    // ================== 管理端（Day 17 · 库存查询 / 调整 / 流水） ==================

    /**
     * ★ 管理端库存分页（JOIN 出 SKU 名与商品名，让列表自解释）。
     *
     * <p>★ 与上面三个写点最大的不同：本方法<b>不碰任何一行数据</b>，
     * 它只是把 {@code inventories} 的四格数字连同名称一起读出来。
     * 也正因为如此，它<b>不需要 {@code @Transactional}</b> ——
     * 「读一张表」的一致性由单条 SELECT 自己的快照保证。
     *
     * <p>★ 分页夹紧规则与前两个模块<b>逐字相同</b>（同一套实测依据）：
     * {@code size} 落在 1..100、{@code page} 归一到 ≥ 1，
     * ★ 夹紧必须写在 {@code new Page<>(...)} <b>之前</b>。
     *
     * @param page 页码，从 1 开始
     * @param size 每页条数，最终落在 1..100
     */
    PageResult<InventoryVO> listSkus(long page, long size);

    /**
     * ★★★ 管理端人工调整库存（Day 17 · <b>第四个写点</b>）。
     *
     * <p>★★ <b>本方法必须加 {@code @Transactional}</b> —— 它是两条语句：
     * 「改 {@code inventories}」+「写 {@code inventory_logs}」。
     * 没有事务兜底就会出现「库存改了、流水没写」这种账本与现值的静默分叉，
     * 而那正是流水表要防的事。
     * ⚠️ 传播行为用默认 {@code REQUIRED}，<b>绝不能</b> {@code REQUIRES_NEW}。
     * <p>★ 对照：{@code ship}（Day 15）当初不加事务，是因为它<b>只写一张表</b>。
     * 「要不要事务」的判据永远是<b>写点个数</b>，不是「这个方法重不重要」。
     *
     * <p>★ 调整语义 = 同向同量地改 {@code total} 与 {@code available}：
     * <pre>
     *   delta &gt; 0  补货 / 盘盈      delta &lt; 0  报损 / 盘亏
     * </pre>
     * <b>绝不碰 {@code locked} / {@code sold}</b>（那是已发生的业务事实）。
     *
     * <p>★ 校验分工（两条都写在实现里）：
     * <ol>
     *   <li>{@code delta == 0} → 400。⚠️ <b>这个判断在 Service 里</b>，
     *       不在 DTO 上 —— Jakarta 没有「不等于某值」的现成注解，
     *       而「delta 为 0 是一次无意义的改动」本质是<b>业务规则</b>，放这里更贴切；</li>
     *   <li>{@code reason} 的 {@code @NotBlank} 在 DTO 上（格式类校验留注解）。
     *       ⚠️ 本日 {@code reason} <b>只校验、不落库</b>（流水表没有备注列），
     *       这是显式取舍，见规划 §4.3。</li>
     * </ol>
     *
     * <p>★ 0 行（守卫不成立）→ 400「调整后可用/总库存不能为负」——
     * 这是<b>用户可理解的业务结果</b>，不是服务端账目不一致
     * （对比 {@link #moveLockedToSold} / {@link #releaseLocked} 的 0 行是 500）。
     * <p>★★ 本方法写一条 {@code ADMIN_ADJUST} 流水，
     * 其 {@code change = delta}、{@code reference_id = NULL}。
     *
     * @param skuId  SKU 主键
     * @param delta  带符号的变化量（必须非 0）
     * @param reason 调整理由（必填、≤200 字；本日只校验不落库）
     */
    void adjust(Long skuId, int delta, String reason);

    /**
     * ★ 管理端库存流水分页（可按 {@code skuId} / {@code type} 过滤）。
     *
     * <p>★ 只读接口，无事务。两张过滤条件都是<b>可选筛选</b>：
     * {@code skuId} 看某个 SKU 的来龙去脉、{@code type} 看某一类动作
     * （比如只看 {@code ADMIN_ADJUST} 就是一份「人工调整审计」）。
     *
     * <p>★ 流水表<b>只增不改</b>，所以本接口不需要（也不该有）任何写能力。
     * 它的用途只有两个：人工排查、以及<b>对账</b>——
     * Day 17 新加的那条守恒式正是靠它算出来的：
     * <pre>
     *   Σ(ADMIN_ADJUST.change) == 调整后的 total − 调整前的 total
     * </pre>
     *
     * <p>★ 分页夹紧规则同 {@link #listSkus}。
     * <p>⚠️ 排序必须显式写（{@code ORDER BY id DESC}）——
     * 不带排序的分页 = 随机翻页；流水按 id 倒序看，正好是「最近发生了什么」。
     *
     * @param skuId 可选的 SKU 过滤（null = 不筛）
     * @param type  可选的流水类型过滤（null / 空串 = 不筛），取值只用
     *              {@link com.mallx.inventory.common.InventoryLogType} 的四个常量
     * @param page  页码，从 1 开始
     * @param size  每页条数，最终落在 1..100
     */
    PageResult<InventoryLogVO> listLogs(Long skuId, String type, long page, long size);
}
