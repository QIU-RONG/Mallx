package com.mallx.admin.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.admin.dto.AdminCreateDTO;
import com.mallx.admin.dto.AdminUpdateDTO;
import com.mallx.admin.entity.Admin;
import com.mallx.admin.mapper.AdminMapper;
import com.mallx.admin.mapper.AdminRbacMapper;
import com.mallx.admin.service.AdminAccountManageService;
import com.mallx.admin.vo.AdminDetailVO;
import com.mallx.admin.vo.AdminVO;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import org.springframework.beans.BeanUtils;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 管理员的建档与治理实现（Day 23 骨架）。
 *
 * <p>★ 继承 {@code ServiceImpl<AdminMapper, Admin>} 只为了拿 {@code getById} /
 * {@code page} / {@code update} 这几个 {@code BaseMapper} 的现成方法 ——
 * 与 {@code AdminUserServiceImpl} 同一形状。
 * <p>★ 关联表的写入走 {@link AdminRbacMapper}（手写 SQL），
 * 因为 {@code admin_roles} 是复合主键表、且「建档」需要 {@code ON CONFLICT RETURNING}。
 */
@Service
public class AdminAccountManageServiceImpl extends ServiceImpl<AdminMapper, Admin>
        implements AdminAccountManageService {

    /**
     * 分页上限：单页最多 100 条。
     *
     * <p>★★ 本处是第 <b>7</b> 份拷贝（前六：OrderServiceImpl / InventoryServiceImpl /
     * ReviewServiceImpl / ProductServiceImpl / CouponServiceImpl / AdminUserServiceImpl）。
     * <p>★ {@code docs/backlog.md} 的 T1 写的触发条件是「等出现第 6 份拷贝」——
     * 那个条件在 Day 22 就已达成了，当时的结论是<b>仍然不抽</b>，理由是
     * 「抽常量要动 5 个模块的 POM 可见性与编译边界，收益是省 4 行，
     * 风险却是 5 条已验收链路同时受影响」。
     * <b>本日维持同一结论</b>，并把「现在已经是第 7 份」这个事实写下来 ——
     * 免得下次看到 T1 又以为它停在 5 份。
     * <p>⚠️ 真正该抽的时机是「规则本身要变」（比如改成配置项）而不是「又多了一份」：
     * 多一份拷贝的成本是抄 4 行，而改动 5 个模块的成本是重跑 5 条 E2E。
     *
     * <p>★ 夹紧必须写在 {@code new Page<>(...)} <b>之前</b> —— 写进构造参数里就晚了
     * （{@code size = -1} 会撞 MP 的「负数=不限量」语义，直接查全表）。
     */
    private static final long MAX_PAGE_SIZE = 100;

    private final AdminRbacMapper adminRbacMapper;
    private final PasswordEncoder passwordEncoder;

    /**
     * 构造器注入：{@code PasswordEncoder} 由 mall-common 的 SecurityConfig 提供
     * （{@code AdminAuthController} 也是这么拿的 —— 同一个 Bean，
     * 所以「建档时 encode」与「登录时 matches」天然是同一套算法）。
     */
    public AdminAccountManageServiceImpl(AdminRbacMapper adminRbacMapper,
                                         PasswordEncoder passwordEncoder) {
        this.adminRbacMapper = adminRbacMapper;
        this.passwordEncoder = passwordEncoder;
    }

    /**
     * 管理员分页（含已禁用）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>夹紧两行（{@code safePage} / {@code safeSize}）必须在 {@code new Page<>()} 之前；</li>
     *   <li>{@code keyword} 跨 {@code username} / {@code nickname} 两列任一命中
     *       ⇒ {@code .and(w -> w.like(...).or().like(...))}
     *       ★ <b>包括号</b>：直写会与 {@code status} 条件拼成 {@code status=? AND a OR b}
     *       —— AND 优先级高于 OR ⇒「已禁用但命中关键字」的行会漏进来
     *       （与 Day 22 {@code pageUsers} 完全同一个坑）；</li>
     *   <li>出口换壳 {@code Page<Admin>} → {@code Page<AdminVO>}，
     *       ★ {@code total/current/size} 必须搬到新 Page（否则前端 total=0）；</li>
     *   <li>★ 逐行 {@code BeanUtils.copyProperties}，<b>绝不能返回 Admin 实体</b>
     *       —— 它带 {@code password}（Day 22 那个外泄的同款形状）。</li>
     * </ol>
     */
    @Override
    public Page<AdminVO> pageAdmins(long current, long size, String keyword, Integer status) {
        // ★ 夹紧两行必须在 new Page<>(...) 之前 —— size=-1 会撞 MP 的「负数=不限量」。
        long safePage = Math.max(current, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        LambdaQueryWrapper<Admin> wrapper = new LambdaQueryWrapper<Admin>()
                // 管理端口径：不写死 status，不传就「启用 + 禁用」都要（同 Day 22 pageUsers）
                .eq(status != null, Admin::getStatus, status)
                // ★★ keyword 必须用 .and(...) 包一层括号：直写会拼成
                //    status=? AND username LIKE ? OR nickname LIKE ? —— AND 优先级高于 OR，
                //    「已禁用但命中关键字」的行会漏进来（Day 22 pageUsers 同一个坑）。
                .and(keyword != null && !keyword.isBlank(),
                        w -> w.like(Admin::getUsername, keyword)
                                .or().like(Admin::getNickname, keyword))
                .orderByDesc(Admin::getId);

        Page<Admin> page = this.page(new Page<>(safePage, safeSize), wrapper);

        // ★★ 出口换壳：Admin 实体带 password，绝不能原样返回（Day 22 那个外泄的同款形状）。
        List<AdminVO> voList = new ArrayList<>();
        for (Admin a : page.getRecords()) {
            AdminVO vo = new AdminVO();
            BeanUtils.copyProperties(a, vo);
            voList.add(vo);
        }

        // 换壳：total/current/size 必须搬到新 Page 上，否则前端看到 total=0
        Page<AdminVO> voPage = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        voPage.setRecords(voList);
        return voPage;
    }

    /**
     * 管理员详情（含角色 id + 角色码）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>{@code this.getById(id)}，null → 404（真 404，不伪装）；</li>
     *   <li>角色 id：{@code adminRbacMapper.selectRoleIdsByAdminId(id)}；</li>
     *   <li>角色码：<b>复用</b> {@code this.baseMapper.selectRoleCodesByAdminId(id)}
     *       （已有资产，不必新写 SQL）；</li>
     *   <li>出口 {@link AdminDetailVO}（平铺赋值，<b>不含 password</b>）。</li>
     * </ol>
     * ⚠️ 刻意<b>不</b>从 token 里取角色码：token 是签发时的快照（路线①），
     * 详情页要的是「此刻」。
     */
    @Override
    public AdminDetailVO getDetail(Long id) {
        Admin admin = this.getById(id);
        if (admin == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "管理员不存在");
        }
        AdminDetailVO vo = new AdminDetailVO();
        BeanUtils.copyProperties(admin, vo);
        // 角色 id：关联表直查；角色码：复用既有 SQL（AdminMapper，不新写 —— 少一处漂移面）
        vo.setRoleIds(adminRbacMapper.selectRoleIdsByAdminId(id));
        vo.setRoleCodes(this.baseMapper.selectRoleCodesByAdminId(id));
        return vo;
    }

    /**
     * 新建管理员。
     *
     * <p>实现要点：
     * <ol>
     *   <li>★ {@code String encoded = passwordEncoder.encode(dto.getPassword())}
     *       —— 落库的是 {@code $2a$…}。照抄种子里的 {@code {noop}admin123} = 明文入库；</li>
     *   <li>构造 {@code Admin} 实体（username / encoded / nickname），
     *       ⚠️ {@code status} 不用设（XML 里固定写 1，不让「新建一个已禁用的账号」存在）；</li>
     *   <li>调 {@code adminRbacMapper.insertAdminIfAbsent(admin)}，
     *       ★ 返回 {@code null} = username 撞了 UNIQUE ⇒
     *       {@code throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
     *       "用户名已存在")}（<b>400</b>，不是 500）；</li>
     *   <li>返回新 id。★ 不加 {@code @Transactional}：单条 INSERT 自身即原子，
     *       且它不写关联表（新管理员默认无角色）。</li>
     * </ol>
     */
    @Override
    public Long create(AdminCreateDTO dto) {
        Admin admin = new Admin();
        admin.setUsername(dto.getUsername());
        // ★ 必须 encode：照抄种子里的 {noop}admin123 等于明文入库。
        //   同一个 Bean 与 AdminAuthController 登录时的 matches 配成一套算法。
        admin.setPassword(passwordEncoder.encode(dto.getPassword()));
        admin.setNickname(dto.getNickname());
        // ⚠️ status 不设：XML 里固定写 1 —— 不让「新建一个已禁用的账号」存在。

        // ★ ON CONFLICT (username) DO NOTHING RETURNING id ⇒ 返回 null = 用户名已被占用。
        //   不 catch DuplicateKeyException：GlobalExceptionHandler 没有它的出口，会被兜成 500。
        Long newId = adminRbacMapper.insertAdminIfAbsent(admin);
        if (newId == null) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "用户名已存在");
        }
        // 不加 @Transactional：单条 INSERT 自身即原子，且不写关联表（新管理员默认无角色）。
        return newId;
    }

    /**
     * 编辑管理员（昵称 / 状态）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>★ 先判语义：{@code dto.getNickname() == null && dto.getStatus() == null}
     *       ⇒ 400（一次没有任何意图的请求）；</li>
     *   <li>★ <b>护栏③</b>：{@code dto.getStatus() != null && dto.getStatus() == 0
     *       && id.equals(currentAdminId)} ⇒ 400（不许停用自己）。
     *       判据是 {@code id.equals(...)} 而<b>不是</b> {@code ==}
     *       —— {@code Long} 在 [-128,127] 以外不拆箱比较就<b>是</b>引用比较，
     *       而管理员 id 恰好可能大于 127（本机新装库不会，但这是「错得安静」的形状）；</li>
     *   <li>条件更新一句到底：
     *       {@code this.baseMapper.update(null, new LambdaUpdateWrapper<Admin>()
     *          .eq(Admin::getId, id)
     *          .set(dto.getNickname() != null, Admin::getNickname, dto.getNickname())
     *          .set(dto.getStatus()   != null, Admin::getStatus,   dto.getStatus())
     *          .set(Admin::getUpdatedAt, LocalDateTime.now()))}
     *       ★ {@code .set(条件, …)} 的重载让「字段可选地更新」在一句 SQL 里表达出来 ——
     *       这比「先读出来改字段再整体 update」少一次往返，也避免覆盖掉并发写；
     *       ⚠️ 手写 UpdateWrapper 的 UPDATE <b>不走</b>自动填充器 ⇒ 显式补 {@code updated_at}
     *       （同 Day 22 的 {@code AdminUserServiceImpl#updateStatus}）；</li>
     *   <li>★ <b>影响行数即答案</b>：0 行 = 该 id 不存在 ⇒ 404。</li>
     * </ol>
     */
    @Override
    public void update(Long id, AdminUpdateDTO dto, Long currentAdminId) {
        // ① 一次没有任何意图的请求 ⇒ 400（宁可显式拒绝，也不发一条空 UPDATE）
        if (dto.getNickname() == null && dto.getStatus() == null) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "没有需要修改的字段");
        }
        // ② ★ 护栏③：不许停用自己。
        //    ⚠️ 判 id.equals(currentAdminId) 而不是 ==：Long 是包装类型，
        //    在缓存区间 [-128,127] 之外 == 比较的是引用 ⇒ 会「错得安静」。
        if (dto.getStatus() != null && dto.getStatus() == 0 && id.equals(currentAdminId)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "不能停用当前登录账号");
        }
        // ③ 条件更新一句到底：.set(条件, ...) 把「字段可选地更新」表达在同一句 SQL 里，
        //    比「先读出来改字段再整体 update」少一次往返，也不会覆盖并发写。
        //    ⚠️ 手写 UpdateWrapper 不走自动填充器 ⇒ 显式补 updated_at。
        int rows = this.baseMapper.update(null, new LambdaUpdateWrapper<Admin>()
                .eq(Admin::getId, id)
                .set(dto.getNickname() != null, Admin::getNickname, dto.getNickname())
                .set(dto.getStatus() != null, Admin::getStatus, dto.getStatus())
                .set(Admin::getUpdatedAt, LocalDateTime.now()));

        // ④ ★ 影响行数即答案：0 行 = 该 id 不存在 ⇒ 404
        if (rows == 0) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "管理员不存在");
        }
    }

    /**
     * 物理删除管理员（含先清 {@code admin_roles}）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>★ <b>护栏③</b>：{@code id.equals(currentAdminId)} ⇒ 400（不许删自己）。
     *       ⚠️ 这条要在任何 delete <b>之前</b>；</li>
     *   <li>{@code adminRbacMapper.deleteAdminRolesByAdminId(id)} —— 先清引用
     *       （FK 是 NO ACTION，不清就 23503）；</li>
     *   <li>{@code this.baseMapper.deleteById(id)}；★ 影响行数 0 ⇒ 404；</li>
     *   <li>★ 必须 {@code @Transactional}：这是<b>两条语句</b>
     *       （判据同 {@code InventoryService:119}）。</li>
     * </ol>
     * ⚠️ 顺序细节：把「清关联行」放在「删主行」之前，是因为 FK 拦的是旧方向；
     * 但如果 id 压根不存在，第 2 步会白删 0 行、第 3 步才报 404 —— 可接受
     * （同事务，无副作用残留）。★ 若想更早失败，也可以在删前先 {@code exists} 一次，
     * 但那就多一次往返；沿用「影响行数即答案」即可。
     */
    @Override
    @Transactional
    public void delete(Long id, Long currentAdminId) {
        // ★ 护栏③：不许删自己 —— 必须在任何 delete 之前（否则先清完关联行才报错）
        if (id.equals(currentAdminId)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "不能删除当前登录账号");
        }
        // 先清引用：FK 是 NO ACTION，不清就是 23503（现场 500）
        adminRbacMapper.deleteAdminRolesByAdminId(id);

        int rows = this.baseMapper.deleteById(id);
        // ★ 影响行数即答案：0 行 = 该 id 不存在 ⇒ 404。
        //    ⚠️ 此时上一步的 deleteAdminRoles 已经白删了 0 行 —— 同事务一起回滚，无残留。
        if (rows == 0) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "管理员不存在");
        }
    }

    /**
     * 给管理员全量替换角色。
     *
     * <p>实现要点（顺序很重要）：
     * <ol>
     *   <li>★ <b>护栏③</b>：{@code id.equals(currentAdminId) && roleIds.isEmpty()}
     *       ⇒ 400（不许清空自己的角色）。<b>只拦「清空」</b>——
     *       给自己换个角色（非空集合）是合法操作；</li>
     *   <li>★ 判管理员存在：{@code this.getById(id) == null} ⇒ 404
     *       （这一步是「读」，不构成 TOCTOU：后面写的是关联表，
     *       而 {@code admins} 行的存在性由 FK 保证 —— 真的并发删了，
     *       第 4 步的 INSERT 会撞 23503，仍然不会静默写坏数据）；</li>
     *   <li>★ 预校验角色 id：{@code roleIds} 非空时
     *       {@code adminRbacMapper.countRolesByIds(roleIds) != roleIds.size()} ⇒ 400
     *       （「含不存在的角色 id」）。<b>空集合时跳过</b>（{@code IN ()} 会语法错）；</li>
     *   <li>{@code deleteAdminRolesByAdminId(id)}；</li>
     *   <li>★ {@code roleIds} 非空时才 {@code insertAdminRoles(id, roleIds)}
     *       （空集合时 {@code <foreach>} 会拼出空 VALUES）；</li>
     *   <li>★ 必须 {@code @Transactional}（第 4、5 步是两条语句，
     *       中间有一瞬「无角色」的窗口，事务把它吃掉）。</li>
     * </ol>
     */
    @Override
    @Transactional
    public void assignRoles(Long id, List<Long> roleIds, Long currentAdminId) {
        // 去重：count(*) 对 IN (1,1) 只算 1 行，不去重会把「传了重复 id」误报成
        // 「含不存在的角色 id」（报错信息与事实不符）。顺序无关，故 distinct 即可。
        List<Long> target = (roleIds == null) ? new ArrayList<>() : roleIds.stream().distinct().toList();

        // ★ 护栏③：不许清空自己的角色。只拦「清空」—— 给自己换成另一个角色是合法操作。
        if (id.equals(currentAdminId) && target.isEmpty()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "不能清空当前登录账号的角色");
        }
        // 判管理员存在（这一步是「读」，不构成 TOCTOU：后面写的是关联表，
        // 而 admins 行的存在性由 FK 保证 —— 真被并发删了，INSERT 会撞 23503，不会静默写坏）。
        if (this.getById(id) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "管理员不存在");
        }
        // 预校验角色 id：空集合必须跳过（<foreach> 会拼出 IN () ⇒ 语法错）。
        // ★ 这是「不靠异常做控制流」——不让 FK 的 23503 兜底变成 500。
        if (!target.isEmpty() && adminRbacMapper.countRolesByIds(target) != target.size()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "含不存在的角色 id");
        }

        // 全量替换：先清后插，两条语句必须同事务（中间有一瞬「无角色」的窗口）
        adminRbacMapper.deleteAdminRolesByAdminId(id);
        if (!target.isEmpty()) {
            adminRbacMapper.insertAdminRoles(id, target);
        }
    }
}
