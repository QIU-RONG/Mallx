package com.mallx.product.service;

import com.baomidou.mybatisplus.spring.service.IService;
import com.mallx.product.dto.BrandCreateDTO;
import com.mallx.product.dto.BrandUpdateDTO;
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

    // ======================================================================
    // Day 24 · L5②：管理端品牌 CRUD（三个写点）
    // ----------------------------------------------------------------------
    // 【与 listEnabled / listAll 的分工】
    //   上面两个是【读】入口（C 端 / 管理端两套口径），返回 BrandVO；
    //   下面三个是【写】入口，只走管理端。
    //
    // 【三条共同规则】
    //   ① 每个方法都带 @Transactional：存在性/引用「检查」与「写入」之间不能被插队
    //      （否则就是「先查后改」的 TOCTOU，同 CategoryServiceImpl 的三条注释）。
    //   ② name 有 UNIQUE 约束（01-schema.sql:70）⇒ 重名必须翻译成【400 + 人话】，
    //      不能让 23505 冒到兜底 handler 变成 500。
    //   ③ brands 表【没有 is_deleted】⇒ 删除是物理删，与 categories 同族
    //      （对照 products：那张表有软删，所以那边不存在「真删」这个动作）。
    // ======================================================================

    /**
     * 新建品牌，返回新 id。
     *
     * @throws com.mallx.common.exception.BusinessException 名称重复（400）
     */
    Long createBrand(BrandCreateDTO dto);

    /**
     * 修改品牌（局部更新语义：DTO 里没传的字段 = 不动）。
     *
     * @throws com.mallx.common.exception.BusinessException 品牌不存在（404）/ 名称重复（400）
     */
    void updateBrand(Long id, BrandUpdateDTO dto);

    /**
     * 删除品牌（物理删，删前判「还有没有商品引用它」—— 含已软删商品）。
     *
     * @throws com.mallx.common.exception.BusinessException 品牌不存在（404）/ 有商品引用（400）
     */
    void deleteBrand(Long id);
}
