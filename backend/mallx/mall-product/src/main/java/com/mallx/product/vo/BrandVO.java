package com.mallx.product.vo;

import lombok.Data;

/**
 * 品牌字典项（L5，Day 20 补漏）。
 * <p>
 * ★ 只是【字典】：id +展示字段 + status。故意<b>不</b>带 createdAt / updatedAt ——
 * 前端做品牌筛选只需要「有哪些品牌」，时间戳在这里是噪声。
 * <p>
 * ★ 也<b>不</b>带 productCount（该品牌下有多少商品）：
 * 那是一个会随商品增删变化的统计值，一旦塞进字典，前端就会拿它当缓存 key 用，
 * 而字典本身没有失效机制 ⇒ 必然出现「品牌显示 0 个商品但点进去有货」。
 * 要统计另行开接口（口径还得跟 @TableLogic 对齐，见 ProductMapper#countByCategoryId 的教训）。
 */
@Data
public class BrandVO {

    private Long id;

    private String name;

    private String logo;

    private String description;

    /** 1 = 启用，0 = 停用。C 端只返回 1；管理端两个都返回（停用的要能重新启用）。 */
    private Integer status;
}
