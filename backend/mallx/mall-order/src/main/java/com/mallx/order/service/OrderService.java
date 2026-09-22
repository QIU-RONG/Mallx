package com.mallx.order.service;

import com.mallx.common.api.PageResult;
import com.mallx.order.api.OrderItemBuyContext;
import com.mallx.order.dto.OrderCreateDTO;
import com.mallx.order.vo.AdminOrderVO;
import com.mallx.order.vo.OrderDetailVO;
import com.mallx.order.vo.OrderVO;

/**
 * 订单服务
 */
public interface OrderService {

    /**
     * 从购物车下单：把当前用户【已勾选】的购物车项结算成一张订单。
     *
     * <p>整个方法在一个事务里完成：校验地址 → 读选中项 → 失效校验 → 算金额
     * → 按 skuId 升序锁库存 → 插 orders + order_items → 清购物车选中项。
     *
     * @return 新订单 id
     */
    Long createFromCart(Long userId, OrderCreateDTO dto);

    /**
     * 我的订单列表（分页，按创建时间倒序）。
     *
     * <p>★ 只查 {@code user_id = 当前用户} 的行 —— 越权防线写死在 SQL 条件里，
     * 不接受任何来自客户端的「查谁」参数。
     *
     * <p>★ 分页参数由本方法负责夹紧（实测依据见实现类的注释）：
     * <ul>
     *   <li>{@code size < 1} → 当成 1。
     *       ★ 关键是 {@code size < 0}：MyBatis-Plus 把它解读为「不执行分页、查全部」；
     *       而 {@code size = 0} 会返回【空列表】但 total 不变（用户会以为没订单）。</li>
     *   <li>{@code size > 100} → 截到 100（防止一次把整张表拖出来）。</li>
     *   <li>{@code page < 1} → 归一到 1。属防御性规范化 ——
     *       MyBatis-Plus 自身已对 {@code current <= 1} 做了保护，不会因负 offset 报错。</li>
     * </ul>
     *
     * @param page 页码，从 1 开始
     * @param size 每页条数，最终落在 1..100
     */
    PageResult<OrderVO> listMyOrders(Long userId, long page, long size);

    /**
     * 订单详情（订单头 + 明细快照）。
     *
     * <p>★ 「订单不存在」与「订单不属于当前用户」返回同一个 404 ——
     * 若两种情况的响应可区分，攻击者遍历 id 就能画出「哪些订单真实存在」的地图。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在
     */
    OrderDetailVO detail(Long userId, Long orderId);

    /**
     * 支付成功：把订单从「待支付」推进到「已支付」（CAS 条件 UPDATE）。
     *
     * <p>★ 条件 UPDATE 而不是「先查后改」—— 并发下两个线程都会先读到
     * {@code PENDING_PAYMENT}，各自 UPDATE 一次就收了<b>两笔钱</b>。
     * 把状态判断放进 {@code WHERE}，由数据库做原子比较，只有一个人能拿到 1 行。
     *
     * <p>★ 不加 {@code @Transactional}：单条 UPDATE 自身即原子，
     * 事务边界由调用方（{@code PaymentServiceImpl.pay}）持有 ——
     * 让「插支付单 + 改订单状态 + 改 N 个 SKU 库存」共处一个事务才有意义。
     *
     * <p>★ 状态不对时抛业务异常（HTTP 200 + body.code=400）。
     * 这里是 400 而不是 500 —— 「订单已经付过了」是用户可理解的正常结果，
     * 刷新一下就能看到正确状态；对比 {@link com.mallx.inventory.service.InventoryService#moveLockedToSold}
     * 的 0 行是「服务端账目不一致」，那才报 500。
     *
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许支付
     */
    void markPaid(Long orderId);

