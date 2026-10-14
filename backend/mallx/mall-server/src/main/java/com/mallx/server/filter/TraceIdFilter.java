package com.mallx.server.filter;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;

/**
 * ★ 请求上下文过滤器（Day 48 · 日志改进第一批）—— 给<b>每一条日志</b>自动带上
 * 「哪次请求」的身份标识。
 *
 * <hr>
 *
 * <p><b>为什么需要它</b>：改造前本项目用的是 Spring Boot 默认日志格式
 * （时间戳 + 级别 + 线程 + 类名 + 消息），<b>没有任何请求身份信息</b>。
 * 于是「用户投诉下单失败」时的排查姿势是：
 * <ol>
 *   <li>业务日志只写了 {@code 业务异常：code=400,message=库存不足}</li> ——
 *       不知道是<b>谁的</b>哪一次请求；</li>
 *   <li>只能拿用户提供的「大概几点几分」去日志里数时间戳 ——
 *       并发一高，同一毫秒有十几条日志，根本对不上；</li>
 *   <li>更糟：同一次请求会打好几行（Controller → Service → Mapper），
 *       没有共同标识时<b>无法证明它们属于同一次调用</b>。</li>
 * </ol>
 *
 * <p><b>做法：MDC（Mapped Diagnostic Context）</b> —— SLF4J 提供的线程级上下文，
 * 放进去的键值会被<b>该线程后续所有日志</b>自动带上，且零侵入（不用改每个 log 调用）。
 * 这里的 {@code logback-spring.xml} 把 {@code %X{traceId}} 和 {@code %X{uri}} 加进了 pattern。
 *
 * <p><b>为什么 traceId 优先取请求头</b>：将来前后端之间、服务与服务之间可以传递
 * 同一个 traceId（链路追踪的起点）。现在没有调用方，就自己生成 ——
 * 但先把「能从外面带进来」这个口子留着，比将来改实现便宜。
 *
 * <hr>
 *
 * <p>★★ <b>{@link #clearMdc()} 是必须的，不是洁癖</b>：
 * Tomcat 的worker 线程是<b>池化复用</b>的。如果在 {@code doFilter} 里只 put 不 remove，
 * 下一个请求复用同一线程时，MDC 里残留的还是<b>上一个请求的 traceId</b> ——
 * 于是两条毫不相干的日志被打上同一个标识，比没有标识更糟（它会误导你往错的方向查）。
 * 这是 MDC 最经典的事故，写这段代码的人几乎都踩过。
 *
 * <p>★ 同理：<b>异步线程不继承 MDC</b>。本项目的异步场景（MQ 消费者、定时任务）
 * 拿不到 traceId —— 那些地方的日志必须自己带业务标识（orderId / refundNo），
 * 这也是业务日志里显式写业务 id 的另一个理由。
 *
 * <p>⚠️ 顺序：用 {@code HIGHEST_PRECEDENCE} 而不是默认注册顺序 ——
 * Spring Security 的 FilterChain 顺序是 {@code -100}，
 * 默认注册的 {@code @Component} Filter 会排在它<b>后面</b>，
 * 那样 Security 层拒绝（401/403）的日志就带不上 traceId 了。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    /** 客户端可以带这个头把上游的 traceId 传进来（链路追踪的接入口）。 */
    public static final String TRACE_HEADER = "X-Trace-Id";

    private static final String TRACE_KEY = "traceId";
    private static final String URI_KEY = "uri";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String traceId = request.getHeader(TRACE_HEADER);
        if (traceId == null || traceId.isBlank()) {
            // ★ 取 UUID 前 8 位：全量 36 位在日志里太长，而 8 位十六进制的碰撞概率
            //   在单应用单次会话里可以忽略（排障只需在几千行日志里区分，不需要全局唯一）。
            traceId = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        }
        // ★ 回写响应头：用户/前端报障时报这个 id，比报"大概几点"精确一万倍
        response.setHeader(TRACE_HEADER, traceId);

        MDC.put(TRACE_KEY, traceId);
        MDC.put(URI_KEY, request.getMethod() + " " + request.getRequestURI());
        try {
            filterChain.doFilter(request, response);
        } finally {
            // ★★ 线程池复用 ⇒ 不清理就会串号（见类注释）
            clearMdc();
        }
    }

    /** 抽出来独立成方法：{@code finally} 里只调一个方法，将来加键时只改一处。 */
    private void clearMdc() {
        MDC.remove(TRACE_KEY);
        MDC.remove(URI_KEY);
    }
}
