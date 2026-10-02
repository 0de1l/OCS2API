# OCS2API

OCS2API 是基于 Flask 的本地题库与 AI 答题服务，为 [OCS](https://github.com/ocsjs/ocsjs) 提供兼容 AnswererWrapper 的搜索接口。Windows 版本提供系统托盘、浏览器管理页面和 PyInstaller 单文件程序，也可从源码或通过 Docker 运行。

项目基于 LynnGuo666 的 [ocsjs-ai-answer-service / EduBrain AI](https://github.com/LynnGuo666/ocsjs-ai-answer-service) 修改。原项目许可证待原作者确认，详见 [第三方与来源说明](THIRD_PARTY_NOTICES.md)。

## 功能与使用边界

- 搜索顺序为本地 JSON 题库、内存缓存、兼容 OpenAI Chat Completions 的上游模型；成功取得的上游答案自动写入题库。
- 支持单选、多选、判断、填空的提示与答案处理；模型答案和多选格式转换仍需人工核对。
- 管理页面支持配置保存、状态统计、日志查看、题库导入/导出/清空、缓存清空和复制 OCS 配置。
- 运行日志在内存中最多保留 300 条，页面每 3 秒读取最近 200 条；重启后清空，不自动生成持久日志文件。
- Windows exe 无需另装 Python，启动时打开浏览器并显示托盘图标。

**仅在本机可信环境中使用。** 默认 `host` 为 `0.0.0.0`，会监听所有网卡，并不等于仅允许本机访问。可在 `config.json` 中设为 `127.0.0.1` 后重启。当前 CORS 全开，管理接口没有完整鉴权；访问令牌只保护部分接口，不能据此宣称服务可安全暴露到公网。具体覆盖范围见 [API 文档](api_docs.md)。

## Windows exe 使用

1. 将自行构建或由维护者实际发布的 `OCS2API.exe` 放入有写权限的独立目录。构建产物为 `dist/OCS2API.exe`，当前不承诺已有可下载的 Release。
2. 双击程序，浏览器通常会自动打开 `http://127.0.0.1:5000`。首次启动在 exe 同目录生成 `config.json` 和空的 `question_bank.json`。
3. 在设置中填写上游 API Base URL、API Key 和模型名称并保存。默认 Key 为空；没有 Key 时仍可使用已导入的本地题库，未命中题库或缓存的请求会提示配置 Key。
4. 在页面复制 OCS 配置，按下文添加到 OCS。更换端口后必须退出并重启程序，再从新地址打开页面并重新复制配置。

关闭浏览器不会停止服务。右键 Windows 托盘图标可选择“打开控制台”或“停止服务”。停止操作先尝试本机关闭接口，随后强制结束进程；不要在题库导入或配置保存期间退出。单独调用关闭 API 不保证能结束程序。

升级时先等待请求与保存完成，再通过托盘停止服务，备份并保留原目录的 `config.json` 和 `question_bank.json`，只替换 exe，然后重新启动。不要用空示例覆盖已有配置和题库；迁移目录时一并移动这两个文件。配置中以明文保存 Key 和令牌，应只留在自己的运行目录。

## 源码安装与启动

推荐 Python 3.12，最低使用 Python 3.10。以下命令均从项目根目录执行。源码桌面启动入口是 `python app.py`，会尝试打开浏览器和系统托盘。

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

若 PowerShell 不允许激活脚本，可直接使用虚拟环境解释器，无需更改全局执行策略：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

无需预先创建 `.env` 即可进入管理页面。源码模式也可参考 `.env.example` 设置 `.env`，或参考 `config.example.json` 创建 `config.json`；不要覆盖已有运行配置。

### Linux 无头运行

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5000 --limit-request-line 16380 app:app
```

无头环境使用 `app:app` 导入 Flask 应用，不启动桌面入口。JSON 题库没有跨进程同步，缓存和计数也在进程内，必须保持单 worker，并避免多个服务实例同时写同一个题库。Gunicorn 的监听地址和端口由 `--bind` 决定，不由页面的 `port` 设置控制。用 `Ctrl+C` 或所属进程管理器停止服务。

### Docker Compose

Dockerfile 使用 Python 3.12，运行 Gunicorn 单 worker、4 threads。安装 Docker 与 Compose 后，在项目根目录执行：

```bash
docker compose up -d --build
docker compose logs -f
```

打开 `http://127.0.0.1:5000`，直接在页面填写并保存上游配置。无需 `.env`、`env_file` 或预建 JSON 文件。Compose 设置 `OCS2API_DATA_DIR=/data`，将宿主机 `./data` 整个目录挂载到 `/data`：首次启动自动创建空题库，页面保存配置后生成 `data/config.json`，后续数据保留在该目录中。升级容器时备份并保留 `data/`，不要将它提交或加入发行包。

默认映射为 `127.0.0.1:5000:5000`，仅向宿主机回环地址发布端口。要更换宿主机端口，在 `docker-compose.yml` 中将映射改为例如 `127.0.0.1:5001:5000`，再执行 `docker compose up -d`。**容器内部监听端口固定为 5000，修改页面端口设置不会改变 Gunicorn 或 Docker 的端口映射。** 之后应从新地址重新复制 OCS 配置。

用 `docker compose down` 停止服务；此目录挂载的数据不会随容器删除。构建镜像时使用不含真实凭据、题库和备份的源码目录；需挂载整个数据目录，以支持配置和题库的原子文件替换，不应改为逐个文件挂载。

## 配置规则

exe 的配置和题库始终位于 exe 同目录。源码默认位于 `config.py` 所在目录，也可在启动进程前设置系统环境变量 `OCS2API_DATA_DIR` 指向独立数据目录；Docker Compose 已将其设为 `/data`。exe 忽略 `OCS2API_DATA_DIR`。

`OCS2API_DATA_DIR` 在加载 `.env` 之前读取，只认启动时已有的进程环境，不是 `config.json` 字段；不要只把它写入 `.env`。建议使用绝对路径，相对值按进程启动目录解析。改动后需重启，程序不会自动迁移旧数据。

| 运行方式 | 配置优先级，由高到低 |
| --- | --- |
| Windows exe | `config.json` > 内置默认值；不读取 `.env`，也不导入下表中的进程环境配置 |
| 源码 / Gunicorn / Docker | 数据目录的 `config.json` > 项目目录的 `.env` > 进程环境变量 > 内置默认值 |

优先级逐字段合并。已有 `config.json` 的空 Key 也会覆盖环境中的 Key。源码 `.env` 使用覆盖模式加载，因此同名值优先于进程环境变量。页面保存会写入完整配置，之后仅改 `.env` 通常无法覆盖这些已保存字段。

| `config.json` 字段 | 源码环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `host` | `HOST` | `0.0.0.0` | 桌面服务器监听地址；本机使用建议 `127.0.0.1`，修改后重启 |
| `port` | `PORT` | `5000` | 整数，1 至 65535；桌面服务器重启后生效 |
| `openai_api_base` | `OPENAI_API_BASE` | `https://api.openai.com/v1` | 上游 API Base URL，不能为空；兼容服务按其说明填写，通常含 `/v1` |
| `openai_api_key` | `OPENAI_API_KEY` | 空字符串 | 上游 Key，明文保存在本地配置中 |
| `openai_model` | `OPENAI_MODEL` | `gpt-4o-mini` | 由上游支持的模型标识；留空会回退到默认值 |
| `access_token` | `ACCESS_TOKEN` | 空字符串 | 非空时对部分接口启用令牌校验 |
| `log_level` | `LOG_LEVEL` | `INFO` | 如 `DEBUG`、`INFO`、`WARNING`；日志级别在启动时应用 |
| `max_tokens` | `MAX_TOKENS` | `500` | 正整数，传给上游的输出 Token 上限 |
| `temperature` | `TEMPERATURE` | `0.7` | 0 至 2，上游是否支持以其接口为准 |
| `enable_cache` | `ENABLE_CACHE` | `true` | 是否启用进程内缓存，不控制本地题库读写 |
| `cache_expiration` | `CACHE_EXPIRATION` | `86400` | 正整数，内存缓存有效秒数，不使持久题库过期 |

JSON 布尔值使用 `true` / `false`；环境值 `1`、`true`、`yes`、`on`（忽略大小写和首尾空白）会启用缓存，其他字符串为关闭。

页面或配置 API 保存成功后会重建上游客户端和内存缓存，已有缓存随之清空；题库不会清空。上游与缓存设置、访问令牌立即应用，桌面监听的 `host`、`port` 和日志级别需重启。直接编辑配置文件也需要重启加载。页面未提供所有字段的输入框，可停机编辑配置文件或使用 [配置 API](api_docs.md#配置)。Key 和令牌输入框留空表示保留；显式清除方式见 API 文档。

## 本地题库

`question_bank.json` 使用 UTF-8 JSON，导出格式为数组。以下是可导入的合成示例：

```json
[
  {
    "question": "1 + 1 等于多少？",
    "type": "single",
    "options": "A. 1\nB. 2\nC. 3",
    "answer": "2"
  },
  {
    "question": "水的化学式是 H2O。",
    "type": "judgement",
    "options": "",
    "answer": "正确"
  }
]
```

题库和搜索缓存均按“题目 + 题型 + 选项”匹配；搜索先对三个字段分别执行 `strip()`，只去掉首尾空白。内部空格、换行、标点、大小写和选项顺序均不做归一化；空题型或空选项不是通配符。页面的简单测试只提交题目，不能据此判断带题型、选项的记录是否能命中。

导入也接受 `{"questions": [...]}`，以及兼容形式 `{"records": [...]}`；单次最多 10000 条。同一匹配键覆盖答案，缺少题目或答案的记录跳过。持久文件建议保持导出数组格式，直接编辑后需重启。清空内存缓存不会删除题库，清空题库也不会同时清空内存缓存；如需让已有问题重新请求上游，两处都需清除，并先备份题库。

## 接入 OCS

在管理页面复制配置，粘贴到 OCS 的自定义题库配置。以下示例用于 OCS 和服务运行在同一台机器的情况：

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
      "options": "${options}"
    },
    "handler": "return (res)=> res.code === 1 ? [res.question, res.answer] : [res.msg, undefined]"
  }
]
```

**当前一键复制不包含访问令牌。** 如果配置了 `access_token`，须自行在上面对象的 `data` 中加入 `token`，例如替换为：

```json
{
  "title": "${title}",
  "type": "${type}",
  "options": "${options}",
  "token": "REPLACE_WITH_YOUR_ACCESS_TOKEN"
}
```

GET 模式下 `data.token` 作为查询参数发送。其他客户端可使用 `X-Access-Token` 请求头；把令牌放在 POST JSON 请求体中不会通过校验。不要分享含真实令牌的配置。复制的 URL 来自当前访问页面的主机和端口；更改端口并重启后，应从新地址重新获取。若 OCS 脚本管理器提示连接权限，允许其访问对应的本机地址。

完整请求参数、响应、错误状态和管理接口见 [API 文档](api_docs.md)。

## 测试与构建

在 Windows 上使用虚拟环境执行：

```powershell
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python scripts/check_release.py
.\build_exe.ps1
python scripts/smoke_exe.py
```

`tests/test_service.py` 等 unittest 测试离线运行，不调用真实上游。另有针对已启动服务的健康 smoke 检查，只访问 `/api/health`，不会调用模型或产生上游费用：

```powershell
python scripts/smoke_service.py --url http://127.0.0.1:5000
```

`build_exe.ps1` 使用 `OCS2API.spec`，生成 `dist/OCS2API.exe`，图标由 `logo.png` 转换。默认 Key 与访问令牌为空，spec 仅包含资源白名单，不应打包 `.env`、运行配置或个人题库。`check_release.py` 通过 `git ls-files` 检查源码；新文件需先纳入暂存清单才能完整检查。`smoke_exe.py` 在临时目录启动 exe，验证环境隔离、页面、本地题库和日志，不调用真实上游。托盘菜单与升级流程仍应人工验证；文档变更后须重新构建以包含新版 API 文档。

Windows CI 执行 tests、构建与 exe smoke，只上传 GitHub Actions artifact，不自动创建 GitHub Release。artifact 是工作流构建附件，不能当作已经发布的下载页面；exe 正式分发放入手动创建的 Releases。

## 目录简图

```text
OCS2API/
|-- app.py                    Flask 接口和桌面入口
|-- config.py                 配置优先级、校验和持久化
|-- question_bank.py          JSON 题库
|-- utils.py                  缓存、提示和答案处理
|-- templates/                管理页面
|-- static/                   页面脚本与样式
|-- logo.png                  程序图标源图
|-- config.example.json       空 Key 配置示例
|-- .env.example              源码环境配置示例
|-- requirements.txt          运行依赖
|-- requirements-build.txt    构建依赖
|-- build_exe.ps1             Windows 构建入口
|-- OCS2API.spec              PyInstaller 打包清单
|-- Dockerfile
|-- docker-compose.yml
|-- tests/                    离线 unittest 自动测试
|-- scripts/check_release.py  发布前检查
|-- scripts/smoke_service.py  已运行服务的健康检查
|-- scripts/smoke_exe.py      临时目录中的 exe 冒烟验证
|-- README.md
|-- api_docs.md
|-- THIRD_PARTY_NOTICES.md
|-- config.json               默认数据目录中的运行配置，不入库
|-- question_bank.json        默认数据目录中的题库，不入库
|-- data/                     Compose 的数据目录，不入库
`-- dist/OCS2API.exe           构建生成，不入库
```

