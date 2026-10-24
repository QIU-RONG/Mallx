package com.mallx.payment.dto;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

/**
 * 批量支付（Day 78）：跨店拆单后一次付清多张待支付订单。
 *
 * <p>★ 金额不由客户端传：每张订单的实付额由服务端逐单读取并累加。
 */
@Data
public class BatchPayDTO {

    @NotEmpty(message = "请选择要支付的订单")
    @Size(max = 20, message = "一次最多支付 20 张订单")
    private List<Long> orderIds;

    @Pattern(regexp = "ALIPAY|WECHAT|BALANCE", message = "支付方式只能是 ALIPAY / WECHAT / BALANCE")
    private String method = "BALANCE";
}
