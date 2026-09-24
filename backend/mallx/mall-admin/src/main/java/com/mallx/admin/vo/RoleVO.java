package com.mallx.admin.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 角色可公开字段（管理端列表共用，Day 23）。
 *
 * <p>★ 含 {@code status}：与 L5 品牌的教训同源（{@code BrandService} 的
 * {@code listEnabled / listAll} 两个方法）—— 「停用的东西 C 端看不见、
 * 管理端必须看得见」，因为管理员要把它<b>重新启用</b>，看不见就无从操作。
 * 本端点是管理端，所以<b>返回全部</b>（含 {@code status = 0}）。
 *
 * <p>⚠️ {@code code} 一旦签发进 token 就成为存量 token 的一部分（路线①）——
 * 本 VO 只读地把它显示出来，编辑接口<b>不给改</b>（见 {@code RoleUpdateDTO}）。
 */
@Data
public class RoleVO {

    private Long id;

    private String name;

    /** 角色码，UNIQUE；例 SUPER_ADMIN */
    private String code;

    private String description;

    /** 1 = 启用，0 = 已停用 */
    private Integer status;

    private LocalDateTime createdAt;
}
