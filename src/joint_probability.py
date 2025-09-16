import elasticsearch
from elasticsearch import Elasticsearch
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
import seaborn as sns
from scipy import stats
from sklearn.neighbors import KernelDensity
import warnings
warnings.filterwarnings('ignore')
import os

import os
import elasticsearch
from elasticsearch import Elasticsearch
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
import seaborn as sns
from scipy import stats
from sklearn.neighbors import KernelDensity
import warnings
import os
warnings.filterwarnings('ignore')

# 1. 连接到Elasticsearch并获取数据
def connect_to_elasticsearch():
    print("正在连接到Elasticsearch...")
    es = Elasticsearch(
        hosts=["http://39.105.216.221:9200/"],
        basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
    )
    
    if es.ping():
        print("成功连接到Elasticsearch")
        return es
    else:
        print("无法连接到Elasticsearch")
        return None

def fetch_data_from_elasticsearch(es, index_name, size=10000):
    print(f"正在从索引 {index_name} 获取数据...")
    # 使用scroll API处理大量数据
    query = {
        "query": {
            "match_all": {}
        },
        "size": 1000  # 每批获取1000条记录
    }
    
    # 初始化scroll
    result = es.search(index=index_name, body=query, scroll='5m')
    scroll_id = result['_scroll_id']
    hits = result['hits']['hits']
    
    # 获取所有结果
    all_hits = hits
    while len(hits) > 0:
        result = es.scroll(scroll_id=scroll_id, scroll='5m')
        hits = result['hits']['hits']
        all_hits.extend(hits)
        if len(hits) < 1000:  # 如果返回的结果数小于批量大小，说明已到达末尾
            break
    
    print(f"成功获取 {len(all_hits)} 条记录")
    
    # 将结果转换为DataFrame
    data = [hit['_source'] for hit in all_hits]
    df = pd.DataFrame(data)
    return df

# 2. 数据预处理
def preprocess_data(df):
    print("正在进行数据预处理...")
    # 检查并处理缺失值
    print(f"原始数据形状: {df.shape}")
    print(f"缺失值统计: \n{df.isnull().sum()}")
    
    # 移除gwp, human_health或eco_quality为空的记录
    df = df.dropna(subset=['gwp', 'human_health', 'eco_quality'])
    print(f"处理缺失值后数据形状: {df.shape}")
    
    # 基本统计描述
    numeric_cols = ['gwp', 'human_health', 'eco_quality']
    print("数据描述性统计:")
    print(df[numeric_cols].describe())
    
    # 识别异常值并可能进行处理
    for col in numeric_cols:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 3 * IQR
        upper_bound = Q3 + 3 * IQR
        outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
        print(f"{col} 异常值数量: {len(outliers)}")
    
    return df

# 3. 按category分组数据
def group_by_category(df):
    print("正在按category分组数据...")
    categories = df['category'].unique()
    print(f"发现的category数量: {len(categories)}")
    print(f"Categories: {categories}")
    
    return categories

# 4. 针对每个category计算GWP与human_health和eco_quality的联合概率分布
def calculate_joint_probabilities(df, categories):
    print("正在计算联合概率分布...")
    results = {}
    
    for category in categories:
        print(f"\n处理category: {category}")
        # 筛选出当前category的数据
        cat_df = df[df['category'] == category]
        print(f"该category下数据点数量: {len(cat_df)}")
        
        if len(cat_df) < 10:  # 如果数据点太少，跳过
            print(f"跳过category {category}，数据点数量不足")
            continue
            
        # 提取GWP, human_health和eco_quality数据
        gwp_values = cat_df['gwp'].values
        hh_values = cat_df['human_health'].values
        eq_values = cat_df['eco_quality'].values
        
        # 计算GWP与human_health的联合概率分布
        try:
            H_gwp_hh, xedges_gwp_hh, yedges_gwp_hh = np.histogram2d(
                gwp_values, hh_values, bins=20, density=True
            )
            
            # 计算GWP与eco_quality的联合概率分布
            H_gwp_eq, xedges_gwp_eq, yedges_gwp_eq = np.histogram2d(
                gwp_values, eq_values, bins=20, density=True
            )
            
            # 存储结果
            results[category] = {
                'gwp_hh': {
                    'H': H_gwp_hh,
                    'xedges': xedges_gwp_hh,
                    'yedges': yedges_gwp_hh
                },
                'gwp_eq': {
                    'H': H_gwp_eq,
                    'xedges': xedges_gwp_eq,
                    'yedges': yedges_gwp_eq
                },
                'data_points': len(cat_df)
            }
            print(f"成功计算category {category}的联合概率分布")
        except Exception as e:
            print(f"计算category {category}的联合概率分布时出错: {str(e)}")
    
    return results

