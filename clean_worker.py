from cleaner import advanced_path_matching_process
from log_utils import setup_script_logging
from runtime_config import load_runtime_config
from runtime_paths import data_path, ensure_runtime_layout


def main_entry():
    ensure_runtime_layout()
    cfg = load_runtime_config()
    paths = cfg.get("paths", {})
    params = cfg.get("params", {})

    folder_path = paths.get("CLEAN_FOLDER", data_path("Paper"))
    csv_file_path = paths.get("CLEAN_CSV_IN", data_path("PaperDoi_updated.csv"))
    output_csv_path = paths.get("CLEAN_CSV_OUT", data_path("PaperDoi_updated_clean.csv"))
    threshold_kb = int(params.get("CLEAN_THRESHOLD", 47))

    setup_script_logging(__file__, script_name="clean_worker")
    advanced_path_matching_process(folder_path, csv_file_path, output_csv_path, size_threshold_kb=threshold_kb)


if __name__ == "__main__":
    main_entry()
