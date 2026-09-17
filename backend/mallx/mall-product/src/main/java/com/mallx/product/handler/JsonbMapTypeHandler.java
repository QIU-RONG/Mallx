package com.mallx.product.handler;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Map;

/**
 * {@code Map<String,Object>} ↔ PostgreSQL jsonb 的翻译官。
 *
 * <h3>【为什么需要它】</h3>
 * PG 的 jsonb 列<b>拒收 setString</b>，会报：
 * <pre>ERROR: column "attributes" is of type jsonb but expression is of type character varying</pre>
 * 必须用 {@code setObject(..., Types.OTHER)} 告诉驱动"这个参数我不指定 JDBC 类型，
 * 交给数据库按目标列的类型去推断"。
 * <p>
 * 更坑的是：<b>MyBatis-Plus 自带的 JacksonTypeHandler / Jackson3TypeHandler 也不行</b> ——
 * 用 {@code javap -c} 反编译 mybatis-plus-extension-3.5.17 可见
 * {@code AbstractJsonTypeHandler.setNonNullParameter} 内部调用的正是
 * {@code PreparedStatement.setString}，即上面失败的那条路。
 * <p>
 * 根因：本项目的 JDBC URL 没有 {@code stringtype=unspecified}（默认 stringtype=varchar），
 * 而 PostgreSQL 的类型系统不像 MySQL 那样"帮你猜"。
 *
 * <h3>【为什么不用 @MappedTypes 全局注册】</h3>
 * 全局注册（例如配 {@code mybatis-plus.type-handlers-package}）是按 <b>Java 类型</b>匹配的。
 * 本 handler 声明处理 {@code Map}，一旦全局注册，项目里<b>所有 Map 参数</b>都会被套上 jsonb 逻辑 ——
 * 这类问题排查起来极其难受。这里只通过 {@code @TableField(typeHandler = ...)} 精确指定给 attributes 一个字段。
 */
public class JsonbMapTypeHandler extends BaseTypeHandler<Map<String, Object>> {

    /**
     * 静态复用：ObjectMapper 是线程安全的，没必要每次 new。
     * 这里刻意用 Jackson 2（com.fasterxml.*）——它是本项目 jjwt-jackson 传递进来的，
     * 与框架的 Jackson 3（tools.jackson.*）互不干扰。
     */
    private static final ObjectMapper MAPPER = new ObjectMapper();

    /** Java → JDBC：写库时把 Map 序列化成 JSON 文本，并声明为"未指定类型" */
    @Override
    public void setNonNullParameter(PreparedStatement ps, int i,
                                    Map<String, Object> parameter, JdbcType jdbcType) throws SQLException {
        ps.setObject(i, toJson(parameter), Types.OTHER);
    }

    /** JDBC → Java：读库时把 jsonb 文本反序列化回 Map（getString 对 jsonb 是安全的） */
    @Override
    public Map<String, Object> getNullableResult(ResultSet rs, String columnName) throws SQLException {
        return parse(rs.getString(columnName));
    }

    @Override
    public Map<String, Object> getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        return parse(rs.getString(columnIndex));
    }

    @Override
    public Map<String, Object> getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        return parse(cs.getString(columnIndex));
    }

    private String toJson(Map<String, Object> map) {
        try {
            return MAPPER.writeValueAsString(map);
        } catch (Exception e) {
            // 抛 RuntimeException：一是让 @Transactional 能回滚（默认只回滚 RuntimeException），
            // 二是异常往外走才能被 GlobalExceptionHandler 看到
            throw new IllegalArgumentException("attributes 无法序列化为 JSON", e);
        }
    }

    private Map<String, Object> parse(String json) {
        if (json == null) {
            return null;
        }
        try {
            return MAPPER.readValue(json, new TypeReference<Map<String, Object>>() { });
        } catch (Exception e) {
            throw new IllegalArgumentException("attributes 不是合法 JSON：" + json, e);
        }
    }
}
