# OCS2API API 文档

[README](README.md) · [来源与许可](THIRD_PARTY_NOTICES.md)

默认本机地址为 `http://127.0.0.1:5000`。桌面端口变更需重启；Gunicorn 以启动参数为准，Docker 内部固定 5000，宿主机端口在 Compose 映射中调整。

## 访问令牌与限制

默认监听 `0.0.0.0`，CORS 全开，管理接口没有完整鉴权。仅在本机可信环境使用，可将桌面配置 `host` 改为 `127.0.0.1` 后重启。令牌不是全站登录或公网安全保障。

当 `access_token` 非空时，下表标记“是”的接口接受 `X-Access-Token: REPLACE_WITH_YOUR_ACCESS_TOKEN` 请求头，或 URL 查询参数 `?token=REPLACE_WITH_YOUR_ACCESS_TOKEN`。非空请求头优先；JSON / 表单请求体中的 `token` 和 Bearer 认证不被识别。未配置令牌时不要求此校验。

| 方法 | 路径 | 校验已配置的令牌 | 说明 |
| --- | --- | --- | --- |
| GET / POST | `/api/search` | 是 | 搜索题目 |
| GET | `/api/health`、`/api/status` | 否 | 健康与状态 |
| GET | `/api/stats` | 是 | 同一状态结构 |
| GET | `/api/config` | 否 | 读取公开配置 |
| PUT / POST | `/api/config` | 否 | 保存配置 |
| GET | `/api/logs` | 否 | 内存日志 |
| POST | `/api/logs/clear` | 否 | 清空日志 |
| POST | `/api/cache/clear` | 是 | 清空内存缓存 |
| GET | `/api/question-bank` | 否 | 读取完整题库 |
| POST | `/api/question-bank/import` | 是 | 合并导入题库 |
| GET | `/api/question-bank/export` | 否 | 下载题库 JSON |
| POST | `/api/question-bank/clear` | 是 | 清空持久题库 |
| GET | `/api/ocs-config` | 否 | 生成不含令牌的 OCS 配置 |
| POST | `/api/shutdown` | 是，且限制本机来源 | 尝试关闭服务 |
| GET | `/`、`/dashboard`、`/docs` | 否 | 管理页面或 API 文档文本 |

令牌无效返回 HTTP 403：

```json
{"code": 0, "msg": "访问令牌无效"}
```

## 搜索

`GET /api/search` 使用查询参数；`POST /api/search` 接受 JSON 对象或表单，JSON 字段优先。JSON 请求使用 `Content-Type: application/json`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 题目，去除首尾空白后不能为空 |
| `type` | string | 否 | `single` 单选、`multiple` 多选、`judgement` 判断、`completion` 填空；默认空 |
| `options` | string | 否 | 原始选项文本；默认空 |

POST 请求体示例：

```json
{"title": "1 + 1 等于多少？", "type": "single", "options": "A. 1\nB. 2\nC. 3"}
```

成功响应为 HTTP 200：

```json
{"code": 1, "question": "1 + 1 等于多少？", "answer": "2"}
```

顺序为本地题库、内存缓存、上游模型。题目、题型和选项分别执行 `strip()` 后完全匹配，不归一化内部空格、换行、标点、大小写或选项顺序，空字段不是通配符。上游答案成功后写入题库，并在启用时写入缓存；本地命中不要求 Key。多选上游答案仅做启发式 `#` 分隔处理，不保证格式和正确性；本地题库答案按存储值返回。

| 情况 | HTTP 状态 | 响应 |
| --- | --- | --- |
| 题目为空 | 200 | `{"code":0,"msg":"未提供题目内容"}` |
| 未命中且未配置 Key | 200 | `{"code":0,"msg":"请先在设置中配置上游 API Key"}` |
| 上游或处理异常 | 200 | `{"code":0,"msg":"发生错误: ..."}` |
| 令牌无效 | 403 | `{"code":0,"msg":"访问令牌无效"}` |

