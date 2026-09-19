package com.mallx.inventory.common;

/**
 * 库存流水类型常量（inventory_logs.type）
 *
 * <p>⚠️ 列是 {@code VARCHAR(50)} 且【无 CHECK 约束】—— 写错字符串数据库不会拦你。
 * 与 {@code OrderStatus} 同一个理由：全项目必须只用这里的常量，禁止散落裸字符串
 * （否则会出现 {@code "ORDER_LOCK"} 与 {@code "ORDER_LOCKED"} 共存这种数据灾难）。
 *
 * <p>★ 三个常量与三个库存写点一一对应，不多不少：
 * <pre>
 *   ORDER_LOCK       deductStock       available - n , locked + n      （下单）
 *   PAY_SOLD         moveLockedToSold  locked - n    , sold + n        （支付）
 *   CANCEL_RELEASE   releaseLocked     locked - n    , available + n   （取消 / 超时关单）
 * </pre>
 *
 * <p>★★ 记住这张表就能推出流水里 {@code change_quantity} 的正负（流水记的是
 * {@code available_stock} 的变化，见 {@link com.mallx.inventory.entity.InventoryLog}）：
 * <pre>
 *   ORDER_LOCK       → available 减少 → change = -n
 *   PAY_SOLD         → available 不动 → change = 0   ← ★ 恒为 0，不是漏写
 *   CANCEL_RELEASE   → available 增加 → change = +n
 * </pre>
 * 所以「某条 {@code PAY_SOLD} 的 change ≠ 0」= 支付动了 {@code available_stock}
 * = Day 13 反复强调的那场事故。流水把这个不变量变成了可自动断言的检查。
 */
public final class InventoryLogType {

    /** 下单锁库：{@code available → locked}（Day 12） */
    public static final String ORDER_LOCK = "ORDER_LOCK";

    /** 支付转已售：{@code locked → sold}（Day 13，★ available 不动） */
    public static final String PAY_SOLD = "PAY_SOLD";

    /** 取消 / 超时关单回补：{@code locked → available}（Day 14） */
    public static final String CANCEL_RELEASE = "CANCEL_RELEASE";

    private InventoryLogType() {
    }
}
