package com.mallx.inventory.service.impl;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.inventory.common.InventoryLogType;
import com.mallx.inventory.entity.InventoryLog;
import com.mallx.inventory.mapper.InventoryLogMapper;
import com.mallx.inventory.mapper.InventoryMapper;
import com.mallx.inventory.vo.InventoryLogVO;
import com.mallx.inventory.vo.InventoryVO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ★ 库存域第一批单元测试（Day 48）—— 只测 {@link InventoryServiceImpl} 自己那部分判定。
 *
 * <hr>
 *
 * <p>★★★ 为什么这些事<b>必须</b>用单测锁，端到端（{@code day14/15/16}）盖不住：
 *
 * <ol>
 *   <li><b>「失败时不能留孤儿流水」是概率性命题。</b>
 *       端到端只能看到「跑完之后数据库长什么样」，而「失败路径没写流水」在成功路径里
 *       <b>永远观察不到</b>。要让它在端到端里现形，得先让一条 UPDATE 返回 0 行
 *       —— 那需要把库存改坏，属于「为了测而制造故障」。
 *       单测里只要让 mapper 返回 {@code null} 就行，<b>确定、便宜、可重复</b>。</li>
 *
 *   <li><b>「PAY_SOLD 的 change 恒为 0」是一条不变量，不是一个值。</b>
 *       端到端能断言「这条流水是 0」，但断言不了「<i>任何情况</i>下它都必须是 0」——
 *       后者是设计意图，只有盯着代码语义的单测说得清。
 *       这条是 Day 13 那场事故（同一件货被扣两遍）的可审计形式，
 *       它一旦被改歪，<b>没有任何编译错误、没有任何测试会红</b>（不写就没人知道）。</li>
 *
 *   <li><b>400 / 500 的分野是【语义】不是【数字】。</b>
 *       {@code deductForOrder} 的 0 行 = 库存不足（用户可理解 → 400），
 *       另外三个写点的 0 行 = 账目不一致（服务端错 → 500）。
 *       这两个数字端到端都能看到，但「为什么是这两个数字」没有东西记着 ——
 *       改的人只会看到一个魔法数，很难知道自己正在改坏一条判据。</li>
 * </ol>
 *
 * <p>不启 Spring、不连库、不连 Redis：只 mock 两个 Mapper。
 * ★ 库存服务是本模块里<b>依赖最少</b>的类（构造只吃两个 Mapper），
 * 这也是先拿它开刀的原因 —— 单测的成本与「要 mock 几个协作者」正相关。
 */
@ExtendWith(MockitoExtension.class)
class InventoryServiceImplTest {

    @Mock
    private InventoryMapper inventoryMapper;
    @Mock
    private InventoryLogMapper inventoryLogMapper;

    @InjectMocks
    private InventoryServiceImpl service;

    private static final Long SKU = 7L;
    private static final Long ORDER = 100L;

    // ==================================================================
    // 工具
    // ==================================================================

    /**
     * 取出「刚刚写进去的那条流水」 —— 本文件绝大多数断言的落点。
     *
     * <p>★ 用 {@code verify(...).insert(captor.capture())} 而不是拿到返回值：
     * 写点是 {@code void}，<b>「写了什么」只能从被调参数上看</b>。
     * 这是单测里最常见的一类断言形状（void 方法的副作用 → 抓参数）。
     */
    private InventoryLog capturedLog() {
        ArgumentCaptor<InventoryLog> c = ArgumentCaptor.forClass(InventoryLog.class);
        verify(inventoryLogMapper).insert(c.capture());
        return c.getValue();
    }

    // ==================================================================
    // [A] 四个写点 · 成功路径：流水记对了没有
    // ==================================================================

