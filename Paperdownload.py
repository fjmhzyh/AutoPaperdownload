import os
import re
import csv
import time
import sys
import html
import subprocess
import threading
import pyautogui
import pyperclip
import json
import psutil
import shutil
import requests
from urllib.parse import urlparse
from urllib.parse import urljoin
from urllib.parse import quote
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Set
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
import random
from log_utils import setup_script_logging
from parent_guard import start_parent_guard
from platform_compat import (
    get_browser_process_names,
    get_default_edge_browser_path,
    get_last_open_url_error,
    hotkey,
    is_windows,
    open_url,
)
from runtime_config import load_runtime_config
from runtime_paths import data_path, ensure_runtime_layout, get_bundle_dir, get_data_dir
from publisher import (
    LegacyLoginFallback,
    LoginContext,
    normalize_domain,
    resolve_handler,
)

ensure_runtime_layout()
_BUNDLE_DIR = get_bundle_dir()
_DATA_DIR = get_data_dir()


def _resolve_yanzhen_script_path() -> Optional[str]:
    """解析验证码助手脚本路径（优先 photos/yanzhen.py）。"""
    candidates = [
        os.path.join(_BUNDLE_DIR, "photos", "yanzhen.py"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos", "yanzhen.py"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "yanzhen.py"),
        data_path("photos", "yanzhen.py"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _build_yanzhen_command(script_path: str) -> Optional[List[str]]:
    """构建验证码助手启动命令。"""
    if not script_path:
        return None
    if not getattr(sys, "frozen", False):
        return [sys.executable, script_path]

    worker_candidates = [
        os.path.join(os.path.dirname(sys.executable), "yanzhen_worker", "yanzhen_worker"),
        os.path.join(os.path.dirname(sys.executable), "yanzhen_worker.exe"),
        os.path.join(os.path.dirname(sys.executable), "yanzhen_worker"),
        os.path.join(_BUNDLE_DIR, "yanzhen_worker", "yanzhen_worker"),
        os.path.join(_BUNDLE_DIR, "yanzhen_worker.exe"),
        os.path.join(_BUNDLE_DIR, "yanzhen_worker"),
    ]
    for worker in worker_candidates:
        if os.path.isfile(worker):
            return [worker]

    python_cmd = shutil.which("python3") or shutil.which("python")
    if python_cmd:
        return [python_cmd, script_path]
    return None


def _start_yanzhen_helper() -> Optional[subprocess.Popen]:
    """启动验证码助手子进程。"""
    script_path = _resolve_yanzhen_script_path()
    if not script_path:
        print("[验证码助手] 未找到脚本 photos/yanzhen.py，跳过启动")
        return None

    command = _build_yanzhen_command(script_path)
    if not command:
        print("[验证码助手] 未找到可用启动命令，跳过启动")
        return None

    try:
        proc = subprocess.Popen(
            command,
            cwd=os.path.dirname(script_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        print(f"[验证码助手] 已启动 PID={proc.pid} 脚本={script_path} 命令={' '.join(command)}")

        def _forward_output() -> None:
            try:
                if not proc.stdout:
                    return
                for line in proc.stdout:
                    text = line.rstrip("\n")
                    if text:
                        print(f"[验证码助手][输出] {text}")
            except Exception as read_err:
                print(f"[验证码助手] 读取输出失败: {read_err}")
            finally:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass

        threading.Thread(target=_forward_output, daemon=True, name="yanzhen-output-forward").start()
        time.sleep(1)
        exit_code = proc.poll()
        if exit_code is not None:
            print(f"[验证码助手] 启动后立即退出 Exit={exit_code}")
            return None
        return proc
    except Exception as e:
        print(f"[验证码助手] 启动失败: {e}")
        return None


def _stop_yanzhen_helper(proc: Optional[subprocess.Popen]) -> None:
    """关闭验证码助手子进程。"""
    if not proc:
        return
    try:
        if proc.poll() is not None:
            print(f"[验证码助手] 已结束 PID={proc.pid}")
            return
        proc.terminate()
        proc.wait(timeout=3)
        print(f"[验证码助手] 已停止 PID={proc.pid}")
    except Exception:
        try:
            proc.kill()
            print(f"[验证码助手] 已强制停止 PID={proc.pid}")
        except Exception as e:
            print(f"[验证码助手] 停止失败 PID={proc.pid}: {e}")


def _default_watch_dirs() -> List[str]:
    """返回跨平台常见下载目录，用于自动归集到Paper目录"""
    dirs: List[str] = [os.path.expanduser("~/Downloads")]
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        dirs.append(os.path.join(userprofile, "Downloads"))
    onedrive = os.environ.get("OneDrive", "")
    if onedrive:
        dirs.append(os.path.join(onedrive, "Downloads"))
    return dirs


def _paste_url_to_address_bar(url: str) -> bool:
    """优先通过剪贴板粘贴URL到地址栏，失败时回退逐字输入。"""
    previous_clipboard = None
    try:
        previous_clipboard = pyperclip.paste()
    except Exception:
        previous_clipboard = None

    try:
        print("[地址栏输入] 使用粘贴方式打开URL")
        pyperclip.copy(url)
        time.sleep(0.1)
        hotkey("paste")
        return True
    except Exception as e:
        print(f"[地址栏输入] 粘贴失败，回退逐字输入: {e}")
        pyautogui.write(url, interval=0.01)
        return False
    finally:
        if previous_clipboard is not None:
            try:
                pyperclip.copy(previous_clipboard)
            except Exception:
                pass


# 全局配置
class Config:
    """应用程序配置类"""
    DOWNLOAD_PATH = data_path("html")  # HTML保存路径
    JSON_PATH = data_path("Paperkeyword.json")  # 关键词json路径
    DOMAIN_BRANCH_JSON = data_path("DomainBranch.json")  # 域名分支配置
    DOWNLOAD_TEMPLATE_JSON = data_path("DownloadTemplates.json")  # 下载模板配置
    DOWNLOAD_SETTINGS_JSON = data_path("DownloadSettings.json")  # 下载设置配置
    LOGIN_CONFIG_JSON = data_path("LoginConfig.json")  # 登录配置路径
    CSV_PATH = data_path("PaperDoi.csv")  # 论文列表CSV
    EDGE_DRIVER_PATH = os.path.join(
        _BUNDLE_DIR,
        "edgedriver",
        "msedgedriver.exe" if is_windows() else "msedgedriver",
    )  # Selenium驱动路径
    EDGE_BROWSER_PATH = get_default_edge_browser_path()
    USE_SELENIUM = False  # 是否使用Selenium方案
    DELAY_BETWEEN_PAPERS = 60  # 每篇论文间隔时间(秒)
    PAGE_LOAD_TIMEOUT = 15  # 页面加载超时时间(秒)
    DOCUMENT_EXTENSIONS = ["pdf"]  # 支持的文档扩展名
    PAPER_DOWNLOAD_FOLDER = data_path("Paper")  # Paper下载文件夹
    EXTRA_WATCH_DIRS = _default_watch_dirs()  # 额外监听下载目录（Windows/mac常见下载目录）

    @classmethod
    def _resolve_path(cls, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(_DATA_DIR, path))

    @classmethod
    def normalize_paths(cls):
        """将相对路径转换为项目内绝对路径"""
        cls.DOWNLOAD_PATH = cls._resolve_path(cls.DOWNLOAD_PATH)
        cls.CSV_PATH = cls._resolve_path(cls.CSV_PATH)
        cls.PAPER_DOWNLOAD_FOLDER = cls._resolve_path(cls.PAPER_DOWNLOAD_FOLDER)
        cls.EXTRA_WATCH_DIRS = list({os.path.abspath(p) for p in cls.EXTRA_WATCH_DIRS})

    @classmethod
    def ensure_directories_exist(cls):
        """确保所有必要的目录都存在"""
        cls.normalize_paths()
        os.makedirs(cls.DOWNLOAD_PATH, exist_ok=True)
        os.makedirs(cls.PAPER_DOWNLOAD_FOLDER, exist_ok=True)

    @classmethod
    def apply_runtime_config(cls):
        def _to_bool(value):
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "y"}

        cfg = load_runtime_config()
        paths = cfg.get("paths", {})
        params = cfg.get("params", {})

        cls.DOWNLOAD_PATH = paths.get("DOWNLOAD_PATH", cls.DOWNLOAD_PATH)
        cls.CSV_PATH = paths.get("CSV_PATH", cls.CSV_PATH)
        cls.PAPER_DOWNLOAD_FOLDER = paths.get("PAPER_FOLDER", cls.PAPER_DOWNLOAD_FOLDER)

        cls.USE_SELENIUM = _to_bool(params.get("USE_SELENIUM", cls.USE_SELENIUM))
        cls.DELAY_BETWEEN_PAPERS = int(params.get("DELAY_PAPER", cls.DELAY_BETWEEN_PAPERS))
        cls.PAGE_LOAD_TIMEOUT = int(params.get("TIMEOUT", cls.PAGE_LOAD_TIMEOUT))
        cls.normalize_paths()


class ProcessManager:
    """进程管理类"""
    @staticmethod
    def kill_browser_processes():
        """关闭所有浏览器进程"""
        try:
            print("[进程管理] 正在关闭所有浏览器进程...")
            browser_names = set(get_browser_process_names())
            killed = 0
            
            for proc in psutil.process_iter():
                try:
                    if proc.name().lower() in browser_names:
                        proc.kill()
                        killed += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            print(f"[进程管理] 已关闭 {killed} 个浏览器进程")
        except Exception as e:
            print(f"[进程管理错误] 关闭浏览器进程失败: {str(e)}")


class DownloadSettingsManager:
    """下载设置管理类"""
    DEFAULT_SETTINGS = {
        "use_ctrl_s": True,        # 是否使用Ctrl+S保存操作
        "ctrl_s_delay": 5,         # Ctrl+S操作后的等待时间(秒)
        "max_retries": 3,          # 最大重试次数
        "retry_delay": 10          # 重试之间的延迟(秒)
    }
    
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.default_settings = self.DEFAULT_SETTINGS.copy()
        self.domain_settings = {}
        
    def load_settings(self):
        """加载下载设置"""
        try:
            if not os.path.exists(self.json_path):
                print(f"[下载设置] 配置文件不存在，将创建默认配置: {self.json_path}")
                self._create_default_config()
                return
                
            with open(self.json_path, 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
                
                # 加载默认设置
                if "default" in config:
                    self.default_settings.update(config["default"])
                
                # 加载域名特定设置
                if "domains" in config:
                    self.domain_settings = config["domains"]
                
                print(f"[下载设置] 成功加载: 默认设置和 {len(self.domain_settings)} 个域名特定设置")
        except Exception as e:
            print(f"[下载设置错误] 配置文件读取失败，使用默认设置: {str(e)}")
    
    def _create_default_config(self):
        """创建默认的下载设置配置"""
        default_config = {
            "default": self.DEFAULT_SETTINGS.copy(),
            "domains": {
                "pubs.acs.org": {
                    "use_ctrl_s": False,
                    "ctrl_s_delay": 0,
                    "max_retries": 2,
                    "retry_delay": 5
                },
                "sciencedirect.com": {
                    "use_ctrl_s": True,
                    "ctrl_s_delay": 10,
                    "max_retries": 3,
                    "retry_delay": 15
                }
            }
        }
        try:
            with open(self.json_path, 'w', encoding='utf-8-sig') as f:
                json.dump(default_config, f, indent=2)
            print(f"[下载设置] 已创建默认配置文件: {self.json_path}")
        except Exception as e:
            print(f"[下载设置错误] 创建配置文件失败: {str(e)}")
    
    def get_settings_for_domain(self, domain: str) -> Dict:
        """获取指定域名的下载设置"""
        # 尝试直接匹配完整域名
        if domain in self.domain_settings:
            return self.domain_settings[domain]
        
        # 尝试匹配主域名（去掉子域名部分）
        parts = domain.split('.')
        if len(parts) >= 2:
            main_domain = parts[-2] + '.' + parts[-1]
            if main_domain in self.domain_settings:
                return self.domain_settings[main_domain]
        
        # 如果没有匹配，默认返回默认设置
        return self.default_settings
    
    def should_use_ctrl_s(self, domain: str) -> bool:
        """返回指定域名是否使用Ctrl+S操作"""
        settings = self.get_settings_for_domain(domain)
        return settings.get("use_ctrl_s", True)
    
    def get_ctrl_s_delay(self, domain: str) -> int:
        """返回指定域名Ctrl+S操作后的等待时间"""
        settings = self.get_settings_for_domain(domain)
        return settings.get("ctrl_s_delay", 5)
    
    def get_max_retries(self, domain: str) -> int:
        """返回指定域名的最大重试次数"""
        settings = self.get_settings_for_domain(domain)
        return settings.get("max_retries", 3)
    
    def get_retry_delay(self, domain: str) -> int:
        """返回指定域名的重试之间的延迟时间"""
        settings = self.get_settings_for_domain(domain)
        return settings.get("retry_delay", 10)


class DomainClickManager:
    """域名点击位置管理类"""
    def __init__(self):
        self.special_domains = {
            "oiccpress.com": "center",
            "ieeexplore.ieee.org": "center"
        }
    
    def get_click_position(self, domain: str) -> Tuple[int, int]:
        """获取指定域名的点击位置"""
        if domain in self.special_domains:
            # 特殊域名使用屏幕中心位置
            print(f"[域名点击] 使用特殊域名 {domain} 的中心位置")
            screen_width, screen_height = pyautogui.size()
            if self.special_domains[domain] == "center":
                print(f"[域名点击] 使用屏幕中心位置: ({screen_width // 2}, {screen_height // 2})")  
                return (screen_width // 2, screen_height // 2)
                
        # 默认返回屏幕左上角附近位置
        print(f"[域名点击] 使用默认位置: (700, 150)")
        return (700, 150)


class CSVManager:
    """CSV文件管理类"""
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.rows: List[Dict] = []
        self.fieldnames: List[str] = []
        
    def load_data(self) -> List[Dict]:
        """加载CSV数据，跳过DownloadStatus为Success的行"""
        print(f"[CSV] 正在读取文件: {self.csv_path}")
        try:
            with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                self.fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                self.rows = list(reader)
            
                # 筛选有DOI的论文
                papers = [row for row in self.rows if row.get('DOI', '').strip()]
            
                # 找到第一个DownloadStatus为空的行
                start_index = 0
                for i, row in enumerate(papers):
                    status = row.get('DownloadStatus', '').strip()
                    if not status :  # 只处理空状态的行
                        start_index = i
                        break
            
                # 从第一个可处理行开始，但跳过所有Success状态的行
                papers = papers[start_index:]
                papers = [row for row in papers if row.get('DownloadStatus', '').strip() != 'Success' or "Failed"]
            
                print(f"[CSV] 找到 {len(papers)} 篇需要处理的论文(有DOI且状态不为Success)，从第{start_index+1}行开始")
                return papers
        except Exception as e:
            print(f"[CSV错误] 文件读取失败: {str(e)}")
            return []

    def update_row_by_doi(self, doi: str, updates: Dict):
        """根据DOI更新行数据"""
        doi = doi.strip()
        updated = False
        
        # 检查是否有新字段
        field_names_changed = False
        for key in updates.keys():
            if key not in self.fieldnames:
                self.fieldnames.append(key)
                field_names_changed = True
                print(f"[CSV] 添加新字段: {key}")
        
        for row in self.rows:
            if row.get('DOI', '').strip() == doi:
                row.update(updates)
                updated = True
                print(f"[CSV] 已更新DOI={doi}的数据: {updates}")
                break
                
        if not updated:
            print(f"[CSV警告] 未找到DOI={doi}，无法更新数据")
            return
            
        # 写回文件
        self._save_to_file(field_names_changed)
    
    def _save_to_file(self, skip_field_check: bool = False):
        """保存数据到CSV文件"""
        try:
            with open(self.csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
                writer.writerows(self.rows)
            print("[CSV] 文件已更新")
        except Exception as e:
            print(f"[CSV错误] 写回文件失败: {str(e)}")


class DomainBranchManager:
    """域名分支管理类"""
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.branch_rules = {}
        
    def load_rules(self):
        """加载域名分支规则"""
        try:
            if not os.path.exists(self.json_path):
                print(f"[域名分支] 配置文件不存在，将创建一个新文件: {self.json_path}")
                self._create_default_config()
                return
                
            with open(self.json_path, 'r', encoding='utf-8-sig') as f:
                rules_list = json.load(f)
                
                # 将列表转换为字典，domain为键，direct为值
                self.branch_rules = {item["domain"]: item["direct"] for item in rules_list}
                print(f"[域名分支] 已加载 {len(self.branch_rules)} 条域名规则")
        except Exception as e:
            print(f"[域名分支错误] 配置文件读取失败: {str(e)}")
    
    def _create_default_config(self):
        """创建默认的域名分支配置（使用新格式）"""
        default_config = [
            {
                "domain": "pubs.acs.org",
                "direct": "1"
            },
            {
                "domain": "sciencedirect.com",
                "direct": "1"
            },
            {
                "domain": "pubs.rsc.org",
                "direct": "1"
            },
            {
                "domain": "example.com",
                "direct": "0"
            }
        ]
        try:
            with open(self.json_path, 'w', encoding='utf-8-sig') as f:
                json.dump(default_config, f, indent=2)
            print(f"[域名分支] 已创建默认配置文件: {self.json_path}")
        except Exception as e:
            print(f"[域名分支错误] 创建配置文件失败: {str(e)}")
    
    def get_domain_direct_value(self, domain: str) -> int:
        """获取指定域名的direct值，如果没有匹配项则返回0"""
        # 尝试直接匹配完整域名
        if domain in self.branch_rules:
            return self.branch_rules[domain]
        
        # 尝试匹配主域名（去掉子域名部分）
        parts = domain.split('.')
        if len(parts) >= 2:
            main_domain = parts[-2] + '.' + parts[-1]
            if main_domain in self.branch_rules:
                return self.branch_rules[main_domain]
        
        # 如果没有匹配，默认返回0（原分支）
        return 0


class DownloadTemplateManager:
    """下载模板管理类"""
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.download_templates = {}
        
    def load_templates(self):
        """加载下载模板"""
        try:
            if not os.path.exists(self.json_path):
                print(f"[下载模板] 配置文件不存在，将创建一个新文件: {self.json_path}")
                self._create_default_config()
                return
                
            with open(self.json_path, 'r', encoding='utf-8-sig') as f:
                self.download_templates = json.load(f)
                print(f"[下载模板] 已加载 {len(self.download_templates)} 个下载模板")
        except Exception as e:
            print(f"[下载模板错误] 配置文件读取失败: {str(e)}")
    
    def _create_default_config(self):
        """创建默认的下载模板配置"""
        default_config = {
            "pubs.acs.org": "https://pubs.acs.org/doi/pdf/{doi}",
            "nature.com": "https://www.nature.com/articles/{doi}.pdf",
            "springer.com": "https://link.springer.com/content/pdf/{doi}.pdf",
            "wiley.com": "https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
            "ieeexplore.ieee.org": "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}"
        }
        try:
            with open(self.json_path, 'w', encoding='utf-8-sig') as f:
                json.dump(default_config, f, indent=2)
            print(f"[下载模板] 已创建默认配置文件: {self.json_path}")
        except Exception as e:
            print(f"[下载模板错误] 创建配置文件失败: {str(e)}")
    
    def get_download_url(self, domain: str, doi: str, original_url: str = None) -> Optional[str]:
        """根据域名和DOI生成下载URL"""
        # 特殊处理pubs.rsc.org
        if domain == "pubs.rsc.org" and original_url:
            return self._handle_rsc_org(original_url)
            
        if domain in self.download_templates:
            template = self.download_templates[domain]
            
            # IEEE Explore特殊处理
            if domain == "ieeexplore.ieee.org":
                return self._handle_ieee_explore(template, doi)
            
            # 其他域名直接替换DOI
            download_url = template.replace("{doi}", doi)
            print(f"[下载模板] 生成下载URL: {download_url}")
            return download_url
        
        # 尝试匹配主域名（去掉子域名部分）
        parts = domain.split('.')
        if len(parts) >= 2:
            main_domain = parts[-2] + '.' + parts[-1]
            if main_domain in self.download_templates:
                template = self.download_templates[main_domain]
                
                # IEEE Explore特殊处理
                if main_domain == "ieeexplore.ieee.org":
                    return self._handle_ieee_explore(template, doi)
                
                download_url = template.replace("{doi}", doi)
                print(f"[下载模板] 生成下载URL: {download_url}")
                return download_url
        
        print(f"[下载模板警告] 未找到域名 {domain} 的下载模板")
        return None
    
    def _handle_rsc_org(self, original_url: str) -> str:
        """处理RSC的特殊URL格式"""
        print("[下载模板] RSC特殊处理")
        
        # 将原始URL转换为小写并替换articlelanding为articlepdf
        download_url = original_url.lower().replace("articlelanding", "articlepdf")
        print(f"[下载模板] 生成RSC下载URL: {download_url}")
        return download_url
    
    def _handle_ieee_explore(self, template: str, doi: str) -> str:
        """处理IEEE Explore的特殊DOI格式"""
        print("[下载模板] IEEE Explore特殊处理")
        
        # 提取DOI的最后一部分数字
        parts = doi.split('.')
        if len(parts) > 1:
            arnumber = parts[-1]
            print(f"[下载模板] 提取arnumber: {arnumber}")
            download_url = template.replace("{doi}", arnumber)
        else:
            print("[下载模板警告] IEEE Explore DOI格式异常，使用完整DOI")
            download_url = template.replace("{doi}", doi)
        
        print(f"[下载模板] 生成IEEE Explore下载URL: {download_url}")
        return download_url


class WebScraper:
    """网页内容抓取类"""
    BASE_URL = "https://www.baidu.com/"

    def __init__(self, use_selenium: bool = False):
        self.use_selenium = use_selenium
        self.screen_width, self.screen_height = pyautogui.size()
        self.driver = None  # Selenium驱动实例
        self.work_tab_open = False
        
    def __del__(self):
        """析构函数，确保关闭浏览器"""
        if self.driver:
            self.driver.quit()
    
    def fetch_html(self, doi: str) -> Tuple[Optional[str], Optional[str]]:
        """获取HTML内容"""
       
        return self._fetch_html_with_pyautogui(doi)

    def _is_baidu_url(self, url: Optional[str]) -> bool:
        if not url:
            return False
        candidate = str(url).strip().lower()
        return candidate == self.BASE_URL

    def open_base_page(self) -> bool:
        print(f"[基准页] 启动打开百度页: {self.BASE_URL}")
        ok = open_url(self.BASE_URL, browser_path=Config.EDGE_BROWSER_PATH)
        if not ok:
            err = get_last_open_url_error()
            if err:
                print(f"[基准页] 打开百度页失败: {err}")
            else:
                print("[基准页] 打开百度页失败")
            return False
        time.sleep(2)
        return True

    def ensure_base_page_current(self) -> bool:
        max_close_checks = 20
        close_checks = 0
        while True:
            current_url = self._get_current_url(allow_about_blank=True, quiet=True)
            if not current_url:
                print("[基准页][降级] URL读取失败，按策略不关闭标签，继续DOI流程")
                return True

            if self._is_baidu_url(current_url):
                print("[基准页] 已回到百度页，开始处理DOI")
                return True

            close_checks += 1
            if close_checks > max_close_checks:
                print("[基准页][保护] 连续检查超过上限，停止关闭并继续DOI流程")
                return True

            print(f"[基准页] 当前URL非百度，关闭当前标签: {current_url}")
            try:
                hotkey("close_tab")
            except Exception as e:
                print(f"[基准页] 关闭当前标签失败: {e}")
                return False
            time.sleep(1)
            self.work_tab_open = False

    def open_work_tab_with_url(self, url: str) -> bool:
        try:
            print(f"[工作Tab] 打开: {url}")
            hotkey("new_tab")
            time.sleep(0.8)
            hotkey("focus_address_bar")
            time.sleep(0.4)
            hotkey("select_all")
            _paste_url_to_address_bar(url)
            time.sleep(0.2)
            pyautogui.press("enter")
            pyautogui.press("enter")
            self.work_tab_open = True
            print(f"[工作Tab] 打开成功: {url}")
            return True
        except Exception as e:
            print(f"[浏览器会话] 工作标签打开失败，回退系统打开: {str(e)}")
            ok = open_url(url, browser_path=Config.EDGE_BROWSER_PATH)
            self.work_tab_open = bool(ok)
            if ok:
                print(f"[工作Tab] 回退系统打开成功: {url}")
            return ok

    def close_work_tab(self):
        if not self.work_tab_open:
            return
        try:
            print("[工作Tab] 关闭当前工作标签")
            hotkey("close_tab")
            time.sleep(1)
            print("[工作Tab] 关闭成功")
        except Exception as e:
            print(f"[工作Tab] 关闭失败: {str(e)}")
        finally:
            self.work_tab_open = False

    def resolve_final_url_with_pyautogui(self, doi: str) -> Optional[str]:
        """通过PyAutoGUI打开DOI页面并复制地址栏URL作为final_url"""
        print(f"[URL获取] 通过PyAutoGUI打开DOI页面: {doi}")
        try:
            doi_url = f"https://doi.org/{doi}"
            startup_confirmed = False

            for startup_attempt in range(1, 4):
                print(f"[URL启动尝试] DOI={doi} 第{startup_attempt}/3次打开工作标签")
                if not self.open_work_tab_with_url(doi_url):
                    startup_error = get_last_open_url_error()
                    if startup_error:
                        print(f"[URL启动确认] DOI={doi} 第{startup_attempt}/3次失败：工作标签打开失败，错误={startup_error}")
                    else:
                        print(f"[URL启动确认] DOI={doi} 第{startup_attempt}/3次失败：工作标签打开失败")
                    time.sleep(1)
                    continue

                print(f"[URL启动确认] DOI={doi} 第{startup_attempt}/3次成功：工作标签已打开")
                startup_confirmed = True
                break

            if not startup_confirmed:
                print(f"[URL启动失败] DOI={doi} 工作标签连续3次打开失败，终止当前DOI")
                return None

            print(f"[URL获取] 等待页面加载({Config.PAGE_LOAD_TIMEOUT}秒)...")
            time.sleep(Config.PAGE_LOAD_TIMEOUT)

            # 调用验证码处理逻辑（检测到则自动点击一次）
            # try:
            #     from captcha_verify import try_click_captcha
            #     try_click_captcha(max_wait_seconds=8.0)
            # except Exception as captcha_error:
            #     print(f"[验证码] 调用失败，继续后续流程: {captcha_error}")

            final_url = None
            for attempt in range(1, 4):
                try:
                    pyperclip.copy("")
                except Exception:
                    pass
                final_url = self._get_current_url()
                if final_url:
                    break
                print(f"[URL获取重试] 第{attempt}/3次读取地址栏失败，2秒后重试")
                time.sleep(2)

            if not final_url:
                print("[URL获取错误] 地址栏URL为空或读取失败")
                self.close_work_tab()
                return None

            print(f"[URL解析成功] DOI={doi} -> {final_url}")
            return final_url
        except Exception as e:
            print(f"[URL获取错误] PyAutoGUI获取final_url失败: {str(e)}")
            self.close_work_tab()
            return None

    def fetch_html_in_new_tab(self, url: str) -> Optional[str]:
        """在新标签页打开URL，抓取源码后关闭当前标签页"""
        print(f"[PyAutoGUI] 新标签页抓取HTML: {url}")
        try:
            if not self.open_work_tab_with_url(url):
                print("[PyAutoGUI错误] 打开新标签页失败")
                return None
            print(f"[PyAutoGUI] 等待页面加载({Config.PAGE_LOAD_TIMEOUT}秒)...")
            time.sleep(Config.PAGE_LOAD_TIMEOUT)
            html = self._get_page_source()
            return html
        except Exception as e:
            print(f"[PyAutoGUI错误] 新标签页抓取HTML失败: {str(e)}")
            return None
        finally:
            self.close_work_tab()
    
    
    def _fetch_html_with_pyautogui(self, doi: str) -> Tuple[Optional[str], Optional[str]]:
        """使用PyAutoGUI获取HTML"""
        print(f"[PyAutoGUI] 通过DOI获取HTML: {doi}")
        try:
            print("[PyAutoGUI] 启动浏览器...")
            if not open_url(
                f"https://doi.org/{doi}",
                browser_path=Config.EDGE_BROWSER_PATH,
            ):
                print("[PyAutoGUI错误] 浏览器启动失败")
                return None, None
            
            print(f"[PyAutoGUI] 等待页面加载({Config.PAGE_LOAD_TIMEOUT}秒)...")
            time.sleep(Config.PAGE_LOAD_TIMEOUT)
            
            # 获取最终URL
            final_url = self._get_current_url()
            if not final_url:
                return None, None
                
            # 获取HTML源码
            html = self._get_page_source()
            
            # 关闭标签页
            self._close_current_tab()
            
            return html, final_url
        except Exception as e:
            print(f"[PyAutoGUI错误] 浏览器操作失败: {str(e)}")
            return None, None
    
    def _get_current_url(self, allow_about_blank: bool = False, quiet: bool = False) -> Optional[str]:
        """获取当前浏览器URL"""
        try:
            pyperclip.copy('')
            hotkey("focus_address_bar")
            time.sleep(1)
            hotkey("select_all")
            time.sleep(1)
            hotkey("copy")
            pyautogui.press('esc')
            time.sleep(2)
            pyautogui.press('esc')
            copied = (pyperclip.paste() or "").strip()
            if not copied:
                if not quiet:
                    print("[PyAutoGUI警告] 剪贴板为空，复制url失败")
                return None
            if allow_about_blank and (copied == "about:blank" or copied.startswith("file://")):
                return copied
            if not (copied.startswith("http://") or copied.startswith("https://")):
                if not quiet:
                    print(f"[PyAutoGUI警告] url复制错误: {copied}")
                return None
            return copied
        except Exception as e:
            if not quiet:
                print(f"[PyAutoGUI错误] 获取URL失败: {str(e)}")
            return None
    
    def _get_page_source(self) -> Optional[str]:
        """获取页面源代码"""
        try:
            print("[PyAutoGUI] 获取页面源代码...")
            hotkey("view_source")
            time.sleep(10)
            hotkey("select_all")
            time.sleep(1)
            hotkey("copy")
            time.sleep(3)
            return pyperclip.paste()
        except Exception as e:
            print(f"[PyAutoGUI错误] 获取源码失败: {str(e)}")
            return None
    
    def _close_current_tab(self):
        """关闭当前标签页"""
        try:
            print("[PyAutoGUI] 关闭标签页...")
            hotkey("close_tab")
            time.sleep(2)
        except Exception as e:
            print(f"[PyAutoGUI警告] 关闭标签页失败: {str(e)}")


class FileHandler:
    """文件处理类"""
    @staticmethod
    def save_html_content(content: str, filename: str) -> Optional[str]:
        """保存HTML内容到文件"""
        filename = FileHandler.normalize_filename(filename)
        filepath = os.path.join(Config.DOWNLOAD_PATH, f"{filename}.txt")
        try:
            if isinstance(content, tuple):
                content = content[0]  # Take the first element if it's a tuple
            elif not isinstance(content, str):
                content = str(content)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            if os.path.exists(filepath):
                print(f"[文件] HTML内容已保存到: {filepath}")
                return filepath
            else:
                print("[文件警告] 文件保存后未找到，可能保存失败")
                return None
        except Exception as e:
            print(f"[文件错误] 保存失败: {str(e)}")
            return None
    
    @staticmethod
    def normalize_filename(filename: str) -> str:
        """标准化文件名，移除无效字符"""
        return re.sub(r'[\\/*?:"<>|]', "_", filename)
    
    @staticmethod
    def is_document_link(url: str) -> bool:
        """检查URL是否是文档链接(PDF)"""
        if not url:
            return False
            
        # 检查URL是否以文档扩展名结尾
        ext = url.split('.')[-1].lower()
        if ext in Config.DOCUMENT_EXTENSIONS:
            return True
            
        # 检查URL中是否包含文档扩展名(可能带参数)
        pattern = r'\.(pdf)(\?|$|/)'
        return bool(re.search(pattern, url.lower()))
    
    @staticmethod
    def extract_main_domain(url: str) -> Optional[str]:
        """从URL中提取主域名"""
        if not url:
            return None
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            return domain
        except Exception as e:
            print(f"[域名解析错误] URL={url}, 错误: {str(e)}")
            return None


class PaperExtractor:
    """论文处理类"""
    def __init__(self, json_path: str):
        self.json_path = json_path
        self._last_is_full_supp = False  # 确保初始化
        
    def extract_paper_url(self, txt_path: str, doi: str) -> Optional[str]:
        """从HTML文件提取Paper链接(仅返回文档链接)"""
        print(f"[Paper] 提取Paper文档链接: {txt_path}")
        try:
            filename = os.path.basename(txt_path)
            domain = filename.split('_')[0]  # 获取主域名
            print(f"[Paper] 解析主域名: {domain}")
        
            # 从JSON文件查找关键词
            keywords_info = self._get_keywords_from_json(domain)
            if not keywords_info:
                return None
                
            paper_keywords = keywords_info['keywords']
            print(f"[Paper] 找到Paper关键词: {paper_keywords}")
            
            if not paper_keywords:
                print("[Paper警告] 未找到有效的Paper关键词")
                return None
            
            # 读取HTML内容
            content = self._read_html_content(txt_path)

            # 特殊处理：当关键词包含"pdf"时
            if "pdf" in paper_keywords:
                result = self._special_extraction_for_pdf_keyword(content, paper_keywords)
                if result:
                    return result
                print("[Paper] 特殊处理未找到匹配，尝试常规方法")
            
            #特殊处理：当关键词包含"md5"时
            elif "md5" in paper_keywords:
                result = self._special_extraction_for_md5_keyword(content, paper_keywords)
                if result:
                    return result
                print("[Paper] 特殊处理未找到匹配，尝试常规方法")
            
            #特殊处理：当关键词包含"downloadpdf"时
            elif "downloadpdf" in paper_keywords:
                urls = re.findall(r'content=[\'"]?([^\'" >]+)', content)
                print(f"[Paper] 共找到 {len(urls)} 个链接")
            
                # 查找有效链接
                return self._find_valid_paper_url(urls, paper_keywords, domain, doi)
                

            # 常规查找链接
            else:
                urls = re.findall(r'href=[\'"]?([^\'" >]+)', content)
                print(f"[Paper] 共找到 {len(urls)} 个链接")
            
                # 查找有效链接
                return self._find_valid_paper_url(urls, paper_keywords, domain, doi)
            
        except Exception as e:
            print(f"[Paper错误] 提取失败: {str(e)}")
            return None
    
    def _special_extraction_for_pdf_keyword(self, html_content: str, keywords: List[str]) -> Optional[str]:
        """专门处理当keywords中包含'pdf'的特殊情况"""
        print("[特殊处理] 检测到关键词中包含'pdf'，启动特殊解析模式")
        
        # 创建正则模式匹配同时包含class和href的属性组合
        pattern = r'class\s*=\s*["\']([^"\']*)["\'][^>]*?href\s*=\s*["\']([^"\']*)["\']'
        matches = re.findall(pattern, html_content)  # 修正了参数传递方式
        
        if not matches:
            print("[特殊处理] 未找到同时包含class和href的属性组合")
            return None
        
        print(f"[特殊处理] 找到 {len(matches)} 个class+href属性组合")
        
        # 准备用于搜索的关键词（排除pdf）
        search_keywords = keywords[0]
    
        # 匹配class属性中包含关键词的链接
        for class_val, href_val in matches:
            # 检查class值是否包含任一关键词
            if search_keywords in class_val:
                print(f"[特殊处理] 找到匹配链接: href={href_val} | class={class_val}")
                return href_val
        
        print("[特殊处理] 未找到匹配的class和href组合")
        return None
    
    def _special_extraction_for_md5_keyword(self, html_content: str, keywords: List[str]) -> Optional[str]:
        """专门处理当keywords中包含'md5'的特殊情况"""
        print("[特殊处理] 检测到关键词中包含'md5'，启动特殊解析模式")
    
        # 改进1：修正正则表达式，使用捕获组提取各部分值
        pattern = r'\{"md5":"([a-f0-9]{32})","pid":"([^"]+)"\},"pii":"([A-Z0-9]{10,})"'
        # 改进2：实际在HTML内容中搜索匹配项，而不是错误地解析正则表达式
        matches = re.findall(pattern, html_content)
    
        if not matches:
            print("[特殊处理] 未找到同时包含md5和pid的属性组合")
            return None
    
        print(f"[特殊处理] 找到 {len(matches)} 个md5+pid+pii属性组合")
    
        # 改进3：准备用于搜索的关键词（排除md5）
        search_keywords = "mainext"  # 关键词可以根据实际需要调整
    
        # 改进4：遍历所有匹配项
        for match in matches:
            md5_val, pid_val, pii_val = match
            # 改进5：检查pid值是否包含任何关键词
            if any(keyword.lower() in pid_val.lower() for keyword in search_keywords):
                print(f"[特殊处理] 找到匹配链接: md5={md5_val} | pid={pid_val}")
                # 改进6：正确构造完整的URL
                return f"https://www.sciencedirect.com/science/article/pii/{pii_val}/pdfft?md5={md5_val}&pid={pid_val}-mainext.pdf"
    
        print("[特殊处理] 没有找到包含指定关键词的pid值")
        return None
    
    def _get_keywords_from_json(self, domain: str) -> Optional[Dict]:
        """从JSON获取关键词配置"""
        try:
            with open(self.json_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                
            for item in data:
                if not all(key in item for key in ('url', 'keywords')):
                    continue
                    
                if 'url' in item and domain in str(item['url']):
                    return item
                    
            print(f"[Paper] 未找到匹配的Paper关键词: {domain}")
            return None
        except Exception as e:
            print(f"[Paper错误] JSON读取失败: {str(e)}")
            return None
    
    def _find_valid_paper_url(self, urls: List[str], keywords: List[str], domain: str, doi: str) -> Optional[str]:
        """查找有效Paper链接"""
        valid_urls = []
        keyword = keywords[0]
        for url in urls:
            if keyword in url:
                valid_urls.append(url)
                print(f"[Paper] 找到匹配链接: {url}")
            else:
                continue
        
        if not valid_urls:
            print(f"[Paper] 未找到包含关键词的文档链接")
            return None
            
        # 返回链接
        paper_url = valid_urls[0]
        
        # 确保URL完整
        if not paper_url.startswith('http') and not paper_url.startswith("//"+domain):
            paper_url = f"https://{domain}/{paper_url.lstrip('/')}"
        elif not paper_url.startswith('http'):
            paper_url = f"https://{paper_url.lstrip('/')}"
        else:
            paper_url = paper_url.strip()
    
        return paper_url
    
    def _read_html_content(self, txt_path: str) -> str:
        """读取HTML文件内容"""
        with open(txt_path, 'r', encoding='utf-8') as f:
            return f.read()


class FileDownloader:
    """文件下载类"""
    def __init__(
        self,
        download_folder: str,
        settings_manager: DownloadSettingsManager,
        web_scraper: Optional[WebScraper] = None,
    ):
        self.download_folder = download_folder
        self.settings_manager = settings_manager
        self.web_scraper = web_scraper
        self.last_downloaded_file = None  # 记录最后下载的文件名
        self.domain_click_manager = DomainClickManager()  # 新增的点击位置管理器
        self.download_tab_opened = False
        os.makedirs(self.download_folder, exist_ok=True)
        
    def download_and_rename(self, doi: str, url: str, domain: str) -> Tuple[bool, Optional[str]]:
        """
        下载并重命名文件
        1. 获取初始文件列表
        2. 打开URL
        3. 模拟下载操作（如果需要）
        4. 判断是否下载成功
        5. 失败时重试
        
        返回: (下载是否成功, 文件名)
        """
        print(f"[下载] 开始处理: {doi} (域名: {domain})")
        max_retries = self.settings_manager.get_max_retries(domain)
        
        # 获取初始文件快照（多目录监听）
        initial_snapshot = self._snapshot_watch_dirs()
        
        # 打开URL
        self._open_url_in_browser(url)
        time.sleep(Config.PAGE_LOAD_TIMEOUT)  # 等待页面加载
        
        try:
            for attempt in range(1, max_retries + 1):
                print(f"[下载] 尝试 #{attempt}/{max_retries}")
                success, filename = self._download_attempt(doi, url, domain, attempt, initial_snapshot)
                if success:
                    self.last_downloaded_file = filename
                    return True, filename
                    
                if attempt < max_retries:
                    delay = self.settings_manager.get_retry_delay(domain)
                    hotkey("dismiss_dialog")  # 关闭当前标签页
                    print(f"[下载] 将在 {delay} 秒后重试...")
                    time.sleep(delay)
        
            print(f"[下载] 所有尝试失败，跳过: {doi}")
            return False, None
        finally:
            # 无论成功与否，在所有尝试完成后关闭浏览器
            self._cleanup_after_download()
    
    def download_with_template(self, doi: str, url: str, domain: str) -> Tuple[bool, Optional[str]]:
        """使用模板生成的URL下载文件，支持重试"""
        print(f"[下载] 使用模板URL下载: {url} (域名: {domain})")
        max_retries = self.settings_manager.get_max_retries(domain)
        
        # 获取初始文件快照（多目录监听）
        initial_snapshot = self._snapshot_watch_dirs()
        
        # 打开URL
        self._open_url_in_browser(url)
        
        try:
            for attempt in range(1, max_retries + 1):
                print(f"[下载] 尝试 #{attempt}/{max_retries}")
                success, filename = self._download_template_attempt(doi, url, domain, attempt, initial_snapshot)
                if success:
                    self.last_downloaded_file = filename
                    return True, filename
                    
                if attempt < max_retries:
                    delay = self.settings_manager.get_retry_delay(domain)
                    print(f"[下载] 将在 {delay} 秒后重试...")
                    time.sleep(delay)
        
            print(f"[下载] 所有尝试失败，跳过: {doi}")
            return False, None
        finally:
            # 无论成功与否，在所有尝试完成后关闭浏览器
            self._cleanup_after_download()
    
    def _download_attempt(
        self,
        doi: str,
        url: str,
        domain: str,
        attempt: int,
        initial_snapshot: Dict[str, Set[str]],
    ) -> Tuple[bool, Optional[str]]:
        """单次下载尝试"""
        # 尝试模拟Ctrl+S（如果需要）
        ctrl_s_delay = 40
        if self.settings_manager.should_use_ctrl_s(domain):
            print("[下载] 尝试模拟Ctrl+S保存")
            self._simulate_save(domain,doi)  # 传递domain参数
            ctrl_s_delay = self.settings_manager.get_ctrl_s_delay(domain)
            
        # 等待下载完成
        time.sleep(ctrl_s_delay)
        
        # 检查是否下载成功
        downloaded_filename = self._get_downloaded_filename(initial_snapshot, doi)
        
        if downloaded_filename:
            print(f"[下载] 下载成功 (尝试 {attempt})，文件: {downloaded_filename}")
            return True, downloaded_filename
        
        print(f"[下载] 下载失败 (尝试 {attempt})")
        return False, None
    
    def _download_template_attempt(
        self,
        doi: str,
        url: str,
        domain: str,
        attempt: int,
        initial_snapshot: Dict[str, Set[str]],
    ) -> Tuple[bool, Optional[str]]:
        """使用模板的单次下载尝试"""
        time.sleep(15)  # 等待页面加载
        
        # 尝试模拟Ctrl+S（如果需要）
        ctrl_s_delay = 0
        if self.settings_manager.should_use_ctrl_s(domain):
            print("[下载] 尝试模拟Ctrl+S保存")
            self._simulate_save(domain,doi)
            ctrl_s_delay = self.settings_manager.get_ctrl_s_delay(domain)
            
        # 等待下载完成
        time.sleep(ctrl_s_delay)
        
        # 检查是否下载成功
        downloaded_filename = self._get_downloaded_filename(initial_snapshot, doi)
        
        if downloaded_filename:
            print(f"[下载] 下载成功 (尝试 {attempt})，文件: {downloaded_filename}")
            return True, downloaded_filename
        
        print(f"[下载] 下载失败 (尝试 {attempt})")
        return False, None
    
    def _open_url_in_browser(self, url: str):
        """在浏览器新标签页打开URL"""
        self.download_tab_opened = False
        if self.web_scraper:
            ok = self.web_scraper.open_work_tab_with_url(url)
            self.download_tab_opened = bool(ok)
            if not ok:
                print("[浏览器错误] 下载阶段打开工作标签失败")
            return
        try:
            print("[浏览器] 新标签页打开URL...")
            hotkey("new_tab")
            time.sleep(1)
            hotkey("focus_address_bar")
            time.sleep(0.5)
            hotkey("select_all")
            _paste_url_to_address_bar(url)
            time.sleep(0.2)
            pyautogui.press("enter")
            time.sleep(0.5)
            pyautogui.press("enter")
            self.download_tab_opened = True
            print(f"[浏览器] 已在新标签页打开URL: {url}")
        except Exception as e:
            print(f"[浏览器警告] 新标签页打开失败，回退系统打开: {str(e)}")
            if not open_url(url, browser_path=Config.EDGE_BROWSER_PATH):
                print("[浏览器错误] 打开URL失败")
                return
            self.download_tab_opened = True
            print(f"[浏览器] 已回退系统方式打开URL: {url}")
    
    def _cleanup_after_download(self):
        """下载完成后清理下载工作标签"""
        try:
            print("[工作Tab] 下载阶段清理工作标签")
            if not self.download_tab_opened:
                print("[工作Tab] 下载阶段未打开工作标签，跳过关闭")
                return
            if self.web_scraper:
                self.web_scraper.close_work_tab()
                print("[工作Tab] 下载阶段工作标签已关闭")
                return
            for i in range(2):
                try:
                    hotkey("close_tab")
                    time.sleep(1)
                    print(f"[工作Tab] 下载标签关闭完成(尝试{i + 1}/2)")
                    break
                except Exception as e:
                    print(f"[工作Tab] 下载标签关闭失败(尝试{i + 1}/2): {str(e)}")
            print("[工作Tab] 下载阶段清理完成")
        except Exception as e:
            print(f"[清理错误] 清理过程中出错: {str(e)}")
        finally:
            self.download_tab_opened = False
    
    def _simulate_save(self, domain: str = None,doi: str = None):
        """模拟保存文件操作，支持根据域名调整点击位置"""
        try:
            print("[下载] 模拟Ctrl+S保存文件...")
            time.sleep(20)
            doi = str(doi or "").strip().replace("/", "_")  # 替换斜杠以避免文件名问题
            if not doi:
                doi = "unknown_doi"
            save_name = doi + "_pdf.pdf"
            save_target = os.path.join(self.download_folder, save_name)
            if not self._predelete_existing_target_file(save_target):
                print(f"[下载警告] 保存预清理失败，已中止本次模拟保存: {save_target}")
                return
            
            # 获取点击位置
            if domain :
                x, y = self.domain_click_manager.get_click_position(domain)
            else:
                x, y = 700, 150  # 默认位置
            pyautogui.click(x=x, y=y)
            time.sleep(5)
            hotkey("print_page")
            time.sleep(5)
            pyautogui.press('enter')
            time.sleep(5)

            if is_windows():
                # Windows保持原有路径输入逻辑
                pyautogui.write(save_target, interval=0.03)
            else:
                # mac: 使用“前往文件夹 + 粘贴”避免输入法把路径字符改写
                save_dir = os.path.abspath(self.download_folder)
                print(f"[下载保存] mac路径跳转目录: {save_dir}")
                pyperclip.copy(save_dir)
                hotkey("go_to_folder")
                time.sleep(0.8)
                hotkey("paste")
                time.sleep(0.3)
                pyautogui.press("enter")
                time.sleep(0.8)
                pyperclip.copy(save_name)
                hotkey("select_all")
                time.sleep(0.2)
                hotkey("paste")
                print(f"[下载保存] mac文件名: {save_name}")
            time.sleep(2)
            pyautogui.press('enter')
            time.sleep(1)
            pyautogui.press('enter',presses=3,interval=0.2)
            time.sleep(2)

        except Exception as e:
            print(f"[下载警告] 模拟保存失败: {str(e)}")

    def _predelete_existing_target_file(self, target_path: str) -> bool:
        """保存前预清理同名文件（策略3）。"""
        target_abs = os.path.abspath(target_path)
        target_dir = os.path.abspath(self.download_folder)
        try:
            if os.path.commonpath([target_abs, target_dir]) != target_dir:
                print(f"[保存预清理] 路径安全校验失败，目标不在下载目录内: {target_abs}")
                return False
        except Exception as e:
            print(f"[保存预清理] 路径校验异常: {e}")
            return False

        ext = os.path.splitext(target_abs)[1].lower().lstrip(".")
        allowed_exts = {str(item).lower().lstrip(".") for item in Config.DOCUMENT_EXTENSIONS}
        if ext and ext not in allowed_exts:
            print(f"[保存预清理] 扩展名不在允许列表，拒绝删除: {target_abs}")
            return False

        if not os.path.exists(target_abs):
            print(f"[保存预清理] 目标不存在，无需删除: {target_abs}")
            return True
        if not os.path.isfile(target_abs):
            print(f"[保存预清理] 目标不是普通文件，拒绝删除: {target_abs}")
            return False

        print(f"[保存预清理] 检测到同名文件，准备删除: {target_abs}")
        try:
            os.remove(target_abs)
            print(f"[保存预清理] 删除成功: {target_abs}")
            return True
        except Exception as e:
            print(f"[保存预清理] 删除失败: {target_abs} | {e}")
            return False
            
    def _get_watch_dirs(self) -> List[str]:
        dirs = [self.download_folder] + list(Config.EXTRA_WATCH_DIRS)
        normalized: List[str] = []
        for d in dirs:
            abs_dir = os.path.abspath(d)
            if abs_dir not in normalized:
                normalized.append(abs_dir)
        return normalized

    def _snapshot_watch_dirs(self) -> Dict[str, Set[str]]:
        snapshots: Dict[str, Set[str]] = {}
        watch_dirs = self._get_watch_dirs()
        print(f"[下载监听] 监听目录: {watch_dirs}")
        for watch_dir in watch_dirs:
            try:
                snapshots[watch_dir] = set(os.listdir(watch_dir)) if os.path.isdir(watch_dir) else set()
                print(f"[下载监听] 初始快照: {watch_dir} 文件数={len(snapshots[watch_dir])}")
            except Exception:
                snapshots[watch_dir] = set()
                print(f"[下载监听警告] 无法读取目录: {watch_dir}")
        return snapshots

    def _move_download_to_target(self, source_path: str) -> str:
        os.makedirs(self.download_folder, exist_ok=True)
        target_dir = os.path.abspath(self.download_folder)
        source_abs = os.path.abspath(source_path)
        source_dir, source_name = os.path.split(source_abs)

        if os.path.abspath(source_dir) == target_dir:
            print(f"[下载归集] 文件已在目标目录，无需移动: {source_abs}")
            return source_abs

        base, ext = os.path.splitext(source_name)
        target_path = os.path.join(target_dir, source_name)
        counter = 1
        while os.path.exists(target_path):
            target_path = os.path.join(target_dir, f"{base}_{counter}{ext}")
            counter += 1

        try:
            print(f"[下载归集] 开始移动文件: {source_abs} -> {target_path}")
            shutil.move(source_abs, target_path)
            print(f"[下载归集] 移动成功: {target_path}")
            return target_path
        except Exception as e:
            print(f"[下载警告] 文件归集失败，保留原位置: {source_abs}，错误: {str(e)}")
            return source_abs

    def _recent_candidates_summary(self, limit_per_dir: int = 3) -> str:
        summaries: List[str] = []
        for watch_dir in self._get_watch_dirs():
            if not os.path.isdir(watch_dir):
                summaries.append(f"{watch_dir}(目录不存在)")
                continue
            try:
                files = []
                for name in os.listdir(watch_dir):
                    full_path = os.path.join(watch_dir, name)
                    if os.path.isfile(full_path):
                        files.append((name, os.path.getmtime(full_path)))
                files.sort(key=lambda item: item[1], reverse=True)
                recent = [name for name, _ in files[:limit_per_dir]]
                summaries.append(f"{watch_dir} 最近文件={recent}")
            except Exception as e:
                summaries.append(f"{watch_dir}(读取失败:{e})")
        return " | ".join(summaries)

    def _find_new_downloaded_file(
        self,
        initial_snapshot: Dict[str, Set[str]],
    ) -> Optional[Tuple[str, str, str]]:
        current_snapshot = self._snapshot_watch_dirs()
        temp_extensions = {"crdownload", "part", "tmp", "download"}
        candidates: List[Tuple[str, float]] = []

        for watch_dir, current_files in current_snapshot.items():
            previous_files = initial_snapshot.get(watch_dir, set())
            new_files = current_files - previous_files
            if new_files:
                print(f"[下载检测] 目录={watch_dir} 新增候选={sorted(list(new_files))}")

            for filename in new_files:
                ext = filename.split(".")[-1].lower() if "." in filename else ""
                if ext in temp_extensions:
                    continue
                if ext not in Config.DOCUMENT_EXTENSIONS:
                    continue
                source_path = os.path.join(watch_dir, filename)
                if os.path.isfile(source_path):
                    candidates.append((source_path, os.path.getmtime(source_path)))

        if not candidates:
            print("[下载检测] 未找到符合条件的新文件")
            return None

        print(f"[下载检测] 匹配候选数量={len(candidates)}")
        source_path = max(candidates, key=lambda item: item[1])[0]
        target_path = self._move_download_to_target(source_path)
        filename = os.path.basename(target_path)
        return source_path, target_path, filename

    def _get_downloaded_filename(
        self,
        initial_snapshot: Dict[str, Set[str]],
        doi: str,
    ) -> Optional[str]:
        """获取新下载的文件名（支持多目录监听和自动归集）"""
        found = self._find_new_downloaded_file(initial_snapshot)
        if not found:
            print(f"[下载未命中] DOI={doi} 未检测到新增下载文件")
            print(f"[下载未命中] 最近文件摘要: {self._recent_candidates_summary()}")
            return None

        source_path, target_path, filename = found
        print(f"[下载成功] DOI={doi} 文件={filename} 来源={source_path} 目标={target_path}")
        target_dir = os.path.abspath(self.download_folder)
        if os.path.abspath(os.path.dirname(target_path)) == target_dir:
            print(f"[下载目录确认] 文件已统一归集到: {target_dir}")
        if os.path.exists(target_path):
            try:
                size_bytes = os.path.getsize(target_path)
                print(f"[下载落盘确认] DOI={doi} 路径={target_path} 大小={size_bytes} bytes")
            except Exception as e:
                print(f"[下载落盘确认警告] DOI={doi} 已找到文件但读取大小失败: {e}")
        else:
            print(f"[下载落盘确认警告] DOI={doi} 目标文件不存在: {target_path}")
        return filename


class BrowserController:
    """浏览器控制类"""
    def __init__(self):
        pass

    def open_url_in_browser(self, url: str):
        """在默认浏览器中打开URL（Windows优先Edge）"""
        open_url(url, browser_path=Config.EDGE_BROWSER_PATH)
        print(f"[浏览器] 已打开URL: {url}")


class LoginManager:
    """登录管理类"""

    def __init__(self, json_path: str):
        self.json_path = json_path
        self.login_domains = set()
        self.login_context = LoginContext(base_dir=_BUNDLE_DIR)
        self.legacy_fallback = LegacyLoginFallback()

    def load_config(self):
        """加载登录配置"""
        try:
            if not os.path.exists(self.json_path):
                print(f"[登录配置] 配置文件不存在，将创建默认配置: {self.json_path}")
                self._create_default_config()
                return

            with open(self.json_path, 'r', encoding='utf-8-sig') as f:
                domains = json.load(f)
                normalized = [normalize_domain(item) for item in domains]
                self.login_domains = {item for item in normalized if item}
                print(f"[登录配置] 已加载 {len(self.login_domains)} 个需要登录的域名")
        except Exception as e:
            print(f"[登录配置错误] 配置文件读取失败: {str(e)}")

    def _create_default_config(self):
        """创建默认的登录配置"""
        default_domains = [
            "pubs.acs.org",
            "sciencedirect.com",
            "link.springer.com",
            "tandfonline.com",
            "advanced.onlinelibrary.wiley.com",
            "onlinelibrary.wiley.com",
            "aiche.onlinelibrary.wiley.com",
            "analyticalsciencejournals.onlinelibrary.wiley.com",
            "iopscience.iop.org",
            "ieeexplore.ieee.org",
            "karger.com",
            "pubs.rsc.org",
        ]
        try:
            with open(self.json_path, 'w', encoding='utf-8-sig') as f:
                json.dump(default_domains, f, indent=2)
            print(f"[登录配置] 已创建默认配置文件: {self.json_path}")
            self.login_domains = set(default_domains)
        except Exception as e:
            print(f"[登录配置错误] 创建配置文件失败: {str(e)}")

    def needs_login(self, domain: str) -> bool:
        """检查指定域名是否需要登录"""
        normalized = normalize_domain(domain)
        if normalized in self.login_domains:
            return True

        parts = normalized.split('.')
        if len(parts) >= 2:
            main_domain = '.'.join(parts[-2:])
            if main_domain in self.login_domains:
                return True

        return False

    def perform_login(self, domain: str) -> bool:
        """执行登录操作（插件路由 + legacy兜底）"""
        if not self.needs_login(domain):
            print(f"[登录结果] domain={domain} -> Skipped(无需登录)")
            return True

        normalized = normalize_domain(domain)
        try:
            handler = resolve_handler(normalized)
            if handler:
                print(f"[登录路由] {normalized} -> {handler.handler_name}")
                print(f"[登录执行] handler={handler.handler_name} domain={normalized}")
                result = bool(handler.login(normalized, self.login_context))
                print(f"[登录结果] domain={normalized} -> {'Success' if result else 'Failed'}")
                return result

            print(f"[登录路由] {normalized} -> 未命中")
            print(f"[登录兜底] 使用legacy逻辑")
            result = bool(self.legacy_fallback.perform_login(normalized, self.login_context))
            print(f"[登录结果] domain={normalized} -> {'Success' if result else 'Failed'}")
            return result
        except Exception as e:
            print(f"[登录错误] handler执行异常: domain={normalized}, error={e}")
            print(f"[登录兜底] 使用legacy逻辑")
            try:
                result = bool(self.legacy_fallback.perform_login(normalized, self.login_context))
            except Exception as fallback_error:
                print(f"[登录错误] legacy执行异常: domain={normalized}, error={fallback_error}")
                result = False
            print(f"[登录结果] domain={normalized} -> {'Success' if result else 'Failed'}")
            return result


class PaperProcessor:
    """论文处理主类"""
    def __init__(self):
        Config.ensure_directories_exist()
        
        # 初始化组件
        self.csv_manager = CSVManager(Config.CSV_PATH)
        self.web_scraper = WebScraper(Config.USE_SELENIUM)
        self.paper_extractor = PaperExtractor(Config.JSON_PATH)
        
        # 下载设置管理
        self.download_settings_manager = DownloadSettingsManager(Config.DOWNLOAD_SETTINGS_JSON)
        self.download_settings_manager.load_settings()
        
        # 文件下载器需要下载设置管理器
        self.file_downloader = FileDownloader(
            Config.PAPER_DOWNLOAD_FOLDER,
            self.download_settings_manager,
            self.web_scraper,
        )
        
        # 域名分支管理
        self.domain_branch_manager = DomainBranchManager(Config.DOMAIN_BRANCH_JSON)
        self.domain_branch_manager.load_rules()
        
        # 下载模板管理
        self.download_template_manager = DownloadTemplateManager(Config.DOWNLOAD_TEMPLATE_JSON)
        self.download_template_manager.load_templates()
        
        # 登录管理
        self.login_manager = LoginManager(Config.LOGIN_CONFIG_JSON)
        self.login_manager.load_config()
        
        # 浏览器控制器
        self.browser_controller = BrowserController()
        
        # 运行状态
        self.start_time = datetime.now()
        self.screen_width, self.screen_height = pyautogui.size()
        
        # 打印开始信息
        self._print_startup_info()
    
    def __del__(self):
        """析构函数，确保关闭所有资源"""
        if hasattr(self, 'web_scraper') and hasattr(self.web_scraper, 'driver') and self.web_scraper.driver:
            self.web_scraper.driver.quit()
    
    def _print_startup_info(self):
        """打印启动信息"""
        print(f"\n{'='*50}")
        print(f"论文处理程序启动 - {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"HTML保存路径: {Config.DOWNLOAD_PATH}")
        print(f"Paper下载文件夹: {Config.PAPER_DOWNLOAD_FOLDER}")
        print(f"论文列表文件: {Config.CSV_PATH}")
        print(f"域名分支配置文件: {Config.DOMAIN_BRANCH_JSON}")
        print(f"下载模板配置文件: {Config.DOWNLOAD_TEMPLATE_JSON}")
        print(f"下载设置配置文件: {Config.DOWNLOAD_SETTINGS_JSON}")
        print(f"登录配置文件: {Config.LOGIN_CONFIG_JSON}")
        print(f"使用{'Selenium' if Config.USE_SELENIUM else 'PyAutoGUI'}方案")
        print(f"目标文件类型: {', '.join(Config.DOCUMENT_EXTENSIONS)}")
        print(f"{'='*50}\n")
    
    def run(self):
        """主运行流程"""
        papers = self.csv_manager.load_data()
        if not papers:
            print("[错误] 无有效论文数据，程序退出")
            return

        if not self.web_scraper.open_base_page():
            print("[基准页错误] 启动阶段打开百度页失败，程序退出")
            return
        
        total = len(papers)
        print(f"[处理开始] 共 {total} 篇论文，预计时间: ~{total * Config.DELAY_BETWEEN_PAPERS // 60}分钟")
        
        success_count = 0
        for i, paper in enumerate(papers, 1):
            # 处理单篇论文
            result = self.process_paper(paper, i, total)
            if result:
                success_count += 1
                
            # 等待间隔
            if i < total:
                self._wait_between_papers(i, total)
            
        self._print_summary(success_count, total)
        self.web_scraper.close_work_tab()
        print("[工作Tab] 全部论文处理完成，已执行收尾清理")
    
    def process_paper(self, paper: Dict, index: int, total: int) -> bool:
        """处理单篇论文"""
        self._print_progress(index, total, paper)
        doi = paper.get('DOI', '').strip()
        paper_id = paper.get('Key', f"paper_{index}")
        
        if not doi:
            print("[跳过] 无DOI，跳过处理")
            return False
        try:
            if not self.web_scraper.ensure_base_page_current():
                print("[基准页错误] 未能回到百度页，跳过当前DOI")
                return False

            # 阶段1: 通过PyAutoGUI获取最终URL并提取域名
            final_url = self._get_final_url(doi)
            if not final_url:
                return False
                
            domain = FileHandler.extract_main_domain(final_url)
            
            # 阶段2: 在当前已打开页面执行登录检查（不关闭当前页）
            if domain and self.login_manager.needs_login(domain):
                print(f"[登录] 检测到需要登录的域名: {domain}")
                self.login_manager.perform_login(domain)
                time.sleep(10)  # 等待登录完成
                
            # 阶段3: 新开标签页获取并保存HTML内容（抓取后仅关闭该标签页）
            html = self._get_html_content(final_url)
            if not html:
                return False
                
            file_path = self._save_html(html, final_url, paper_id, doi)
            if not file_path:
                return False
            
            self.csv_manager.update_row_by_doi(doi, {'HTMLFile': file_path})

            normalized_domain = normalize_domain(domain) if domain else ""
            if normalized_domain == "link.springer.com":
                print("[Springer专用] 命中 link.springer.com，跳过direct判定，进入专用流程")
                return self._process_springer_special(doi, file_path, final_url, domain)
                
            # 检查是否需要使用新分支
            use_new_branch = False
            if domain:
                # 获取域名的direct值
                direct_value = self.domain_branch_manager.get_domain_direct_value(domain)
                print(f"[域名分支] 域名: {domain}, direct值: {direct_value}")
                
                # 如果direct值为1，使用新分支
                if direct_value == "1":
                    print("[域名分支] 进入新分支处理流程")
                    use_new_branch = True
                else:
                    print("[域名分支] 进入原有处理流程")
            else:
                print("[域名分支] 未获取到域名，使用原有处理流程")
            
            if use_new_branch:
                # 新分支处理
                return self._process_new_branch(doi, domain, final_url, file_path)
            else:
                # 原有处理流程
                return self._process_normal_branch(doi, file_path, final_url, domain)
        finally:
            self.web_scraper.close_work_tab()
    
    def _get_final_url(self, doi: str) -> Optional[str]:
        """获取论文的最终URL"""
        print(f"[URL获取] 正在获取DOI={doi}的最终URL")
        final_url = self.web_scraper.resolve_final_url_with_pyautogui(doi)
        if self._is_valid_final_url(final_url):
            return final_url

        if final_url:
            print(f"[URL解析警告] DOI={doi} 地址栏结果异常，将启用HTTP兜底: {final_url}")
        else:
            print(f"[URL解析警告] DOI={doi} 地址栏读取失败，将启用HTTP兜底")

        fallback_url = self._resolve_final_url_via_http(doi)
        if fallback_url and self._is_valid_final_url(fallback_url):
            print(f"[URL解析兜底成功] DOI={doi} -> {fallback_url}")
            return fallback_url
        return None

    @staticmethod
    def _is_valid_final_url(url: Optional[str]) -> bool:
        if not url:
            return False
        candidate = str(url).strip()
        if not (candidate.startswith("http://") or candidate.startswith("https://")):
            return False
        parsed = urlparse(candidate)
        if not parsed.netloc:
            return False
        return True

    def _resolve_final_url_via_http(self, doi: str) -> Optional[str]:
        """通过HTTP重定向解析DOI最终URL"""
        doi_url = f"https://doi.org/{doi}"
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        ]

        for attempt in range(1, 4):
            headers = {
                "User-Agent": random.choice(user_agents),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "close",
                "Referer": "https://doi.org/",
            }
            try:
                response = requests.get(
                    doi_url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=(10, 30),
                )
                final_url = self._extract_final_url_from_response(response, doi_url)
                if final_url:
                    if response.status_code >= 400:
                        print(
                            f"[URL解析警告] DOI={doi} 终点HTTP状态码={response.status_code}，但已获取真实地址: {final_url}"
                        )
                    print(f"[URL解析成功] DOI={doi} -> {final_url}")
                    return final_url

                print(
                    f"[URL解析重试] DOI={doi} 第{attempt}/3次未解析出有效地址，HTTP状态码: {response.status_code}"
                )
            except requests.RequestException as e:
                print(f"[URL解析重试] DOI={doi} 第{attempt}/3次请求异常: {str(e)}")

            if attempt < 3:
                time.sleep(min(2 * attempt, 5) + random.uniform(0.2, 0.8))

        # 最后兜底：不跟随重定向，尝试直接读取Location
        try:
            response = requests.get(
                doi_url,
                headers={
                    "User-Agent": random.choice(user_agents),
                    "Accept": "*/*",
                    "Connection": "close",
                },
                allow_redirects=False,
                timeout=(10, 20),
            )
            location = response.headers.get("Location", "").strip()
            if location:
                final_url = urljoin(doi_url, location)
                print(f"[URL解析成功] DOI={doi} -> {final_url}")
                return final_url
        except requests.RequestException as e:
            print(f"[URL解析错误] DOI={doi} 兜底解析异常: {str(e)}")

        print(f"[URL解析错误] DOI={doi} 未获取到最终URL")
        return None

    @staticmethod
    def _extract_final_url_from_response(response: requests.Response, doi_url: str) -> Optional[str]:
        """从响应与重定向链中提取真实URL（允许终点403但URL可用）"""
        candidates: List[str] = []

        final_url = (response.url or "").strip()
        if final_url:
            candidates.append(final_url)

        for history_resp in response.history:
            location = history_resp.headers.get("Location", "").strip()
            if location:
                candidates.append(urljoin(history_resp.url, location))

        for candidate in candidates:
            if not candidate:
                continue
            if candidate.startswith("https://doi.org/") or candidate.startswith("http://doi.org/"):
                continue
            return candidate

        return None
    
    def _get_html_content(self, final_url: str) -> Optional[str]:
        """获取HTML内容（新标签页抓取，不影响当前会话页面）"""
        return self.web_scraper.fetch_html_in_new_tab(final_url)

    def _normalize_springer_link(self, link: str) -> str:
        candidate = html.unescape(str(link or "").strip()).replace("\\/", "/")
        if not candidate:
            return ""
        if candidate.startswith("//"):
            return f"https:{candidate}"
        if candidate.startswith("/"):
            return urljoin("https://link.springer.com", candidate)
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
        return urljoin("https://link.springer.com/", candidate.lstrip("/"))

    def _find_springer_download_url_from_html(self, html_path: str, doi: str) -> Optional[str]:
        try:
            with open(html_path, "r", encoding="utf-8", errors="ignore") as file:
                content = file.read()
        except Exception as e:
            print(f"[Springer专用] 读取HTML失败: {html_path} | {e}")
            return None

        content = content.replace("\\/", "/")
        links = re.findall(r'href=[\'"]?([^\'" >]+)', content, flags=re.IGNORECASE)
        print(f"[Springer专用] HTML链接候选数量: {len(links)}")

        doi_value = str(doi or "").strip()
        if not doi_value:
            print("[Springer专用] DOI为空，无法匹配模板链接")
            return None

        doi_encoded = quote(doi_value, safe="")
        template_rules = [
            ("_reference.pdf", [f"/content/pdf/{doi_value}_reference.pdf", f"/content/pdf/{doi_encoded}_reference.pdf"]),
            (".pdf", [f"/content/pdf/{doi_value}.pdf", f"/content/pdf/{doi_encoded}.pdf"]),
        ]

        for rule_name, tokens in template_rules:
            for raw_link in links:
                normalized_link = self._normalize_springer_link(raw_link)
                if not normalized_link:
                    continue
                if any(token in normalized_link for token in tokens):
                    print(f"[Springer专用] 命中模板{rule_name}: {normalized_link}")
                    return normalized_link

        print("[Springer专用] 未在HTML中找到Springer模板链接")
        return None

    def _process_springer_special(self, doi: str, file_path: str, final_url: str, domain: str) -> bool:
        """link.springer.com专用流程：从HTML中查找两个模板链接，命中即下载。"""
        print(f"[Springer专用] 开始处理: DOI={doi} HTML={file_path}")
        download_url = self._find_springer_download_url_from_html(file_path, doi)
        if not download_url:
            self.csv_manager.update_row_by_doi(doi, {"DownloadStatus": "Failed"})
            return False

        success, filename = self.file_downloader.download_with_template(doi, download_url, domain or "link.springer.com")
        if success:
            self.csv_manager.update_row_by_doi(
                doi,
                {
                    "DownloadStatus": "Success",
                    "Filename": filename,
                    "DownloadURL": download_url,
                },
            )
            print(f"[Springer专用] 下载成功: DOI={doi} URL={download_url}")
            if filename:
                final_path = os.path.join(Config.PAPER_DOWNLOAD_FOLDER, filename)
                print(f"[Springer专用] 文件路径={final_path} 存在={os.path.exists(final_path)}")
            return True

        self.csv_manager.update_row_by_doi(doi, {"DownloadStatus": "Failed", "DownloadURL": download_url})
        print(f"[Springer专用] 下载失败: DOI={doi} URL={download_url}")
        return False


    def _process_new_branch(self, doi: str, domain: str, final_url: str, file_path: str) -> bool:
        """
        新分支处理
        1. 根据域名获取下载模板
        2. 用DOI填充模板生成下载URL
        3. 使用生成的URL下载文件
        """
        print(f"[新分支] 开始处理: {doi} (域名: {domain})")
        
        # 1. 获取下载URL模板
        download_url = self.download_template_manager.get_download_url(domain, doi, final_url)
        if not download_url:
            print("[新分支错误] 无法生成下载URL")
            return False
        
        # 2. 下载文件（不需要再次检查登录，因为已经在第一次访问时处理过）
        success, filename = self.file_downloader.download_with_template(doi, download_url, domain)
        
        # 3. 更新状态和文件名
        if success:
            self.csv_manager.update_row_by_doi(doi, {
                'DownloadStatus': 'Success',
                'Filename': filename,
                'DownloadURL': download_url
            })
            print(f"[流程成功] DOI={doi} 已写入CSV并标记Success")
            if filename:
                final_path = os.path.join(Config.PAPER_DOWNLOAD_FOLDER, filename)
                print(f"[流程落盘] DOI={doi} Filename={filename} 路径={final_path} 存在={os.path.exists(final_path)}")
            return True
        else:
            self.csv_manager.update_row_by_doi(doi, {
                'DownloadStatus': 'Failed',
                'DownloadURL': download_url
            })
            return False
    
    def _process_normal_branch(self, doi: str, file_path: str, final_url: str, domain: str) -> bool:
        """原有处理流程"""
        # 1. 提取Paper链接
        paper_url = self.paper_extractor.extract_paper_url(file_path, doi)
        if not paper_url:
            self.csv_manager.update_row_by_doi(doi, {'DownloadStatus': 'Failed'})
            return False
        
        # 2. 下载文件
        success, filename = self.file_downloader.download_and_rename(doi, paper_url, domain)
        
        # 3. 更新状态
        if success:
            self.csv_manager.update_row_by_doi(doi, {
                'DownloadStatus': 'Success',
                'Filename': filename,
                'DownloadURL': paper_url
            })
            print(f"[流程成功] DOI={doi} 已写入CSV并标记Success")
            if filename:
                final_path = os.path.join(Config.PAPER_DOWNLOAD_FOLDER, filename)
                print(f"[流程落盘] DOI={doi} Filename={filename} 路径={final_path} 存在={os.path.exists(final_path)}")
            return True
        else:
            self.csv_manager.update_row_by_doi(doi, {
                'DownloadStatus': 'Failed',
                'DownloadURL': paper_url
            })
            return False
    
    def _save_html(self, html: str, final_url: str, paper_id: str, doi: str) -> Optional[str]:
        """保存HTML内容到文件"""
        url_part = FileHandler.extract_main_domain(final_url) if final_url else f"doi_{doi.replace('/', '_')}"
        filename = f"{url_part}_{paper_id}"
        return FileHandler.save_html_content(html, filename)
    
    def _print_progress(self, index: int, total: int, paper: Dict):
        """打印处理进度"""
        title = paper.get('Title', '无标题')[:50]
        progress = f"[进度] {index}/{total} ({index/total:.1%})"
        elapsed = datetime.now() - self.start_time
        remaining = elapsed * (total - index) / max(index, 1)
        time_info = f"[时间] 已用: {str(elapsed).split('.')[0]} | 剩余: ~{str(remaining).split('.')[0]}"
        print(f"\n{'='*40}")
        print(f"{progress} {time_info}")
        print(f"[论文] {title}")
        print(f"{'='*40}")
    
    def _wait_between_papers(self, current_index: int, total: int):
        """论文处理间隔等待"""
        print(f"\n[等待] 暂停 {Config.DELAY_BETWEEN_PAPERS} 秒...")
        remaining_papers = total - current_index
       
        remaining_time= remaining_papers * Config.DELAY_BETWEEN_PAPERS
        
        start = time.time()
        while time.time() - start < Config.DELAY_BETWEEN_PAPERS:
            elapsed = time.time() - start
            time_left = Config.DELAY_BETWEEN_PAPERS - elapsed
            time.sleep(1)
    
    def _print_summary(self, success_count: int, total: int):
        """打印摘要信息"""
        elapsed = datetime.now() - self.start_time
        print(f"\n{'='*50}")
        print(f"[处理完成] 成功处理 {success_count}/{total} 篇论文")
        print(f"总用时: {str(elapsed).split('.')[0]}")
        if total > 0:
            print(f"平均每篇用时: {elapsed.total_seconds()/total:.1f}秒")
        print(f"{'='*50}")


def main_entry():
    start_parent_guard()
    Config.apply_runtime_config()
    setup_script_logging(__file__, script_name="Paperdownload")
    yanzhen_proc = _start_yanzhen_helper()
    processor = PaperProcessor()
    try:
        processor.run()
    except KeyboardInterrupt:
        print("\n[用户中断] 程序被手动终止")
    except Exception as e:
        print(f"[错误] 程序运行出错: {str(e)}")
    finally:
        _stop_yanzhen_helper(yanzhen_proc)


if __name__ == "__main__":
    main_entry()
