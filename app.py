# -*- coding: utf-8 -*-
"""OCS2API: OCS-compatible AI answer service and local management UI."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import openai
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from werkzeug.serving import run_simple

from config import Config, QUESTION_BANK_PATH
from question_bank import QuestionBank
from utils import SimpleCache, extract_answer, format_answer_for_ocs, parse_question_and_options


logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ai_answer_service")
runtime_logs = deque(maxlen=300)
runtime_log_lock = threading.Lock()


def append_runtime_log(message: str, level: str = "INFO") -> None:
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level.upper(),
        "message": str(message),
    }
    with runtime_log_lock:
        runtime_logs.append(entry)


class RuntimeLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            append_runtime_log(record.getMessage(), record.levelname)
        except Exception:
            self.handleError(record)


runtime_log_handler = RuntimeLogHandler()
logging.getLogger().addHandler(runtime_log_handler)

RESOURCE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "static"),
)
CORS(app)

MAX_RECORDS = 100
qa_records: list[Dict[str, Any]] = []
start_time = time.time()
question_bank = QuestionBank(QUESTION_BANK_PATH)
cache: Optional[SimpleCache] = None
client: Optional[openai.OpenAI] = None
metrics = {
    "requests": 0,
    "local_hits": 0,
    "cache_hits": 0,
    "upstream_requests": 0,
    "errors": 0,
}
metrics_lock = threading.Lock()


def initialize_runtime() -> None:
    global cache, client
    cache = SimpleCache(Config.CACHE_EXPIRATION) if Config.ENABLE_CACHE else None
    client = None
    if Config.api_key():
        client = openai.OpenAI(api_key=Config.api_key(), base_url=Config.OPENAI_API_BASE)


initialize_runtime()
logger.info("服务初始化完成，题库已加载 %d 条记录", len(question_bank.records))


def tray_image():
    """Load the bundled logo for the Windows notification area."""
    from PIL import Image

    return Image.open(RESOURCE_DIR / "logo.png").convert("RGBA")


def stop_from_tray(icon) -> None:
    """Ask Flask to stop, then guarantee the standalone process exits."""
    try:
        url = f"http://127.0.0.1:{Config.PORT}/api/shutdown"
        request = urllib.request.Request(url, method="POST")
        if Config.ACCESS_TOKEN:
            request.add_header("X-Access-Token", Config.ACCESS_TOKEN)
        urllib.request.urlopen(request, timeout=2).read()
    except (OSError, urllib.error.URLError):
        logger.warning("服务关闭接口不可用，执行强制退出")
    finally:
        icon.stop()
        os._exit(0)


def open_from_tray(_icon, _item) -> None:
    open_local_ui()


def run_tray() -> None:
    """Run the notification-area icon without blocking Flask."""
    try:
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("打开控制台", open_from_tray, default=True),
            pystray.MenuItem("停止服务", lambda icon, _item: stop_from_tray(icon)),
        )
        icon = pystray.Icon("OCS2API", tray_image(), "OCS2API - AI 智能题库", menu)
        icon.run()
    except Exception:
        logger.exception("系统托盘启动失败")


def increment_metric(name: str) -> None:
    with metrics_lock:
        metrics[name] += 1


def verify_access_token() -> bool:
    if not Config.ACCESS_TOKEN:
        return True
    token = request.headers.get("X-Access-Token") or request.args.get("token")
    return bool(token and token == Config.ACCESS_TOKEN)


def auth_error():
    return jsonify({"code": 0, "msg": "访问令牌无效"}), 403


def record_qa(question: str, question_type: str, options: str, answer: str, source: str) -> None:
    current_time = datetime.now()
    qa_records.append(
        {
            "time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": current_time.isoformat(),
            "question": question,
            "type": question_type,
            "options": options,
            "answer": answer,
            "source": source,
        }
    )
    if len(qa_records) > MAX_RECORDS:
        qa_records.pop(0)


def current_status() -> Dict[str, Any]:
    with metrics_lock:
        counters = dict(metrics)
    return {
        "status": "ok",
        "uptime": round(time.time() - start_time, 1),
        "version": "2.0.0",
        "model": Config.OPENAI_MODEL,
        "upstream_url": Config.OPENAI_API_BASE,
        "api_key_configured": bool(Config.api_key()),
        "cache_enabled": Config.ENABLE_CACHE,
        "cache_size": len(cache.cache) if cache else 0,
        "question_bank_size": len(question_bank.records),
        "qa_records_count": len(qa_records),
        "counters": counters,
        "port": Config.PORT,
    }


@app.route("/api/search", methods=["GET", "POST"])
def search():
    """Handle the OCS AnswererWrapper-compatible question request."""
    increment_metric("requests")
    if not verify_access_token():
        return auth_error()

    try:
        if request.method == "GET":
            question = request.args.get("title", "")
            question_type = request.args.get("type", "")
            options = request.args.get("options", "")
        else:
            data = request.get_json(silent=True) or {}
            question = data.get("title", request.form.get("title", ""))
            question_type = data.get("type", request.form.get("type", ""))
            options = data.get("options", request.form.get("options", ""))

        question = str(question or "").strip()
        question_type = str(question_type or "").strip()
        options = str(options or "").strip()
        if not question:
            return jsonify({"code": 0, "msg": "未提供题目内容"})

        local_answer = question_bank.find(question, question_type, options)
        if local_answer is not None:
            increment_metric("local_hits")
            logger.info("本地题库命中: %s", question[:80])
            record_qa(question, question_type, options, local_answer, "本地题库")
            return jsonify(format_answer_for_ocs(question, local_answer))

        if cache:
            cached_answer = cache.get(question, question_type, options)
            if cached_answer:
                increment_metric("cache_hits")
                logger.info("内存缓存命中: %s", question[:80])
                record_qa(question, question_type, options, cached_answer, "内存缓存")
                return jsonify(format_answer_for_ocs(question, cached_answer))

        if client is None:
            logger.warning("请求被拒绝：尚未配置上游 API Key")
            return jsonify({"code": 0, "msg": "请先在设置中配置上游 API Key"})

        prompt = parse_question_and_options(question, options, question_type)
        increment_metric("upstream_requests")
        logger.info("调用上游模型 %s: %s", Config.OPENAI_MODEL, question[:80])
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            temperature=Config.TEMPERATURE,
            max_tokens=Config.MAX_TOKENS,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的考试答题助手。请直接给出答案，不要解释。"
                        "单选题只返回选项内容；多选题使用#分隔；判断题返回正确或错误；"
                        "填空题直接返回答案。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        ai_answer = (response.choices[0].message.content or "").strip()
        if not ai_answer:
            raise RuntimeError("上游模型返回了空答案")
        processed_answer = extract_answer(ai_answer, question_type)

        if cache:
            cache.set(question, processed_answer, question_type, options)
        question_bank.upsert(question, question_type, options, processed_answer)
        record_qa(question, question_type, options, processed_answer, "上游模型")
        logger.info("上游模型回答完成: %s", question[:80])
        return jsonify(format_answer_for_ocs(question, processed_answer))
    except Exception as exc:
        increment_metric("errors")
        logger.exception("处理题目时发生错误")
        return jsonify({"code": 0, "msg": f"发生错误: {exc}"})


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify(current_status())


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    """Stop only when called locally by the tray process."""
    if request.remote_addr not in {None, "127.0.0.1", "::1"}:
        return jsonify({"success": False, "message": "仅允许本机关闭服务"}), 403
    if not verify_access_token():
        return auth_error()
    shutdown_func = request.environ.get("werkzeug.server.shutdown")
    if shutdown_func is None:
        return jsonify({"success": False, "message": "当前服务器不支持关闭操作"}), 503
    threading.Timer(0.1, shutdown_func).start()
    return jsonify({"success": True, "message": "服务正在停止"})


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify(current_status())


@app.route("/api/logs", methods=["GET"])
def get_runtime_logs():
    try:
        limit = min(max(int(request.args.get("limit", 200)), 1), 300)
    except ValueError:
        limit = 200
    with runtime_log_lock:
        entries = list(runtime_logs)[-limit:]
    return jsonify({"logs": entries, "total": len(entries)})


@app.route("/api/logs/clear", methods=["POST"])
def clear_runtime_logs():
    with runtime_log_lock:
        runtime_logs.clear()
    append_runtime_log("运行日志已清空")
    return jsonify({"success": True, "message": "运行日志已清空"})


@app.route("/api/stats", methods=["GET"])
def get_stats():
    if not verify_access_token():
        return auth_error()
    return jsonify(current_status())


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(Config.public())


@app.route("/api/config", methods=["PUT", "POST"])
def update_config():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "message": "配置内容必须是 JSON 对象"}), 400

    old_port = Config.PORT
    try:
        Config.update(payload)
        initialize_runtime()
    except (ValueError, RuntimeError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        logger.exception("保存配置失败")
        return jsonify({"success": False, "message": f"保存配置失败: {exc}"}), 500

    port_changed = old_port != Config.PORT
    logger.info("配置已保存%s", "，端口将在重启后生效" if port_changed else "")
    return jsonify(
        {
            "success": True,
            "message": "配置已保存" + ("，请重新启动服务以应用新端口" if port_changed else ""),
            "restart_required": port_changed,
            "config": Config.public(),
        }
    )


@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    if not verify_access_token():
        return auth_error()
    if cache is None:
        return jsonify({"success": False, "message": "缓存未启用"})
    cache.clear()
    return jsonify({"success": True, "message": "缓存已清除"})


@app.route("/api/question-bank", methods=["GET"])
def get_question_bank():
    return jsonify({"questions": question_bank.snapshot(), "total": len(question_bank.records)})


@app.route("/api/question-bank/import", methods=["POST"])
def import_question_bank():
    if not verify_access_token():
        return auth_error()
    payload = request.get_json(silent=True)
    try:
        result = question_bank.import_records(payload)
    except (ValueError, TypeError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, **result})


@app.route("/api/question-bank/export", methods=["GET"])
def export_question_bank():
    data = json.dumps(question_bank.snapshot(), ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        BytesIO(data),
        mimetype="application/json",
        as_attachment=True,
        download_name="question_bank.json",
    )


@app.route("/api/question-bank/clear", methods=["POST"])
def clear_question_bank():
    if not verify_access_token():
        return auth_error()
    question_bank.clear()
    return jsonify({"success": True, "message": "本地题库已清空"})


@app.route("/api/ocs-config", methods=["GET"])
def ocs_config():
    base_url = request.host_url.rstrip("/")
    return jsonify(
        [
            {
                "name": "OCS2API",
                "url": f"{base_url}/api/search",
                "method": "get",
                "contentType": "json",
                "data": {
                    "title": "${title}",
                    "type": "${type}",
                    "options": "${options}",
                },
                "handler": "return (res)=> res.code === 1 ? [res.question, res.answer] : [res.msg, undefined]",
            }
        ]
    )


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("index.html")


@app.route("/docs", methods=["GET"])
def docs():
    docs_path = RESOURCE_DIR / "api_docs.md"
    try:
        content = docs_path.read_text(encoding="utf-8")
    except OSError:
        content = "API 文档文件未打包。"
    return f"<html lang='zh-CN'><meta charset='utf-8'><title>API 文档</title><pre>{content}</pre>"


def open_local_ui() -> None:
    webbrowser.open(f"http://127.0.0.1:{Config.PORT}")


def run_server() -> None:
    logger.info("服务监听 %s:%s", Config.HOST, Config.PORT)
    run_simple(
        Config.HOST,
        Config.PORT,
        app,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    threading.Thread(target=run_server).start()
    threading.Timer(0.8, open_local_ui).start()
    run_tray()
