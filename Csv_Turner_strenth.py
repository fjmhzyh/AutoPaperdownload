import csv
import os
from log_utils import setup_script_logging
from runtime_config import load_runtime_config
from runtime_paths import data_path, ensure_runtime_layout

ensure_runtime_layout()

def filter_failed_dois(input_file, output_file):
    """
    从CSV文件中筛选DownloadStatus为Failed的行，保留所有标题但只保留DOI列的数据
    使用标准库的csv.reader方式读取CSV文件
    """
    try:
        # 读取输入文件
        with open(input_file, 'r', newline='', encoding='utf-8-sig') as infile:
            reader = csv.reader(infile)
            rows = list(reader)
            
            if not rows:
                print("错误：CSV文件为空")
                return
                
            # 提取标题行
            header = rows[0]
            
            # 检查必要的列是否存在
            if 'DOI' not in header or 'DownloadStatus' not in header:
                print("错误：CSV文件中缺少必要的列（DOI或DownloadStatus）")
                return
                
            # 找到DOI和DownloadStatus列的索引
            doi_index = header.index('DOI')
            status_index = header.index('DownloadStatus')
            
            # 准备结果数据 - 保留所有标题
            result_rows = [header]  # 保留完整的标题行
            
            # 处理数据行
            failed_count = 0
            for i, row in enumerate(rows[1:], 1):  # 跳过标题行
                try:
                    # 确保有足够的列
                    if len(row) > max(doi_index, status_index):
                        # 检查DownloadStatus是否为Failed
                        if row[status_index].strip() == 'Failed':
                            # 创建新行，所有列都为空，只保留DOI列的值
                            new_row = [''] * len(header)  # 创建与标题行长度相同的空行
                            new_row[doi_index] = row[doi_index]  # 只保留DOI列的值
                            result_rows.append(new_row)
                            failed_count += 1
                except Exception as e:
                    print(f"警告：处理第{i}行时出错: {e}")
                    continue
            
            # 写入新文件
            with open(output_file, 'w', newline='', encoding='utf-8-sig') as outfile:
                writer = csv.writer(outfile)
                writer.writerows(result_rows)
            
            print(f"筛选完成！共找到 {failed_count} 条Failed记录")
            print(f"输入文件: {input_file}")
            print(f"输出文件: {output_file}")
            print(f"新文件包含完整的标题行，但数据行只保留DOI列的值")
            
            return result_rows
            
    except FileNotFoundError:
        print(f"错误：找不到文件 {input_file}")
    except Exception as e:
        print(f"处理过程中出现错误: {e}")

def main_entry():
    cfg = load_runtime_config()
    paths = cfg.get("paths", {})
    input_file = paths.get("TURNER_IN", data_path("PaperDoi_updated.csv"))
    output_file = paths.get("TURNER_OUT", data_path("PaperDoi_failed.csv"))

    setup_script_logging(__file__, script_name="Csv_Turner_strenth")
    result = filter_failed_dois(input_file, output_file)
    if result:
        print("\n处理完成！")
    else:
        print("\n处理失败！")


if __name__ == "__main__":
    main_entry()
