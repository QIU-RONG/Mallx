package com.mallx.admin.mapper;

import com.mallx.admin.vo.TrendPointVO;
import org.apache.ibatis.annotations.Param;

import java.math.BigDecimal;
import java.util.List;

/**
 * 仪表盘取数（Day 22）。
 *
 * <p>★★ <b>本 Mapper 直查四张表（users / products / orders / payments），
 * 而 mall-admin 模块只依赖 mall-common</b> —— 这不是违规，是本日刻意选定的取数方式：
 * <pre>
 *   选项 A（选定）：mall-admin 里手写 XML，SQL 直查表名 ⇒ 零 POM 改动、零跨模块耦合
 *   选项 B：加 4 个模块依赖，各模块暴露 count/sum 方法，本类只做拼装
 *           ⇒ 模块边界更干净，但要改 5 个 POM + 4 个模块加方法
 * </pre>
 * 判据：<b>只读聚合不是业务写</b>。写操作跨模块必须走 Service 接口（事务与不变量在那边），
 * 而「算几个数」不构成模块间的语义依赖 —— 它只依赖**表结构**。
 * 反过来说：一旦哪天这些统计需要业务规则（比如「销售额要扣掉退款、按渠道分组」），
 * 就该换成选项 B 或建 mall-stat，因为那时它有了语义。
 *
 * <p>★ 不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包
 * （同 {@code AdminMapper} / 各模块 Mapper 的写法）。
 */
public interface DashboardMapper {

    /** 用户总数（users 全表，含已禁用） */
    long countUsers();

    /**
     * 商品数。
     * <p>
     * ⚠️★ 手写 XML 的 SELECT <b>不受 {@code @TableLogic} 管辖</b> —— MP 的软删条件是
     * 它拼 wrapper 时加的，与手写 SQL 无关。所以这里必须<b>自己写
     * {@code WHERE is_deleted = 0}</b>，否则会把软删商品算进来（「漏列」正是
     * 三层验证盲区的第三层：XML 良构 ✅、SQL 能跑 ✅、口径错 ❌）。
     */
    long countProducts();

    /** 订单总数（全表，含已取消） */
    long countOrders();

    /**
     * 销售额（支付流水口径）。
     * <p>
     * ★ 必须 {@code coalesce(sum(amount), 0)}：空表（或全是失败支付）时 {@code sum}
     * 返回 <b>NULL</b>，映射到 {@code BigDecimal} 就是 {@code null} ⇒ 前端显示 "null"。
     * 「漏 COALESCE」与本项目记过的「漏列」是同一类盲区。
     */
    BigDecimal sumPaidAmount();

    /**
     * 最近 {@code days} 天的按天趋势（订单量 + 销售额，缺数据的日子补 0）。
     *
     * @param startDate 起始日期（含），格式 {@code yyyy-MM-dd}。
     *                  ★ 由 Java 侧算好传入，而不是在 SQL 里写 {@code CURRENT_DATE - (? - 1) * INTERVAL}：
     *                  PG 在 {@code (? - 1) * INTERVAL '1 day'} 这种表达式里会报
     *                  {@code could not determine data type of parameter}
     *                  （JDBC 占位符无法推断类型）。要么 {@code CAST(#{startDate} AS date)}
     *                  显式定类型，要么像本方法这样直接传算好的日期字符串。
     */
    List<TrendPointVO> selectDailyTrend(@Param("startDate") String startDate);
}
