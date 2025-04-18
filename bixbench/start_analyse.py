#!/usr/bin/env python
import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

import datasets
import yaml

GENERATE_TRAJECTORIES_YAML = "run_configuration/generate_trajectories.yaml"
POSTPROCESSING_YAML = "run_configuration/postprocessing.yaml"


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="BixBench分析工具")
    parser.add_argument("--run_name", type=str, required=True, help="运行名称，例如：bixbench-run-1-gpt4o")
    parser.add_argument("--llm_model", type=str, required=True, help="LLM模型名称，例如：gpt-4o、claude-3-sonnet")
    parser.add_argument(
        "--capsule_mode", 
        type=str, 
        choices=["open", "mcq"],
        default="open", 
        help="胶囊模式: open或mcq (默认: open)"
    )
    parser.add_argument(
        "--short_ids", 
        type=str, 
        nargs="*", 
        help="要运行的胶囊short_id列表，不指定则运行所有胶囊"
    )
    parser.add_argument(
        "--skip_generation", 
        action="store_true", 
        help="跳过生成轨迹阶段，直接进行后处理"
    )
    parser.add_argument(
        "--skip_postprocessing", 
        action="store_true", 
        help="跳过后处理阶段"
    )
    parser.add_argument(
        "--total_questions", 
        type=int, 
        default=296, 
        help="评估的总问题数量 (默认: 296)"
    )

    return parser.parse_args()


def generate_trajectory_yaml(args):
    """生成轨迹生成的YAML配置文件"""
    # 获取原始YAML文件的路径
    script_dir = Path(__file__).parent
    yaml_path = script_dir / GENERATE_TRAJECTORIES_YAML
    
    # 读取原始YAML内容
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 更新配置
    config["run_name"] = args.run_name
    config["agent"]["agent_kwargs"]["llm_model"]["name"] = args.llm_model
    config["capsule"]["mode"] = args.capsule_mode
    
    # 根据capsule_mode设置system_prompt
    if args.capsule_mode == "open":
        config["capsule"]["system_prompt"] = "CAPSULE_SYSTEM_PROMPT_OPEN"
    elif args.capsule_mode == "mcq":
        config["capsule"]["system_prompt"] = "CAPSULE_SYSTEM_PROMPT_MCQ"
    
    # 保存更新后的YAML
    output_path = script_dir / f"run_configuration/{args.run_name}_generate_trajectories.yaml"
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    return output_path


def generate_postprocessing_yaml(args):
    """生成后处理的YAML配置文件"""
    # 获取原始YAML文件的路径
    script_dir = Path(__file__).parent
    yaml_path = script_dir / POSTPROCESSING_YAML
    
    # 读取原始YAML内容
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 更新配置
    config["data_path"] = f"data/trajectories/{args.run_name}/"
    config["results_dir"] = f"bixbench_results_{args.run_name}"
    
    # 设置运行比较配置
    if config["run_comparison"]["run"]:
        config["run_comparison"]["total_questions"] = args.total_questions
        config["run_comparison"]["run_name_groups"] = [[args.run_name]]
        config["run_comparison"]["group_titles"] = [args.llm_model]
    
    # 保存更新后的YAML
    output_path = script_dir / f"run_configuration/{args.run_name}_postprocessing.yaml"
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    return output_path


async def load_and_filter_capsules(args):
    """加载并过滤胶囊数据集"""
    # 加载BixBench数据集
    bixbench = datasets.load_dataset("futurehouse/bixbench", split="train").to_list()
    
    # 如果指定了short_ids，过滤数据集
    if args.short_ids and len(args.short_ids) > 0:
        filtered_capsules = [
            capsule for capsule in bixbench 
            if capsule["short_id"] in args.short_ids
        ]
        if not filtered_capsules:
            print(f"错误：未找到指定的short_ids: {args.short_ids}")
            print(f"可用的short_ids: {[c['short_id'] for c in bixbench]}")
            sys.exit(1)
        return filtered_capsules
    
    return bixbench


async def run_selected_capsules(config_path, capsules):
    """直接运行指定的胶囊，无需修改generate_trajectories.py文件"""
    try:
        # 导入所需模块 - 使用本地导入
        script_dir = Path(__file__).parent
        sys.path.insert(0, str(script_dir.parent))  # 将父目录添加到sys.path
        
        # 动态导入 TrajectoryGenerator
        import importlib.util
        generate_trajectories_path = script_dir / "generate_trajectories.py"
        spec = importlib.util.spec_from_file_location("generate_trajectories", generate_trajectories_path)
        generate_trajectories_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generate_trajectories_module)
        TrajectoryGenerator = generate_trajectories_module.TrajectoryGenerator
        
        # 加载配置
        config_path = Path(config_path)
        
        # 创建TrajectoryGenerator实例
        generator = TrajectoryGenerator(config_path=config_path)
        
        # 处理胶囊数据（确保必要的数据已准备好）
        for capsule in capsules:
            await generator.process_capsule(capsule)
        
        # 设置环境并运行批处理
        environments = [generator.environment_factory(capsule) for capsule in capsules]
        
        # 批量处理环境
        print(f"开始处理 {len(environments)} 个胶囊...")
        results = await generator.batch_rollout(environments)
        
        # 存储轨迹
        for trajectory, env in results:
            await generator.store_trajectory(trajectory, env)
            
        return True
    except Exception as e:
        import traceback
        print(f"运行指定胶囊时出错: {e}")
        print(traceback.format_exc())
        return False


def run_generate_trajectories(config_path):
    """运行generate_trajectories.py脚本"""
    script_dir = Path(__file__).parent
    generate_trajectories_path = script_dir / "generate_trajectories.py"
    
    cmd = [sys.executable, str(generate_trajectories_path), "--config", str(config_path)]
    print(f"执行命令: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"generate_trajectories.py 运行失败: {e}")
        return False


def run_postprocessing(config_path):
    """运行postprocessing.py脚本"""
    script_dir = Path(__file__).parent
    postprocessing_path = script_dir / "postprocessing.py"
    
    cmd = [sys.executable, str(postprocessing_path), "--config", str(config_path)]
    print(f"执行命令: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"postprocessing.py 运行失败: {e}")
        return False


async def main():
    """主函数"""
    args = parse_args()
    
    # 生成配置文件
    trajectory_config_path = generate_trajectory_yaml(args)
    postprocessing_config_path = generate_postprocessing_yaml(args)
    
    print(f"已生成配置文件:")
    print(f"- 轨迹生成配置: {trajectory_config_path}")
    print(f"- 后处理配置: {postprocessing_config_path}")
    
    # 轨迹生成阶段
    if not args.skip_generation:
        # 如果指定了short_ids，使用专用函数运行
        if args.short_ids and len(args.short_ids) > 0:
            capsules = await load_and_filter_capsules(args)
            print(f"找到 {len(capsules)} 个胶囊")
            print(f"将运行以下胶囊: {[c['short_id'] for c in capsules]}")
            success = await run_selected_capsules(trajectory_config_path, capsules)
        else:
            # 运行所有胶囊
            success = run_generate_trajectories(trajectory_config_path)
        
        if not success:
            print("轨迹生成失败，退出程序")
            return
    
    # 后处理阶段
    if not args.skip_postprocessing:
        print("开始后处理...")
        run_postprocessing(postprocessing_config_path)


if __name__ == "__main__":
    asyncio.run(main()) 