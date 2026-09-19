package com.mallx.user.vo;

import lombok.Data;

import java.time.LocalDateTime;

/** 地址出参：刻意不含 userId，不把内部归属字段泄给客户端 */
@Data
public class AddressVO {
    private Long id;
    private String receiverName;
    private String receiverPhone;
    private String province;
    private String city;
    private String district;
    private String detailAddress;
    private Boolean isDefault;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
