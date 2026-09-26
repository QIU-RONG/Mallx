package com.mallx.order.mq;

import com.mallx.order.service.impl.OrderCancelExecutor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

/**
 * 延迟关单消费者（V1.1 · D41）。
 *
 * <p>消费 {@code mallx.order.close} 队列：TTL 到期的订单 id 逐个走
 * {@link OrderCancelExecutor#cancelOne(Long)} —— 与 {@code @Scheduled} 扫描关单
 * 共用同一个 CAS 入口，<b>幂等</b>：用户已支付/已取消时 cancelOne 返回 false（0 行），无害。
 *
 * <p>★ 异常处理：单笔失败 catch 住打日志——不能让一条坏消息把消费通道卡死；
 * 该单随后会被 @Scheduled 扫描兜底（双保险的意义）。
 */
@Component
public class OrderCloseListener {

    private static final Logger log = LoggerFactory.getLogger(OrderCloseListener.class);

    private final OrderCancelExecutor cancelExecutor;

    public OrderCloseListener(OrderCancelExecutor cancelExecutor) {
        this.cancelExecutor = cancelExecutor;
    }

    @RabbitListener(queues = OrderDelayMqConfig.QUEUE_CLOSE)
    public void onClose(String orderIdText) {
        long orderId;
        try {
            orderId = Long.parseLong(orderIdText.trim());
        } catch (NumberFormatException e) {
            log.warn("延迟关单：非法消息体 {}，丢弃", orderIdText);
            return;
        }
        try {
            boolean closed = cancelExecutor.cancelOne(orderId);
            log.info("延迟关单：orderId={} {}", orderId, closed ? "已关闭" : "状态已非待支付（跳过）");
        } catch (Exception e) {
            // 吞掉：@RabbitListener 默认会 requeue，坏消息会无限循环；
            // 打日志 + 交给扫描兜底，是这里最安全的语义。
            log.warn("延迟关单失败，交由扫描兜底 orderId={}", orderId, e);
        }
    }
}
