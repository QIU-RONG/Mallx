package com.mallx.review.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.mallx.review.entity.Review;
import com.mallx.review.vo.ReviewVO;
import org.apache.ibatis.annotations.Param;

import java.math.BigDecimal;

/**
 * 商品评价 Mapper —— ★ 本文件是<b>骨架</b>，方法体（SQL）由你写在
 * {@code src/main/resources/mapper/ReviewMapper.xml}。
 *
 * <p>★★ 为什么本模块<b>一条 SQL 都不用 BaseMapper 的 CRUD</b>：
 * <ol>
 *   <li><b>写入</b>要 {@code INSERT ... ON CONFLICT (order_item_id) DO NOTHING}
 *       —— 「冲突检测」是 {@code BaseMapper.insert} 表达不了的，
 *       而它正是「一明细一评」的<b>并发安全</b>防线（见 {@link #insertReview}）；</li>
 *   <li><b>读取</b>要 JOIN {@code users}（取昵称）与 {@code order_items}（取商品快照）
 *       —— 同样超出 BaseMapper 的能力。</li>
 * </ol>
 *
 * <p>★ 不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包，
 * 且 {@code mall-server} 已依赖 {@code mall-review}。
 *
 * <p>⚠️ 每个方法名必须与 XML 的 statement {@code id} <b>逐字符一致</b> ——
 * 差一个字母就在调用时抛 {@code Invalid bound statement (not found)}，<b>编译期不报错</b>。
 *
 * <p>⚠️ 多参数方法（≥2 个参数）<b>每个参数都要 {@code @Param}</b>，
 * 否则 MyBatis 只会给它们 {@code arg0/param1} 这种名字，XML 里写 {@code #{userId}} 解析不到。
 */
public interface ReviewMapper extends BaseMapper<Review> {

    /**
     * ★★★ 本日最核心的 SQL：插入一条评价，用<b>冲突检测</b>当 CAS。
     *
     * <p>SQL 形状（你自己写进 XML）：
     * <pre>
     *   INSERT INTO reviews (user_id, product_id, order_id, order_item_id,
     *                        rating, content, status, created_at, updated_at)
     *   VALUES (#{userId}, #{productId}, #{orderId}, #{orderItemId},
     *           #{rating}, #{content}, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
     *   ON CONFLICT (order_item_id) DO NOTHING
     * </pre>
     *
     * <p>★★ <b>返回的影响行数就是答案</b>（探针 4 已实测）：
     * <pre>
     *   1 → 插入成功
     *   0 → 该明细已评过，冲突被 DO NOTHING 吞掉 → 上层抛 400「该商品已评价过」
     * </pre>
     * 这与项目一路走来的 CAS <b>完全同构</b>：前几次是
     * {@code UPDATE ... WHERE status = 'PAID'}「条件不满足 → 0 行」，
     * 这次是 {@code INSERT ... ON CONFLICT DO NOTHING}「冲突 → 0 行」。
     * <b>把判断交给数据库、把影响行数当返回值</b>，是同一种思想。
     *
     * <p>★ 为什么<b>不</b>「先 SELECT 查有没有、没有才 INSERT」：两个并发请求会<b>同时</b>
     * 查到「没有」，然后双双插入（TOCTOU）。
     * ★ 为什么<b>不</b>「硬插 + catch DuplicateKeyException」：效果一样但要靠异常做控制流，
     * 而且 {@code DuplicateKeyException} 是 RuntimeException 的子类、
     * {@code GlobalExceptionHandler} 里没有它的专用出口 → 会被兜成 500。
     * 走 {@code ON CONFLICT} 就<b>不用动 GlobalExceptionHandler 一个字节</b>。
     *
     * <p>★★ {@code DO NOTHING} 的判定依赖唯一索引 ⇒ 这是 {@code NOT NULL} 与
     * {@code UNIQUE} <b>两条</b> DDL 缺一不可的原因：列可空时 NULL 行会整条绕过它（探针 5）。
     *
     * <p>⚠️ {@code created_at} / {@code updated_at} 必须在 SQL 里手写 ——
     * 自定义 XML 的 INSERT <b>不走</b> {@code MetaObjectHandler}。
     *
     * <p>★ 参数是实体对象：单参数的 POJO 不需要 {@code @Param}，
     * MyBatis 直接把它当根对象，{@code #{userId}} 等价于 {@code review.getUserId()}。
     *
     * @return 影响行数：1 = 插入成功；0 = 该明细已评过
     */
    int insertReview(Review review);

