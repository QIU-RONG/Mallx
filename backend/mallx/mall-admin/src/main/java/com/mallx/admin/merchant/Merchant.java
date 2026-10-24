package com.mallx.admin.merchant;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 商户账号（Day 75）：一个店铺一个账号，登录后只能管自己店铺的商品 */
@Data
@TableName("merchants")
public class Merchant {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long shopId;

    private String username;

    private String password;

    private String name;

    /** 1 = 启用，0 = 停用 */
    private Integer status;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
