# BixBench 分析工具使用指南

`start_analyse.py` 是一个用于简化 BixBench 评测流程的工具，可以帮助用户快速配置、运行和评估各种 LLM 模型在 BixBench 基准测试上的表现。

## 功能特点

1. 自动生成配置文件：根据命令行参数生成轨迹生成和后处理的 YAML 配置文件
2. 支持指定胶囊：可以通过 short_id 指定运行特定的胶囊或胶囊列表
3. 一键式流程：自动执行轨迹生成和后处理评估
4. 灵活控制：支持跳过特定阶段，如轨迹生成或后处理
5. 无侵入性实现：通过直接调用 TrajectoryGenerator 类而非修改脚本文件

## 使用方法

### 基本用法

```bash
python bixbench/start_analyse.py --run_name RUN_NAME --llm_model MODEL_NAME [选项]
```

### 必填参数

- `--run_name`: 运行名称，如 "bixbench-run-1-gpt4o"
- `--llm_model`: LLM 模型名称，如 "gpt-4o", "claude-3-sonnet" 等

### 可选参数

- `--capsule_mode`: 胶囊模式，可选 "open" 或 "mcq"，默认为 "open"
- `--short_ids`: 要运行的胶囊 short_id 列表，如不指定则运行所有胶囊
- `--skip_generation`: 跳过轨迹生成阶段，直接进行后处理
- `--skip_postprocessing`: 跳过后处理阶段
- `--total_questions`: 评估的总问题数量，默认为 296

### 示例

1. 运行单个模型评测所有胶囊：

```bash
python bixbench/start_analyse.py --run_name bixbench-run-gpt4o --llm_model gpt-4o
```

2. 运行特定模型评测特定胶囊，并使用 MCQ 模式：

```bash
python bixbench/start_analyse.py --run_name bixbench-run-claude --llm_model claude-3-sonnet --capsule_mode mcq --short_ids capsule1 capsule2
```

3. 仅生成轨迹，不进行后处理：

```bash
python bixbench/start_analyse.py --run_name bixbench-run-llama --llm_model llama-3-70b --skip_postprocessing
```

4. 仅进行后处理，不生成轨迹：

```bash
python bixbench/start_analyse.py --run_name bixbench-run-gpt4o --llm_model gpt-4o --skip_generation
```

## 工作流程说明

1. **配置生成阶段**：脚本根据参数生成适当的 YAML 配置文件
2. **胶囊筛选阶段**：如果指定了 short_ids，脚本会筛选出对应的胶囊
3. **轨迹生成阶段**：
   - 对于特定胶囊：直接导入并使用 TrajectoryGenerator 类进行处理
   - 对于所有胶囊：调用标准的 generate_trajectories.py 脚本
4. **后处理评估阶段**：脚本运行 postprocessing.py 进行评估和可视化

## 技术实现

- 针对特定胶囊的运行采用了直接导入并使用 TrajectoryGenerator 类的方式，而非修改源文件
- 这种实现方式更加优雅，无侵入性，不会对原有代码产生副作用

## 注意事项

- 确保已安装所有必要依赖，如 datasets、pyyaml 等
- 如果使用 short_ids 筛选胶囊，确保指定的 ID 存在
- 建议在运行大规模评测前，先用少量胶囊进行测试
- 结果将保存在 `bixbench_results_[RUN_NAME]` 目录中 