# Apifox 测试指南

## 文件

| 文件 | 用途 |
|---|---|
| `apifox-collection.json` | **Postman Collection v2.1** 格式，7 个文件夹 / 34 个请求，带断言脚本与变量 |
| `apifox-env.json` | 环境变量（baseUrl + 三个 token 占位） |
| `openapi.json` | 后端实时导出的 OpenAPI 3 规范（也可以直接导入，但只有接口、没有断言与登录脚本） |

## 导入

Apifox → 项目 → **导入数据** → 选择 **Postman**（或「OpenAPI/Swagger」）：

1. 导入 `apifox-collection.json`，会自动生成同名集合；
2. 导入 `apifox-env.json` 作为环境，或在「环境管理」里手动加 `baseUrl`；
3. 后端地址默认 `http://localhost:8080`（IDEA 里跑的端口）。如果跑在 8081，把 `baseUrl` 改掉即可。

## 跑的顺序

**先跑 `01 认证`**，三个登录请求会把 token 写进集合变量：

- `userToken` ← demo / demo123
- `adminToken` ← admin / admin123
- `merchantToken` ← merchant / merchant123

然后按 02 → 07 顺序跑。依赖说明：

- `03 购物车 → 下单 → 支付`：「查看购物车」会把 `cartItemId` 写进变量，后面的勾选请求用它；
  「提交订单」把返回数组的第一张写入 `orderId`，批量支付用它；
- 默认变量：`productId=1`、`skuId=1`、`shopId=1`、`addressId=1`（对应种子数据；数据重建后 id 仍是这些）。

## 断言约定

- 本项目业务失败是 **HTTP 200 + body.code**：脚本先断言 HTTP 200，再断言 `body.code === 200`；
- `商户：尝试看别家商品` 是**反向用例**，期望 `body.code === 404`（已单独处理，不套用 code=200）；
- 每个请求都有基础断言，能直接看「哪一条红了」。

## 不包含

- **SSE 流式接口** `/api/ai/chat/stream`：Apifox 对 `text/event-stream` 展示有限，建议用 curl；
- **图片上传**（multipart）：在 Apifox 里手动建一个 multipart 请求即可，字段名 `file`；
- **管理端增删改**：集合以「读 + 一条新建券」为主，避免反复跑脏数据；需要时按 Swagger 里的 DTO 补。
