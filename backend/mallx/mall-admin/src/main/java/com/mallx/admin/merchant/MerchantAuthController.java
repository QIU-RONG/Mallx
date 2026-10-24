package com.mallx.admin.merchant;

import com.mallx.admin.mapper.MerchantMapper;
import com.mallx.common.api.Result;
import com.mallx.common.dto.LoginDTO;
import com.mallx.common.security.JwtProperties;
import com.mallx.common.security.JwtUtil;
import com.mallx.common.security.ShopScope;
import com.mallx.common.vo.LoginVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

/**
 * 商户登录（Day 75）。
 *
 * <p>★ 与管理员登录同一套 token（type=ADMIN），差别只在 perms：
 * 商品域四个权限 + 分类/品牌字典读 + 一条 {@code SHOP_SCOPE_<shopId>}。
 * 过滤器不改，商户 token 直接能过 {@code @PreAuthorize}；
 * 数据范围由 {@link ShopScope#currentShopId()} 在商品服务里附加过滤。
 *
 * <p>★★ 商户【没有】product:delete —— 删商品会让历史订单失去关联，留给平台。
 */
@Tag(name = "商户认证")
@RestController
@RequestMapping("/api/auth/merchant")
public class MerchantAuthController {

    private final MerchantMapper merchantMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final JwtProperties jwtProperties;

    public MerchantAuthController(MerchantMapper merchantMapper,
                                  PasswordEncoder passwordEncoder,
                                  JwtUtil jwtUtil,
                                  JwtProperties jwtProperties) {
        this.merchantMapper = merchantMapper;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtil = jwtUtil;
        this.jwtProperties = jwtProperties;
    }

    @Operation(summary = "商户登录")
    @PostMapping("/login")
    public Result<LoginVO> login(@RequestBody @Valid LoginDTO dto) {
        Merchant m = merchantMapper.selectOne(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Merchant>()
                        .eq(Merchant::getUsername, dto.getUsername()).last("LIMIT 1"));
        // 查不到也统一提示，不泄露账号是否存在
        if (m == null || !passwordEncoder.matches(dto.getPassword(), m.getPassword())) {
            throw new BadCredentialsException("用户名或密码错误");
        }
        if (m.getStatus() == null || m.getStatus() != 1) {
            throw new BadCredentialsException("账号已被禁用");
        }

        List<String> perms = new ArrayList<>(List.of(
                "product:list",
                "product:detail",
                "product:create",
                "product:update",
                "category:list",
                "brand:list"
        ));
        perms.add(ShopScope.authority(m.getShopId()));

        String token = jwtUtil.generateForAdmin(m.getId(), m.getUsername(), perms);
        return Result.ok(new LoginVO(
                token,
                "Bearer",
                jwtProperties.getExpireMinutes() * 60,
                m.getId(),
                m.getUsername(),
                "商户"));
    }
}
