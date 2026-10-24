package com.mallx.server.controller;

import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.UUID;

/**
 * 图片上传（Day 74）。
 *
 * <p>★ 存本地磁盘（{@code mallx.upload.dir}，默认 {@code ./uploads}），返回相对 URL
 * {@code /uploads/yyyy/MM/uuid.ext}，由 {@code UploadWebConfig} 映射成静态资源。
 * 没接 OSS：本项目的部署环境没有对象存储，先让「换掉占位图」这件事能跑通。
 *
 * <p>★★ 安全取舍：
 * <ul>
 *   <li>扩展名 <b>由 Content-Type 推导</b>，不用原始文件名 —— 防 {@code ../} 与可执行扩展名；</li>
 *   <li>目标路径 normalize 后必须仍在根目录内；</li>
 *   <li>只收 image/jpeg|png|webp|gif，单文件 ≤ 2MB；</li>
 *   <li>权限：需要商品新增或编辑权限（{@code product:create} / {@code product:update}），
 *       不是「登录了就能传」。</li>
 * </ul>
 */
@Tag(name = "管理端-上传")
@RestController
@RequestMapping("/api/admin/upload")
public class UploadController {

    private static final Map<String, String> EXT_BY_TYPE = Map.of(
            "image/jpeg", "jpg",
            "image/png", "png",
            "image/webp", "webp",
            "image/gif", "gif"
    );
    private static final long MAX_BYTES = 2L * 1024 * 1024;

    private final String uploadDir;

    public UploadController(@Value("${mallx.upload.dir:./uploads}") String uploadDir) {
        this.uploadDir = uploadDir;
    }

    @Operation(summary = "上传商品图片（需 product:create 或 product:update）")
    @PostMapping("/image")
    @PreAuthorize("hasAnyAuthority('product:create','product:update')")
    public Result<String> image(@RequestParam("file") MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "请选择图片");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "图片不能超过 2MB");
        }
        String ext = EXT_BY_TYPE.get(file.getContentType());
        if (ext == null) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "只支持 jpg / png / webp / gif");
        }

        String sub = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy/MM"));
        Path root = Paths.get(uploadDir).toAbsolutePath().normalize();
        Path target = root.resolve(sub).resolve(UUID.randomUUID() + "." + ext).normalize();
        if (!target.startsWith(root)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "非法路径");
        }
        Files.createDirectories(target.getParent());
        file.transferTo(target.toFile());

        return Result.ok("/uploads/" + sub + "/" + target.getFileName());
    }
}
