package com.mallx.marketing.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.marketing.common.CouponType;
import com.mallx.marketing.dto.CouponCreateDTO;
import com.mallx.marketing.entity.Coupon;
import com.mallx.marketing.entity.UserCoupon;
import com.mallx.marketing.mapper.CouponMapper;
import com.mallx.marketing.mapper.UserCouponMapper;
import com.mallx.marketing.service.CouponService;
import com.mallx.marketing.vo.CouponVO;
import com.mallx.marketing.vo.UserCouponVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * ★★★ 优惠券服务实现 —— <b>骨架</b>，5 处方法体由你写。
 *
 * <p>★ <b>填实现时：整段替换那行 TODO 与紧跟的 {@code throw}</b>，
 * <b>只删你正在填的那一个</b>（一个类里好几处 throw 长得一样，删错就编译不过）。
 *
 * <p>★★ <b>哪 5 处留给你，哪 2 处已经给了，为什么这么分</b>：
 * <pre>
 *   留给你的（本日的新东西）：
 *     ① pageCoupons   —— Page&lt;Coupon&gt; → Page&lt;CouponVO&gt; 换壳（Day 18 学过一遍）
 *     ② createCoupon  —— 「类型 ↔ 金额字段」的关系校验（DTO 层表达不了）
 *     ③ deleteCoupon  —— 被引用就不能删的守卫（FK NO ACTION）
 *     ④ receive       —— ★★ 本日核心：占名额 → 发到手（同一事务）
 *     ⑤ diagnoseReceiveFailure —— 慢路径诊断，只为把错误消息说清楚
 *
 *   已经给你的（与既有代码逐字同构，再敲一遍是浪费）：
 *     · listAvailable / listMine —— 形状与 ReviewServiceImpl 的 pageByProduct / pageMine
 *       <b>完全一样</b>（夹紧 → 调用 → PageResult.of）。你真想自己写，删掉重写即可。
 * </pre>
 *
 * <p>★ 本类<b>没有</b> {@code fillNames} 那种补名逻辑：券不需要查别的表，
 * 「我的券」的券面信息由 XML 的 JOIN 一次带出来。
 */
@Service
public class CouponServiceImpl extends ServiceImpl<CouponMapper, Coupon> implements CouponService {

    /**
     * 分页上限：单页最多 100 条 —— 与 {@code OrderServiceImpl} / {@code InventoryServiceImpl} /
     * {@code PaymentServiceImpl} / {@code ReviewServiceImpl} / {@code ProductServiceImpl}
     * 同一个值、同一套夹紧规则（本处是<b>第 6 份拷贝</b>）。
     *
     * <p>★ 仍不抽到 {@code mall-common}：那是一次跨模块重构，与本步无关；
     * 各处留一份、注释互相指明，等真有需要时再抽。
     *
     * <p>⚠️ 夹紧规则：{@code size = -1} 在 MP 里表示「不执行分页 = 查全表」；
     * {@code size = 0} 返回空列表但 total 正常（比报错更难发现）；
     * {@code size = 999} 不截断就会一次拖走整张表。★ 夹紧必须写在 {@code new Page<>()} <b>之前</b>。
     */
    private static final long MAX_PAGE_SIZE = 100;

    /** 领取记录 —— 只有领券与「我的券」会用到 */
    private final UserCouponMapper userCouponMapper;

    public CouponServiceImpl(UserCouponMapper userCouponMapper) {
        this.userCouponMapper = userCouponMapper;
    }

    // ================================================================
    // 管理端三件事
    // ================================================================

