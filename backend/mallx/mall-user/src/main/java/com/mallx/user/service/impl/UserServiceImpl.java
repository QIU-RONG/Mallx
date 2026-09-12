package com.mallx.user.service.impl;

import com.mallx.user.mapper.UserMapper;
import com.mallx.user.entity.User;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.user.service.UserService;
import org.springframework.stereotype.Service;

@Service
public class UserServiceImpl extends ServiceImpl<UserMapper, User> implements UserService {

}
