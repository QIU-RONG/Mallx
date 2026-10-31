package com.mallx.admin.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** 管理端操作审计（Day 106） */
@Data
@TableName("admin_audit_logs")
public class AdminAuditLog {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String adminName;

    private String action;

    private String targetType;

    private String targetId;

    private String detail;

    private LocalDateTime createdAt;
}
