# AutoPaperdownload

一个基于 Python 的学术论文自动搜索与下载工具。

## 📖 项目简介

AutoPaperdownload 旨在帮助研究人员和学生通过自动化脚本，利用关键词检索或预先准备好的文献 DOI 号，快速从学术资源库检索并下载所需的文献。项目结合 pyautogui、Selenium 等自动化技术模拟浏览器操作，绕过繁琐的手动搜索与下载流程。

## ✨ 主要功能

- **关键词搜索**：支持在 PubMed 上根据关键词自动检索，通过 RSS 订阅提取 DOI
- **自动化下载**：根据 DOI 号自动访问文献页面并下载 PDF 到本地
- **补充材料下载**：自动抓取论文的 Supporting Information (SI)
- **多平台支持**：已适配 30+ 主流学术出版商网站（ACS、Wiley、Springer、Elsevier、Nature 等）
- **人机验证应对**：通过模拟真人操作行为绕过基本的人机验证
- **域名规则向导**：遇到新网站时可通过 GUI 三步添加下载规则
- **失败重试**：自动识别下载失败的文献，支持提取 Failed DOI 进行二次下载

## 🛠️ 环境要求

- **Python** 3.x
- **浏览器**
  - **Windows**：默认优先使用 Edge
  - **macOS**：使用系统默认浏览器（推荐 Safari/Chrome/Edge）
- **WebDriver（可选）**：仅在启用 Selenium 时需要与 Edge 版本匹配的驱动

## 📦 安装

