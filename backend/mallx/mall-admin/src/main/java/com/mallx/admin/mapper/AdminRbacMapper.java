package com.mallx.admin.mapper;

import com.mallx.admin.entity.Admin;
import com.mallx.admin.entity.Role;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * RBAC 关联表与建档写入（Day 23）—— 本日<b>全部手写 SQL 的集中地</b>。
 *
 * <p>★★ <b>为什么 {@code admin_roles} / {@code role_permissions} 不建实体</b>：
 * 两张表都是<b>复合主键</b>的纯关联表（{@code PRIMARY KEY (admin_id, role_id)} /
 * {@code (role_id, permission_id)}，{@code 01-schema.sql:352-368}）。
 * MyBatis-Plus 的 {@code BaseMapper} 假定「一行有一个主键」，对复合主键支持别扭
 * （要硬指定一个 {@code @TableId}，还有一个字段就得 {@code @TableField(value=..., exist=false)}）——
 * 硬凑出来的实体在 {@code updateById} / {@code deleteById} 上语义都是错的。
 * ⇒ 照项目惯例手写 XML。
 *
 * <p>★ <b>为什么 {@code insertAdminIfAbsent} / {@code insertRoleIfAbsent} 也在这里</b>
 * （它们写的是主表 {@code admins} / {@code roles}）：
 * ① 这两个插入服务的是 RBAC 建档（管理员 / 角色），与关联表的替换同属一个事务边界；
 * ② 它们是「带 {@code ON CONFLICT} 的 INSERT」，{@code BaseMapper.insert} 给不了；
 * ③ 集中放本文件，可以让 {@code AdminMapper.xml} 本日<b>只承担那一条缺陷修复</b>，
 * 改动面最小、最好审（见 {@code AdminMapper.xml} 的注释）。
 *
 * <p>★★ <b>「UNIQUE 撞车要转 400」的正确姿势（项目成文判据）</b>：
 * 不 catch {@code DuplicateKeyException}，而是 {@code INSERT … ON CONFLICT DO NOTHING}
 * —— 见 {@code ReviewMapper.java:59-62} 的原文推理：
 * 「{@code DuplicateKeyException} 是 RuntimeException 的子类、
 * {@code GlobalExceptionHandler} 里没有它的专用出口 → 会被兜成 500。
 * 走 {@code ON CONFLICT} 就<b>不用动 GlobalExceptionHandler 一个字节</b>。」
 * <p>配合 {@code RETURNING id}，返回值天然区分两种结果：
 * 插进去了 ⇒ 拿到新 id；撞车 ⇒ <b>NULL</b> ⇒ 实现侧抛 400。
 * 这是「<b>影响行数即答案</b>」在 INSERT 上的同构写法（同 {@code INSERT … ON CONFLICT DO NOTHING}、
 * 同条件 UPDATE 的 0 行）。
 *
 * <p>★★ <b>所有 {@code deleteXxx} + {@code insertXxx} 的「全量替换」必须包在同一个
 * {@code @Transactional} 里</b>：DELETE 与批量 INSERT 之间有一瞬「关联为空」的窗口，
 * 事务把它吃掉。这是本项目<b>少数几处「两条语句」必须加事务</b>的地方
 * （判据同 {@code InventoryService:119}）。
 *
 * <p>⚠️ 所有 {@code IN (…)} 与 {@code VALUES (…)} 的 {@code <foreach>} 在<b>空集合</b>下
 * 会拼出 {@code IN ()} / {@code VALUES} 空体 ⇒ SQL 语法错误。
 * ⇒ 实现侧对空集合<b>必须先判、直接跳过该语句</b>（空数组的语义是「清空」，
 * 此时只要 DELETE 生效就够了）。
 */
@Mapper
public interface AdminRbacMapper {

    /** 某管理员当前的角色 id 集合（详情页回显 / 护栏③ 判「是否清空自己的角色」）。 */
    List<Long> selectRoleIdsByAdminId(@Param("adminId") Long adminId);

    /**
     * 某角色<b>定义</b>的权限 id 集合。
     * <p>⚠️ 与 {@code AdminMapper.selectPermissionCodesByAdminId} 不是一回事：
     * 那条是「按管理员查、穿两层关联、并按 status 过滤」的<b>生效</b>集合；
     * 本条是「这个角色定义了哪些权限」的<b>定义</b>集合。别混用（L2 的教训）。
     */
    List<Long> selectPermissionIdsByRoleId(@Param("roleId") Long roleId);

