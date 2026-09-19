package com.mallx.order.vo;

import lombok.Data;

/**
 * 下单时读出的地址快照原料（{@code OrderMapper.selectAddressForOrder} 的结果集）。
 *
 * <p>字段名对应 XML 里 SELECT 出的列名，靠 yml 的 {@code map-underscore-to-camel-case} 自动映射。
 * 这里【不含 id / userId】—— 只承担「把内容拷进 orders 快照」这一个职责。
 */
@Data
public class AddressForOrderVO {

    private String receiverName;

    private String receiverPhone;

    private String province;

    private String city;

    private String district;

    private String detailAddress;
}
