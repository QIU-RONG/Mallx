package com.mallx.product.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 新增品牌（Day 24 · L5②）。
 * <p>
 * 字段与 {@code brands} 表一一对应（01-schema.sql:68-76）：
 * <pre>
 *   id          BIGSERIAL      -- 服务端生成，DTO 里没有
 *   name        VARCHAR(100)   NOT NULL UNIQUE   ← ★ 有唯一约束，见下
 *   logo        VARCHAR(500)
 *   description TEXT
 *   status      SMALLINT       NOT NULL DEFAULT 1
 * </pre>
 * <p>
 * ★★ <b>为什么这里【有】{@code status}，而 {@code CategoryCreateDTO} 里【没有】</b>
 * （两次的取舍不同，必须写下来，否则后来者会以为其中一个漏了）：
 * <table border="1">
 *   <tr><th>表</th><th>status 的消费方</th><th>DTO 给不给</th></tr>
 *   <tr><td>categories</td><td><b>没有</b>（C 端 tree() 不过滤 status；上下架由商品自己管）</td><td>不给</td></tr>
 *   <tr><td>brands</td><td><b>有</b>：C 端 {@code listEnabled()} 过滤 status=1、 管理端 {@code listAll()} 含停用</td><td><b>给</b></td></tr>
 * </table>
 * 判据是「<b>有没有真实消费方读这个字段</b>」，不是「表里有没有这一列」。
 * 品牌这一列是有用的（管理员要能新建一个「暂时停用」的品牌、要能把品牌停用而不删），
 * 所以必须能在创建时就指定；否则只能「先建启用的、再调一次 update 停用」，白白多一次写入。
 * <p>
 * ⚠️ <b>不传 status</b>（null）= 走 DDL 默认值 1（MyBatis-Plus 的 NOT_NULL 更新策略会跳过
 * null 字段，DB 的 DEFAULT 自然生效）—— 与 {@code CategoryCreateDTO} 同一条机制。
 * <p>
 * ⚠️ <b>不校验 name 是否重名</b>：那要查库，属于 Service 的活（同
 * {@code CategoryCreateDTO} 对 parentId 的分工）。DTO 只表达「形状对不对」，
 * 不表达「业务允许不允许」。
 */
@Data
public class BrandCreateDTO {

    @NotBlank(message = "品牌名称不能为空")
    @Size(max = 100, message = "品牌名称不能超过 100 字")
    private String name;

    @Size(max = 500, message = "品牌 logo 地址不能超过 500 字")
    private String logo;

    /** 品牌简介（TEXT，无长度上限） */
    private String description;

    /** 1 = 启用，0 = 停用；不传 = 1（数据库默认值） */
    @Min(value = 0, message = "status 只能是 0 或 1")
    @Max(value = 1, message = "status 只能是 0 或 1")
    private Integer status;
}
