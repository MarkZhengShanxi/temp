# OpenAI-Compatible Chrome Side Panel Browser Agent

这个项目实现了一个 Chrome Side Panel 浏览器 Agent。用户在 Side Panel 中用自然语言描述任务，插件读取当前页面和浏览器状态，本地后端调用 ChatGPT / OpenAI-compatible Chat Completions API 规划下一步动作，插件再在真实网页中执行点击、输入、滚动、标签页操作等动作。

## 目录

```text
extension/   Chrome Manifest V3 插件，无需打包
backend/     FastAPI 本地后端，调用 /v1/chat/completions
```

## 能力

- Side Panel 自然语言任务输入
- 可配置 OpenAI-compatible：`base_url`、`api_key`、`model`
- 当前页面观察：标题、URL、可见文本、交互元素、viewport、浏览器 tabs
- 多步循环：观察 → 模型规划 → 执行动作 → 重新观察
- 动作：点击、输入、清空、按键、选择、滚动、等待、读取页面、打开/切换/关闭标签页
- 用户可见状态日志
- 对提交、删除、支付、发送、上传、密码等危险操作强制确认
- 不使用 Anthropic SDK，也不使用 Anthropic 专有参数

## 启动后端

```bash
cd /Users/admin/work/temp/task4/backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8765/health
```

后端日志会同时输出到启动 `uvicorn` 的终端，以及文件：

```text
/Users/admin/work/temp/task4/backend/logs/backend.log
```

实时查看文件日志：

```bash
tail -f /Users/admin/work/temp/task4/backend/logs/backend.log
```

日志会记录 base_url、model、请求状态码和错误摘要，但不会打印 API Key。

`.env` 可配置默认模型：

```bash
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=你的_key
OPENAI_MODEL=gpt-4.1-mini
```

你也可以在 Side Panel 中临时输入 API Key 和模型名。Side Panel 里的配置会覆盖 `.env` 默认值。

## 加载 Chrome 插件

1. 打开 Chrome：`chrome://extensions`
2. 开启 **Developer mode / 开发者模式**
3. 点击 **Load unpacked / 加载已解压的扩展程序**
4. 选择目录：

```text
/Users/admin/work/temp/task4/extension
```

5. 点击插件图标打开 Side Panel。
6. 配置：
   - 本地后端 URL：`http://127.0.0.1:8765`
   - Base URL：`https://api.openai.com/v1` 或其他兼容服务
   - API Key
   - Model：例如 `gpt-4.1-mini`，或你的兼容服务模型名
7. 点击“测试连接”。

## 示例任务

在普通网页打开 Side Panel 后输入：

```text
总结当前页面内容
```

```text
向下滚动，找到 pricing 相关链接并点击
```

```text
在搜索框里输入 Claude API，但不要提交
```

如果 Agent 即将执行敏感或不可逆动作，Side Panel 会显示确认卡片，你可以选择“允许一次”或“拒绝并停止”。

## OpenAI-Compatible 服务说明

后端直接调用：

```text
POST {base_url}/chat/completions
Authorization: Bearer <api_key>
```

默认请求包含：

```json
{
  "model": "gpt-4.1-mini",
  "messages": [],
  "temperature": 0.2,
  "max_tokens": 2048,
  "response_format": { "type": "json_object" }
}
```

如果服务不支持 `response_format` 并返回 400，后端会自动重试一次不带该字段。

可用服务示例：

- OpenAI 官方：`https://api.openai.com/v1`
- 本地兼容服务：`http://127.0.0.1:11434/v1`
- 其他兼容代理：`https://your-provider.example/v1`

## 安全限制

- API Key 不会发送给当前网页或 content script。
- content script 不支持任意 JavaScript eval。
- 密码框 value 不会被读取或回传。
- 危险动作需要确认，包括提交表单、付款、删除、下单、发送消息、上传文件等。
- 网页文本被视为不可信观察数据，不能覆盖用户任务或后端安全规则。
- 默认最大 20 步，避免无限自动操作。

## 测试

```bash
cd /Users/admin/work/temp/task4/backend
pytest
```

## 重要文件

- `extension/manifest.json`：Chrome 插件声明
- `extension/background.js`：tab 状态、content script 注入和动作转发
- `extension/content.js`：页面观察和真实网页动作执行
- `extension/sidepanel.js`：Side Panel 配置、任务循环、确认流程
- `backend/app/llm_client.py`：OpenAI-compatible Chat Completions 客户端
- `backend/app/agent.py`：Agent run 和步骤管理
- `backend/app/safety.py`：危险动作确认策略
- `backend/app/planner.py`：Agent prompt