    /**
     * 回查刚写入（或被拒绝）的那条评价 —— 发表接口的返回值用它装配。
     *
     * <p>★ 单表查询 + JOIN {@code users} / {@code order_items}，
     * 与列表共用同一份字段集，所以 {@code resultType} 直接指向 {@link ReviewVO}，不另建 VO。
     *
     * @param orderItemId 订单明细 id（唯一约束保证最多一行）
     * @return 该明细的评价；不存在时返回 {@code null}
     */
    ReviewVO selectByOrderItemId(@Param("orderItemId") Long orderItemId);

    /**
     * ★★ 商品维度的评价列表（分页）—— <b>公开接口</b>，游客也能看。
     *
     * <p>★ 过滤条件只有两个：{@code WHERE product_id = #{productId} AND status = 1}。
     * {@code status = 1} 不能省：将来管理端把评价置为不可见（{@code status = 0}）时，
     * 不加这个条件就会把下架的评价又露出来。
     *
     * <p>★ 要 {@code LEFT JOIN users} 取 {@code nickname}、{@code LEFT JOIN order_items}
     * 取商品快照（{@code product_name} / {@code sku_name} / {@code image}）。
     * ⚠️ 这里 JOIN {@code users} 是<b>只读的跨域查询</b>，<b>不是</b>模块依赖 ——
     * {@code mall-review} 的编译期依赖仍然只有 {@code mall-common} + {@code mall-order}
     * （与 {@code PaymentMapper.xml} JOIN {@code orders} 是同一种做法）。
     * 请把这句话写进 XML 的注释里。
     *
     * <p>★ 排序：{@code ORDER BY created_at DESC, id DESC} —— 不能省排序（不带排序的分页 =
     * 随机翻页）；再加 {@code id} 倒序兜底，避免同毫秒的两行在翻页时「又出现又消失」。
     *
     * <p>★★ <b>首参必须是 {@code IPage}</b>：MyBatis-Plus 的 {@code PaginationInnerInterceptor}
     * 靠「方法参数里有没有 {@code IPage}」来决定是否改写 SQL 加 {@code LIMIT/OFFSET} 并跑 count。
     * 少了它<b>不报错，只是静默查全表</b>。
     *
     * @param page      分页参数（由 Service 夹紧后构造，★ 夹紧必须在 new Page 之前）
     * @param productId 商品 id
     */
    IPage<ReviewVO> selectProductReviews(IPage<ReviewVO> page, @Param("productId") Long productId);

    /**
     * ★ 我的评价列表（分页）—— <b>需登录</b>。
     *
     * <p>★ 归属条件 {@code WHERE user_id = #{userId}} 写死在 SQL 里，
     * 不接受任何来自客户端的「查谁」参数（与 {@code PaymentMapper} 同一条铁律）。
     *
     * <p>★ 同样要 JOIN {@code order_items} 取商品快照，好让「我的评价」列表能直接展示
     * 「是哪件商品」—— 不需要前端再查一次订单接口。
     *
     * @param page   分页参数（由 Service 夹紧后构造）
     * @param userId 当前登录用户（来自 token）
     */
    IPage<ReviewVO> selectMyReviews(IPage<ReviewVO> page, @Param("userId") Long userId);

    /**
     * 商品平均分（1 位小数；无评价时返回 0）。
     *
     * <p>SQL：{@code SELECT COALESCE(ROUND(AVG(rating)::numeric, 1), 0) FROM reviews
     * WHERE product_id = #{productId} AND status = 1}
     *
     * <p>★ {@code products} 表<b>没有</b> {@code rating} / {@code review_count} 冗余列
     * （已核对），所以聚合只能实时算 —— 这是<b>故意的</b>：
     * 冗余列要靠「每次评价后重算」维护，一旦漏算就<b>永久漂移</b>
     * （本项目 Day 14 已经花了一整个白天处理账目漂移）。
     * 实时 {@code AVG} 的值<b>必然等于</b>明细重算 —— 这是「没有第二个真相」的又一处体现。
     *
     * @return 平均分，如 {@code 4.5}；该商品一条评价都没有时为 {@code 0}
     */
    BigDecimal selectProductAvgRating(@Param("productId") Long productId);

    /**
     * 商品评价总数（与 {@link #selectProductAvgRating} 同一批数据源）。
     *
     * <p>★ 分两次查而不是一次：本日允许（见规划 §4.2「一次查两件事（或两次查询）」）。
     * 好处是<b>零映射风险</b>（不用为一行两列再造一个 VO），代价是一次额外往返 —— V1.0 够用。
     *
     * @return 该商品 {@code status = 1} 的评价条数
     */
    long selectProductReviewCount(@Param("productId") Long productId);
}
