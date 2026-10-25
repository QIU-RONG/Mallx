package com.mallx.server.controller;

import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Value;
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
 * C 端图片上传（Day 80）：评价晒图用。
 *
 * <p>★ 与 {@link UploadController}（管理端）共用同一个存储目录与校验规则，
 * 但入口不同：这里只要求「已登录」，不要求商品权限 —— 买家也要能传评价图。
 *
 * <p>⚠️ <b>不能</b>把管理端那个接口的 {@code @PreAuthorize} 摘掉让两端共用：
 * 那样任何登录用户都能传图到管理端入口，权限语义就糊了。
 * 两个入口、同一套校验，各自表达「谁能传」。
 */
@Tag(name = "上传-评价晒图")
@RestController
@RequestMapping("/api/upload")
public class UploadPublicController {

    private static final Map<String, String> EXT_BY_TYPE = Map.of(
            "image/jpeg", "jpg",
            "image/png", "png",
            "image/webp", "webp",
            "image/gif", "gif"
    );
    private static final long MAX_BYTES = 2L * 1024 * 1024;

    private final String uploadDir;

    public UploadPublicController(@Value("${mallx.upload.dir:./uploads}") String uploadDir) {
        this.uploadDir = uploadDir;
    }

    @Operation(summary = "上传评价图片（需登录，≤2MB）")
    @PostMapping("/image")
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
