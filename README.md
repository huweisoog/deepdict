# DeepDict · 全局划词 + DeepSeek 多轮追问助手

> 轻量级开源桌面划词翻译工具，支持 **Windows** 与 **macOS**。  
> 在浏览器、Adobe Acrobat PDF、Word、编辑器等**任意桌面应用**中选中文字 → 点击蓝色悬浮气泡（或按全局快捷键）→ 用 DeepSeek 流式给出「译文 + 语境讲解」→ 并直接在卡片底部**连续多轮追问**。

---

## 核心特性

- **全局任意应用划词**：不只是浏览器插件，记事本、Chrome/Edge、Word、**Adobe Acrobat PDF** 等应用都能用。
- **蓝色悬浮胶囊气泡**：拖选或双击文字后在光标附近弹出，支持**直接拖动移位**避免遮挡其他工具栏，点击不抢占原窗口焦点。
- **卡片内多轮追问**：译完一句话后可直接在底部输入框继续提问（例如“拆解语法”“给学术论文同义替换”“解释背景”），自动携带原文与完整上下文。
- **清爽浅色 UI + 流式渲染**：纯白卡片搭配清晰 Markdown 排版，支持钉住、标题栏拖动、复制、重试、Esc 收起。
- **安全取词不污染剪贴板**：Windows 优先走 UI Automation，失败后退回分段 `Ctrl+C` + 剪贴板稳定等待（兼容 Adobe 多格式剪贴板）并延迟还原；macOS 使用安全 `Cmd+C` 并还原剪贴板。
- **隐私与零中转**：仅在本地保存你自己的 API Key，请求直连 DeepSeek 官方或任意 OpenAI 兼容接口（如中转、本地 Ollama）。

---

## 平台支持

| 平台 | 取词与监听机制 | 默认热键 | 备注 |
| --- | --- | --- | --- |
| **Windows 10/11** | Raw Input 后台鼠标监听 + UI Automation / 安全 `Ctrl+C` + `RegisterHotKey` | `Ctrl+Alt+Q` / `Ctrl+Alt+S` | 已完成记事本、浏览器、Adobe Acrobat 实机验证 |
| **macOS** | `pynput` 全局键鼠监听 + 安全 `Cmd+C` + `LaunchAgents` 开机自启 | `Cmd+Alt+Q` / `Cmd+Alt+S` | 首次使用需在「系统设置 → 隐私与安全性 → 辅助功能」授予终端/Python 权限 |

---

## 命令行一键安装

> 前置要求：Python 3.10+（[Windows 下载](https://www.python.org/downloads/)；macOS 可用 `brew install python@3.12`）。

### 方式 1：使用 `pipx` 或 `pip` 安装（推荐，Windows / macOS 通用）

```bash
# 使用 pipx（自动隔离环境，最省心）
pipx install git+https://github.com/huweisoog/deepdict.git

# 或直接使用 pip
pip install git+https://github.com/huweisoog/deepdict.git
```

安装完成后直接运行：

```bash
deepdict
```

### 方式 2：一键脚本安装（自动建独立虚拟环境 + 配置命令）

**Windows（PowerShell）**：

```powershell
irm https://raw.githubusercontent.com/huweisoog/deepdict/main/scripts/install.ps1 | iex
```

**macOS（Terminal）**：

```bash
curl -fsSL https://raw.githubusercontent.com/huweisoog/deepdict/main/scripts/install.sh | bash
```

### 方式 3：从本地源码安装

```bash
git clone https://github.com/huweisoog/deepdict.git
cd deepdict

# Windows
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Source .

# macOS
bash ./scripts/install.sh .
```

---

## 快速上手

### 常用命令

```bash
deepdict              # 启动 DeepDict（首次运行自动弹出设置框填 API Key）
deepdict --demo       # 演示模式（无需 API Key，直接体验翻译卡片与追问界面）
deepdict --selftest   # 环境自检（检查依赖、剪贴板、热键与权限状态）
deepdict --version    # 查看版本号
deepdict --help       # 查看命令行帮助
```

### 日常操作

| 操作 | 效果 |
| --- | --- |
| 拖选或双击任意应用里的文字 | 光标旁弹出蓝色「译 翻译」胶囊气泡；轻点翻译，按住可拖动位置 |
| `Ctrl+Alt+Q`（macOS：`Cmd+Alt+Q`） | 直接翻译当前选中的文字 |
| `Ctrl+Alt+S`（macOS：`Cmd+Alt+S`） | 打开「输入翻译」框手动粘贴/输入文本 |
| 卡片底部追问框输入并回车 | 带着原文和译文上下文继续向 DeepSeek 多轮提问 |
| 点击卡片顶部「钉住」 | 切换回 PDF/网页看原文时卡片不自动收起 |
| `Esc` / 点击卡片外区域 | 关闭结果卡片 |

---

## 配置与隐私说明

- **配置文件位置**：
  - Windows：`%APPDATA%\DeepDict\config.json` 与 `.env`
  - macOS：`~/Library/Application Support/DeepDict/config.json` 与 `.env`
- **API Key 安全**：
  - API Key 仅保存在本地 `.env`（或通过环境变量 `DEEPDICT_API_KEY` / `DEEPSEEK_API_KEY` 传入），**不会写入 `config.json`，也不会上传至任何第三方服务器**。
  - 仓库已通过 `.gitignore` 严格排除 `.env`、`.user-config/`、`config.json` 等所有本地配置。
- **任意 OpenAI 兼容接口**：
  - 默认接口：`https://api.deepseek.com/v1`（支持 `deepseek-chat` 与 `deepseek-reasoner`）
  - 本地 Ollama 示例：接口地址填 `http://127.0.0.1:11434/v1`，模型填 `qwen2.5:7b`，API Key 任意非空值即可。

---

## 开发与打包

```bash
# 运行单元测试
python -m unittest discover -s tests -v

# Windows 打包独立绿色目录版（推荐 --onedir）
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name DeepDict --icon assets/deepdict.ico ^
  --exclude-module tkinter --exclude-module PIL --exclude-module numpy run.pyw
```

> **Windows 权限提示**：请勿将最终运行的打包程序放在带 `Low Mandatory Level`（低完整性标签）的沙盒目录中，否则 Windows UIPI 会拦截后台鼠标事件与 `Ctrl+C` 取词。使用上述一键脚本安装到 `%LOCALAPPDATA%\DeepDict` 即可自动保证正常的 Medium 完整性级别。

---

## License

[MIT License](LICENSE)
