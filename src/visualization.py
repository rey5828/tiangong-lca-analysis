import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import glob
from matplotlib.colors import LogNorm
import warnings
warnings.filterwarnings('ignore')

def log_transform_visualize(input_dir='output/results', output_dir='output/log_transformed_results'):
    """
    对指定目录中的CSV文件进行对数变换并重新可视化
    
    Args:
        input_dir: 包含原始CSV文件的目录
        output_dir: 保存对数变换后可视化结果的目录
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"正在处理目录: {input_dir} 中的CSV文件...")
    
    # 查找所有联合概率和条件概率的CSV文件
    joint_prob_files = glob.glob(os.path.join(input_dir, 'joint_prob_*.csv'))
    cond_prob_files = glob.glob(os.path.join(input_dir, 'cond_prob_*.csv'))
    
    # 处理联合概率分布文件
    for file_path in joint_prob_files:
        try:
            file_name = os.path.basename(file_path)
            category = file_name.split('_')[-1].replace('.csv', '')
            print(f"处理文件: {file_name}")
            
            # 读取CSV文件
            df = pd.read_csv(file_path)
            
            # 确定文件类型
            if 'gwp_hh' in file_name:
                x_col = 'gwp'
                y_col = 'human_health'
                title_suffix = 'GWP and Human Health'
                output_suffix = 'gwp_hh'
            elif 'gwp_eq' in file_name:
                x_col = 'gwp'
                y_col = 'eco_quality'
                title_suffix = 'GWP and Eco Quality'
                output_suffix = 'gwp_eq'
            else:
                continue
                
            # 对数变换 (log1p)
            df[f'log_{x_col}'] = np.log1p(df[x_col].abs())
            df[f'log_{y_col}'] = np.log1p(df[y_col].abs())
            
            # 创建对数变换后的2D直方图
            plt.figure(figsize=(12, 10))
            
            # 使用pivot_table重构数据以便于绘图
            pivot_df = df.pivot_table(
                index=f'log_{x_col}',
                columns=f'log_{y_col}',
                values='joint_probability'
            ).fillna(0)
            
            # 绘制热图
            sns.heatmap(
                pivot_df,
                cmap='viridis',
                cbar_kws={'label': 'Joint Probability Density'},
                xticklabels=20,  # 控制横轴刻度数量
                yticklabels=20   # 控制纵轴刻度数量
            )
            
            plt.xlabel(f'log(1+{x_col.upper()})')
            plt.ylabel(f'log(1+{y_col.upper()})')
            plt.title(f'Category: {category} - {title_suffix} Joint Probability Distribution (Log-transformed)')
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, f'log_joint_prob_{output_suffix}_{category}.png'))
            plt.close()
            
            print(f"成功生成对数变换后的联合概率分布图: {category} - {title_suffix}")
        except Exception as e:
            print(f"处理文件 {file_path} 时发生错误: {str(e)}")
    
    # 处理条件概率分布文件
    for file_path in cond_prob_files:
        try:
            file_name = os.path.basename(file_path)
            category = file_name.split('_')[-1].replace('.csv', '')
            print(f"处理文件: {file_name}")
            
            # 读取CSV文件
            df = pd.read_csv(file_path)
            
            # 确定文件类型
            if 'hh_given_gwp' in file_name:
                x_col = 'gwp'
                y_col = 'human_health'
                title_suffix = 'Human Health Given GWP Conditional Probability'
                output_suffix = 'hh_given_gwp'
                prob_label = 'Conditional Probability Density P(Human Health | GWP)'
            elif 'eq_given_gwp' in file_name:
                x_col = 'gwp'
                y_col = 'eco_quality'
                title_suffix = 'Eco Quality Given GWP Conditional Probability'
                output_suffix = 'eq_given_gwp'
                prob_label = 'Conditional Probability Density P(Eco Quality | GWP)'
            else:
                continue
                
            # 对数变换 (log1p)
            df[f'log_{x_col}'] = np.log1p(df[x_col].abs())
            df[f'log_{y_col}'] = np.log1p(df[y_col].abs())
            
            # 创建对数变换后的2D直方图
            plt.figure(figsize=(12, 10))
            
            # 使用pivot_table重构数据以便于绘图
            pivot_df = df.pivot_table(
                index=f'log_{x_col}',
                columns=f'log_{y_col}',
                values='conditional_probability'
            ).fillna(0)
            
            # 绘制热图
            sns.heatmap(
                pivot_df,
                cmap='viridis',
                cbar_kws={'label': prob_label},
                xticklabels=20,
                yticklabels=20
            )
            
            plt.xlabel(f'log(1+{x_col.upper()})')
            plt.ylabel(f'log(1+{y_col.upper()})')
            plt.title(f'Category: {category} - {title_suffix} (Log-transformed)')
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, f'log_cond_prob_{output_suffix}_{category}.png'))
            plt.close()
            
            print(f"成功生成对数变换后的条件概率分布图: {category} - {title_suffix}")
        except Exception as e:
            print(f"处理文件 {file_path} 时发生错误: {str(e)}")
    
    print(f"\n所有文件处理完成! 结果保存在: {output_dir}")

def alternative_visualization(input_dir='output/results', output_dir='output/log_transformed_results'):
    """
    使用散点图和KDE进行对数变换后的可视化，可能对稀疏数据效果更好
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"使用替代方法处理目录: {input_dir} 中的CSV文件...")
    
    # 查找所有联合概率和条件概率的CSV文件
    joint_prob_files = glob.glob(os.path.join(input_dir, 'joint_prob_*.csv'))
    
    # 处理联合概率分布文件
    for file_path in joint_prob_files:
        try:
            file_name = os.path.basename(file_path)
            category = file_name.split('_')[-1].replace('.csv', '')
            print(f"处理文件: {file_name}")
            
            # 读取CSV文件
            df = pd.read_csv(file_path)
            
            # 确定文件类型
            if 'gwp_hh' in file_name:
                x_col = 'gwp'
                y_col = 'human_health'
                title_suffix = 'GWP and Human Health'
                output_suffix = 'gwp_hh'
            elif 'gwp_eq' in file_name:
                x_col = 'gwp'
                y_col = 'eco_quality'
                title_suffix = 'GWP and Eco Quality'
                output_suffix = 'gwp_eq'
            else:
                continue
                
            # 对数变换 (log1p)
            df[f'log_{x_col}'] = np.log1p(df[x_col].abs())
            df[f'log_{y_col}'] = np.log1p(df[y_col].abs())
            
            # 使用散点图和KDE可视化
            plt.figure(figsize=(12, 10))
            
            # 使用散点图，颜色和大小代表联合概率密度
            sizes = df['joint_probability'] * 5000  # 根据数据范围调整系数
            sizes = np.clip(sizes, 5, 500)  # 限制散点大小范围
            
            scatter = plt.scatter(
                df[f'log_{x_col}'],
                df[f'log_{y_col}'],
                c=df['joint_probability'],
                cmap='viridis',
                s=sizes,
                alpha=0.6
            )
            
            # 添加颜色条
            cbar = plt.colorbar(scatter)
            cbar.set_label('Joint Probability Density')
            
            # 添加KDE轮廓线
            sns.kdeplot(
                x=df[f'log_{x_col}'],
                y=df[f'log_{y_col}'],
                weights=df['joint_probability'],
                levels=5,
                color='red',
                linewidths=1
            )
            
            plt.xlabel(f'log(1+{x_col.upper()})')
            plt.ylabel(f'log(1+{y_col.upper()})')
            plt.title(f'Category: {category} - {title_suffix} Joint Probability Distribution (Scatter+KDE)')
            plt.tight_layout()
            plt.savefig(os.path.join(output_dir, f'log_scatter_kde_{output_suffix}_{category}.png'))
            plt.close()
            
            print(f"成功生成散点图+KDE可视化: {category} - {title_suffix}")
        except Exception as e:
            print(f"处理文件 {file_path} 时发生错误: {str(e)}")

if __name__ == "__main__":
    # 执行对数变换可视化
    log_transform_visualize()
    
    # 使用替代方法可视化（针对稀疏数据）
    alternative_visualization()