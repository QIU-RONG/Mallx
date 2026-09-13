package com.mallx.product.vo;

import lombok.Data;

import java.util.ArrayList;
import java.util.List;

@Data
public class CategoryVO {
    private Long id;
    private Long parentId;
    private String name;
    private Integer sortOrder;

    private List<CategoryVO> children = new ArrayList<>();
}