    /**
     * 管理端券列表（分页）。
     *
     * <p>四步，与 {@code ProductServiceImpl.pageAdminProducts} 同构：
     * <pre>
     *   ① 夹紧（★ 必须在 new Page 之前）：
     *        long safePage = Math.max(page, 1);
     *        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
     *   ② 条件 wrapper：
     *        new LambdaQueryWrapper&lt;Coupon&gt;()
     *            .eq(status != null, Coupon::getStatus, status)   ← 条件过滤：不传就全都要
     *            .orderByDesc(Coupon::getId);
     *      ★ status 是 Integer，只有 null 表达得出「不过滤」—— 这就是签名不用 int 的原因。
     *   ③ this.page(new Page&lt;&gt;(safePage, safeSize), wrapper)  → Page&lt;Coupon&gt;
     *   ④ ★ 换壳成 Page&lt;CouponVO&gt;：this.page() 只能吐实体。
     *      逐条 BeanUtils.copyProperties(c, vo) 之后，必须 new 一个新 Page 并
     *      【把 total/current/size 搬过去】—— 漏搬的话前端看到 total=0，分页器直接坏掉
     *      （Day 18 已踩过这个坑）。
     *   最后 return PageResult.of(voPage);
     * </pre>
     * ★ 本方法<b>不加</b> {@code @Transactional}：只读。
     */
    @Override
    public PageResult<CouponVO> pageCoupons(Integer status, long page, long size) {
        // ① 夹紧：★ 必须写在 new Page<>(...) 之前
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        // ② 条件 wrapper：status != null 才拼进 SQL —— 不传就是「全都要（含下架）」
        LambdaQueryWrapper<Coupon> wrapper = new LambdaQueryWrapper<Coupon>()
                .eq(status != null, Coupon::getStatus, status)
                .orderByDesc(Coupon::getId);

        // ③ 实体分页
        Page<Coupon> entityPage = this.page(new Page<>(safePage, safeSize), wrapper);

        // ④ 换壳 Page<Coupon> → Page<CouponVO>
        List<CouponVO> voList = new ArrayList<>();
        for (Coupon c : entityPage.getRecords()) {
            CouponVO vo = new CouponVO();
            BeanUtils.copyProperties(c, vo);
            voList.add(vo);
        }

        // ★★ total/current/size 必须一起搬过来 —— 漏搬的话前端看到 total=0，分页器直接坏掉
        Page<CouponVO> voPage = new Page<>(entityPage.getCurrent(), entityPage.getSize(),
                entityPage.getTotal());
        voPage.setRecords(voList);
        return PageResult.of(voPage);
    }

    /**
     * 管理端发券。
     *
     * <p>★ <b>两条关系校验</b>（DTO 层的 {@code @Valid} 表达不了，只能在这里守）：
     * <pre>
     *   ① endTime 必须晚于 startTime
     *        → BusinessException(VALIDATE_FAILED, "结束时间必须晚于开始时间")
     *      ★ 别漏：反过来的时间窗会让券「永远领不到」，而且不报错。
     *   ② 类型与金额字段必须配对（见 CouponType 的注释）：
     *        FIXED    → discountAmount 必须非 null，discountRate 应为 null
     *        DISCOUNT → discountRate   必须非 null，discountAmount 应为 null
     *      → 缺哪个就报哪个，消息里写明是哪种券缺了什么
     *      ★ 为什么不允许「两个都填」：一张券同时「减 20」和「打 8 折」，
     *        下单时按哪个算？—— 歧义本身就是拒绝的理由（阶段二会算金额，那时才发现就晚了）。
     * </pre>
     *
     * <p>★ 落库用 {@code this.save(coupon)} —— MP 的 insert，<b>会走填充器</b>
     * （{@code Coupon} 上标了 {@code @TableField(fill = ...)}），
     * 所以 {@code created_at} / {@code updated_at} <b>不用</b>你管。
     * <p>★ {@code status} 默认 1（可领）：列有 DEFAULT 1，但实体字段是 null 时 MP 会把它显式插成 null？
     * —— 不会：MP 的 NOT_NULL 策略跳过 null 字段，DB 默认值生效。不过<b>显式 set 1 更清楚</b>，
     * 由你决定；两种都对。
     * <p>★ {@code receivedCount} 必须<b>显式 set 0</b> 或交给 DB 默认值 ——
     * 但绝不能留 null 不管：列是 {@code NOT NULL DEFAULT 0}，靠 DEFAULT 兜住。
     *
     * <p>★ 返回新券 id（{@code coupon.getId()}，save 之后自增主键会回填）。
     */
    @Override
    public Long createCoupon(CouponCreateDTO dto) {
        // ============ 两条【关系】校验：@Valid 表达不了，只能在这里守 ============

        // ① 时间窗：反过来的时间窗会让券「永远领不到」，而且不报错
        if (!dto.getEndTime().isAfter(dto.getStartTime())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "结束时间必须晚于开始时间");
        }

