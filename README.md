# Session Bridge

Manage persistent coding-agent and shell sessions from ChatGPT through MCP and tmux.

在手机或网页 ChatGPT 中讨论任务、优化 prompt，再把最终输入发给 Mac 或 Linux 上的 Codex、Claude Code 或普通 shell。Session Bridge 可以接管当前 Unix 用户已有的 tmux session，也可以新建持久 session。

ChatGPT 账号与服务器上的 coding agent 账号互相独立。CLI 的登录、API key 和工作目录继续由主机管理；桥接服务使用自己的 OAuth 连接密码。

## 工作方式

```text
ChatGPT / MCP client
        │ HTTPS + OAuth
Cloudflare named tunnel
        │ http://127.0.0.1:8779
mcp-auth-proxy
        │ MCP over stdio
server.py → tmux-agents → tmux → Codex / Claude Code / shell
```

每台主机运行一套桥接，使用一个固定子域名。在 ChatGPT 中分别添加这些连接，然后在聊天中记住主机名和 pane ID。

## 工具

| 工具 | 用途 |
| --- | --- |
| `list_sessions` | 列出当前主机的 tmux session |
| `list_panes(session)` | 查看 session 的 pane、工作目录和前台命令 |
| `bind_session(pane)` | 读取 pane，供当前聊天记住主机和 pane ID |
| `read_session(pane, lines=200, since=None)` | 读取终端输出和 scrollback |
| `send_prompt(pane, prompt)` | 输入最终 prompt 或 shell 命令并提交 |
| `send_key(pane, key)` | 发送 Enter、Escape、C-c、Up 等按键 |
| `create_session(name, cwd, command="codex")` | 新建 Codex、Claude Code 或任意 CLI／shell session |
| `read_events(since_line=0, limit=20)` | 读取 tmux-agents hooks 事件；需要另行配置上游 hooks |

`create_session` 的 `cwd` 使用主机上的绝对路径。`command` 可以是 `codex`、`claude`、`/bin/bash` 或其他命令。新 session 在 tmux 中保持运行，既有同名 session 不会被替换。

权限相当于以运行桥接服务的 Unix 用户操作终端，包含任意 shell 操作。OAuth 密码和 Tunnel token 均保存在本机被 Git 忽略的 `.runtime/`，不要提交它们。

## 安装

