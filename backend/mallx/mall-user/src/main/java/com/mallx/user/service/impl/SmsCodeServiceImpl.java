package com.mallx.user.service.impl;

import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.user.service.SmsCodeService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * 短信验证码实现（Day 52）。
 *
 * <p>★★★ <b>关于「发送」这一步 —— 本实现不真的发短信，必须知道为什么</b>
 *
 * <p>真实短信要接服务商（阿里云 / 腾讯云短信），需要账号、签名报备与费用。
 * 本项目（本机 + CI）没有这个账号，所以这里的做法是：
 * <ol>
 *   <li>正常生成码并写进 Redis（存储/限流/校验逻辑与线上<b>完全一致</b>）；</li>
 *   <li>打一条 <b>WARN</b> 日志（方便在后端日志里直接看到）；</li>
 *   <li><b>仅非 prod profile</b> 把明文码返回给调用方，由 Controller 放进响应体，
 *       前端弹出提示 —— 这样演示与自动化验收都能闭环。</li>
 * </ol>
 *
 * <p>⚠️⚠️ <b>上线的唯一改动点就在这里</b>：把第 2 步换成「调用短信 SDK 把 code 发出去」，
 * 并且 prod 下绝不返回明文（下面 {@code isProd()} 的判断已经保证了这一点）。
 * 一个把验证码写在响应里的登录接口，等于没有验证码。
 */
@Slf4j
@Service
public class SmsCodeServiceImpl implements SmsCodeService {

    /** 验证码本身：value 是 6 位数字 */
    private static final String CODE_KEY = "mallx:sms:code:";
    /** 发送限流：存在即代表「刚发过」 */
    private static final String LIMIT_KEY = "mallx:sms:limit:";

    /** ★ 用 SecureRandom 而不是 Random：Random 是可预测的（种子可推），
     *  而验证码的全部安全性就建立在「猜不到」上面。 */
    private static final SecureRandom RANDOM = new SecureRandom();

    private final StringRedisTemplate redis;
    private final Environment environment;

    public SmsCodeServiceImpl(StringRedisTemplate redis, Environment environment) {
        this.redis = redis;
        this.environment = environment;
    }

    @Override
    public String send(String phone) {
        String limitKey = LIMIT_KEY + phone;
        // ★ setIfAbsent = 「不存在才写入」，天然是原子的 ——
        //   不能用「先 get 判断、再 set」，那在并发下会漏（两个请求同时通过 get）。
        //   与库存扣减的 CAS 是同一条思路：让数据库/Redis 的原子操作做判定，别自己先查后改。
        Boolean first = redis.opsForValue().setIfAbsent(limitKey, "1", SEND_INTERVAL);
        if (Boolean.FALSE.equals(first)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "验证码发送过于频繁，请 " + SEND_INTERVAL.getSeconds() + " 秒后再试");
        }

        String code = String.format("%06d", RANDOM.nextInt(1_000_000));
        redis.opsForValue().set(CODE_KEY + phone, code, CODE_TTL);

        // ① 发短信的「替身」：写日志（真实项目这里改成短信 SDK 调用）
        log.warn("【开发模式·未接短信服务商】手机号 {} 的验证码 = {}（{} 分钟内有效）",
                maskPhone(phone), code, CODE_TTL.toMinutes());

        // ② 只有非 prod 才把明文交给调用方
        return isProd() ? null : code;
    }

    @Override
    public void verify(String phone, String code) {
        String saved = redis.opsForValue().get(CODE_KEY + phone);

        if (saved == null) {
            // 「已过期」与「从没发过」在用户眼里是同一件事，不分开报 —— 分开只会让人猜
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(),
                    "验证码已过期，请重新获取");
        }
        if (!constantTimeEquals(saved, code)) {
            // ⚠️ 这里【不删码】：删了的话用户打错一位就得重新获取，体验很刺眼
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "验证码不正确");
        }
    }

    @Override
    public void consume(String phone) {
        // ★ 一次性：换到结果后立刻作废，防止同一个码被重放（例如注册完再拿去登录）
        redis.delete(CODE_KEY + phone);
        log.info("【短信验证码】手机号 {} 的验证码已作废", maskPhone(phone));
    }

    private boolean isProd() {
        return environment.acceptsProfiles(Profiles.of("prod"));
    }

    /**
     * 常量时间比较，避免「逐字符比较 + 提前返回」把正确前缀的长度泄露出去。
     * <p>6 位数字码的时序攻击在实际网络里很难利用，但这一行的成本是零，
     * 没有理由不写。
     */
    private static boolean constantTimeEquals(String a, String b) {
        return MessageDigest.isEqual(
                a.getBytes(StandardCharsets.UTF_8),
                b.getBytes(StandardCharsets.UTF_8));
    }

    /**
     * 日志里只打掩码手机号。
     * <p>★ 日志是最容易被忽略的数据泄露面 —— 它会被采集、长期留存、
     * 给一堆没有业务权限的人看。手机号属于个人信息，不该以明文躺在日志里。
     */
    private static String maskPhone(String phone) {
        if (phone == null || phone.length() < 11) {
            return "***";
        }
        return phone.substring(0, 3) + "****" + phone.substring(7);
    }
}
