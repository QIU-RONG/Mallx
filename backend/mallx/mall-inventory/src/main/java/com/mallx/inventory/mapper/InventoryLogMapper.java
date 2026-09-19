package com.mallx.inventory.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.mallx.inventory.entity.InventoryLog;

/**
 * 库存流水 Mapper
 *
 * <p>★ 这里【故意是空的】：流水只有两种操作 —— 「追加一条」（{@code insert}）
 * 和「查出来对账」（{@code selectList}），{@link BaseMapper} 全都提供了。
 * 手写 XML 只在「一条语句要完成判断 + 修改」时才值得（见 {@link InventoryMapper}），
 * 流水没有这种需求，所以不写 XML、也不声明任何方法。
 *
 * <p>⚠️ 一条纪律：流水表<b>只增不改不删</b>。任何时候都不要对 {@code InventoryLog}
 * 调 {@code updateById} / {@code deleteById} —— 账本一旦可改就不再是账本。
 * 排错时请另建临时表或用 SQL 直查，不要动生产数据。
 *
 * <p>不加 {@code @Mapper} 注解：全局 {@code @MapperScan("com.mallx.**.mapper")} 已覆盖本包。
 */
public interface InventoryLogMapper extends BaseMapper<InventoryLog> {
}