    @Test
    @DisplayName("A1 下单扣减 → ORDER_LOCK：change = -n，before = after + n，referenceId 为 null（订单此刻还不存在）")
    void deductForOrder_writesLockLog() {
        when(inventoryMapper.deductStock(SKU, 3)).thenReturn(10);

        service.deductForOrder(SKU, 3);

        InventoryLog log = capturedLog();
        assertEquals(InventoryLogType.ORDER_LOCK, log.getType());
        assertEquals(-3, log.getChangeQuantity().intValue());
        assertEquals(10, log.getAfterStock().intValue());
        assertEquals(13, log.getBeforeStock().intValue());
        assertNull(log.getReferenceId(), "下单是「先扣库存、后插订单」，走到这里订单还没有 id");
    }

    @Test
    @DisplayName("A2 ★★ 支付成功 → PAY_SOLD：change 必须【恒为 0】—— 不为 0 就说明支付动了 available（Day 13 事故）")
    void moveLockedToSold_changeIsAlwaysZero() {
        when(inventoryMapper.moveLockedToSold(SKU, 3)).thenReturn(42);

        service.moveLockedToSold(SKU, 3, ORDER);

        InventoryLog log = capturedLog();
        assertEquals(InventoryLogType.PAY_SOLD, log.getType());
        assertEquals(0, log.getChangeQuantity().intValue(),
                "★ PAY_SOLD 只做 locked → sold 的搬运，available 一动不动 ⇒ change 恒为 0");
        assertEquals(log.getAfterStock(), log.getBeforeStock(),
                "before == after 是 change == 0 的另一半证据");
        assertEquals(ORDER, log.getReferenceId());
    }

    @Test
    @DisplayName("A3 取消/超时 → CANCEL_RELEASE：change = +n（available 加回去），带订单 id")
    void releaseLocked_writesReleaseLog() {
        when(inventoryMapper.releaseLocked(SKU, 3)).thenReturn(20);

        service.releaseLocked(SKU, 3, ORDER);

        InventoryLog log = capturedLog();
        assertEquals(InventoryLogType.CANCEL_RELEASE, log.getType());
        assertEquals(3, log.getChangeQuantity().intValue());
        assertEquals(20, log.getAfterStock().intValue());
        assertEquals(17, log.getBeforeStock().intValue());
        assertEquals(ORDER, log.getReferenceId());
    }

    @Test
    @DisplayName("A4 退款退货 → REFUND_RETURN：change = +n（sold 回到 available）")
    void returnToStock_writesReturnLog() {
        when(inventoryMapper.returnStock(SKU, 2)).thenReturn(30);

        service.returnToStock(SKU, 2, ORDER);

        InventoryLog log = capturedLog();
        assertEquals(InventoryLogType.REFUND_RETURN, log.getType());
        assertEquals(2, log.getChangeQuantity().intValue());
        assertEquals(28, log.getBeforeStock().intValue());
        assertEquals(ORDER, log.getReferenceId());
    }

    // ==================================================================
    // [B] 四个写点 · 失败路径：0 行 → 哪个错
    // ==================================================================

    @Test
    @DisplayName("B1 扣减 0 行 = 库存不足 → 400（用户可理解的业务结果）")
    void deductForOrder_zeroRows_isBadRequest() {
        when(inventoryMapper.deductStock(SKU, 999)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.deductForOrder(SKU, 999));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
    }

    @Test
    @DisplayName("B2 moveLockedToSold 0 行 = 账目不一致 → 500（★ 不是 400：订单说锁着 3 件、库存说只锁着 1 件，重试无意义）")
    void moveLockedToSold_zeroRows_isServerError() {
        when(inventoryMapper.moveLockedToSold(SKU, 3)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.moveLockedToSold(SKU, 3, ORDER));

        assertEquals(ResultCode.FAIL.getCode(), e.getCode());
    }

    @Test
    @DisplayName("B3 releaseLocked 0 行 = 账目不一致 → 500")
    void releaseLocked_zeroRows_isServerError() {
        when(inventoryMapper.releaseLocked(SKU, 3)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.releaseLocked(SKU, 3, ORDER));

        assertEquals(ResultCode.FAIL.getCode(), e.getCode());
    }

