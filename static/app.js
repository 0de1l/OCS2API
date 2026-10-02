(function () {
    "use strict";

    const state = {
        accessToken: sessionStorage.getItem("ocs_access_token") || "",
        toastTimer: null,
    };

    const $ = (selector) => document.querySelector(selector);

    function notify(message, isError) {
        const toast = $("#toast");
        toast.textContent = message;
        toast.classList.toggle("error", Boolean(isError));
        toast.classList.add("show");
        clearTimeout(state.toastTimer);
        state.toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
    }

    async function api(path, options) {
        const requestOptions = options || {};
        const headers = new Headers(requestOptions.headers || {});
        if (requestOptions.body && !headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json");
        }
        if (state.accessToken) headers.set("X-Access-Token", state.accessToken);
        const response = await fetch(path, { ...requestOptions, headers });
        const contentType = response.headers.get("content-type") || "";
        const data = contentType.includes("application/json") ? await response.json() : await response.text();
        if (!response.ok) throw new Error(data.message || data.msg || `请求失败 (${response.status})`);
        return data;
    }

    function formatUptime(seconds) {
        const value = Math.max(0, Number(seconds) || 0);
        const days = Math.floor(value / 86400);
        const hours = Math.floor((value % 86400) / 3600);
        const minutes = Math.floor((value % 3600) / 60);
        if (days) return `${days}天 ${hours}小时`;
        if (hours) return `${hours}小时 ${minutes}分`;
        return `${minutes}分钟`;
    }

    function setValue(id, value) { const element = $(`#${id}`); if (element) element.value = value ?? ""; }

    async function loadConfig() {
        const config = await api("/api/config");
        setValue("port", config.port);
        setValue("openai-api-base", config.openai_api_base);
        setValue("openai-model", config.openai_model);
        setValue("max-tokens", config.max_tokens);
        setValue("temperature", config.temperature);
        $("#enable-cache").checked = Boolean(config.enable_cache);
        $("#api-key-state").textContent = config.api_key_configured ? `已配置 ${config.api_key_masked}` : "尚未配置";
        $("#bank-path").textContent = config.question_bank_path || "启动后自动创建 JSON 文件";
    }

    function renderStatus(status) {
        const online = status.status === "ok";
        $("#status-pill").classList.toggle("offline", !online);
        $("#status-label").textContent = online ? "运行中" : "异常";
        $("#metric-status").textContent = online ? "在线" : "异常";
        $("#metric-port").textContent = `端口 ${status.port || "--"}`;
        $("#metric-uptime").textContent = formatUptime(status.uptime);
        $("#metric-bank").textContent = status.question_bank_size ?? "--";
        $("#metric-requests").textContent = status.counters ? status.counters.requests : "--";
        const requests = status.counters ? status.counters.requests : 0;
        const hits = status.counters ? status.counters.local_hits : 0;
        $("#metric-hit-rate").textContent = `本地命中 ${requests ? Math.round(hits * 100 / requests) : 0}%`;
        $("#upstream-status").textContent = status.api_key_configured ? "已配置" : "待配置";
        $("#upstream-status").classList.toggle("ready", Boolean(status.api_key_configured));
        $("#status-model").textContent = status.model || "--";
        $("#status-cache").textContent = status.cache_enabled ? `${status.cache_size} 项` : "未启用";
        $("#status-upstream-requests").textContent = status.counters ? status.counters.upstream_requests : "--";
    }

    async function loadStatus() {
        try { renderStatus(await api("/api/status")); }
        catch (error) {
            $("#status-pill").classList.add("offline");
            $("#status-label").textContent = "连接失败";
            notify(error.message, true);
        }
    }

    async function loadOcsConfig() {
        try {
            const config = await api("/api/ocs-config");
            $("#ocs-config").textContent = JSON.stringify(config, null, 2);
        } catch (error) { $("#ocs-config").textContent = error.message; }
    }

    function renderLogs(data) {
        const output = $("#runtime-log-output");
        const shouldStickToBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 24;
        const entries = data.logs || [];
        output.textContent = entries.length
            ? entries.map((entry) => `[${entry.time}] ${String(entry.level).padEnd(7)} ${entry.message}`).join("\n")
            : "> waiting for service output...";
        $("#log-count").textContent = `${entries.length} lines`;
        if (shouldStickToBottom) output.scrollTop = output.scrollHeight;
    }

    async function loadLogs() {
        try { renderLogs(await api("/api/logs?limit=200")); }
        catch (error) { $("#runtime-log-output").textContent = `> log stream unavailable: ${error.message}`; }
    }

    async function clearLogs() {
        try { notify((await api("/api/logs/clear", { method: "POST" })).message); await loadLogs(); }
        catch (error) { notify(error.message, true); }
    }

    async function saveConfig(event) {
        event.preventDefault();
        const payload = {
            port: Number($("#port").value),
            openai_api_base: $("#openai-api-base").value.trim(),
            openai_model: $("#openai-model").value.trim(),
            max_tokens: Number($("#max-tokens").value),
            temperature: Number($("#temperature").value),
            enable_cache: $("#enable-cache").checked,
        };
        const key = $("#openai-api-key").value.trim();
        const accessToken = $("#access-token").value.trim();
        if (key) payload.openai_api_key = key;
        if (accessToken) payload.access_token = accessToken;
        try {
            const result = await api("/api/config", { method: "PUT", body: JSON.stringify(payload) });
            if (accessToken) {
                state.accessToken = accessToken;
                sessionStorage.setItem("ocs_access_token", accessToken);
            }
            $("#openai-api-key").value = "";
            $("#access-token").value = "";
            $("#api-key-state").textContent = result.config.api_key_configured ? `已配置 ${result.config.api_key_masked}` : "尚未配置";
            notify(result.message);
            if (result.restart_required) {
                notify(`端口已保存为 ${result.config.port}，请关闭并重新启动应用`, false);
            } else {
                await loadStatus();
            }
        } catch (error) { notify(error.message, true); }
    }

    async function copyOcs() {
        try {
            await navigator.clipboard.writeText($("#ocs-config").textContent);
            notify("OCS 配置已复制");
        } catch (error) { notify("复制失败，请手动选择代码块复制", true); }
    }

    async function importBank(event) {
        const file = event.target.files[0];
        if (!file) return;
        try {
            const result = await api("/api/question-bank/import", { method: "POST", body: await file.text() });
            notify(`已导入 ${result.imported} 道题目，跳过 ${result.skipped} 条`);
            await loadStatus();
        } catch (error) { notify(error.message, true); }
        event.target.value = "";
    }

    async function clearCache() {
        try { notify((await api("/api/cache/clear", { method: "POST" })).message); await loadStatus(); }
        catch (error) { notify(error.message, true); }
    }

    async function clearBank() {
        if (!window.confirm("确定清空本地题库吗？此操作不可撤销。")) return;
        try { notify((await api("/api/question-bank/clear", { method: "POST" })).message); await loadStatus(); }
        catch (error) { notify(error.message, true); }
    }

    async function testQuestion(event) {
        event.preventDefault();
        const result = $("#test-result");
        result.textContent = "请求中...";
        try {
            const question = $("#test-question").value.trim();
            const data = await api(`/api/search?title=${encodeURIComponent(question)}`);
            result.textContent = JSON.stringify(data, null, 2);
            await loadStatus();
        } catch (error) { result.textContent = error.message; }
    }

    document.addEventListener("DOMContentLoaded", async () => {
        $("#settings-form").addEventListener("submit", saveConfig);
        $("#refresh-button").addEventListener("click", () => { loadStatus(); loadOcsConfig(); });
        $("#clear-logs").addEventListener("click", clearLogs);
        $("#copy-ocs").addEventListener("click", copyOcs);
        $("#bank-file").addEventListener("change", importBank);
        $("#export-bank").addEventListener("click", () => { window.location.href = "/api/question-bank/export"; });
        $("#clear-cache").addEventListener("click", clearCache);
        $("#clear-bank").addEventListener("click", clearBank);
        $("#test-form").addEventListener("submit", testQuestion);
        try { await loadConfig(); } catch (error) { notify(error.message, true); }
        await Promise.all([loadStatus(), loadOcsConfig(), loadLogs()]);
        setInterval(loadStatus, 10000);
        setInterval(loadLogs, 3000);
    });
}());
