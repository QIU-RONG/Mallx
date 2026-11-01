package com.mallx.ai.controller;

import com.mallx.ai.service.AiServiceClient;
import com.mallx.common.api.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

/** 知识库管理（Day 120）：只做转发，索引仍在 Python 侧 */
@Tag(name = "管理端-AI 知识库")
@RestController
@RequestMapping("/api/admin/ai/kb")
public class AdminAiKbController {

    private final AiServiceClient client;

    public AdminAiKbController(AiServiceClient client) {
        this.client = client;
    }

    @Operation(summary = "知识库文档列表")
    @GetMapping("/docs")
    @PreAuthorize("hasAuthority('dashboard:overview')")
    public Result<Object> docs() throws Exception {
        return Result.ok(client.get("/kb/docs", null));
    }

    @Operation(summary = "某文档的切片")
    @GetMapping("/chunks")
    @PreAuthorize("hasAuthority('dashboard:overview')")
    public Result<Object> chunks(@RequestParam String source) throws Exception {
        String encoded = URLEncoder.encode(source, StandardCharsets.UTF_8);
        return Result.ok(client.get("/kb/chunks?source=" + encoded, null));
    }

    @Operation(summary = "重建索引（重新切分全部文档）")
    @PostMapping("/rebuild")
    @PreAuthorize("hasAuthority('dashboard:overview')")
    public Result<Object> rebuild() throws Exception {
        return Result.ok(client.post("/kb/rebuild", Map.of(), null));
    }

    @Operation(summary = "上传/覆盖知识文档并重建索引")
    @PostMapping("/upload")
    @PreAuthorize("hasAuthority('dashboard:overview')")
    public Result<Object> upload(@RequestBody Map<String, Object> body) throws Exception {
        Object name = body.get("name");
        Object content = body.get("content");
        if (name == null || content == null) {
            return Result.ok(Map.of("code", 400, "message", "name/content 不能为空"));
        }
        return Result.ok(client.post("/kb/upload", Map.of("name", name, "content", content), null));
    }
}
