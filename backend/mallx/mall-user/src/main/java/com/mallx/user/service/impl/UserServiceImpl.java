package com.mallx.user.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.user.entity.User;
import com.mallx.user.mapper.UserMapper;
import com.mallx.user.service.UserService;
import com.mallx.user.vo.UserVO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * C 端用户服务实现。
 *
 * <p>★ 两个读/改方法的正确形状都很短（各 3-5 行），要点写在下面每个方法上。
 */
@Slf4j
@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {

    private final PasswordEncoder passwordEncoder;

    public UserServiceImpl(PasswordEncoder passwordEncoder) {
        this.passwordEncoder = passwordEncoder;
    }

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

    /**
     * 按手机号查用户（Day 52 · 手机号验证码登录/注册分流用）。
     *
     * <p>★ 返回 {@code null} 表示<b>没查到</b>，这是正常分支而不是异常 ——
     * 调用方正是要拿它来决定「登录」还是「引导去注册」。
     * 把「查不到」写成抛异常，会让这个分支比正常路径还难走。
     *
     * <p>⚠️ {@code getOne(wrapper, false)} 的第二个参数是 {@code throwEx=false}：
     * phone 上有 UNIQUE 约束，理论上最多一条；但把「多条」的兜底关掉，
     * 是为了避免将来有人把唯一约束去掉后，这里突然开始抛异常。
     */
    @Override
    public User findByPhone(String phone) {
        return this.getOne(new LambdaQueryWrapper<User>().eq(User::getPhone, phone), false);
    }

    /**
     * 手机号注册（Day 52）。
     *
     * <p>★★ <b>为什么「先查一次」和「唯一索引」两个都要</b>：
     * 先查是为了让「已注册」这个错误<b>说人话</b>（而不是把数据库的唯一约束异常抛给用户）；
     * 但先查<b>挡不住并发</b> —— 两个请求可以同时通过它（TOCTOU），
     * 这时真正拦住重复注册的是 {@code users.phone} 的 UNIQUE 约束。
     * <b>先查负责体验，唯一索引负责正确性。</b>
     * （与 Day 46 退款「重复申请」那条完全同构，那里也是 SELECT + 部分唯一索引双层。）
     */
    @Override
    @Transactional
    public User registerByPhone(String phone, String nickname) {
        if (findByPhone(phone) != null) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该手机号已注册，请直接登录");
        }

        User u = new User();
        // ★ username 直接用手机号：它 NOT NULL + UNIQUE，而手机号本身也唯一且已知，
        //   没必要再让用户想一个（也没必要自己拼接一个容易撞的）。
        u.setUsername(phone);
        u.setPhone(phone);
        // ★★ 随机密码占位：users.password 是 NOT NULL，但手机号登录根本不看它。
        //    写一个连我们自己都不知道的随机值（再哈希）=
        //    「从设计上关掉这个账号的密码登录」——
        //    比设个默认密码（如 123456）安全得多，默认密码是最经典的被撞库入口。
        u.setPassword(passwordEncoder.encode(UUID.randomUUID().toString()));
        u.setNickname(StringUtils.hasText(nickname) ? nickname : "用户" + phone.substring(7));
        u.setStatus(1);

        try {
            this.save(u);
        } catch (DuplicateKeyException e) {
            // ★★ 并发兜底：能走到这里说明 ① 的检查被并发绕过了。
            //    ⚠️ 不接住它 ⇒ 冒泡到全局 ExceptionHandler 的兜底 ⇒
            //    前端看到「系统异常」，而真相是「这个号已经注册过了」。
            //    （Day 46 的 DataIntegrityViolationException 是同一个坑。）
            log.warn("【注册】并发注册冲突已翻译为业务错误 phone={}", maskPhone(phone));
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "该手机号已注册，请直接登录");
        }

        log.info("【注册】成功 userId={} phone={}", u.getId(), maskPhone(phone));
        return u;
    }

    /**
     * 日志里只打掩码手机号。
     * <p>★ 日志是最容易被忽略的数据泄露面：它会被采集、长期留存、给一堆
     * 没有业务权限的人看。手机号属于个人信息，不该明文躺在日志里。
     */
    private static String maskPhone(String phone) {
        if (phone == null || phone.length() < 11) {
            return "***";
        }
        return phone.substring(0, 3) + "****" + phone.substring(7);
    }
}
