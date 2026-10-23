package com.mallx.product.service;

import com.mallx.product.dto.ShopCreateDTO;
import com.mallx.product.dto.ShopUpdateDTO;
import com.mallx.product.vo.ShopVO;

import java.util.List;

/** 店铺服务（Day 64，展示层） */
public interface ShopService {

    /** 管理端：全部店铺（含停用） */
    List<ShopVO> listAll();

    /** 新建；店名重复 → 400 */
    Long create(ShopCreateDTO dto);

    /** 局部更新；不存在 → 404，改重名 → 400 */
    void update(Long id, ShopUpdateDTO dto);
}
