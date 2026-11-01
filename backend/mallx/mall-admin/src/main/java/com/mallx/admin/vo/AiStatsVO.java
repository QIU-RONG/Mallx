package com.mallx.admin.vo;

import lombok.Data;

import java.math.BigDecimal;

/** AI 运营指标（Day 116） */
@Data
public class AiStatsVO {

    private Long calls;

    private Long todayCalls;

    private Long promptTokens;

    private Long completionTokens;

    private BigDecimal avgElapsedMs;

    private Long refusals;

    private BigDecimal refusalRate;
}
