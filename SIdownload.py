import os
import re
import csv
import time
import pyautogui
from datetime import datetime
import json
import random
from log_utils import setup_script_logging
from platform_compat import (
    get_default_edge_browser_path,
    hotkey,
    is_windows,
    open_url,
    resource_path,
)
from runtime_config import load_runtime_config
from runtime_paths import bundle_path, data_path, ensure_runtime_layout, get_bundle_dir

ensure_runtime_layout()
_BUNDLE_DIR = get_bundle_dir()

# 全局配置
CONFIG = {
    "DOWNLOAD_PATH": data_path("html"),  # HTML保存路径
    "JSON_PATH": data_path("SIkeyword.json"),  # 关键词json路径
    "CSV_PATH": data_path("PaperDoi.csv"),  # 论文列表CSV
    "EDGE_DRIVER_PATH": os.path.join(
        _BUNDLE_DIR, "edgedriver", "msedgedriver.exe" if is_windows() else "msedgedriver"
    ),  # Selenium驱动路径
    "EDGE_BROWSER_PATH": get_default_edge_browser_path(),
    "USE_SELENIUM": False,  # 是否使用Selenium方案
    "DELAY_BETWEEN_PAPERS": 5,  # 每篇论文间隔时间(秒)
    "PAGE_LOAD_TIMEOUT": 40,  # 页面加载超时时间(秒)
    "DOCUMENT_EXTENSIONS": ["pdf", "docx", "doc", "zip"],  # 支持的文档扩展名
    "SI_DOWNLOAD_FOLDER": data_path("SI"),  # SI下载文件夹
    "RANDOM_DELAY_RANGE": (0.8, 1.2),  # 延迟随机倍数  
    "MOUSE_MOVEMENT_STEPS": (5, 10),   # 鼠标移动步数  
    "HUMAN_BEHAVIOR_PROB": 0.3,        # 人性化行为概率
}


def apply_runtime_config():
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y"}

    cfg = load_runtime_config()
    paths = cfg.get("paths", {})
    params = cfg.get("params", {})
    CONFIG["DOWNLOAD_PATH"] = paths.get("DOWNLOAD_PATH", CONFIG["DOWNLOAD_PATH"])
    CONFIG["CSV_PATH"] = paths.get("CSV_PATH", CONFIG["CSV_PATH"])
    CONFIG["SI_DOWNLOAD_FOLDER"] = paths.get("SI_FOLDER", CONFIG["SI_DOWNLOAD_FOLDER"])
    CONFIG["USE_SELENIUM"] = _to_bool(params.get("USE_SELENIUM", CONFIG["USE_SELENIUM"]))
    CONFIG["DELAY_BETWEEN_PAPERS"] = int(params.get("DELAY_SI", CONFIG["DELAY_BETWEEN_PAPERS"]))
    CONFIG["PAGE_LOAD_TIMEOUT"] = int(params.get("TIMEOUT", CONFIG["PAGE_LOAD_TIMEOUT"]))

