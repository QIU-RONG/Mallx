package com.mallx.user.service;

import com.mallx.user.dto.AddressSaveDTO;
import com.mallx.user.vo.AddressVO;

import java.util.List;

public interface AddressService {

    /** 我的地址列表（默认地址排最前） */
    List<AddressVO> list(Long userId);

    /** 地址详情（非本人 → 404） */
    AddressVO detail(Long userId, Long addressId);

    /** 新增地址（第一条自动成为默认） */
    Long create(Long userId, AddressSaveDTO dto);

    /** 修改地址（业务字段全量覆盖；isDefault=true 时转移默认） */
    void update(Long userId, Long addressId, AddressSaveDTO dto);

    /** 删除地址（物理删除；若删掉的是默认地址，自动补位选一条新的） */
    void remove(Long userId, Long addressId);

    /** 设为默认地址（事务内互斥：先清掉该用户其余行，再置本行） */
    void setDefault(Long userId, Long addressId);
}