调用方必须检查 `code`，不能只检查 HTTP 状态。接口没有为所有非法输入或内部异常提供统一错误结构。

## 健康与统计

`GET /api/health`、`GET /api/status`、`GET /api/stats` 返回同一结构，仅 `/api/stats` 校验令牌。示例：

```json
{
  "status": "ok",
  "uptime": 12.3,
  "version": "2.0.0",
  "model": "gpt-4o-mini",
  "upstream_url": "https://api.openai.com/v1",
  "api_key_configured": false,
  "cache_enabled": true,
  "cache_size": 0,
  "question_bank_size": 0,
  "qa_records_count": 0,
  "counters": {
    "requests": 0,
    "local_hits": 0,
    "cache_hits": 0,
    "upstream_requests": 0,
    "errors": 0
  },
  "port": 5000
}
```

`uptime` 是进程运行秒数。问答记录上限 100；计数、日志和缓存均在进程内，重启后丢失。`requests` 包括令牌错误等搜索请求，`upstream_requests` 包括失败的上游调用，`errors` 仅统计搜索捕获的异常，不等于全部业务拒绝。过期缓存按访问检查，`cache_size` 不保证全是有效项。

健康检查不调用上游，不验证 Key、额度或模型可用性。`port` 是当前配置值，可能与尚未重启的桌面监听端口或 Gunicorn 实际绑定不同。版本示例不表示已经发布 Release。

## 配置

`GET /api/config` 无令牌校验。返回 `host`、`port`、`openai_api_base`、`openai_model`、`max_tokens`、`temperature`、`enable_cache`、`cache_expiration`，以及：

| 字段 | 含义 |
| --- | --- |
| `api_key_configured` | 是否配置 Key |
| `api_key_masked` | 掩码及 Key 最后四个字符，未配置时为空 |
| `access_token_enabled` | 是否配置访问令牌 |
| `config_path`、`question_bank_path` | 当前实例的数据路径 |

不返回完整 Key、令牌或 `log_level`。路径和部分 Key 信息仍会暴露，不应公开此接口。

