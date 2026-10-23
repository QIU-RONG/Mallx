package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.dto.ShopCreateDTO;
import com.mallx.product.dto.ShopUpdateDTO;
import com.mallx.product.entity.Shop;
import com.mallx.product.mapper.ShopMapper;
import com.mallx.product.service.ShopService;
import com.mallx.product.vo.ShopVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 店铺服务实现（Day 64）。
 *
 * <p>★ 店名 UNIQUE 的处理与 brands 一致：先查重，命中返回 <b>400 人话</b>
 * —— 不能把数据库的 23505 冒到兜底 handler 变成 500。
 */
@Service
public class ShopServiceImpl implements ShopService {

    private final ShopMapper shopMapper;

    public ShopServiceImpl(ShopMapper shopMapper) {
        this.shopMapper = shopMapper;
    }

    @Override
    public List<ShopVO> listAll() {
        return shopMapper.selectList(new LambdaQueryWrapper<Shop>().orderByAsc(Shop::getId))
                .stream()
                .map(this::toVo)
                .toList();
    }

    @Override
    public Long create(ShopCreateDTO dto) {
        String name = dto.getName() == null ? "" : dto.getName().trim();
        if (name.isEmpty()) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "店铺名不能为空");
        }
        ensureNameFree(name, null);

        Shop shop = new Shop();
        shop.setName(name);
        shop.setLogo(dto.getLogo());
        shop.setDescription(dto.getDescription());
        shop.setStatus(dto.getStatus() == null ? 1 : dto.getStatus());
        shop.setCreatedAt(LocalDateTime.now());
        shop.setUpdatedAt(LocalDateTime.now());
        shopMapper.insert(shop);
        return shop.getId();
    }

    @Override
    public void update(Long id, ShopUpdateDTO dto) {
        Shop shop = shopMapper.selectById(id);
        if (shop == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "店铺不存在");
        }
        if (dto.getName() != null) {
            String name = dto.getName().trim();
            if (name.isEmpty()) {
                throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "店铺名不能为空");
            }
            ensureNameFree(name, id);
            shop.setName(name);
        }
        if (dto.getLogo() != null) {
            shop.setLogo(dto.getLogo());
        }
        if (dto.getDescription() != null) {
            shop.setDescription(dto.getDescription());
        }
        if (dto.getStatus() != null) {
            shop.setStatus(dto.getStatus());
        }
        shop.setUpdatedAt(LocalDateTime.now());
        shopMapper.updateById(shop);
    }

    private void ensureNameFree(String name, Long excludeId) {
        Shop exist = shopMapper.selectOne(new LambdaQueryWrapper<Shop>().eq(Shop::getName, name).last("LIMIT 1"));
        if (exist != null && !exist.getId().equals(excludeId)) {
            throw new BusinessException(ResultCode.VALIDATE_FAILED.getCode(), "店铺名已存在");
        }
    }

    private ShopVO toVo(Shop shop) {
        ShopVO vo = new ShopVO();
        BeanUtils.copyProperties(shop, vo);
        return vo;
    }
}
