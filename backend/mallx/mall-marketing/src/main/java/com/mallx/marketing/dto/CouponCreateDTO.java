package com.mallx.marketing.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 新建优惠券（管理端）—— {@code POST /api/admin/coupons} 的请求体。
 *
 * <p>★★ <b>本 DTO 只做「参数层」能做的校验</b>：非空、格式、范围。而
 * 「FIXED 必须有 discountAmount / DISCOUNT 必须有 discountRate」以及
 * 「endTime 必须晚于 startTime」属于<b>字段之间的关系</b>，参数层表达不了
 * （除非用 {@code @AssertTrue}，但那会让请求体多出一个伪字段 {@code timeRangeValid}
 * 出现在 Swagger 上）→ 这两条放在 {@code CouponServiceImpl.createCoupon} 里守。
 *
 * <p>★ 这就是本项目反复出现的那条分层：<b>{@code @Valid} 跑在 {@code @PreAuthorize} 之前</b>
 * （校验在参数解析期、授权在方法调用期）→ 非法请求会<b>先撞 400</b>，与有没有权限无关。
 *
 * <p>⚠️ 字段一律用<b>包装类型</b>（{@code Integer} / {@code BigDecimal}），不用基本类型：
 * 基本类型无法表达「没传」，且 {@code @NotNull} 对基本类型恒为 true。
 *
 * <p>⚠️ {@code discountRate} 的上限写 {@code 99.99}：列是 {@code NUMERIC(5,2)}
 * → 整数部分最多 3 位。折扣率若允许 100，语义上应该是「不打折」，
 * 那种券没人会发；写成 {@code 99.99} 是把「无意义的值」挡在入口。
 */
@Data
public class CouponCreateDTO {

    /** 券名。列 VARCHAR(100)，无 UNIQUE → 允许重名（真实业务里同名券很常见） */
    @NotBlank(message = "券名不能为空")
    @Size(max = 100, message = "券名不能超过 100 字")
    private String name;

    /**
     * 券类型：FIXED / DISCOUNT。
     * ★ 用 {@code @Pattern} 而不是 {@code @NotNull} + Service 判断：
     * 取值集合是<b>参数层就能说清</b>的事实，不该拖到业务层。
     */
    @NotBlank(message = "券类型不能为空")
    @Pattern(regexp = "FIXED|DISCOUNT", message = "券类型只能是 FIXED 或 DISCOUNT")
    private String type;

    /** 满减金额：type=FIXED 时必填（关系校验在 Service） */
    @DecimalMin(value = "0.01", message = "满减金额必须大于 0")
    private BigDecimal discountAmount;

    /**
     * 折扣率：type=DISCOUNT 时必填（关系校验在 Service）。
     * ★ <b>应付比例系数</b>，{@code 0.80} = 打 8 折（实付 80%）；取值 {@code (0, 1]}。
     *
     * <p>⚠️ 这里的 {@code @DecimalMin("0.01")} 比业务判据 {@code (0,1]} 更严
     * （把 {@code (0, 0.01)} 也挡了）—— 方向是安全的：<b>入口比业务严，只会少收
     * 合法值，不会放过脏数据</b>。但业务侧的 {@code rate <= 0 || rate > 1}
     * 仍然必须留着，它还要挡「绕过接口直接写库」的那类脏数据。
     */
    @DecimalMin(value = "0.01", message = "折扣率必须大于 0")
    @DecimalMax(value = "1.00", message = "折扣率不能大于 1（0.80 表示打 8 折）")
    private BigDecimal discountRate;

    /** 使用门槛（可选）。阶段一不参与计算，只是券面展示信息 */
    @DecimalMin(value = "0.00", message = "使用门槛不能为负")
    private BigDecimal minAmount;

    /**
     * 发行总量。
     * ★ 允许 0：那是一张「建得出来但谁都领不到」的券 —— 合法且有用（先占位后放量）。
     * 验收链路 I 会专门断言这个边界（建得出、领不到、不报错）。
     */
    @NotNull(message = "发行总量不能为空")
    @Min(value = 0, message = "发行总量不能为负")
    private Integer totalCount;

    /** 可领起始时间（列 NOT NULL，无默认值 → 必须传） */
    @NotNull(message = "开始时间不能为空")
    private LocalDateTime startTime;

    /** 可领截止时间（列 NOT NULL，无默认值 → 必须传） */
    @NotNull(message = "结束时间不能为空")
    private LocalDateTime endTime;
}
