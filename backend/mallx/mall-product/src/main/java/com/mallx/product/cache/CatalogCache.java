package com.mallx.product.cache;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mallx.product.vo.ProductDetailVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.time.Duration;

/**
 * 目录缓存（V1.1 · D38）：商品详情的 cache-aside + 「代次键」失效。
 *
 * <p><b>为什么用代次键，而不是逐键删除 / SCAN 匹配删除？</b>
 * 详情响应里内嵌了 {@code categoryName} / {@code brandName} 两个冗余字段（Day 09 的装配决定），
 * 所以失效点不只是「商品被改」——分类改名、品牌改名同样会让已缓存的详情变脏。
 * 失效点是<b>一族</b>（3 个 Controller、9 个写方法），逐键删除就得维护「哪些 key 属于这个分类」
 * 的反向索引；SCAN/KEYS 又是 O(N) 全库扫描。
 * 代次键把问题变成一个计数器：<b>任何目录写操作把代次号 +1，旧代次的 key 一次性全部失活</b>
 * （读不到旧 key = miss 回源），旧 key 留到 TTL 自然过期即可，不需要删除。
 *
 * <p><b>缓存内容边界（D38 的脏读课题结论）</b>：
 * {@code ProductDetailVO} 里<b>没有库存</b>——SKU 出参只含价格/属性/图片，
 * 库存属于 mall-inventory 的独立上下文，从不出现在详情响应里
 * ⇒ 缓存的失效点就是目录写，不存在「库存变了缓存还在」的脏读窗口。
 *
 * <p><b>降级纪律</b>：本类所有 Redis 操作都可能失败（Redis 挂了 / 超时），
 * 失败一律吞掉并降级——{@link #readDetail} 返回 null（回源数据库）、
 * {@link #bump}/{@code writeDetail} 静默放弃。<b>缓存永远不能把业务打挂</b>；
 * 代价只是「这次多查一次库」。降级日志打 warn 不打 error（常态可恢复，不是事故）。
 */
@Component
public class CatalogCache {

    private static final Logger log = LoggerFactory.getLogger(CatalogCache.class);

    /** 代次号 key：目录域的「版本号」，INCR 即全体失效 */
    public static final String KEY_GEN = "mallx:catalog:gen";

    /** 详情缓存 TTL 基准 30 分钟 + 0~300 秒抖动（防同一秒失效引发集体回源） */
    private static final long TTL_BASE_SECONDS = 1800;
    private static final long TTL_JITTER_SECONDS = 300;

    private final StringRedisTemplate redis;
    /**
     * ★ 自建 Jackson 2 的 ObjectMapper，不注入：Boot 4.1 的自动配置给的是 Jackson 3
     *   （{@code tools.jackson.databind.ObjectMapper}），注入 com.fasterxml 版本会直接
     *   启动失败（D38 实测）。本类只序列化 ProductDetailVO 这个简单 POJO，
     *   裸 ObjectMapper 足够；关掉 UNKNOWN 属性报错，为将来 VO 加字段留兼容余地。
     */
    private final ObjectMapper objectMapper = new ObjectMapper()
            .configure(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    private final SecureRandom jitter = new SecureRandom();

    public CatalogCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** 当前代次号（Redis 不可用返回 "0"——降级成「代次永不变」，等于退回纯回源） */
    public String generation() {
        try {
            String gen = redis.opsForValue().get(KEY_GEN);
            return gen == null ? "0" : gen;
        } catch (Exception e) {
            log.warn("catalog cache: 读代次号失败，降级回源 gen=0: {}", e.getMessage());
            return "0";
        }
    }

    /**
     * 目录写失效：代次号 +1，旧代次全部失活。
     * <p>★ 在事务方法<b>末尾</b>调用（commit 前一瞬间）：极端情况下「事务回滚但代次已 +1」
     * 只造成一轮多余的 cache miss，方向是安全的；反过来「先删后写」造成的一致性风险更大。
     */
    public void bump() {
        try {
            redis.opsForValue().increment(KEY_GEN);
        } catch (Exception e) {
            // 降级：失效失败 ⇒ 旧缓存会活到 TTL（≤30 分钟）。对目录类数据可接受，
            // 但必须在日志里留痕，便于与「改了怎么没生效」的用户反馈对账。
            log.warn("catalog cache: 代次号 +1 失败，旧缓存最长存活到 TTL: {}", e.getMessage());
        }
    }

    /** 读缓存（miss / Redis 不可用 / 反序列化失败 都返回 null ⇒ 调用方回源） */
    public ProductDetailVO readDetail(String generation, long id) {
        try {
            String json = redis.opsForValue().get(detailKey(generation, id));
            if (json == null) {
                return null;
            }
            return objectMapper.readValue(json, ProductDetailVO.class);
        } catch (Exception e) {
            // 反序列化失败视同 miss：宁可回源，不可把坏数据吐给用户
            log.warn("catalog cache: 详情读缓存失败/反序列化失败，降级回源 id={}: {}", id, e.getMessage());
            return null;
        }
    }

    /** 回填缓存（失败静默——下一次请求重新回源而已） */
    public void writeDetail(String generation, long id, ProductDetailVO vo) {
        try {
            long ttl = TTL_BASE_SECONDS + jitter.nextInt((int) TTL_JITTER_SECONDS);
            redis.opsForValue().set(detailKey(generation, id),
                    objectMapper.writeValueAsString(vo), Duration.ofSeconds(ttl));
        } catch (Exception e) {
            log.warn("catalog cache: 详情回填失败 id={}: {}", id, e.getMessage());
        }
    }

    private String detailKey(String generation, long id) {
        return "mallx:cache:product:detail:v" + generation + ":" + id;
    }

    // ==================== D39：分类树 / 品牌列表（同一代次键域） ====================
    // 它们的写点就是 detail 的失效点（目录写一族）⇒ bump 一次三层（detail/tree/brands）受益。

    /** 分类树缓存 key（整棵树一个 key：分类总量小，整存整取最简单） */
    public String treeKey(String generation) {
        return "mallx:cache:category:tree:v" + generation;
    }

    /** 品牌列表缓存 key（按 status 分桶：C 端 1 / 管理端 null） */
    public String brandListKey(String generation, Integer status) {
        return "mallx:cache:brand:list:v" + generation + ":" + (status == null ? "all" : status);
    }

    /** 通用读（miss / Redis 不可用 / 反序列化失败 ⇒ null，调用方回源） */
    public <T> T readJson(String key, TypeReference<T> type) {
        try {
            String json = redis.opsForValue().get(key);
            if (json == null) {
                return null;
            }
            return objectMapper.readValue(json, type);
        } catch (Exception e) {
            log.warn("catalog cache: 读缓存失败 {}，降级回源: {}", key, e.getMessage());
            return null;
        }
    }

    /** 通用写（失败静默；TTL 与 detail 同款基准+抖动） */
    public void writeJson(String key, Object value) {
        try {
            long ttl = TTL_BASE_SECONDS + jitter.nextInt((int) TTL_JITTER_SECONDS);
            redis.opsForValue().set(key, objectMapper.writeValueAsString(value), Duration.ofSeconds(ttl));
        } catch (Exception e) {
            log.warn("catalog cache: 回填失败 {}: {}", key, e.getMessage());
        }
    }
}
