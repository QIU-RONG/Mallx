package com.mallx.user.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 地址新增/修改共用（PUT 是全量覆盖语义，不做差分） */
@Data
public class AddressSaveDTO {

    @NotBlank(message = "收件人不能为空")
    @Size(max = 50, message = "收件人姓名不能超过 50 字")
    private String receiverName;

    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1[3-9]\\d{9}$", message = "手机号格式不正确")
    private String receiverPhone;

    @NotBlank(message = "省份不能为空")
    @Size(max = 50, message = "省份不能超过 50 字")
    private String province;

    @NotBlank(message = "城市不能为空")
    @Size(max = 50, message = "城市不能超过 50 字")
    private String city;

    @NotBlank(message = "区县不能为空")
    @Size(max = 50, message = "区县不能超过 50 字")
    private String district;

    @NotBlank(message = "详细地址不能为空")
    @Size(max = 255, message = "详细地址不能超过 255 字")
    private String detailAddress;

    /** 可空：null 视作 false。最终是否为默认，由 Service 结合「是不是第一条」决定 */
    private Boolean isDefault;
}
