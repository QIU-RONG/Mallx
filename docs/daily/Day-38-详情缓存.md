# Day 38 · 商品详情 cache-aside —— 代次键失效 + 毒性注入对照组

> D37 把 Redis 管道接通后，D38 回答缓存的核心三问：**缓存什么、什么时候失效、
> 失效失败怎么办**。全部实现落在 `mall-product/cache/CatalogCache`，业务代码只多两行。

## 一、脏读课题的结论（开工前的疑问，答案比预想干净）

预想中的难点是「详情含实时库存，缓存会有脏读窗口」。读代码后发现：
**`SkuVO` 从设计上就不含 stock**——详情响应 = 商品 + 分类名/品牌名（冗余）+ SKU 价格属性 + 图集，
全是目录数据。库存属于 mall-inventory 的独立上下文，从不出现在详情里。

⇒ 失效点只剩**目录写**，而且是一族（9 个方法）：
商品 create/update/delete ×1 组、分类 ×1 组、品牌 ×1 组——
**detail 内嵌了 categoryName/brandName，分类/品牌改名同样致脏**。

## 二、代次键失效（本日核心设计）

| 方案 | 问题 |
|---|---|
| 逐键删除 | 要维护「哪些详情缓存属于这个分类」的反向索引 |
| SCAN/KEYS 匹配删 | O(N) 全库扫描 |
| **代次键 ✅** | 一个计数器：目录写 `INCR mallx:catalog:gen`，读路径用 `v{gen}:{id}` 拼 key——**旧代次一次性整批失活**，旧 key 留到 TTL（30min+0~300s 抖动）自然过期 |

`bump()` 放在事务方法末尾（commit 前一瞬间）：回滚后多 bump 一次只是多一轮 miss，方向安全。
bump 失败（Redis 挂）只影响失效及时性（旧缓存活到 TTL），日志 warn 留痕对账。

## 三、降级纪律

CatalogCache 所有 Redis 操作吞异常：`readDetail` 失败/坏 JSON → 返回 null 回源；
`writeDetail` 失败 → 静默放弃；`generation()` 失败 → 返回 "0"。
**缓存永远不能把业务打挂**，代价只是多查一次库。

## 四、踩坑

- **Boot 4.1 的 Jackson 是 3.x**（`tools.jackson.databind.ObjectMapper`）——
  注入 `com.fasterxml` 版 ObjectMapper 直接启动失败（第一轮冒烟抓到）。
  CatalogCache 自建裸 ObjectMapper + 关 `FAIL_ON_UNKNOWN_PROPERTIES`。
- **软删商品会永久堵死分类删除**：`countByCategoryId`（含已软删口径）> 0 ⇒ API 删不掉
  验收夹具的分类 ⇒ 脚本按 day26 先例用 **psql 物理清理**
  （inventories → product_skus → product_images → products → categories → brands；
  inventory_logs.sku_id 无 FK，链路安全）。
- **Redis 重启（无持久化）gen 计数器清零** ⇒ 可能与历史代次撞号（旧 key 复活）。
  缓解 = 旧 key TTL ≤30min 自愈 + 目录写低频；根治（RDB/AOF 或 bump 后强校验）留给 D40。

## 五、验收（`day38-redis-detail-verify.py`，25/25）

1. **miss→回源→回填**：首次 GET 后 `mallx:cache:product:detail:v{gen}:{id}` 必须存在；
2. **命中**：二次 GET 与首次 data 逐字节一致；
3. **★ 对照组（毒性注入）**：直接覆写缓存里的 name 为毒值 → GET 必须读到毒值——
   若实现错成「永远读库」，这条必挂（护栏有分辨力，不只是"跑通"）；
4. **双失效路径**：商品改名 + 分类改名（B 型脏点）都让 gen+1、读到新数据；
5. **降级**：docker stop redis 后 GET 仍 200 且数据正确；
6. **删除失效**：软删后 C 端 404 伪装，缓存没有复活它；
7. 夹具 psql 物理清理，高水位归零。

CI（f839584，run 36233377910）**success** —— 带 redis 拓扑的全链回归绿。

## 六、下一步（D39）

分类树 `/api/categories/tree` 与品牌列表 `/api/brands` 缓存：同一 CatalogCache 模式
（代次键天然覆盖——它们的写点就是 detail 的失效点，**一次失效两层受益**）。