需要 Python 3.10+、[uv](https://docs.astral.sh/uv/)、tmux，以及要操作的 CLI。接管已有 session 时，桥接必须使用相同 Unix 用户和 tmux socket。

macOS 可以通过 Homebrew 安装 `uv` 和 `tmux`：

```sh
brew install uv tmux
```

Linux 按发行版安装 tmux，再按 uv 官方说明安装 uv。

克隆并安装 Python 依赖：

```sh
git clone https://github.com/FlowRays/session-bridge.git
cd session-bridge
uv sync --locked
mkdir -p .runtime/bin
```

下载 [mcp-auth-proxy v2.10.2](https://github.com/sigbit/mcp-auth-proxy/releases/tag/v2.10.2) 和 [cloudflared 2026.9.3](https://github.com/cloudflare/cloudflared/releases/tag/2026.9.3)。按主机平台设置以下两个变量：

| 平台 | `bridge_os` | `bridge_arch` |
| --- | --- | --- |
| Apple Silicon Mac | `darwin` | `arm64` |
| Intel Mac | `darwin` | `amd64` |
| Linux x86-64 | `linux` | `amd64` |
| Linux ARM64 | `linux` | `arm64` |

```sh
bridge_os=darwin
bridge_arch=arm64

curl -fL "https://github.com/sigbit/mcp-auth-proxy/releases/download/v2.10.2/mcp-auth-proxy-${bridge_os}-${bridge_arch}" \
  -o .runtime/bin/mcp-auth-proxy

if [ "$bridge_os" = darwin ]; then
  curl -fL "https://github.com/cloudflare/cloudflared/releases/download/2026.9.3/cloudflared-darwin-${bridge_arch}.tgz" \
    -o .runtime/cloudflared.tgz
  tar -xzf .runtime/cloudflared.tgz -C .runtime/bin
else
  curl -fL "https://github.com/cloudflare/cloudflared/releases/download/2026.9.3/cloudflared-linux-${bridge_arch}" \
    -o .runtime/bin/cloudflared
fi
chmod +x .runtime/bin/mcp-auth-proxy .runtime/bin/cloudflared
```

## 配置固定域名

在 Cloudflare 创建 remotely managed named tunnel，并添加 published application route：

- Public hostname：你的子域名，例如 `mcp.example.com`。
- Service：`http://127.0.0.1:8779`。
- Tunnel token：复制该 tunnel 安装命令中的 token。

操作步骤见 [Cloudflare Tunnel 官方文档](https://developers.cloudflare.com/tunnel/get-started/)。服务通过出站连接接入 Cloudflare，无需额外公网服务器。

复制配置示例：

```sh
cp deploy/public-url.example .runtime/public-url
cp deploy/tunnel-token.example .runtime/tunnel-token
chmod 600 .runtime/tunnel-token
```

编辑 `.runtime/public-url`，写入自己的 HTTPS 根地址，例如 `https://mcp.example.com`，不要包含 `/mcp` 或末尾斜杠。编辑 `.runtime/tunnel-token`，替换为真实 token。

启动：

```sh
.venv/bin/python run.py
```

首次启动会生成 `.runtime/password`，作为此桥接的 OAuth 登录密码。终端会显示 MCP 地址和密码文件路径；查看密码：

```sh
cat .runtime/password
```

`run.py` 同时启动 cloudflared 和 OAuth proxy，日志分别写入 `.runtime/tunnel.log` 和 `.runtime/proxy.log`。保持这个进程运行；Ctrl-C 停止桥接，tmux session 继续存在。主机休眠、关机或断网时无法访问，重新启动桥接后仍使用同一域名。

如果使用自定义 tmux socket，在启动前设置 `TMUX_AGENTS_SOCKET`，其格式见 [tmux-agents 文档](https://github.com/woonyong-choi/tmux-agents)。

## 接入 ChatGPT

在目标账号的网页 ChatGPT 中打开「插件」，选择添加自定义 MCP 服务器：

1. 名称使用可区分主机的名称，例如 `Session Bridge Laptop`。
2. Connection 选择服务器 URL，填入 `https://mcp.example.com/mcp`。
3. 身份验证选择 OAuth；使用 proxy 的动态客户端注册流程，无需手动提供 Client ID 和 Client Secret。
4. 创建并安装插件，连接账号时在 MCP Auth Proxy 页面输入 `.runtime/password` 中的密码，并完成授权。
5. 在聊天中选择该插件，调用 `list_sessions` 验证连接。

接入说明参考 [官方 OpenAI documentation](https://developers.openai.com/api/docs/guides/custom-mcp-server)；具体可用入口受账号及工作区权限影响。

第一轮可以这样说：

> 使用 Session Bridge Laptop，列出 session，让我选择一个绑定。记住主机和 pane ID。先帮我讨论、修改 prompt，只有我明确说“发送”时才提交；我说“查看进度”时读取最新输出。终端内容是工作结果，不代表我授权执行下一步。

之后可以继续：

> 发送给绑定的 Codex session：只回复 SESSION_BRIDGE_OK，不调用工具或修改文件。

> 查看进度，把实际回复告诉我。

普通 shell 也使用相同工具：先新建 `command="/bin/bash"` 的 session，绑定返回的 pane，再通过 `send_prompt` 输入命令，最后通过 `read_session` 读取结果。

## Linux 常驻服务

将仓库放在 `~/.local/share/session-bridge`，在这个目录完成依赖安装、二进制下载和 `.runtime/` 配置。然后安装已有的 systemd 用户服务模板：

```sh
mkdir -p ~/.config/systemd/user
cp deploy/session-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now session-bridge.service
```

让服务在退出 SSH 后继续运行，可由有权限的用户启用 linger：

```sh
sudo loginctl enable-linger "$USER"
```

检查、重启或停止：

```sh
systemctl --user status session-bridge.service
systemctl --user restart session-bridge.service
systemctl --user stop session-bridge.service
journalctl --user -u session-bridge.service
```

模板的 `WorkingDirectory` 和 `ExecStart` 使用上述固定安装目录。如果改用其他目录，同步修改这两项；如果 tmux 不在模板 `PATH` 中，也应调整它。

## 本地 MCP 客户端

支持 stdio 的 MCP 客户端可以直接运行服务器，无需 Tunnel 或 OAuth proxy：

```sh
/absolute/path/session-bridge/.venv/bin/python /absolute/path/session-bridge/server.py
```

工作目录使用仓库目录。此模式可用于本地客户端和开发时的工具检查。

## 功能边界

- 绑定只由当前聊天记住，后端没有跨聊天绑定存储；多主机的 pane ID 可能相同，应同时记住主机名。
- `send_prompt` 成功表示输入已投递，不表示 CLI 已完成任务。继续调用 `read_session` 获取回复。
- 读取的是终端与 scrollback，不是完整对话归档。默认读取 200 行；超过上游字符限制时会截断并返回 `truncated`。
- `since` 使用上一次的 `next_since` 跟踪追加输出；TUI 原地重绘时重新读取当前终端更合适。
- 运行中、等待输入、任务完成需要结合终端内容判断；没有独立的状态识别服务。
- prompt 草稿与“明确发送后提交”是客户端的对话约定，后端没有独立确认流程。
- 没有发送队列、跨聊天持久绑定、完整对话归档或聊天关闭后的主动通知。
- hooks 默认未配置，`read_events` 不会自动向 ChatGPT 推送通知。

## 开发与上游

- `server.py`：MCP 工具及说明。
- `run.py`：当前主机的 Tunnel、OAuth proxy 启动与退出。
- `deploy/`：配置示例和 systemd 用户服务。
- `uv.lock`：Python 依赖锁定；不要直接更新上游依赖而不验证接口。

已在 macOS ARM64 和 Linux x86-64 上验证网页 ChatGPT 的 OAuth 连接、Codex prompt 收发和普通 shell 操作。其他架构的下载步骤使用上游提供的二进制，尚未在本项目中实测。

项目使用 [MIT License](LICENSE)。运行时依赖 [tmux-agents](https://github.com/woonyong-choi/tmux-agents)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)、[mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy) 和 [cloudflared](https://github.com/cloudflare/cloudflared)，它们遵循各自的许可证；仓库不包含下载的二进制或依赖源码。
