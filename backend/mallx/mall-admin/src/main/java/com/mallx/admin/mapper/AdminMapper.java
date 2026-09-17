package com.mallx.admin.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.admin.entity.Admin;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface AdminMapper extends BaseMapper<Admin> {
    List<String> selectPermissionCodesByAdminId(@Param("adminId") Long adminId);

    List<String> selectRoleCodesByAdminId(@Param("adminId") Long adminId);
}
