package com.mallx.inventory.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.inventory.entity.Inventory;

import org.apache.ibatis.annotations.Param;

/**
 * 库存 Mapper
 *
 * <p>{@link BaseMapper} 提供全套单表 CRUD；扣库存这种「原子动作」走 XML 手写 SQL。
 *
 * <p>⚠️ 铁律：这里声明的 {@code deductStock}，{@code InventoryMapper.xml} 里必须有同名
 * {@code <select id="deductStock">}，否则 MyBatis 启动时不报错、一调用就
 * {@code Invalid bound statement}。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包。
 *
 * <hr>
 *
 * <p>★★ Day 14 起，本类三个方法的返回类型从 {@code int} 改成 {@code Integer}，
 * 语义也随之升级：
 * <pre>
 *   改之前：返回【影响行数】 → 1 = 成功，0 = 守卫不成立
 *   改之后：返回【更新后的 available_stock】 → 非 null = 成功，null = 守卫不成立
 * </pre>
 * 为什么改：{@code inventory_logs} 流水要同时记 {@code before_stock} 和 {@code after_stock}，
 * 而「改成了多少」只有 PostgreSQL 的 {@code RETURNING} 能一条语句拿到（见下方「为什么不先查后改」）。
 * 顺带白赚一个好处：原来只知道「成没成功」，现在还知道「成功之后是多少」。
 *
 * <p>★★ 为什么是 {@code <select>} 而不是 {@code <update>}：
 * {@code <update>} 会把结果集丢掉，且它没有 {@code resultType} 属性，没法接 {@code RETURNING}。
 * 用 {@code <select>} 包住一条 {@code UPDATE} 语句，MyBatis 就把 {@code RETURNING} 的结果集
 * 当普通查询结果映射。{@code resultType="java.lang.Integer"} 对应单值结果。
 *
 * <p>★★ 为什么 XML 里必须写 {@code flushCache="true"}（★ 实测踩过，不是保险写法）：
 * MyBatis 的<b>一级缓存</b>（本地缓存，{@code localCacheScope} 默认 {@code SESSION}）
 * <b>始终开启</b>；{@code <select>} 会填充它，而只有 {@code insert/update/delete}
 * 才会刷新它。不写这个属性，<b>同一个事务内用相同参数调第二次会直接命中缓存、
 * SQL 根本不发</b> —— 上层以为改成功了，实际数据库没动。
 * <pre>
 *   实测对照（同一 SqlSession，相同参数连调两次 releaseLocked(sku=4, qty=1)）：
 *     flushCache="true"  → 第二次照样发 SQL，Total: 0 → 返回 null          ✅
 *     flushCache="false" → 第二次连 Preparing: 行都没有，直接返回陈旧的 147  ❌
 * </pre>
 * 本项目真的会踩到：{@code order_items} 没有 {@code (order_id, sku_id)} 唯一约束，
 * 一张订单可以有两行同 SKU 同数量的明细 → 循环里第二次调用的缓存键与第一次完全相同。
 * <b>所以 {@code flushCache="true"} 是承重结构。</b>
 * （{@code useCache="false"} 是顺手关掉二级缓存，属保险，不是关键。）
 *
 * <p>⚠️ 三处守卫的「0 行」含义各不相同，判错就会把用户错误报成系统故障（或反之）——
 * 见各方法 Javadoc 与 {@code InventoryService}。
 */
public interface InventoryMapper extends BaseMapper<Inventory> {

