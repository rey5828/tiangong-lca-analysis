import os
import elasticsearch
from elasticsearch import Elasticsearch
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.gridspec as gridspec
from scipy import stats
import warnings
import os
from pathlib import Path
warnings.filterwarnings('ignore')

# 1. 连接到Elasticsearch并获取数据
def connect_to_elasticsearch():
    print("正在连接到Elasticsearch...")
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    
    es = Elasticsearch(
        hosts=["http://39.105.216.221:9200/"],
        basic_auth=(username, password),
    )
    
    if es.ping():
        print("成功连接到Elasticsearch")
        return es
    else:
        print("无法连接到Elasticsearch")
        return None

def fetch_data_from_elasticsearch(es, index_name):
    print(f"正在从索引 {index_name} 获取数据...")
    
    # 使用scroll API处理大量数据
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"process_type": "UNIT_PROCESS"}}
                ]
            }
        },
        "size": 1000
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

# 2. 数据预处理和分析
def preprocess_and_analyze_data(df):
    print("正在预处理数据...")
    
    # 验证数据中是否有我们需要的字段
    required_fields = ['category', 'gwp', 'flow_name', 'flow_direction', 'flow_category', 'process_type']
    for field in required_fields:
        if field not in df.columns:
            print(f"错误: 数据中缺少必需的字段 '{field}'")
            return None
    
    # 筛选出Nitrogen oxides的记录
    #nitrogen_oxide_condition = (
        #(df['flow_name'] == 'Nitrogen oxides') & 
        #(df['flow_direction'] == 'output') & 
        #(df['flow_category'] == 'ELEMENTARY_FLOW') & 
        #(df['process_type'] == 'UNIT_PROCESS')
    #)

    nitrogen_oxide_condition = (
        (df['flow_name'] == 'Zinc II') & 
        (df['flow_direction'] == 'output') &
        (df['process_type'] == 'UNIT_PROCESS')
    )
    
    # 创建一个标志列，表示是否为Nitrogen oxides排放
    df['is_nitrogen_oxide'] = nitrogen_oxide_condition
    
    # 检查每个category中的nitrogen oxide记录数
    categories = df['category'].unique()
    print(f"发现的category数量: {len(categories)}")
    
    category_stats = []
    for category in categories:
        cat_df = df[df['category'] == category]
        nox_count = cat_df['is_nitrogen_oxide'].sum()
        total_count = len(cat_df)
        percentage = (nox_count / total_count) * 100 if total_count > 0 else 0
        
        category_stats.append({
            'category': category,
            'total_records': total_count,
            'nox_records': nox_count,
            'nox_percentage': percentage
        })
    
    stats_df = pd.DataFrame(category_stats)
    print("每个category的统计信息:")
    print(stats_df)
    
    return df, categories

# 3. 按process_id分组计算gwp和nitrogen oxide的共现关系
def calculate_cooccurrence(df, categories):
    print("正在计算GWP和Nitrogen oxides的共现关系...")
    
    results = {}
    
    for category in categories:
        print(f"\n处理category: {category}")
        cat_df = df[df['category'] == category]
        
        # 按process_id分组，检查每个过程是否有gwp和nitrogen oxide排放
        process_groups = cat_df.groupby('process_id').agg({
            'gwp': 'sum',  # 每个过程的gwp总和
            'is_nitrogen_oxide': 'sum'  # 每个过程的nitrogen oxide排放次数
        }).reset_index()
        
        # 创建是否有gwp和是否有nitrogen oxide的标志
        process_groups['has_gwp'] = process_groups['gwp'] > 0
        process_groups['has_nox'] = process_groups['is_nitrogen_oxide'] > 0
        
        # 计算共现统计
        total_processes = len(process_groups)
        processes_with_gwp = process_groups['has_gwp'].sum()
        processes_with_nox = process_groups['has_nox'].sum()
        processes_with_both = ((process_groups['has_gwp']) & (process_groups['has_nox'])).sum()
        
        # 计算概率
        p_gwp = processes_with_gwp / total_processes if total_processes > 0 else 0
        p_nox = processes_with_nox / total_processes if total_processes > 0 else 0
        p_both = processes_with_both / total_processes if total_processes > 0 else 0
        p_nox_given_gwp = processes_with_both / processes_with_gwp if processes_with_gwp > 0 else 0
        
        results[category] = {
            'total_processes': total_processes,
            'processes_with_gwp': processes_with_gwp,
            'processes_with_nox': processes_with_nox,
            'processes_with_both': processes_with_both,
            'p_gwp': p_gwp,
            'p_nox': p_nox,
            'p_both': p_both,
            'p_nox_given_gwp': p_nox_given_gwp
        }
        
        print(f"Category: {category}")
        print(f"总过程数: {total_processes}")
        print(f"有GWP排放的过程数: {processes_with_gwp} ({p_gwp:.2%})")
        print(f"有Nitrogen oxides排放的过程数: {processes_with_nox} ({p_nox:.2%})")
        print(f"同时有GWP和Nitrogen oxides排放的过程数: {processes_with_both} ({p_both:.2%})")
        print(f"在有GWP排放的条件下，有Nitrogen oxides排放的条件概率: {p_nox_given_gwp:.2%}")
        
        # 针对有gwp的过程，分析gwp值与是否有nitrogen oxide的关系
        gwp_with_nox = process_groups[process_groups['has_nox']]['gwp']
        gwp_without_nox = process_groups[~process_groups['has_nox']]['gwp']
        
        results[category]['gwp_with_nox'] = gwp_with_nox.tolist()
        results[category]['gwp_without_nox'] = gwp_without_nox.tolist()
    
    return results