## FAQ

### 浏览器关闭后端口仍被占用？

关闭页面不等于关闭服务。用托盘“停止服务”退出，并检查是否重复启动了多个实例。端口被其他程序占用时，停机修改 `config.json` 中的 `port` 后再启动；Docker 应调整 Compose 的宿主机映射端口。

### 改了 `.env`，为什么 Key 或端口没有变化？

exe 不加载 `.env`。源码模式也优先使用 `config.json`，包括其中已保存的空值。通过页面修改，或停机后编辑对应配置；桌面监听端口必须重启才能改变。Docker 内部固定 5000，页面设置不改变容器映射。

### 设置令牌后 OCS 或页面操作返回 403？

OCS 一键复制没有自动带令牌，需自行添加 `data.token`。页面仅在当前浏览器会话中保存所输入的令牌；新会话可能没有它，可在设置中重新输入现有令牌并保存。令牌并未保护全部管理接口。

### 明明有相同题目，却仍然请求模型？

确认题目、题型和选项三个字段都一致。选项顺序、内部换行或标点变化都可能导致未命中。简单测试框未发送题型和选项。

### 清了缓存或换了模型，为什么答案没变？

持久题库优先于缓存和上游，换模型不会使题库答案失效。先导出备份，再修正相关记录；若执行题库清空，需另行清空内存缓存才能完全排除旧答案。

