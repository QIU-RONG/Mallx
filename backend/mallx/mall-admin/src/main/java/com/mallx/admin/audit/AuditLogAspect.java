package com.mallx.admin.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mallx.admin.entity.AdminAuditLog;
import com.mallx.common.audit.AuditLog;
import com.mallx.admin.mapper.AdminAuditLogMapper;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Arrays;

/**
 * 审计切面（Day 106）：只记录成功的写操作，日志失败不影响业务。
 */
@Aspect
@Component
public class AuditLogAspect {

    private static final ObjectMapper JSON = new ObjectMapper();
    private final AdminAuditLogMapper mapper;
    private final com.mallx.admin.mapper.AdminMapper adminMapper;

    public AuditLogAspect(AdminAuditLogMapper mapper, com.mallx.admin.mapper.AdminMapper adminMapper) {
        this.mapper = mapper;
        this.adminMapper = adminMapper;
    }

    @Around("@annotation(auditLog)")
    public Object around(ProceedingJoinPoint pjp, AuditLog auditLog) throws Throwable {
        Object result = pjp.proceed();
        try {
            AdminAuditLog log = new AdminAuditLog();
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            log.setAdminName(resolveName(auth));
            log.setAction(auditLog.action());
            log.setTargetType(auditLog.targetType());
            Object[] args = pjp.getArgs();
            if (args.length > 0) {
                log.setTargetId(String.valueOf(args[0]));
                if (args.length > 1) {
                    log.setDetail(truncate(JSON.writeValueAsString(args[1])));
                }
            }
            log.setCreatedAt(LocalDateTime.now());
            mapper.insert(log);
        } catch (Exception ignored) {
            // 审计失败不阻断业务
        }
        return result;
    }

    /** 管理端 principal 是管理员 id（getName() 得到 "1"），这里翻成用户名 */
    private String resolveName(Authentication auth) {
        if (auth == null) {
            return "system";
        }
        String raw = String.valueOf(auth.getName());
        try {
            long id = Long.parseLong(raw);
            com.mallx.admin.entity.Admin admin = adminMapper.selectById(id);
            if (admin != null && admin.getUsername() != null) {
                return admin.getUsername();
            }
        } catch (NumberFormatException ignored) {
            // 非数字 = 已经是用户名
        }
        return raw;
    }

    private String truncate(String s) {
        return s == null || s.length() <= 480 ? s : s.substring(0, 480);
    }
}
