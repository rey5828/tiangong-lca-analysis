import pandas as pd

# 读取Excel文件
file_path = r"/mnt/d/json/output.xlsx"
df = pd.read_excel(file_path)

# 删除重复行，只保留第一行
df_unique = df.drop_duplicates()

# 保存处理后的Excel文件
output_path = r"/mnt/d/json/unique_output.xlsx"
df_unique.to_excel(output_path, index=False)

print(f"处理后的文件已保存到 {output_path}")
