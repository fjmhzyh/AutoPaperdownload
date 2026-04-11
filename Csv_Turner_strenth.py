import csv
import os

# 项目根目录（自动获取）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

# 使用示例
if __name__ == "__main__":
    # 在这里指定输入和输出文件路径
    input_file = os.path.join(_BASE_DIR, "PaperDoi_updated.csv")  # 替换为您的输入文件路径
    output_file = os.path.join(_BASE_DIR, "PaperDoi_failed.csv")  # 替换为您的输出文件路径
    
    # 调用筛选函数
    result = filter_failed_dois(input_file, output_file)
    
    if result:
        print("\n处理完成！")
        # 显示处理结果预览
        print("\n处理结果预览:")
        for i, row in enumerate(result[:6]):  # 显示前6行
            if i == 0:
                print(f"标题行: {row}")
            else:
                print(f"第{i}行: {row}")
        if len(result) > 6:
            print(f"... (还有{len(result)-6}行)")
    else:
        print("\n处理失败！")