# 4. 可视化结果
def visualize_results(results, output_dir):
    print("\n正在可视化结果...")
    
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 1. 创建条形图比较不同category的条件概率 P(NOx|GWP)
    plt.figure(figsize=(14, 8))
    categories = list(results.keys())
    probabilities = [results[cat]['p_nox_given_gwp'] for cat in categories]
    
    # 按条件概率降序排序
    sorted_indices = np.argsort(probabilities)[::-1]
    sorted_categories = [categories[i] for i in sorted_indices]
    sorted_probabilities = [probabilities[i] for i in sorted_indices]
    
    # 使用不同的颜色
    colors = plt.cm.viridis(np.linspace(0, 0.8, len(categories)))
    
    bars = plt.bar(range(len(sorted_categories)), sorted_probabilities, color=colors)
    plt.xlabel('Category', fontsize=12)
    plt.ylabel('P(Nitrogen oxides | GWP)', fontsize=12)
    plt.title('在排放GWP的条件下排放Nitrogen oxides的条件概率', fontsize=14)
    plt.xticks(range(len(sorted_categories)), sorted_categories, rotation=45, ha='right')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 在每个条形上方显示概率值
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                f'{sorted_probabilities[i]:.2%}',
                ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/conditional_probability_by_category.png', dpi=300)
    plt.close()
    
    # 2. 创建堆叠条形图显示每个category中的过程分布
    plt.figure(figsize=(14, 8))
    
    # 准备数据
    categories = list(results.keys())
    gwp_only = [results[cat]['processes_with_gwp'] - results[cat]['processes_with_both'] for cat in categories]
    nox_only = [results[cat]['processes_with_nox'] - results[cat]['processes_with_both'] for cat in categories]
    both = [results[cat]['processes_with_both'] for cat in categories]
    neither = [results[cat]['total_processes'] - results[cat]['processes_with_gwp'] - results[cat]['processes_with_nox'] + results[cat]['processes_with_both'] for cat in categories]
    
    # 绘制堆叠条形图
    width = 0.6
    plt.bar(categories, neither, width, label='Neither GWP nor NOx', color='lightgray')
    plt.bar(categories, gwp_only, width, bottom=neither, label='GWP only', color='royalblue')
    plt.bar(categories, nox_only, width, bottom=[i+j for i,j in zip(neither, gwp_only)], label='NOx only', color='orangered')
    plt.bar(categories, both, width, bottom=[i+j+k for i,j,k in zip(neither, gwp_only, nox_only)], label='Both GWP and NOx', color='forestgreen')
    
    plt.xlabel('Category', fontsize=12)
    plt.ylabel('Number of Processes', fontsize=12)
    plt.title('每个Category中过程的分布', fontsize=14)
    plt.xticks(rotation=45, ha='right')
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/process_distribution_by_category.png', dpi=300)
    plt.close()
    
    # 3. 创建散点图矩阵比较不同category中GWP与是否有NOx的关系
    gs = gridspec.GridSpec(3, 3)
    plt.figure(figsize=(15, 15))
    
    for i, category in enumerate(categories[:min(9, len(categories))]):  # 最多显示9个category
        ax = plt.subplot(gs[i // 3, i % 3])
        
        gwp_with_nox = results[category]['gwp_with_nox']
        gwp_without_nox = results[category]['gwp_without_nox']
        
        if gwp_with_nox and gwp_without_nox:  # 确保两个集合都不为空
            # 创建箱线图
            data = [gwp_with_nox, gwp_without_nox]
            labels = ['With NOx', 'Without NOx']
            
            ax.boxplot(data, labels=labels, showfliers=False)
            ax.set_title(f'Category: {category}')
            ax.set_ylabel('GWP')
            ax.grid(True, linestyle='--', alpha=0.7)
        else:
            ax.text(0.5, 0.5, 'Insufficient data', 
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax.transAxes)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/gwp_distribution_by_nox_presence.png', dpi=300)
    plt.close()
    
    # 4. 创建热图显示不同指标间的关系
    plt.figure(figsize=(15, 8))
    
    # 准备数据
    data_for_heatmap = {
        'Category': categories,
        'P(GWP)': [results[cat]['p_gwp'] for cat in categories],
        'P(NOx)': [results[cat]['p_nox'] for cat in categories],
        'P(GWP and NOx)': [results[cat]['p_both'] for cat in categories],
        'P(NOx|GWP)': [results[cat]['p_nox_given_gwp'] for cat in categories]
    }
    
    df_heatmap = pd.DataFrame(data_for_heatmap)
    df_heatmap = df_heatmap.set_index('Category')
    
    # 绘制热图
    sns.heatmap(df_heatmap, annot=True, fmt='.2%', cmap='viridis',
                linewidths=0.5, cbar_kws={'label': 'Probability'})
    
    plt.title('各Category中不同概率指标热图', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/probability_heatmap_by_category.png', dpi=300)
    plt.close()
    
    # 5. 创建饼图显示每个category中同时排放GWP和NOx的比例
    num_categories = len(categories)
    cols = 3
    rows = (num_categories + cols - 1) // cols
    
    plt.figure(figsize=(15, 5 * rows))
    
    for i, category in enumerate(categories):
        plt.subplot(rows, cols, i+1)
        
        # 准备数据
        gwp_only = results[category]['processes_with_gwp'] - results[category]['processes_with_both']
        both = results[category]['processes_with_both']
        labels = ['GWP only', 'Both GWP and NOx']
        sizes = [gwp_only, both]
        colors = ['royalblue', 'forestgreen']
        
        # 绘制饼图
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                startangle=90, wedgeprops={'edgecolor': 'white'})
        plt.axis('equal')
        plt.title(f'Category: {category}')
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/gwp_nox_pie_charts.png', dpi=300)
    plt.close()
    
    # 6. 综合比较图：条形图并列显示P(GWP), P(NOx)和P(NOx|GWP)
    plt.figure(figsize=(15, 10))
    
    # 准备数据
    x = np.arange(len(categories))
    width = 0.25
    
    p_gwp = [results[cat]['p_gwp'] for cat in categories]
    p_nox = [results[cat]['p_nox'] for cat in categories]
    p_nox_given_gwp = [results[cat]['p_nox_given_gwp'] for cat in categories]
    
    # 绘制条形图
    plt.bar(x - width, p_gwp, width, label='P(GWP)', color='royalblue')
    plt.bar(x, p_nox, width, label='P(NOx)', color='orangered')
    plt.bar(x + width, p_nox_given_gwp, width, label='P(NOx|GWP)', color='forestgreen')
    
    plt.xlabel('Category', fontsize=12)
    plt.ylabel('Probability', fontsize=12)
    plt.title('各Category中不同概率指标比较', fontsize=14)
    plt.xticks(x, categories, rotation=45, ha='right')
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/probability_comparison_by_category.png', dpi=300)
    plt.close()
    
    print(f"可视化结果已保存到目录: {output_dir}")

# 5. 保存结果到CSV文件
def save_results_to_csv(results, output_dir):
    print("\n正在保存结果到CSV文件...")
    
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 创建汇总结果的DataFrame
    summary_data = []
    for category, data in results.items():
        summary_data.append({
            'category': category,
            'total_processes': data['total_processes'],
            'processes_with_gwp': data['processes_with_gwp'],
            'processes_with_nox': data['processes_with_nox'],
            'processes_with_both': data['processes_with_both'],
            'p_gwp': data['p_gwp'],
            'p_nox': data['p_nox'],
            'p_both': data['p_both'],
            'p_nox_given_gwp': data['p_nox_given_gwp']
        })
    
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(f'{output_dir}/gwp_nox_probability_summary.csv', index=False)
    
    print(f"结果已保存到文件: {output_dir}/gwp_nox_probability_summary.csv")

# 主函数
def main():
    # 设置Elasticsearch连接参数
    index_name = 'processwithghg_dedup2'
    output_dir = 'output/gwp_nox_analysis_Zinc II'
    
    # 连接到Elasticsearch
    es = connect_to_elasticsearch()
    if es is None:
        return
    
    # 获取数据
    df = fetch_data_from_elasticsearch(es, index_name)
    
    # 数据预处理和分析
    preprocessed_data = preprocess_and_analyze_data(df)
    if preprocessed_data is None:
        return
    
    df, categories = preprocessed_data
    
    # 计算GWP和Nitrogen oxides的共现关系
    results = calculate_cooccurrence(df, categories)
    
    # 可视化结果
    visualize_results(results, output_dir)
    
    # 保存结果到CSV文件
    save_results_to_csv(results, output_dir)
    
    print("\n所有操作完成！")

if __name__ == "__main__":
    main()