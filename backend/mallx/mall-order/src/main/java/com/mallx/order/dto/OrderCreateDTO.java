package com.mallx.order.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 下单入参（POST /api/orders）
 *
 * <p>★ 只有 {@code addressId}，没有 skuIds / quantity：
 * 买什么、买几件，唯一来源是「购物车里 {@code selected = TRUE} 的行」，
 * 客户端只表达「用哪个地址」—— 少一个可以被伪造的输入面。
 *
 * <p>为什么传 id 而不是收货信息：地址是用户维护的独立资源，下单时按 id 引用、
 * 把内容【拷贝成快照】存进 orders（并校验归属，防 IDOR）。
 */
@Data
public class OrderCreateDTO {

    @NotNull(message = "收货地址不能为空")
    private Long addressId;
}
