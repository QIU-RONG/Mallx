package com.mallx.admin.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.admin.dto.RoleCreateDTO;
import com.mallx.admin.dto.RoleUpdateDTO;
import com.mallx.admin.vo.RoleDetailVO;
import com.mallx.admin.vo.RoleVO;

import java.util.List;

/**
 * 角色的建档与治理（Day 23，§5.6 RBAC）。
 *
 * <p>★★ <b>本类承载护栏①②</b>（本项目 RBAC 里唯一的「不可逆事故」防线）：
 * <table border="1">
 *   <tr><th>护栏</th><th>落在哪个方法</th><th>判据</th></tr>
 *   <tr><td>① SUPER_ADMIN 不可删、不可停用</td><td>{@link #delete} / {@link #update}</td>
 *       <td>{@code role.code == "SUPER_ADMIN"} ⇒ 400</td></tr>
 *   <tr><td>② SUPER_ADMIN 的权限只许增、不许减</td><td>{@link #assignPermissions}</td>
 *       <td>目标集合必须 <b>⊇</b> 现有集合，否则 400</td></tr>
 * </table>
 * <p>为什么这两条是硬性的、而不是「靠文档约定」：
 * 自锁是 RBAC 唯一的<b>不可逆</b>事故 —— 代码全对、库没坏、日志干净，
 * 但<b>任何人也进不来了</b>（只剩改库一条路）。详见 Day-23 文档 §五。
 *
 * <p>★ <b>为什么护栏① 判的是 {@code code} 而不是 {@code id == 1}</b>：
 * {@code id} 是插入顺序的产物，而 {@code SUPER_ADMIN} 是<b>语义</b>。
 * 项目里已经出现过「用 id 当契约」的教训（Day 22：{@code user:list} 的 path 写着
 * C 端路径，因为当初是按 id 一对一对上的）。判 {@code code} 即使有人手工挪过 id 也依然正确。
 *
 * <p>★ 与 {@code AdminAccountManageService} 一样：本类<b>不做归属过滤</b>，
 * 也不带 {@code currentAdminId} —— 角色是全局资产，不存在「我的角色」这个概念。
 * 护栏①② 保护的是<b>角色本身</b>，与「谁在操作」无关。
 */
public interface RoleManageService {

    /**
     * 角色分页（含已停用 —— 管理端要能看见，才能重新启用；同 L5 品牌的教训）。
     *
     * @param keyword 可选；匹配 {@code name} 或 {@code code}
     *                ★ 括号问题同 {@code AdminAccountManageService#pageAdmins}
     *                （本方法只有一个 keyword 条件，但一旦将来加 status 过滤，
     *                漏括号就是同一个坑 ⇒ 实现时就按「包括号」的形状写）。
     */
    Page<RoleVO> pageRoles(long current, long size, String keyword);

    /**
     * 角色详情（含 {@code permissionIds} 与 {@code permissionCodes}）。
     *
     * @throws com.mallx.common.exception.BusinessException 不存在 ⇒ 404
     *         ⚠️ 这里查的是角色<b>定义</b>了哪些权限（{@code selectPermissionIdsByRoleId}），
     *         <b>不是</b>「谁通过它拿到了什么」—— 后者会被 {@code status} 过滤，
     *         混用会让「停用角色的详情」看起来权限为空（明明只是暂时不生效）。
     */
    RoleDetailVO getDetail(Long id);

    /**
     * 新建角色。
     *
     * @return 新角色的 id
     * @throws com.mallx.common.exception.BusinessException code 撞 UNIQUE ⇒ <b>400</b>
     *         ★ 靠 {@code AdminRbacMapper#insertRoleIfAbsent} 返回 NULL 判定，
     *         形状与理由同 {@code AdminAccountManageService#create}。
     */
    Long create(RoleCreateDTO dto);

    /**
     * 编辑角色（名称 / 说明 / 状态）。<b>不能改 code</b>（见 {@code RoleUpdateDTO}）。
     *
     * @throws com.mallx.common.exception.BusinessException
     *         <ul>
     *           <li>三个字段全为 null ⇒ 400；</li>
     *           <li>{@code status = 0} 且目标是 {@code SUPER_ADMIN} ⇒ 400（<b>护栏①</b>）；</li>
     *           <li>目标不存在 ⇒ 404。</li>
     *         </ul>
     *         ★ 判「目标是不是 SUPER_ADMIN」需要<b>先读一次</b>角色的 code ——
     *         这与项目「绝不先查后改」的纪律<b>不冲突</b>：那条纪律针对的是
     *         <b>并发正确性</b>（TOCTOU：读到的状态会被别人改掉）。
     *         这里是「读一个不变的身份属性（code 不可改）来决定要不要拒绝」，
     *         读到的值不会因并发而失效。⚠️ 但<b>更新语句本身</b>仍要写成条件更新
     *         （{@code WHERE id = ?} + 影响行数 0 ⇒ 404），两件事分开做。
     */
    void update(Long id, RoleUpdateDTO dto);

    /**
     * 删除角色（含先清 {@code role_permissions} 与 {@code admin_roles}）。
     *
     * @throws com.mallx.common.exception.BusinessException
     *         目标是 {@code SUPER_ADMIN} ⇒ 400（<b>护栏①</b>）；不存在 ⇒ 404
     *         ★★ 三条容易漏的：
     *         <ol>
     *           <li>删角色要清<b>两张</b>关联表：{@code role_permissions}（它定义了哪些权限）
     *               <b>和</b> {@code admin_roles}（谁在用它）。少清一张就是 23503 现场 500；</li>
     *           <li>三条语句（两个 delete + 一个 delete）⇒ 必须 {@code @Transactional}；</li>
     *           <li>★ 护栏① 的检查要在任何 delete <b>之前</b>。</li>
     *         </ol>
     *         ⚠️ 这与「删管理员」不同：删管理员只需清 {@code admin_roles}（它不拥有别的关联）。
     */
    void delete(Long id);

    /**
     * 给角色<b>全量替换</b>权限。
     *
     * @param permissionIds 空数组 = 清空该角色的全部权限
     * @throws com.mallx.common.exception.BusinessException
     *         <ul>
     *           <li>角色不存在 ⇒ 404；</li>
     *           <li>{@code permissionIds} 含不存在的 id ⇒ <b>400</b>（预校验 count）；</li>
     *           <li>★ 目标是 {@code SUPER_ADMIN} 且目标集合<b>不包含</b>现有集合 ⇒ 400（<b>护栏②</b>）。</li>
     *         </ul>
     *         ★★ 护栏② 的判法（实现时最容易写错的一处）：
     *         需要「现有集合 - 目标集合」必须为<b>空</b>，即
     *         {@code Set.copyOf(current).stream().allMatch(target::contains)}
     *         —— 注意是<b>只许增</b>：目标可以有现有之外的新权限（那是「增」，允许），
     *         但不能丢掉任何一个现有的（那是「减」，拒绝）。
     *         ⚠️ 别写成 {@code target.containsAll(current)} 之外的等价物时把方向弄反；
     *         也别写成「两个集合相等」（那会禁止「增」，与 §五 的决策相反）。
     *         ★ 形状：{@code @Transactional} + {@code deleteRolePermissionsByRoleId}
     *         + {@code insertRolePermissions}；空集合时跳过 insert（{@code <foreach>} 坑）。
     */
    void assignPermissions(Long id, List<Long> permissionIds);
}