# 5. 可视化结果
def visualize_joint_probabilities(results, output_dir='.'):
    print("\n正在可视化联合概率分布...")
    
    for category, result in results.items():
        try:
            # GWP与human_health的联合概率分布热图
            plt.figure(figsize=(12, 10))
            
            H_gwp_hh = result['gwp_hh']['H']
            xedges_gwp_hh = result['gwp_hh']['xedges']
            yedges_gwp_hh = result['gwp_hh']['yedges']
            
            plt.pcolormesh(xedges_gwp_hh, yedges_gwp_hh, H_gwp_hh.T, cmap='viridis')
            plt.colorbar(label='联合概率密度')
            plt.xlabel('GWP')
            plt.ylabel('Human Health')
            plt.title(f'Category: {category} - GWP与Human Health联合概率分布 (数据点: {result["data_points"]})')
            plt.tight_layout()
            plt.savefig(f'{output_dir}/joint_prob_gwp_hh_{category}.png')
            plt.close()
            
            # GWP与eco_quality的联合概率分布热图
            plt.figure(figsize=(12, 10))
            
            H_gwp_eq = result['gwp_eq']['H']
            xedges_gwp_eq = result['gwp_eq']['xedges']
            yedges_gwp_eq = result['gwp_eq']['yedges']
            
            plt.pcolormesh(xedges_gwp_eq, yedges_gwp_eq, H_gwp_eq.T, cmap='viridis')
            plt.colorbar(label='联合概率密度')
            plt.xlabel('GWP')
            plt.ylabel('Eco Quality')
            plt.title(f'Category: {category} - GWP与Eco Quality联合概率分布 (数据点: {result["data_points"]})')
            plt.tight_layout()
            plt.savefig(f'{output_dir}/joint_prob_gwp_eq_{category}.png')
            plt.close()
            
            print(f"成功保存category {category}的可视化结果")
        except Exception as e:
            print(f"可视化category {category}的结果时出错: {str(e)}")

# 6. 计算条件概率
def calculate_conditional_probabilities(results):
    print("\n正在计算条件概率...")
    conditional_probs = {}
    
    for category, result in results.items():
        try:
            # 计算P(human_health | gwp)
            H_gwp_hh = result['gwp_hh']['H']
            gwp_marginal = H_gwp_hh.sum(axis=1)
            gwp_marginal = np.where(gwp_marginal == 0, 1e-10, gwp_marginal)  # 避免除以零
            P_hh_given_gwp = H_gwp_hh / gwp_marginal[:, np.newaxis]
            
            # 计算P(eco_quality | gwp)
            H_gwp_eq = result['gwp_eq']['H']
            P_eq_given_gwp = H_gwp_eq / gwp_marginal[:, np.newaxis]
            
            # 存储结果
            conditional_probs[category] = {
                'P_hh_given_gwp': P_hh_given_gwp,
                'P_eq_given_gwp': P_eq_given_gwp,
                'gwp_edges': result['gwp_hh']['xedges'],
                'hh_edges': result['gwp_hh']['yedges'],
                'eq_edges': result['gwp_eq']['yedges']
            }
            print(f"成功计算category {category}的条件概率")
        except Exception as e:
            print(f"计算category {category}的条件概率时出错: {str(e)}")
    
    return conditional_probs

# 7. 可视化条件概率
def visualize_conditional_probabilities(conditional_probs, output_dir='.'):
    print("\n正在可视化条件概率...")
    
    for category, result in conditional_probs.items():
        try:
            # P(human_health | gwp)的热图
            plt.figure(figsize=(12, 10))
            
            P_hh_given_gwp = result['P_hh_given_gwp']
            gwp_edges = result['gwp_edges']
            hh_edges = result['hh_edges']
            
            plt.pcolormesh(gwp_edges, hh_edges, P_hh_given_gwp.T, cmap='viridis')
            plt.colorbar(label='条件概率密度 P(Human Health | GWP)')
            plt.xlabel('GWP')
            plt.ylabel('Human Health')
            plt.title(f'Category: {category} - 给定GWP时Human Health的条件概率分布')
            plt.tight_layout()
            plt.savefig(f'{output_dir}/cond_prob_hh_given_gwp_{category}.png')
            plt.close()
            
            # P(eco_quality | gwp)的热图
            plt.figure(figsize=(12, 10))
            
            P_eq_given_gwp = result['P_eq_given_gwp']
            eq_edges = result['eq_edges']
            
            plt.pcolormesh(gwp_edges, eq_edges, P_eq_given_gwp.T, cmap='viridis')
            plt.colorbar(label='条件概率密度 P(Eco Quality | GWP)')
            plt.xlabel('GWP')
            plt.ylabel('Eco Quality')
            plt.title(f'Category: {category} - 给定GWP时Eco Quality的条件概率分布')
            plt.tight_layout()
            plt.savefig(f'{output_dir}/cond_prob_eq_given_gwp_{category}.png')
            plt.close()
            
            print(f"成功保存category {category}的条件概率可视化结果")
        except Exception as e:
            print(f"可视化category {category}的条件概率时出错: {str(e)}")