`PUT /api/config` 或 `POST /api/config` 接受 JSON 对象，当前也无令牌校验。可写字段及默认值见 [README 配置表](README.md#配置规则)，未提交的字段保留，未知字段忽略。示例：

```json
{"host": "127.0.0.1", "port": 5001, "enable_cache": true}
```

`openai_api_key`、`access_token` 留空或省略表示保留。显式清除使用布尔字段，清除标志优先于同次提交的新值：

```json
{"clear_api_key": true, "clear_access_token": true}
```

成功返回 `success: true`、`message`、`restart_required` 与 `config`；后者与 GET 结构相同。保存会持久化配置并重建客户端和缓存，因此原缓存被清空，题库保留。上游、令牌与缓存参数即时应用；桌面监听地址、端口和日志级别需重启。`restart_required` 只比较端口，修改 `host` 或 `log_level` 时即使为 `false` 也需重启。Docker 页面端口不控制容器映射。

非对象或校验失败返回 HTTP 400，其他保存或客户端初始化异常返回 HTTP 500，结构为 `{"success":false,"message":"..."}`。配置先保存再初始化客户端，失败响应不保证回滚，应读取配置核对。

exe 只读取同目录配置，不读取 `.env` 或运行环境中的配置值。源码优先级是 `config.json` > 项目 `.env` > 环境变量 > 默认；源码数据目录可由启动时的系统环境变量 `OCS2API_DATA_DIR` 指定，exe 忽略它。详见 [README](README.md#配置规则)。

## 日志与缓存

`GET /api/logs?limit=200` 返回最近日志，按旧到新排列。`limit` 默认 200，整数限制在 1 至 300，不能转换时回退到 200：

```json
{"logs": [{"time": "12:34:56", "level": "INFO", "message": "运行日志已清空"}], "total": 1}
```

`total` 是本次返回数量。内存最多保留 300 条，页面每 3 秒取最近 200 条，没有持久日志文件保证。

`POST /api/logs/clear` 返回 `{"success":true,"message":"运行日志已清空"}`。清空后追加一条清空操作日志。以上日志接口均不校验令牌。

`POST /api/cache/clear` 校验已配置的令牌。启用时返回 `{"success":true,"message":"缓存已清除"}`；未启用时返回 `{"success":false,"message":"缓存未启用"}`，两者均为 HTTP 200。它不删除题库；题库优先级更高且不会随缓存过期。

## 题库

`GET /api/question-bank` 无令牌校验，返回全部记录，无分页：

```json
{
  "questions": [
    {"question": "1 + 1 等于多少？", "type": "single", "options": "A. 1\nB. 2\nC. 3", "answer": "2"}
  ],
  "total": 1
}
```

`GET /api/question-bank/export` 无令牌校验，以 `application/json` 附件下载 `question_bank.json`，内容是上述 `questions` 数组本身。

`POST /api/question-bank/import` 校验已配置的令牌，以 JSON 文本发送数组、`{"questions":[...]}` 或兼容的 `{"records":[...]}`，不是 multipart 上传。有 `questions` 时优先使用；对象缺少这两个键会按空数组处理。

每条的 `question`（兼容 `title`）与 `answer` 必须非空，`question` 优先于 `title`；`type`、`options` 默认空。字段转为文本并去首尾空白，非对象及缺题目/答案的条目跳过。单次最多 10000 条，按题目、题型、选项合并，同键覆盖答案，批次中后项覆盖前项。

```json
{"success": true, "imported": 1, "skipped": 0, "total": 1}
```

`imported` 是有效处理条目数，包含覆盖和重复，不等于新增数；`skipped` 为跳过数，`total` 为最终总条数。验证错误返回 HTTP 400 的 `success: false` 与 `message`；写入错误等可能返回 HTTP 500。导入会持久化题库但不清缓存。持久文件建议使用导出数组格式，直接编辑后需重启；`records` 包装只用于导入兼容。

`POST /api/question-bank/clear` 校验已配置的令牌，返回 `{"success":true,"message":"本地题库已清空"}`，并将持久题库写为空数组。接口没有撤销步骤，应先导出备份。它不清内存缓存；要排除所有旧答案，还需清理缓存。

## OCS 配置

`GET /api/ocs-config` 返回配置数组，URL 取自请求的主机和端口。当前接口和页面一键复制都不含令牌。启用令牌时，手动在 GET 配置的 `data` 中加入 `token`：

```json
[
  {
    "name": "OCS2API",
    "url": "http://127.0.0.1:5000/api/search",
    "method": "get",
    "contentType": "json",
    "data": {
      "title": "${title}",
      "type": "${type}",
      "options": "${options}",
      "token": "REPLACE_WITH_YOUR_ACCESS_TOKEN"
    },
    "handler": "return (res)=> res.code === 1 ? [res.question, res.answer] : [res.msg, undefined]"
  }
]
```

未启用时删除 `token` 即可；`name` 可自定义。端口变更后从新地址重新获取配置，不分享含真实令牌的内容。

## 关闭服务

`POST /api/shutdown` 校验已配置的令牌，并限制来源。当前实现认可 `127.0.0.1`、`::1` 和无来源地址的内部请求。

| 情况 | HTTP 状态 | 响应 |
| --- | --- | --- |
| 非本机来源 | 403 | `{"success":false,"message":"仅允许本机关闭服务"}` |
| 无服务器关闭钩子 | 503 | `{"success":false,"message":"当前服务器不支持关闭操作"}` |
| 存在关闭钩子 | 200 | `{"success":true,"message":"服务正在停止"}` |

令牌错误仍返回 HTTP 403 的 `code: 0` 结构。现代 Werkzeug 或 Gunicorn 可能没有关闭钩子，API 不保证退出进程。Windows 托盘先尝试接口，随后停止托盘并强制退出；应等待保存、导入和请求完成。无头服务用终端或进程管理器停止，Compose 使用 `docker compose down`。
