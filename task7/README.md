# AI记事本

一个轻量 Python 前后端 AI 记事本应用：支持长文本输入、浏览器按住说话、AI 智能解析记事/提醒/查找/删除意图，以及到点提醒。

## 功能

- 输入自然语言，自动识别：
  - 普通记事
  - 单次提醒
  - 频率提醒（例如“每隔5分钟提醒我喝水”）
  - 查找已有记录
  - 物理删除已有记录
- 前端支持 Web Speech API 按住说话（浏览器支持时可用）
- 后端通过 SSE 推送到点提醒
- 页面内提醒 + Browser Notification 系统通知
- SQLite 本地持久化

## 技术栈

- FastAPI
- SQLModel + SQLite
- APScheduler
- Anthropic Python SDK（默认 `claude-opus-4-8`，也支持 Anthropic-compatible 代理配置）
- 原生 HTML/CSS/JavaScript

## 安装

```bash
cd /Users/admin/work/temp/task7
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

复制配置文件：

```bash
cp .env.example .env
```

如果要使用 Claude AI 解析，请配置 Anthropic 凭据：

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

或使用 Anthropic CLI 登录后让 SDK 自动读取本地凭据：

```bash
ant auth login
```

如果你使用 Claude Code 同款 Anthropic-compatible 代理配置，可以在 `.env` 中设置：

```bash
ANTHROPIC_AUTH_TOKEN=your-token
ANTHROPIC_BASE_URL=xxxx
ANTHROPIC_DEFAULT_OPUS_MODEL=openai/gpt-5.5
API_TIMEOUT_MS=600000
ANTHROPIC_ENABLE_CLAUDE_PARAMS=false
```

说明：当模型名不是 `claude-*` 时，应用默认不发送 `thinking` / `output_config` 这类 Claude 专用参数，以兼容代理模型。如果你的代理支持这些参数，可将 `ANTHROPIC_ENABLE_CLAUDE_PARAMS=true`。

没有凭据时，应用仍会使用内置规则解析常见命令。

## 运行

```bash
uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000/
```

## 示例输入

- `记一下：今天客户说预算下周确认`
- `10分钟后提醒我开会`
- `每隔5分钟提醒我喝水`
- `找一下合同相关的记录`
- `删除喝水提醒`

## 测试

```bash
pytest
```

## MVP 限制

- 语音输入依赖浏览器 Web Speech API 支持。
- 调度器运行在 FastAPI 单进程内，适合本地和单 worker 部署；多 worker/生产部署建议拆出独立 scheduler worker。
- 搜索使用 SQLite LIKE；后续可升级到 FTS5、中文分词或向量检索。
- 当前重点支持单次提醒、interval 频率提醒和基础 daily 提醒。
- 暂无多用户登录。
