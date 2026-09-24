package com.mallx.admin.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.admin.dto.RoleCreateDTO;
import com.mallx.admin.dto.RoleUpdateDTO;
import com.mallx.admin.entity.Permission;
import com.mallx.admin.entity.Role;
import com.mallx.admin.mapper.AdminRbacMapper;
import com.mallx.admin.mapper.PermissionMapper;
import com.mallx.admin.mapper.RoleMapper;
import com.mallx.admin.service.RoleManageService;
import com.mallx.admin.vo.RoleDetailVO;
import com.mallx.admin.vo.RoleVO;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 角色的建档与治理实现（Day 23 骨架）—— 护栏①② 的落点。
 */
@Service
public class RoleManageServiceImpl extends ServiceImpl<RoleMapper, Role>
        implements RoleManageService {

    /**
     * 超级管理员的角色码（护栏①② 的判据）。
     * <p>★ 判 {@code code} 而<b>不是</b> {@code id == 1}：{@code id} 是插入顺序的产物，
     * {@code code} 才是语义。判 {@code id} 会在「有人手工挪过 id」时静默失效。
     * <p>★ 定义成常量而不是到处写字符串字面量：护栏①（update / delete）与护栏②（assignPermissions）
     * 三处都要用同一个值，写三遍字面量迟早有一处打错（而打错的后果是护栏静默失效）。
     */
    private static final String SUPER_ADMIN_CODE = "SUPER_ADMIN";

    /**
     * 分页上限：单页最多 100 条（★ 第 8 份拷贝 —— 见
     * {@code AdminAccountManageServiceImpl} 的同名常量注释，T1 的结论仍是「不抽」）。
     * <p>★ 夹紧必须写在 {@code new Page<>(...)} 之前。
     */
    private static final long MAX_PAGE_SIZE = 100;

    private final AdminRbacMapper adminRbacMapper;
    private final PermissionMapper permissionMapper;

    /**
     * ★ 为什么还要注入 {@code PermissionMapper}：{@link #getDetail} 要把
     * {@code permissionIds} 翻译成 {@code permissionCodes}，需要查 {@code permissions} 表
     * —— 用 {@code BaseMapper.selectBatchIds(ids)} 即可，<b>不必</b>新写 SQL
     * （11 条手写语句里没有「按 id 批量查权限码」这一条，是刻意的：
     * BaseMapper 已经提供，重写一份就是多一处漂移面）。
     * <p>⚠️ 空集合时<b>不要</b>调用 {@code selectBatchIds}（空 {@code IN} 在部分版本会拼出
     * {@code IN ()}）—— 直接给空 list。
     */
    public RoleManageServiceImpl(AdminRbacMapper adminRbacMapper,
                                 PermissionMapper permissionMapper) {
        this.adminRbacMapper = adminRbacMapper;
        this.permissionMapper = permissionMapper;
    }

    /**
     * 角色分页（含已停用）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>夹紧两行在 {@code new Page<>()} 之前；</li>
     *   <li>{@code keyword} 跨 {@code name} / {@code code} 两列任一命中 ⇒
     *       ★ 写成 {@code .and(w -> w.like(...).or().like(...))} <b>包括号</b>
     *       （本方法目前只有一个条件，括不括号结果一样 —— 但按包括号的形状写，
     *       将来加 status 过滤时就不会掉进那个坑）；</li>
     *   <li>出口换壳 {@code Page<Role>} → {@code Page<RoleVO>}，
     *       {@code total/current/size} 必须搬过去。</li>
     * </ol>
     */
    @Override
    public Page<RoleVO> pageRoles(long current, long size, String keyword) {
        // ★ 夹紧两行必须在 new Page<>(...) 之前（size=-1 会撞 MP 的「负数=不限量」）
        long safePage = Math.max(current, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        LambdaQueryWrapper<Role> wrapper = new LambdaQueryWrapper<Role>()
                // ★ 包括号：本方法目前只有 keyword 一个条件，括不括号结果一样 —— 但按包括号的
                //   形状写，将来加 status 过滤时就不会掉进「status=? AND a OR b」那个坑。
                .and(keyword != null && !keyword.isBlank(),
                        w -> w.like(Role::getName, keyword).or().like(Role::getCode, keyword))
                .orderByDesc(Role::getId);

        Page<Role> page = this.page(new Page<>(safePage, safeSize), wrapper);

        List<RoleVO> voList = new ArrayList<>();
        for (Role r : page.getRecords()) {
            RoleVO vo = new RoleVO();
            BeanUtils.copyProperties(r, vo);
            voList.add(vo);
        }

        // 换壳：total/current/size 必须搬到新 Page，否则前端看到 total=0
        Page<RoleVO> voPage = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        voPage.setRecords(voList);
        return voPage;
    }

    /**
     * 角色详情（含 permissionIds + permissionCodes）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>{@code this.getById(id)}，null → 404；</li>
     *   <li>{@code adminRbacMapper.selectPermissionIdsByRoleId(id)} → {@code permissionIds}；</li>
     *   <li>{@code permissionCodes}：用注入的 {@code permissionMapper.selectBatchIds(permissionIds)}
     *       查 {@code permissions} 表（⚠️ 不能用 {@code this.baseMapper} —— 那是 roles 的 mapper）；
     *       ★ 空集合时不要调用 {@code selectBatchIds}，直接给空 list；</li>
     *   <li>出口 {@link RoleDetailVO}。</li>
     * </ol>
     */
    @Override
    public RoleDetailVO getDetail(Long id) {
        Role role = this.getById(id);
        if (role == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
        RoleDetailVO vo = new RoleDetailVO();
        BeanUtils.copyProperties(role, vo);

        // 「角色【定义】了哪些权限」—— 与 AdminMapper 那条「按管理员查的【生效】集合」不是一回事
        List<Long> permissionIds = adminRbacMapper.selectPermissionIdsByRoleId(id);
        vo.setPermissionIds(permissionIds);

        // 把 permissionIds 翻译成 permissionCodes。★ 空集合不要调 selectBatchIds
        // （部分版本会拼出 IN ()）⇒ 直接给空 list。
        List<String> codes = new ArrayList<>();
        if (!permissionIds.isEmpty()) {
            for (Permission p : permissionMapper.selectBatchIds(permissionIds)) {
                codes.add(p.getCode());
            }
        }
        vo.setPermissionCodes(codes);
        return vo;
    }

    /**
     * 新建角色。
     *
     * <p>实现要点：
     * <ol>
     *   <li>构造 {@code Role}（name / code / description）；
     *       ⚠️ 不设 {@code status}（XML 固定写 1）；</li>
     *   <li>{@code adminRbacMapper.insertRoleIfAbsent(role)}；</li>
     *   <li>★ 返回 {@code null} = code 撞 UNIQUE ⇒ 400「角色码已存在」；</li>
     *   <li>返回新 id。★ 不加 {@code @Transactional}（单条 INSERT）。</li>
     * </ol>
     */
    @Override
    public Long create(RoleCreateDTO dto) {
        Role role = new Role();
        role.setName(dto.getName());
        role.setCode(dto.getCode());
        role.setDescription(dto.getDescription());
        // ⚠️ status 不设：XML 里固定写 1

        // ★ ON CONFLICT (code) DO NOTHING RETURNING id ⇒ null = 角色码已被占用（400，不是 500）
        Long newId = adminRbacMapper.insertRoleIfAbsent(role);
        if (newId == null) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "角色码已存在");
        }
        // 不加 @Transactional：单条 INSERT
        return newId;
    }

    /**
     * 编辑角色（name / description / status）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>先判「三个字段全 null」⇒ 400；</li>
     *   <li>★ <b>护栏①</b>（不许停用 SUPER_ADMIN）：需要先读一次目标角色
     *       （{@code this.getById(id)}），null ⇒ 404；
     *       然后 {@code if (dto.getStatus() != null && dto.getStatus() == 0
     *       && SUPER_ADMIN_CODE.equals(role.getCode()))} ⇒ 400；
     *       ⚠️ 用 {@code SUPER_ADMIN_CODE.equals(role.getCode())} 而不是反过来
     *       （目标为空时 {@code role.getCode().equals(...)} 会 NPE —— 这里是
     *       「先判 null 再判归属」的同一条纪律，{@code requireOwn} 的教训）；</li>
     *   <li>条件更新：{@code LambdaUpdateWrapper<Role>().eq(Role::getId, id)
     *       .set(条件, …) × 3 + .set(Role::getUpdatedAt, LocalDateTime.now())}；
     *       ⚠️ 注意 {@code code} <b>不在</b>可更新字段里（{@code RoleUpdateDTO} 就没给）；</li>
     *   <li>影响行数 0 ⇒ 404（虽然第 2 步已经查过，但保留这条断言 = 形状上的正确）。</li>
     * </ol>
     * <p>★ 关于「先查后改」的免责：第 2 步确实是「先读」，但读的是 <b>code</b>
     * —— 它<b>不可修改</b>（DTO 没给它），所以读到的值不会因并发而失效。
     * 真正的写语句仍是条件更新，并发安全不受影响。这条区别要写清，
     * 免得下一个人以为是「违反了绝不先查后改的纪律」。
     */
    @Override
    public void update(Long id, RoleUpdateDTO dto) {
        if (dto.getName() == null && dto.getDescription() == null && dto.getStatus() == null) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "没有需要修改的字段");
        }
        // ★ 护栏①：不许停用 SUPER_ADMIN。
        //    这一步确实是「先读」，但读的是 code —— 它不可修改（RoleUpdateDTO 没给它），
        //    所以读到的值不会因并发而失效；真正的写语句仍是条件更新，并发安全不受影响。
        Role role = this.getById(id);
        if (role == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
        // ⚠️ 用 SUPER_ADMIN_CODE.equals(role.getCode()) 而不是反过来：目标 code 为 null 时
        //    反过来写会 NPE（「先判 null 再判归属」的同一条纪律）。
        if (dto.getStatus() != null && dto.getStatus() == 0 && SUPER_ADMIN_CODE.equals(role.getCode())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "不允许停用超级管理员角色");
        }
        // 条件更新：code 不在可更新字段里（DTO 就没给）；⚠️ 显式补 updated_at（不走填充器）
        int rows = this.baseMapper.update(null, new LambdaUpdateWrapper<Role>()
                .eq(Role::getId, id)
                .set(dto.getName() != null, Role::getName, dto.getName())
                .set(dto.getDescription() != null, Role::getDescription, dto.getDescription())
                .set(dto.getStatus() != null, Role::getStatus, dto.getStatus())
                .set(Role::getUpdatedAt, LocalDateTime.now()));

        // 影响行数 0 ⇒ 404（第 2 步已经查过，但保留这条 = 形状上的正确）
        if (rows == 0) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
    }

    /**
     * 删除角色（含先清两张关联表）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>★ <b>护栏①</b>：先 {@code getById(id)}，null ⇒ 404；
     *       {@code SUPER_ADMIN_CODE.equals(role.getCode())} ⇒ 400（不许删超管角色）。
     *       ⚠️ 这条必须在任何 delete <b>之前</b>；</li>
     *   <li>{@code deleteRolePermissionsByRoleId(id)}（它定义了哪些权限）；</li>
     *   <li>{@code deleteAdminRolesByRoleId(id)}（谁在用它）——
     *       ★★ 两张表都要清，少一张就是 23503 现场 500；</li>
     *   <li>{@code this.baseMapper.deleteById(id)}；影响行数 0 ⇒ 404；</li>
     *   <li>★ 必须 {@code @Transactional}（<b>三条语句</b>）。</li>
     * </ol>
     */
    @Override
    @Transactional
    public void delete(Long id) {
        Role role = this.getById(id);
        if (role == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
        // ★ 护栏①：不许删超管角色 —— 必须在任何 delete 之前
        if (SUPER_ADMIN_CODE.equals(role.getCode())) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "不允许删除超级管理员角色");
        }
        // ★★ 两张关联表都要清：少一张就是 23503 现场 500。
        //    role_permissions = 它定义了哪些权限；admin_roles = 谁在用它。
        adminRbacMapper.deleteRolePermissionsByRoleId(id);
        adminRbacMapper.deleteAdminRolesByRoleId(id);

        int rows = this.baseMapper.deleteById(id);
        if (rows == 0) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
    }

    /**
     * 给角色全量替换权限。
     *
     * <p>实现要点：
     * <ol>
     *   <li>先 {@code getById(id)}，null ⇒ 404；</li>
     *   <li>★ 预校验权限 id：{@code permissionIds} 非空时
     *       {@code countPermissionsByIds(permissionIds) != permissionIds.size()} ⇒ 400。
     *       <b>空集合跳过</b>（{@code IN ()} 语法错）；</li>
     *   <li>★★ <b>护栏②</b>（只许增不许减）—— 只在目标是 SUPER_ADMIN 时才判：
     *       <pre>
     *       if (SUPER_ADMIN_CODE.equals(role.getCode())) {
     *           List&lt;Long&gt; current = adminRbacMapper.selectPermissionIdsByRoleId(id);
     *           if (!permissionIds.containsAll(current)) {
     *               throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
     *                       "超级管理员的权限只允许增加，不允许移除");
     *           }
     *       }
     *       </pre>
     *       ⚠️ 方向别弄反：是「目标必须包含全部现有」= {@code permissionIds.containsAll(current)}，
     *       <b>不是</b> {@code current.containsAll(permissionIds)}（那是「不许增」），
     *       也不是「两个集合相等」（那也禁止了「增」，与 §五 的决策相反）；
     *       ⚠️ {@code containsAll} 判的是<b>集合包含</b>，与顺序、重复无关 ——
     *       正好是我们要的语义（前端多选框的顺序不该影响结果）；
     *       ⚠️ 这一步需要「现有集合」，所以在 DELETE <b>之前</b>读；</li>
     *   <li>{@code deleteRolePermissionsByRoleId(id)}；</li>
     *   <li>{@code permissionIds} 非空时才 {@code insertRolePermissions(id, permissionIds)}；</li>
     *   <li>★ 必须 {@code @Transactional}（第 4、5 步两条语句）。</li>
     * </ol>
     * <p>★ 幂等性注意：重复提交<b>同一份集合</b>两次，结果必须相同
     * （DELETE 全清 + INSERT 全建 ⇒ 天然幂等，因为结果只取决于最后一次的入参）。
     * 验收里 D 组会连打两次并断言两次的库内状态一致。
     */
    @Override
    @Transactional
    public void assignPermissions(Long id, List<Long> permissionIds) {
        // 去重（理由同 AdminAccountManageServiceImpl#assignRoles：count(*) 对重复 id 只算一次）
        List<Long> target = (permissionIds == null) ? new ArrayList<>()
                : permissionIds.stream().distinct().toList();

        Role role = this.getById(id);
        if (role == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
        // 预校验权限 id（空集合跳过 —— IN () 是语法错）
        if (!target.isEmpty() && adminRbacMapper.countPermissionsByIds(target) != target.size()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "含不存在的权限 id");
        }
        // ★★ 护栏②：超管的权限【只许增不许减】。必须在 DELETE 之前读「现有集合」。
        //    ⚠️ 方向别弄反：permissionIds.containsAll(current) = 「目标包含全部现有」= 只许增；
        //       current.containsAll(permissionIds) 是「不许增」，两个都相等则是「不许改」——都不是本意。
        //    ⚠️ containsAll 判集合包含，与顺序、重复无关 —— 正好是我们要的语义。
        if (SUPER_ADMIN_CODE.equals(role.getCode())) {
            List<Long> current = adminRbacMapper.selectPermissionIdsByRoleId(id);
            if (!target.containsAll(current)) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                        "超级管理员的权限只允许增加，不允许移除");
            }
        }

        // 全量替换：DELETE 全清 + INSERT 全建 ⇒ 天然幂等（结果只取决于最后一次入参）
        adminRbacMapper.deleteRolePermissionsByRoleId(id);
        if (!target.isEmpty()) {
            adminRbacMapper.insertRolePermissions(id, target);
        }
    }
}
