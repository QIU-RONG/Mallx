package com.mallx.common.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** 标记需要写审计日志的写操作（Day 106）；切面在 mall-admin。 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditLog {

    /** 动作名，如「商品编辑」 */
    String action();

    /** 目标类型，如 product / coupon / order */
    String targetType() default "";
}
