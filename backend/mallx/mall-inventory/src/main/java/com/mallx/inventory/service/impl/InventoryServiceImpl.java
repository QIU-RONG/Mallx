package com.mallx.inventory.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.common.InventoryLogType;
import com.mallx.inventory.entity.InventoryLog;
import com.mallx.inventory.mapper.InventoryLogMapper;
import com.mallx.inventory.mapper.InventoryMapper;
import com.mallx.inventory.service.InventoryService;
import com.mallx.inventory.vo.InventoryLogVO;
import com.mallx.inventory.vo.InventoryVO;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 库存服务实现
 *
 * <hr>
 *
 * <p>★★ Day 14 起，三个方法【都加了 {@code @Transactional}】——
 * 这里要说明清楚为什么<b>理由变了</b>，否则容易照着旧注释把注解删掉：
 * <pre>
 *   Day 12 / 13 的旧理由：「整段逻辑只有一条 UPDATE，它自身就是原子动作，无需再包一层事务」
 *   Day 14 起失效：    现在每条路径都是【两条语句】—— 先 UPDATE 库存，再 INSERT 流水
 * </pre>
 * 两条语句之间一旦没有事务兜底，就会出现「库存改了、流水没写」这种账本与现值的静默分叉，
 * 而这正是 {@code inventory_logs} 要防的事。<b>加了流水，就必须有事务。</b>
 *
 * <p>★ 传播行为用默认的 {@code REQUIRED}（有事务就加入、没有就新开）：
 * 调用方（{@code OrderServiceImpl} / {@code PaymentServiceImpl} / {@code OrderCancelExecutor}）
 * 都持有事务，所以「改订单状态 + 改 N 个 SKU 库存 + 写 N 条流水」共处一个事务，
 * 任何一步失败整笔回滚 —— 第 2 步的实验里已经实测过这个行为（一个 HTTP 请求写三张表是一个事务）。
 *
 * <p>⚠️ <b>绝不能改成 {@code REQUIRES_NEW}</b>：那样本方法会自己提交，
 * 调用方后续失败时库存就回不来了 —— 这是绝不能碰的线。
 */
@Service
public class InventoryServiceImpl implements InventoryService {

    /**
     * 分页上限：单页最多 100 条 —— 与 {@code OrderServiceImpl.MAX_PAGE_SIZE} /
     * {@code ReviewServiceImpl.MAX_PAGE_SIZE} 同一个值、同一套夹紧规则。
     *
     * <p>★ 不抽到 {@code mall-common} 做成公共常量：那是一次跨模块重构，与本步无关。
     * 三处各留一份、注释互相指明，等真有需要时再抽。
     * （本日新增的是第 4 处 —— 库存列表与库存流水各用一次，共用这一个常量。）
     */
    private static final long MAX_PAGE_SIZE = 100;

    private final InventoryMapper inventoryMapper;
    private final InventoryLogMapper inventoryLogMapper;

    public InventoryServiceImpl(InventoryMapper inventoryMapper,
                                InventoryLogMapper inventoryLogMapper) {
        this.inventoryMapper = inventoryMapper;
        this.inventoryLogMapper = inventoryLogMapper;
    }

