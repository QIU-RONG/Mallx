package com.mallx.admin.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.admin.dto.AdminCreateDTO;
import com.mallx.admin.dto.AdminUpdateDTO;
import com.mallx.admin.vo.AdminDetailVO;
import com.mallx.admin.vo.AdminVO;

import java.util.List;

/**
 * 管理员的建档与治理（Day 23，§5.6 RBAC）。
 *
 * <p>★ <b>与 {@code security.AdminAccountService} 的分工</b>（名字像，职责不同）：
 * <table border="1">
 *   <tr><th>类</th><th>职责</th><th>被谁调用</th></tr>
 *   <tr><td>{@code security.AdminAccountService}</td>
 *       <td><b>登录</b>：按 username 查人 + 拼权限集合</td>
 *       <td>{@code AdminAuthController#adminLogin}</td></tr>
 *   <tr><td>{@code AdminAccountManageService}（本类）</td>
 *       <td><b>管理</b>：管理员的增删改查 + 分配角色</td>
 *       <td>{@code AdminAccountController}</td></tr>
 * </table>
 * ⚠️ 实现侧要复用 {@code AdminMapper}（同一个 Mapper 两个 Service 用是正常的），
 * 但<b>不要</b>把「拼权限」的逻辑从登录侧搬过来 —— 那是登录的职责。
 *
 * <p>★ <b>本类所有方法都不做归属过滤</b>：与 Day 17–22 的管理端同一条纪律
 * （「管理端不归属过滤，防线是权限码」）。所以这里<b>不该</b>出现任何
 * {@code WHERE admin_id = ?} 式的过滤。
 * <p>⚠️ 唯一与「当前操作人」有关的是<b>护栏③</b>：那传的是 {@code currentAdminId}，
 * 用途是「拒绝操作自己」，与归属过滤是两件事（后者是「只能看自己的」，
 * 前者是「不许对自己动手」）。
 *
 * <p>★ 三个写方法带 {@code currentAdminId} 的，都是因为要落护栏③：
 * {@link #update}（不许停用自己）/ {@link #delete}（不许删自己）/
 * {@link #assignRoles}（不许清空自己的角色）。
 * <p>★ <b>为什么护栏③ 落在 Service 而不是 Controller</b>：
 * Controller 拿 {@code Authentication} 取 id 是它的活，但「目标是不是自己」
 * 是<b>业务规则</b>；写在 Service 里才能被单测直接调用、也才在「有人新增第二个调用方」
 * 时不失效。
 */
public interface AdminAccountManageService {

    /**
     * 管理员分页（含已禁用）。
     *
     * @param keyword 可选；匹配 {@code username} 或 {@code nickname}
     *                ★ 实现要点同 Day 22 的 {@code AdminUserServiceImpl#pageUsers}：
     *                多列 keyword 必须用 {@code .and(w -> …)} <b>包一层括号</b>，
     *                否则拼成 {@code status=? AND a OR b} —— SQL 的 AND 优先级高于 OR，
     *                「已禁用但命中关键字」的行会漏进来；
     *                ★ 夹紧（{@code size} 上限 100、下限 1）必须写在 {@code new Page<>()} <b>之前</b>。
     */
    Page<AdminVO> pageAdmins(long current, long size, String keyword, Integer status);

    /**
     * 管理员详情（含其角色 id 与角色码）。
     *
     * @throws com.mallx.common.exception.BusinessException 不存在 ⇒ 404
     *         ★ 这里是真的 404（不是 C 端那种「伪装 404」）——管理员本该知道 id 存不存在。
     */
    AdminDetailVO getDetail(Long id);

    /**
     * 新建管理员。
     *
     * @return 新管理员的 id
     * @throws com.mallx.common.exception.BusinessException username 撞 UNIQUE ⇒ <b>400</b>
     *         ★ 实现要点两条，都别省：
     *         <ol>
     *           <li>密码必须 {@code passwordEncoder.encode(dto.getPassword())} 后再落库
     *               —— 照抄种子里的 {@code {noop}admin123} 等于明文入库；</li>
     *           <li>撞 UNIQUE 靠 {@code AdminRbacMapper#insertAdminIfAbsent} 返回的
     *               <b>NULL</b> 判定（{@code ON CONFLICT DO NOTHING RETURNING id}），
     *               <b>不要</b>先 {@code selectOne} 查有没有同名再插（TOCTOU），
     *               也<b>不要</b> catch {@code DuplicateKeyException}（会被兜成 500）。</li>
     *         </ol>
     */
    Long create(AdminCreateDTO dto);

