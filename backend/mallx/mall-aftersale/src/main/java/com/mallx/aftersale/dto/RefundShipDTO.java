package com.mallx.aftersale.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 退货寄出（C 端）—— {@code POST /api/refunds/{id}/ship} 的请求体（Day 46）。
 *
 * <p>★ 只有一个字段：物流单号。
 * 「寄出」这个动作在系统里能记录的就只有它 ——
 * 真正「货到了没有」是外部世界的事，由管理端 {@code receive} 确认。
 *
 * <p>⚠️ 长度 50 与 {@code refunds.tracking_no VARCHAR(50)} 对齐：
 * 这里不校验长度的话，超长字符串会在 INSERT/UPDATE 时抛
 * {@code value too long for type character varying(50)} ——
 * 那是一个 500，而且看起来像数据库坏了。
 */
@Data
public class RefundShipDTO {

    /** 退货物流单号 */
    @NotBlank(message = "物流单号不能为空")
    @Size(max = 50, message = "物流单号不能超过 50 字")
    private String trackingNo;
}
