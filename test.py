import csv
import json
import requests
import time

# ================= 配置区域 =================
CSV_FILE = "doi.csv"           # 输入的 CSV 文件路径
OUTPUT_JS = "address.js"         # 输出的 JS 文件路径
DOI_COLUMN_INDEX = 0             # DOI 所在的列索引（0 表示第一列）
REQUEST_TIMEOUT = 10             # 单次请求超时时间（秒）
DELAY_BETWEEN_REQUESTS = 0.5     # 请求间隔（秒），避免请求过快
USE_CONCURRENT = False           # 是否使用多线程并发（需安装 futures，仅适用于 Python 3）
MAX_WORKERS = 5                  # 并发线程数（若开启并发）
# ===========================================

def resolve_doi(doi):
    """通过 doi.org 解析最终 URL"""
    if not doi or not doi.strip():
        return None
    
    doi = doi.strip()
    base_url = "https://doi.org/" + doi
    
    try:
        # 使用 HEAD 请求减少流量，但有些服务器可能不支持，可改用 GET
        response = requests.head(
            base_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        # 如果 HEAD 被拒绝（405 等），尝试 GET
        if response.status_code == 405:
            response = requests.get(
                base_url,
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT,
                stream=True  # 只获取头部，不下载内容
            )
            response.close()
        return response.url
    except Exception as e:
        print(f"[错误] DOI {doi} 解析失败: {e}")
        return None

def process_csv_serial():
    """串行处理 CSV 文件"""
    results = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        # 尝试跳过标题行（如果第一行第一列是 "DOI" 字样）
        first_row = next(reader, None)
        if first_row and first_row[DOI_COLUMN_INDEX].strip().lower() == "doi":
            print("检测到标题行，已跳过")
        else:
            # 不是标题行，回退处理
            f.seek(0)
            reader = csv.reader(f)
        
        for row in reader:
            if not row:
                continue
            doi = row[DOI_COLUMN_INDEX].strip()
            if not doi:
                continue
            
            print(f"正在解析: {doi}")
            final_url = resolve_doi(doi)
            if final_url:
                results.append({"doi": doi, "url": final_url})
                print(f"  -> {final_url}")
            else:
                results.append({"doi": doi, "url": ""})
                print(f"  -> 解析失败")
            
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    return results

def process_csv_concurrent():
    """并发处理（需安装 futures，Python 3 标准库自带）"""
    import concurrent.futures
    
    dois = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        first_row = next(reader, None)
        if first_row and first_row[DOI_COLUMN_INDEX].strip().lower() == "doi":
            print("检测到标题行，已跳过")
        else:
            f.seek(0)
            reader = csv.reader(f)
        
        for row in reader:
            if row:
                doi = row[DOI_COLUMN_INDEX].strip()
                if doi:
                    dois.append(doi)
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_doi = {executor.submit(resolve_doi, doi): doi for doi in dois}
        for future in concurrent.futures.as_completed(future_to_doi):
            doi = future_to_doi[future]
            try:
                final_url = future.result()
                if final_url:
                    results.append({"doi": doi, "url": final_url})
                    print(f"✅ {doi} -> {final_url}")
                else:
                    results.append({"doi": doi, "url": ""})
                    print(f"❌ {doi} 解析失败")
            except Exception as e:
                results.append({"doi": doi, "url": ""})
                print(f"❌ {doi} 异常: {e}")
    
    # 按原始顺序排序（可选）
    results.sort(key=lambda x: dois.index(x["doi"]))
    return results

def save_to_js(data, output_path):
    """将数据保存为 JavaScript 文件"""
    # 转换为 JSON 字符串，并美化格式
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    js_content = f"// Auto-generated DOI address mapping\nconst addressData = {json_str};\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)
    print(f"\n✅ 结果已保存至: {output_path}")

def main():
    print(f"📂 读取 CSV 文件: {CSV_FILE}")
    if USE_CONCURRENT:
        print("⚡ 使用并发模式")
        results = process_csv_concurrent()
    else:
        print("🐢 使用串行模式")
        results = process_csv_serial()
    
    print(f"\n📊 共处理 {len(results)} 条 DOI")
    save_to_js(results, OUTPUT_JS)

if __name__ == "__main__":
    main()