package com.mallx.user.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.user.entity.User;
import com.mallx.user.vo.UserVO;

/**
 * C 端用户服务接口：继承 IService&lt;User&gt; 获得常用业务方法。
 *
 * <p>★ Day 22 起本接口只服务<b>「我的」</b>语义 —— 方法签名一律<b>带 userId</b>，
 * 且 userId 由 Controller 从 token 的 principal 取，不由请求参数传。
 * 「看别人」这件事已经整体移到管理端 {@code AdminUserService}。
 */
public interface UserService extends IService<User> {

    /**
     * 我的资料（C 端）。
     *
     * <p>★ 入参名刻意叫 {@code userId} 而不是 {@code id}：<b>「谁在问」由 token 决定，
     * 不由请求参数决定</b>。这是本日收口的核心手法 —— 与其「校验入参是不是你自己」，
     * 不如<b>让入参根本不存在</b>。
     *
     * @throws com.mallx.common.exception.BusinessException 用户不存在 → 404
     *         （token 有效但用户已被物理删除的边界；管理员禁用≠删除，禁用照常能看）
     */
    UserVO getMyProfile(Long userId);

    /**
     * 改我的昵称（C 端）。
     *
     * @param nickname 已由 {@code NicknameUpdateDTO} 的 {@code @NotBlank/@Size} 校验过
     */
    void updateMyNickname(Long userId, String nickname);
}
