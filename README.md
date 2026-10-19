# Fusion STEP Evaluator

独立 STEP 评分 CLI 与本地 stdio MCP 服务。输入 candidate STEP、reference STEP 和冻结标注 JSON，输出几何 validation、六项固定权重 v3 分数、测量覆盖率及完整审计文件。运行评分不需要 Autodesk Fusion、建模 CLI、模型账号或 `fusion_pipeline`。

默认协议为 `fusion-step-adapted-v3.0`。本项目复用 CADGenBench 的三项 shape 指标及几何工具，六项总分属于本地适配协议，`ranking_eligible` 保持 `false`。

**指标说明入口：[当前指标、计算公式、benchmark 来源与修改适配](docs/METRICS_AND_ADAPTATIONS.md)。** 包含六项指标及权重、validation 准入、算法公式与参数、备用路径、缺测计分示例，以及相对上游和 v2 的差异。快速规则见 [SCORING_V3](docs/SCORING_V3.md)，源码与论文证据见 [来源报告](docs/EVALUATOR_CODE_PROVENANCE.md)，服务结构见 [架构](docs/ARCHITECTURE.md)。

## 安装与 CLI

源码仓库不包含 Python runtime、参考数据或历史评测结果。已验证环境为 Windows x64 / Python 3.12。新建环境并安装依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-evaluator.txt
$env:FUSION_STEP_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
```

`evaluate.cmd` / `mcp.cmd` 的 Python 选择顺序为环境变量 `FUSION_STEP_PYTHON`、包内 `runtime/python/python.exe`、PATH 中的 `python`。环境变量填可执行文件路径，不能带额外参数。便携 ZIP 可直接使用包内 runtime，源码安装使用自己的依赖环境。

合成盒体示例无需任何私有数据：

```powershell
& $env:FUSION_STEP_PYTHON -B examples/make_box_fixture.py --output inputs/box-example
.\evaluate.cmd --cases inputs/box-example/cases.json --output outputs/box-example
```

每次 `--output` 必须是新目录。也可以直接执行 `python -B evaluate.py --cases ... --output ...`，默认 v3。CLI 保留显式 `--protocol fusion-step-adapted-v2.0` 的历史兼容；MCP 固定 v3。`--timeout` 为逐题进程树超时秒数，`--workers` 为 1–4。

manifest 格式：

```json
{
  "cases": [{
    "case": "part-001",
    "candidate": "C:/benchmark/inputs/candidate.step",
    "gt": "C:/benchmark/inputs/reference.step",
    "annotations": "C:/benchmark/inputs/annotations.json",
    "expected_hashes": {
      "candidate": "<64位SHA256>",
      "gt": "<64位SHA256>",
      "annotations": "<64位SHA256>"
    }
  }]
}
```

三个输入路径均须为绝对路径。标注还须携带 `gt_sha256`，与参考 STEP 的原始字节对应；不能为绕过校验而自动改写已有标注的哈希。标注结构可参考 [合成示例](examples/make_box_fixture.py)，支持的尺寸探针在 [dimension_probes.py](src/dimension_probes.py)。全部输入使用固定世界毫米坐标。

## MCP 使用

```powershell
New-Item -ItemType Directory inputs -Force
Copy-Item service.config.example.json service.config.json
.\mcp.cmd --config service.config.json
```

该命令通过 stdin/stdout 与 MCP 客户端通信，不启动 HTTP 服务。配置是管理员控制的 JSON；相对路径以配置文件所在目录为基准。`allowed_input_roots` 必须已存在，`output_root` 不存在时创建。可选 `python` 指定评分子进程解释器；省略时使用启动服务的解释器。示例中 `timeout_seconds=600`，最多一个活动任务；`max_active_jobs` 允许 1–4。

客户端配置示意，替换为自己的绝对路径：

```json
{
  "mcpServers": {
    "step-evaluator": {
      "command": "C:/tools/fusion-step-evaluator/runtime/python/python.exe",
      "args": ["-B", "C:/tools/fusion-step-evaluator/mcp_server.py", "--config", "C:/tools/fusion-step-evaluator/service.config.json"]
    }
  }
}
```

无内置 runtime 时将 `command` 改为自己的 Python。MCP 支持 `initialize`、`ping`、`tools/list` 和 `tools/call`，使用一行一个 UTF-8 JSON-RPC 消息。协议版本支持 `2025-06-18`、`2025-03-26`、`2024-11-05`。

|工具|参数|结果|
|---|---|---|
|`capabilities`|无|协议、权重、路径边界和并行/超时限制|
|`evaluate`|`candidate`、`gt`、`annotations` 绝对路径；可选 `case`|立即返回 `job_id`；后台启动独立评分进程|
|`status`|可选 `job_id`|单个任务状态；省略则列出本服务会话任务|
|`results`|`job_id`|任务最终状态、完整 `summary` 与报告/manifest/aggregate/log 文件路径|

`evaluate` 调用示例：

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"evaluate","arguments":{"case":"part-001","candidate":"C:/benchmark/inputs/candidate.step","gt":"C:/benchmark/inputs/reference.step","annotations":"C:/benchmark/inputs/annotations.json"}}}
```

