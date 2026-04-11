import csv
import os
import re
import logging

# 项目根目录（自动获取）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==============================================================================
#  【配置参数】 - 由 config_manager.py 自动修改
# ==============================================================================
INPUT_FILE = os.path.join(_BASE_DIR, "input.txt")
CSV_FILE = os.path.join(_BASE_DIR, "PaperDoi.csv")
LOG_FILE = os.path.join(_BASE_DIR, "doi_extractor.log")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_dois(text):
    # 匹配 10.xxxx/xxxx 格式
    pattern = r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b'
    matches = re.findall(pattern, text, re.IGNORECASE)
    return sorted(list(set(m.rstrip('.,;)') for m in matches)))

def process():
    if not os.path.exists(INPUT_FILE):
        print(f"错误：找不到文件 {INPUT_FILE}")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8-sig', errors='ignore') as f:
        dois = extract_dois(f.read())

    # 9列标准标题
    header = ["DOI", "DownloadStatus", "Filename", "URL", "DownloadURL", 
              "SIDownloadStatus", "SIFilename", "HTMLFilename", "HTMLFile"]

    existing = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row: existing.add(row[0])
    else:
        os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerow(header)

    new_count = 0
    with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        for doi in dois:
            if doi not in existing:
                writer.writerow([doi] + [""] * 8)
                new_count += 1
    
    print(f"提取完成！找到: {len(dois)}，新增: {new_count}")

if __name__ == "__main__":
    process()