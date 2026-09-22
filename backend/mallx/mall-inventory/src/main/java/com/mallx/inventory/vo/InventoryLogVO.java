package com.mallx.inventory.vo;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 库存流水行（{@code GET /api/admin/inventory/logs} 的 records 元素）。
 *
 * <p>★ 字段集与 {@code InventoryLog} 实体一一对应 —— 这张表<b>只增不改</b>，
 * 没有需要屏蔽的内部列（对比 {@code OrderVO} 要藏 {@code userId}、
 * {@code InventoryVO} 要不藏），所以出参白名单与实体恰好同形。
 * <p>★ 即便如此，仍然单独建 VO 而不直接把实体交出去：实体是表结构的镜像，
 * 表加一列接口就跟着变。显式列一遍是「出参白名单」的纪律，不是形式主义。
 *
 * <p>★★ 读这张表要记住它的口径（Day 14 拍板，Day 17 沿用）：
 * <pre>
 *   before_stock / after_stock  指的是【available_stock】（可售），不是 total
 *   change_quantity             带符号，恒等于 after_stock - before_stock
 * </pre>
 * 于是四类流水各自的长相（★ 这是可以直接断言的，不是描述）：
 * <pre>
 *   ORDER_LOCK      change = -n
 *   PAY_SOLD        change =  0   ← available 不动，before == after
 *   CANCEL_RELEASE  change = +n
 *   ADMIN_ADJUST    change = ±d   ← ★ Day 17 新增；四条里唯一动了 total 的一条
 * </pre>
 *
 * <p>⚠️ 用作 {@code resultType} 时必须有无参构造（同 {@link InventoryVO} 的说明）。
 *
 * <p>⚠️ 只读接口：本 VO 没有 setter 之外的东西，但被映射出来后<b>不参与任何写回</b> ——
 * 流水表「只增不改不删」是纪律，不要拿查出来的 VO 去做 update。
 */
@Data
@NoArgsConstructor
public class InventoryLogVO {

    private Long id;

    private Long skuId;

    /** 流水类型，取值只用 {@code InventoryLogType} 的四个常量之一 */
    private String type;

    /** 带符号的变化量（记的是 available_stock 的变化） */
    private Integer changeQuantity;

    /** 变动前的 available_stock */
    private Integer beforeStock;

    /** 变动后的 available_stock（来自 UPDATE ... RETURNING） */
    private Integer afterStock;

    /** 关联订单 id；{@code ORDER_LOCK} 与 {@code ADMIN_ADJUST} 为 null（本来就没有） */
    private Long referenceId;

    private LocalDateTime createdAt;
}
