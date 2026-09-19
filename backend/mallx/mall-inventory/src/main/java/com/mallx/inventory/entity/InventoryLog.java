package com.mallx.inventory.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 库存流水（inventory_logs）
 *
 * <p>三个库存写点每动一次库存，就往这里追加一条。它是 {@code inventories} 的
 * <b>只增不改的账本</b> —— 现值看 {@code inventories}，来龙去脉看这里。
 *
 * <p>★ 本表【没有 updated_at 列】：流水写下去就不该再改，只增不改才是账本。
 * 也【没有 is_deleted 列】—— 禁止加 {@code @TableLogic}。
 *
 * <p>★★ 口径（Day 14 §六 决策 ① 拍板）：{@code before_stock} / {@code after_stock}
 * 指的是 <b>{@code available_stock}</b>（可售库存），不是 {@code total_stock}。
 * 理由：{@code available_stock} 是用户唯一能感知的「还剩几件可买」；
 * 若指 {@code total}，三条流水的值会一模一样（total 从不被库存操作改动）→ 没有信息量。
 *
 * <p>★★ {@code change_quantity} 是<b>带符号</b>的，且恒等于 {@code after_stock - before_stock}
 * （不是「恒正 + 靠 type 表方向」）。由此得到一条可以直接断言的铁律：
 * <pre>
 *   ORDER_LOCK      change = -n   （available 减少）
 *   PAY_SOLD        change =  0   （available 不动 ← Day 13 的核心结论）
 *   CANCEL_RELEASE  change = +n   （available 增加）
 * </pre>
 * 任何一条 {@code PAY_SOLD} 的 change ≠ 0，都说明支付动了 {@code available_stock}，
 * 也就是把同一件货扣了两遍 —— 这是流水能自动抓住的、算术守恒抓不到的错误。
 *
 * <p>★★ {@code createdAt} <b>故意不挂</b> {@code @TableField(fill = ...)}：
 * MyBatis-Plus 的插入策略默认是 {@code NOT_NULL}（null 字段不进 INSERT 语句），
 * 所以留 null 就会走建表时的 {@code DEFAULT CURRENT_TIMESTAMP}，
 * 让流水时间与数据库时钟同一条时间轴。若挂上 fill，时间就变成「应用进程的钟」，
 * 两者在容器里并不保证一致，事后对账会平白多一个变量。
 *
 * <p>⚠️ 列名带下划线（{@code change_quantity} / {@code before_stock} / {@code after_stock} /
 * {@code reference_id} / {@code created_at}），MyBatis-Plus 默认
 * {@code tableUnderline = true} 会自动把驼峰转成下划线，不要手写 {@code @TableField}。
 *
 * <p>⚠️ {@code reference_id} 可空：三个写点里只有 {@code ORDER_LOCK} 拿不到订单 id
 * （下单流程是「先扣库存、后插订单」，扣库存时订单还不存在）—— 那种情况就写 NULL。
 */
@Data
@TableName("inventory_logs")
public class InventoryLog {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 被改的 SKU 主键 */
    private Long skuId;

    /** 变化量（★ 带符号，恒等于 afterStock - beforeStock） */
    private Integer changeQuantity;

    /** 变动前的 available_stock */
    private Integer beforeStock;

    /** 变动后的 available_stock（来自 UPDATE ... RETURNING） */
    private Integer afterStock;

    /** 流水类型，取值只用 {@link com.mallx.inventory.common.InventoryLogType} 里的常量 */
    private String type;

    /** 关联的订单 id（可空：下单锁库时订单尚未创建，写 NULL） */
    private Long referenceId;

    /** ★ 不挂 fill，留给 DB 的 DEFAULT CURRENT_TIMESTAMP */
    private LocalDateTime createdAt;
}
