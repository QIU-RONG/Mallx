package com.mallx.product.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.product.entity.Favorite;
import com.mallx.product.entity.Product;
import com.mallx.product.mapper.FavoriteMapper;
import com.mallx.product.mapper.ProductMapper;
import com.mallx.product.mapper.ProductSkuMapper;
import com.mallx.product.service.FavoriteService;
import com.mallx.product.vo.FavoriteVO;
import com.mallx.product.vo.ProductPriceRangeVO;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 收藏服务（Day 82）。
 *
 * <p>★ 列表的「产品名/图/价格」不冗余存储：收藏只存 id，
 * 展示时按 productId 批量回查（一次 selectByIds + 一次价格聚合），商品改价后收藏列表自动跟着变。
 */
@Service
public class FavoriteServiceImpl implements FavoriteService {

    private static final long MAX_PAGE_SIZE = 100;

    private final FavoriteMapper favoriteMapper;
    private final ProductMapper productMapper;
    private final ProductSkuMapper productSkuMapper;

    public FavoriteServiceImpl(FavoriteMapper favoriteMapper, ProductMapper productMapper,
                               ProductSkuMapper productSkuMapper) {
        this.favoriteMapper = favoriteMapper;
        this.productMapper = productMapper;
        this.productSkuMapper = productSkuMapper;
    }

    @Override
    public void add(Long userId, Long productId) {
        if (productMapper.selectById(productId) == null) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "商品不存在");
        }
        Favorite fav = new Favorite();
        fav.setUserId(userId);
        fav.setProductId(productId);
        try {
            favoriteMapper.insert(fav);
        } catch (DuplicateKeyException ignored) {
            // 幂等：唯一索引撞了就说明已经收藏过
        }
    }

    @Override
    public void remove(Long userId, Long productId) {
        favoriteMapper.delete(new LambdaQueryWrapper<Favorite>()
                .eq(Favorite::getUserId, userId)
                .eq(Favorite::getProductId, productId));
    }

    @Override
    public boolean exists(Long userId, Long productId) {
        return favoriteMapper.selectCount(new LambdaQueryWrapper<Favorite>()
                .eq(Favorite::getUserId, userId)
                .eq(Favorite::getProductId, productId)) > 0;
    }

    @Override
    public PageResult<FavoriteVO> page(Long userId, long current, long size) {
        long safePage = Math.max(current, 1);
        long safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);
        IPage<Favorite> result = favoriteMapper.selectPage(new Page<>(safePage, safeSize),
                new LambdaQueryWrapper<Favorite>()
                        .eq(Favorite::getUserId, userId)
                        .orderByDesc(Favorite::getCreatedAt)
                        .orderByDesc(Favorite::getId));

        List<Favorite> records = result.getRecords();
        List<FavoriteVO> voList = new ArrayList<>();
        if (!records.isEmpty()) {
            List<Long> ids = records.stream().map(Favorite::getProductId).toList();
            Map<Long, Product> products = productMapper.selectByIds(ids).stream()
                    .collect(Collectors.toMap(Product::getId, Function.identity()));
            Map<Long, ProductPriceRangeVO> prices = productSkuMapper.selectPriceRange(ids).stream()
                    .collect(Collectors.toMap(ProductPriceRangeVO::getProductId, Function.identity()));
            for (Favorite f : records) {
                Product p = products.get(f.getProductId());
                FavoriteVO vo = new FavoriteVO();
                vo.setProductId(f.getProductId());
                vo.setCreatedAt(f.getCreatedAt());
                if (p != null) {
                    vo.setName(p.getName());
                    vo.setMainImage(p.getMainImage());
                    vo.setStatus(p.getStatus());
                }
                ProductPriceRangeVO price = prices.get(f.getProductId());
                if (price != null) {
                    vo.setMinPrice(price.getMinPrice());
                    vo.setMaxPrice(price.getMaxPrice());
                    vo.setDefaultSkuId(price.getDefaultSkuId());
                }
                voList.add(vo);
            }
        }
        PageResult<FavoriteVO> vo = new PageResult<>();
        vo.setRecords(voList);
        vo.setTotal(result.getTotal());
        vo.setCurrent(result.getCurrent());
        vo.setSize(result.getSize());
        return vo;
    }
}
