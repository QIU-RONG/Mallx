package com.mallx.ai.dto;

import jakarta.validation.constraints.Size;
import lombok.Data;

/** 一轮对话（只用于回传历史） */
@Data
public class ChatTurn {

    /** 服务端只认 user / assistant，其它值在服务层被丢弃 */
    private String role;

    @Size(max = 2000, message = "单条历史最长 2000 字")
    private String content;
}
