import csv
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import psutil

from app_version import APP_VERSION
from log_utils import setup_script_logging
from runtime_config import load_runtime_config, save_runtime_config
from runtime_exec import resolve_worker_command, script_name_for_key
from runtime_paths import data_path, ensure_runtime_layout, get_bundle_dir, get_data_dir

# ==============================================================================
#  【全局配置区】 - 在此处修改文件名和基础设置
# ==============================================================================

BUNDLE_DIR = get_bundle_dir()
DATA_DIR = get_data_dir()

SCRIPT_NAMES = {
    "getdoi": "getdoi_helper.py",
    "paper": "Paperdownload.py",
    "si": "SIdownload.py",
    "clean": "clean_worker.py",
    "csv_turner": "Csv_Turner_strenth.py",
    "doiexacter": "doiexacter.py",
}

JSON_FILENAMES = {
    "paper": "Paperkeyword.json",
    "login": "LoginConfig.json",
    "si": "SIkeyword.json",
    "settings": "DownloadSettings.json",
    "templates": "DownloadTemplates.json",
    "branch": "DomainBranch.json",
}

CSV_DEFAULT_PATH = data_path("PaperDoi.csv")
LOG_DIR = data_path("log")
MAX_LOG_LINES = 5000


class PaperAutomationConsole:
    def __init__(self, root: tk.Tk):
        ensure_runtime_layout()
        self.root = root
        self.root.title(f"论文下载全流程自动化管理控制台 v{APP_VERSION}")
        self.root.geometry("1280x980")

        self.SCRIPTS = {key: os.path.join(BUNDLE_DIR, filename) for key, filename in SCRIPT_NAMES.items()}
        self.json_files = {key: data_path(filename) for key, filename in JSON_FILENAMES.items()}

        # 运行监控状态
        self.process_registry = {}
        self.item_pid_map = {}
        self.log_queue = queue.Queue()
        self.log_file_offsets = {}
        self.log_paused = False
        self.log_line_count = 0
        self.current_script_only = tk.BooleanVar(value=False)
        self.current_script_name = ""
        self.running_count_var = tk.StringVar(value="运行中数量: 0")
        self.latest_script_var = tk.StringVar(value="最近启动脚本: -")
        self.status_updated_var = tk.StringVar(value="状态更新时间: -")
        self.log_filter_target_var = tk.StringVar(value="当前脚本: 全部脚本")
        self.log_start_epoch = datetime.now().timestamp()
        self.pause_button_text = tk.StringVar(value="暂停滚动")

        # CSV 状态
        self.csv_sort_orders = {}
        self.csv_columns = []
        self.csv_data_rows = []
        self.csv_path_var = tk.StringVar(value=CSV_DEFAULT_PATH)
        self.csv_row_count_var = tk.StringVar(value="总行数: 0")
        self.csv_refresh_time_var = tk.StringVar(value="最后刷新: -")
        self.csv_error_var = tk.StringVar(value="")

        # 目录浏览状态
        self.folder_auto_refresh = tk.BooleanVar(value=True)
        self.folder_dirs = {
            "html": data_path("html"),
            "RSS": data_path("RSS"),
            "Paper": data_path("Paper"),
            "SI": data_path("SI"),
        }
        self.folder_trees = {}
        self.folder_item_paths = {}
        self.folder_status_vars = {}

        print(f"当前资源目录: {BUNDLE_DIR}")
        print(f"当前数据目录: {DATA_DIR}")
        self.setup_ui()
        self.load_all_configs()
        self._refresh_csv_table()
        self._refresh_all_folders()

        self.root.after(200, self._drain_log_queue)
        self.root.after(1000, self._poll_log_files)
        self.root.after(1000, self._poll_process_status)
        self.root.after(3000, self._auto_refresh_folders)

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.run_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.run_frame, text=" 任务执行与规则向导 ")
        self.setup_run_and_wizard_tab()

        self.monitor_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.monitor_frame, text=" 运行监控 ")
        self.setup_monitor_tab()

        self.csv_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.csv_frame, text=" CSV查看 ")
        self.setup_csv_view_tab()

        self.folder_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.folder_frame, text=" 目录浏览 ")
        self.setup_folder_browser_tab()

        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text=" 脚本内部参数管理 ")
        self.setup_app_config_tab()

        self.editor_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.editor_frame, text=" JSON 源码编辑器 ")
        self.setup_json_editor_tab()

    def setup_run_and_wizard_tab(self):
        left_frame = ttk.LabelFrame(self.run_frame, text=" 核心任务启动 ")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Button(left_frame, text="启动全自动下载流程", width=30, command=self.run_full_automation).pack(pady=10)
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        tasks = [
            ("getdoi", "1. PubMed 调度"),
            ("paper", "2. 论文正文下载"),
            ("si", "3. 补充材料下载"),
            ("clean", "4. 坏文件清理"),
            ("csv_turner", "5. 提取失败 DOI"),
            ("doiexacter", "6. 指定文档 DOI 提取"),
        ]
        for script_key, nickname in tasks:
            frame = ttk.Frame(left_frame)
            frame.pack(fill=tk.X, padx=20, pady=5)
            ttk.Button(frame, text=nickname, width=28, command=lambda s=script_key: self.execute_script(s)).pack(side=tk.LEFT)

        right_frame = ttk.LabelFrame(self.run_frame, text=" 域名规则向导 ")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(right_frame, text="第一步: 输入文章完整 URL").pack(anchor=tk.W, padx=10, pady=2)
        self.wizard_url = ttk.Entry(right_frame, width=50)
        self.wizard_url.pack(fill=tk.X, padx=10, pady=2)

        ttk.Label(right_frame, text="第二步: 确认下载路径").pack(anchor=tk.W, padx=10, pady=(10, 2))
        self.is_auto_var = tk.BooleanVar(value=True)
        ttk.Radiobutton(
            right_frame,
            text="自动下载 (不需 Ctrl+S)",
            variable=self.is_auto_var,
            value=True,
        ).pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(
            right_frame,
            text="手动下载 (预览页需保存)",
            variable=self.is_auto_var,
            value=False,
        ).pack(anchor=tk.W, padx=20)

        ttk.Label(right_frame, text="第三步: 选择获取方式").pack(anchor=tk.W, padx=10, pady=(10, 2))
        self.method_var = tk.StringVar(value="1")
        ttk.Radiobutton(
            right_frame,
            text="方式1: 模板下载 (输入带{doi}的链接)",
            variable=self.method_var,
            value="1",
        ).pack(anchor=tk.W, padx=20)
        self.wizard_template = ttk.Entry(right_frame, width=50)
        self.wizard_template.pack(fill=tk.X, padx=30, pady=2)

        ttk.Radiobutton(
            right_frame,
            text="方式2: 检索下载 (输入源码关键词)",
            variable=self.method_var,
            value="2",
        ).pack(anchor=tk.W, padx=20)
        self.wizard_keyword = ttk.Entry(right_frame, width=50)
        self.wizard_keyword.pack(fill=tk.X, padx=30, pady=2)

        button_frame = ttk.Frame(right_frame)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text="按照向导添加规则", command=self.wizard_add_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除该域名所有数据", command=self.wizard_delete_data).pack(side=tk.LEFT, padx=5)

    def setup_monitor_tab(self):
        top_frame = ttk.LabelFrame(self.monitor_frame, text=" 任务状态 ")
        top_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=8)

        summary_frame = ttk.Frame(top_frame)
        summary_frame.pack(fill=tk.X, padx=6, pady=(6, 2))
        ttk.Label(summary_frame, textvariable=self.running_count_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(summary_frame, textvariable=self.latest_script_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(summary_frame, textvariable=self.status_updated_var).pack(side=tk.LEFT)

        self.process_tree = ttk.Treeview(
            top_frame,
            columns=("script", "pid", "start", "status"),
            show="headings",
            height=6,
        )
        for col, width, title in [
            ("script", 280, "脚本名"),
            ("pid", 100, "PID"),
            ("start", 220, "开始时间"),
            ("status", 160, "状态"),
        ]:
            self.process_tree.heading(col, text=title)
            self.process_tree.column(col, width=width, anchor=tk.W)
        self.process_tree.tag_configure("running", background="#e6f4ea")
        self.process_tree.tag_configure("stopping", background="#fff4ce")
        self.process_tree.tag_configure("exited", foreground="#666666")

        proc_scroll = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.process_tree.yview)
        self.process_tree.configure(yscrollcommand=proc_scroll.set)
        self.process_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=6)
        proc_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=6)
        self.process_tree.bind("<<TreeviewSelect>>", self._on_process_tree_select)

        log_ctrl = ttk.Frame(self.monitor_frame)
        log_ctrl.pack(fill=tk.X, padx=10, pady=(4, 0))
        ttk.Button(log_ctrl, text="停止选中脚本", command=self._stop_selected_process).pack(side=tk.LEFT)
        ttk.Button(log_ctrl, text="停止全部脚本", command=self._stop_all_processes).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(
            log_ctrl,
            text="仅当前脚本",
            variable=self.current_script_only,
            command=self._on_toggle_current_script_filter,
        ).pack(side=tk.LEFT)
        ttk.Button(log_ctrl, textvariable=self.pause_button_text, command=self._toggle_log_pause).pack(side=tk.LEFT, padx=6)
        ttk.Button(log_ctrl, text="清空日志", command=self._clear_log_text).pack(side=tk.LEFT, padx=6)
        ttk.Label(log_ctrl, textvariable=self.log_filter_target_var).pack(side=tk.RIGHT)

        log_frame = ttk.LabelFrame(self.monitor_frame, text=" 实时日志 ")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self.log_text = ScrolledText(log_frame, height=20, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def setup_csv_view_tab(self):
        info_frame = ttk.LabelFrame(self.csv_frame, text=" CSV信息 ")
        info_frame.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(info_frame, text="路径:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(info_frame, textvariable=self.csv_path_var).grid(row=0, column=1, sticky=tk.W, padx=6, pady=4)
        ttk.Label(info_frame, textvariable=self.csv_row_count_var).grid(row=1, column=0, sticky=tk.W, padx=6, pady=4)
        ttk.Label(info_frame, textvariable=self.csv_refresh_time_var).grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)
        ttk.Label(info_frame, textvariable=self.csv_error_var, foreground="red").grid(
            row=2, column=0, columnspan=2, sticky=tk.W, padx=6, pady=4
        )
        ttk.Button(info_frame, text="刷新", command=self._refresh_csv_table).grid(row=0, column=2, rowspan=2, padx=10, pady=4)

        table_frame = ttk.Frame(self.csv_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.csv_tree = ttk.Treeview(table_frame, show="headings")
        csv_v_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.csv_tree.yview)
        csv_h_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.csv_tree.xview)
        self.csv_tree.configure(yscrollcommand=csv_v_scroll.set, xscrollcommand=csv_h_scroll.set)

        self.csv_tree.grid(row=0, column=0, sticky="nsew")
        csv_v_scroll.grid(row=0, column=1, sticky="ns")
        csv_h_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    def setup_folder_browser_tab(self):
        ctrl_frame = ttk.Frame(self.folder_frame)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(ctrl_frame, text="刷新全部", command=self._refresh_all_folders).pack(side=tk.LEFT)
        ttk.Checkbutton(ctrl_frame, text="自动刷新(3秒)", variable=self.folder_auto_refresh).pack(side=tk.LEFT, padx=8)

        self.folder_notebook = ttk.Notebook(self.folder_frame)
        self.folder_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        for folder_name, folder_path in self.folder_dirs.items():
            frame = ttk.Frame(self.folder_notebook)
            self.folder_notebook.add(frame, text=folder_name)

            ttk.Label(frame, text=f"路径: {folder_path}").pack(anchor=tk.W, padx=6, pady=(6, 2))
            status_var = tk.StringVar(value="未刷新")
            self.folder_status_vars[folder_name] = status_var
            ttk.Label(frame, textvariable=status_var).pack(anchor=tk.W, padx=6, pady=(0, 6))

            tree_frame = ttk.Frame(frame)
            tree_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
            tree = ttk.Treeview(tree_frame, columns=("name", "type", "size", "modified"), show="headings")
            for col, width, title in [
                ("name", 460, "名称"),
                ("type", 110, "类型"),
                ("size", 120, "大小"),
                ("modified", 200, "修改时间"),
            ]:
                tree.heading(col, text=title)
                tree.column(col, width=width, anchor=tk.W)

            v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
            h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=tree.xview)
            tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

            tree.grid(row=0, column=0, sticky="nsew")
            v_scroll.grid(row=0, column=1, sticky="ns")
            h_scroll.grid(row=1, column=0, sticky="ew")
            tree_frame.rowconfigure(0, weight=1)
            tree_frame.columnconfigure(0, weight=1)

            tree.bind("<Double-1>", lambda event, key=folder_name: self._on_folder_item_double_click(event, key))
            self.folder_trees[folder_name] = tree
            self.folder_item_paths[folder_name] = {}

    def setup_app_config_tab(self):
        canvas = tk.Canvas(self.config_frame)
        scrollbar = ttk.Scrollbar(self.config_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        container = ttk.Frame(scrollable_frame)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

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
            ("EXACT_OUT", "文档提取：目标 CSV 路径"),
        ]
        for index, (key, label) in enumerate(path_fields):
            ttk.Label(path_group, text=label).grid(row=index, column=0, sticky=tk.W, padx=5, pady=2)
            entry = ttk.Entry(path_group, width=70)
            entry.grid(row=index, column=1, padx=5)
            self.path_entries[key] = entry
            ttk.Button(path_group, text="浏览", command=lambda k=key: self.browse_path(k)).grid(row=index, column=2)

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
            ("CLEAN_THRESHOLD", "坏文件清理阈值 (KB)"),
        ]
        for index, (key, label) in enumerate(param_fields, 1):
            ttk.Label(param_group, text=label + ":").grid(row=index, column=0, sticky=tk.W, padx=5, pady=5)
            entry = ttk.Entry(param_group, width=15)
            entry.grid(row=index, column=1, sticky=tk.W)
            self.param_entries[key] = entry

        ttk.Label(container, text="PubMed 检索关键词 (SEARCH_QUERY):", font=("Microsoft YaHei", 9, "bold")).pack(anchor=tk.W)
        self.query_text = tk.Text(container, height=4, font=("Consolas", 10))
        self.query_text.pack(fill=tk.X, pady=5)

        ttk.Button(container, text="保存运行时配置", command=self.save_all_configs).pack(pady=15)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def setup_json_editor_tab(self):
        self.editor_nb = ttk.Notebook(self.editor_frame)
        self.editor_nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.editor_texts = {}

        for _, filepath in self.json_files.items():
            display_name = os.path.basename(filepath)
            frame = ttk.Frame(self.editor_nb)
            self.editor_nb.add(frame, text=display_name)
            text = tk.Text(frame, font=("Consolas", 10), undo=True)
            text.pack(fill=tk.BOTH, expand=True)
            self.editor_texts[filepath] = text
            ttk.Button(frame, text=f"保存修改到 {display_name}", command=lambda f=filepath: self.save_json_from_editor(f)).pack(
                pady=5
            )

        ttk.Button(self.editor_frame, text="刷新/读取所有 JSON 内容", command=self.refresh_editor_content).pack(pady=5)

    def wizard_add_data(self):
        raw_url = self.wizard_url.get().strip()
        if not raw_url:
            messagebox.showwarning("提示", "请输入文章完整 URL")
            return

        try:
            parts = raw_url.split("/")
            host = parts[2] if len(parts) > 2 else raw_url
            url = host
            domain = host.replace("www.", "")
        except Exception:
            return

        settings = self.safe_read_json(self.json_files["settings"])
        if "domains" not in settings:
            settings["domains"] = {}
        settings["domains"][domain] = {
            "use_ctrl_s": not self.is_auto_var.get(),
            "ctrl_s_delay": 40,
            "max_retries": 1,
            "retry_delay": 40,
        }
        self.safe_write_json(self.json_files["settings"], settings)

        method = self.method_var.get()
        if method == "1":
            template_url = self.wizard_template.get().strip()
            templates = self.safe_read_json(self.json_files["templates"])
            templates[domain] = template_url
            self.safe_write_json(self.json_files["templates"], templates)

            branch = self.safe_read_json(self.json_files["branch"])
            if not any(item.get("domain") == domain for item in branch):
                branch.append({"domain": domain, "direct": "1"})
                self.safe_write_json(self.json_files["branch"], branch)
        else:
            keyword = self.wizard_keyword.get().strip()
            paper = self.safe_read_json(self.json_files["paper"])
            paper.append({"url": url, "login": "1", "keywords": [keyword]})
            self.safe_write_json(self.json_files["paper"], paper)

        login = self.safe_read_json(self.json_files["login"])
        if domain not in login:
            login.append(domain)
            self.safe_write_json(self.json_files["login"], login)

        messagebox.showinfo("成功", f"域名 {domain} 规则已成功添加")
        self.refresh_editor_content()

    def wizard_delete_data(self):
        raw_url = self.wizard_url.get().strip()
        if not raw_url:
            return
        target = raw_url.split("/")[2].replace("www.", "") if "/" in raw_url else raw_url.replace("www.", "")

        if not messagebox.askyesno("确认", f"确定要从所有文件中删除与 {target} 相关的数据吗？"):
            return

        settings = self.safe_read_json(self.json_files["settings"])
        if "domains" in settings and target in settings["domains"]:
            del settings["domains"][target]
        self.safe_write_json(self.json_files["settings"], settings)

        templates = self.safe_read_json(self.json_files["templates"])
        if target in templates:
            del templates[target]
        self.safe_write_json(self.json_files["templates"], templates)

        login = self.safe_read_json(self.json_files["login"])
        login = [item for item in login if item != target]
        self.safe_write_json(self.json_files["login"], login)

        for key in ["branch", "paper", "si"]:
            data = self.safe_read_json(self.json_files[key])
            data = [
                item
                for item in data
                if item.get("domain", item.get("url")) != target and item.get("url") != "www." + target
            ]
            self.safe_write_json(self.json_files[key], data)

        messagebox.showinfo("清理完成", f"已从所有 JSON 中移除 {target}")
        self.refresh_editor_content()

    def load_all_configs(self):
        try:
            runtime_cfg = load_runtime_config()
            path_cfg = runtime_cfg.get("paths", {})
            param_cfg = runtime_cfg.get("params", {})

            for key, entry in self.path_entries.items():
                value = path_cfg.get(key, "")
                entry.delete(0, tk.END)
                entry.insert(0, value)

            self.sel_var.set("True" if bool(param_cfg.get("USE_SELENIUM", False)) else "False")
            self.param_entries["DELAY_PAPER"].delete(0, tk.END)
            self.param_entries["DELAY_PAPER"].insert(0, str(param_cfg.get("DELAY_PAPER", 60)))
            self.param_entries["DELAY_SI"].delete(0, tk.END)
            self.param_entries["DELAY_SI"].insert(0, str(param_cfg.get("DELAY_SI", 5)))
            self.param_entries["TIMEOUT"].delete(0, tk.END)
            self.param_entries["TIMEOUT"].insert(0, str(param_cfg.get("TIMEOUT", 40)))
            self.param_entries["CLEAN_THRESHOLD"].delete(0, tk.END)
            self.param_entries["CLEAN_THRESHOLD"].insert(0, str(param_cfg.get("CLEAN_THRESHOLD", 47)))

            self.query_text.delete("1.0", tk.END)
            self.query_text.insert("1.0", str(param_cfg.get("SEARCH_QUERY", "")))

            csv_path = self.path_entries["CSV_PATH"].get().strip()
            if csv_path:
                self.csv_path_var.set(os.path.abspath(os.path.expanduser(csv_path)))
            self.refresh_editor_content()
        except Exception as exc:
            print(f"读取配置时出错: {exc}")

    def save_all_configs(self):
        try:
            runtime_cfg = load_runtime_config()
            path_cfg = runtime_cfg.setdefault("paths", {})
            param_cfg = runtime_cfg.setdefault("params", {})

            for key, entry in self.path_entries.items():
                value = entry.get().strip()
                if not value:
                    continue
                expanded = os.path.abspath(os.path.expanduser(value))
                path_cfg[key] = expanded

            def _safe_int(raw: str, fallback: int) -> int:
                try:
                    return int(str(raw).strip())
                except Exception:
                    return fallback

            param_cfg["USE_SELENIUM"] = self.sel_var.get().strip().lower() == "true"
            param_cfg["DELAY_PAPER"] = _safe_int(self.param_entries["DELAY_PAPER"].get(), int(param_cfg.get("DELAY_PAPER", 60)))
            param_cfg["DELAY_SI"] = _safe_int(self.param_entries["DELAY_SI"].get(), int(param_cfg.get("DELAY_SI", 5)))
            param_cfg["TIMEOUT"] = _safe_int(self.param_entries["TIMEOUT"].get(), int(param_cfg.get("TIMEOUT", 40)))
            param_cfg["CLEAN_THRESHOLD"] = _safe_int(
                self.param_entries["CLEAN_THRESHOLD"].get(),
                int(param_cfg.get("CLEAN_THRESHOLD", 47)),
            )
            param_cfg["SEARCH_QUERY"] = self.query_text.get("1.0", tk.END).strip().replace("\n", " ")

            save_runtime_config(runtime_cfg)

            if self.path_entries["CSV_PATH"].get().strip():
                self.csv_path_var.set(os.path.abspath(os.path.expanduser(self.path_entries["CSV_PATH"].get().strip())))
            self._refresh_csv_table()
            messagebox.showinfo("成功", "运行时配置已保存")
        except Exception as exc:
            messagebox.showerror("失败", f"保存失败:\n{exc}")

    def execute_script(self, script_key: str):
        if script_key in self.SCRIPTS and not getattr(sys, "frozen", False):
            self._fix_error(self.SCRIPTS[script_key])
        self._spawn_script_process(script_key)

    def _spawn_script_process(self, script_key: str):
        script_name = script_name_for_key(script_key)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            command = resolve_worker_command(script_key)
            process = subprocess.Popen(
                command,
                cwd=DATA_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except Exception as exc:
            self._append_log_line("GUI", f"启动失败: {script_name} | {exc}")
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item_id = self.process_tree.insert("", tk.END, values=(script_name, process.pid, now_str, "Running"))
        self.item_pid_map[item_id] = process.pid
        self.process_registry[process.pid] = {
            "process": process,
            "script": script_name,
            "script_key": script_key,
            "start": now_str,
            "start_ts": datetime.now().timestamp(),
            "status": "Running",
            "item_id": item_id,
            "ended_logged": False,
        }
        self.current_script_name = script_name
        self.latest_script_var.set(f"最近启动脚本: {script_name}")
        self._update_log_filter_target()
        self._set_process_status(process.pid, "Running")
        self.notebook.select(self.monitor_frame)
        self.process_tree.selection_set(item_id)
        self.process_tree.focus(item_id)
        self.process_tree.see(item_id)
        self._append_log_line(f"PROC:{script_name}", f"[START] PID={process.pid}")

        thread = threading.Thread(target=self._read_process_output, args=(process, script_name), daemon=True)
        thread.start()

    def _read_process_output(self, process: subprocess.Popen, script_name: str):
        try:
            if process.stdout is None:
                return
            for line in process.stdout:
                self.log_queue.put((f"PROC:{script_name}", line.rstrip("\n")))
        finally:
            try:
                if process.stdout:
                    process.stdout.close()
            except Exception:
                pass

    def _drain_log_queue(self):
        try:
            while True:
                prefix, text = self.log_queue.get_nowait()
                self._append_log_line(prefix, text)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.root.after(200, self._drain_log_queue)

    def _poll_log_files(self):
        try:
            if not os.path.isdir(LOG_DIR):
                self.root.after(1000, self._poll_log_files)
                return

            for filename in sorted(os.listdir(LOG_DIR)):
                if not filename.endswith(".log"):
                    continue
                path = os.path.join(LOG_DIR, filename)
                if not os.path.isfile(path):
                    continue

                file_size = os.path.getsize(path)
                if path not in self.log_file_offsets:
                    mtime = os.path.getmtime(path)
                    self.log_file_offsets[path] = 0 if mtime >= self.log_start_epoch - 2 else file_size

                offset = self.log_file_offsets[path]
                if file_size < offset:
                    offset = 0

                if file_size > offset:
                    with open(path, "r", encoding="utf-8", errors="ignore") as file:
                        file.seek(offset)
                        content = file.read()
                        self.log_file_offsets[path] = file.tell()
                    for line in content.splitlines():
                        self.log_queue.put((f"FILE:{filename}", line))
        except tk.TclError:
            return
        except Exception as exc:
            self._append_log_line("GUI", f"log目录轮询失败: {exc}")
        self.root.after(1000, self._poll_log_files)

    def _poll_process_status(self):
        try:
            for pid, info in list(self.process_registry.items()):
                process = info["process"]
                code = process.poll()
                if code is None:
                    status = "Running"
                else:
                    status = f"Exited({code})"
                    if not info["ended_logged"]:
                        self.log_queue.put((f'PROC:{info["script"]}', f"[END] PID={pid} Exit={code}"))
                        info["ended_logged"] = True

                if info["status"] != status:
                    self._set_process_status(pid, status)
        except tk.TclError:
            return
        self.root.after(1000, self._poll_process_status)

    def _set_process_status(self, pid: int, status: str):
        info = self.process_registry.get(pid)
        if not info:
            return
        info["status"] = status
        tag = self._status_to_tag(status)
        try:
            self.process_tree.item(info["item_id"], values=(info["script"], pid, info["start"], status), tags=(tag,))
        except Exception:
            return
        self._resort_process_tree()
        self._update_running_summary()

    def _status_to_tag(self, status: str) -> str:
        if status == "Running":
            return "running"
        if status == "Stopping":
            return "stopping"
        return "exited"

    def _resort_process_tree(self):
        sortable = []
        for pid, info in self.process_registry.items():
            status = info.get("status", "")
            if status == "Running":
                rank = 0
            elif status == "Stopping":
                rank = 1
            else:
                rank = 2
            sortable.append((rank, -float(info.get("start_ts", 0.0)), pid, info.get("item_id")))

        for index, (_, _, _, item_id) in enumerate(sorted(sortable)):
            try:
                self.process_tree.move(item_id, "", index)
            except Exception:
                continue

    def _update_running_summary(self):
        running_count = 0
        for info in self.process_registry.values():
            if info.get("status") in ("Running", "Stopping"):
                running_count += 1
        self.running_count_var.set(f"运行中数量: {running_count}")
        self.status_updated_var.set(f"状态更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _stop_selected_process(self):
        selected = self.process_tree.selection()
        if not selected:
            self._append_log_line("GUI", "[STOP] 未选择脚本，无法停止")
            return

        item_id = selected[0]
        pid = self.item_pid_map.get(item_id)
        if pid is None:
            self._append_log_line("GUI", "[STOP] 选中项无有效PID")
            return
        self._stop_process_tree(pid)

    def _stop_all_processes(self):
        active_pids = []
        for pid, info in self.process_registry.items():
            if info.get("status") in ("Running", "Stopping"):
                active_pids.append(pid)
        if not active_pids:
            self._append_log_line("GUI", "[STOP] 当前没有可停止的运行中脚本")
            return
        for pid in active_pids:
            self._stop_process_tree(pid)

    def _stop_process_tree(self, pid: int):
        info = self.process_registry.get(pid)
        if not info:
            self._append_log_line("GUI", f"[STOP] 未找到PID={pid}对应进程")
            return

        process = info["process"]
        if process.poll() is not None:
            self._append_log_line("GUI", f"[STOP] 脚本已结束: {info['script']} PID={pid}")
            return

        if info.get("status") == "Stopping":
            self._append_log_line("GUI", f"[STOP] 正在停止中: {info['script']} PID={pid}")
            return

        self._set_process_status(pid, "Stopping")
        self._append_log_line("GUI", f"[STOP] 请求停止: {info['script']} PID={pid}")

        stop_thread = threading.Thread(target=self._terminate_then_kill, args=(pid,), daemon=True)
        stop_thread.start()

    def _terminate_then_kill(self, pid: int):
        info = self.process_registry.get(pid)
        if not info:
            return
        process = info["process"]
        script = info["script"]

        try:
            root_proc = psutil.Process(pid)
            descendants = root_proc.children(recursive=True)

            for child in descendants:
                try:
                    child.terminate()
                except Exception:
                    pass
            try:
                root_proc.terminate()
            except Exception:
                pass

            wait_list = descendants + [root_proc]
            _, alive = psutil.wait_procs(wait_list, timeout=3)
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass

            try:
                process.wait(timeout=1)
            except Exception:
                pass

            self.log_queue.put(("GUI", f"[STOP] 已停止: {script} PID={pid}"))
        except Exception as exc:
            try:
                process.terminate()
                process.wait(timeout=3)
                self.log_queue.put(("GUI", f"[STOP] 已停止: {script} PID={pid}"))
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    self.log_queue.put(("GUI", f"[STOP] 强制结束: {script} PID={pid}"))
                except Exception as kill_exc:
                    self.log_queue.put(("GUI", f"[STOP] 停止失败: {script} PID={pid} | {kill_exc}"))
            except Exception:
                self.log_queue.put(("GUI", f"[STOP] 停止失败: {script} PID={pid} | {exc}"))

    def _append_log_line(self, prefix: str, text: str):
        if not self._should_show_line(prefix):
            return

        line = f"[{prefix}] {text}\n"
        self.log_text.insert(tk.END, line)
        self.log_line_count += 1

        if self.log_line_count > MAX_LOG_LINES:
            remove_count = self.log_line_count - MAX_LOG_LINES
            self.log_text.delete("1.0", f"{remove_count + 1}.0")
            self.log_line_count = MAX_LOG_LINES

        if not self.log_paused:
            self.log_text.see(tk.END)

    def _should_show_line(self, prefix: str) -> bool:
        if not self.current_script_only.get():
            return True
        if not self.current_script_name:
            return True

        current_name = self.current_script_name
        current_base = os.path.splitext(current_name)[0]
        if prefix.startswith("PROC:"):
            return prefix == f"PROC:{current_name}"
        if prefix.startswith("FILE:"):
            logfile = prefix.split(":", 1)[1]
            return logfile.startswith(current_base + "_")
        return True

    def _toggle_log_pause(self):
        self.log_paused = not self.log_paused
        self.pause_button_text.set("继续滚动" if self.log_paused else "暂停滚动")

    def _clear_log_text(self):
        self.log_text.delete("1.0", tk.END)
        self.log_line_count = 0

    def _on_toggle_current_script_filter(self):
        self._update_log_filter_target()
        self._append_log_line("GUI", f"日志过滤: {'仅当前脚本' if self.current_script_only.get() else '全部'}")

    def _update_log_filter_target(self):
        if self.current_script_only.get() and self.current_script_name:
            self.log_filter_target_var.set(f"当前脚本: {self.current_script_name}")
        else:
            self.log_filter_target_var.set("当前脚本: 全部脚本")

    def _on_process_tree_select(self, _event=None):
        selected = self.process_tree.selection()
        if not selected:
            return
        pid = self.item_pid_map.get(selected[0])
        if pid is None:
            return
        info = self.process_registry.get(pid)
        if not info:
            return
        self.current_script_name = info.get("script", "")
        self._update_log_filter_target()

    def _refresh_csv_table(self):
        path = self.csv_path_var.get().strip() or CSV_DEFAULT_PATH
        path = os.path.abspath(path)
        self.csv_path_var.set(path)
        self.csv_error_var.set("")

        self.csv_tree.delete(*self.csv_tree.get_children())
        self.csv_tree["columns"] = []
        self.csv_columns = []
        self.csv_data_rows = []

        if not os.path.exists(path):
            self.csv_error_var.set("CSV文件不存在")
            self.csv_row_count_var.set("总行数: 0")
            self.csv_refresh_time_var.set(f"最后刷新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as file:
                reader = csv.reader(file)
                rows = list(reader)

            if not rows:
                self.csv_error_var.set("CSV为空")
                self.csv_row_count_var.set("总行数: 0")
                self.csv_refresh_time_var.set(f"最后刷新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                return

            self.csv_columns = rows[0]
            self.csv_data_rows = [self._normalize_csv_row(row, len(self.csv_columns)) for row in rows[1:]]
            self.csv_sort_orders = {}

            self.csv_tree["columns"] = self.csv_columns
            for col in self.csv_columns:
                self.csv_tree.heading(col, text=col, command=lambda c=col: self._sort_csv_by_column(c))
                self.csv_tree.column(col, width=140, anchor=tk.W)

            self._render_csv_rows()
            self.csv_row_count_var.set(f"总行数: {len(self.csv_data_rows)}")
            self.csv_refresh_time_var.set(f"最后刷新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as exc:
            self.csv_error_var.set(f"读取失败: {exc}")
            self.csv_row_count_var.set("总行数: 0")
            self.csv_refresh_time_var.set(f"最后刷新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def _normalize_csv_row(self, row, col_count):
        if len(row) < col_count:
            return row + [""] * (col_count - len(row))
        return row[:col_count]

    def _render_csv_rows(self):
        self.csv_tree.delete(*self.csv_tree.get_children())
        for row in self.csv_data_rows:
            self.csv_tree.insert("", tk.END, values=row)

    def _sort_csv_by_column(self, col_name: str):
        if not self.csv_columns or col_name not in self.csv_columns:
            return
        index = self.csv_columns.index(col_name)
        ascending = self.csv_sort_orders.get(col_name, True)

        def sort_key(row):
            value = row[index].strip() if index < len(row) and row[index] is not None else ""
            return (value == "", value.lower())

        self.csv_data_rows = sorted(self.csv_data_rows, key=sort_key, reverse=not ascending)
        self.csv_sort_orders[col_name] = not ascending
        self._render_csv_rows()

    def _refresh_all_folders(self):
        for folder_name in self.folder_dirs:
            self._refresh_folder_view(folder_name)

    def _refresh_folder_view(self, folder_name: str):
        tree = self.folder_trees.get(folder_name)
        if tree is None:
            return

        folder_path = self.folder_dirs[folder_name]
        tree.delete(*tree.get_children())
        self.folder_item_paths[folder_name] = {}

        if not os.path.exists(folder_path):
            self.folder_status_vars[folder_name].set("目录不存在")
            return

        try:
            entries = sorted(os.scandir(folder_path), key=lambda item: (not item.is_dir(), item.name.lower()))
            for entry in entries:
                is_dir = entry.is_dir()
                item_type = "Dir" if is_dir else "File"
                size_text = "" if is_dir else self._format_size(entry.stat().st_size)
                modified = datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                item_id = tree.insert("", tk.END, values=(entry.name, item_type, size_text, modified))
                self.folder_item_paths[folder_name][item_id] = entry.path
            self.folder_status_vars[folder_name].set(
                f"{len(entries)} 项 | 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as exc:
            self.folder_status_vars[folder_name].set(f"读取失败: {exc}")

    def _auto_refresh_folders(self):
        try:
            if self.folder_auto_refresh.get():
                self._refresh_all_folders()
        except tk.TclError:
            return
        self.root.after(3000, self._auto_refresh_folders)

    def _on_folder_item_double_click(self, event, folder_name: str):
        tree = self.folder_trees.get(folder_name)
        if tree is None:
            return

        selection = tree.selection()
        if not selection:
            return

        item_id = selection[0]
        path = self.folder_item_paths.get(folder_name, {}).get(item_id)
        if path:
            self._open_path_in_system(path)

    def _open_path_in_system(self, path: str):
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["cmd", "/c", "start", "", path], shell=False)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            self._append_log_line("GUI", f"打开路径失败: {path} | {exc}")

    def _format_size(self, size_bytes: int) -> str:
        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{int(size_bytes)} B"

    def _fix_error(self, filename: str):
        if not os.path.exists(filename):
            return
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
        fixed = re.sub(r"\s*\+\]", "", content)
        if content != fixed:
            with open(filename, "w", encoding="utf-8") as file:
                file.write(fixed)

    def refresh_editor_content(self):
        for filepath, text_widget in self.editor_texts.items():
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", json.dumps(self.safe_read_json(filepath), indent=4, ensure_ascii=False))

    def save_json_from_editor(self, filepath: str):
        try:
            content = self.editor_texts[filepath].get("1.0", tk.END).strip()
            parsed = json.loads(content)
            self.safe_write_json(filepath, parsed)
            messagebox.showinfo("成功", f"{os.path.basename(filepath)} 已保存")
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def safe_read_json(self, filepath: str):
        if not os.path.exists(filepath):
            return {"domains": {}} if "Settings" in filepath else []
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)

    def safe_write_json(self, filepath: str, data):
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    def _fill(self, entry: ttk.Entry, match):
        if match:
            entry.delete(0, tk.END)
            entry.insert(0, match.group(1))

    def browse_path(self, key: str):
        choose_file = "CSV" in key or "IN" in key or "OUT" in key
        path = filedialog.askopenfilename() if choose_file else filedialog.askdirectory()
        if path:
            abs_path = os.path.abspath(path)
            self.path_entries[key].delete(0, tk.END)
            self.path_entries[key].insert(0, abs_path)

    def run_full_automation(self):
        if messagebox.askyesno("确认", "启动全自动下载流程？"):
            self.execute_script("getdoi")


if __name__ == "__main__":
    setup_script_logging(__file__)
    root = tk.Tk()
    PaperAutomationConsole(root)
    root.mainloop()
