# 验证记录与复现方式

日期：2026-10-19。环境：Windows x64、Python 3.12 及 `requirements-evaluator.txt` 对应的可用依赖环境。所有 CAD 输入由测试现场生成，不包含私有题库。评测服务实现前先执行握手验收，因服务文件尚不存在而失败；实现后运行以下完整测试。

```powershell
$env:RUN_GEOMETRY_TESTS = '1'
python -B -m unittest discover -s tests -v
```

最终一次测试结果：**9 tests，0 failures，0 errors，0 skipped，14.330 秒**。

|验证内容|实际结果|
|---|---|
|禁用 site-packages 的独立解释器握手|通过；协议服务仅依赖标准库|
|initialize、tools/list、capabilities、ping|通过；四个工具可发现|
|无效配置|非零退出、错误仅写 stderr|
|无效 STEP 的真实子进程执行|任务 failed，保存日志与最终失败 summary，无虚构得分|
|越界路径、相对路径、缺失文件、额外输出参数、非法 case、标注 GT 哈希不符|拒绝且不创建任务|
|未初始化调用、畸形 JSON、无效请求、未知方法、错误参数|返回对应协议/工具错误，正常会话仍可继续|
|孤立高/低 Unicode 代理字符及正常中文/emoji 请求 ID|回包 ID 保真，随后 ping 正常；输出 JSON 转义防止 UTF-8 编码异常终止服务|
|真实 OCCT 10×20×30 盒体对自身|综合分 1.0、测量权重覆盖 1.0；七模块原始记录与完整报告存在；输入字节未变|
|真实盒体使用不支持的尺寸探针|综合分 .75；dimension 实测为 null、授分 0；总分 policy_lower_bound|

完整盒体用例还检查活动任务上限，以及运行中不可提前读取最终结果。正常完成后的 `results` 返回完整 summary 与持久文件路径。

Unicode 回归测试先在修复前复现 `UnicodeEncodeError` 导致服务退出，再仅调整 MCP 外层回包 JSON 转义，重跑以上完整九项测试。评分核心、权重和算法未改动。

另行实际运行两个 CMD 启动器：

- `evaluate.cmd` 使用环境变量指定的 Python，从包含空格的输入路径读取 manifest，并在包含空格的新输出目录产生盒体分数 1.0；代码及原始输入完整性均通过。
- `mcp.cmd --config <带空格的配置路径>` 使用环境变量指定的 Python，连续返回 initialize、tools/list、capabilities 的三条合法 JSON-RPC 响应，无评分文本污染 stdout。
- 34 项来源文件逐字节对比维护快照并核对 SHA256：全部一致；其中 12 个本地 Python 文件、13 个精选 vendor Python 文件。

测试产生的 STEP、结果与未脱敏原始日志保留在本地忽略目录 `.validation/`，不提交到源码仓库。普通测试用临时目录并在结束时清理。未设置 `RUN_GEOMETRY_TESTS=1` 会跳过两个有效几何用例，因此快速测试通过不能代替上述完整验收。

这些结果验证独立源码服务和配置 Python 启动器；尚未声称新组装的便携 ZIP 已验收。内置 runtime、迁移解压和完整分发清单由发布构建器按 [PACKAGING](PACKAGING.md) 另行验证。运行不涉及 Fusion、模型 CLI、账号或历史评测数据。