```bash
git clone <repo-url>
cd AutoPaperdownload

# 创建虚拟环境
python -m venv venv

# 安装依赖
# Windows PowerShell: .\venv\Scripts\Activate.ps1
# macOS / Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 关键依赖

| 包名 | 用途 |
|------|------|
| pyautogui | 屏幕自动化操作 |
| pyperclip | 剪贴板操作 |
| selenium | 浏览器自动化 |
| opencv-python | 屏幕图像匹配（locateOnScreen 的 confidence 参数必需） |
| psutil | 进程管理 |
| Pillow | 图像处理 |
| requests | HTTP 请求 |

## 📂 项目结构

```
AutoPaperdownload/
├── config_manager.py        # GUI 管理控制台（主入口）
├── getdoi_helper.py         # PubMed 关键词检索 → DOI 提取
├── Paperdownload.py         # 核心论文下载引擎
├── SIdownload.py            # 补充材料 (SI) 下载
├── doiexacter.py            # 从本地文档提取 DOI
├── Csv_Turner_strenth.py    # 提取下载失败的 DOI
├── 筛选文件大小.py            # 清理空壳/损坏文件
├── Paperkeyword.json        # 各出版商下载关键词规则
├── DownloadSettings.json    # 下载参数配置
├── DownloadTemplates.json   # 模板链接配置
├── DomainBranch.json        # 域名分支配置
├── LoginConfig.json         # 需登录域名配置
├── SIkeyword.json           # SI 下载关键词配置
├── PaperDoi.csv             # DOI 列表（输入/输出）
├── edgedriver/              # Edge WebDriver
├── photos/                  # 屏幕匹配用的参考图片
├── RSS/                     # RSS 订阅内容保存目录
├── requirements.txt         # Python 依赖
└── venv/                    # 虚拟环境
```

## 🚀 运行方式

### 方式一：GUI 管理控制台（推荐）

```bash
python config_manager.py
```

通过图形界面完成所有操作：配置参数、添加规则、执行下载。

### 方式二：关键词检索全自动流程

1. 在 `getdoi_helper.py` 中设置 `SEARCH_QUERY`（检索词）和输出路径
2. 运行：
   ```bash
   python getdoi_helper.py
   ```
3. 程序会自动完成：PubMed 搜索 → RSS 获取 → DOI 提取 → 调用 Paperdownload.py 下载正文 → 调用 SIdownload.py 下载补充材料

> ⚠️ 注意：当前 PubMed RSS 单次最多获取最新 15 篇文献

### 方式三：已有 DOI 列表直接下载

如果你已经有包含 DOI 的文献列表（txt 文件或 CSV）：

1. **从文档提取 DOI**：通过 GUI 的"指定文档 DOI 提取"功能，或直接运行 `doiexacter.py`
2. **确保 CSV 格式正确**：`PaperDoi.csv` 首行为表头 `DOI,DownloadStatus,Filename,URL,DownloadURL,SIDownloadStatus,SIFilename,HTMLFilename`，DOI 列填入纯 DOI 号（如 `10.1021/acsami.5c20306`）
3. **修改路径**：在 `Paperdownload.py` 的 `Config` 类中将 `CSV_PATH` 和 `PAPER_DOWNLOAD_FOLDER` 指向你的目标目录
4. **运行下载**：
   ```bash
   python Paperdownload.py
   ```
5. **下载补充材料**（可选）：正文下载完成后运行 `python SIdownload.py`

### 后续处理

- **清理无效文件**：运行 `筛选文件大小.py` 剔除空壳/损坏文件
- **失败重试**：运行 `Csv_Turner_strenth.py` 提取失败 DOI，重新下载

## 📦 安装包构建（Windows + macOS）

### 运行时目录说明

- 开发态（`python config_manager.py`）：默认直接使用项目根目录作为数据目录。
- 打包态（安装包运行）：
  - Windows：`%LOCALAPPDATA%/AutoPaperdownload`
  - macOS：`~/Library/Application Support/AutoPaperdownload`
- 程序会在数据目录自动创建：`log/`、`html/`、`RSS/`、`Paper/`、`SI/`，并在首次启动时自动复制默认 JSON/CSV。

### macOS 构建

```bash
pip install pyinstaller
bash scripts/build_mac.sh
```

- 产物：
  - `dist/AutoPaperdownload.app`
  - `release/mac/AutoPaperdownload-<version>-mac-arm64.dmg`
- 首次运行需在系统设置授权：
  - 辅助功能（Accessibility）
  - 屏幕录制（Screen Recording）

### Windows 构建

```powershell
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\scripts\build_win.ps1
```

- 产物：
  - `release/win/AutoPaperdownload-Setup-<version>-win64.exe`（安装包，需本机已安装 Inno Setup）
  - 若未安装 Inno Setup，则至少产出 `dist/AutoPaperdownload/` 可分发目录

### 安装包目标

- 不依赖目标机器预装 Python。
- GUI 通过 worker 可执行文件调度 `getdoi/paper/si` 及辅助脚本，不再依赖 `python xxx.py`。
- 所有运行日志统一写入数据目录下 `log/`。

### GitHub Actions 自动打包发布（Windows + macOS）

仓库内已提供工作流：`.github/workflows/release.yml`

- 触发方式：
  - 推送标签：`v*`（如 `v1.0.0`）后自动构建并发布
  - 手动触发：`Actions -> Build And Release -> Run workflow`
- 构建内容：
  - macOS：`release/mac/*.dmg`
  - Windows：`release/win/*.exe`
- 发布位置：
  - GitHub 仓库 `Releases` 页面（自动上传安装包）

快速发布示例：

```bash
git tag v1.0.0
git push origin v1.0.0
```

## 🌐 添加新网站支持

通过 GUI 的"域名规则向导"三步完成，或手动编辑配置文件：

**第一步：获取文章页面 URL**

例如：`https://onlinelibrary.wiley.com/doi/10.1002/anie.202508314`

**第二步：确认下载路径**

- **自动下载**：右键下载按钮复制链接，如 `https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/anie.202508314?download=true`
- **手动下载**：点击 PDF 图标后的页面链接，如 `https://pubs.acs.org/doi/pdf/10.1021/la061142v?ref=article_openPDF`（需 Ctrl+S 保存）

**第三步：确定链接获取方式**

- **模板下载**：链接格式固定、只变 DOI 号 → 写入 `DownloadTemplates.json`
- **检索下载**：在文章源代码（Ctrl+U）中找到下载链接的特征关键词（如 `openPDF`、`epdf`）→ 写入 `Paperkeyword.json`

## ⚠️ 注意事项

- 运行时请勿操作鼠标键盘，pyautogui 会控制屏幕操作
- 保存 CSV 时注意避免双重后缀（如 `PaperDoi.csv.csv`）
- 部分出版商网站需要机构登录才能下载全文，请确保浏览器已登录
- macOS 需为 Python/终端授予“辅助功能”和“屏幕录制”权限（系统设置 → 隐私与安全性）
- Windows 默认优先 Edge，macOS 默认使用系统浏览器（Safari/Chromium 系快捷键模型）
