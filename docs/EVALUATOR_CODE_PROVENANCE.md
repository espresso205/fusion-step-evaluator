# STEP 评测器代码与指标来源报告

核对日期：2026-10-19。本报告从维护端同日的 `EVALUATOR_CODE_PROVENANCE_20261019.md` 移植整理，范围为独立评分服务的默认 `fusion-step-adapted-v3.0` 及保留的 v2 CLI。移除了维护机绝对路径、私有运行记录和跨 CLI 编排信息；原评分实现保持原始字节，复制清单见 [SOURCE_HASHES.json](SOURCE_HASHES.json)。

## 1. 主要结论

1. **shape 的体积 IoU、Surface Distance F1、Topology Match 直接复用 CADGenBench 官方实现。** 本地把三项取均值，再以 30% 权重加入六项总分；这不是 CADGenBench 官方 CAD Score。
2. distance 复用 CADGenBench 的 STEP 加载与表面采样，双向最近采样点距离 p99 的指数评分由本地协议定义，没有调用 DeepCAD 或 CADBench 的 Chamfer 评分器。
3. v3 validation、dimension、mass、face_match、section 的验证/计分流程由本项目实现，调用 OCCT/OCP、SciPy、Open3D、trimesh 等计算库，并在部分路径复用 CADGenBench 网格/采样工具。工具来源不等于整个指标来源。
4. 六项权重、通过 validation 后参与计分、缺失测量保守授分及证据合同属于本地规则。新 stdio MCP 只包装原评测入口，不修改算法。

“本项目实现”表示代码与评分规则的维护归属，不主张基础数学方法具有学术原创性。

## 2. 调用链和来源总表

