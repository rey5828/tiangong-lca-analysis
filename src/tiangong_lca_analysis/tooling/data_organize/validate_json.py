import json
import os

TARGET_DIR = "data/process_compressed"
REPORT_FILE = "json_validation_report.txt"

def validate_json_files():
    errors = []

    print(f"Checking JSON files inside: {TARGET_DIR}\n")

    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.lower().endswith(".json"):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        json.load(f)
                    print(f"[OK]     {full_path}")
                except Exception as e:
                    print(f"[ERROR]  {full_path}  -->  {e}")
                    errors.append((full_path, str(e)))

    # Write report
    with open(REPORT_FILE, "w", encoding="utf-8") as rf:
        if not errors:
            rf.write("All JSON files are valid.\n")
        else:
            rf.write("Invalid JSON Files:\n\n")
            for path, err in errors:
                rf.write(f"{path}\n{err}\n\n")

    print("\nValidation completed.")
    print(f"Report written to: {REPORT_FILE}")


if __name__ == "__main__":
    validate_json_files()
