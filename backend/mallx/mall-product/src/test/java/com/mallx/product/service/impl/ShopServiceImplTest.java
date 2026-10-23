package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.dto.ShopCreateDTO;
import com.mallx.product.dto.ShopUpdateDTO;
import com.mallx.product.entity.Shop;
import com.mallx.product.mapper.ShopMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 店铺服务的三条规则（Day 64）：
 * 1. 店名重复 → 400（不能把 23505 冒成 500）；
 * 2. 编辑不存在的店 → 404；
 * 3. 新建不传 status → 默认 1（启用），而不是 null 写进 NOT NULL 列。
 */
@ExtendWith(MockitoExtension.class)
class ShopServiceImplTest {

    @Mock
    private ShopMapper shopMapper;

    @InjectMocks
    private ShopServiceImpl shopService;

    @Test
    @DisplayName("店名重复 → 400「店铺名已存在」，且不写库")
    void duplicateNameRejected() {
        Shop exist = new Shop();
        exist.setId(1L);
        exist.setName("Apple 官方旗舰店");
        when(shopMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(exist);

        ShopCreateDTO dto = new ShopCreateDTO();
        dto.setName("Apple 官方旗舰店");

        BusinessException ex = assertThrows(BusinessException.class, () -> shopService.create(dto));

        assertEquals(400, ex.getCode());
        verify(shopMapper, never()).insert(any(Shop.class));
    }

    @Test
    @DisplayName("新建不传 status → 默认启用（1），且店名 trim")
    void createDefaultsToEnabled() {
        when(shopMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);

        ShopCreateDTO dto = new ShopCreateDTO();
        dto.setName("  新店铺  ");

        shopService.create(dto);

        ArgumentCaptor<Shop> captor = ArgumentCaptor.forClass(Shop.class);
        verify(shopMapper).insert(captor.capture());
        assertEquals("新店铺", captor.getValue().getName());
        assertEquals(1, captor.getValue().getStatus());
    }

    @Test
    @DisplayName("编辑不存在的店铺 → 404")
    void updateMissingShop() {
        when(shopMapper.selectById(99L)).thenReturn(null);

        ShopUpdateDTO dto = new ShopUpdateDTO();
        dto.setDescription("x");

        BusinessException ex = assertThrows(BusinessException.class, () -> shopService.update(99L, dto));

        assertEquals(404, ex.getCode());
        verify(shopMapper, never()).updateById(any(Shop.class));
    }
}
