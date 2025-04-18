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


def modify_generate_trajectories_script(capsules):
    """临时修改generate_trajectories.py以便只运行指定的胶囊"""
    script_dir = Path(__file__).parent
    generate_trajectories_path = script_dir / "generate_trajectories.py"
    
    # 读取原始脚本内容
    with open(generate_trajectories_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 保存原始脚本备份
    with open(f"{generate_trajectories_path}.bak", "w", encoding="utf-8") as f:
        f.write(content)
    
    # 准备胶囊数据的JSON字符串
    capsules_json = json.dumps([
        {k: v for k, v in capsule.items() if k != "local_data_folder"}
        for capsule in capsules
    ])
    
    # 修改脚本以加载预定义的胶囊列表
    modified_load_bixbench = """
    async def load_bixbench(self) -> list[dict[str, Any]]:
        \"\"\"Load BixBench dataset and process all capsules.\"\"\"
        # 使用预定义的胶囊列表
        bixbench = json.loads('{0}')
        
        # Process all capsules concurrently
        tasks = [self.process_capsule(capsule) for capsule in bixbench]
        await asyncio.gather(*tasks)
        
        return bixbench
    """.format(capsules_json.replace("'", "\\'").replace('"', '\\"'))
    
    # 替换load_bixbench方法
    import re
    pattern = r"async def load_bixbench.*?return bixbench\n"
    modified_content = re.sub(pattern, modified_load_bixbench, content, flags=re.DOTALL)
    
    # 写入修改后的脚本
    with open(generate_trajectories_path, "w", encoding="utf-8") as f:
        f.write(modified_content)
    
    return generate_trajectories_path


def restore_generate_trajectories_script():
    """还原generate_trajectories.py脚本"""
    script_dir = Path(__file__).parent
    generate_trajectories_path = script_dir / "generate_trajectories.py"
    backup_path = script_dir / "generate_trajectories.py.bak"
    
    if backup_path.exists():
        with open(backup_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        with open(generate_trajectories_path, "w", encoding="utf-8") as f:
            f.write(original_content)
        
        backup_path.unlink()  # 删除备份文件


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
    
    # 加载并过滤胶囊
    if not args.skip_generation:
        capsules = await load_and_filter_capsules(args)
        print(f"找到 {len(capsules)} 个胶囊")
        
        # 如果指定了short_ids，修改generate_trajectories.py脚本
        if args.short_ids and len(args.short_ids) > 0:
            print(f"将运行以下胶囊: {[c['short_id'] for c in capsules]}")
            try:
                modify_generate_trajectories_script(capsules)
                print("已临时修改generate_trajectories.py以运行指定胶囊")
                
                # 运行generate_trajectories.py
                success = run_generate_trajectories(trajectory_config_path)
                
                # 还原脚本
                restore_generate_trajectories_script()
                print("已还原generate_trajectories.py")
                
                if not success:
                    return
            except Exception as e:
                print(f"修改脚本时出错: {e}")
                # 确保脚本被还原
                restore_generate_trajectories_script()
                return
        else:
            # 直接运行generate_trajectories.py
            success = run_generate_trajectories(trajectory_config_path)
            if not success:
                return
    
    # 运行后处理
    if not args.skip_postprocessing:
        print("开始后处理...")
        run_postprocessing(postprocessing_config_path)


if __name__ == "__main__":
    asyncio.run(main()) 