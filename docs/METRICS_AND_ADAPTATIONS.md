# 当前评测指标、计算公式与来源适配

核对日期：2026-10-19。适用协议：**`fusion-step-adapted-v3.0`**，即当前 CLI 默认协议和 MCP 唯一评分协议。本文按本仓库实际代码编写；评分实现与 `v1.0.0` 发布标签一致。本次补充文档，没有修改算法、参数或权重。v2 仅作为差异说明，不混入当前公式。

## 1. 评测了什么

输入为候选 STEP、参考 STEP（GT）、绑定 GT SHA256 的冻结标注；输出为一项几何准入检查和六项分数。评的是**交付几何与参考的符合程度**，不评 Fusion 操作步骤、特征树质量、建模速度、代码风格或语言模型回答。

|模块|衡量内容|权重|指标/代码来源|本地修改或适配|
|---|---|---:|---|---|
|validation / 输出键 `validity`|候选 BRep、闭壳、正体积、自交、实体间干涉、残留几何|不加权|本地流程，调用 OCCT/OCP|与测量资格解耦；检测器失败与确认无效分开|
|shape|体积 IoU、表面 F1、拓扑一致性|30%|三项直接复用 CADGenBench|固定世界坐标；三项等权平均为本地 shape；未复用其官方总分|
|dimension|冻结尺寸探针的通过率|25%|本地 BRep 探针，调用 OCP|参考自检、按标注项计数；不是官方参数序列准确率|
|distance|双向采样距离的 p99 尾部偏差|15%|CADGenBench 加载/采样；本地距离聚合与映射|两个方向 p99 取最大值，再指数映射；不是 DeepCAD Chamfer|
|mass|体积和质心主惯性矩相对误差|10%|本地评分；OCCT 积分、trimesh 备用积分|保留误差公式，增加积分路径与经验收敛检查|
|face_match|有限曲面的双向面积覆盖|10%|本地 F1；复用 CADGenBench 采样/网格工具，调用 Open3D|0.05 mm、5°、双种子；替换 v2 的逐 BRep 面匹配|
|section|标注附近双侧截面的面积、周长、环数|10%|本地算法，调用 OCCT、CADGenBench 网格工具和 trimesh|GT 冻结双侧平面；同平面备用；逐侧评分后平均|

