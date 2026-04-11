import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import os
import sys
import json
import re
from platform_compat import is_windows

# ==============================================================================
#  【全局配置区】 - 在此处修改文件名和基础设置
# ==============================================================================

# 1. 基础路径配置 (自动获取当前脚本所在文件夹的绝对路径)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 核心 Python 脚本文件名配置
SCRIPT_NAMES = {
    "getdoi": "getdoi_helper.py",       # PubMed 调度脚本
    "paper": "Paperdownload.py",        # 正文下载脚本
    "si": "SIdownload.py",              # 补充材料下载脚本
    "clean": "筛选文件大小.py",            # 文件清理脚本
    "csv_turner": "Csv_Turner_strenth.py", # 失败 DOI 提取脚本
    "doiexacter": "doiexacter.py"       # 指定文档 DOI 提取脚本 (新增)
}

# 3. 配置文件 JSON 文件名配置
JSON_FILENAMES = {
    "paper": "Paperkeyword.json",       # 关键词配置
    "login": "LoginConfig.json",        # 登录域名配置
    "si": "SIkeyword.json",             # SI 关键词配置
    "settings": "DownloadSettings.json",# 下载参数配置
    "templates": "DownloadTemplates.json",# 模板链接配置
    "branch": "DomainBranch.json"       # 域名分支配置
}

# ==============================================================================
#  【主程序逻辑】
# ==============================================================================

