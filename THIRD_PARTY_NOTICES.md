# 第三方与来源说明

[README](README.md) · [API 文档](api_docs.md)

## 原项目

OCS2API 基于 [ocsjs-ai-answer-service](https://github.com/LynnGuo666/ocsjs-ai-answer-service) 修改，保留原作者 **LynnGuo666** 和原 README 项目名 **EduBrain AI** 的来源署名。更名不表示全部代码、界面与素材均为后续维护者原创，也不代表原作者为后续修改背书。

上游基准 HEAD 为 `08a1fc4e343d8daafbf974c5da8cb7879e0f7c73`。该提交的 Git tree 未见 `LICENSE`、`COPYING` 或 `NOTICE`，本地源目录也未见 `LICENSE`。这一记录不等于对上游所有历史版本的许可认定。

## 许可证待确认

原项目许可证、修改与再分发条件待原作者确认。仓库可访问、保留署名或更名均不自动构成授权；OCS2API 不擅自添加 MIT 或其他许可证，不宣称已经获得原作者许可。

本地文档整理、测试与构建准备可以继续。公开发布源码、exe、容器镜像或素材前，应确认适用许可与署名要求，并按实际结果补充相应文件。

## 依赖来源

以下为主要依赖及相关项目索引，不是完整依赖清单或逐项许可核验。实际版本以构建环境为准，各依赖按其自身许可证使用，不能以依赖许可替代原项目许可。

| 项目 | 用途 | 来源 |
| --- | --- | --- |
| Flask | Web 应用与接口 | <https://github.com/pallets/flask> |
| Werkzeug | HTTP 服务工具 | <https://github.com/pallets/werkzeug> |
| Flask-CORS | 跨域响应 | <https://github.com/corydolphin/flask-cors> |
| python-dotenv | 源码环境配置 | <https://github.com/theskumar/python-dotenv> |
| OpenAI Python SDK | 兼容接口客户端 | <https://github.com/openai/openai-python> |
| Gunicorn | Linux / 容器 WSGI 服务 | <https://github.com/benoitc/gunicorn> |
| pystray | 系统托盘 | <https://github.com/moses-palmer/pystray> |
| Pillow | 图像与图标处理 | <https://github.com/python-pillow/Pillow> |
| PyInstaller | Windows 程序打包 | <https://github.com/pyinstaller/pyinstaller> |
| Python | 运行时 | <https://www.python.org/> |
| OCS | 兼容客户端生态 | <https://github.com/ocsjs/ocsjs> |

二进制分发需按实际包含的 Python 运行时、直接与间接依赖，保留或附带其要求的版权和许可文本，并核对打包工具适用于输出程序的条款。本文件不能替代原始许可材料。

## 图标与用户数据

`logo.png` 用于界面、托盘和构建图标；本地材料未提供独立的素材许可确认，应与代码来源一并核实，不默认视为公有领域。

文档题库示例是合成数据。个人配置、导入题库、生成答案和运行日志不随源码或发行包分发。上游模型服务仍适用实际提供方的服务条款；接口兼容不代表获得服务方或 OCS 的背书。
