package com.mallx.user.controller;


import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import com.mallx.common.dto.LoginDTO;
import com.mallx.common.exception.BusinessException;
import com.mallx.common.security.JwtProperties;
import com.mallx.common.security.JwtUtil;
import com.mallx.common.vo.LoginVO;
import com.mallx.user.dto.SmsLoginDTO;
import com.mallx.user.dto.SmsRegisterDTO;
import com.mallx.user.dto.SmsSendDTO;
import com.mallx.user.entity.User;
import com.mallx.user.security.LoginUser;
import com.mallx.user.service.SmsCodeService;
import com.mallx.user.service.UserService;
import com.mallx.user.vo.SmsSendVO;
import jakarta.validation.Valid;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthenticationManager authenticationManager;
    private final JwtUtil jwtUtil;
    private final JwtProperties jwtProperties;
    private final UserService userService;
    private final SmsCodeService smsCodeService;

    public AuthController(AuthenticationConfiguration configuration, JwtUtil jwtUtil,
                          JwtProperties jwtProperties, UserService userService,
                          SmsCodeService smsCodeService) {
        this.authenticationManager = configuration.getAuthenticationManager();
        this.jwtUtil = jwtUtil;
        this.jwtProperties = jwtProperties;
        this.userService = userService;
        this.smsCodeService = smsCodeService;
    }

    @PostMapping("/login")
    public Result<LoginVO> login(@RequestBody @Valid LoginDTO loginDTO) {

        // ① 认证：查库 + 比密码 + 判 status 都在 authenticate() 内部完成
        Authentication authentication = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(loginDTO.getUsername(), loginDTO.getPassword()));

        // ② 从认证结果里取出 LoginUser（框架声明是 Object，所以要强转回自己的类型）
        LoginUser loginUser = (LoginUser) authentication.getPrincipal();

        // ③ 签发 token
        String token = jwtUtil.generate(loginUser.getUserId(), loginUser.getUsername());

        // ④ 补查昵称：LoginUser 里没有 nickname 字段
        User user = userService.getById(loginUser.getUserId());

        // ⑤ 组装返回（expireMinutes 是分钟，VO 里的 expiresIn 要的是秒）
        return Result.ok(new LoginVO(
                token,
                "Bearer",
                jwtProperties.getExpireMinutes() * 60,
                loginUser.getUserId(),
                loginUser.getUsername(),
                user != null ? user.getNickname() : null));
    }

    // ==================== Day 52：手机号验证码登录 / 注册 ====================
    // 三条路径都已进 SecurityConfig 白名单（精确路径）。它们都是「还没有身份」时用的，
    // 因此不可能挂 @PreAuthorize —— C 端 token 也没有 perms。

    /**
     * 发送验证码。
     *
     * <p>⚠️ 这里<b>不返回「该手机号是否已注册」</b>，是有意的：若在发码阶段就回答这个问题，
     * 任何人拿一份手机号名单刷一遍就能枚举出平台的全部用户。
     * 「是否注册」这个判断放到验证码校验<b>之后</b>（见 {@link #smsLogin}）。
     */
    @PostMapping("/sms/send")
    public Result<SmsSendVO> smsSend(@RequestBody @Valid SmsSendDTO dto) {
        // devCode 仅开发模式有值，prod 恒为 null（见 SmsSendVO 的注释）
        return Result.ok(new SmsSendVO(smsCodeService.send(dto.getPhone())));
    }

    /**
     * 手机号 + 验证码登录；未注册则要求先注册。
     */
    @PostMapping("/sms/login")
    public Result<LoginVO> smsLogin(@RequestBody @Valid SmsLoginDTO dto) {
        // ① 校验验证码 —— ★ 是 verify 而不是 verifyAndConsume：
        //    下面「未注册」的分支要把用户送去注册页，而注册**还要用同一个码**。
        //    在这里就把码消费掉，用户到注册页会发现码已作废、又得等 60 秒重发。
        smsCodeService.verify(dto.getPhone(), dto.getCode());

        // ② 查手机号是否已注册
        User user = userService.findByPhone(dto.getPhone());
        if (user == null) {
            // ★★ 未注册 ⇒ 抛【专属业务码 4041】，前端据此带上手机号跳注册页。
            //    ⚠️ 这一句必须在「验证码校验通过」之后：让「你得先证明你持有这个号」
            //    成为用户枚举的门槛（与上面 smsSend 不返回注册状态是同一条防线）。
            throw new BusinessException(ResultCode.PHONE_NOT_REGISTERED.getCode(),
                    ResultCode.PHONE_NOT_REGISTERED.getMessage());
        }

        // ③ 被禁用的账号不许登录（种子数据 status=1 为正常）
        if (user.getStatus() != null && user.getStatus() != 1) {
            throw new BusinessException(ResultCode.FORBIDDEN.getCode(), "账号已被禁用");
        }

        // ④ 到这里才作废验证码（理由见 SmsCodeService 接口注释）
        smsCodeService.consume(dto.getPhone());

        return issue(user);
    }

    /**
     * 手机号注册；成功后<b>直接登录</b>。
     *
     * <p>★ 为什么要直接登录：刚填完资料的用户的耐心是用完的。
     * 让他回到登录页重新输手机号、再等一条新验证码，是纯粹的浪费。
     * 反正他刚刚已经证明了自己持有这个号。
     */
    @PostMapping("/sms/register")
    public Result<LoginVO> smsRegister(@RequestBody @Valid SmsRegisterDTO dto) {
        // ★ 注册是「校验 + 作废」一步到位：这次校验确实要换出一个新账号
        smsCodeService.verifyAndConsume(dto.getPhone(), dto.getCode());

        User user = userService.registerByPhone(dto.getPhone(), dto.getNickname());

        return issue(user);
    }

    /**
     * 签发令牌并组装登录响应 —— 短信登录与注册共用这一段。
     *
     * <p>★ 抽出来是为了让「令牌怎么签发」只有<b>一个来源</b>：
     * 两处各写一遍，迟早出现一处改了过期时间、另一处没改。
     */
    private Result<LoginVO> issue(User user) {
        String token = jwtUtil.generate(user.getId(), user.getUsername());
        return Result.ok(new LoginVO(
                token,
                "Bearer",
                jwtProperties.getExpireMinutes() * 60,
                user.getId(),
                user.getUsername(),
                user.getNickname()));
    }
}
