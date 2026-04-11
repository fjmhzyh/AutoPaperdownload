import csv
import os
import sys

def delete_success_files(csv_path):
    """
    读取CSV文件并删除成功下载的文件
    所有文件都保存在LAPaper文件夹内
    :param csv_path: CSV文件路径
    """
    deleted_files = []
    error_files = []
    csv_dir = os.path.dirname(os.path.abspath(csv_path))  # 获取CSV文件所在目录
    
    # LAPaper文件夹路径（在CSV文件所在目录下）
    lapaper_dir = os.path.join(csv_dir, "LAPaper")
    
    # 确保LAPaper文件夹存在
    if not os.path.exists(lapaper_dir):
        os.makedirs(lapaper_dir)
        print(f"已创建LAPaper文件夹: {lapaper_dir}")

    try:
        with open(csv_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            for row_num, row in enumerate(reader, start=2):
                filename = row.get('Filename', '').strip()
                status = row.get('DownloadStatus', '').strip().lower()
                
                if not filename:
                    error_files.append((f"第{row_num}行", "文件名为空"))
                    continue
                
                # 所有文件都在LAPaper文件夹内
                # 获取文件名（不含路径）
                base_name = os.path.basename(filename)
                # 构建在LAPaper文件夹中的完整路径
                file_in_lapaper = os.path.join(lapaper_dir, base_name)
                
                # 处理非完整路径的情况
                original_filename = filename  # 保存原始文件名用于错误报告
                
                # 尝试在多个位置查找文件
                possible_paths = [
                    file_in_lapaper,  # 首选位置：LAPaper文件夹内
                    os.path.join(csv_dir, filename),  # CSV文件所在目录
                    os.path.join(os.getcwd(), filename),  # 当前工作目录
                    os.path.join(os.path.expanduser("~"), "Downloads", filename)  # 用户下载目录
                ]
                
                # 查找实际存在的文件
                found = False
                for path in possible_paths:
                    path = os.path.normpath(path)  # 规范化路径
                    if os.path.exists(path):
                        filename = path
                        found = True
                        break
                
                if not found:
                    # 如果都不存在，使用LAPaper文件夹中的路径用于错误报告
                    error_files.append((f"{base_name} (在LAPaper文件夹中未找到)", "文件不存在"))
                    continue

                if status == 'success':
                    try:
                        # 使用 os.remove() 删除文件
                        os.remove(filename)
                        deleted_files.append(filename)
                        print(f"已删除: {filename}")
                    except PermissionError:
                        error_files.append((filename, "删除失败: 权限不足"))
                    except IsADirectoryError:
                        error_files.append((filename, "删除失败: 这是一个目录"))
                    except FileNotFoundError:
                        error_files.append((filename, "删除失败: 文件不存在"))
                    except Exception as e:
                        error_files.append((filename, f"删除失败: {str(e)}"))
    except Exception as e:
        print(f"处理CSV文件时出错: {str(e)}")
        return

    # 输出结果
    print(f"\n成功删除 {len(deleted_files)} 个文件")
    if error_files:
        print("\n错误详情:")
        for file, error in error_files:
            print(f"- {file}: {error}")

if __name__ == "__main__":
    # =====================================================
    # 在这里直接设置CSV文件路径（修改为您实际的CSV文件路径）
    # =====================================================
    csv_path = r"D:\LAPaperdownload\LAsPaperDoi1.csv"
    
    # 检查路径是否存在
    if not os.path.exists(csv_path):
        print(f"错误：CSV文件不存在 - {csv_path}")
        input("按回车键退出...")
        sys.exit(1)
    
    # 确认操作
    print(f"即将处理CSV文件: {csv_path}")
    print("此操作将删除CSV文件中标记为'success'的文件")
    print("所有文件都保存在LAPaper文件夹内")
    print("==============================================")
    
    # 执行删除操作
    print("\n开始处理...")
    delete_success_files(csv_path)
    
    print("\n处理完成")
    input("按回车键退出...")  # 等待用户确认退出