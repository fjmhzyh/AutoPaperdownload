import csv
import os


def matches_file_path(csv_cell_value: str, pdf_filename: str, pdf_full_path: str, base_folder: str) -> bool:
    if not isinstance(csv_cell_value, str):
        return False
    if pdf_filename in csv_cell_value:
        return True
    if pdf_full_path in csv_cell_value:
        return True

    relative_path = os.path.relpath(pdf_full_path, base_folder)
    if relative_path in csv_cell_value:
        return True

    base_name = os.path.splitext(pdf_filename)[0]
    if base_name in csv_cell_value:
        return True

    if os.path.basename(csv_cell_value) == pdf_filename:
        return True

    return False


def advanced_path_matching_process(folder_path: str, csv_file_path: str, output_csv_path: str, size_threshold_kb: int = 47):
    size_threshold = int(size_threshold_kb) * 1024

    try:
        with open(csv_file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
            csv_reader = csv.reader(csvfile)
            headers = next(csv_reader)
            csv_data = list(csv_reader)
    except Exception as exc:
        print(f"读取CSV文件时出错: {exc}")
        return

    if "DownloadStatus" not in headers:
        print("CSV缺少DownloadStatus列，无法处理")
        return

    status_col_index = headers.index("DownloadStatus")
    path_columns = []
    path_keywords = ["Filename", "File", "Path", "Location"]
    for idx, header in enumerate(headers):
        for keyword in path_keywords:
            if keyword.lower() in header.lower():
                path_columns.append(idx)
                break

    if not path_columns:
        path_columns = list(range(len(headers)))

    deleted_count = 0
    updated_count = 0

    if not os.path.isdir(folder_path):
        print(f"目标目录不存在: {folder_path}")
        return

    for filename in os.listdir(folder_path):
        if not filename.lower().endswith(".pdf"):
            continue

        file_path = os.path.join(folder_path, filename)
        try:
            file_size = os.path.getsize(file_path)
        except Exception:
            continue

        if file_size >= size_threshold:
            continue

        try:
            os.remove(file_path)
            deleted_count += 1
        except Exception as exc:
            print(f"删除文件失败: {file_path} | {exc}")
            continue

        for row in csv_data:
            if len(row) <= max(path_columns):
                continue
            matched = False
            for col_index in path_columns:
                cell_value = row[col_index]
                if not cell_value:
                    continue
                if matches_file_path(cell_value, filename, file_path, folder_path):
                    matched = True
                    break
            if matched and row[status_col_index] != "Failed":
                row[status_col_index] = "Failed"
                updated_count += 1
                break

    try:
        with open(output_csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)
            writer.writerows(csv_data)
    except Exception as exc:
        print(f"保存结果失败: {exc}")
        return

    print(f"处理完成: 删除PDF={deleted_count}, 更新CSV={updated_count}, 输出={output_csv_path}")
