package com.mallx.order.task;

import com.mallx.order.service.OrderService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 超时关单定时任务（Day 14 第 3 步）。
 *
 * <p>状态机的第三条边：{@code PENDING_PAYMENT} 超时后<b>自己</b>走向 {@code CANCELLED}
 * （前两条是用户点的「支付」和「取消」）。
 *
 * <p>★★ 本类只做三件事：定时触发、传阈值、兜异常。
 * 真正的逻辑全在 {@link OrderService#cancelTimeoutOrders(int)} 里 ——
 * <b>因为定时任务没有 SecurityContext</b>，它不能走用户视角的
 * {@code cancel(userId, orderId)}（那里要从认证信息里取 userId，取不到会 NPE），
 * 必须走一个「系统视角」的独立入口。这不是省代码，是<b>权限模型的分层</b>。
 *
 * <p>⚠️ 本类能被扫描到，前提是启动类上有 {@code @EnableScheduling}
 * （Day 14 第 3 步已加）。少了它，本类会被正常实例化但<b>永远不会被调用</b> ——
 * 不报错、不告警，只是静静地什么都不做。
 *
 * <p>⚠️ 与用户支付的竞态<b>不需要额外处理</b>：定时任务只是「多了一个竞争者」，
 * 谁赢仍由 {@code WHERE status = 'PENDING_PAYMENT'} 那条 CAS 决定。
 */
@Slf4j
@Component
public class OrderTimeoutTask {

    /**
     * 超时阈值（分钟）。
     *
     * <p>★ 取 2 分钟是为了实验能在合理时间内观察到自动关单；
     * 正式环境这个值应当放进 {@code application.yml}（如
     * {@code mallx.order.timeout-minutes}）而不是硬编码。
     */
    private static final int TIMEOUT_MINUTES = 2;

    /** 轮询间隔（毫秒）：60 秒扫一次。 */
    private static final long POLL_INTERVAL_MS = 60_000L;

    private final OrderService orderService;

    public OrderTimeoutTask(OrderService orderService) {
        this.orderService = orderService;
    }

    /**
     * 每 60 秒扫一次「超时未支付」的订单并逐单取消。
     *
     * <p>★ 用 {@code fixedDelay}（上一轮<b>结束后</b>再等 60 秒）而不是 {@code fixedRate}
     * （按固定频率发起）：取消一批订单可能耗时，{@code fixedRate} 会在上一轮还没跑完时
     * 又发起一轮，白白制造「同一批单被两个线程同时处理」的竞争
     * （虽然 CAS 能兜住，但那属于自己给自己制造麻烦）。
     *
     * <p>★ 本方法<b>不写成功日志</b>：明细日志由
     * {@link OrderService#cancelTimeoutOrders(int)} 在「真的扫到超时单」时打。
     * 没有超时单时保持安静，否则就是每分钟一条噪音。
     */
    @Scheduled(fixedDelay = POLL_INTERVAL_MS)
    public void cancelTimeoutOrders() {
        try {
            orderService.cancelTimeoutOrders(TIMEOUT_MINUTES);
        } catch (Exception e) {
            // ★ 定时任务里必须兜住所有异常：抛出去没有人接，
            //   只会让调度线程的日志变噪音（fixedDelay 仍会继续下一轮）。
            //   注意这里 catch 的是 Exception 而不是 BusinessException ——
            //   连 NPE / SQL 异常一起接住，保证调度不中断。
            log.error("超时关单任务异常", e);
        }
    }
}
