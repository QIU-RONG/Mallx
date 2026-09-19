package com.mallx.user.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.user.dto.AddressSaveDTO;
import com.mallx.user.entity.UserAddress;
import com.mallx.user.mapper.UserAddressMapper;
import com.mallx.user.service.AddressService;
import com.mallx.user.vo.AddressVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class AddressServiceImpl implements AddressService {

    private final UserAddressMapper addressMapper;

    public AddressServiceImpl(UserAddressMapper addressMapper) {
        this.addressMapper = addressMapper;
    }

    @Override
    public List<AddressVO> list(Long userId) {
        List<UserAddress> rows = addressMapper.selectList(new LambdaQueryWrapper<UserAddress>()
                .eq(UserAddress::getUserId, userId)
                .orderByDesc(UserAddress::getIsDefault)
                .orderByAsc(UserAddress::getId));
        return rows.stream().map(this::toVO).collect(Collectors.toList());
    }

    @Override
    public AddressVO detail(Long userId, Long addressId) {
        return toVO(requireOwn(userId, addressId));
    }

    @Override
    @Transactional
    public Long create(Long userId, AddressSaveDTO dto) {
        // ★★ 空 ①：这条地址要不要成为默认？
        //    条件 = 用户显式传了 isDefault=true  ||  这是他的第一条地址（count == 0）
        long count = addressMapper.selectCount(new LambdaQueryWrapper<UserAddress>()
                .eq(UserAddress::getUserId, userId));
        boolean makeDefault = Boolean.TRUE.equals(dto.getIsDefault()) || count == 0;

        // ★★ 空 ②：要成为默认 → 先把该用户现有的默认标记全清掉（同事务内，一行调用）
        if (makeDefault) {
            clearDefault(userId, null);
        }

        // ③ 组装 + 落库（这个是搬砖，我替你写好了）
        UserAddress addr = new UserAddress();
        addr.setUserId(userId);                       // ★ userId 只从参数来，绝不信客户端
        addr.setReceiverName(dto.getReceiverName());
        addr.setReceiverPhone(dto.getReceiverPhone());
        addr.setProvince(dto.getProvince());
        addr.setCity(dto.getCity());
        addr.setDistrict(dto.getDistrict());
        addr.setDetailAddress(dto.getDetailAddress());
        addr.setIsDefault(makeDefault);               // ★ 用算出来的值，不是 dto 原值
        addressMapper.insert(addr);
        return addr.getId();
    }

    @Override
    @Transactional
    public void update(Long userId, Long addressId, AddressSaveDTO dto) {
        UserAddress old = requireOwn(userId, addressId);   // ← 第一行永远先验明正身

        // ★ isDefault 是本接口唯一不做「全量覆盖」的字段：
        //   true → 转移默认（清掉别人的，排除自己）；null / false → 不动当前默认状态。
        //   刻意不允许传 false 直接取消 —— 那会造出「有地址、零默认」的状态，
        //   和 remove() 的补位逻辑自相矛盾。换默认的唯一途径是把另一条设为默认。
        if (Boolean.TRUE.equals(dto.getIsDefault()) && !Boolean.TRUE.equals(old.getIsDefault())) {
            clearDefault(userId, addressId);   // 第二个参数传自己，别把自己也清成 false
            old.setIsDefault(true);
        }

        // 业务字段全量覆盖（PUT 语义：不传就是空，不做差分）
        old.setReceiverName(dto.getReceiverName());
        old.setReceiverPhone(dto.getReceiverPhone());
        old.setProvince(dto.getProvince());
        old.setCity(dto.getCity());
        old.setDistrict(dto.getDistrict());
        old.setDetailAddress(dto.getDetailAddress());

        // ⚠️ old 是 selectById 读回来的（updatedAt 非 null）→ strictUpdateFill 不会刷 updated_at。
        //    当前选择：不管它（审计字段，业务不依赖）。
        addressMapper.updateById(old);
    }

    @Override
    @Transactional
    public void remove(Long userId, Long addressId) {
        UserAddress old = requireOwn(userId, addressId);

        boolean wasDefault = Boolean.TRUE.equals(old.getIsDefault());

        // 本表无 is_deleted → 真 DELETE（这也是全项目唯一一处真删之外的第二处）
        addressMapper.deleteById(addressId);

        if (wasDefault) {
            // 补位：从该用户「剩下的」地址里挑 id 最小的那条接任。
            // ★ selectOne 在结果 >1 行时会直接抛异常，所以必须配 LIMIT 1 约束住；
            //   last() 是往 SQL 尾巴拼原生片段 —— 只许写死常量，绝不能拼用户输入。
            UserAddress next = addressMapper.selectOne(new LambdaQueryWrapper<UserAddress>()
                    .eq(UserAddress::getUserId, userId)
                    .orderByAsc(UserAddress::getId)
                    .last("LIMIT 1"));

            if (next != null) {              // 删的是最后一条地址 → next 为 null，什么都别做
                next.setIsDefault(true);
                addressMapper.updateById(next);   // 同样不刷 updated_at（同上，选择不管）
            }
        }
    }

    @Override
    @Transactional
    public void setDefault(Long userId, Long addressId) {
        UserAddress old = requireOwn(userId, addressId);   // 第一行永远先验明正身

        // 已经是默认 → 幂等短路：省掉两条 UPDATE，也不去无谓地锁一片行。
        // 少了这句功能依然正确（clearDefault 排除自己后再置 true 是幂等的），
        // 但它把「重复请求」挡在数据库门外。
        if (Boolean.TRUE.equals(old.getIsDefault())) {
            return;
        }

        // ★ 与 create 里传 null 不同：这里必须传 addressId 把自己排除在外 ——
        //   传 null 会先把自己也清成 false，再置回 true，功能虽对却白多一次行更新。
        clearDefault(userId, addressId);

        old.setIsDefault(true);
        addressMapper.updateById(old);    // 同样不刷 updated_at（同上，选择不管）
    }

    /**
     * 把该用户的默认标记全部清掉（exceptId 可排除某一行，传 null 表示不排除）。
     *
     * ★ 抽成私有方法，让 create / setDefault 各自在事务内调用它 ——
     *   公开方法之间互相调会「自调用」，不走代理 → @Transactional 静默失效。
     */
    private void clearDefault(Long userId, Long exceptId) {
        addressMapper.update(null, new LambdaUpdateWrapper<UserAddress>()
                .eq(UserAddress::getUserId, userId)
                .eq(UserAddress::getIsDefault, true)
                .ne(exceptId != null, UserAddress::getId, exceptId)   // 条件为假时整段跳过
                .set(UserAddress::getIsDefault, false));
    }

    /**
     * 验明正身：存在 + 属于当前用户。两种失败一律 404（不返 403，避免泄露 id 有效性）。
     */
    private UserAddress requireOwn(Long userId, Long addressId) {
        UserAddress addr = addressMapper.selectById(addressId);
        if (addr == null || !addr.getUserId().equals(userId)) {
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(), "地址不存在");
        }
        return addr;
    }

    private AddressVO toVO(UserAddress addr) {
        AddressVO vo = new AddressVO();
        BeanUtils.copyProperties(addr, vo);      // ★ 这里 copyProperties 是安全的：VO 没有多出来的字段
        return vo;
    }
}