先完成 MCP 初始化，提交后轮询 `status`，等 `completed` 或 `failed` 再读取 `results`。活动任务超限时明确返回工具错误，不静默排队。所有任务使用随机新目录，调用方不能传入命令、权重或输出路径。输入路径经解析后必须在白名单根目录中；这是一层本地调用边界，运行仍属于同一操作系统账户的可信进程。

任务索引限当前服务会话；重启后历史任务不会自动恢复或续跑，磁盘结果保留。正常 stdin 关闭时等待现有任务结束并写入状态；服务级总超时为单题限制加 60 秒。强制终止进程或断电可能留下 `running` 状态及部分证据，应人工检查，不自动重跑同一个目录。

## 输出和故障判读

每次 CLI 输出 `manifest.json`、`summary.json`、`report.md`、`comparison.csv`，每题保留 `aggregate.json`、七模块 `results/*.json`、输入快照、worker 日志、validation/参考预检和切面计划。MCP 在任务目录外层另保存 `cases.json`、`job_status.json`、`evaluator.log`。以最终 summary/aggregate 为准，`provisional.json` 是尚未通过批次完整性核验的临时结果。

`completed` 表示评分 CLI 成功结束且存在 v3 summary，并不意味着几何达到任何业务阈值。`failed` 的任务也可能有可诊断 summary。退出码 2 可能来自候选无效、完整性故障或评测无法完成，必须结合 `validation_passed`、`execution`、`reasons` 判读。通过 validation 但部分测量不可用的 v3 候选仍可能成功完成；其 `measured_score=null`、`awarded_score=0`，总分标注 `policy_lower_bound`。

参考 STEP、标注和评分结果属于评分服务端数据。需要盲评时，请把此 MCP 连接给评测角色，并单独管理建模角色可访问的资料。

## 测试、来源与分发

```powershell
$env:RUN_GEOMETRY_TESTS = '1'
& $env:FUSION_STEP_PYTHON -B -m unittest discover -s tests -v
```

测试真实 stdio 协议、配置/路径错误、无效 STEP、合成盒体和缺失尺寸测量的 v3 政策；不会调用 Fusion 或任何模型。未设置 `RUN_GEOMETRY_TESTS=1` 时两个真实有效几何用例跳过；无效 STEP 失败用例仍启动真实评测子进程。详见 [测试记录](docs/TESTING.md)。

评分入口、`src/`、精选 vendor 和权重与维护快照保持原始字节一致，见 [SOURCE_HASHES](docs/SOURCE_HASHES.json)。MCP 和启动器是独立新增文件。依赖文件列出直接版本，并非完整传递锁文件。便携包接收约定见 [PACKAGING](docs/PACKAGING.md)。本地工程代码保留权利，第三方各自许可见 [LICENSE](LICENSE) 和 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。