    /**
     * 取消订单：把「待支付」的订单推进到「已取消」，并把锁定的库存退回可售池。
     *
     * <p>整个方法在一个事务里完成：归属分流 → 读明细 → CAS 改状态 → 逐个 SKU 回补库存。
     *
     * <p>★★ 与支付链路是<b>完全对称的孪生结构</b>：同样先 {@code SELECT} 分流（404）、
     * 同样用 {@code WHERE status = 'PENDING_PAYMENT'} 抢资格（0 行 400）、
     * 同样用 {@code WHERE locked_stock >= n} 守卫库存（0 行 500）。
     * 差别只在终点：支付是 {@code PAID} + {@code locked → sold}，
     * 取消是 {@code CANCELLED} + {@code locked → available}。
     *
     * <p>★ 只能取消<b>自己的</b>订单：不是自己的与不存在的返回<b>同一个 404</b>——
     * 这是<b>写操作的 IDOR</b>，比读越权危险得多（读是泄露，写是破坏）。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在（含「不是你的」）
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许取消
     */
    void cancel(Long userId, Long orderId);

    /**
     * 系统视角：批量取消「超时未支付」的订单（定时任务入口）。
     *
     * <p>★ 与 {@link #cancel(Long, Long)} 的差别不是少写一行校验，而是<b>权限模型的分层</b>：
     * 前者是「你能取消你的订单」，本方法是「系统有权取消所有人的超时单」——
     * 所以本方法<b>不带 user_id 条件</b>。混成一个方法，要么越权，要么取消不了。
     *
     * <p>★★ 本方法<b>刻意不加 @Transactional</b>：整批共用一个事务的话，
     * 第 37 张单失败会把前 36 张一起回滚。逐单事务由 OrderCancelExecutor.cancelOne 各自持有。
     *
     * <p>★ 与用户支付的竞态不需要新代码 —— 还是 WHERE status='PENDING_PAYMENT' 那条 CAS 兜住，
     * 定时任务只是「多了一个竞争者」。
     *
     * @param minutes 超时阈值（分钟），建议 2
     * @return 本轮真正取消掉的条数（0 = 没有超时单，属正常）
     */
    int cancelTimeoutOrders(int minutes);

    /**
     * 发货：把「已支付」的订单推进到「已发货」（Day 15 第 1 步 · 管理端动作）。
     *
     * <p>★ 与 {@link #markPaid(Long)} / {@link #cancel(Long, Long)} 最大的不同有两点：
     * <ol>
     *   <li><b>不碰库存</b>：货的归属在支付那一刻就已定死，发货只推进物流状态 ——
     *       所以本方法只写 {@code orders} 一张表、一条 UPDATE，不需要事务；</li>
     *   <li><b>不接收 userId</b>：管理员有权给任何人的订单发货。
     *       「只有管理端能调」由调用方的 {@code @PreAuthorize("hasAuthority('order:ship')")}
     *       保证，而不是靠归属校验。</li>
     * </ol>
     *
     * <p>★★ 也正因为如此，本方法<b>不读取 principal</b> ——
     * {@code JwtAuthenticationFilter} 只把 token 的 {@code sub} 转成 {@code Long} 当 principal，
     * 管理端 admin 与 C 端用户的 {@code sub} 可能撞成同一个数值，
     * 拿它当「发货人」是错误的。
     *
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许发货
     */
    void ship(Long orderId);

    /**
     * 确认收货：把「已发货」的订单推进到「已完成」（Day 15 第 2 步 · C 端动作）。
     *
     * <p>★ 与 {@link #ship(Long)} 是<b>三处相反</b>的孪生：本方法<b>带 userId</b>、
     * <b>不做权限校验</b>（C 端 token 的权限集是空的，一挂 {@code @PreAuthorize} 就 403）、
     * <b>要归属分流</b>。
     *
     * <p>★ 与 {@link #cancel(Long, Long)} 同构的两步：先 {@code requireOwn} 分流
     * （不存在 / 不是你的 → 同一个 404，不可区分），再 CAS 抢资格（0 行 → 400）。
     * 两步的顺序不能反 —— CAS 的 {@code WHERE} 里<b>不带</b> {@code user_id}。
     *
     * <p>★ 同样<b>不碰库存</b>：{@code available / locked / sold} 一格不动，不需要事务。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在（含「不是你的」）
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许确认收货
     */
    void confirm(Long userId, Long orderId);

