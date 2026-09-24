package com.mallx.admin.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 管理员详情（{@code GET /api/admin/admins/{id}}，Day 23）—— 多带该管理员的角色。
 *
 * <p>★ <b>为什么是「平铺」而不是 {@code extends AdminVO}</b>：
 * <ol>
 *   <li>Lombok {@code @Data} 在继承下会生成 {@code equals/hashCode} 而不校验父类字段
 *       （会打 warning），项目里既有 VO 全是平的（{@link AdminVO} / {@code UserVO}）；</li>
 *   <li>更重要的是：两个 VO 的<b>演化节奏不同</b> —— 列表字段要克制（列表一次返 N 行），
 *       详情字段可以丰富。平铺能让「详情多了两个集合」在 diff 里一眼看见；
 *       继承会让父类加字段时详情被动跟上，反而难审。</li>
 * </ol>
 *
 * <p>★ 角色同时给 {@code roleIds}（勾选用）与 {@code roleCodes}（显示 / 断言用）：
 * 前者是前端多选框的回显值，后者是可读的语义（{@code ORDER_ADMIN}）。
 * 两者都从库现查，<b>不</b>从 token 里取 —— token 里是签发时的快照（路线①），
 * 详情页要的是「此刻」。
 *
 * <p>⚠️ 本类<b>同样不含 password</b>（见 {@link AdminVO} 的注释）。
 */
@Data
public class AdminDetailVO {

    private Long id;

    private String username;

    private String nickname;

    private Integer status;

    private LocalDateTime createdAt;

    /** 该管理员当前绑定的角色 id（前端多选框回显用） */
    private List<Long> roleIds;

    /** 该管理员当前绑定的角色码，例 [SUPER_ADMIN]；显示 / 验收断言用 */
    private List<String> roleCodes;
}
