package com.mallx.admin.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.admin.entity.AdminAuditLog;
import com.mallx.admin.mapper.AdminAuditLogMapper;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 管理端操作审计查询（Day 106），仅管理员账号管理权限可见 */
@Tag(name = "管理端-操作审计")
@RestController
@RequestMapping("/api/admin/audit-logs")
public class AdminAuditLogController {

    private final AdminAuditLogMapper mapper;

    public AdminAuditLogController(AdminAuditLogMapper mapper) {
        this.mapper = mapper;
    }

    @Operation(summary = "操作审计分页（按动作/管理员筛选）")
    @GetMapping
    @PreAuthorize("hasAuthority('admin:list')")
    public Result<PageResult<AdminAuditLog>> page(
            @RequestParam(required = false) String action,
            @RequestParam(required = false) String adminName,
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long size) {
        long safePage = Math.max(page, 1);
        long safeSize = Math.min(Math.max(size, 1), 100);
        LambdaQueryWrapper<AdminAuditLog> w = new LambdaQueryWrapper<>();
        w.like(action != null && !action.isBlank(), AdminAuditLog::getAction, action)
                .like(adminName != null && !adminName.isBlank(), AdminAuditLog::getAdminName, adminName)
                .orderByDesc(AdminAuditLog::getId);
        return Result.ok(PageResult.of(mapper.selectPage(new Page<>(safePage, safeSize), w)));
    }
}
