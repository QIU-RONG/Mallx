package com.mallx.user.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 收货地址（user_addresses）
 *
 * ⚠️ 本表没有 is_deleted 列 —— 禁止加 @TableLogic（加了所有查询报「列不存在」）。
 * ⚠️ 本表没有任何 UNIQUE 约束，「每个用户最多一条默认地址」只能靠 Service 的事务保证。
 */
@Data
@TableName("user_addresses")
public class UserAddress {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String receiverName;
    private String receiverPhone;
    private String province;
    private String city;
    private String district;
    private String detailAddress;

    /** ★★ 必须是包装类型 Boolean！用 boolean 会让 MP 反推出列名 "default"（PG 保留字） */
    private Boolean isDefault;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