class PaperAutomationConsole:
    def __init__(self, root):
        self.root = root
        self.root.title("论文下载全流程自动化管理控制台")
        self.root.geometry("1200x950")
        
        # --- 初始化路径映射 (将配置区的文件名转换为绝对路径) ---
        self.SCRIPTS = {
            key: os.path.join(BASE_DIR, filename) 
            for key, filename in SCRIPT_NAMES.items()
        }
        
        self.json_files = {
            key: os.path.join(BASE_DIR, filename)
            for key, filename in JSON_FILENAMES.items()
        }
        
        # 打印调试信息
        print(f"当前工作基准路径: {BASE_DIR}")

        self.setup_ui()
        self.load_all_configs()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 标签页 1: 流程执行与规则向导
        self.run_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.run_frame, text=" 任务执行与规则向导 ")
        self.setup_run_and_wizard_tab()

        # 标签页 2: 全局参数管理
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text=" 脚本内部参数管理 ")
        self.setup_app_config_tab()

        # 标签页 3: JSON 源码编辑
        self.editor_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.editor_frame, text=" JSON 源码编辑器 ")
        self.setup_json_editor_tab()

    def setup_run_and_wizard_tab(self):
        # 左侧：脚本启动
        left_frame = ttk.LabelFrame(self.run_frame, text=" 核心任务启动 ")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Button(left_frame, text="🚀 启动全自动下载流程", width=30, command=self.run_full_automation).pack(pady=10)
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        tasks = [
            (self.SCRIPTS["getdoi"], "1. PubMed 调度"),
            (self.SCRIPTS["paper"], "2. 论文正文下载"),
            (self.SCRIPTS["si"], "3. 补充材料下载"),
            (self.SCRIPTS["clean"], "4. 坏文件清理"),
            (self.SCRIPTS["csv_turner"], "5. 提取失败 DOI"),
            (self.SCRIPTS["doiexacter"], "6. 指定文档 DOI 提取")
        ]
        for filepath, nickname in tasks:
            f = ttk.Frame(left_frame)
            f.pack(fill=tk.X, padx=20, pady=5)
            ttk.Button(f, text=nickname, width=28, command=lambda s=filepath: self.execute_script(s)).pack(side=tk.LEFT)

        # 右侧：向导功能 (完全保留您要求的 1-2-3 步逻辑)
        right_frame = ttk.LabelFrame(self.run_frame, text=" 域名规则向导 ")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(right_frame, text="第一步: 输入文章完整 URL").pack(anchor=tk.W, padx=10, pady=2)
        self.wizard_url = ttk.Entry(right_frame, width=50)
        self.wizard_url.pack(fill=tk.X, padx=10, pady=2)

        ttk.Label(right_frame, text="第二步: 确认下载路径").pack(anchor=tk.W, padx=10, pady=(10,2))
        self.is_auto_var = tk.BooleanVar(value=True)
        ttk.Radiobutton(right_frame, text="自动下载 (不需 Ctrl+S)", variable=self.is_auto_var, value=True).pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(right_frame, text="手动下载 (预览页需保存)", variable=self.is_auto_var, value=False).pack(anchor=tk.W, padx=20)

        ttk.Label(right_frame, text="第三步: 选择获取方式").pack(anchor=tk.W, padx=10, pady=(10,2))
        self.method_var = tk.StringVar(value="1")
        ttk.Radiobutton(right_frame, text="方式1: 模板下载 (输入带{doi}的链接)", variable=self.method_var, value="1").pack(anchor=tk.W, padx=20)
        self.wizard_template = ttk.Entry(right_frame, width=50)
        self.wizard_template.pack(fill=tk.X, padx=30, pady=2)
        
        ttk.Radiobutton(right_frame, text="方式2: 检索下载 (输入源码关键词)", variable=self.method_var, value="2").pack(anchor=tk.W, padx=20)
        self.wizard_keyword = ttk.Entry(right_frame, width=50)
        self.wizard_keyword.pack(fill=tk.X, padx=30, pady=2)

        btn_f = ttk.Frame(right_frame)
        btn_f.pack(pady=20)
        ttk.Button(btn_f, text="✅ 按照向导添加规则", command=self.wizard_add_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="🗑️ 删除该域名所有数据", command=self.wizard_delete_data).pack(side=tk.LEFT, padx=5)

    def setup_app_config_tab(self):
        """参数管理页"""
        canvas = tk.Canvas(self.config_frame)
        scrollbar = ttk.Scrollbar(self.config_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        container = ttk.Frame(scrollable_frame)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 路径设置
        path_group = ttk.LabelFrame(container, text=" 路径与文件夹配置 ")
        path_group.pack(fill=tk.X, pady=5)
        self.path_entries = {}
        path_fields = [
            ("DOWNLOAD_PATH", "HTML 缓存路径"),
            ("PAPER_FOLDER", "正文保存文件夹"),
            ("SI_FOLDER", "SI 保存文件夹"),
            ("CSV_PATH", "论文列表 CSV 路径"),
            ("CLEAN_FOLDER", "筛选程序：清理目标文件夹"),
            ("CLEAN_CSV_IN", "筛选程序：输入 CSV 路径 "),
            ("CLEAN_CSV_OUT", "筛选程序：输出 CSV 路径 "),
            ("TURNER_IN", "失败提取：输入 CSV"),
            ("TURNER_OUT", "失败提取：输出 CSV"),
            ("EXACT_IN", "文档提取：源文件路径"), 
            ("EXACT_OUT", "文档提取：目标 CSV 路径")  
        ]
        for i, (key, label) in enumerate(path_fields):
            ttk.Label(path_group, text=label).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            ent = ttk.Entry(path_group, width=70)
            ent.grid(row=i, column=1, padx=5)
            self.path_entries[key] = ent
            ttk.Button(path_group, text="浏览", command=lambda k=key: self.browse_path(k)).grid(row=i, column=2)

        # 参数设置
        param_group = ttk.LabelFrame(container, text=" 逻辑、时间与筛选参数 ")
        param_group.pack(fill=tk.X, pady=10)
        self.param_entries = {}
        self.sel_var = tk.StringVar(value="False")
        ttk.Label(param_group, text="使用 Selenium (True/False):").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(param_group, textvariable=self.sel_var, width=15).grid(row=0, column=1, sticky=tk.W)

        param_fields = [
            ("DELAY_PAPER", "正文下载间隔(秒)"),
            ("DELAY_SI", "SI 下载间隔(秒)"),
            ("TIMEOUT", "页面加载超时(秒)"),
            ("CLEAN_THRESHOLD", "坏文件清理阈值 (KB)")
        ]
        for i, (key, label) in enumerate(param_fields, 1):
            ttk.Label(param_group, text=label + ":").grid(row=i, column=0, sticky=tk.W, padx=5, pady=5)
            ent = ttk.Entry(param_group, width=15)
            ent.grid(row=i, column=1, sticky=tk.W)
            self.param_entries[key] = ent

        ttk.Label(container, text="PubMed 检索关键词 (SEARCH_QUERY):", font=('Microsoft YaHei', 9, 'bold')).pack(anchor=tk.W)
        self.query_text = tk.Text(container, height=4, font=('Consolas', 10))
        self.query_text.pack(fill=tk.X, pady=5)

        ttk.Button(container, text="💾 保存所有配置到脚本", command=self.save_all_configs).pack(pady=15)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def setup_json_editor_tab(self):
        self.editor_nb = ttk.Notebook(self.editor_frame)
        self.editor_nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.editor_texts = {}

        for key, filepath in self.json_files.items():
            display_name = os.path.basename(filepath)
            frame = ttk.Frame(self.editor_nb)
            self.editor_nb.add(frame, text=display_name)
            txt = tk.Text(frame, font=('Consolas', 10), undo=True)
            txt.pack(fill=tk.BOTH, expand=True)
            self.editor_texts[filepath] = txt
            ttk.Button(frame, text=f"保存修改到 {display_name}", 
                       command=lambda f=filepath: self.save_json_from_editor(f)).pack(pady=5)
        
        ttk.Button(self.editor_frame, text="刷新/读取所有 JSON 内容", command=self.refresh_editor_content).pack(pady=5)

    # --- 核心向导逻辑 (完全恢复您提供的实现) ---
    def wizard_add_data(self):
        raw_url = self.wizard_url.get().strip()
        if not raw_url:
            messagebox.showwarning("提示", "请输入文章完整 URL")
            return
        
        try:
            parts = raw_url.split('/')
            host = parts[2] if len(parts) > 2 else raw_url
            url = host
            domain = host.replace("www.", "")
        except: return

        # 1. DownloadSettings.json
        settings = self.safe_read_json(self.json_files["settings"])
        # 处理可能的嵌套结构
        if "domains" not in settings: settings["domains"] = {}
        settings["domains"][domain] = {
            "use_ctrl_s": not self.is_auto_var.get(),
            "ctrl_s_delay": 40,
            "max_retries": 1,
            "retry_delay": 40
        }
        self.safe_write_json(self.json_files["settings"], settings)

        # 2. 方式处理
        method = self.method_var.get()
        if method == "1":
            t_url = self.wizard_template.get().strip()
            templates = self.safe_read_json(self.json_files["templates"])
            templates[domain] = t_url
            self.safe_write_json(self.json_files["templates"], templates)
            
            branch = self.safe_read_json(self.json_files["branch"])
            if not any(i.get("domain") == domain for i in branch):
                branch.append({"domain": domain, "direct": "1"})
                self.safe_write_json(self.json_files["branch"], branch)
        else:
            kw = self.wizard_keyword.get().strip()
            paper = self.safe_read_json(self.json_files["paper"])
            paper.append({"url": url, "login": "1", "keywords": [kw]})
            self.safe_write_json(self.json_files["paper"], paper)

        # 3. LoginConfig.json
        login = self.safe_read_json(self.json_files["login"])
        if domain not in login:
            login.append(domain)
            self.safe_write_json(self.json_files["login"], login)
        
        messagebox.showinfo("成功", f"域名 {domain} 规则已成功添加")
        self.refresh_editor_content()

    def wizard_delete_data(self):
        raw_url = self.wizard_url.get().strip()
        if not raw_url: return
        target = raw_url.split('/')[2].replace("www.", "") if '/' in raw_url else raw_url.replace("www.", "")
        
        if not messagebox.askyesno("确认", f"确定要从所有文件中删除与 {target} 相关的数据吗？"):
            return

        # 批量清理
        s = self.safe_read_json(self.json_files["settings"])
        if "domains" in s and target in s["domains"]: del s["domains"][target]
        self.safe_write_json(self.json_files["settings"], s)

        t = self.safe_read_json(self.json_files["templates"])
        if target in t: del t[target]
        self.safe_write_json(self.json_files["templates"], t)

        login = self.safe_read_json(self.json_files["login"])
        login = [i for i in login if i != target]
        self.safe_write_json(self.json_files["login"], login)

        for fkey in ["branch", "paper", "si"]:
            data = self.safe_read_json(self.json_files[fkey])
            data = [i for i in data if i.get("domain", i.get("url")) != target and i.get("url") != "www."+target]
            self.safe_write_json(self.json_files[fkey], data)

        messagebox.showinfo("清理完成", f"已从所有 JSON 中移除 {target}")
        self.refresh_editor_content()

    # --- 脚本参数同步逻辑 (保留原所有正则替换并新增 doiexacter) ---
    def load_all_configs(self):
        try:
            # Paperdownload.py
            if os.path.exists(self.SCRIPTS["paper"]):
                with open(self.SCRIPTS["paper"], 'r', encoding='utf-8') as f: c = f.read()
                self._fill(self.path_entries["DOWNLOAD_PATH"], re.search(r'DOWNLOAD_PATH\s*=\s*r"([^"]+)"', c))
                self._fill(self.path_entries["PAPER_FOLDER"], re.search(r'PAPER_DOWNLOAD_FOLDER\s*=\s*r"([^"]+)"', c))
                self._fill(self.path_entries["CSV_PATH"], re.search(r'CSV_PATH\s*=\s*r"([^"]+)"', c))
                self._fill(self.param_entries["DELAY_PAPER"], re.search(r'DELAY_BETWEEN_PAPERS\s*=\s*(\d+)', c))
                self._fill(self.param_entries["TIMEOUT"], re.search(r'PAGE_LOAD_TIMEOUT\s*=\s*(\d+)', c))
                sel = re.search(r'USE_SELENIUM\s*=\s*(True|False)', c)
                if sel: self.sel_var.set(sel.group(1))

            # SIdownload.py
            if os.path.exists(self.SCRIPTS["si"]):
                with open(self.SCRIPTS["si"], 'r', encoding='utf-8') as f: c = f.read()
                self._fill(self.path_entries["SI_FOLDER"], re.search(r'"SI_DOWNLOAD_FOLDER":\s*r"([^"]+)"', c))
                self._fill(self.param_entries["DELAY_SI"], re.search(r'"DELAY_BETWEEN_PAPERS":\s*(\d+)', c))

            # 筛选文件大小.py
            if os.path.exists(self.SCRIPTS["clean"]):
                with open(self.SCRIPTS["clean"], 'r', encoding='utf-8') as f: c = f.read()
                thresh = re.search(r'SIZE_THRESHOLD\s*=\s*(\d+)\s*\*\s*1024', c)
                if thresh: self.param_entries["CLEAN_THRESHOLD"].delete(0, tk.END); self.param_entries["CLEAN_THRESHOLD"].insert(0, thresh.group(1))
                self._fill(self.path_entries["CLEAN_FOLDER"], re.search(r'advanced_path_matching_process\(\s*r"([^"]+)"', c))
                self._fill(self.path_entries["CLEAN_CSV_IN"], re.search(r'advanced_path_matching_process\(\s*r"[^"]+",\s*r"([^"]+)"', c))
                self._fill(self.path_entries["CLEAN_CSV_OUT"], re.search(r'advanced_path_matching_process\(\s*r"[^"]+",\s*r"[^"]+",\s*r"([^"]+)"', c))

            # getdoi_helper.py
            if os.path.exists(self.SCRIPTS["getdoi"]):
                with open(self.SCRIPTS["getdoi"], 'r', encoding='utf-8') as f:
                    m = re.search(r'SEARCH_QUERY\s*=\s*"(.*?)"', f.read(), re.DOTALL)
                    if m: self.query_text.delete("1.0", tk.END); self.query_text.insert("1.0", m.group(1))

            # Csv_Turner_strenth.py
            if os.path.exists(self.SCRIPTS["csv_turner"]):
                with open(self.SCRIPTS["csv_turner"], 'r', encoding='utf-8') as f: c = f.read()
                self._fill(self.path_entries["TURNER_IN"], re.search(r'input_file\s*=\s*r"([^"]+)"', c))
                self._fill(self.path_entries["TURNER_OUT"], re.search(r'output_file\s*=\s*r"([^"]+)"', c))

            # doiexacter.py (新增读取逻辑)
            if os.path.exists(self.SCRIPTS["doiexacter"]):
                with open(self.SCRIPTS["doiexacter"], 'r', encoding='utf-8') as f: c = f.read()
                self._fill(self.path_entries["EXACT_IN"], re.search(r'INPUT_FILE\s*=\s*r"([^"]+)"', c))
                self._fill(self.path_entries["EXACT_OUT"], re.search(r'CSV_FILE\s*=\s*r"([^"]+)"', c))

            self.refresh_editor_content()
        except Exception as e: print(f"读取配置时出错: {e}")

    def save_all_configs(self):
        try:
            def esc(key): return self.path_entries[key].get().replace('\\', '\\\\')

            # 更新 Paperdownload.py
            if os.path.exists(self.SCRIPTS["paper"]):
                with open(self.SCRIPTS["paper"], 'r', encoding='utf-8') as f: c = f.read()
                c = re.sub(r'DOWNLOAD_PATH\s*=\s*r"[^"]+"', f'DOWNLOAD_PATH = r"{esc("DOWNLOAD_PATH")}"', c)
                c = re.sub(r'PAPER_DOWNLOAD_FOLDER\s*=\s*r"[^"]+"', f'PAPER_DOWNLOAD_FOLDER = r"{esc("PAPER_FOLDER")}"', c)
                c = re.sub(r'CSV_PATH\s*=\s*r"[^"]+"', f'CSV_PATH = r"{esc("CSV_PATH")}"', c)
                c = re.sub(r'DELAY_BETWEEN_PAPERS\s*=\s*\d+', f'DELAY_BETWEEN_PAPERS = {self.param_entries["DELAY_PAPER"].get()}', c)
                c = re.sub(r'PAGE_LOAD_TIMEOUT\s*=\s*\d+', f'PAGE_LOAD_TIMEOUT = {self.param_entries["TIMEOUT"].get()}', c)
                c = re.sub(r'USE_SELENIUM\s*=\s*(True|False)', f'USE_SELENIUM = {self.sel_var.get()}', c)
                with open(self.SCRIPTS["paper"], 'w', encoding='utf-8') as f: f.write(c)

            # 更新 SIdownload.py
            if os.path.exists(self.SCRIPTS["si"]):
                with open(self.SCRIPTS["si"], 'r', encoding='utf-8') as f: c = f.read()
                c = re.sub(r'"SI_DOWNLOAD_FOLDER":\s*r"[^"]+"', f'"SI_DOWNLOAD_FOLDER": r"{esc("SI_FOLDER")}"', c)
                c = re.sub(r'"DELAY_BETWEEN_PAPERS":\s*\d+', f'"DELAY_BETWEEN_PAPERS": {self.param_entries["DELAY_SI"].get()}', c)
                with open(self.SCRIPTS["si"], 'w', encoding='utf-8') as f: f.write(c)

            # 更新 筛选文件大小.py
            if os.path.exists(self.SCRIPTS["clean"]):
                with open(self.SCRIPTS["clean"], 'r', encoding='utf-8') as f: c = f.read()
                c = re.sub(r'SIZE_THRESHOLD\s*=\s*\d+\s*\*\s*1024', f'SIZE_THRESHOLD = {self.param_entries["CLEAN_THRESHOLD"].get()} * 1024', c)
                p_cl, p_in, p_out = esc("CLEAN_FOLDER"), esc("CLEAN_CSV_IN"), esc("CLEAN_CSV_OUT")
                pat = r'(advanced_path_matching_process\(\s*)r"[^"]+",\s*r"[^"]+",\s*r"[^"]+"'
                c = re.sub(pat, rf'\1r"{p_cl}", r"{p_in}", r"{p_out}"', c)
                with open(self.SCRIPTS["clean"], 'w', encoding='utf-8') as f: f.write(c)

            # 更新 getdoi_helper.py
            if os.path.exists(self.SCRIPTS["getdoi"]):
                with open(self.SCRIPTS["getdoi"], 'r', encoding='utf-8') as f: c = f.read()
                q = self.query_text.get("1.0", tk.END).strip().replace('\n', '')
                c = re.sub(r'SEARCH_QUERY\s*=\s*".*?"', f'SEARCH_QUERY = "{q}"', c, flags=re.DOTALL)
                with open(self.SCRIPTS["getdoi"], 'w', encoding='utf-8') as f: f.write(c)

            # 更新 Csv_Turner_strenth.py
            if os.path.exists(self.SCRIPTS["csv_turner"]):
                with open(self.SCRIPTS["csv_turner"], 'r', encoding='utf-8') as f: c = f.read()
                c = re.sub(r'input_file\s*=\s*r"[^"]+"', f'input_file = r"{esc("TURNER_IN")}"', c)
                c = re.sub(r'output_file\s*=\s*r"[^"]+"', f'output_file = r"{esc("TURNER_OUT")}"', c)
                with open(self.SCRIPTS["csv_turner"], 'w', encoding='utf-8') as f: f.write(c)

            # 更新 doiexacter.py (新增保存逻辑)
            if os.path.exists(self.SCRIPTS["doiexacter"]):
                with open(self.SCRIPTS["doiexacter"], 'r', encoding='utf-8') as f: c = f.read()
                c = re.sub(r'INPUT_FILE\s*=\s*r"[^"]+"', f'INPUT_FILE = r"{esc("EXACT_IN")}"', c)
                c = re.sub(r'CSV_FILE\s*=\s*r"[^"]+"', f'CSV_FILE = r"{esc("EXACT_OUT")}"', c)
                with open(self.SCRIPTS["doiexacter"], 'w', encoding='utf-8') as f: f.write(c)
                
            messagebox.showinfo("成功", "所有脚本参数同步保存成功")
        except Exception as e: messagebox.showerror("失败", f"保存失败:\n{str(e)}")

    def execute_script(self, filepath):
        def run():
            self._fix_error(filepath)
            popen_kwargs = {}
            if is_windows() and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([sys.executable, filepath], **popen_kwargs)
        threading.Thread(target=run, daemon=True).start()

    def _fix_error(self, filename):
        if not os.path.exists(filename): return
        with open(filename, 'r', encoding='utf-8') as f: c = f.read()
        fixed = re.sub(r'\s*\+\]', '', c)
        if c != fixed:
            with open(filename, 'w', encoding='utf-8') as f: f.write(fixed)

    def refresh_editor_content(self):
        for filepath, txt in self.editor_texts.items():
            txt.delete("1.0", tk.END)
            txt.insert("1.0", json.dumps(self.safe_read_json(filepath), indent=4, ensure_ascii=False))

    def save_json_from_editor(self, filepath):
        try:
            d = json.loads(self.editor_texts[filepath].get("1.0", tk.END).strip())
            self.safe_write_json(filepath, d)
            messagebox.showinfo("成功", f"{os.path.basename(filepath)} 已保存")
        except Exception as e: messagebox.showerror("错误", str(e))

    def safe_read_json(self, f):
        if not os.path.exists(f): return {"domains":{}} if "Settings" in f else []
        with open(f, 'r', encoding='utf-8') as fl: return json.load(fl)

    def safe_write_json(self, f, data):
        with open(f, 'w', encoding='utf-8') as fl: json.dump(data, fl, indent=4, ensure_ascii=False)

    def _fill(self, ent, m):
        if m: ent.delete(0, tk.END); ent.insert(0, m.group(1))

    def browse_path(self, key):
        p = filedialog.askopenfilename() if "CSV" in key or "IN" in key or "OUT" in key else filedialog.askdirectory()
        if p:
            abs_p = os.path.abspath(p)
            self.path_entries[key].delete(0, tk.END)
            self.path_entries[key].insert(0, abs_p)

    def run_full_automation(self):
        if messagebox.askyesno("确认", "启动全自动下载流程？"):
            self.execute_script(self.SCRIPTS["getdoi"])

if __name__ == "__main__":
    root = tk.Tk()
    PaperAutomationConsole(root)
    root.mainloop()
