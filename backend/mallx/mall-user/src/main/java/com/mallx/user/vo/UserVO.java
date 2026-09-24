package com.mallx.user.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 用户可公开字段（C 端「我的资料」与管理端用户列表/详情【共用】）。
 *
 * <p>★★ 本类存在的唯一理由是<b>把 password 挡在出口之外</b>。
 * 从前 C 端 {@code UserController} 的三个方法直接返回 {@code Result<User>}，
 * 而 {@code User} 实体带 {@code password} 字段且<b>没有</b> {@code @JsonIgnore}：
 * <pre>
 *   实测（day22-sec-probe.py，2026-09-24）：
 *   demo token GET /api/users        -> HTTP 200，返回全站 2 个用户，每条都带 password
 *   demo token GET /api/users/2      -> HTTP 200，password 与 DB 里的哈希【逐字节相同】
 *   demo token PUT /api/users/2/nickname -> HTTP 200（能改别人的行）
 * </pre>
 * ⇒ 任何登录用户（含只有 order:* 四个权限的 op_order）都能拉走全站口令哈希。
 *
 * <p>★ <b>为什么 C 端与管理端共用一份，而不是拆成 UserVO / AdminUserVO</b>：
 * 两者的字段集<b>完全相同</b> —— 「用户的可公开字段」这个定义不因访问者而变。
 * 对比 Day 20 的 L2（{@code getDetail} / {@code getAdminDetail} 必须拆方法）：
 * 那两个拆的是<b>判据</b>（C 端判 status、管理端不判），判据不同才需要两个方法；
 * 这里没有判据差异，共用一份反而少一份漂移风险。
 *
 * <p>⚠️ 以后往这里加字段前先自问：<b>这个字段给【任何】已登录用户看，有没有问题？</b>
 * <p>⚠️ 表里有 {@code avatar} 列，但 {@code User} 实体未映射它（Day 22 未动）——
 * 本 VO 与实体保持一致，不加「有字段但无来源」的列。
 */
@Data
public class UserVO {

    private Long id;

    private String username;

    private String nickname;

    private String phone;

    private String email;

    /** 1 = 正常，0 = 已禁用。管理端可改（{@code PUT /api/admin/users/{id}/status}），C 端只读 */
    private Integer status;

    private LocalDateTime createdAt;
}