    /**
     * 扣减可售库存并锁入 locked（下单专用）。
     *
     * <p>★ 本方法是「原子动作」，不是「先查后改」：判定条件 {@code available_stock >= quantity}
     * 写在 UPDATE 的 WHERE 里，由数据库在同一条语句内完成「判断 + 扣减」。
     * 调用方通过<b>返回值</b>得知结果：
     * <pre>
     *   非 null = 扣成功，值就是【扣完之后】的 available_stock
     *   null    = 库存不足（一行都没改，所以 RETURNING 空手而归）
     * </pre>
     *
     * <p>★ 对应的流水：{@code type = ORDER_LOCK}，
     * {@code before = 返回值 + quantity}（因为它减了 quantity），
     * {@code after = 返回值}，{@code change = -quantity}。
     *
     * <p>⚠️ {@code reference_id} 只能写 NULL：下单流程是「先扣库存（⑤）、后插订单（⑥）」，
     * 走到这里时订单还不存在，没有 id 可记。这是流程顺序决定的，不是漏写。
     *
     * @param skuId    SKU 主键
     * @param quantity 扣减数量（必须 &gt; 0）
     * @return 更新后的 available_stock；null 表示库存不足（守卫不成立）
     */
    Integer deductStock(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    /**
     * 把锁定库存转为已售（支付成功专用）。
     *
     * <p>★ 与 {@code deductStock} 是同一招的第二次使用：判定条件 {@code locked_stock >= quantity}
     * 写在 WHERE 里，由数据库在同一条语句内完成「判断 + 转移」。
     *
     * <p>★★ 特别注意：<b>{@code available_stock} 一动不动</b>。
     * 这件货在下单那一刻就已经从「可售」挪进「锁定」了，支付只是把它从「锁定」挪到「已售」——
     * 再动一次 available 就等于把同一件货扣两遍。
     *
     * <p>★★ 正因为 available 不动，这条流水的 {@code change} <b>恒为 0</b>，
     * {@code before == after == 返回值}。这不是「没记到东西」——
     * <b>「PAY_SOLD 的 change 必须是 0」本身就是一条可以直接断言的铁律</b>：
     * 哪天它不为 0，就说明支付动了 available，也就是 Day 13 反复强调的那场事故又回来了。
     *
     * <p>条件里的 {@code locked_stock >= quantity} 是守卫：确保不会把「本来没锁定的货」卖掉。
     * 正常流程永远满足；一旦返回 null，说明订单与库存已经对不上账（数据被旁路改过），
     * 必须整笔事务回滚而不是继续。
     *
     * @param skuId    SKU 主键
     * @param quantity 转移数量（必须 &gt; 0）
     * @return 更新后的 available_stock（★ 与转移前相等）；null 表示锁定库存不足（异常态）
     */
    Integer moveLockedToSold(@Param("skuId") Long skuId, @Param("quantity") int quantity);

    /**
     * 把锁定库存退还可售（取消订单 / 超时关单专用）。
     *
     * <p>★ 本方法是 {@code deductStock} 的<b>严格逆操作</b>：
     * 一个 {@code available → locked}，一个 {@code locked → available}。
     * 到此为止三个库存写点构成完整闭环，恒等式不变量保持：
     * <pre>
     *   deductStock       available - n , locked + n      （下单）
     *   moveLockedToSold  locked - n    , sold + n        （支付）
     *   releaseLocked     locked - n    , available + n   （取消 / 超时）
     * </pre>
     *
     * <p>★★ 守卫是 {@code locked_stock >= quantity}，与 {@code moveLockedToSold} 相同，
     * 而<b>不是</b> {@code available_stock >= quantity}。判据永远是「我要动的那一格够不够」——
     * 本次要动的是 {@code locked}，所以判 {@code locked}。
     * 若误判成 {@code available}，取消一张「从未锁定过货」的订单也能执行成功 →
     * <b>凭空造货</b>。
     *
     * <p>★ 对应的流水：{@code type = CANCEL_RELEASE}，
     * {@code before = 返回值 - quantity}（因为它加了 quantity），
     * {@code after = 返回值}，{@code change = +quantity}。
     *
     * <p>★ 返回 null = 订单说「我锁着 3 件」而库存说「我只锁着 1 件」= 服务端账目不一致，
     * 重试无意义，必须整笔回滚（与 {@code deductStock} 的 null = 用户可控的「库存不足」不同）。
     *
     * @param skuId    SKU 主键
     * @param quantity 退还数量（必须 &gt; 0）
     * @return 更新后的 available_stock；null 表示锁定库存不足（异常态）
     */
    Integer releaseLocked(@Param("skuId") Long skuId, @Param("quantity") int quantity);
}