    /**
     * ★★ 供评价模块（{@code mall-review}）调用：按「订单明细 id」取出这笔购买的事实。
     *
     * <p>★ 为什么评价模块要绕道订单服务，而不是自己裸读 {@code orders} / {@code order_items}：
     * 「这笔购买是不是你的」「这张订单完成了吗」这两个问题的<b>权威答案在订单域</b>
     * —— 状态机的所有权柄都在这里（{@code OrderStatus} + 那几条 CAS UPDATE）。
     * 让别的模块自己去读状态列，等于把状态机的知识复制到第二个模块，
     * 以后状态机一改就得满仓库找。
     * 这里开一扇<b>只读门面</b>：它只取事实，不改任何东西。
     *
     * <p>★★ 返回值 {@code null} <b>同时</b>表示「明细不存在」与「明细不属于该用户」——
     * 归属条件写死在 SQL 的 {@code WHERE} 里，两种原因在数据库层就合成了一个空结果。
     * 调用方（评价服务）把 {@code null} 统一翻成 404，与订单详情的口径完全一致。
     * <b>不要把这两种情况分开报</b>：可区分 = 可枚举，攻击者遍历 id 就能画出
     * 「哪些明细真实存在」的地图。
     *
     * <p>★ 本方法只读、不加事务：单条 SELECT 自身即一致性快照，
     * 也不需要与调用方的事务绑在一起（评价的写入是一条 INSERT，原子性由它自己保证）。
     *
     * @param userId      当前登录用户（来自 token，不接受客户端传参）
     * @param orderItemId 订单明细 id
     * @return 这笔购买的事实；明细不存在<b>或</b>不属于该用户 → {@code null}
     */
    OrderItemBuyContext getBuyContext(Long userId, Long orderItemId);

    // ================== 管理端（Day 17 · 数据权限反转） ==================

    /**
     * ★★★ 管理端订单列表：<b>全站</b>订单分页（不按归属过滤）。
     *
     * <p>★★ 与 {@link #listMyOrders(Long, long, long)} 的差别<b>不是少写一行校验</b>，
     * 而是<b>防线整体上移了一层</b>：
     * <pre>
     *                 C 端 listMyOrders            管理端 listAllOrders
     *   谁能调        登录即可（anyRequest）          必须持有 order:list 权限码
     *   看到哪些行    归属过滤，写死在 SQL            全都在（或按运营传的条件筛）
     *   失败形态      非本人 → 伪装 404               无权限 → 真 HTTP 403
     *   越权边界      「别人的数据」                  「别人能不能拿到这个能力」
     * </pre>
     *
     * <p>★★ 一个必须记住的推论：<b>管理端的「不看归属」是允许的，
     * 前提是「有没有权限」这一关真的把住了。</b>
     * 把关一旦失效（这个端点忘了挂 {@code @PreAuthorize}），
     * 它就从「管理端接口」退化成「任何登录用户都能拉全站订单」——
     * 不是一个 403 的 bug，是一个<b>全量数据泄露</b>。
     *
     * <p>★ 两个过滤参数<b>都是可选的筛选条件，不是权限边界</b>：
     * {@code status} 筛状态、{@code userId} 筛买家（运营想看某人的单）。
     * 有没有它们都不影响「谁能调这个接口」—— 这句话听起来像废话，但它是
     * {@code §3.1 不要用布尔开关}那三条理由的源头：
     * 一旦参数能改变<b>可见行集的范围</b>，参数就变成了防线的一部分。
     *
     * <p>★ 分页夹紧规则与 {@link #listMyOrders} 完全相同（同一套实测依据）：
     * {@code size} 落在 1..100，{@code page} 归一到 ≥ 1，<b>夹紧写在 {@code new Page<>()} 之前</b>。
     *
     * @param status 可选的订单状态过滤（null / 空串 = 不筛）
     * @param userId 可选的买家过滤（null = 不筛）
     * @param page   页码，从 1 开始
     * @param size   每页条数，最终落在 1..100
     */
    PageResult<AdminOrderVO> listAllOrders(String status, Long userId, long page, long size);

