package com.mallx.admin.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 新建管理员（{@code POST /api/admin/admins}，Day 23）。
 *
 * <p>★ <b>password 的落库形状是本类最要紧的一件事</b>：
 * 表里种子行写的是 {@code {noop}admin123}（{@code 03-data.sql:149}），
 * 那是 {@code DelegatingPasswordEncoder} 的「明文前缀」—— 照抄它 = 明文入库。
 * 实现侧必须 {@code passwordEncoder.encode(dto.getPassword())}，
 * 落库结果是 {@code $2a$…}（BCrypt）。
 * ⇒ 验收里唯一的真证明不是「看库里是不是 $2a$ 开头」，
 * 而是 <b>拿新密码去 {@code /api/auth/admin/login} 能登进来</b>
 * （后者顺带证明 encoder 的 encode/matches 是同一套算法）。
 *
 * <p>★ {@code username} 有 UNIQUE 约束（{@code 01-schema.sql:318}）——
 * 撞车必须转 <b>400</b> 而不是 500。做法<b>不是</b> try/catch
 * {@code DuplicateKeyException}：本项目的成文判据（{@code ReviewMapper.java:59-62}）
 * 写着「{@code GlobalExceptionHandler} 里没有它的专用出口 → 会被兜成 500；
 * 走 {@code ON CONFLICT} 就不用动公共层一个字节」⇒ 见
 * {@code AdminRbacMapper#insertAdminIfAbsent}。
 *
 * <p>⚠️ <b>校验在前、授权在后</b>（{@code @Valid} 跑在 {@code @PreAuthorize} 之前，
 * Day 07 定型）⇒ 断 403 时必须给<b>合法载荷</b>，否则永远先撞 400。
 */
@Data
public class AdminCreateDTO {

    /** 登录名，UNIQUE */
    @NotBlank(message = "username 不能为空")
    @Size(min = 3, max = 32, message = "username 长度需在 3..32 之间")
    private String username;

    /**
     * 原始密码（明文，只在此刻存在于内存）。
     * <p>★ 长度下限 6 是<b>刻意的弱约束</b>：V1.0 不做密码策略，
     * 但「1 位密码」这种明显失手要在入口挡住。
     */
    @NotBlank(message = "password 不能为空")
    @Size(min = 6, max = 64, message = "password 长度需在 6..64 之间")
    private String password;

    /** 显示名，可选（不传则实现侧留 null，管理端列表显示为空） */
    @Size(max = 32, message = "昵称最长 32 字符")
    private String nickname;
}
