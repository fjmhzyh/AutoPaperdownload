import time
import csv
import os
import sys
import pyautogui
import pyperclip
import re
import logging
import psutil
import traceback  # 添加traceback用于详细错误日志
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET
import platform
from log_utils import setup_script_logging
from platform_compat import (
    get_browser_process_names,
    get_default_edge_browser_path,
    hotkey,
    open_url,
    resource_path,
)
from runtime_config import load_runtime_config
from runtime_exec import run_worker_blocking
from runtime_paths import data_path, ensure_runtime_layout, get_bundle_dir, get_data_dir

ensure_runtime_layout()

_BUNDLE_DIR = get_bundle_dir()
_DATA_DIR = get_data_dir()

# 配置参数
WEBSITE_URL = "https://pubmed.ncbi.nlm.nih.gov/"
SEARCH_QUERY = "(PCL) AND (Light curing)"
OUTPUT_FOLDER = data_path("RSS")
CSV_FILE = data_path("PaperDoi.csv")
BROWSER_PATH = get_default_edge_browser_path()
RSS_PNG = resource_path("photos", "RSS.png", base_dir=_BUNDLE_DIR)
CREATE_PNG = resource_path("photos", "create.png", base_dir=_BUNDLE_DIR)
NEXT_PROGRAM = "Paperdownload.py"
NEW_PROGRAM = "SIdownload.py"
LOG_FILE = data_path("log", "doi_extractor.log")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

pyautogui.PAUSE = 1
pyautogui.FAILSAFE = True


def apply_runtime_config() -> None:
    global SEARCH_QUERY, OUTPUT_FOLDER, CSV_FILE
    cfg = load_runtime_config()
    params = cfg.get("params", {})
    paths = cfg.get("paths", {})

    SEARCH_QUERY = str(params.get("SEARCH_QUERY", SEARCH_QUERY)).strip() or SEARCH_QUERY
    CSV_FILE = paths.get("CSV_PATH", CSV_FILE)
    OUTPUT_FOLDER = data_path("RSS")

    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def locate_on_screen_safe(image_path: str, confidences=(0.9, 0.8, 0.7), retries: int = 2):
    """安全查找屏幕图像，兼容 pyautogui 抛 ImageNotFoundException 的行为"""
    for _ in range(retries):
        for confidence in confidences:
            try:
                pos = pyautogui.locateOnScreen(image_path, confidence=confidence)
                if pos:
                    return pos
            except Exception:
                continue
        time.sleep(1)
    return None


def fetch_dois_via_pubmed_api(query: str, retmax: int = 15) -> Optional[List[str]]:
    """
    通过 NCBI E-utilities 兜底获取DOI，避免图像识别失败导致流程中断
    返回 None 表示API请求失败；返回 [] 表示成功但未提取到DOI
    """
    try:
        esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        esearch_resp = requests.get(
            esearch_url,
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": retmax,
                "sort": "pub+date",
            },
            timeout=(10, 30),
        )
        esearch_resp.raise_for_status()
        ids = esearch_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        efetch_resp = requests.get(
            efetch_url,
            params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            },
            timeout=(10, 30),
        )
        efetch_resp.raise_for_status()

        root = ET.fromstring(efetch_resp.text)
        dois = []
        for article_id in root.findall(".//ArticleId"):
            if article_id.attrib.get("IdType", "").lower() == "doi":
                val = (article_id.text or "").strip().lower().rstrip(".")
                if val:
                    dois.append(val)
        # 去重并保持顺序
        unique = list(dict.fromkeys(dois))
        return unique
    except Exception as e:
        logger.error(f"PubMed API兜底失败: {repr(e)}")
        logger.error(traceback.format_exc())
        return None


def handle_extracted_dois(dois: List[str]):
    """统一处理DOI统计、写入CSV和调度后续程序"""
    if dois:
        logger.info(f"\n从内容中找到 {len(dois)} 个DOI")

        unique_dois = set(dois)
        if len(unique_dois) < len(dois):
            logger.info(f"警告：当前提取的DOI中有 {len(dois)-len(unique_dois)} 个重复值")

        stats = update_doi_csv(dois)
        if stats:
            logger.info("\nDOI统计信息:")
            logger.info(f"- 本次提取DOI总数: {stats['total_extracted']}")
            logger.info(f"- 本次提取中的重复DOI: {stats['duplicates_in_current']}")
            logger.info(f"- 新增DOI数量: {stats['new_dois_added']}")
            logger.info(f"- 已有DOI总数: {stats['existing_dois']}")

            if stats['new_dois_added'] > 0:
                run_next_program()
    else:
        logger.info("未在内容中找到任何DOI")