# 8. 保存结果到CSV文件
def save_results_to_csv(results, conditional_probs, output_dir='.'):
    print("\n正在保存结果到CSV文件...")
    
    # 保存联合概率分布数据
    for category, result in results.items():
        try:
            # GWP与Human Health
            gwp_values = (result['gwp_hh']['xedges'][:-1] + result['gwp_hh']['xedges'][1:]) / 2
            hh_values = (result['gwp_hh']['yedges'][:-1] + result['gwp_hh']['yedges'][1:]) / 2
            
            joint_prob_data = []
            for i, gwp in enumerate(gwp_values):
                for j, hh in enumerate(hh_values):
                    joint_prob_data.append({
                        'gwp': gwp,
                        'human_health': hh,
                        'joint_probability': result['gwp_hh']['H'][i, j]
                    })
            
            joint_prob_df_hh = pd.DataFrame(joint_prob_data)
            joint_prob_df_hh.to_csv(f'{output_dir}/joint_prob_gwp_hh_{category}.csv', index=False)
            
            # GWP与Eco Quality
            eq_values = (result['gwp_eq']['yedges'][:-1] + result['gwp_eq']['yedges'][1:]) / 2
            
            joint_prob_data = []
            for i, gwp in enumerate(gwp_values):
                for j, eq in enumerate(eq_values):
                    joint_prob_data.append({
                        'gwp': gwp,
                        'eco_quality': eq,
                        'joint_probability': result['gwp_eq']['H'][i, j]
                    })
            
            joint_prob_df_eq = pd.DataFrame(joint_prob_data)
            joint_prob_df_eq.to_csv(f'{output_dir}/joint_prob_gwp_eq_{category}.csv', index=False)
            
            print(f"成功保存category {category}的联合概率分布数据")
        except Exception as e:
            print(f"保存category {category}的联合概率分布数据时出错: {str(e)}")
    
    # 保存条件概率分布数据
    for category, result in conditional_probs.items():
        try:
            # P(Human Health | GWP)
            gwp_values = (result['gwp_edges'][:-1] + result['gwp_edges'][1:]) / 2
            hh_values = (result['hh_edges'][:-1] + result['hh_edges'][1:]) / 2
            
            cond_prob_data = []
            for i, gwp in enumerate(gwp_values):
                for j, hh in enumerate(hh_values):
                    cond_prob_data.append({
                        'gwp': gwp,
                        'human_health': hh,
                        'conditional_probability': result['P_hh_given_gwp'][i, j]
                    })
            
            cond_prob_df_hh = pd.DataFrame(cond_prob_data)
            cond_prob_df_hh.to_csv(f'{output_dir}/cond_prob_hh_given_gwp_{category}.csv', index=False)
            
            # P(Eco Quality | GWP)
            eq_values = (result['eq_edges'][:-1] + result['eq_edges'][1:]) / 2
            
            cond_prob_data = []
            for i, gwp in enumerate(gwp_values):
                for j, eq in enumerate(eq_values):
                    cond_prob_data.append({
                        'gwp': gwp,
                        'eco_quality': eq,
                        'conditional_probability': result['P_eq_given_gwp'][i, j]
                    })
            
            cond_prob_df_eq = pd.DataFrame(cond_prob_data)
            cond_prob_df_eq.to_csv(f'{output_dir}/cond_prob_eq_given_gwp_{category}.csv', index=False)
            
            print(f"成功保存category {category}的条件概率分布数据")
        except Exception as e:
            print(f"保存category {category}的条件概率分布数据时出错: {str(e)}")

# 主函数
def main():
    # 设置Elasticsearch连接参数（根据您的实际情况调整）
    index_name = 'processwithghg_dedup2'  # 请替换为您的实际索引名称
    output_dir = 'output/results'  # 输出目录，请确保此目录存在
    
    # 连接到Elasticsearch
    es = Elasticsearch(
    hosts=["http://39.105.216.221:9200/"],
    basic_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
)
    
    # 获取数据
    df = fetch_data_from_elasticsearch(es, index_name)
    
    # 数据预处理
    df = preprocess_data(df)
    
    # 按category分组
    categories = group_by_category(df)
    
    # 计算联合概率分布
    results = calculate_joint_probabilities(df, categories)
    
    # 可视化联合概率分布
    visualize_joint_probabilities(results, output_dir)
    
    # 计算条件概率
    conditional_probs = calculate_conditional_probabilities(results)
    
    # 可视化条件概率
    visualize_conditional_probabilities(conditional_probs, output_dir)
    
    # 保存结果到CSV文件
    save_results_to_csv(results, conditional_probs, output_dir)
    
    print("\n所有操作完成！")

if __name__ == "__main__":
    main()