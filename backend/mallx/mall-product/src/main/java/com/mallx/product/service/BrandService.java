package com.mallx.product.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.entity.Brand;
import com.mallx.product.vo.BrandVO;

import java.util.List;

/**
 * 品牌字典（L5，Day 20 补漏）。
 * <p>
 * 【为什么需要它】商品列表 / 详情早就带 {@code brandName}（{@code ProductServiceImpl.fillNames}
 * 用 {@code brandMapper} 反查），所以业务上并不缺能力。缺的是
 * <b>「有哪些品牌」这个字典查询</b> —— 前端做品牌筛选时没有任何可选值来源，
 * 只能遍历商品反推，既不准也漏掉「暂时没有商品」的品牌。
 * <p>
 * ★★ <b>两个方法刻意分开，不是重复</b>：
 * <table border="1">
 *   <tr><th>方法</th><th>口径</th><th>给谁</th></tr>
 *   <tr><td>{@link #listEnabled()}</td><td>只含 status = 1</td><td>C 端（公开）</td></tr>
 *   <tr><td>{@link #listAll()}</td><td>全部（含 status = 0）</td><td>管理端（brand:list）</td></tr>
 * </table>
 * 这与 {@code ProductServiceImpl.getDetail / getAdminDetail} 是<b>同一条教训</b>：
 * 「停用的东西 C 端看不见、管理端必须看得见」—— 因为管理员要把它<b>重新启用</b>，
 * 看不见就无从操作。合成一个方法再传布尔参数（{@code listBrands(boolean forAdmin)}）可读性更差，
 * 且以后再有人加第三个入口时必然传错。
 */
public interface BrandService extends IService<Brand> {

    /** C 端品牌字典：只含【启用】品牌（status = 1），按 id 升序。 */
    List<BrandVO> listEnabled();

    /** 管理端品牌字典：含【全部】品牌（含已停用），按 id 升序。 */
    List<BrandVO> listAll();
}
