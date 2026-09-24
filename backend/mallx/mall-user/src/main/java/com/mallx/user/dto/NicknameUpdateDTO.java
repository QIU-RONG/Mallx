package com.mallx.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 改昵称请求体（{@code PUT /api/users/me/nickname}）。
 *
 * <p>★ 从「裸 {@code @RequestBody String nickname}」升级成 DTO 的三个理由：
 * <ol>
 *   <li>裸 String <b>没有办法加校验</b> —— 空串、纯空格、超长昵称都能直写进库；</li>
 *   <li>{@code @NotBlank} 才能把「只发一个空格」这种<b>看起来非空、实际为空</b>的入参挡住；</li>
 *   <li>练手期那种「body 直接就是字符串」的写法在前后端分离下会<b>依赖 Content-Type</b>：
 *       传 {@code {"nickname":"x"}} 会被当成整串存进去（连花括号一起进去）。</li>
 * </ol>
 *
 * <p>⚠️ 这里<b>不</b>做「昵称唯一性」校验：业务上昵称可以重复（唯一性只属于
 * {@code username} / {@code phone} / {@code email} 三列，DB 已各有唯一索引）。
 */
@Data
public class NicknameUpdateDTO {

    @NotBlank(message = "昵称不能为空")
    @Size(max = 50, message = "昵称最长 50 个字符")
    private String nickname;
}
