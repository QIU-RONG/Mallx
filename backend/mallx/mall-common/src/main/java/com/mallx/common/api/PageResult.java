package com.mallx.common.api;

import com.baomidou.mybatisplus.core.metadata.IPage;
import lombok.Data;
import java.util.List;


@Data
public class PageResult<T> {
    public List<T> records;
    private long total;        // 总共有多少条
    private long current;      // 当前第几页
    private long size;

    public static <T> PageResult<T> of(IPage<T> page){
        PageResult<T>  r = new PageResult<>();
        r.setRecords(page.getRecords());
        r.setTotal(page.getTotal());
        r.setCurrent(page.getCurrent());
        r.setSize(page.getSize());
        return r;
    }
}