    /**
     * ★★ 管理端订单详情：任意订单都能看，<b>不做归属分流</b>。
     *
     * <p>与 {@link #detail(Long, Long)} 的唯一差别就是<b>少了 {@code requireOwn} 那一步</b>：
     * <pre>
     *   C 端     detail(userId, orderId)        requireOwn → 不是你的就伪装 404
     *   管理端   detailByAdmin(orderId)         （跳过归属判断，因为管理员有权看任何单）
     * </pre>
     *
     * <p>★ 但<b>「不存在」仍然要报 404</b> —— 这里没有越权问题，只有一个诚实的
     * 「这个 id 没有对应的订单」。所以两个端点在这一点上形态相同、原因完全不同：
     * C 端的 404 是<b>伪装</b>（不可区分是防枚举），管理端的 404 是<b>事实</b>。
     *
     * <p>★ 返回值<b>复用 {@link OrderDetailVO}</b>（订单头 + 明细快照），不另建 VO：
     * 它本来就不含 {@code userId}，而管理端要看的买家信息
     * （{@code userId} / {@code userNickname}）在<b>列表接口</b>里已经给了。
     * ⚠️ 若将来管理端详情也要显示买家，正确做法是新建 {@code AdminOrderDetailVO}，
     * <b>而不是</b>给 {@code OrderDetailVO} 加字段 —— 那会让 C 端的响应跟着变胖
     * （理由同 {@link AdminOrderVO} 的类注释）。
     *
     * @throws com.mallx.common.exception.BusinessException code=404 订单不存在
     */
    OrderDetailVO detailByAdmin(Long orderId);

    /**
     * ★★★ 管理端取消订单：<b>复用同一段回补代码</b>（本日最容易写错的一处）。
     *
     * <p>与 {@link #cancel(Long, Long)} 在业务上的差别<b>只有一条</b>：
     * <pre>
     *   用户取消   cancel(userId, orderId)   ：requireOwn（404） → CAS → 回补库存
     *   管理端取消 cancelByAdmin(orderId)    ：（跳过归属）      → CAS → 回补库存
     *                                            ↑ 唯一差别
     * </pre>
     * 其余每一步（{@code WHERE status='PENDING_PAYMENT'} 抢资格、
     * {@code releaseLocked} 回补、写 {@code CANCEL_RELEASE} 流水）
     * <b>必须逐字相同</b> —— 所以两边都调 {@code cancelExecutor.cancelOne(orderId)}，
     * 谁也不许再写第二份。
     *
     * <p>★ 为什么不能写第二份：{@code releaseLocked} 的守卫
     * （{@code locked_stock >= quantity}）与流水口径（{@code CANCEL_RELEASE} / {@code change = +n}）
     * 是和 Day 14 的全链路对账<b>绑定在一起</b>的。两处各写一遍，早晚分叉 ——
     * 分叉之后对账脚本会开始报「账目不一致」，而错误会看起来像库存模块的 bug。
     *
     * <p>★★ <b>本方法不做「取消已支付订单」</b>：那是<b>退款</b>，属于售后域
     * （要动 {@code mall-payment}、要给状态机加边）。本方法的 CAS 条件与用户取消
     * <b>完全一致</b>，所以 PAID 单过来会被 CAS 挡成 400 ——
     * 这不是缺陷，是<b>本日边界的显式声明</b>。
     *
     * <p>★ 保留 {@code @Transactional}：{@code cancelOne} 是 REQUIRED 传播，会加入本方法的事务，
     * 所以「改状态 + 回补 N 个 SKU 库存 + 写 N 条流水」仍是一个原子操作。
     *
     * @throws com.mallx.common.exception.BusinessException code=400 订单状态不允许取消（含 PAID 单）
     */
    void cancelByAdmin(Long orderId);

}
