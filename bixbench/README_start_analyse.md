# BixBench 分析工具使用指南

`start_analyse.py` 是一个用于简化 BixBench 评测流程的工具，可以帮助用户快速配置、运行和评估各种 LLM 模型在 BixBench 基准测试上的表现。

## 前置准备工作

在使用 BixBench 分析工具前，请确保完成以下准备工作：

1. **服务器环境**：在 deepomix 服务器上运行本工具
   ```bash
   # 登录到 deepomix 服务器
   ssh {username}@47.108.50.84
   ```

2. **Docker环境**：进入已有的 Docker 容器环境
   ```bash
   # 进入 Docker 容器
   docker exec -it 00c31 bash
   ```

3. **API密钥设置**：设置必要的环境变量
   ```bash
   # 设置 OpenAI API 密钥
   export OPENAI_API_KEY='your_api_key_here'
   ```

4. **验证环境**：确认环境变量已正确设置
   ```bash
   # 检查环境变量
   echo $OPENAI_API_KEY
   ```

## ⚠️ 重要说明 - 运行名称 ⚠️

**每次运行工具时，必须修改`--run_name`参数，确保使用唯一的运行名称。**

原因：
- 相同的`run_name`会导致数据覆盖，丢失之前的评测结果
- 使用不同的`run_name`可以保留多次评测的历史记录
- 便于后续比较不同模型或配置的性能差异

推荐的命名格式：
```
bixbench-run-{模型名称}-{日期}-{序号}
```

例如：`bixbench-run-gpt4o-20231015-1`

## 功能特点

1. 自动生成配置文件：根据命令行参数生成轨迹生成和后处理的 YAML 配置文件
2. 支持指定胶囊：可以通过 short_id 指定运行特定的胶囊或胶囊列表
3. 一键式流程：自动执行轨迹生成和后处理评估
4. 灵活控制：支持跳过特定阶段，如轨迹生成或后处理
5. 无侵入性实现：通过直接调用 TrajectoryGenerator 类而非修改脚本文件
6. 优化数据导出：生成精简的CSV和JSON格式评估数据，方便后续分析

## 使用方法

### 基本用法

```bash
python bixbench/start_analyse.py --run_name RUN_NAME --llm_model MODEL_NAME [选项]
```

### 必填参数

- `--run_name`: 运行名称，如 "bixbench-run-1-gpt4o"（**每次运行必须修改为新的唯一名称**）
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
python bixbench/start_analyse.py --run_name bixbench-run-gpt4o-20231015-1 --llm_model gpt-4o
```

2. 运行特定模型评测特定胶囊，并使用 MCQ 模式：

```bash
python bixbench/start_analyse.py --run_name bixbench-run --llm_model gpt-4o --capsule_mode mcq --short_ids bix-1 bix-3
```

3. 仅生成轨迹，不进行后处理：

```bash
python bixbench/start_analyse.py --run_name bixbench-run --llm_model gpt-4o --skip_postprocessing
```

4. 仅进行后处理，不生成轨迹：

```bash
python bixbench/start_analyse.py --run_name bixbench-run --llm_model gpt-4o --skip_generation
```

## 工作流程说明

1. **配置生成阶段**：脚本根据参数生成适当的 YAML 配置文件
2. **胶囊筛选阶段**：如果指定了 short_ids，脚本会筛选出对应的胶囊
3. **轨迹生成阶段**：
   - 对于特定胶囊：直接导入并使用 TrajectoryGenerator 类进行处理
   - 对于所有胶囊：调用标准的 generate_trajectories.py 脚本
4. **后处理评估阶段**：脚本运行 postprocessing.py 进行评估和可视化
5. **数据导出阶段**：生成精简的评估数据
   - CSV格式：移除了 md_notebook、md_images 和 prompt 列
   - JSON格式：结构化数据，便于程序化分析

## 技术实现

- 针对特定胶囊的运行采用了直接导入并使用 TrajectoryGenerator 类的方式，而非修改源文件
- 这种实现方式更加优雅，无侵入性，不会对原有代码产生副作用
- 优化的数据导出处理了各种数据类型，确保 JSON 序列化的兼容性

## 数据输出

评估结果将以两种格式输出到 `bixbench_results_[RUN_NAME]` 目录中：
1. **CSV格式** (`eval_df_new.csv`)：包含所有评估指标，但移除了体积较大的列
2. **JSON格式** (`eval_df_new.json`)：与CSV内容相同，但使用JSON格式，便于程序化处理

## 注意事项

- **重要**：每次运行评测时，必须修改`--run_name`参数值，避免覆盖之前的评测结果
- 确保已安装所有必要依赖，如 datasets、pyyaml 等
- 如果使用 short_ids 筛选胶囊，确保指定的 ID 存在
- 建议在运行大规模评测前，先用少量胶囊进行测试
- 结果将保存在 `bixbench_results_[RUN_NAME]` 目录中
- 对于不同的模型提供商，可能需要设置不同的API密钥环境变量 