实际分派入口为 [worker.run_v3](../worker.py#L14)，聚合规则在 [contract_v3.py](../src/contract_v3.py) 和 [weights_v3.json](../weights_v3.json)。validation 单列为准入检查，六项固定权重总分为：

```text
S = .30 shape + .25 dimension + .15 distance + .10 mass + .10 face_match + .10 section
```

|模块|当前执行函数|来源与复用边界|
|---|---|---|
|validation|`src.robust_metrics.validity`|本地 OCCT BRep、闭壳、正体积、自交、实体干涉和残留几何检查；不是 CADGenBench validity 的直接准入结论|
|shape|`src.metrics.shape`|CADGenBench `compare_step_files(align=False)` 和 `topo_match`；三项均值和固定坐标由本地规定|
|dimension|`src.metrics.dimension`|本地标注探针和 OCP；未复用其他论文的尺寸评分器|
|distance|`src.metrics.distance`|CADGenBench `sample_surface_points` / `_load_occ_shape`、SciPy KDTree；本地 p99 和指数映射|
|mass|`src.robust_metrics.mass`|本地误差映射；OCCT 积分，CADGenBench 网格化和 trimesh 备用质量属性|
|face_match|`src.robust_metrics.face_match`|本地有限曲面覆盖 F1；CADGenBench 网格/面积采样、Open3D 最近面查询|
|section|`src.robust_metrics.section`|本地双侧截面和误差映射；OCCT 剖切，CADGenBench/trimesh 同平面备用|

## 3. CADGenBench 固定版本

上游为 [huggingface/cadgenbench](https://github.com/huggingface/cadgenbench/tree/33304cf771fc5639144b1df9611e347251052cf8)，commit `33304cf771fc5639144b1df9611e347251052cf8`。本仓库精选 [vendor/cadgenbench](../vendor/cadgenbench) 中 13 个 Python 文件，与维护快照及已核对的该固定提交字节一致；同时保留 [LICENSE](../vendor/cadgenbench_LICENSE) 和 [pyproject 元数据](../vendor/cadgenbench_pyproject.toml)。具体文件 SHA256、大小及来源见 [复制清单](SOURCE_HASHES.json)。

此处是**未修改的上游源码 + 本地适配/聚合**。`pyproject` 中的 `0.1.0` 不足以单独标识版本。`licenses/UPSTREAM_SOURCES.json` 仅记录 OCCT/Apache 许可文本来源，不替代源码版本清单。本次确认的是官方仓库及指标文档，未确认与该版本对应的正式 CADGenBench 论文 DOI/arXiv，因此引用仓库和 commit，不补写未经核对的论文。

### 3.1 直接复用的三个 shape 指标

|指标|固定版本代码|含义|
|---|---|---|
|体积 IoU|[shape_similarity.py](https://github.com/huggingface/cadgenbench/blob/33304cf771fc5639144b1df9611e347251052cf8/src/cadgenbench/eval/shape_similarity.py#L605)、[booleans.py](https://github.com/huggingface/cadgenbench/blob/33304cf771fc5639144b1df9611e347251052cf8/src/cadgenbench/eval/booleans.py#L114)|三角网格实体交集体积 / 并集体积；底层 manifold3d，不是精确 BRep 等价认证|
|Surface Distance F1|[shape_similarity.py](https://github.com/huggingface/cadgenbench/blob/33304cf771fc5639144b1df9611e347251052cf8/src/cadgenbench/eval/shape_similarity.py#L524)|每侧 50,000 面积采样点、seed 0；点到另一网格表面的距离和法向通过率形成双向 F1|
|Topology Match|[topo_match.py](https://github.com/huggingface/cadgenbench/blob/33304cf771fc5639144b1df9611e347251052cf8/src/cadgenbench/eval/topo_match.py#L159)|按网格估计 Betti 数，对各维平滑比值惩罚相乘|

Surface F1 的距离门限为 `max(1e-6 mm, .005 D_GT)`，法向实际代码使用 `abs(dot) > cos(20°)`，即不区分法向正反；不能把注释中的方向性描述当作实际逻辑。Topology 分项为 `exp(-2 abs(log((b_candidate+1)/(b_GT+1))))`，各维相乘；网格拓扑估计不等于完整 CAD 语义证明。

本地 [metrics.shape](../src/metrics.py#L239) 为 `(IoU + SurfaceF1 + Topology) / 3`。上游 [官方总分](https://github.com/huggingface/cadgenbench/blob/33304cf771fc5639144b1df9611e347251052cf8/src/cadgenbench/eval/evaluate.py) 对生成任务组合 `0.4 shape_similarity + 0.4 interface + 0.2 topology`，缺轴重归一，并包含刚体对齐。这与本地固定世界坐标、未计 Interface Match、缺失不重归一的六项总分不同。本地 `align=True` 只生成诊断，不计入最终分数。

当前 [StepArtifacts](../vendor/cadgenbench/common/artifacts.py) 缓存可能优先使用各模型自身 bbox 决定的网格精度，不能仅依据上游注释就声称全部比较都用同一 GT 挠度。精选 vendor 保留解析、网格、采样、拓扑、布尔和诊断对齐工具；未携带官方全流程总分、Interface Match、LLM baseline 或报告模块。

## 4. 本地指标与底层算法边界

### 4.1 validation 和 dimension

[robust_metrics.validity](../src/robust_metrics.py#L155) 本地组合 `BRepCheck_Analyzer`、闭壳、正体积、`BOPAlgo_ArgumentAnalyzer` / `BOPAlgo_SelfIntersect`、`BRepAlgoAPI_Common` 等检查。正常接触和正体积干涉分开处理；检测故障不冒充已确认无效。v3 不依赖 CADGenBench validity 决定准入，shape 后端仍可能运行上游网格校验。

[metrics.dimension](../src/metrics.py#L123) 为通过标注项数 / 总项数；[dimension_probes.py](../src/dimension_probes.py) 覆盖圆柱直径与阵列、环面、圆锥、平面间距。探针来自本地旧 STEP 尺寸工具和 OCP 遍历方式，不是 DeepCAD/CADBench 官方参数准确率。当前 GT 派生探针、圆柱面计数不等于独立图纸/GD&T 真值或语义孔数。

### 4.2 distance

[metrics.distance](../src/metrics.py#L219) 借用每侧 50,000 点、seed 0 的 CADGenBench 采样，以 SciPy KDTree 计算双向点到采样点距离：

```text
p99_sym = max(percentile99(d_GT→candidate), percentile99(d_candidate→GT))
tau = max(1e-6 mm, .005 D_GT)
distance_score = exp(-p99_sym / (10 tau))
```

尺度借用 Surface F1 思路，p99、10 倍软化及指数映射是本地规则。`(mean_AB+mean_BA)/2` 及双向均值之和只作诊断，不是此分的公式。p99 不是严格最大 Hausdorff；点到采样点有采样噪声，与 shape 的点到网格 Surface F1 路径不同。

### 4.3 mass

[robust_metrics.mass](../src/robust_metrics.py#L282) 使用：

```text
eV = abs(V_candidate-V_GT) / V_GT
eI = max_i(abs(lambda_candidate,i-lambda_GT,i) / lambda_GT,i)
mass_score = exp(-(eV+eI)/.1)
```

lambda 为排序后的质心主惯性矩。质心位置不加权，单位密度几何质量属性不代表材料重量。误差尺度和指数映射是本地规则。v3 依次尝试 OCCT 自适应积分、Gauss–Kronrod、逐级闭合网格积分，检查本地收敛预算。备用网格来自 CADGenBench，属性由 trimesh 计算，非无误差真值。

trimesh `triangles.mass_properties` 明确引用 David Eberly 的 [Polyhedral Mass Properties (Revisited)](https://www.geometrictools.com/Documentation/PolyhedralMassProperties.pdf)。已核对文档首页：Geometric Tools，创建 2002-12-31、修订 2009-11-03，当前文档为 CC BY 4.0。它属于通过依赖间接复用的底层多面体积分资料，**不是本地指数评分公式或 CAD benchmark 指标的来源**。

### 4.4 face_match

[robust_metrics.face_match](../src/robust_metrics.py#L306) 对完整有限曲面面积采样，距离 ≤ .05 mm、`abs(dot) ≥ cos(5°)` 的双向比例形成 F1。每侧每 seed 20,000 点，seed 0/1 的两次 F1 取平均。复用 CADGenBench 网格化和 `smooth_normals=False` 面法向采样，本地 Open3D 查询最近三角面。

它使用与 Surface F1 相同一类“距离 + 法向 + 双向 F1”思想，但公差、样本数、双种子、法向和调用路径属于本地版本，未直接调用上游 F1 函数；不是 Interface Match，也不再是 v2 的 BRep 面一一计数。它与 shape 有相关性，六项不能宣称完全独立。

### 4.5 section

[robust_metrics.section](../src/robust_metrics.py#L457) 在标注 h 两侧比较 `h ± delta`，`delta=max(.001 mm, 1e-5 D_GT)`，切面计划仅由参考冻结：

```text
score_side = exp(-(relative_area_error+relative_perimeter_error)/.05)
             * (contour_counts_equal ? 1 : .5)
section = 每个标注两侧先平均，再对标注平均
```

空截面有显式判定。原 [section.py](../src/section.py) 调用 OCCT 剖切和积分；失败时在**同一平面**使用 CADGenBench 网格化/trimesh 切面并检查细化收敛。切面选择、环组织、误差映射、轮廓惩罚和平均由本项目实现。该分比较面积、周长和轮廓数，不证明截面逐点相等。

## 5. 历史调研项目与当前代码区分

|项目|固定来源与论文|当前 v3 官方评分器复用|
|---|---|---|
|DeepCAD|[f7b3507](https://github.com/rundiwu/DeepCAD/tree/f7b350790a3bce0267a5345339fd09be0250c8cb)、[2105.09492](https://arxiv.org/abs/2105.09492)|无；当前无 CAD 命令序列准确率，distance 不调用其 Chamfer|
|CADBench|[99e41a2](https://github.com/anniedoris/CADBench/tree/99e41a2eeb351f04611e83980f9f23cb0ca216c7)、[2605.10873](https://arxiv.org/abs/2605.10873)|无；本项目 IoU 来自 CADGenBench，未计建模操作数|
|JoinABLe|[5a3b993](https://github.com/AutodeskAILab/JoinABLe/tree/5a3b9933e91269d19b6cc733b244a879eb4bfc30)、[2111.12772](https://arxiv.org/abs/2111.12772)|无；实体干涉验证不是 joint 预测准确率|
|MechVQA|[c8d6151](https://github.com/xiaofengShi/MechVQA/tree/c8d61513aef05b4f5d117bb0c6d1a055451d6f33)、[2605.30794](https://arxiv.org/abs/2605.30794)|无；未运行问答投票评分|

以上项目曾被历史调研/独立实验涉及，并不属于本服务依赖。DeepCAD Chamfer 是双向最近距离平方均值之和，CADBench 对应函数是未平方距离均值之和；本地诊断量名称相近或公式相同不表示继承了这些函数的代码来源。

## 6. v2 与 v3 差异

|模块|保留的 v2|默认 v3|
|---|---|---|
|validity|基本 BRep + CADGenBench artifacts 网格检查|本地 OCCT 完整门禁，与测量网格失败分开|
|shape/distance/dimension|`src.metrics`|同一实现，未更换公式|
|mass|既有 OCCT 积分和稳定性门控|更多积分/网格备用，指数公式等价保留|
|face_match|解析面类型与门限、SciPy 一一匹配、面计数 F1|有限曲面面积覆盖 F1，语义已变化|
|section|标注单平面，异常阻断|参考双侧切面和同平面备用，局部映射保留|
|总分|完整资格和测量门控|validation 通过且证据有效即参与，缺失测量明确保守授分|

不能把两版直接当成同一指标体系。缺失测量保持 `measured_score=null`、计入 `awarded_score=0`，标记 `policy_lower_bound` 并报告覆盖率；这不是虚构实测零分。

## 7. 依赖与许可

[requirements-evaluator.txt](../requirements-evaluator.txt) 锁定直接依赖：build123d 0.10.0、cadquery-ocp 7.8.1.1.post1、VTK 9.3.1、NumPy 2.5.4、SciPy 1.18.1、trimesh 5.1.1、manifold3d 3.5.4、Open3D 0.20.0。它不是完整传递锁文件。CADGenBench 为随仓库 Apache-2.0 vendor；其他库是 CAD/数值/网格计算依赖，不自动构成对其论文指标的复用。

许可文本与 native OCCT 区分见 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)。可选便携 ZIP 的实际运行时版本和完整许可清单由自身的 `runtime.lock.json` 与 `licenses/inventory.json` 记录，不能把 source-only 仓库描述为已携带这些二进制。

对外应称“复用 CADGenBench 部分指标和工具的 STEP v3 适配评分服务”；不称 CADGenBench 官方完整评分器或论文排行榜复现。更换源码、阈值、采样、权重或执行路径时，应同时更新协议及本报告。
