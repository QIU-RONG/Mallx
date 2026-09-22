package com.mallx.inventory.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 管理端库存调整入参（{@code POST /api/admin/inventory/skus/{skuId}/adjust}）。
 *
 * <p>★★ {@code delta} 是<b>带符号</b>的：
 * <pre>
 *   delta > 0   补货 / 盘盈（仓库里真的多了货）→ total + d , available + d
 *   delta < 0   报损 / 盘亏（仓库里真的少了货）→ total - d , available - d
 * </pre>
 * ★ 为什么不让调用方传「调整后的目标值」而要传「变化量」：
 * 目标值写法必须「先查当前值、再算差值」—— 那是 TOCTOU（两个管理员同时提交，
 * 后一个会把前一个的调整覆盖掉，账面 silently 少一次调整）。
 * 变化量写法则是 {@code total_stock + #{delta}}，由数据库在一条 UPDATE 里原子完成，
 * 两个并发请求会各自生效（或其中一个被守卫挡下），不会互相覆盖。
 *
 * <p>⚠️ {@code delta == 0} 的拒绝<b>不在这里</b>：Jakarta Validation 没有
 * 「不等于某值」的现成注解，硬凑（比如 {@code @Min(-99999)}）只能表达幅度，
 * 表达不了「非 0」。所以那一条由 Service 手工判 —— 见
 * {@code InventoryServiceImpl.adjust} 的骨架说明。
 * （这不是取舍：语义上「delta=0」是<b>业务规则</b>不是<b>格式规则</b>，
 *   放 Service 反而更贴切。格式类校验留在注解里、业务类校验留在服务里，
 *   这条分界本身就是规矩。）
 *
 * <p>★ {@code reason} <b>必填</b>：管理端的每一次改动都要有理由 —— 这是审计的最低要求，
 * 成本只是一个字段。
 * <p>⚠️ <b>本日只校验、不落库</b>（{@code inventory_logs} 没有备注列）。
 * 这是<b>显式取舍</b>：要落库就得加列（DDL + 实体 + VO 三处改动），
 * 而 V1.0 无前端、审计需求尚未成型。已记在
 * {@code docs/daily/Day-17-管理端订单与库存.md} §4.3，留到真有需求时一起做。
 */
@Data
public class InventoryAdjustDTO {

    @NotNull(message = "delta 不能为空（正数=补货，负数=报损）")
    private Integer delta;

    @NotBlank(message = "reason 不能为空（管理端改动必须留下理由）")
    @Size(max = 200, message = "reason 最长 200 字")
    private String reason;
}
