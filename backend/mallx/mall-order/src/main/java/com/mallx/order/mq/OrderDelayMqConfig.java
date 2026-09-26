package com.mallx.order.mq;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 延迟关单的 MQ 拓扑（V1.1 · D41）—— <b>DLX + per-message TTL</b>，不依赖延迟插件。
 *
 * <pre>
 *   下单 ──publish(expiration=TTL)──▶ exchange: mallx.order.delay ──rk=ttl──▶ queue: mallx.order.ttl
 *                                                                          （无消费者，只等过期）
 *                                                                                │ TTL 到期
 *                                                                                ▼ (dead-letter)
 *                                     listener ◀── queue: mallx.order.close ◀──rk=close──┘
 * </pre>
 *
 * <p><b>为什么不用 rabbitmq_delayed_message_exchange 插件</b>：官方镜像不带，
 * 要自己装社区插件（版本耦合 + 离线环境拉不到）。DLX 方案是 RabbitMQ 原生语义，
 * 唯一代价是 TTL 队列里排队的消息只有队首到期才投递（本场景每单一消息、TTL 相同，无此问题）。
 *
 * <p><b>为什么保留 @Scheduled 扫描</b>（双保险）：发布失败 / MQ 宕机 / 消息丢失时，
 * 60 秒扫描兜底关单；两条路径最终都收敛到 {@code cancelOne} 的 CAS
 * （{@code WHERE status='PENDING_PAYMENT'}），谁先到谁赢，重复执行是 0 行无害。
 */
@Configuration
public class OrderDelayMqConfig {

    public static final String EXCHANGE = "mallx.order.delay";
    public static final String QUEUE_TTL = "mallx.order.ttl";
    public static final String QUEUE_CLOSE = "mallx.order.close";
    public static final String RK_TTL = "ttl";
    public static final String RK_CLOSE = "close";

    @Bean
    public DirectExchange orderDelayExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    /** TTL 停靠队列：没有消费者；到期后经 DLX 转投 close 队列 */
    @Bean
    public Queue orderTtlQueue() {
        return QueueBuilder.durable(QUEUE_TTL)
                .deadLetterExchange(EXCHANGE)
                .deadLetterRoutingKey(RK_CLOSE)
                .build();
    }

    @Bean
    public Queue orderCloseQueue() {
        return QueueBuilder.durable(QUEUE_CLOSE).build();
    }

    @Bean
    public Binding ttlBinding() {
        return BindingBuilder.bind(orderTtlQueue()).to(orderDelayExchange()).with(RK_TTL);
    }

    @Bean
    public Binding closeBinding() {
        return BindingBuilder.bind(orderCloseQueue()).to(orderDelayExchange()).with(RK_CLOSE);
    }
}