    @Test
    @DisplayName("B4 returnToStock 0 行 = 已售状态异常 → 500")
    void returnToStock_zeroRows_isServerError() {
        when(inventoryMapper.returnStock(SKU, 2)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.returnToStock(SKU, 2, ORDER));

        assertEquals(ResultCode.FAIL.getCode(), e.getCode());
    }

    // ==================================================================
    // [C] ★★ 本文件最重要的两条
    // ==================================================================

    @Test
    @DisplayName("C1 ★★ 四个写点 0 行时，流水【一次都不能写】—— 否则就是「库存没动、账本动了」的孤儿流水")
    void noOrphanLogWhenUpdateAffectsZeroRows() {
        when(inventoryMapper.deductStock(SKU, 1)).thenReturn(null);
        when(inventoryMapper.moveLockedToSold(SKU, 1)).thenReturn(null);
        when(inventoryMapper.releaseLocked(SKU, 1)).thenReturn(null);
        when(inventoryMapper.returnStock(SKU, 1)).thenReturn(null);

        assertThrows(BusinessException.class, () -> service.deductForOrder(SKU, 1));
        assertThrows(BusinessException.class, () -> service.moveLockedToSold(SKU, 1, ORDER));
        assertThrows(BusinessException.class, () -> service.releaseLocked(SKU, 1, ORDER));
        assertThrows(BusinessException.class, () -> service.returnToStock(SKU, 1, ORDER));

        // ★ 这条断言存在的理由：writeLog 在四个方法里都排在「判 null」【之后】，
        //   一旦有人把顺序调反（先写流水再判错），库存没动而账本多了一条 ——
        //   端到端看得到「多一条流水」吗？看不到，因为它只在失败时出现，而失败路径没人跑。
        // ★ any(InventoryLog.class) 而不是 any()：BaseMapper 同时有 insert(T) 与
        //   insert(Collection<T>) 两个重载，裸 any() 会让编译器无法选定重载（编译期即失败）。
        verify(inventoryLogMapper, never()).insert(any(InventoryLog.class));
    }

    @Test
    @DisplayName("C2 ★ 恒等式 change == after - before 由【构造】保证（before 是算出来的，不是查出来的）"
            + " —— ⚠️ 它只守 writeLog 的构造，【守不住】某个写点传错 change（那是 A2 的职责）")
    void ledgerIdentityHoldsForEveryWritePath() {
        when(inventoryMapper.deductStock(SKU, 3)).thenReturn(10);
        when(inventoryMapper.moveLockedToSold(SKU, 3)).thenReturn(10);
        when(inventoryMapper.releaseLocked(SKU, 3)).thenReturn(10);
        when(inventoryMapper.returnStock(SKU, 3)).thenReturn(10);
        when(inventoryMapper.adjustStock(SKU, 5)).thenReturn(50);

        service.deductForOrder(SKU, 3);
        service.moveLockedToSold(SKU, 3, ORDER);
        service.releaseLocked(SKU, 3, ORDER);
        service.returnToStock(SKU, 3, ORDER);
        service.adjust(SKU, 5, "盘点");

        ArgumentCaptor<InventoryLog> c = ArgumentCaptor.forClass(InventoryLog.class);
        verify(inventoryLogMapper, org.mockito.Mockito.times(5)).insert(c.capture());
        for (InventoryLog log : c.getAllValues()) {
            assertEquals(log.getChangeQuantity().intValue(),
                    log.getAfterStock().intValue() - log.getBeforeStock().intValue(),
                    "★ before 必须恒等于 after - change（写歪了就只能靠这条发现）");
        }
    }

    // ==================================================================
    // [D] 管理端调整
    // ==================================================================

    @Test
    @DisplayName("D1 delta == 0 → 400，且【既不调 mapper 也不写流水】（无意义的改动不该留下任何痕迹）")
    void adjust_zeroDelta_rejectedBeforeTouchingDb() {
        BusinessException e = assertThrows(BusinessException.class,
                () -> service.adjust(SKU, 0, "手滑"));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        verify(inventoryMapper, never()).adjustStock(any(), any(Integer.class));
        // ★ any(InventoryLog.class) 而不是 any()：BaseMapper 同时有 insert(T) 与
        //   insert(Collection<T>) 两个重载，裸 any() 会让编译器无法选定重载（编译期即失败）。
        verify(inventoryLogMapper, never()).insert(any(InventoryLog.class));
    }