def extract_strict_dois(text: str) -> List[str]:
    """
    严格提取 doi: 10.xxxx/xxxx 格式的DOI
    返回格式：["10.1088/2057-1976/adf8ee", ...]
    去除</dc:identifier>等XML/HTML标签后缀和doi:前缀
    确保DOI结尾不包含句点(.)
    """
    # 严格匹配 doi: 10.xxxx/xxxx 格式
    strict_doi_pattern = r'\bdoi:\s*(10\.[0-9]{4,}(?:\.[0-9]+)*/[^\s<;,)]+)'
    matches = re.findall(strict_doi_pattern, text, re.IGNORECASE)
    
    # 清理结果
    clean_dois = []
    for doi in matches:
        # 移除XML/HTML标签
        clean_doi = re.sub(r'<[^>]+>', '', doi)
        # 移除末尾的标点，特别注意去除句点
        clean_doi = re.sub(r'[^0-9a-zA-Z./-]+$', '', clean_doi)
        clean_doi = clean_doi.rstrip('.')
        clean_dois.append(clean_doi.lower())
    
    return clean_dois

def save_html_to_file(content: str) -> Optional[str]:
    """将HTML内容保存到文件"""
    try:
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"PubMed_RSS_{timestamp}.txt"
        filepath = os.path.join(OUTPUT_FOLDER, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"已保存HTML内容到: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"保存文件失败: {str(e)}")
        return None

def update_doi_csv(dois: List[str]) -> Optional[Dict]:
    """更新CSV文件中的DOI记录，只写入不存在的纯DOI号"""
    try:
        existing_dois = set()
        # 读取现有CSV文件中的所有DOI
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # 跳过标题行
                existing_dois = {row[0].lower().strip() for row in reader if row and row[0]}
        
        # 首先对当前提取的DOI列表去重
        unique_dois = list({doi.lower().strip() for doi in dois})
        if len(unique_dois) < len(dois):
            logger.info(f"注意：当前提取的DOI中有 {len(dois)-len(unique_dois)} 个重复值已被过滤")
        
        # 筛选出新DOI（不包含在existing_dois中的）
        new_dois = [doi for doi in unique_dois 
                   if doi not in existing_dois]
        
        if new_dois:
            # 写入新DOI（只包含DOI号，不包含"doi:"前缀）
            with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for doi in new_dois:
                    writer.writerow([doi, '', '', '', '','', '', ''])
            logger.info(f"已添加 {len(new_dois)} 个新DOI到CSV文件")
            logger.info("新增DOI列表:")
            for doi in new_dois:
                logger.info(f"  - {doi}")
        else:
            logger.info("没有发现新的DOI需要添加")
            
        # 返回统计信息
        return {
            "total_extracted": len(dois),
            "duplicates_in_current": len(dois) - len(unique_dois),
            "new_dois_added": len(new_dois),
            "existing_dois": len(existing_dois)
        }
    except Exception as e:
        logger.error(f"更新CSV文件失败: {str(e)}")
        return None

def get_html_from_browser() -> Optional[str]:
    """从浏览器获取HTML内容"""
    try:
        # 确保浏览器窗口激活
        time.sleep(3)
        hotkey("select_all")
        time.sleep(1)
        hotkey("copy")
        time.sleep(2)
        return pyperclip.paste().strip()
    except Exception as e:
        logger.error(f"获取HTML内容失败: {str(e)}")
        return None

def initialize_csv():
    """初始化CSV文件（如果不存在）"""
    if not os.path.exists(CSV_FILE):
        os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['DOI', 'DownloadStatus', 'Filename', "URL", "DownloadURL","SIDownloadStatus","SIFilename","HTMLFilename"])
        logger.info(f"已创建新的CSV文件: {CSV_FILE}")

def kill_browser_processes():
    """关闭所有浏览器进程"""
    try:
        logger.info("正在关闭所有浏览器进程...")
        browser_names = set(get_browser_process_names())
        killed = 0
        
        for proc in psutil.process_iter():
            try:
                if proc.name().lower() in browser_names:
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        logger.info(f"已关闭 {killed} 个浏览器进程")
    except Exception as e:
        logger.error(f"关闭浏览器进程失败: {str(e)}")

