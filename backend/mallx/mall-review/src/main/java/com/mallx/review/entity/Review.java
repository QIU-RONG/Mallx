package com.mallx.review.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 商品评价（reviews）—— ★ Day 16 建模块，同时也是这张表<b>自 Day 03 建表以来的第一次使用</b>。
 *
 * <p>⚠️ 类名 {@code Review} 反推出来的默认表名是 {@code review}（少 s），
 * 真实表名是 {@code reviews} —— 必须显式写 {@code @TableName("reviews")}，
 * 否则所有 SQL 报「表不存在」。与 {@code Payment} / {@code Order} / {@code Inventory} 是同一个坑。
 *
 * <p>⚠️ 本表没有 {@code is_deleted} 列 —— 禁止加 {@code @TableLogic}。
 *
 * <p>★★ 本表在 Day 16 之前是「有 FK、但零唯一约束」的表：
 * <pre>
 *   约束：fk_review_user / fk_review_product / fk_review_order （3 个外键，只保证「对象存在」）
 *   ★ 它【拦不住】「同一个订单明细被评两次」—— 这一条是 Day 16 补的两条 DDL 才有的牙齿：
 *       ALTER TABLE reviews ALTER COLUMN order_item_id SET NOT NULL;
 *       ALTER TABLE reviews ADD CONSTRAINT uk_reviews_order_item UNIQUE (order_item_id);
 *   （见 backend/sql/04-review-constraints.sql；缺 NOT NULL 时 UNIQUE 会被 NULL 行绕过）
 * </pre>
 *
 * <p>★★ 三个「派生字段」—— 它们是本日的安全核心（见 docs/daily/Day-16-商品评价.md §3.1）：
 * <ul>
 *   <li>{@link #userId} ← 来自 token 的 principal，<b>绝不</b>从请求体读；</li>
 *   <li>{@link #orderId} ← 由 {@code orderItemId} 反查 {@code order_items}；</li>
 *   <li>{@link #productId} ← 同上。★ 若让客户端传 {@code product_id}，
 *       攻击者拿<b>自己一张合法的已完成订单</b>就能给<b>任意商品</b>刷五星 —— 一次下单刷遍全站。</li>
 * </ul>
 *
 * <p>★ 为什么不带 {@code images} 字段：本日不做晒图（需要图片上传接口，是独立的一步）。
 * 表里有这个 JSONB 列，但本模块既不读也不写，所以实体里干脆不映射它 ——
 * 少一个字段就少一条「不小心把 JSONB 当 String 写回去」的路径。
 * （对比：{@code mall-product} 里为 JSONB 备了 {@code JsonbMapTypeHandler}，
 *   而本模块刻意不依赖 {@code mall-product}。）
 *
 * <p>⚠️ 本实体的时间戳<b>不会</b>自动填：本日所有写入都走<b>自定义 XML</b>
 * （为了 {@code ON CONFLICT (order_item_id) DO NOTHING}），而自定义 XML 的 INSERT
 * <b>不走</b> {@code MetaObjectHandler}（{@code mall-server} 的 {@code MyMetaObjectHandler}）
 * ⇒ {@code created_at} / {@code updated_at} 必须在 XML 里手写。
 * 这里的 {@code @TableField(fill = ...)} 是为了将来有人用 {@code BaseMapper.insert} 时仍然对。
 */
@Data
@TableName("reviews")
public class Review {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** ★ 派生字段：来自 token 的 principal，客户端不能传 */
    private Long userId;

    /** ★★ 派生字段：由 orderItemId 反查 order_items —— 客户端绝不能传（防「一单刷全站」） */
    private Long productId;

    /** ★ 派生字段：由 orderItemId 反查 order_items */
    private Long orderId;

    /**
     * 评价的唯一入口：一条订单明细只能评一次。
     * ★ 本列 Day 16 起是 {@code NOT NULL} + {@code UNIQUE}（{@code uk_reviews_order_item}），
     * 缺任一条，「一明细一评」就没有牙齿。
     */
    private Long orderItemId;

    /** 评分 1..5（列是 SMALLINT，<b>无 CHECK 约束</b> → 范围只能靠应用层 {@code @Min/@Max} 守） */
    private Integer rating;

    /** 评价内容（列是 TEXT，<b>无长度上限</b> → 只能靠应用层 {@code @Size(max = 500)} 守） */
    private String content;

    /** 1 = 正常可见；本日固定写 1，列表查询一律带 {@code status = 1} */
    private Integer status;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