    /**
     * 编辑管理员（昵称 / 状态）。
     *
     * @param currentAdminId 当前操作人（从 token principal 取）
     * @throws com.mallx.common.exception.BusinessException
     *         <ul>
     *           <li>{@code nickname} 与 {@code status} 都为 null ⇒ 400（没有语义的请求）；</li>
     *           <li>{@code status = 0} 且 {@code id == currentAdminId} ⇒ 400（<b>护栏③</b>，不许停用自己）；</li>
     *           <li>目标不存在 ⇒ 404。</li>
     *         </ul>
     *         ★ 形状用<b>条件更新</b>（{@code UPDATE admins SET … WHERE id = ?}），
     *         影响行数 0 = 不存在 ⇒ 404。<b>不要</b>先 {@code getById} 再 {@code updateById}。
     *         ⚠️ 昵称与状态要能<b>各自单独</b>更新 ⇒ 用 {@code LambdaUpdateWrapper} 的
     *         {@code .set(条件, ...)}，而不是先读出来改字段再整体 update。
     */
    void update(Long id, AdminUpdateDTO dto, Long currentAdminId);

    /**
     * 物理删除管理员（含先清 {@code admin_roles}）。
     *
     * @param currentAdminId 当前操作人
     * @throws com.mallx.common.exception.BusinessException
     *         {@code id == currentAdminId} ⇒ 400（<b>护栏③</b>，不许删自己）；
     *         不存在 ⇒ 404
     *         ★★ 两条容易漏的：
     *         <ol>
     *           <li>{@code admins} <b>没有</b> {@code is_deleted} 列 ⇒ 是<b>物理删</b>。
     *               而 {@code admin_roles} 的 FK 是 {@code NO ACTION} ⇒
     *               必须先删关联行，否则 {@code DELETE FROM admins} 抛 <b>23503</b>
     *               （现场 500）。「谁引用我，决定我能否物理删」——同 L5 品牌的教训；</li>
     *           <li>「先删关联行」与「再删主行」是<b>两条语句</b> ⇒ 必须
     *               {@code @Transactional}（判据同 {@code InventoryService:119}）。</li>
     *         </ol>
     *         ★ 顺序上有个细节：护栏③ 的检查该放在删关联行<b>之前</b> ——
     *         否则「拒绝了自己」但关联行已经删了（虽然同事务会回滚，但逻辑上别留这种顺序）。
     */
    void delete(Long id, Long currentAdminId);

    /**
     * 给管理员<b>全量替换</b>角色。
     *
     * @param roleIds 空数组 = 清空该管理员的全部角色（显式意图）
     * @param currentAdminId 当前操作人
     * @throws com.mallx.common.exception.BusinessException
     *         <ul>
     *           <li>{@code id == currentAdminId} 且 {@code roleIds} 为空 ⇒ 400
     *               （<b>护栏③</b>，不许清空自己的角色）；</li>
     *           <li>管理员不存在 ⇒ 404；</li>
     *           <li>{@code roleIds} 含不存在的 id ⇒ <b>400</b>
     *               （用 {@code countRolesByIds} 预校验，别让 FK 的 23503 变 500）。</li>
     *         </ul>
     *         ★ 形状：{@code @Transactional} + {@code deleteAdminRolesByAdminId}
     *         + {@code insertAdminRoles}（两条语句 ⇒ 必须加事务）。
     *         ⚠️ {@code roleIds} 为空时<b>不要调用</b> {@code insertAdminRoles}
     *         （{@code <foreach>} 会拼出空 VALUES ⇒ 语法错误）。
     *         ⚠️ 空集合的「跳过校验」也要写对：{@code countRolesByIds} 同样会在空集合上
     *         拼出 {@code IN ()} ⇒ 空集合时两者都跳过。
     */
    void assignRoles(Long id, List<Long> roleIds, Long currentAdminId);
}
