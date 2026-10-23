package com.mallx.product.vo;

import lombok.Data;

/** 店铺出参（Day 64） */
@Data
public class ShopVO {

    private Long id;
    private String name;
    private String logo;
    private String description;
    private Integer status;
}
