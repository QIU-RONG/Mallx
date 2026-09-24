package com.mallx.user.service.impl;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.user.entity.User;
import com.mallx.user.mapper.UserMapper;
import com.mallx.user.service.UserService;
import com.mallx.user.vo.UserVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

/**
 * C 端用户服务实现。
 *
 * <p>★ 两个方法的正确形状都很短（各 3-5 行），要点写在下面每个方法上。
 */
@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {

    /**
     * 我的资料。
     *
     * <p>实现要点：
     * <ol>
     *   <li>{@code this.getById(userId)}，null → {@code throw new BusinessException(
     *       ResultCode.NOT_FOUND.getCode(), "用户不存在")}；</li>
     *   <li>★ 出口是 {@code UserVO} 而<b>不是</b> {@code User}：
     *       这是本日那个漏洞的<b>正解</b>。「给实体加 {@code @JsonIgnore}」也能挡住
     *       password，但那会连<b>反序列化</b>一起挡掉（{@code POST} 建用户时 password 收不到），
     *       得改用 {@code @JsonProperty(access = WRITE_ONLY)} 才行 —— 而且
     *       <b>实体不出门</b>本来就是全项目的既定口径（每个出口都有 VO）。</li>
     *   <li>用 {@code BeanUtils.copyProperties(user, vo)} 拷（同
     *       {@code ProductServiceImpl.pageProducts} 的做法），别手写 7 行 setter；</li>
     *   <li>不加 {@code @Transactional}：纯读。</li>
     * </ol>
     */
    @Override
    public UserVO getMyProfile(Long userId) {
        User user = this.getById(userId);
        if (user == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "用户不存在");
        }
        // ★ 出口是 UserVO 而不是 User —— 这是本日那个漏洞的正解。
        //   实体出门 = 带 password 出门；VO 里根本没有这个字段。
        UserVO vo = new UserVO();
        BeanUtils.copyProperties(user, vo);
        return vo;
    }

    /**
     * 改我的昵称。
     *
     * <p>实现要点：
     * <ol>
     *   <li>正确形状是<b>条件更新一句到底</b>：
     *       {@code UPDATE users SET nickname=? WHERE id=?} —— 用
     *       {@code LambdaUpdateWrapper} 的 {@code .eq(User::getId, userId).set(...)}
     *       配合 {@code this.update(null, wrapper)}；
     *       ⚠️ <b>不要</b>走 {@code getById → setNickname → updateById}：
     *       那是先查后改，多一次往返（本方法的语义下不算 TOCTOU，但形状是错的）；</li>
     *   <li>★ <b>影响行数即答案</b>：0 行 = 用户不存在 ⇒ 抛 404；</li>
     *   <li>⚠️ {@code updateById} 与自动填充的坑（本项目已踩过）：手写
     *       {@code UpdateWrapper} 的 UPDATE <b>不走</b>自动填充器 ⇒ {@code updated_at}
     *       不会刷新。若希望它刷新，要么显式 {@code .set("updated_at", ...)}，
     *       要么改回 {@code updateById} 并把实体里其余字段留 null（MP 默认只更新非 null 字段）；</li>
     *   <li>不加 {@code @Transactional}：单条 UPDATE。</li>
     * </ol>
     */
    @Override
    public void updateMyNickname(Long userId, String nickname) {
        // ★ 条件更新一句到底：WHERE id = <token 里的 userId>，不做「先查后改」。
        // ★ 影响行数即答案：0 行 = 用户不存在 ⇒ 404。
        // ⚠️ 手写 UpdateWrapper 不走自动填充器 ⇒ 显式补 updated_at（同 AdminUserServiceImpl）。
        int rows = this.baseMapper.update(null, new LambdaUpdateWrapper<User>()
                .eq(User::getId, userId)
                .set(User::getNickname, nickname)
                .set(User::getUpdatedAt, LocalDateTime.now()));

        if (rows == 0) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "用户不存在");
        }
    }
}
