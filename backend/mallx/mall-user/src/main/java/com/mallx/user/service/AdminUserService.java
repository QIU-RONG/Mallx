package com.mallx.user.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.user.vo.UserVO;
import jakarta.validation.constraints.NotNull;

/**
 * 管理端用户管理（Day 22）。
 *
 * <p>★ 与 C 端 {@link UserService} 的分工是<b>数据权限反转</b>（本项目第三次出现，前两次是
 * Day 17 订单/库存、Day 18 商品/分类）：
 * <pre>
 *   C 端 UserService    ：方法签名【带 userId】，归属过滤写在 SQL/条件里 —— 只看自己
 *   管理端 AdminUserService：方法签名【不带 userId】，不做任何归属过滤 —— 看全部
 * </pre>
 * ⚠️ 「管理端不过滤」的前提是<b>每个端点都挂了权限码</b>。少挂一个就是静默公开
 * （这正是本日实测出来的那个洞的成因：{@code /api/users} 既没有归属过滤、
 * 又没有 {@code @PreAuthorize}）。
 *
 * <p>★ 本接口<b>不提供</b>删除用户：{@code users} 是订单/评价/券/地址四张表的外键目标
 * （全 NO ACTION），物理删必然撞约束；软删又会让历史订单的买家消失。
 * 治理语义由「禁用」承担 —— 这就是 {@code users.status} 这一列的用途。
 */
public interface AdminUserService {

    /**
     * 用户分页（管理端：含已禁用）。
     *
     * @param current 页码，从 1 开始
     * @param size    每页条数（★ 必须夹紧到 1..100，见实现里的 MAX_PAGE_SIZE）
     * @param keyword 可选：username / nickname / phone 三列模糊匹配（任一命中）
     * @param status  可选：1=正常 0=已禁用；★ 不传 = 两者都要（用 Integer，不能用 int）
     */
    Page<UserVO> pageUsers(long current, long size, String keyword, Integer status);

    /**
     * 用户详情。
     *
     * @throws com.mallx.common.exception.BusinessException 用户不存在 → {@code 404}
     *         ★ 管理端这里用<b>真 404 语义</b>（code=404），不伪装 ——
     *         「伪装 404」是给 C 端私有资源用的（不泄露「存在但不是你的」），
     *         管理员本来就该知道 id 存不存在。
     */
    UserVO getDetail(Long id);

    /**
     * 改用户状态。
     *
     * @param status 1 = 启用，0 = 禁用（DTO 已挡 0/1 之外的值）
     * @throws com.mallx.common.exception.BusinessException 用户不存在 → {@code 404}
     */
    void updateStatus(@NotNull Long id, @NotNull Integer status);
}
