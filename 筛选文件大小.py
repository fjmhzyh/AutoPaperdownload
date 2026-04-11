import os

# 项目根目录（自动获取）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
import csv
import re

def advanced_path_matching_process(folder_path, csv_file_path, output_csv_path):
    """
    增强版路径匹配处理
    """
    SIZE_THRESHOLD = 47 * 1024  # 47KB
    
    # 读取CSV文件
    csv_data = []
    headers = []
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig', newline='') as csvfile:
            csv_reader = csv.reader(csvfile)
            headers = next(csv_reader)
            csv_data = list(csv_reader)
        print(f"CSV文件读取成功，找到 {len(csv_data)} 条记录")
    except Exception as e:
        print(f"读取CSV文件时出错: {e}")
        return
    
    # 查找列索引
    status_col_index = headers.index('DownloadStatus')
    path_columns = []
    
    # 查找所有可能包含文件路径的列
    path_keywords = ['Filename', 'File', 'Path', 'Location']
    for i, header in enumerate(headers):
        for keyword in path_keywords:
            if keyword.lower() in header.lower():
                path_columns.append(i)
                print(f"找到路径相关列: {header} (索引: {i})")
                break
    
    if not path_columns:
        print("未找到路径相关列，使用所有列进行匹配")
        path_columns = list(range(len(headers)))
    
    # 处理PDF文件
    deleted_count = 0
    updated_count = 0
    
    print(f"开始处理文件夹: {folder_path}")
    print(f"大小阈值: {SIZE_THRESHOLD/(1024 * 1024):.1f} MB")
    
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf'):
            file_path = os.path.join(folder_path, filename)
            
            try:
                file_size = os.path.getsize(file_path)
                
                if file_size < SIZE_THRESHOLD:
                    print(f"\n删除小文件: {filename} ({file_size/(1024 * 1024):.2f} MB)")
                    os.remove(file_path)
                    deleted_count += 1
                    
                    # 在CSV中查找匹配项
                    matches_found = False
                    
                    for i, row in enumerate(csv_data):
                        if len(row) <= max(path_columns):
                            continue
                            
                        # 检查所有路径列
                        for col_index in path_columns:
                            cell_value = row[col_index]
                            if not cell_value:
                                continue
                                
                            # 多种匹配策略
                            if matches_file_path(cell_value, filename, file_path, folder_path):
                                if row[status_col_index] != 'Failed':
                                    row[status_col_index] = 'Failed'
                                    updated_count += 1
                                    matches_found = True
                                    print(f"  匹配成功! 列 '{headers[col_index]}': {cell_value}")
                                    print(f"  更新状态为: Failed")
                                    break
                        
                        if matches_found:
                            break
                    
                    if not matches_found:
                        print(f"  未找到匹配的CSV记录")
                        
                else:
                    print(f"保留文件: {filename} ({file_size/(1024 * 1024):.2f} MB)")
                    
            except Exception as e:
                print(f"处理文件 {filename} 时出错: {e}")
    
    # 保存结果
    try:
        with open(output_csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            writer.writerows(csv_data)
        
        print(f"\n=== 处理完成 ===")
        print(f"删除PDF文件: {deleted_count} 个")
        print(f"更新CSV记录: {updated_count} 条")
        print(f"结果保存到: {output_csv_path}")
        
    except Exception as e:
        print(f"保存结果失败: {e}")

def matches_file_path(csv_cell_value, pdf_filename, pdf_full_path, base_folder):
    """
    检查CSV单元格值是否与PDF文件路径匹配
    """
    # 策略1: 直接文件名匹配
    if pdf_filename in csv_cell_value:
        return True
    
    # 策略2: 完整路径匹配
    if pdf_full_path in csv_cell_value:
        return True
    
    # 策略3: 相对路径匹配
    relative_path = os.path.relpath(pdf_full_path, base_folder)
    if relative_path in csv_cell_value:
        return True
    
    # 策略4: 文件名基础名匹配（不含扩展名）
    base_name = os.path.splitext(pdf_filename)[0]
    if base_name in csv_cell_value:
        return True
    
    # 策略5: 路径中包含PDF文件名
    if os.path.basename(csv_cell_value) == pdf_filename:
        return True
    
    return False

# 使用增强版
if __name__ == "__main__":
    advanced_path_matching_process(
        os.path.join(_BASE_DIR, "Paper"), os.path.join(_BASE_DIR, "PaperDoi_updated.csv"), os.path.join(_BASE_DIR, "PaperDoi_updated_clean.csv")
    )