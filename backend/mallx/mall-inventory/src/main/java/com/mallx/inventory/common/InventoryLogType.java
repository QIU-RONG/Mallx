package com.mallx.inventory.common;

/**
 * 库存流水类型常量（inventory_logs.type）
 *
 * <p>⚠️ 列是 {@code VARCHAR(50)} 且【无 CHECK 约束】—— 写错字符串数据库不会拦你。
 * 与 {@code OrderStatus} 同一个理由：全项目必须只用这里的常量，禁止散落裸字符串
 * （否则会出现 {@code "ORDER_LOCK"} 与 {@code "ORDER_LOCKED"} 共存这种数据灾难）。
 *
 * <p>★★ 四个常量与四个库存写点一一对应，不多不少：
 * <pre>
 *   ORDER_LOCK       deductStock       available - n , locked + n      （下单）
 *   PAY_SOLD         moveLockedToSold  locked - n    , sold + n        （支付）
 *   CANCEL_RELEASE   releaseLocked     locked - n    , available + n   （取消 / 超时关单）
 *   ADMIN_ADJUST     adjustStock       total + d , available + d       （管理端调整，Day 17）
 * </pre>
 * （★ 本行原先写「三个常量与三个库存写点」。Day 17 加了管理端调整这条路径，它必须跟着改 ——
 *   <b>说谎的注释比没有注释更坏</b>：下一个人会照着「只有三个写点」去找，
 *   然后漏掉 {@code ADMIN_ADJUST} 这条路径。这是本日唯一一处「改历史注释」，
 *   所以它值得被单独记一笔。）
 *
 * <p>★★ 记住这张表就能推出流水里 {@code change_quantity} 的正负（流水记的是
 * {@code available_stock} 的变化，见 {@link com.mallx.inventory.entity.InventoryLog}）：
 * <pre>
 *   ORDER_LOCK       → available 减少        → change = -n
 *   PAY_SOLD         → available 不动        → change = 0   ← ★ 恒为 0，不是漏写
 *   CANCEL_RELEASE   → available 增加        → change = +n
 *   ADMIN_ADJUST     → available 跟着 total 走 → change = ±d（带符号）
 * </pre>
 * 所以「某条 {@code PAY_SOLD} 的 change ≠ 0」= 支付动了 {@code available_stock}
 * = Day 13 反复强调的那场事故。流水把这个不变量变成了可自动断言的检查。
 *
 * <p>★★ {@code ADMIN_ADJUST} 是四条里<b>唯一会改 {@code total_stock} 的一条</b> ——
 * 这是它区别于其余三条的唯一特征，也是 Day 17 新对账式的全部依据：
 * <pre>
 *   Σ(ADMIN_ADJUST.change) == 调整后的 total − 调整前的 total
 * </pre>
 * 其余三条改的都是「货归哪一格」（{@code available} ↔ {@code locked} ↔ {@code sold}），
 * 总量<b>不变</b>。只有本类型改的是「仓库里到底有多少货」——
 * 「调整」这个词的语义正是这个。
 */
public final class InventoryLogType {

    /** 下单锁库：{@code available → locked}（Day 12） */
    public static final String ORDER_LOCK = "ORDER_LOCK";

    /** 支付转已售：{@code locked → sold}（Day 13，★ available 不动） */
    public static final String PAY_SOLD = "PAY_SOLD";

    /** 取消 / 超时关单回补：{@code locked → available}（Day 14） */
    public static final String CANCEL_RELEASE = "CANCEL_RELEASE";

    /**
     * ★★ 管理端人工调整：{@code total ±d , available ±d}（Day 17）
     * —— <b>四条里唯一会改 {@code total_stock} 的一条</b>。
     *
     * <p>★ {@code change_quantity} 记的是 {@code available} 的变化量，也就是 {@code ±d}
     * （因为 {@code available} 与 {@code total} 同向、同量移动）。
     *
     * <p>★ 对应流水的 {@code reference_id} 写 {@code NULL}：管理端调整没有关联订单 ——
     * 与 {@code ORDER_LOCK} 同一个理由。⚠️ 不是「拿不到」，是<b>本来就没有</b>。
     *
     * <p>⚠️ 本类型<b>绝不碰 {@code locked} / {@code sold}</b>：那两格记的是
     * <b>已发生的业务事实</b>（谁锁着、谁买过）。要把 {@code locked} 降下来，
     * 唯一合法的路径是「释放超时单」那条业务流程（它同时会改订单状态）；
     * 单独调 {@code locked} 等于让账本和事实脱钩。
     */
    public static final String ADMIN_ADJUST = "ADMIN_ADJUST";

    private InventoryLogType() {
    }
}