def is_program_running(program_name: str) -> bool:
    """检查程序是否正在运行"""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.cmdline()
                if cmdline and any(program_name in part for part in cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except Exception as e:
        logger.error(f"检查程序状态失败: {e}")
        return False

def run_next_program():
    """运行下一个Python程序"""
    try:
        logger.info(f"\n正在启动下一个程序: {NEXT_PROGRAM}")
        run_worker_blocking("paper", cwd=_DATA_DIR)
        logger.info("下一个程序已完成")
    except Exception as e:
        logger.error(f"启动下一个程序失败: {e}")

def run_new_program():
    """运行新的程序"""
    try:
        logger.info(f"\n正在启动新程序: {NEW_PROGRAM}")
        run_worker_blocking("si", cwd=_DATA_DIR)
        logger.info("新程序已完成")
    except Exception as e:
        logger.error(f"启动新程序失败: {e}")

def wait_for_program_completion(program_name: str, timeout: int = 20 * 60 * 60, interval: int = 30):
    """
    等待指定程序运行完成
    :param program_name: 要等待的程序名称或路径
    :param timeout: 最大等待时间（秒）
    :param interval: 检查间隔（秒）
    """
    start_time = time.time()
    logger.info(f"\n等待程序完成: {program_name}")
    logger.info(f"超时时间: {timeout}秒, 检查间隔: {interval}秒")
    
    while time.time() - start_time < timeout:
        if not is_program_running(program_name):
            logger.info(f"检测到程序已完成: {program_name}")
            return True
        
        elapsed = int(time.time() - start_time)
        remaining = timeout - elapsed
        logger.info(f"程序仍在运行，已等待: {elapsed}秒，剩余时间: {remaining}秒")
        time.sleep(interval)
    
    logger.warning(f"等待超时，程序可能仍在运行: {program_name}")
    return False

def get_system_info() -> Dict[str, str]:
    """获取运行系统信息，并供主流程分支使用"""
    os_name = platform.system().lower()
    info = {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "os_name": os_name,
        "is_windows": os_name == "windows",
        "is_mac": os_name == "darwin",
    }
    return info


def handle_rss_for_windows():
    """Windows分支：保持原RSS获取逻辑不变"""
    rss_pos = locate_on_screen_safe(RSS_PNG)
    if rss_pos:
        pyautogui.click(rss_pos)
        time.sleep(2)

        create_pos = locate_on_screen_safe(CREATE_PNG)
        if create_pos:
            pyautogui.click(create_pos)
            time.sleep(2)

            hotkey("copy")
            time.sleep(2)
            rss_link = pyperclip.paste()
            logger.info(f"获取的RSS链接: {rss_link}")

            # 在新标签页打开RSS链接
            logger.info("\n正在打开RSS订阅页面...")
            if not open_url(rss_link, browser_path=BROWSER_PATH, new_window=True):
                logger.error("打开RSS订阅页面失败")
                raise RuntimeError("打开RSS订阅页面失败")
            time.sleep(5)

            # 获取HTML内容
            logger.info("\n正在获取HTML内容...")
            html_content = get_html_from_browser()
            if html_content:
                logger.info("成功获取HTML内容")

                # 保存HTML文件
                saved_file = save_html_to_file(html_content)
                if saved_file:
                    dois = extract_strict_dois(html_content)
                    handle_extracted_dois(dois)
            else:
                logger.error("未能获取HTML内容")
                raise RuntimeError("获取RSS HTML内容失败")
        else:
            logger.warning("未找到'Create RSS'按钮，尝试PubMed API兜底获取DOI")
            api_dois = fetch_dois_via_pubmed_api(SEARCH_QUERY, retmax=15)
            if api_dois is None:
                raise RuntimeError("未找到Create RSS按钮且API兜底失败")
            handle_extracted_dois(api_dois)
    else:
        logger.warning("未找到RSS图标，尝试PubMed API兜底获取DOI")
        api_dois = fetch_dois_via_pubmed_api(SEARCH_QUERY, retmax=15)
        if api_dois is None:
            raise RuntimeError("未找到RSS图标且API兜底失败")
        handle_extracted_dois(api_dois)


def handle_rss_for_mac(system_info: Dict[str, str]) -> bool:
    """
    mac分支：在此处补充你自己的RSS获取逻辑
    返回True表示本轮RSS处理成功，返回False表示未处理
    """
    pyautogui.press('tab', presses=5, interval=0.3) 
    pyautogui.press('enter')  # 点enter打开订阅界面
    pyautogui.press('tab',presses=2, interval=0.3)
    pyautogui.press('enter') # 点击创建按钮

    hotkey("copy")
    time.sleep(3)
    rss_link = pyperclip.paste()
    logger.info(f"获取的RSS链接: {rss_link}")

    # 在新标签页打开RSS链接
    logger.info("\n正在打开RSS订阅页面...")
    if not open_url(rss_link, browser_path=BROWSER_PATH, new_window=True):
        logger.error("打开RSS订阅页面失败")
        raise RuntimeError("打开RSS订阅页面失败")
    time.sleep(5)

    # 获取HTML内容
    logger.info("\n正在获取HTML内容...")
    html_content = get_html_from_browser()
    if html_content:
        logger.info("成功获取HTML内容")

        # 保存HTML文件
        saved_file = save_html_to_file(html_content)
        if saved_file:
            dois = extract_strict_dois(html_content)
            handle_extracted_dois(dois)
            return True
    else:
        logger.error("未能获取HTML内容")
        raise RuntimeError("获取RSS HTML内容失败")
        return False


def main():
    logger.info("=== PubMed RSS DOI提取程序 ===")
    system_info = get_system_info()
    logger.info(
        "系统信息: system=%s release=%s machine=%s python=%s",
        system_info["platform_system"],
        system_info["platform_release"],
        system_info["machine"],
        system_info["python_version"],
    )
    
    while True:  # 添加无限循环实现定时执行
        try:
            logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("开始执行新的一轮任务...")
            
            # 初始化CSV文件
            initialize_csv()
            
            # 打开PubMed网站
            logger.info("\n正在打开PubMed网站...")
            if not open_url(WEBSITE_URL, browser_path=BROWSER_PATH, new_window=True):
                logger.error("打开PubMed失败，跳过本轮")
                raise RuntimeError("打开PubMed失败")
            time.sleep(10)
            
            # 执行搜索
            logger.info(f"\n正在执行搜索: {SEARCH_QUERY}")
            try:
                pyautogui.typewrite(SEARCH_QUERY, interval=0.05)
                pyautogui.press('enter')
                time.sleep(5)
            except Exception as e:
                logger.error(f"搜索时出错: {e}")
                raise RuntimeError(f"搜索阶段失败: {repr(e)}")
            
            # 获取RSS链接
            logger.info("\n正在获取RSS订阅链接...")
            try:
                if system_info["is_windows"]:
                    handle_rss_for_windows()
                elif system_info["is_mac"]:
                    handled = handle_rss_for_mac(system_info)
                    if not handled:
                        raise RuntimeError("mac RSS逻辑未实现，请在 handle_rss_for_mac 中补充")
                else:
                    raise RuntimeError(f"不支持的系统: {system_info['platform_system']}")
            except Exception as e:
                logger.error(f"获取RSS链接时出错: {repr(e)}")
                logger.error(traceback.format_exc())
                raise RuntimeError(f"RSS阶段失败: {repr(e)}")
            
            logger.info("\nDOI提取程序执行完成")
            logger.info("等待Paperdownload.py程序运行完成...")
            
            # 等待Paperdownload.py程序完成
            paperdownload_name = os.path.basename(NEXT_PROGRAM)
            if wait_for_program_completion(paperdownload_name):
                logger.info("Paperdownload.py程序已运行完成")
                run_new_program()
            else:
                logger.warning("跳过新程序启动（等待超时）")
            
            logger.info("所有程序调度完成")
            
        except Exception as e:
            logger.error(f"程序执行过程中发生错误: {str(e)}")
            logger.error(traceback.format_exc())
        
        finally:
            # 无论程序是否成功执行，最后都尝试关闭浏览器窗口
            kill_browser_processes()
        
        # 计算并等待下一次执行时间
        next_run = datetime.now() + timedelta(hours=24)
        logger.info(f"当前任务完成，下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 计算需要等待的秒数
        wait_seconds = (next_run - datetime.now()).total_seconds()
        
        # 添加倒计时显示
        while wait_seconds > 0:
            hours, remainder = divmod(wait_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
            logger.info(f"距离下次执行还有: {countdown}")
            time.sleep(60)  # 每分钟更新一次倒计时
            wait_seconds = (next_run - datetime.now()).total_seconds()
        
        logger.info("\n" + "="*50)
        logger.info("开始新一轮执行...")
        logger.info("="*50 + "\n")

def main_entry():
    apply_runtime_config()
    setup_script_logging(__file__, script_name="getdoi_helper")
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    start_time = datetime.now()
    logger.info(f"程序启动于: {start_time}")
    main()


if __name__ == "__main__":
    main_entry()