### 健康检查成功，但模型请求失败？

健康接口只说明本地进程能响应，不会验证 Key、模型权限、上游网络或额度。查看页面运行日志和搜索响应中的 `code` / `msg`；业务错误通常仍使用 HTTP 200。多选答案转换只是启发式处理，不保证格式与正确性。

### 可以配置多 worker 或直接开放公网吗？

当前 JSON 题库采用进程内锁，应使用单 worker、单写入实例。管理接口鉴权和 CORS 仍有明确限制，当前使用范围是本机可信环境，不宣称具备公网生产安全性。

## 致谢与许可

保留原项目作者 **LynnGuo666** 与原项目名 **EduBrain AI** 的来源署名，感谢 [原项目](https://github.com/LynnGuo666/ocsjs-ai-answer-service)、[OCS](https://github.com/ocsjs/ocsjs) 及相关开源依赖。上游基准提交为 `08a1fc4e343d8daafbf974c5da8cb7879e0f7c73`。

本地源目录未见 `LICENSE`，该基准提交的 Git tree 未见 `LICENSE`、`COPYING` 或 `NOTICE`；原项目许可证与再分发条件待原作者确认。OCS2API 更名不代表取得授权，不擅自添加 MIT 或其他许可声明。本地整理、测试与构建准备可继续；公开发布前需确认可适用的许可及署名要求。详见 [第三方与来源说明](THIRD_PARTY_NOTICES.md)。