    @Test
    @DisplayName("D2 adjust 0 行 → 400（★ 不是 500：管理员填了个太大的负数，是用户可理解的结果）")
    void adjust_zeroRows_isBadRequestAndLeavesNoLog() {
        when(inventoryMapper.adjustStock(SKU, -9999)).thenReturn(null);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.adjust(SKU, -9999, "填错了"));

        assertEquals(ResultCode.VALIDATE_FAILED.getCode(), e.getCode());
        // ★ any(InventoryLog.class) 而不是 any()：BaseMapper 同时有 insert(T) 与
        //   insert(Collection<T>) 两个重载，裸 any() 会让编译器无法选定重载（编译期即失败）。
        verify(inventoryLogMapper, never()).insert(any(InventoryLog.class));
    }

    @Test
    @DisplayName("D3 调整成功 → ADMIN_ADJUST，change = delta，referenceId 为 null（管理端调整本来就没有关联订单）")
    void adjust_success_writesAdjustLog() {
        when(inventoryMapper.adjustStock(SKU, 5)).thenReturn(50);

        service.adjust(SKU, 5, "盘点盈余");

        InventoryLog log = capturedLog();
        assertEquals(InventoryLogType.ADMIN_ADJUST, log.getType());
        assertEquals(5, log.getChangeQuantity().intValue());
        assertNull(log.getReferenceId());
    }

    @Test
    @DisplayName("D4 负 delta 也要写流水（change 为负）—— 「减少」不是「删除」，账本必须留痕")
    void adjust_negativeDelta_stillWritesLog() {
        when(inventoryMapper.adjustStock(SKU, -8)).thenReturn(12);

        service.adjust(SKU, -8, "报损");

        InventoryLog log = capturedLog();
        assertEquals(-8, log.getChangeQuantity().intValue());
        assertEquals(20, log.getBeforeStock().intValue());
    }

    // ==================================================================
    // [E] 分页夹紧（★ 夹紧必须写在 new Page 之前，所以【只能】看被调参数）
    // ==================================================================

    /** 抓住传给 mapper 的那个 Page —— 夹紧对不对，只能从这里看（方法返回的是 PageResult）。 */
    private IPage<?> capturedPage() {
        ArgumentCaptor<IPage> c = ArgumentCaptor.forClass(IPage.class);
        verify(inventoryMapper).selectInventoryPage(c.capture());
        return c.getValue();
    }

    @Test
    @DisplayName("E1 size = -1 → 夹到【下限 1】（★ 未夹紧时 MyBatis-Plus 的语义是不限量、查全表）")
    void listSkus_negativeSize_clampedToLowerBound() {
        when(inventoryMapper.selectInventoryPage(any())).thenReturn(new Page<InventoryVO>());

        service.listSkus(1, -1);

        assertEquals(1, capturedPage().getSize());
    }

    @Test
    @DisplayName("E2 size = 0 → 夹到 1（★ 未夹紧时返回空列表但 total 正常，看着像接口坏了）")
    void listSkus_zeroSize_clampedToOne() {
        when(inventoryMapper.selectInventoryPage(any())).thenReturn(new Page<InventoryVO>());

        service.listSkus(1, 0);

        assertEquals(1, capturedPage().getSize());
    }

    @Test
    @DisplayName("E3 size = 1000 → 夹到【上限 100】")
    void listSkus_hugeSize_clampedToUpperBound() {
        when(inventoryMapper.selectInventoryPage(any())).thenReturn(new Page<InventoryVO>());

        service.listSkus(1, 1000);

        assertEquals(100, capturedPage().getSize());
    }

    /**
     * ⚠️ 这条是【弱断言】，写明它弱在哪，别把它和 E1–E3 混为一谈：
     * MyBatis-Plus 的 {@code new Page<>(current, size)} 自己就有一层保护
     * （{@code current <= 0} 时保持默认的 1），所以即使我们把
     * {@code Math.max(page, 1)} 这行删掉，这里<b>依然是 1</b> —— 控制组实测不红。
     *
     * <p>★ 于是「页码夹紧」在本项目里是<b>防御性冗余</b>，而真正的洞在
     * {@code size} 方向（{@code size <= 0} 在 MP 里是「不限量、查全表」，它不兜）
     * —— 这正是 L1 当年要堵的那个洞。
     * ⇒ 这条只锁「结果正确」，不锁「是我们夹的」。想锁后者做不到，也不必。
     */
    @Test
    @DisplayName("E4 page = 0 → 最终 current 为 1（⚠️ MP 的 Page 自带这层保护，本条只锁结果、不锁我们的夹紧）")
    void listSkus_zeroPage_clampedToOne() {
        when(inventoryMapper.selectInventoryPage(any())).thenReturn(new Page<InventoryVO>());

        service.listSkus(0, 10);

        assertEquals(1, capturedPage().getCurrent());
    }

    // ==================================================================
    // [F] 流水查询：可选过滤的「不炸」边界
    //
    // ★★ 这里有一条【单测覆盖不到】的判定，写明它、而不是假装覆盖了：
    //   「type = \"\" 必须被归一化为 null，否则拼出 `type = ''`（恒不匹配且不报错）」
    //   要断言它就得读最终 SQL 文本，而 MP 的 lambda 方法引用依赖 TableInfo 缓存
    //   —— 纯 Mockito 单测（不启 Spring、不初始化 MyBatis）下拿不到，
    //   强行走 getCustomSqlSegment() 会抛
    //   "can not find lambda cache for this entity"（本文件第一版实测过）。
    // ⇒ 该判定归 day17-f（库存流水端到端）覆盖。
    // ★ 一般化：写单测时要能说清「这条为什么在这里测不了」，
    //   说不清就容易产生「写了但其实是恒真」的假绿。
    // ==================================================================

    @Test
    @DisplayName("F1 type 为空串时不炸、且真的去查了库（★ 归一化本身由 day17-f 端到端断言，见本节注释）")
    void listLogs_blankType_doesNotBlowUp() {
        doReturn(new Page<InventoryLog>()).when(inventoryLogMapper).selectPage(any(), any());

        org.junit.jupiter.api.Assertions.assertNotNull(service.listLogs(SKU, "", 1, 10));

        verify(inventoryLogMapper).selectPage(any(), any());
    }

    @Test
    @DisplayName("F2 type 与 skuId 同时为 null（两个可选过滤都不传）仍然成立 —— 挡的是「null 拼进 SQL 恒不匹配」那个坑")
    void listLogs_bothFiltersAbsent_doesNotBlowUp() {
        doReturn(new Page<InventoryLog>()).when(inventoryLogMapper).selectPage(any(), any());

        org.junit.jupiter.api.Assertions.assertNotNull(service.listLogs(null, null, 1, 10));

        verify(inventoryLogMapper).selectPage(any(), any());
    }

    @Test
    @DisplayName("F3 流水同样受夹紧保护（size = -1 → 1），且出参是 VO 而不是实体")
    void listLogs_clampsPageSize() {
        doReturn(new Page<InventoryLog>()).when(inventoryLogMapper).selectPage(any(), any());

        service.listLogs(SKU, null, 1, -1);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<IPage<InventoryLog>> pc = ArgumentCaptor.forClass(IPage.class);
        verify(inventoryLogMapper).selectPage(pc.capture(), any());
        assertEquals(1, pc.getValue().getSize());
        // 顺带证明出参类型是 VO：编译期即成立（返回值声明就是 PageResult<InventoryLogVO>），
        // 这里断言的其实是「不抛异常地走完了 convert」
        org.junit.jupiter.api.Assertions.assertNotNull(service.listLogs(SKU, null, 1, 10));
    }
}