    /**
     * 下单扣减：{@code available → locked}，并写一条 {@code ORDER_LOCK} 流水。
     *
     * <p>★ {@code reference_id} 写 NULL：下单是「先扣库存（⑤）、后插订单（⑥）」，
     * 走到这里时订单还不存在。这是流程顺序决定的，不是漏写。
     */
    @Override
    @Transactional
    public void deductForOrder(Long skuId, int quantity) {
        Integer after = inventoryMapper.deductStock(skuId, quantity);
        if (after == null) {
            // 返回 null = 影响 0 行，有两种可能：SKU 没有库存行，或 available_stock < quantity。
            // 对客户端而言都是「买不到」，统一报同一个错，不泄露内部结构。
            // ★ 此刻还没有写流水，抛异常让整个事务回滚，不会留下孤儿流水。
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "库存不足");
        }
        // available 减少了 quantity，所以 change = -quantity
        writeLog(skuId, InventoryLogType.ORDER_LOCK, -quantity, after, null);
    }

    /**
     * 支付成功：{@code locked → sold}，并写一条 {@code PAY_SOLD} 流水。
     *
     * <p>★ 0 行是【服务端异常态】，不是用户错误：订单说「我锁定着 3 件」，库存说「我只锁着 1 件」。
     * 这种账对不上不可能靠重试解决，必须整笔回滚，所以用 {@code FAIL(500)} 而不是 {@code 400}。
     * （对比 {@code deductForOrder} 的 0 行 = 「库存不足」，那是正常的用户可理解结果。）
     *
     * <p>★★ 本方法写出的流水 {@code change_quantity} <b>恒为 0</b>（{@code before == after}）：
     * 因为 {@code moveLockedToSold} 压根不碰 {@code available_stock}。
     * 这不是「没记到东西」—— 它恰恰是 Day 13 那条铁律的可审计化：
     * <b>「PAY_SOLD 的 change 必须是 0」，一旦不为 0，就说明支付动了 available，
     * 也就是同一件货被扣了两遍。</b>
     */
    @Override
    @Transactional
    public void moveLockedToSold(Long skuId, int quantity, Long orderId) {
        Integer after = inventoryMapper.moveLockedToSold(skuId, quantity);
        if (after == null) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，支付已回滚");
        }
        // available 一动不动，所以 change = 0（RETURNING 出来的值就是转移前的值）
        writeLog(skuId, InventoryLogType.PAY_SOLD, 0, after, orderId);
    }

    /**
     * 取消订单 / 超时关单：{@code locked → available}（{@code deductForOrder} 的逆操作），
     * 并写一条 {@code CANCEL_RELEASE} 流水。
     *
     * <p>★ 0 行与 {@code moveLockedToSold} 同类，是【服务端异常态】：
     * 订单说「我锁定着 3 件」，库存说「我只锁着 1 件」。账对不上，重试无意义，必须整笔回滚，
     * 所以用 {@code FAIL(500)} 而不是 {@code 400}。
     * 与 {@code deductForOrder} 的 0 行形成三足对照：
     * <pre>
     *   deductForOrder   0 行 = 库存不足（用户能理解）      → 400
     *   moveLockedToSold 0 行 = 账目不一致（服务端错）      → 500
     *   releaseLocked    0 行 = 账目不一致（服务端错）      → 500
     * </pre>
     */
    @Override
    @Transactional
    public void releaseLocked(Long skuId, int quantity, Long orderId) {
        Integer after = inventoryMapper.releaseLocked(skuId, quantity);
        if (after == null) {
            throw new BusinessException(ResultCode.FAIL.getCode(), "库存锁定状态异常，取消已回滚");
        }
        // available 增加了 quantity，所以 change = +quantity
        writeLog(skuId, InventoryLogType.CANCEL_RELEASE, quantity, after, orderId);
    }

    // ============================ 私有工具 ============================

    /**
     * 追加一条库存流水。
     *
     * <p>★★ 注意 {@code beforeStock} 是<b>算出来的</b>（{@code after - change}），不是单独查出来的。
     * 这样写有两个好处：
     * <ol>
     *   <li>恒等式 {@code change == after - before} <b>由构造保证</b>，不可能写歪 ——
     *       如果改成让调用方分别传 before 和 after，就有机会传成自相矛盾的一对值；</li>
     *   <li>不需要为了拿 before 而多一次 SELECT（那正是 Day 14 §六 否掉的方案 A/B）。</li>
     * </ol>
     *
     * <p>★ {@code createdAt} 故意留 null：MyBatis-Plus 插入策略默认 {@code NOT_NULL}
     * （null 字段不进 INSERT），于是走建表时的 {@code DEFAULT CURRENT_TIMESTAMP}，
     * 让流水时间与数据库时钟同一条时间轴。
     *
     * @param skuId      被改的 SKU
     * @param type       流水类型，只用 {@link InventoryLogType} 的常量
     * @param change     带符号的变化量（ORDER_LOCK 为负、PAY_SOLD 为 0、CANCEL_RELEASE 为正）
     * @param after      UPDATE ... RETURNING 拿到的更新后 available_stock
     * @param referenceId 关联订单 id，可为 null
     */
    private void writeLog(Long skuId, String type, int change, int after, Long referenceId) {
        InventoryLog log = new InventoryLog();
        log.setSkuId(skuId);
        log.setType(type);
        log.setChangeQuantity(change);
        log.setAfterStock(after);
        log.setBeforeStock(after - change);
        log.setReferenceId(referenceId);
        inventoryLogMapper.insert(log);
    }

    // ================== 管理端（Day 17 · 库存查询 / 调整 / 流水） ==================

    /**
     * ★ 管理端库存分页 —— <b>骨架</b>，方法体由你写。
     *
     * <p>三步（与 {@code OrderServiceImpl.listAllOrders} 同款，只少一个过滤归一化）：
     * <pre>
     *   ① 夹紧（★ 必须在 new Page 之前）：
     *        long safePage = Math.max(page, 1);
     *        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
     *   ② IPage&lt;InventoryVO&gt; result =
     *        inventoryMapper.selectInventoryPage(new Page&lt;&gt;(safePage, safeSize));
     *   ③ return PageResult.of(result);
     * </pre>
     *
     * <p>⚠️ 别去找 {@code PageResult.convert} —— 它不存在（{@code PageResult} 只有 {@code of}）。
     * 本方法也不需要转换：{@code selectInventoryPage} 返回的本来就是 {@code IPage<InventoryVO>}。
     *
     * <p>★ <b>不加 {@code @Transactional}</b>：只读一张表，
     * 单条 SELECT 自身即一致性快照（与三个写点「必须加」形成对照 ——
     * 判据是<b>写点个数</b>，不是「方法重不重要」）。
     */
    @Override
    public PageResult<InventoryVO> listSkus(long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        IPage<InventoryVO> result = inventoryMapper.selectInventoryPage(new Page<>(safePage, safeSize));
        return PageResult.of(result);
    }

    /**
     * ★★★ 管理端调整库存 —— <b>骨架</b>，方法体由你写（本日最重要的一段）。
     *
     * <p>五个步骤，顺序不能换：
     * <pre>
     *   ① delta == 0 → BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "调整量不能为 0")
     *      ★ 为什么在这里而不是 DTO 上：Jakarta 没有「不等于某值」的现成注解，
     *        而「delta = 0 是一次无意义的改动」本质是【业务规则】，不是格式规则。
     *        格式类校验留注解、业务类校验留服务 —— 这条分界本身就是规矩。
     *   ② Integer after = inventoryMapper.adjustStock(skuId, delta);
     *   ③ after == null → BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
     *                        "调整后可用/总库存不能为负")
     *      ★★ 400 而不是 500：这是【用户可理解的业务结果】（管理员填了个太大的负数），
     *         与 moveLockedToSold / releaseLocked 的 0 行（账目不一致，500）不是一回事。
     *      ★★ 此刻【还没有写流水】—— 抛异常让事务回滚，不会留下孤儿流水。
     *         这正是「调 400 前先确认没有副作用」的落地方式。
     *   ④ writeLog(skuId, InventoryLogType.ADMIN_ADJUST, delta, after, null);
     *      ★ change = delta：available 跟着 total 同向同量动，所以变化量就是 delta
     *      ★ referenceId = null：管理端调整没有关联订单（不是「拿不到」，是本来就没有）
     *      ★ 复用私有方法 writeLog —— 它已经把 before = after - change 算好了，
     *        恒等式 change == after - before 由构造保证，不可能写歪
     *   ⑤ 返回类型是 void：前端拿到 200 后重新拉一次库存列表即可。
     *      （前端想立刻看到新值，也可以顺手把 ② 的 after 作为返回值 ——
     *        那是接口设计的选择，本日保持与另外三个写点同款：void。）
     * </pre>
     *
     * <p>⚠️ {@code reason} 在本方法里【只出现、不使用】：本日不落库（显式取舍，见规划 §4.3）。
     * 它已经在 DTO 上被 {@code @NotBlank} 校验过，这里不必再判一次 ——
     * <b>同一条规则只在一处表达</b>，重复校验看起来更安全，实际是两份真相的开始。
     */
    @Override
    @Transactional
    public void adjust(Long skuId, int delta, String reason) {
        // TODO(你写): 按上面 ①②③④ 五步实现（⑤ 是返回类型，不用写代码）。
        throw new UnsupportedOperationException("TODO: InventoryServiceImpl.adjust");
    }

    /**
     * ★ 管理端库存流水 —— <b>骨架</b>，方法体由你写。
     *
     * <p>四步：
     * <pre>
     *   ① 夹紧（同 listSkus，★ 必须在 new Page 之前）
     *   ② 归一化空串：String safeType = (type == null || type.isBlank()) ? null : type;
     *   ③ IPage&lt;InventoryLog&gt; result = inventoryLogMapper.selectPage(
     *          new Page&lt;&gt;(safePage, safeSize),
     *          new LambdaQueryWrapper&lt;InventoryLog&gt;()
     *              .eq(skuId != null, InventoryLog::getSkuId, skuId)
     *              .eq(safeType != null, InventoryLog::getType, safeType)
     *              .orderByDesc(InventoryLog::getId));
     *   ④ return PageResult.of(result.convert(this::toLogVO));
     * </pre>
     *
     * <p>★ <b>③ 用的是「条件版 eq」</b>：{@code eq(boolean condition, 列, 值)} ——
     * 第一个参数为 false 时<b>整个条件根本不拼进 SQL</b>。
     * 这正是「可选过滤」的正统写法，比在 XML 里堆 {@code <if>} 更直接。
     * ⚠️ 写成 {@code .eq(InventoryLog::getSkuId, skuId)} 且 skuId 为 null 时，
     * 会拼出 {@code WHERE sku_id = null} → <b>永远不成立、且不报错</b>（返回空列表）
     * —— 与 XML 里 {@code AS userNickname} 那类坑同一个性质：<b>安静地错</b>。
     *
     * <p>★★ <b>为什么这里用 MP wrapper 而不是新写 XML</b>（对规划 §8.2 的一处偏离）：
     * <ol>
     *   <li>它是<b>单表查询 + 可选等值条件</b>，不需要任何 JOIN ——
     *       {@code LambdaQueryWrapper} 天生就是为这个场景做的
     *       （{@code OrderServiceImpl.listMyOrders} 用的是同一手法）；</li>
     *   <li>{@code InventoryLogMapper} 的类注释明确写着「<b>故意是空的</b>……
     *       流水没有这种需求，所以不写 XML、也不声明任何方法」——
     *       为一次简单分页去推翻它，不如顺着它；</li>
     *   <li>XML 只在「一条语句要完成判断 + 修改」或「要 JOIN 跨表」时才值得写
     *       （本日 {@code adjustStock} 与 {@code selectInventoryPage} 都属于后者）。</li>
     * </ol>
     * ⚠️ 代价：实体是 {@code InventoryLog}、出参要 {@code InventoryLogVO}，
     * 所以多一步 {@code convert(this::toLogVO)} —— 这就是下面那个私有方法存在的理由。
     *
     * <p>★ <b>不加 {@code @Transactional}</b>：只读。
     */
    @Override
    public PageResult<InventoryLogVO> listLogs(Long skuId, String type, long page, long size) {
        // TODO(你写): 按上面 ①②③④ 四步实现。
        throw new UnsupportedOperationException("TODO: InventoryServiceImpl.listLogs");
    }

    /**
     * 流水实体 → 流水行（只为 {@link #listLogs} 存在）。
     *
     * <p>★ 八个字段一一对应搬过去。这张表<b>只增不改</b>，没有需要屏蔽的内部列，
     * 所以这是本项目里最「直白」的一次 VO 装配 —— 但它仍然值得单独存在：
     * 「实体可以出接口」这个先例一旦开了，表加一列出参就跟着变。
     */
    private InventoryLogVO toLogVO(InventoryLog log) {
        // TODO(你写): 8 个字段一一搬（id / skuId / type / changeQuantity /
        //   beforeStock / afterStock / referenceId / createdAt）。
        throw new UnsupportedOperationException("TODO: InventoryServiceImpl.toLogVO");
    }
}
