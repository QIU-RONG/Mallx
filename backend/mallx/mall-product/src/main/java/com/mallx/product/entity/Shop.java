package com.mallx.product.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 店铺（Day 64，展示层）。
 *
 * <p>★ 这一版只解决「商品属于哪家店」的展示：
 * {@code products.shop_id} 可空（历史商品允许未归属），没有商户登录、没有数据隔离。
 * 真正的多商户（商户后台 / 拆单 / 分账）是另一个量级的工程，见 20-shops.sql 文件头。
 */
@Data
@TableName("shops")
public class Shop {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 店铺名，UNIQUE —— 重名会让「按店名找店」失效 */
    private String name;

    private String logo;

    private String description;

    /** 1 = 启用，0 = 停用（停用只影响 C 端展示，不删数据） */
    private Integer status;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
