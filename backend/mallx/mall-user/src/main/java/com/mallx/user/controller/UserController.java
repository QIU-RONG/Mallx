package com.mallx.user.controller;

import com.mallx.common.api.Result;
import com.mallx.user.dto.NicknameUpdateDTO;
import com.mallx.user.service.UserService;
import com.mallx.user.vo.UserVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * C 端「我的资料」（Day 22 收口重写）。
 *
 * <p>★★ <b>本类为什么被重写</b>（实测证据见 {@code backend/loadtest/day22-sec-probe.py}，
 * 16/16 全绿）—— 重写前的三个端点是 Day 06 的练手产物：
 * <pre>
 *   GET    /api/users            -> Result&lt;PageResult&lt;User&gt;&gt;   全站用户列表，每条带 password
 *   GET    /api/users/{id}       -> Result&lt;User&gt;               任意人详情，带 password
 *   PUT    /api/users/{id}/nickname -> Result&lt;User&gt;             改任意人的昵称
 * </pre>
 * 三者<b>都没有</b> {@code @PreAuthorize}（C 端 token 无 perms，挂了必 403 —— 所以
 * 「不挂」本身是对的），也<b>都没有</b>归属过滤，而出口是带 password 的实体本身。
 * 合起来就是一个洞：<b>任何登录用户都能拉走全站口令哈希并改任何人的资料</b>
 * （连只有 {@code order:*} 四个权限的 {@code op_order} 都可以）。
 *
 * <p>★★ <b>收口手法：把 id 从入参里【移除】，而不是给它加校验</b>
 * <pre>
 *   改造前：GET /api/users/{id}          id 是【用户输入】⇒ 必须做 requireOwn（伪装 404）
 *   改造后：GET /api/users/me            id 来自 token 的 principal ⇒ 结构上不可能越权
 * </pre>
 * 这两条路的安全性差异不是程度问题而是<b>性质问题</b>：前者靠「校验写对了」，
 * 后者靠「伪造入口不存在」。同族做法见项目里那几条铁律
 * （{@code requireOwn} 先判 null、{@code releaseByOrder} 必须在 CAS 之后）——
 * <b>位置/结构本身就是语义</b>，而可省掉的校验是最安全的校验。
 *
 * <p>★ 权限：C 端接口<b>不能</b>挂 {@code @PreAuthorize}（C 端 token 不带 perms，
 * 一挂必 403）。本类的防线是「必须登录」—— 由 {@code anyRequest().authenticated()}
 * 在白名单之外兜住，匿名访问得到<b>真 HTTP 401</b>（不是 200+code）。
 *
 * <p>★ 路径说明：{@code /me} 是字面量，优先于任何变量模式 —— 所以将来若有人补回
 * {@code /{id}}，{@code /me} 也不会被它吃掉（PathPattern 的「字面量优先」，
 * Day 19 的 {@code /api/products/search} 实测过同一条）。
 */
@Tag(name = "用户")
@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    /**
     * 我的资料。
     * <p>
     * ★ 要 {@code Authentication} 参数（同 {@code OrderController.confirm}），
     * 而发货那种管理端方法则<b>不要</b> —— 判据是「这个接口是否关心『谁在问』」。
     */
    @Operation(summary = "我的资料（只能看自己）")
    @GetMapping("/me")
    public Result<UserVO> me(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        return Result.ok(userService.getMyProfile(userId));
    }

    /**
     * 改我的昵称。
     * <p>
     * ★ 用 {@code @Valid} + DTO：裸 {@code @RequestBody String} 校验不了空串/超长。
     * ★ 校验跑在方法调用之前 ⇒ 非法载荷永远先撞 400，与登录与否无关。
     */
    @Operation(summary = "改我的昵称")
    @PutMapping("/me/nickname")
    public Result<Void> updateMyNickname(Authentication authentication,
                                        @RequestBody @Valid NicknameUpdateDTO dto) {
        Long userId = (Long) authentication.getPrincipal();
        userService.updateMyNickname(userId, dto.getNickname());
        return Result.ok();
    }
}
