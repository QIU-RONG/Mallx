package com.mallx.ai.service;

import org.springframework.stereotype.Component;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 极简限流（Day 59）—— 内存滑动窗口，单实例够用。
 *
 * <p>★ 为什么不用 Redis：AI 调用是<b>可选增强</b>，不该因为缓存/中间件挂了整个客服不可用；
 * 而限流的目的是「别让一个人把额度刷爆」，内存版完全够。多实例时退化为「每实例 N 次/分」，
 * 对内部演示足够，真上线再换集中式计数器。
 */
@Component
public class AiRateLimiter {

    private final Map<String, Deque<Long>> buckets = new ConcurrentHashMap<>();

    public boolean allow(String key, int perMinute) {
        long now = System.currentTimeMillis();
        long windowStart = now - 60_000L;
        Deque<Long> q = buckets.computeIfAbsent(key, k -> new ArrayDeque<>());
        synchronized (q) {
            while (!q.isEmpty() && q.peekFirst() < windowStart) {
                q.pollFirst();
            }
            if (q.size() >= perMinute) {
                return false;
            }
            q.addLast(now);
            return true;
        }
    }
}