    /** 清空某管理员的全部角色（分配角色时「替换」的前半步）。 */
    int deleteAdminRolesByAdminId(@Param("adminId") Long adminId);

    /**
     * 清空某角色在 {@code admin_roles} 里的全部引用。
     * <p>★ 存在的理由：删除角色时，FK 是 {@code NO ACTION} ⇒ 不先清这行，
     * {@code DELETE FROM roles} 会抛 <b>23503</b>（现场 500）。
     * 「谁引用我，决定我能否物理删」—— 同 L5 品牌那条教训。
     */
    int deleteAdminRolesByRoleId(@Param("roleId") Long roleId);

    /** 清空某角色的全部权限（分配权限时「替换」的前半步；删角色时也要先清）。 */
    int deleteRolePermissionsByRoleId(@Param("roleId") Long roleId);

    /**
     * 批量插入管理员-角色关联（<b>全量替换</b>的后半步）。
     * <p>⚠️ {@code roleIds} 为空 ⇒ 实现侧<b>不要调用本方法</b>（会拼出空 VALUES）。
     * <p>⚠️ {@code roleIds} 含不存在的 id ⇒ FK 抛 23503。实现侧必须先
     * {@link #countRolesByIds} 预校验并抛 400，别让 FK 兜底。
     */
    int insertAdminRoles(@Param("adminId") Long adminId,
                         @Param("roleIds") List<Long> roleIds);

    /** 批量插入角色-权限关联。<p>⚠️ 空集合、含不存在 id 的注意事项同 {@link #insertAdminRoles}。 */
    int insertRolePermissions(@Param("roleId") Long roleId,
                              @Param("permissionIds") List<Long> permissionIds);

    /**
     * 这些角色 id 里有几个是真实存在的。
     * <p>★ 用途：预校验「传了不存在的 id」⇒ 与传入长度比较 ⇒ 不等就抛 400。
     * 这是「<b>不靠异常做控制流</b>」的落地（对比：硬插 + catch 23503）。
     * <p>⚠️ 空集合 ⇒ 实现侧跳过校验（空 = 清空，无需校验）。
     * <p>⚠️ 刻意<b>不</b>过滤 {@code status}：允许把角色分配给一个已停用的角色
     * （它只是<b>暂时不生效</b>，负责人有权先配好再启用）；这与
     * {@code selectPermissionCodesByAdminId} 按 {@code r.status} 过滤
     * 是两个不同层面的决定，别把它们对齐。
     */
    long countRolesByIds(@Param("roleIds") List<Long> roleIds);

    /** 这些权限 id 里有几个真实存在。<p>注意事项同上（空集合跳过、不过滤 status）。 */
    long countPermissionsByIds(@Param("permissionIds") List<Long> permissionIds);

    /**
     * 插入管理员，用户名已被占用则<b>不插</b>。
     *
     * <pre>
     *   INSERT INTO admins (username, password, nickname, status, created_at, updated_at)
     *   VALUES (#{username}, #{password}, #{nickname}, 1, now(), now())
     *   ON CONFLICT (username) DO NOTHING
     *   RETURNING id
     * </pre>
     *
     * @return 新 id；<b>NULL 表示 username 撞了 UNIQUE</b>（⇒ 实现侧抛 400）
     *         <p>★ 为什么返回 {@code Long} 而不是 {@code int}：{@code RETURNING} 让
     *         「成功 / 撞车」这件事变成<b>一个可空的值</b>，实现侧不用再查一次。
     *         ⚠️ 用 {@code <select>} 包 {@code INSERT … RETURNING} 时必须写
     *         {@code flushCache="true"}：MyBatis 一级缓存会让同事务内的第二次调用
     *         <b>根本不发 SQL</b>（本项目已踩过）。
     *         <p>⚠️ {@code ON CONFLICT (username)} 硬依赖该列上有唯一约束 ——
     *         {@code 01-schema.sql:318} 确认存在。
     */
    Long insertAdminIfAbsent(Admin admin);

    /**
     * 插入角色，角色码已被占用则不插。
     * <p>形状与 {@link #insertAdminIfAbsent} 同构（{@code ON CONFLICT (code) DO NOTHING
     * RETURNING id}），{@code roles.code} 的唯一约束见 {@code 01-schema.sql:330}。
     *
     * @return 新 id；{@code NULL} = code 撞了 UNIQUE ⇒ 实现侧抛 400
     */
    Long insertRoleIfAbsent(Role role);
}
