package com.mallx.admin.controller;

import com.mallx.admin.mapper.DashboardMapper;
import com.mallx.admin.vo.AiStatsVO;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** AI 运营看板（Day 116）：数据来自 ai_messages，与 Python 服务同一张表 */
@Tag(name = "管理端-AI 运营")
@RestController
@RequestMapping("/api/admin/ai")
public class AdminAiStatsController {

    private final DashboardMapper mapper;

    public AdminAiStatsController(DashboardMapper mapper) {
        this.mapper = mapper;
    }

    @Operation(summary = "AI 调用量 / token / 平均耗时 / 拒答率")
    @GetMapping("/stats")
    @PreAuthorize("hasAuthority('dashboard:overview')")
    public Result<AiStatsVO> stats() {
        AiStatsVO vo = new AiStatsVO();
        vo.setCalls(mapper.countAiCalls());
        vo.setTodayCalls(mapper.countAiTodayCalls());
        vo.setPromptTokens(mapper.sumAiPromptTokens());
        vo.setCompletionTokens(mapper.sumAiCompletionTokens());
        vo.setAvgElapsedMs(mapper.avgAiElapsedMs());
        vo.setRefusals(mapper.countAiRefusals());
        long calls = vo.getCalls() == null ? 0 : vo.getCalls();
        long refusals = vo.getRefusals() == null ? 0 : vo.getRefusals();
        vo.setRefusalRate(calls == 0 ? BigDecimal.ZERO
                : BigDecimal.valueOf(refusals).divide(BigDecimal.valueOf(calls), 3, RoundingMode.HALF_UP));
        return Result.ok(vo);
    }
}
