# 便携包接收约定

源码仓库仅包含源码、测试、文档和必要许可，不提交 runtime、大型依赖、私有数据、运行结果或认证信息。

发布构建器可使用已提交的仓库文件，再加入已验证的 Windows x64 Python 3.12 runtime。解释器位置必须为 `runtime/python/python.exe`，以便现有两个 CMD 启动器直接找到。源代码文件仍保持原样，不为了便携化改写算法。

分发包同时保留 `runtime.lock.json`、完整依赖许可证、`licenses/inventory.json`、CPython 许可及原始包内部的 license/NOTICE/COPYING 文件。若 runtime 复用共享依赖集合，应明确其中可能有本评分服务未使用的依赖；这些额外库不意味着依赖 Fusion、模型 CLI 或流水线。CADGenBench 原始许可和 OCCT LGPL 2.1 + exception 必须保持可读。

发布构建器对所有最终文件产生 SHA256 清单/manifest，压缩后重新核对 ZIP 内容。`docs/SOURCE_HASHES.json` 验证算法来源字节，发布清单验证最终分发字节；两者目的不同。打包必须从受控源码文件集读取，不能递归复制工作目录中的 `inputs/`、`outputs/`、`.validation/`、venv 或已有 runtime。

便携验收应从含空格的新解压目录执行以下动作：

1. 使用内置 Python 生成 `examples/make_box_fixture.py` 的盒体。
2. 用 `evaluate.cmd` 在新目录完成 v4 geometry 评分（另验显式 v3 兼容），确认全测、分数接近 1.0。
3. 使用 `mcp.cmd --config ...` 验证初始化和工具目录，完成一次 MCP 评分及结果读取。
4. 校验完整许可清单、算法来源哈希、包文件清单及未携带私有输入/凭据。

本仓库服务测试不等于新便携 ZIP 已通过以上验收；最终 ZIP 应附自己的构建和验收记录。