直接复用的 benchmark 是 **[Hugging Face CADGenBench](https://github.com/huggingface/cadgenbench/tree/33304cf771fc5639144b1df9611e347251052cf8)**，固定 commit 为 `33304cf771fc5639144b1df9611e347251052cf8`。本仓库保留 13 个未修改的上游 Python 文件及 Apache-2.0 许可，见 [vendor](../vendor/cadgenbench)、[来源哈希](SOURCE_HASHES.json)。CADGenBench 与 `anniedoris/CADBench` 是两个不同项目。

其余指标的“本地实现”表示代码和评分规则在本项目维护，不表示基础数学方法具有学术原创性。底层几何库的使用不等于直接复用了某篇 benchmark 论文的指标。完整上游、论文和许可证据见[代码来源报告](EVALUATOR_CODE_PROVENANCE.md)。

## 2. 记号、坐标与总分

- $G$：参考几何；$C$：候选几何；$\mathbf{1}[\cdot]$：条件成立时为 1，否则为 0。
- 长度按毫米解释。OCCT 读取器做 STEP 声明单位到毫米的转换；这不构成对候选的最佳拟合缩放。
- 计分使用固定世界坐标，不为提升分数平移、旋转、镜像或缩放。shape 另外生成的对齐结果只作诊断。
- 各项实测分 $s_i\in[0,1]$，JSON 保存 0–1，报告显示 $100S$。
- $D_G$ 表示相应路径使用的 GT 包围盒对角线。实现并非所有模块都使用相同的包围盒算法：distance 使用 `Add_s`，v3 robust 模块使用 `AddOptimal_s`，shape 使用 CADGenBench measurements；应以该模块实际记录的尺度为准。

默认权重来自 [weights_v3.json](../weights_v3.json)：

$$
S=0.30a_{\mathrm{shape}}+0.25a_{\mathrm{dimension}}+
0.15a_{\mathrm{distance}}+0.10a_{\mathrm{mass}}+
0.10a_{\mathrm{face}}+0.10a_{\mathrm{section}}.
$$

$a_i$ 是最终授分：测量可用时等于 $s_i$，不可用时按第 10 节政策取 0。validation 没有加权项。六项权重是本地设计，未做独立的人类质量评分拟合或排行榜校准，`ranking_eligible=false`。

## 3. validation：候选几何准入

实现：[robust_metrics.validity](../src/robust_metrics.py#L155)、[_validate_shape](../src/robust_metrics.py#L89)。

读取候选后检查：至少一个实体；所有 shell/face/edge/vertex 均归属于实体；每个实体 BRep 检查通过、至少一个壳且所有壳闭合、体积有限且严格大于 0、包围盒有限。随后用 `BOPAlgo_ArgumentAnalyzer` 检查实体自交，用 `BRepAlgoAPI_Common` 检查实体间正体积交叠。

对体积为 $V_i,V_j$ 的实体：

$$
t_{ij}=\max(10^{-7}\ {\rm mm}^3,\ 10^{-9}\min(V_i,V_j)).
$$

仅当交集体积 $V_{i\cap j}>t_{ij}$ 时判为干涉。仅接触或不超过阈值的交叠不被这条规则拒绝。包围盒在任一轴没有正长度交叠时跳过该对布尔；布尔/检测器失败记为评测错误，不能等同于“已经证实模型无效”。

**候选验证和参考验证分开。** 先检查候选，再检查 GT；候选已通过时，即使后续 GT 无效或 GT 验证出错，候选仍可进入评分，各项参考测量能否完成另行判断。候选确认无效、候选验证未完成或身份/哈希证据不一致时不放行。这里的检查集合不是对所有 CAD 缺陷的数学完备性证明。

来源与适配：本地 OCCT 准入流程，不直接沿用 CADGenBench 网格 validity 作为候选准入结论。与旧流程相比，避免健康 BRep 仅因某个评分网格失败就被当作无效候选；不自动修复或修改提交几何。

## 4. shape：体积、表面与拓扑的等权平均

实现：[metrics.shape](../src/metrics.py#L239)。设体积 IoU 为 $I$，表面 F1 为 $F$，拓扑分为 $T$：

$$
s_{\mathrm{shape}}=\frac{I+F+T}{3}.
$$

这三项各占本地总分最多 10 分。三项须全部得到有效结果；若其中任何一项失败，当前适配器将整个 shape 记为不可测，不将其余子项重归一。原始结果保留在 `results/shape.json`。

### 4.1 体积 IoU

直接复用 [CADGenBench shape_volume_iou](../vendor/cadgenbench/eval/shape_similarity.py)：

$$
I=\frac{V(G\cap C)}{V(G\cup C)}
=\frac{V(G\cap C)}{V(G)+V(C)-V(G\cap C)}.
$$

这里的体积来自三角网格经 manifold3d 的布尔和积分，不是直接对精确 BRep 求交的证明。要求两侧和并集体积为正，最终限制在 $[0,1]$。

### 4.2 Surface Distance F1

直接复用 [CADGenBench 表面 F1](../vendor/cadgenbench/eval/shape_similarity.py#L524)。两侧各按面积抽样 $N=50{,}000$ 点，seed=0。对样本 $p$，寻找另一侧**网格表面**最近点 $q(p)$，门限为：

$$
\tau=\max(10^{-6}\ {\rm mm},\ 0.005D_G),\qquad
H(p)=\mathbf{1}[\|p-q(p)\|_2\le\tau\ \land\
|\hat n_p\cdot\hat n_{q(p)}|>\cos20^\circ].
$$

$$
P=\frac1N\sum_{p\sim C}H(p),\quad
R=\frac1N\sum_{p\sim G}H(p),\quad
F=\begin{cases}\frac{2PR}{P+R},&P+R>0\\0,&P+R=0.\end{cases}
$$

采样点法向使用上游平滑法向路径。代码使用绝对点积，法向正反视为等价；不能依据注释将它称为有向法向判定。点到网格距离也不同于第 6 节的点到采样点距离。

### 4.3 Topology Match

直接复用 [CADGenBench topo_match](../vendor/cadgenbench/eval/topo_match.py#L159)。网格估计三个 Betti 数：$b_0$ 为连通实体分量数，$b_1$ 为独立贯穿通道/柄数，$b_2$ 为内部封闭空腔数。

边界网格的欧拉特征为 $\chi_\partial=N_V-N_E+N_F$。实现根据壳的包含关系估计 $b_0,b_2$，并以 `b1 = b0 + b2 - chi_surface // 2` 恢复 $b_1$。在满足假设的闭合流形上对应 $b_1=b_0+b_2-\chi_\partial/2$。

$$
t_k=\exp\left(-2\left|\log\frac{b_k^C+1}{b_k^G+1}\right|\right),\qquad
T=\prod_{k=0}^{2}t_k.
$$

负 Betti 计数被该实现判为对应分项 0。相同 Betti 数可得到拓扑满分，但不证明形状、拓扑嵌入或 CAD 语义完全相同。

### 4.4 相对 CADGenBench 的适配

- 上游三个函数保持原字节；本地将 Topology 与 IoU/F1 放入同一个 shape 平均。
- 上游生成任务 CAD Score 是 `0.4 × shape_similarity + 0.4 × interface + 0.2 × topology`，缺失轴重归一；本项目没有调用该总分，也没有纳入 Interface Match。
- 本地强制 `align=False` 计算正式分数；`align=True` 的额外结果仅用于解释姿态误差。
- 上游 `metric_errors` 被本地提升为 shape 测量不可用，再由 v3 授分政策处理，不把上游异常临时填入的 0 伪装成可信测量。
- 当前 `StepArtifacts` 缓存路径可能按各模型自身对角线决定挠度；不能声称候选和 GT 在所有调用路径上严格使用相同挠度。上游基础挠度函数为 `clip(0.001 × D, 0.005 mm, 0.5 mm)`，实际网格路径还可能细化，见 [artifacts](../vendor/cadgenbench/common/artifacts.py) 与 [mesh](../vendor/cadgenbench/common/mesh.py)。

## 5. dimension：冻结尺寸探针的通过率

实现：[metrics.dimension](../src/metrics.py#L123)、[dimension_probes](../src/dimension_probes.py)。对 $M$ 个标注项：

$$
s_{\mathrm{dimension}}=\frac1M\sum_{j=1}^{M}\mathbf{1}[\text{候选通过标注项 }j].
$$

每项等权，通过为 1、失败为 0；没有按尺寸误差大小连续扣分。先在 GT 上运行相同探针，要求标注非空、id 唯一、类型受支持且 GT 全部通过；否则该模块不可测，不以候选几何不合格解释。

|探针|实际检查与公式|需要注意|
|---|---|---|
|`cylinder`|筛选 `abs(2r − nominal) ≤ tol` 的圆柱面，并要求数量等于 `count`|计数是 BRep 圆柱面数，不一定是孔数|
|圆柱可选阵列|`pattern_radius` 检查轴定位点的 XY 径向距离；`pattern_positions` 比较 XY 点两两距离多重集；默认 `pattern_tol=0.1 mm`|不逐点做唯一位置匹配；可选 `centroid_within` 限制 XY 均值到世界原点距离；不检查全部轴向/深度|
|`torus`|筛选小半径接近 `minor_nominal` 的环面，再检查小/大半径容差及数量|实现分别取筛选集合小/大半径的最小值，不是语义圆角特征的一一配对|
|`cone`|检查半锥角（度）满足 `abs(angle − nominal) ≤ tol`，并检查数量|不是完整倒角位置或边拓扑匹配|
|`plane_pair`|筛选法向与指定轴绝对点积 ≥ cos(5°) 的平面；从质心轴向投影差中选最接近标称距离的一对，检查尺寸容差|可选 `near/near_radius` 筛选面质心；没有强制唯一面配对|

找不到容差内圆柱/环面/锥面时的最近值关联用于诊断，最终仍须通过原容差和数量条件。当前十题使用 GT 派生探针，`annotation_kind=gt_derived_probe`；它不是独立人工图纸、公差链或完整 GD&T 真值。

来源与适配：本地实现，复用 OCP BRep 遍历与解析曲面属性；没有复用 DeepCAD/CADBench 的命令序列或参数准确率评分器。参考自检和 GT 哈希绑定用于避免把错标注误算为候选错误。

## 6. distance：双向 p99 采样距离

实现：[metrics.distance](../src/metrics.py#L219)。CADGenBench `sample_surface_points` 对每侧按面积抽样 $N=50{,}000$，seed=0，采样路径默认线挠度 0.1 mm、角挠度 0.5 rad。使用 SciPy `cKDTree` 求最近采样点距离：

$$
d_{G\to C}(p)=\min_{q\in P_C}\|p-q\|_2,\qquad
d_{C\to G}(q)=\min_{p\in P_G}\|q-p\|_2.
$$

$$
d_{99}=\max\left(Q_{0.99}(d_{G\to C}),Q_{0.99}(d_{C\to G})\right),\qquad
\tau=\max(10^{-6}\ {\rm mm},0.005D_G),
$$

$$
s_{\mathrm{distance}}=\exp\left(-\frac{d_{99}}{10\tau}\right).
$$

例如 $d_{99}=10\tau$ 时，该项约为 0.3679。p99 对极少数最远点比最大距离宽容，但不等于最大 Hausdorff 距离。

来源与适配：加载和采样来自 CADGenBench；p99、两个方向取最大、10 倍软化及指数映射是本地规则。借用了上游表面 F1 的尺度思想，没有调用其 F1 函数计分，也没有调用 DeepCAD/CADBench Chamfer。输出中的 `symmetric_mean_cd1_mm`（双向均值的平均）、`bidirectional_mean_sum_mm`、p95、max 都是诊断量，不进入总分。

这里比较采样点集合，存在表示方式和随机采样造成的噪声底；固定 seed 不保证几何等价但三角划分不同的模型距离为零。没有实施噪声偏差校正。

## 7. mass：体积与质心主惯性矩

实现：[robust_metrics.mass](../src/robust_metrics.py#L282)。取单位密度下的体积 $V$ 与质心惯性张量的三个升序特征值 $\lambda_1,\lambda_2,\lambda_3$：

$$
e_V=\frac{|V_C-V_G|}{V_G},\qquad
e_I=\max_{i=1,2,3}\frac{|\lambda_{C,i}-\lambda_{G,i}|}{\lambda_{G,i}},
\qquad
s_{\mathrm{mass}}=\exp\left(-\frac{e_V+e_I}{0.1}\right).
$$

分母为 0.1；它与 v2 的 $\sqrt{\exp(-e_V/0.05)\exp(-e_I/0.05)}$ 等价。质心位移和主轴方向不参与该分；因此该项单独不能识别整体平移或旋转。它衡量几何质量属性，不是材料实际重量。

### 测量与备用路径

依次尝试：

1. OCCT 自适应 Gauss 积分，`eps=1e-6` 与 `1e-8`。
2. 未接受时尝试 OCCT Gauss–Kronrod，同样两个 eps。
3. 再尝试 CADGenBench 网格化加 trimesh 闭合多面体积分；对当前被测模型自身 $D$，采用 $d_k=\max(10^{-5}\ {\rm mm},D f_k)$，其中 $f_k=10^{-4},5\times10^{-5},2.5\times10^{-5},1.25\times10^{-5}$。

两次测量 $a,b$ 需同时满足：

$$
\frac{|V_a-V_b|}{V_b}\le10^{-6},\quad
\max_i\frac{|\lambda_{a,i}-\lambda_{b,i}|}{\lambda_{b,i}}\le10^{-6},\quad
\|c_a-c_b\|_2\le\max(10^{-8}\ {\rm mm},10^{-6}D).
$$

网格路径要求 `trimesh.is_volume`，使用局部原点降低大世界坐标下的消减误差。GT 或候选任一侧未收敛，则整个 mass 不可测；有限估计只存为 `score_estimate_diagnostic_only`。成功结果仍标记近似，细化差不是严格数值误差界。

来源与适配：误差组合和指数分属于本地规则；OCCT 为主积分后端，CADGenBench 仅提供网格工具。trimesh 的多面体积分间接引用 David Eberly 的 [Polyhedral Mass Properties (Revisited)](https://www.geometrictools.com/Documentation/PolyhedralMassProperties.pdf)，该资料不是本地 benchmark 评分公式来源。v3 的主要变化是备用路径和收敛证据，而非权重或指数公式。

## 8. face_match：有限曲面双向面积覆盖

实现：[robust_metrics.face_match](../src/robust_metrics.py#L306)。双方共用 GT 确定的线挠度：

$$
d_{\rm mesh}=\max(10^{-5}\ {\rm mm},\min(0.05/8\ {\rm mm},2\times10^{-5}D_G)).
$$

seed $s\in\{0,1\}$ 下，每侧各抽 $N=20{,}000$ 个面积加权样本，用 Open3D 找到另一网格表面的最近点：

$$
H_s(p)=\mathbf{1}[\|p-q(p)\|_2\le0.05\ {\rm mm}\ \land\
|\hat n_p\cdot\hat n_{q(p)}|\ge\cos5^\circ].
$$

$$
P_s=\frac1N\sum_{p\sim C}H_s(p),\quad R_s=\frac1N\sum_{p\sim G}H_s(p),\quad
F_s=\begin{cases}\frac{2P_sR_s}{P_s+R_s},&P_s+R_s>0\\0,&P_s+R_s=0.\end{cases}
\qquad s_{\mathrm{face}}=\frac{F_0+F_1}{2}.
$$

使用三角面法向，`smooth_normals=false`，绝对点积使正反方向等价。未使用逐面语义标注，`ann` 参数不参与计算。

来源与适配：采用与 Surface F1 相同一类距离/法向/双向 F1 思路，但没有直接调用 CADGenBench 的完整 F1 函数；仅复用其网格和采样工具。相较 shape 内的 F1，本项使用固定毫米公差、5°、20,000 点、两个 seed、平面片法向及本地最近表面查询。

v2 的 face_match 是解析 BRep 面匹配与面计数 F1；v3 改为对完整有限曲面区域采样，减少只比较无限解析支撑面或面拆分数量造成的语义偏差。它不是 CADGenBench Interface Match。

当前只有**一个网格挠度和两个随机种子**，没有执行此项的逐级网格收敛检查。输出的两次 F1 最小/最大值只是种子敏感性范围，不是置信区间。`unassessed_area_fraction=0` 表示没有预先排除曲面类别，不表示有限采样检查了每一点。此项与 shape 有相关性，不能认为六项完全独立。

## 9. section：参考冻结的双侧截面

实现：[build_section_plan](../src/robust_metrics.py#L356)、[section](../src/robust_metrics.py#L457)。标注必须非空、id 唯一、轴为 x/y/z、offset 为有限且非布尔的数；不满足时该模块不可测。对每个标注轴和偏移 $h_j$，只根据 GT 决定：

$$
\delta=\max(10^{-3}\ {\rm mm},10^{-5}D_G),\qquad
h_j^-=h_j-\delta,\quad h_j^+=h_j+\delta.
$$

计划记录 GT SHA256，并与重新按 GT 生成的计划核对一致。两侧分别比较候选和 GT 的同一平面，不根据候选结果移动平面、选较好一侧或作最佳匹配搜索。

对一个对应侧，记材料面积为 $A$、全部闭环周长为 $L$、闭环数量为 $K$（包括外环和孔环）。若两侧面积均非零：

$$
e_A=\frac{|A_C-A_G|}{A_G},\qquad
e_L=\frac{|L_C-L_G|}{L_G},\qquad
q=\begin{cases}1,&K_C=K_G\\0.5,&K_C\ne K_G,\end{cases}
$$

$$
s_{\rm side}=\exp\left(-\frac{e_A+e_L}{0.05}\right)q,\qquad
s_{\mathrm{section}}=\frac1M\sum_{j=1}^{M}\frac{s_{j,-}+s_{j,+}}2.
$$

空截面分支：双方面积均为 0 得 1；仅一方为 0 得 0。双方零面积时不再比较周长或环数。**v3 不读取 `expected_empty`**；以对应侧实际面积判空。标注等权、两侧等权，先求每侧分，再平均。

### 截面算法与备用

- 首选 [OCCT 截面曲线](../src/section.py#L26)：提取剖切边、积分边长、构造闭环和面、按嵌套奇偶加减面积。端点容差为 $10^{-5}$ mm；共面歧义、退化、重复边、开放/分叉图等会使此路径的测量不合格。“exact section curves” 是后端名称，不代表任意精度数值真值。
- 失败时在**原平面**调用 trimesh `mesh_plane`，端点以 $10^{-6}$ mm 聚类，合并重复无向边并要求闭环；用二维鞋带公式求每环面积、嵌套奇偶扣孔、欧氏线段长度求周长。
- 备用网格使用两档 GT 尺度挠度 $d_c=\max(10^{-5}{\rm mm},2\times10^{-5}D_G)$、$d_f=\max(10^{-5}{\rm mm},10^{-5}D_G)$。环数必须一致，面积和周长各自满足 $|x_f-x_c|\le\max(10^{-8},10^{-3}|x_f|)$；绝对项分别按 mm²、mm 解释。
- 任一参考/候选侧在声明路径后仍失败，则整个 section 不可测，不只平均成功平面。模块标记为近似，并保留逐侧后端与细化差。

来源与适配：局部评分、环组织、切面选择与聚合为本地实现；底层依赖为 OCCT、CADGenBench 网格工具和 trimesh。相对 v2，非空侧的指数/环数惩罚保留，但单平面改为 GT 双侧计划，并改进空截面和同平面备用逻辑。相同面积、周长和环数不证明轮廓逐点相同。

## 10. 测量失败怎样计分

实现：[contract_v3.aggregate_case](../src/contract_v3.py#L14)。候选通过 validation 且身份/哈希证据有效时，始终保留参与资格。每个合格实测分需满足 `status=ok`、`measurement_valid=true`、身份匹配且是有限的 0–1 数。

$$
a_i=\begin{cases}s_i,&\text{测量可用}\\0,&\text{测量不可用},\end{cases}
\qquad
\mathrm{coverage}=\sum_{i:\ s_i\text{可用}}w_i.
$$

不可测项同时保留 `measured_score=null`、`awarded_score=0`、原因及后端证据；总分标为 `policy_lower_bound`，不虚构实测零分，不删除这道题，不重新分配权重。可得分范围为：

$$
\left[S,\ \min\left(1,S+\sum_{i:\ s_i\text{不可用}}w_i\right)\right].
$$

这只表示缺失项的政策计分范围，不是数值误差界或统计置信区间。六项可用时 `score_kind=measured` 仍可能包含已披露的近似测量。

例：shape=0.90、dimension=0.80、distance=0.85、mass=0.95、face_match=0.90、section 不可测，则 $S=0.7825$，报告 **78.25/100**，实测权重覆盖率 90%，缺项范围 **78.25–88.25**。

[批次均分](../evaluate.py#L210)对全部参与者的 `final_score` 取算术平均，包含政策下界分。确认无效、缺失提交、候选验证未完成的题单列；参与数必须与总题数一起展示，不能只给均分掩盖缺考。

## 11. 来源与版本适配清单

|对照对象|复用内容|修改或新增|未复用/不能等同|
|---|---|---|---|
|CADGenBench 固定 commit|IoU、Surface F1、Topology 原始函数；网格、采样、解析等工具|本地六项汇总、固定坐标、shape 三项平均、错误转不可测、独立准入|官方 CAD Score、Interface Match、整套生成/编辑任务与排行榜|
|DeepCAD|当前评分路径未调用其代码|无|命令序列/参数准确率、其 Chamfer 不是本项目 distance|
|CADBench|当前评分路径未调用其代码|无|其 IoU/Chamfer/操作数不构成本项目官方指标来源|
|JoinABLe、MechVQA|只属于历史调研背景|无|没有 joint 预测或问答评分|
|trimesh / Eberly 多面体质量属性资料|质量属性备用积分的底层算法|本地相对误差与指数评分、收敛准入|不是直接复用一套 CAD benchmark 的 mass 指标|
|本地 v2|shape/dimension/distance 公式；mass 等价指数；非空 section 局部映射|v3 候选独立 validation、多后端 mass、面积 face_match、双侧 section、缺测授分合同|v2/v3 face_match 与 section 不能当同一语义直接混榜|

其他工程适配：独立进程与超时、输入/代码 SHA256、在经哈希校验的输入副本上评分、逐模块证据、只读历史结果、MCP/CLI 和便携运行时。输入副本保留在输出目录的 `<case>/inputs/` 中。这些用于调度、完整性与可复现性，不是新增几何指标。MCP 包装没有改变评分核心。

v3 robust 网格工具使用角挠度 0.1 rad，单次网格超过 2,000,000 三角形则报错；它调用 `tessellate_shape`，并非所有后续路径都运行 CADGenBench 完整网格门禁。mass 另检查 `is_volume`，section 检查剖切闭环和细化，face_match 当前没有网格收敛门控。应分别阅读各模块的质量证据。

## 12. 如何从一次结果复核公式

1. 查看 `manifest.json` 的协议、权重、输入/代码哈希和依赖版本。
2. 查看 `results/validity.json` 的候选健康证据与自交/干涉记录。
3. 查看 `results/shape.json` 的 IoU/F1/topology，`dimension.json` 的逐项 pass，`distance.json` 的双向 p99 和 tau。
4. 查看 `mass.json` 的体积/惯性误差与收敛，`face_match.json` 的两个 seed 的 P/R/F1，`section.json` 的每个对应侧测量和分数。
5. 查看 `aggregate.json` 的六项 `measured_score/awarded_score`、覆盖率和缺项范围，按固定权重重算。最终批次以 `summary.json`、`report.md`、`comparison.csv` 为准。

快速规则见 [SCORING_V3](SCORING_V3.md)，来源证据见 [EVALUATOR_CODE_PROVENANCE](EVALUATOR_CODE_PROVENANCE.md)，输入与运行方法见 [README](../README.md)。源码或参数改变时应同步更新协议、来源记录与本说明，不能沿用旧版本名称掩盖评分变化。
