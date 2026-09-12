package com.mallx.user.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.mallx.common.api.PageResult;
import com.mallx.common.api.Result;
import com.mallx.common.api.ResultCode;
import com.mallx.common.exception.BusinessException;
import com.mallx.user.entity.User;
import com.mallx.user.service.UserService;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
public class UserController {

    /**
     * 用户服务
     */

    private final UserService userService;

    public UserController(UserService userService){
        this.userService = userService;
    }

    @PostMapping
    public Result<Long> create(@RequestBody User user) {
      userService.save(user);
      return Result.ok(user.getId());
    }

    @GetMapping("/{id}")
    public Result<User> getUserById(@PathVariable Long id) {
        User user = userService.getById(id);
        if(user == null ){
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(),"用户不存在");
        }
      return Result.ok(user);
    }

    @GetMapping
    public Result<PageResult<User>> page
            (@RequestParam(defaultValue = "1") long current ,
             @RequestParam(defaultValue = "10") long size){

        Page<User> page = userService.page(new Page<>(current,size));
        return Result.ok(PageResult.of(page));
    }

    @DeleteMapping("/{id}")
    public Result<Void> delete(@PathVariable Long id) {
        userService.removeById(id);
        return Result.ok();
    }

    @PutMapping("/{id}/nickname")
    public Result<User> updateNickname(@PathVariable Long id,@RequestBody String nickname) {
        User user = userService.getById(id);
        if(user == null ){
            throw new BusinessException(ResultCode.NOT_FOUND.getCode(),"用户不存在");
        }
        user.setNickname(nickname);
        userService.updateById(user);
        return Result.ok(user);
    }


}
