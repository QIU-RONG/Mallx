package com.mallx.admin.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 管理员可公开字段（管理端列表 / 详情共用，Day 23）。
 *
 * <p>★★ <b>本类存在的唯一理由是把 {@code password} 挡在出口之外。</b>
 * <p>实体 {@code Admin} 带 {@code password} 字段且<b>没有</b> {@code @JsonIgnore}，
 * 而 {@code AdminLoginUser} 还把密码原文一直带到 Controller（登录要 {@code matches}）。
 * 只要有一个端点直接返回 {@code Result<Admin>} 或 {@code Result<AdminLoginUser>}，
 * 管理端口令哈希（甚至凭 {@code {noop}} 前缀推回明文）就外泄了 ——
 * 这与 Day 22 实测出的 C 端全站口令哈希外泄（{@code day22-sec-probe.py} 16/16）
 * 是<b>同一个形状</b>，区别只在「这次还没发生」。
 *
 * <p>★ 于是本日的验收里有一条<b>结构性断言</b>：
 * 详情响应 JSON 的键集合里<b>不存在</b> {@code password}（而不是 {@code "password": null}）。
 * 这正是 Day 22 给 {@code UserVO} 定的同一条纪律 ——
 * 「把字段从 VO 里摘掉」比「加注解忽略」更难被后人改坏。
 *
 * <p>⚠️ 以后往这里加字段前先自问：<b>这个字段给任何持有 {@code admin:list} 的人看，有没有问题？</b>
 * <p>⚠️ {@code admins} 表没有 {@code is_deleted} 列（物理删）⇒ 本 VO 也没有该字段。
 */
@Data
public class AdminVO {

    private Long id;

    private String username;

    /** 显示名，可为 null（创建时未填） */
    private String nickname;

    /** 1 = 启用，0 = 已禁用 */
    private Integer status;

    private LocalDateTime createdAt;
}
