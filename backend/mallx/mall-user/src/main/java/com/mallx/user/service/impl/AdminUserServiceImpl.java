package com.mallx.user.service.impl;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.user.entity.User;
import com.mallx.user.mapper.UserMapper;
import com.mallx.user.service.AdminUserService;
import com.mallx.user.vo.UserVO;
import org.springframework.stereotype.Service;

/**
 * 管理端用户管理实现（Day 22）。
 *
 * <p>★ 本类是「管理端不归属过滤」的第三处落地（前两处：Day 17 订单/库存、Day 18 商品/分类）。
 * 防线不在这一层，而在 Controller 的 {@code @PreAuthorize} —— 所以本类里<b>不该</b>
 * 出现任何 {@code WHERE user_id = ?} 式的归属过滤。
 */
@Service
public class AdminUserServiceImpl extends ServiceImpl<UserMapper, User> implements AdminUserService {

    /**
     * 分页上限：单页最多 100 条 —— 与 {@code OrderServiceImpl} / {@code InventoryServiceImpl} /
     * {@code ReviewServiceImpl} / {@code ProductServiceImpl} 同一个值、同一套夹紧规则
     * （★★ 本处是第 <b>6</b> 份拷贝）。
     *
     * <p>★ {@code docs/backlog.md} 的 T1 写着「等出现第 6 份拷贝、或规则本身要变时再抽」——
     * <b>本处正好触发了那个条件</b>。仍维持不抽，理由不变：抽常量要动 5 个模块的 POM
     * 可见性与编译边界，收益是省 4 行，风险却是 5 条已验收链路同时受影响。
     * 这里把这个判断<b>写下来</b>，免得下次看到 T1 以为是漏了。
     *
     * <p>★ 夹紧必须写在 {@code new Page<>(...)} <b>之前</b> —— 写进构造参数里就晚了
     * （{@code size=-1} 会撞 MP 的「负数=不限量」语义，直接查全表）。
     */
    private static final long MAX_PAGE_SIZE = 100;

    /**
     * 用户分页（管理端）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>过滤口径与 C 端相反：<b>不写死 status</b>
     *       —— {@code .eq(status != null, User::getStatus, status)}，不传就两者都要；</li>
     *   <li>{@code keyword} 要<b>跨三列任一命中</b>（username / nickname / phone）
     *       ⇒ 用 {@code .and(w -> w.like(...).or().like(...).or().like(...))}
     *       ★ 必须用 {@code .and(...)} <b>包一层括号</b>：直接写成
     *       {@code .like(a).or().like(b)} 会与 status 条件形成
     *       {@code status=? AND a OR b} —— SQL 的 AND 优先级高于 OR，
     *       于是「已禁用但昵称命中」的行会漏进来（本项目的口径漂移又一处）；</li>
     *   <li>夹紧两行要在 {@code new Page<>()} 之前；</li>
     *   <li>出口换壳：{@code Page<User>} → {@code Page<UserVO>}，且
     *       <b>total/current/size 必须搬到新 Page</b>，否则前端看到 total=0
     *       （照 {@code ProductServiceImpl.pageProducts} 的写法）；</li>
     *   <li>★ 逐行 {@code User} → {@code UserVO}，<b>绝不能把 User 实体直接返回</b>
     *       —— 那正是本日实测出的口令哈希外泄。</li>
     * </ol>
     */
    @Override
    public Page<UserVO> pageUsers(long current, long size, String keyword, Integer status) {
        throw new UnsupportedOperationException("TODO: AdminUserServiceImpl.pageUsers");
    }

    /**
     * 用户详情（管理端：已禁用的也能看）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>{@code this.getById(id)}，null → {@code throw new BusinessException(
     *       ResultCode.NOT_FOUND.getCode(), "用户不存在")}；</li>
     *   <li>★ 这里是<b>真 404 语义</b>，不做「伪装」—— 伪装 404 是给 C 端私有资源用的
     *       （见 {@code AddressServiceImpl#requireOwn}），管理员本该知道 id 存不存在；</li>
     *   <li>返回 {@code UserVO}（不是 User）。</li>
     * </ol>
     */
    @Override
    public UserVO getDetail(Long id) {
        throw new UnsupportedOperationException("TODO: AdminUserServiceImpl.getDetail");
    }

    /**
     * 改用户状态（1=启用 0=禁用）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>★ 这是<b>定点写</b>，正确形状是<b>条件更新</b>：
     *       {@code UPDATE users SET status=? WHERE id=?} 一句到底，
     *       用 {@code updateById} 要先查后改（多一次往返，且是 TOCTOU 的形状）；</li>
     *   <li>★ <b>影响行数即答案</b>：0 行 = 用户不存在 ⇒ 抛 404。
     *       <b>不要</b>先 {@code getById} 判存在再改 —— 那是「先查后改」；</li>
     *   <li>★ 幂等：把 1 改成 1 也是 1 行（MP 的 {@code update} 不带乐观锁时不看旧值），
     *       所以「已禁用再禁用」返回 200 —— 这是 REST 语义正确的，<b>要有断言盯着</b>；</li>
     *   <li>不加 {@code @Transactional}：单条 UPDATE 自身即原子
     *       （项目成文判据见 {@code InventoryService.java:119}「它是两条语句」才加）。</li>
     * </ol>
     */
    @Override
    public void updateStatus(Long id, Integer status) {
        throw new UnsupportedOperationException("TODO: AdminUserServiceImpl.updateStatus");
    }
}
