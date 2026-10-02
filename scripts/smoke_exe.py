"""Validate a Windows EXE in a disposable directory, using local-only queries."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", nargs="?", default="dist/OCS2API.exe")
    args = parser.parse_args()
    executable = Path(args.exe).resolve()
    if os.name != "nt" or not executable.is_file():
        raise SystemExit("A Windows build of OCS2API.exe is required")

    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 5000))
            port = 5000
        except OSError:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

    with tempfile.TemporaryDirectory(prefix="ocs2api-smoke-") as directory:
        root = Path(directory)
        target = root / f"OCS2API-smoke-{os.getpid()}.exe"
        shutil.copy2(executable, target)
        if port != 5000:
            (root / "config.json").write_text(json.dumps({"port": port}), encoding="utf-8")
        (root / ".env").write_text("OPENAI_API_KEY=example-must-not-load\nOPENAI_MODEL=example-must-not-load\n", encoding="utf-8")
        env = dict(os.environ, OPENAI_API_KEY="example-must-not-load", OPENAI_MODEL="example-must-not-load")
        base = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def call(path, payload=None):
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
            with opener.open(request, timeout=3) as response:
                return response.read()

        process = subprocess.Popen([str(target)], cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 45
            while True:
                if process.poll() is not None:
                    raise RuntimeError("EXE exited before becoming ready")
                try:
                    health = json.loads(call("/api/health"))
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("EXE did not start within 45 seconds")
                    time.sleep(0.25)
            assert health["status"] == "ok"
            assert health["api_key_configured"] is False
            assert health["model"] == "gpt-4o-mini"
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            assert config.get("openai_api_key", "") == ""
            assert json.loads((root / "question_bank.json").read_text(encoding="utf-8")) == []
            assert b"OCS2API" in call("/")
            assert b"runtime-log-output" in call("/static/app.js")
            assert b"terminal-output" in call("/static/style.css")
            record = {"question": "1+1?", "type": "", "options": "", "answer": "2"}
            assert json.loads(call("/api/question-bank/import", [record]))["success"]
            assert json.loads(call("/api/search?" + urllib.parse.urlencode({"title": "1+1?"})))["answer"] == "2"
            assert json.loads(call("/api/question-bank/export")) == [record]
            assert json.loads(call("/api/ocs-config"))[0]["url"].endswith(f":{port}/api/search")
            assert json.loads(call("/api/logs"))["logs"]
            print("EXE smoke passed: isolated startup, no inherited key, bundled UI, local bank, OCS URL, logs.")
            if port != 5000:
                print("Port 5000 was occupied; used a temporary port configuration.")
        finally:
            if process.poll() is None:
                # Stop only the process tree launched by this test.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            subprocess.run(["taskkill", "/IM", target.name, "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