class PaperProcessor:
    def __init__(self):
        self.screen_width, self.screen_height = pyautogui.size()
        os.makedirs(CONFIG["DOWNLOAD_PATH"], exist_ok=True)
        os.makedirs(CONFIG["SI_DOWNLOAD_FOLDER"], exist_ok=True)
        self.start_time = datetime.now()
        self.csv_rows = []
        self.csv_fieldnames = []
        self.last_extract_by_eid = False  # 新增实例变量跟踪eid模式
        self._last_is_full_supp = False  # 跟踪full#supplementary-material模式
        
        print(f"\n{'='*50}")
        print(f"论文处理程序启动 - {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"HTML保存路径: {CONFIG['DOWNLOAD_PATH']}")
        print(f"SI下载文件夹: {CONFIG['SI_DOWNLOAD_FOLDER']}")
        print(f"论文列表文件: {CONFIG['CSV_PATH']}")
        print(f"使用{'Selenium' if CONFIG['USE_SELENIUM'] else 'PyAutoGUI'}方案")
        print(f"目标文件类型: {', '.join(CONFIG['DOCUMENT_EXTENSIONS'])}")
        print(f"{'='*50}\n")
    def simulate_human_behavior(self):  
        """模拟人类行为"""  
        # 随机滚动  
        if random.random() < 0.3:  # 30%概率  
            pyautogui.scroll(random.randint(-3, 3))  
            time.sleep(random.uniform(0.5, 1.5))  
        
        # 随机鼠标移动  
        if random.random() < 0.2:  # 20%概率  
            x_offset = random.randint(-50, 50)  
            y_offset = random.randint(-50, 50)  
            pyautogui.moveRel(x_offset, y_offset, duration=0.2)
    def normalize_filename(self, filename):
        """标准化文件名"""
        return re.sub(r'[\\/*?:"<>|]', "_", filename)
    
    def update_csv_column(self, doi, column, value):
        """按DOI查找并更新指定列"""
        updated = False
        for row in self.csv_rows:
            # 安全处理DOI值
            row_doi = row.get('DOI', '')
            if isinstance(row_doi, str):
                row_doi = row_doi.strip()
            else:
                row_doi = str(row_doi).strip() if row_doi is not None else ""
                
            if row_doi == doi:
                row[column] = value
                updated = True
                break
                
        if updated:
            try:
                with open(CONFIG["CSV_PATH"], 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=self.csv_fieldnames)
                    writer.writeheader()
                    writer.writerows(self.csv_rows)
                print(f"[CSV] 已更新DOI={doi}的{column}列为: {value}")
            except Exception as e:
                print(f"[CSV错误] 写回CSV失败: {str(e)}")
        else:
            print(f"[CSV警告] 未找到DOI={doi}，无法更新{column}")
    
    def get_csv_papers(self):
        """从CSV获取待处理论文列表"""
        print(f"[准备阶段] 正在读取论文列表CSV文件: {CONFIG['CSV_PATH']}")
        try:
            with open(CONFIG["CSV_PATH"], 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                self.csv_fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                self.csv_rows = list(reader)
                
                papers = []
                found_start = False
                
                for i, row in enumerate(self.csv_rows, 1):
                    # 安全获取和处理字段值
                    doi = row.get('DOI', '')
                    doi = doi.strip() if isinstance(doi, str) else str(doi).strip() if doi is not None else ""
                    
                    sidownload_status = row.get('SIDownloadStatus', '')
                    sidownload_status = sidownload_status.strip().upper() if isinstance(sidownload_status, str) else ""
                    
                    title = row.get('Title', '无标题')[:50]
                    
                    # 跳过已完成的条目
                    if sidownload_status == "SUCCESS" or sidownload_status == "NOSI":
                        print(f"[跳过] 第{i}行: {title} (状态: {sidownload_status})")
                        continue
                        
                    # 检查必要条件 - 只检查DOI和HTML文件名，不再检查URL
                    if not doi:
                        print(f"[跳过] 第{i}行: 缺少DOI")
                        continue
                        
                    html_filename = row.get('HTMLFile', '')
                    html_filename = html_filename.strip() if isinstance(html_filename, str) else ""
                    if not html_filename:
                        print(f"[跳过] 第{i}行: 缺少HTML文件名")
                        continue
                    
                    # 找到第一个符合条件的论文
                    if not found_start:
                        print(f"[起始点] 从第{i}行开始处理: {title}")
                        found_start = True
                    
                    papers.append(row)
                
                if not papers:
                    print("[准备阶段] 没有需要处理的论文")
                else:
                    print(f"[准备阶段] 找到 {len(papers)} 篇待处理论文")
                
                return papers
        except Exception as e:
            print(f"[错误] CSV读取失败: {str(e)}")
            return []
    
    def is_document_link(self, url):
        """检查URL是否是文档链接"""
        if not url or not isinstance(url, str):
            return False
            
        # 检查URL是否以文档扩展名结尾
        ext = url.split('.')[-1].lower()
        if ext in CONFIG["DOCUMENT_EXTENSIONS"]:
            return True
            
        # 检查URL中是否包含文档扩展名
        pattern = r'\.(pdf|docx|doc)(\?|$|/)'
        return bool(re.search(pattern, url.lower()))
    
    def get_download_flag(self, domain):
        """从JSON文件获取download标志"""
        if not domain or not isinstance(domain, str):
            return 0
            
        print(f"[分析阶段] 正在从JSON文件查找download标志: {CONFIG['JSON_PATH']}")
        try:
            with open(CONFIG["JSON_PATH"], 'r', encoding='utf-8') as f:
                data = json.load(f)
        
            if not isinstance(data, list):
                print("[警告] JSON文件格式应为数组形式")
                return 0
            
            for item in data:
                if not all(key in item for key in ('url', 'download')):
                    continue
                
                item_url = item.get('url', '')
                if not isinstance(item_url, str):
                    continue
                    
                if domain in item_url:
                    download_flag = item.get('download', '')
                    if isinstance(download_flag, str):
                        download_flag = download_flag.strip()
                    else:
                        download_flag = str(download_flag).strip()
                    return 1 if download_flag == '1' else 0
        
            print(f"[分析阶段] 未找到匹配的download标志: {domain}")
            return 0
        except Exception as e:
            print(f"[错误] JSON文件读取失败: {str(e)}")
            return 0
    
    def extract_si_url(self, txt_path, doi, domain):
        """从HTML文件提取SI链接"""
        if not os.path.exists(txt_path):
            print(f"[错误] HTML文件不存在: {txt_path}")
            return None
        
        print(f"[分析阶段] 正在从HTML提取SI文档链接: {txt_path}")
        try:
            # 处理域名
            if isinstance(domain, str) and domain.startswith('www.'):
                domain = domain[4:]
            print(f"[分析阶段] 使用域名: {domain}")
    
            # 从JSON文件查找关键词
            print(f"[分析阶段] 正在从JSON文件查找SI关键词: {CONFIG['JSON_PATH']}")
            with open(CONFIG["JSON_PATH"], 'r', encoding='utf-8') as f:
                data = json.load(f)
    
            if not isinstance(data, list):
                print("[错误] JSON文件格式应为数组形式")
                return None
        
            # 查找匹配的关键词数组
            si_keywords = []
            for item in data:
                if not all(key in item for key in ('url', 'keywords')):
                    continue
            
                item_url = item.get('url', '')
                if not isinstance(item_url, str):
                    continue
                 
                if domain in item_url:
                    keywords = item.get('keywords', [])
                    if isinstance(keywords, list):
                        si_keywords = keywords
                    break
    
            if not si_keywords:
                print(f"[分析阶段] 未找到匹配的SI关键词: {domain}")
                return None
    
            print(f"[分析阶段] 找到SI关键词: {si_keywords}")

            # 处理特殊关键词
            is_doi_keyword = len(si_keywords) == 1 and isinstance(si_keywords[0], str) and si_keywords[0].lower() == "doi"
            is_full_supp = len(si_keywords) == 1 and isinstance(si_keywords[0], str) and si_keywords[0].lower() == "full#supplementary-material"
            is_eid = len(si_keywords) == 1 and isinstance(si_keywords[0], str) and si_keywords[0].lower() == "eid"
        
            if is_doi_keyword:
                if doi and isinstance(doi, str):
                    si_keywords = [doi + "/s"]
                    print(f"[分析阶段] 关键词为doi，已替换为DOI/s格式: {si_keywords}")
                else:
                    print("[警告] 关键词为doi但未提供有效论文DOI")
                    return None
        
            # 从HTML文件读取内容
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # eid关键词特殊处理
            if is_eid:
                self.last_extract_by_eid = True
                eid_match = re.search(r'"eid":"([^"]+)"', content)
                if not eid_match:
                    print(f"[分析阶段] 未找到eid")
                    self.update_csv_column(doi, 'SIDownloadStatus', 'NOSI')
                    return None
                eid = eid_match.group(1)
                si_url = f"https://ars.els-cdn.com/content/image/{eid}-mmc1.pdf"
                print(f"[分析阶段] 基于eid构建PDF链接: {si_url}")
                return si_url
    
            # 从HTML内容中提取所有URL
            urls = re.findall(r'href=[\'"]?([^\'" >]+)', content)
            print(f"[分析阶段] 共找到 {len(urls)} 个链接，正在筛选文档链接...")

            if is_full_supp:
                valid_urls = []
                for url in urls:
                    if not isinstance(url, str):
                        continue
                    if any(isinstance(k, str) and k.lower() in url.lower() for k in si_keywords):
                        valid_urls.append(url)
                        print(f"[分析阶段] 找到有效链接(full#supplementary-material): {url}")
                if not valid_urls:
                    print(f"[分析阶段] 未找到包含{si_keywords}的链接")
                    self.update_csv_column(doi, 'SIDownloadStatus', 'NOSI')
                    return None
                si_url = valid_urls[0]
                if not si_url.startswith('http'):
                    si_url = f"https://{domain}/{si_url.lstrip('/')}"
                print(f"[分析阶段] 最终选择的SI文档链接: {si_url}")
                self._last_is_full_supp = True
                return si_url
            else:
                self._last_is_full_supp = False
            
            # 筛选有效链接
            valid_urls = []
            for url in urls:
                if not isinstance(url, str):
                    continue
                
                has_keyword = any(isinstance(k, str) and k.lower() in url.lower() for k in si_keywords)
            
                if is_doi_keyword:
                    if has_keyword:
                        valid_urls.append(url)
                        print(f"[分析阶段] 找到有效链接(doi模式): {url}")
                elif has_keyword and self.is_document_link(url):
                    valid_urls.append(url)
                    print(f"[分析阶段] 找到有效文档链接: {url}")
    
            if not valid_urls:
                print(f"[分析阶段] 未找到包含{si_keywords}和文档扩展名的链接")
                if si_keywords:
                    self.update_csv_column(doi, "SIDownloadStatus", 'NOSI')
                return None
        
            # 优先返回PDF链接
            pdf_url = next((u for u in valid_urls if u.lower().endswith('.pdf')), None)
            si_url = pdf_url if pdf_url else valid_urls[0]
    
            # 确保URL完整
            if not si_url.startswith('http'):
                si_url = f"https://{domain}/{si_url.lstrip('/')}"
    
            print(f"[分析阶段] 最终选择的SI文档链接: {si_url}")
            return si_url
    
        except Exception as e:
            print(f"[错误] SI链接提取失败: {str(e)}")
            return None
    def simulate_natural_movement(self,target_x, target_y):  
        """模拟自然鼠标移动"""  
        current_x, current_y = pyautogui.position()  
        steps = random.randint(5, 10)  
        
        for i in range(steps):  
            x = current_x + (target_x - current_x) * (i + 1) / steps  
            y = current_y + (target_y - current_y) * (i + 1) / steps  
            pyautogui.moveTo(x, y, duration=random.uniform(0.1, 0.3))  
            time.sleep(random.uniform(0.05, 0.15))  
    def download_and_rename_file(self, doi, url, auto_download=False, wait_time=40):
        """下载并重命名文件"""
        if not doi or not url:
            print("[错误] 缺少DOI或URL")
            return None
            
        print(f"[文件下载] 正在处理DOI: {doi}")
        
        # 获取下载文件夹中的初始文件列表
        initial_files = set(os.listdir(CONFIG["SI_DOWNLOAD_FOLDER"]))

        try:
            if not open_url(url, browser_path=CONFIG["EDGE_BROWSER_PATH"]):
                print("[错误] 浏览器打开失败")
                return None
            print("[浏览器操作] 成功打开文档链接")
            
            if not auto_download:
                print("[文件下载] 正在模拟Ctrl+S保存文件...")
                time.sleep(random.uniform(8, 12))
                self.simulate_natural_movement(700, 100)
                pyautogui.click(x=700, y=100)
                time.sleep(5)
                hotkey("print_page")
                time.sleep(5)
                pyautogui.press('enter')
                time.sleep(5)
                full_file_path = os.path.join(
                    CONFIG["SI_DOWNLOAD_FOLDER"], 'doi')
                pyautogui.write(full_file_path, interval=0.1) 
                time.sleep(2)
                pyautogui.press('enter')
                 
                time.sleep(8)
                pyautogui.press('enter')
                time.sleep(2)
                hotkey("close_tab")

            time.sleep(wait_time)

            # 获取下载后的文件列表
            final_files = set(os.listdir(CONFIG["SI_DOWNLOAD_FOLDER"]))
            new_files = final_files - initial_files
            
            if not new_files:
                print("[警告] 未检测到新下载的文件")
                return None
            
            # 获取最新下载的文件
            downloaded_file = max(new_files, key=lambda f: os.path.getmtime(os.path.join(CONFIG["SI_DOWNLOAD_FOLDER"], f)))
            original_path = os.path.join(CONFIG["SI_DOWNLOAD_FOLDER"], downloaded_file)
            
            # 根据DOI生成新文件名
            safe_doi = self.normalize_filename(doi.replace('/', '_'))
            file_ext = os.path.splitext(downloaded_file)[1]
            new_filename = f"{safe_doi}{file_ext}"
            new_path = os.path.join(CONFIG["SI_DOWNLOAD_FOLDER"], new_filename)
            
            # 重命名文件
            try:
                os.rename(original_path, new_path)
                print(f"[文件下载] 文件已重命名为: {new_filename}")
                return new_filename
            except Exception as e:
                print(f"[错误] 文件重命名失败: {str(e)}")
                return None
        except Exception as e:
            print(f"[错误] 下载操作失败: {str(e)}")
            return None
    
    def click_download_button_and_close(self, button_image_path, doi, wait_time=20):
        """点击下载按钮并重命名文件"""
        if not doi:
            print("[错误] 缺少DOI")
            return None
            
        folder = CONFIG["SI_DOWNLOAD_FOLDER"]
        before = set(os.listdir(folder))
        print(f"[自动操作] 正在查找并点击下载按钮: {button_image_path}")
        start_time = time.time()
        found = False
        
        try:
            while time.time() - start_time < wait_time:
                location = pyautogui.locateCenterOnScreen(button_image_path, confidence=0.8)
                if location:
                    pyautogui.moveTo(location)
                    pyautogui.click()
                    print("[自动操作] 已点击下载按钮")
                    found = True
                    time.sleep(2)
                    break
                time.sleep(1)
        except Exception as e:
            print(f"[错误] 按钮识别失败: {str(e)}")
            
        if not found:
            print("[警告] 未找到下载按钮")
            try:
                hotkey("close_tab")
                time.sleep(2)
            except:
                pass
            return None
            
        # 检测新下载文件夹并重命名
        if found:
            print("[自动操作] 检测新下载文件夹并重命名...")
            return self.rename_latest_downloaded_file_after(before, doi, wait_time=wait_time)
        return None

    def rename_latest_downloaded_file_after(self, before, doi, wait_time=50):
        """重命名最新下载的文件"""
        if not doi:
            return None
            
        folder = CONFIG["SI_DOWNLOAD_FOLDER"]
        time.sleep(wait_time)
        after = set(os.listdir(folder))
        new_files = after - before
        
        if not new_files:
            print("[警告] 未检测到新下载的文件")
            return None
            
        try:
            downloaded_file = max(new_files, key=lambda f: os.path.getmtime(os.path.join(folder, f)))
            original_path = os.path.join(folder, downloaded_file)
            safe_doi = self.normalize_filename(doi.replace('/', '_'))
            file_ext = os.path.splitext(downloaded_file)[1]
            new_filename = f"{safe_doi}{file_ext}"
            new_path = os.path.join(folder, new_filename)
            os.rename(original_path, new_path)
            print(f"[文件下载] 文件已重命名为: {new_filename}")
            return new_filename
        except Exception as e:
            print(f"[错误] 文件重命名失败: {str(e)}")
            return None

    def open_in_edge(self, url, doi, need_download):
        """用浏览器打开URL并下载文件（Windows优先Edge）"""
        if not url or not doi:
            print("[错误] 缺少URL或DOI")
            return None
            
        print(f"[浏览器操作] 正在打开SI文档链接: {url}")
        try:
            # 检查是否为特殊处理
            is_full_supp = getattr(self, '_last_is_full_supp', False)
            
            if is_full_supp:
                if not open_url(url, browser_path=CONFIG["EDGE_BROWSER_PATH"]):
                    print("[错误] 浏览器打开失败")
                    return None
                print("[浏览器操作] 成功打开文档链接")
                self.simulate_human_behavior()  
                time.sleep(CONFIG["PAGE_LOAD_TIMEOUT"])
                self.simulate_human_behavior()
                download_button_image = resource_path("photos", "download.png", base_dir=_BUNDLE_DIR)
                if not os.path.exists(download_button_image):
                    print(f"[警告] 未找到下载按钮参考图: {download_button_image}")
                    return None
                return self.click_download_button_and_close(download_button_image, doi, wait_time=20)

            elif need_download:
                print("[浏览器操作] 需要下载文件，等待页面加载...")
                time.sleep(random.uniform(1, 3))
                return self.download_and_rename_file(doi, url, auto_download=False)
            else:
                print("[浏览器操作] 不需要下载文件，等待页面加载...")
                time.sleep(random.uniform(1, 3))
                return self.download_and_rename_file(doi, url, auto_download=True)

        except Exception as e:
            print(f"[错误] 浏览器打开失败: {str(e)}")
            return None
    
    def print_progress(self, index, total, title):
        """打印进度信息"""
        progress = f"[进度] {index}/{total} ({index/total:.1%})"
        elapsed = datetime.now() - self.start_time
        if index > 0:
            remaining = elapsed * (total - index) / index
            time_info = f"[时间] 已用: {str(elapsed).split('.')[0]} | 预计剩余: {str(remaining).split('.')[0]}"
        else:
            time_info = f"[时间] 已用: {str(elapsed).split('.')[0]}"
            
        print(f"\n{'='*30}")
        print(f"{progress} {time_info}")
        print(f"[当前论文] {title[:60]}{'...' if len(title)>60 else ''}")
        print(f"{'='*30}")
    
    def process_paper(self, paper, index, total):
        """处理单篇论文"""
        # 安全获取字段值
        doi = paper.get('DOI', '')
        doi = doi.strip() if isinstance(doi, str) else str(doi).strip() if doi is not None else ""
        
        title = paper.get('Title', '无标题')
        title = title[:50] if isinstance(title, str) else "无标题"
        
        # 每次处理新论文时重置eid标志
        self.last_extract_by_eid = False
        
        self.print_progress(index, total, title)
        print(f"[处理开始] DOI: {doi}")

        # 获取HTML文件路径
        html_filename = paper.get('HTMLFile', '')
        html_filename = html_filename.strip() if isinstance(html_filename, str) else ""
        if not html_filename:
            print("[跳过] 缺少HTML文件名")
            return False
            
        html_path = os.path.join(CONFIG["DOWNLOAD_PATH"], html_filename)
        if not os.path.exists(html_path):
            print(f"[跳过] HTML文件不存在: {html_path}")
            return False
        
        # 从HTML文件名中提取域名
        try:
            # 获取文件名（不含路径）
            filename_only = os.path.basename(html_filename)
            # 移除扩展名
            filename_without_ext = os.path.splitext(filename_only)[0]
            # 分割文件名，提取域名部分（第一部分）
            parts = filename_without_ext.split('_')
            if len(parts) < 1:
                print("[错误] 无法从HTML文件名解析域名")
                return False
                
            domain = parts[0]  # 第一部分是域名，如"sciencedirect.com"
            print(f"[分析阶段] 从文件名提取域名: {domain}")
            
        except Exception as e:
            print(f"[错误] 域名提取失败: {str(e)}")
            return False

        # 提取SI文档链接
        si_url = self.extract_si_url(html_path, doi, domain)
        if not si_url:
            print("[跳过] 未找到有效SI文档链接")
            self.update_csv_column(doi, 'SIDownloadStatus', 'NOSI')
            return False

        print(f"[成功] 找到SI文档链接: {si_url}")

        # 获取下载标志并下载文件
        need_download = self.get_download_flag(domain)
        print(f"[下载标志] 需要下载: {'是' if need_download else '否'}")
        
        result_filename = self.open_in_edge(si_url, doi, need_download)
        
        # 更新CSV状态
        if result_filename:
            # 更新SIDownloadStatus为SUCCESS
            self.update_csv_column(doi, 'SIDownloadStatus', 'SUCCESS')
            # 更新SIFilename为下载的文件名
            self.update_csv_column(doi, 'SIFilename', result_filename)
            return True
        else:
            # eid模式下载失败时标记NOSI
            if self.last_extract_by_eid:
                print("[处理结果] eid模式下载失败，标记为NOSI")
                self.update_csv_column(doi, 'SIDownloadStatus', 'NOSI')
            return False
    
    def run(self):
        """主运行流程"""
        papers = self.get_csv_papers()
        if not papers:
            print("[终止] 无需要处理的论文，程序退出")
            return
        
        total = len(papers)
        print(f"[开始处理] 共 {total} 篇论文，预计时间: ~{total*CONFIG['DELAY_BETWEEN_PAPERS']//60}分钟")
        
        delay = CONFIG["DELAY_BETWEEN_PAPERS"] * random.uniform(0.8, 1.2)  

        success_count = 0
        for i, paper in enumerate(papers, 1):
            if self.process_paper(paper, i, total):
                success_count += 1
            
            if i < total:
                print(f"\n[等待] 暂停 {CONFIG['DELAY_BETWEEN_PAPERS']} 秒...")
                time.sleep(delay)
        
        elapsed = datetime.now() - self.start_time
        print(f"\n{'='*50}")
        print(f"[处理完成] 成功处理 {success_count}/{total} 篇论文")
        print(f"总用时: {str(elapsed).split('.')[0]}")
        print(f"平均每篇用时: {elapsed.total_seconds()/total:.1f}秒")
        print(f"{'='*50}")

def main_entry():
    apply_runtime_config()
    setup_script_logging(__file__, script_name="SIdownload")
    processor = PaperProcessor()
    processor.run()


if __name__ == "__main__":
    main_entry()
