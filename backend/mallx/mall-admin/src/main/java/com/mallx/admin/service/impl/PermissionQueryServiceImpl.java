package com.mallx.admin.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import com.mallx.admin.entity.Permission;
import com.mallx.admin.mapper.PermissionMapper;
import com.mallx.admin.service.PermissionQueryService;
import com.mallx.admin.vo.PermissionVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 权限只读查询实现（Day 23 骨架）。
 *
 * <p>★ 本类是三个 Service 里唯一<b>没有写方法</b>的 —— 与「permissions 只读」
 * 这个决策一致（Day-23 文档 §一 决策 1）。
 */
@Service
public class PermissionQueryServiceImpl extends ServiceImpl<PermissionMapper, Permission>
        implements PermissionQueryService {

    /**
     * 权限字典（不分页）。
     *
     * <p>实现要点：
     * <ol>
     *   <li>用 {@code LambdaQueryWrapper<Permission>}：
     *       {@code .eq(type != null && !type.isBlank(), Permission::getType, type)}
     *       + {@code .and(keyword != null && !keyword.isBlank(),
     *         w -> w.like(Permission::getName, keyword).or().like(Permission::getCode, keyword))}
     *       + {@code .orderByAsc(Permission::getId)}；
     *       ★ keyword 的<b>包括号</b>：现在只有 type 一个兄弟条件、括不括号结果一样，
     *       但一旦将来加第二个过滤条件，漏括号就是那个老坑
     *       （{@code status=? AND name LIKE ? OR code LIKE ?} ⇒ AND 优先级高于 OR）；</li>
     *   <li>★ <b>不做分页</b>：{@code this.list(wrapper)} 直接拿全部 ——
     *       这是「字典式接口」的刻意选择（与 L5 的 {@code GET /api/admin/brands} 同形状）。
     *       ⚠️ 本接口<b>没有</b> {@code MAX_PAGE_SIZE} 的夹紧，因为它压根不分页 ——
     *       这条性质在验收 F 组里被断言（列表长度 == 全表行数）；
     *       若将来权限过千要改回分页，<b>同步改断言</b>；</li>
     *   <li>出口换壳：逐行 {@code BeanUtils.copyProperties(p, vo)}
     *       （{@link PermissionVO} 比实体少了 {@code parentId} —— 见该 VO 的注释）；</li>
     *   <li>★ 不过滤 {@code status}：停用的权限也要返回（管理端要能看见，
     *       同 {@code RoleVO} 的理由）。</li>
     * </ol>
     */
    @Override
    public List<PermissionVO> list(String type, String keyword) {
        LambdaQueryWrapper<Permission> wrapper = new LambdaQueryWrapper<Permission>()
                .eq(type != null && !type.isBlank(), Permission::getType, type)
                // ★ 包括号：现在只有 type 一个兄弟条件、括不括号结果一样，但一旦加第二个
                //   过滤条件，漏括号就是 status=? AND name LIKE ? OR code LIKE ? 那个老坑。
                .and(keyword != null && !keyword.isBlank(),
                        w -> w.like(Permission::getName, keyword)
                                .or().like(Permission::getCode, keyword))
                .orderByAsc(Permission::getId);

        // ★ 刻意不分页：字典式接口（同 GET /api/admin/brands 的形状）。
        //   代价是「全量返回」，对应验收 F 组「列表长度 == 全表行数」那条断言；
        //   若将来权限过千要改回分页，同步改断言。
        List<PermissionVO> voList = new ArrayList<>();
        for (Permission p : this.list(wrapper)) {
            PermissionVO vo = new PermissionVO();
            BeanUtils.copyProperties(p, vo);
            voList.add(vo);
        }
        // ★ 不过滤 status：停用的权限也要返回（管理端要能看见它，同 RoleVO 的理由）
        return voList;
    }
}
