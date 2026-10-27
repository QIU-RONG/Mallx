package com.mallx.product.service;

import com.mallx.common.api.PageResult;
import com.mallx.product.vo.FavoriteVO;

/** 收藏（Day 82） */
public interface FavoriteService {

    /** 收藏（幂等：已收藏直接返回） */
    void add(Long userId, Long productId);

    /** 取消收藏（幂等） */
    void remove(Long userId, Long productId);

    boolean exists(Long userId, Long productId);

    PageResult<FavoriteVO> page(Long userId, long current, long size);
}
