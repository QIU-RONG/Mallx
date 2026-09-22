package com.mallx.product.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 新增分类（Day 18）。
 * <p>
 * 字段与 {@code categories} 表一一对应：
 * <pre>
 *   id          BIGSERIAL      -- 服务端生成，DTO 里没有
 *   parent_id   BIGINT         -- null = 顶级分类
 *   name        VARCHAR(100)   NOT NULL
 *   sort_order  INT            NOT NULL DEFAULT 0
 *   status      SMALLINT       NOT NULL DEFAULT 1
 * </pre>
 * ★ <b>为什么 DTO 里没有 {@code status}</b>：V1.0 没有任何消费方读分类的 status
 * （C 端 {@code tree()} 不做 status 过滤），传了也没人看。留空即走 DDL 默认值 1 ——
 * MyBatis-Plus 默认 NOT_NULL 更新策略会跳过 null 字段，DB 的 DEFAULT 自然生效。
 * ★ <b>为什么不校验 parentId 是否存在</b>：那要查库，属于 Service 的活。
 * DTO 上的注解只表达「形状对不对」，不表达「业务允许不允许」——
 * 这也是 {@code @NotBlank} 只挂在 name 上的原因。
 */
@Data
public class CategoryCreateDTO {

    /** 父分类 id；null = 新建顶级分类 */
    private Long parentId;

    @NotBlank(message = "分类名称不能为空")
    @Size(max = 100, message = "分类名称不能超过 100 字")
    private String name;

    /** 排序值，越小越靠前；不传 = 0（数据库默认值） */
    private Integer sortOrder;
}
