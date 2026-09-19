package com.mallx.user.controller;

import com.mallx.common.api.Result;
import com.mallx.user.dto.AddressSaveDTO;
import com.mallx.user.service.AddressService;
import com.mallx.user.vo.AddressVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 收货地址接口（全部需登录）
 *
 * ★ 取当前用户：principal 是 Long userId，不是 LoginUser
 * ★ 不挂 @PreAuthorize：C 端 token 权限集为空，挂了必 403
 */
@Tag(name = "收货地址")
@RestController
@RequestMapping("/api/addresses")
public class AddressController {

    private final AddressService addressService;

    public AddressController(AddressService addressService) {
        this.addressService = addressService;
    }

    @Operation(summary = "我的地址列表（默认地址排最前）")
    @GetMapping
    public Result<List<AddressVO>> list(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(addressService.list(userId));
    }

    @Operation(summary = "地址详情（非本人返 404）")
    @GetMapping("/{id}")
    public Result<AddressVO> detail(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(addressService.detail(userId, id));
    }

    @Operation(summary = "新增地址（第一条自动成为默认）")
    @PostMapping
    public Result<Long> create(Authentication authentication, @RequestBody @Valid AddressSaveDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(addressService.create(userId, dto));
    }

    @Operation(summary = "修改地址（业务字段全量覆盖；isDefault=true 表示设为默认）")
    @PutMapping("/{id}")
    public Result<Void> update(Authentication authentication,
                              @PathVariable Long id,
                              @RequestBody @Valid AddressSaveDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        addressService.update(userId, id, dto);
        return Result.ok();
    }

    @Operation(summary = "删除地址（删掉默认地址会自动补位；非本人返 404）")
    @DeleteMapping("/{id}")
    public Result<Void> remove(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        addressService.remove(userId, id);
        return Result.ok();
    }

    /** 无 body：要设哪一条全在 URL 里，所以刻意不挂 @RequestBody（挂了反而要求发空体） */
    @Operation(summary = "设为默认地址（无 body；非本人返 404）")
    @PutMapping("/{id}/default")
    public Result<Void> setDefault(Authentication authentication, @PathVariable Long id) {
        Long userId = (Long) authentication.getPrincipal();
        addressService.setDefault(userId, id);
        return Result.ok();
    }
}
