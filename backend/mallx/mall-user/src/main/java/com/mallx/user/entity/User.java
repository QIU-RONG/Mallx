package com.mallx.user.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("users")
public class User {
    @TableId(type = IdType.AUTO) // id设置为自增
    private Long id;

    private String username;

    private String password;

    private String nickname;

    private String phone;

    private String email;

    private Integer status;

    @TableField(fill = FieldFill.INSERT)          // 插入时自动填 created_at
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)   // 插入和更新时都自动填 updated_at
    private LocalDateTime updatedAt;

}