        // ② 类型 ↔ 金额字段必须配对（见 CouponType 的注释）
        //    ★ 不允许「两个都填」：一张券同时「减 20」和「打 8 折」，下单时按哪个算？
        //      —— 歧义本身就是拒绝的理由（阶段二算金额时才发现就晚了）。
        if (CouponType.FIXED.equals(dto.getType())) {
            if (dto.getDiscountAmount() == null) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "满减券（FIXED）必须填写 discountAmount");
            }
            if (dto.getDiscountRate() != null) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "满减券（FIXED）不能同时填写 discountRate");
            }
        } else if (CouponType.DISCOUNT.equals(dto.getType())) {
            if (dto.getDiscountRate() == null) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "折扣券（DISCOUNT）必须填写 discountRate");
            }
            if (dto.getDiscountAmount() != null) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "折扣券（DISCOUNT）不能同时填写 discountAmount");
            }
        } else {
            // 理论上被 DTO 的 @Pattern 拦在外面，这里是「万一绕过参数层」的兜底
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "券类型只能是 FIXED 或 DISCOUNT");
        }

        // ============ 落库 ============
        Coupon coupon = new Coupon();
        BeanUtils.copyProperties(dto, coupon);   // 同名字段（name/type/金额/时间窗/totalCount）
        coupon.setStatus(1);                     // 可领；列有 DEFAULT 1，显式写更清楚
        coupon.setReceivedCount(0);              // 列是 NOT NULL DEFAULT 0，别留 null

        // ★ this.save() 走 MP 的 insert → 填充器生效，created_at / updated_at 不用管
        this.save(coupon);

        // ★ save 之后自增主键回填到实体，直接取
        return coupon.getId();
    }

    /**
     * 管理端删券。
     *
     * <p>★★ <b>守卫：被领取过就不许删。</b>两步：
     * <pre>
     *   ① 查这张券是否存在 → 不存在报 404（"优惠券不存在"）
     *       ★ 与「商品不存在」同一口径：先判 null。
     *   ② 查 user_coupons 里有没有引用它的行：
     *        userCouponMapper.selectCount(
     *            new LambdaQueryWrapper&lt;UserCoupon&gt;().eq(UserCoupon::getCouponId, id))
     *      &gt; 0  → 报 400（"该优惠券已被领取，不能删除"）
     *   ③ 都没有才 this.removeById(id)
     * </pre>
     *
     * <p>★★ <b>为什么必须手写这个守卫，而不是让 DB 报错</b>：
     * {@code user_coupons.coupon_id} 的外键是 <b>NO ACTION</b> → 不守卫的话
     * 数据库会抛一个外键违例，被全局异常处理器兜成 <b>code=500</b> ——
     * 明明是「你的操作不允许」，却报成「服务器内部错误」。
     * 手写守卫把它翻译成 <b>400 + 人话</b>。
     * ★ 这就是「谁引用我决定我能否物理删」（Day 03 立此规矩，Day 18 又踩过一次：
     * 删分类时也要查有没有商品引用它，且那次连<b>软删的商品</b>都得算上）。
     * ⚠️ 注意：{@code user_coupons} <b>没有</b> {@code is_deleted} 列
     * → 这里的 selectCount <b>不会</b>被 {@code @TableLogic} 改写成「只看存活行」，
     * 查到的就是全部。反过来说：如果哪天给这张表加了软删，这条守卫就会静默漏掉已软删的行
     * （Day 18 的 {@code countByCategoryId} 就是为了绕开这个才手写 XML 的）。
     */
    @Override
    public void deleteCoupon(Long id) {
        // ① 券在不在 —— 与「商品不存在」同一口径：先判 null 再说别的
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "优惠券不存在");
        }

        // ② 被领取过就不许删。
        //    ★ 不手写这一步的话，user_coupons.coupon_id 的 FK（NO ACTION）会抛违例，
        //      被全局处理器兜成 code=500 —— 明明是「你的操作不允许」，却报成「服务器内部错误」。
        //    ⚠️ user_coupons 没有 is_deleted 列 → 这个 selectCount 不会被 @TableLogic 改写，
        //       查到的就是全部行。
        long refs = userCouponMapper.selectCount(
                new LambdaQueryWrapper<UserCoupon>().eq(UserCoupon::getCouponId, id));
        if (refs > 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "该优惠券已被领取，不能删除");
        }

        // ③ 两道守卫都过了才真删（物理删，本表无软删列）
        this.removeById(id);
    }

    // ================================================================
    // C 端三件事
    // ================================================================

    /**
     * C 端可领券列表（公开）。
     * <p>★ 本方法<b>已经写好</b>（形状与 {@code ReviewServiceImpl.pageByProduct} 逐字同构）。
     * 三步：夹紧 → 调用 XML → 包公共壳。
     */
    @Override
    public PageResult<CouponVO> listAvailable(long page, long size) {
        // ① 夹紧：必须在 new Page 之前 —— 构造进去的值就是最终发给 DB 的值
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        // ② 首参必须传 IPage，否则分页插件静默不改写 SQL（不报错、查全表）
        IPage<CouponVO> result = baseMapper.selectAvailableCoupons(new Page<>(safePage, safeSize));

        // ③ 字段集正好是分页四件套 —— 直接复用公共壳
        return PageResult.of(result);
    }

    /**
     * ★★★ 领券（本日核心）。
     *
     * <p>三步，<b>顺序不能换</b>：
     * <pre>
     *   ① 占名额：int granted = baseMapper.increaseReceivedCount(couponId);
     *      granted == 0 → 领不到 → 抛异常，消息由 ⑤ diagnoseReceiveFailure(couponId) 生成
     *
     *   ② 发到手：int inserted = userCouponMapper.insertIgnore(userId, couponId);
     *      inserted == 0 → 说明【已经领过】→ 抛 400「您已领取过该优惠券」
     *      ⚠️ 此时 ① 已经加过名额了，但【抛异常会把整个事务回滚】→ 名额自动退回，
     *         不会出现「占了名额却没发到券」的泄漏。
     *
     *   ③ 两步都成功 → 方法直接结束（返回 void，什么都不用返回）
     * </pre>
     *
     * <p>★★ 为什么是「先占名额、后发到手」，而不是反过来：
     * <pre>
     *   先 CAS 后 INSERT  →  重复领时：占了名额 → INSERT 撞唯一约束 → 回滚
     *   先 INSERT 后 CAS  →  抢光时  ：插进去了 → CAS 失败 → 回滚
     * </pre>
     * 两种都对（都在同一事务里），差别只在「重复领」这个<b>最常见的失败</b>上：
     * 先 CAS 的话，重复领这件事在数据库层就被唯一约束挡掉，不需要额外查询。
     *
     * <p>★★ 必须 {@code @Transactional(rollbackFor = Exception.class)} ——
     * 这是本日<b>唯一</b>需要事务的方法：它要保证「两张表的写同生共死」。
     * ★ 判据是「写点个数」，不是「方法重不重要」：
     * 本类其余五个方法要么只读、要么单条写（单条 UPDATE/INSERT 自身即原子），所以都不加。
     * ★ {@code rollbackFor = Exception.class} 要显式写：默认只回滚 RuntimeException，
     * 将来若加进来一个受检异常就会静默不回滚。
     *
     * <p>★ 报错一律走 {@code ResultCode.VALIDATE_FAILED}（= 400），
     * HTTP 状态码仍是 200 —— 业务失败码在 body 里，这是本项目的混合约定。
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void receive(Long userId, Long couponId) {
        // ① 占名额（CAS）：影响行数就是答案 —— 0 行 = 领不到
        //    ⚠️ 绝不「先 getById 查一遍再判断能不能领」—— 那是【先查后改】，并发下会超发。
        //       查只允许出现在失败【之后】的诊断里。
        int granted = baseMapper.increaseReceivedCount(couponId);
        if (granted == 0) {
            // 慢路径诊断：把「领不到」翻译成人话（不参与任何并发判断，只产出文案）
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    this.diagnoseReceiveFailure(couponId));
        }

        // ② 发到手：0 行 = 撞唯一约束 = 已经领过
        //    ⚠️ 此时 ① 已加过名额，但抛异常会把整个事务回滚 → 名额自动退回，
        //       不会出现「占了名额却没发到券」的泄漏。
        int inserted = userCouponMapper.insertIgnore(userId, couponId);
        if (inserted == 0) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "您已领取过该优惠券");
        }

        // ③ 两步都成功 → 直接结束（返回 void）
    }

    /**
     * 我的券（分页）。
     * <p>★ 本方法<b>已经写好</b>（与 {@code ReviewServiceImpl.pageMine} 逐字同构）。
     * 归属过滤在 SQL 里；{@code userId} 只用于「传给 SQL 去过滤」，不参与任何判断。
     */
    @Override
    public PageResult<UserCouponVO> listMine(Long userId, long page, long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        IPage<UserCouponVO> result =
                userCouponMapper.selectMyCoupons(new Page<>(safePage, safeSize), userId);

        return PageResult.of(result);
    }

    // ================================================================
    // 私有辅助
    // ================================================================

    /**
     * ★★ <b>慢路径诊断：把「领不到」翻译成人话</b>。
     *
     * <p>调用时机：<b>只在 {@code increaseReceivedCount} 返回 0 之后</b>。
     *
     * <p>★★ 为什么它可以「先查一下」而不违反「绝不先查后改」：
     * <pre>
     *   正确性早已由 ① 的影响行数定死了（0 行 = 领不到）。
     *   这次查询【不参与任何并发判断】，它唯一的产出是一句错误文案。
     *   所以查得准不准、查的瞬间数据有没有变，都不影响「这张券没领到」这个结论。
     * </pre>
     * ⇒ 这就是「<b>快速路径 CAS + 慢路径诊断</b>」：快路径负责对，慢路径负责好懂。
     * ★ 反过来做（先查、再根据查到的结果决定要不要 CAS）就是 TOCTOU —— 会超发。
     *
     * <p>五条分支（按顺序判，第一条命中即返回）：
     * <pre>
     *   this.getById(couponId) == null                → "优惠券不存在"
     *   status == null || status != 1                 → "优惠券已下架"
     *   LocalDateTime.now().isBefore(startTime)       → "优惠券尚未开始发放"
     *   LocalDateTime.now().isAfter(endTime)          → "优惠券已过期"
     *   receivedCount >= totalCount                   → "优惠券已被抢光"
     *   以上都不是（并发下刚好被别的事务改回来了）    → "优惠券暂不可领取"
     * </pre>
     * ★ 这里用 Java 的 {@code LocalDateTime.now()} 比较是<b>允许</b>的 ——
     * 它在 SQL 的 CAS 里才是不允许的（要与 DB 时钟一致）。
     * 慢路径的文案差几毫秒，没人会发现。
     * ⚠️ 比较前先判 null：{@code start_time} / {@code end_time} 列是 NOT NULL，
     * 但 {@code getById} 返回的实体字段仍可能是 null（比如列被改过），防御性判一下不亏。
     * ⚠️ 最后那条兜底分支不能省：并发场景下「CAS 失败」与「这次查询看到的快照」之间
     * 必然有缝隙，缝隙里发生的事就是用它接住的 —— 否则方法会返回 null 消息。
     */
    private String diagnoseReceiveFailure(Long couponId) {
        // 只查一次 —— 诊断不参与任何并发判断，快照不一致也不影响「这张券没领到」的结论
        Coupon coupon = this.getById(couponId);
        if (coupon == null) {
            return "优惠券不存在";
        }
        if (coupon.getStatus() == null || coupon.getStatus() != 1) {
            return "优惠券已下架";
        }
        LocalDateTime now = LocalDateTime.now();
        // ⚠️ 时间字段判 null 再比：列是 NOT NULL，但实体字段仍可能是 null，防御一下不亏
        if (coupon.getStartTime() != null && now.isBefore(coupon.getStartTime())) {
            return "优惠券尚未开始发放";
        }
        if (coupon.getEndTime() != null && now.isAfter(coupon.getEndTime())) {
            return "优惠券已过期";
        }
        // ⚠️ Integer 拆箱前先判 null，否则 NPE
        if (coupon.getReceivedCount() != null && coupon.getTotalCount() != null
                && coupon.getReceivedCount() >= coupon.getTotalCount()) {
            return "优惠券已被抢光";
        }
        // ★ 兜底分支不能省：并发下「CAS 失败」与「这次查询看到的快照」之间必有缝隙，
        //   缝隙里发生的事就靠它接住 —— 否则方法会返回 null 消息。
        return "优惠券暂不可领取";
    }
}
