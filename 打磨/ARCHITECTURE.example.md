# AI 驱动机器人化制造软件 - 技术架构文档 (最后更新: 2026-05-10)

## 0. 设计第一原则：KISS (Keep It Simple, Stupid)

软件功能的编写和实现始终遵循 KISS(Keep it simple,stupid) 原则：

- **能后处理就不预处理**：不对网格做破坏性裁剪，能在轨迹生成后过滤的绝不提前动数据结构
- **阈值宽松先行，收紧迭代在后**：新功能先用宽松阈值跑通全链路，再根据实测数据收紧参数
- **复用现有数据通道**：新增标签字段优先使用 PolyData 数组（如 `['IsJump']`），不新增文件格式或通信协议
- **修改集最小化**：一个功能的修改应局限在最少的文件集合内，避免跨层涟漪

---

## 1. 前端架构 (GUI)

| 库/框架 | 用途 |
|---------|------|
| **PySide6** | Qt6 Python绑定，主UI框架（窗口、控件、事件、布局） |
| **qt-material** | Material Design深色主题样式表 |
| **PyVista** | VTK的Python封装，3D可视化核心 |
| **pyvistaqt.QtInteractor** | PyVista与Qt的集成组件，嵌入3D渲染窗口 |

**UI组件结构**：
- `QMainWindow` + `QDockWidget` 多面板布局
- `QTreeWidget` 项目树管理
- `QGroupBox`/`QFormLayout` 工艺参数面板
- `QTextEdit` 日志面板
- `SafeSpinBox`/`SafeDoubleSpinBox` 防误触数值控件
- `QTimer` 轨迹仿真动画驱动

---

## 2. 后端架构 (数据处理)

| 库/框架 | 用途 |
|---------|------|
| **NumPy** | 数值计算核心，点云矩阵运算 |
| **SciPy** | `scipy.spatial.transform.Rotation` 坐标变换 |
| **Open3D** | 点云滤波算法（SOR/ROR、体素下采样） |
| **PyVista** | 曲面网格操作、切片算法、ROI裁剪、射线拾取 |
| **Jinja2** | 机器人代码模板渲染引擎 |

**多线程架构**：
- `QThread` 后台运算线程
- `Signal/Slot` Qt信号机制通信

**四大Worker线程**：

| Worker | 功能 |
|--------|------|
| `PointCloudWorker` | 点云读取 + 滤波（SOR/ROR） |
| `SurfaceFittingWorker` | B样条曲面拟合 / 最小二乘平面拟合 |
| `TrajectoryWorker` | Z轴切片法轨迹生成 + 刀具半径补偿 + 孔洞过滤 (2D KDTree) + 跳跃检测 + 断线构造 |
| `PostProcessorWorker` | Jinja2模板后处理（KUKA/UR代码生成） |

---

## 3. 相机连接

| 库/框架 | 用途 |
|---------|------|
| **MechEyeAPI** (`mecheye`) | 梅卡曼德结构光相机SDK |
| **NumPy** | 点云数据格式转换 |

**相机接口架构**：
- `BaseCamera` (ABC抽象基类) → 支持多品牌插件扩展
- `MechMindCamera` 具体实现类

**接口方法**：
- `connect()` - 连接相机
- `capture_pointcloud()` - 采集点云，返回 numpy array (N, 3)
- `disconnect()` - 断开连接

**支持相机型号**：梅卡曼德 (Mech-Mind) 3D结构光相机

---

## 4. 机器人连接

| 库/框架 | 用途 |
|---------|------|
| **socket (TCP)** | UR Primary Client Interface 通讯 |
| **NumPy** | 轨迹点坐标运算、安全校验 |
| **Jinja2** | 模板化机器人代码生成 |

**机器人接口架构**：
- `BaseRobot` (ABC抽象基类) → 支持多品牌插件扩展
- `URRobotController` 具体实现类 (UR5/AUBO)

**通讯协议**：

| 机器人 | 协议 | 端口 | 模板文件 |
|--------|------|------|----------|
| **UR5 / AUBO** | TCP Socket + URScript | 30002 | `ur.script.j2` |
| **KUKA** | TCP Socket + KRL | 30002 | `kuka.src.j2` |

**接口方法**：
- `connect()` - TCP连接
- `send_program()` - 下发URScript/KRL代码
- `emergency_stop()` - 紧急停止指令（双重刹车：`stopj` + `stopl`）
- `validate_trajectory()` - 轨迹安全预检（工作半径、台面高度）

**Waypoint 数据结构**（PostProcessorWorker 产出，模板消费）：

每个航点包含位姿坐标 + `is_jump` 布尔标签：

| 字段 | UR/AUBO | KUKA | 说明 |
|------|---------|------|------|
| 位置 | `x, y, z` (米) | `x, y, z` (毫米) | TCP 坐标 |
| 姿态 | `rx, ry, rz` (旋转向量, 弧度) | `a, b, c` (Z-Y-X 欧拉角, 度) | 刀具指向 |
| `is_jump` | `bool` | `bool` | 是否为孔洞跳跃点，模板据此生成抬刀/下刀指令 |

**模板抬刀逻辑**：
- UR/AUBO: `is_jump=true` → 先 `movej` 到 Z+50mm 安全高度，再 `movel` 下刀
- KUKA: `is_jump=true` → 先 `PTP` 到 Z+50mm 安全高度，再 `LIN` 下刀

---

## 5. 项目文件结构

```
ui7/
├── robot_manufacturing_ui.py   # 主界面（UI构建 + MainController门面）
├── workers.py                  # 后台运算线程
├── view_3d_controller.py       # 3D渲染控制器（Actor管理、交互控件）
├── project_manager.py          # 项目保存/加载管理
├── controllers/                # MVC控制器目录
│   ├── __init__.py
│   ├── process_controller.py   # 工艺流控制器（点云→轨迹→仿真｜语音｜AI助手｜全自动管线）
│   └── hardware_controller.py  # 硬件控制器（相机/机器人/急停）
├── hardware/
│   ├── __init__.py
│   ├── base_camera.py          # 相机抽象基类
│   ├── base_robot.py           # 机器人抽象基类
│   ├── mechmind_camera.py      # 梅卡曼德相机实现
│   ├── ur_robot.py             # UR/AUBO机器人实现
│   ├── send_local_script.py    # 本地脚本发送
│   └── emergency_stop.py       # 急停控制
├── ai_agent/                   # AI Agent 模块（与 UI 完全隔离）
│   ├── __init__.py             # 包导出（8个模块）
│   ├── virtual_evaluator.py    # 轨迹评分器（法向+均匀度双维度）
│   ├── headless_pipeline.py    # 无头管线（无 Qt 依赖）
│   ├── llm_client.py           # LLM 客户端（DeepSeek, 参数推理+语音意图解析）
│   ├── auto_research_worker.py # QThread AI 寻优闭环
│   ├── memory_bank.py          # 工艺记忆库（RAG 检索历史配方）
│   ├── monitor_dialog.py       # AI 寻优实时监控面板（折线图）
│   ├── voice_worker.py         # 本地语音识别（Whisper medium 离线 STT）
│   ├── chat_worker.py          # 聊天智能体（全自主 Auto-CAM Agent）
│   └── test_agent.py           # 单元测试
├── templates/                  # Jinja2机器人代码模板
│   ├── kuka.src.j2             # KUKA KRL模板
│   └── ur.script.j2            # UR/AUBO URScript模板
├── capture_tool.py             # 点云采集工具
└── diagnostic_capture.py       # 相机诊断工具
```

---

## 6. MVC门面架构（重构后）

采用**门面模式 (Facade Pattern)**，将原 `MainController` 上帝类拆分为职责清晰的子控制器：

```
┌─────────────────────────────────────────────────────────────┐
│                    MainController (门面)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │    UI引用   │  │  日志接口   │  │   公共数据容器      │  │
│  │  self.ui    │  │ log_message │  │ planned_trajectory  │  │
│  └─────────────┘  └─────────────┘  │ backup_surface      │  │
│                                    │ backup_inliers       │  │
│                                    └─────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              ProcessController (工艺流控制器)           │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ • 点云加载/滤波          • 语音命令识别 (Voice Copilot)  │  │
│  │ • 曲面拟合               • AI 聊天智能体 (Chat Agent)   │  │
│  │ • ROI交互框              • 动作路由器 (Action Router)   │  │
│  │ • 轨迹规划               • 自动点云加载                 │  │
│  │ • 轨迹仿真播放           • 静默代码输出                 │  │
│  │ • 示教点拾取             • 端到端全自动管线 (E2E)       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              HardwareController (硬件控制器)            │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │ • 相机连接 • 机器人连接 • 急停控制 • 配置持久化 • 脚本发送 │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**控制器职责边界**：

| 控制器 | 职责范围 | 代理访问 |
|--------|----------|----------|
| `ProcessController` | 工艺流程：点云→曲面→轨迹→仿真 | `self.main.ui`, `self.main.view_3d` |
| `HardwareController` | 硬件通信：相机/机器人/急停 | `self.main_controller.log_message()` |

---

## 7. 数据流向

```
相机采集 → 点云滤波 → 曲面拟合 → ROI框选 → 轨迹生成 → 刀具补偿 → KDTree孔洞过滤 → 跳跃检测/断线 → 后处理 → 仿真 → 机器人下发
   │          │          │          │          │          │          │           │          │       │
MechEyeAPI  Open3D     PyVista    PyVista    PyVista    NumPy     cKDTree    NumPy      Jinja2  QTimer
SDK         SOR/ROR    B样条      BoxWidget  切片法     法向补偿   2D遮罩    断点检测   模板    Actor动画
```

---

## 8. 核心设计模式

| 模式 | 应用 |
|------|------|
| **MVC门面分离** | MainController 作为门面，委托给 ProcessController/HardwareController |
| **硬件抽象工厂** | `BaseCamera`/`BaseRobot` ABC接口，支持多品牌插件 |
| **信号槽解耦** | QThread Worker 与 UI 通信 |
| **模板方法** | Jinja2 机器人代码生成，解耦格式与数据 |
| **计算-显示解耦** | 轨迹规划用 `backup_surface`，显示叠加旋转 |

---

## 9. 核心架构铁律 (不可触碰)

### 铁律零：KISS 优先

所有功能设计和实现必须首先通过 KISS 审查：
- 新增逻辑能否在不修改底层数据结构的前提下完成？
- 能否用后处理代替预处理？
- 修改是否局限在最小文件集合内？

违反 KISS 的方案需要明确的工程理由（如性能硬约束）方可例外。

### 铁律一：只读原则

**轨迹规划算法 (`workers.py`) 必须且只能使用未经旋转的原始备份数据**：
- `backup_surface` - 曲面备份
- `backup_inliers` - 点云备份

计算完成后，再将纯净的轨迹叠加当前的复合旋转矩阵用于 UI 显示。

**绝不允许带着旋转去切片！**

### 铁律二：不可变锚点

`self.surface_center` (基点) 是虚拟世界中的物理锚点。

在执行任何旋转矩阵运算时，**绝对不允许修改它的 XYZ 绝对坐标**。

### 铁律三：计算-显示解耦

任何 UI 显示变换（旋转、平移）**不得污染原始计算数据**。

轨迹规划输出必须保持纯净，显示变换仅在渲染层面叠加。

---

## 10. 核心算法与公式

### 刀具半径补偿

```
TCP_point = Surface_point + (Normal_vector × Tool_Radius)
```

- `Surface_point`: 曲面上的点 (mm)
- `Normal_vector`: 单位法向量（已纠正，指向刀具侧）
- `Tool_Radius`: 工具球头半径 (mm)

### 法向量自动纠正

检测法向量 Z 分量均值：
- 若 `mean(nz) < 0` → 全部取反（确保指向刀具侧）

### 射线拾取算法（示教点）

基于数学射线相交，绕过 VTK 透明度拾取 Bug：
1. 屏幕坐标 → 射线起点/终点（VTK DisplayToWorld）
2. 射线与曲面网格求交 (`mesh.ray_trace`)
3. 取最近交点作为示教点

### 孔洞过滤（2D KDTree 空间遮罩）

对刀补后的轨迹点，使用原始点云构建 2D KDTree，剔除落在真实曲面之外（孔洞区域）的假点：

```
kdtree = cKDTree(inliers[:, :2])       # 仅用 XY 平面坐标
dists, _ = kdtree.query(path_points[:, :2])
valid_mask = dists < 5.0               # 5.0mm 遮罩阈值
path_points = path_points[valid_mask]
```

**阈值选取依据**：
- `5.0 mm`：包容下采样导致的网格空隙，同时精准抠除 >10mm 的真实物理空洞
- 仅使用 XY 平面：加工方向为 Z 轴，孔洞在 XY 投影面上表现为空白

### 跳跃检测与轨迹打断

过滤后相邻轨迹点的间距若超过阈值，判定为跨越孔洞边界，需打断连续线段：

```
diffs = path_points[1:] - path_points[:-1]
dists_between_points = np.linalg.norm(diffs, axis=1)

is_jump = np.zeros(N, dtype=bool)
is_jump[0] = True                       # 起始点必为下刀点
is_jump[1:][dists_between_points > 8.0] = True  # 8.0mm 跳跃阈值
```

**断线构造**：跳跃点之间不画连线，3D 渲染呈物理断开状态：

```
lines = []
for i in range(N - 1):
    if not is_jump[i+1]:               # 下一个点不是跳跃点才连线
        lines.extend([2, i, i + 1])
trajectory.lines = np.hstack(lines)
trajectory['IsJump'] = is_jump         # 埋入 PolyData 供后处理器消费
```

**`IsJump` 标签传递链路**：
```
TrajectoryWorker.run()
  → trajectory['IsJump'] = is_jump
  → PostProcessorWorker.run()
      → is_jumps = self.trajectory.get('IsJump', ...)
      → waypoints.append({..., 'is_jump': bool(is_jumps[i])})
      → Jinja2 模板: {% if wp.is_jump %} movej/PTP 抬刀 {% else %} movel/LIN 加工 {% endif %}
```

---

## 11. 关键技术细节

### VTK BoxWidget 状态残留修复

**问题**：ROI 交互框撤销后存在"幽灵框"和形变缓存

**解决方案**：
- `clear_actors_only()` 开头强制调用 `remove_interactive_roi()`
- 硬重启模式：销毁控件 → `QTimer.singleShot(50ms)` → 重建

### QTimer 父对象约束

QTimer 必须挂载到 `QObject` 子类：

```python
# 错误 ❌
self.sim_timer = QTimer(self)  # ProcessController 不是 QObject

# 正确 ✅
self.sim_timer = QTimer(self.main.main_window)  # QMainWindow 是 QObject
```

### Actor 动画低开销

使用 `vtkActor.SetPosition()` 直接设置位置，避免重建几何体：

```python
actor.SetPosition(x, y, z)  # 仅更新变换矩阵
plotter.render()            # 触发重绘
```

---

## 12. 依赖安装

```bash
pip install PySide6
pip install qt-material
pip install pyvista
pip install pyvistaqt
pip install numpy
pip install scipy
pip install open3d
pip install MechEyeAPI  # 梅卡曼德相机SDK
pip install Jinja2      # 模板引擎
```

---

## 13. 环境变量

```python
os.environ['QT_API'] = 'pyside6'  # 强制 pyvistaqt 使用 PySide6
```

---

## 14. AI Agent 模块

### 14.1 模块架构

```
ai_agent/
├── __init__.py              # 包导出（8个模块全部导出）
├── virtual_evaluator.py     # 虚拟轨迹评分器（法向+均匀度双维度）
├── headless_pipeline.py     # 无头管线（后台物理结算，无 Qt 依赖）
├── llm_client.py            # LLM 客户端（DeepSeek API, 参数推理+语音意图解析）
├── auto_research_worker.py  # QThread AI 自动寻优闭环
├── memory_bank.py           # 工艺记忆库（RAG 检索历史配方）
├── monitor_dialog.py        # AI 寻优实时监控面板（PySide6 QDialog 折线图）
├── voice_worker.py          # 本地语音识别（Whisper medium 离线 STT）
├── chat_worker.py           # 聊天智能体（全自主 Auto-CAM Agent）
└── test_agent.py            # 单元测试
```

### 14.2 虚拟评分算法 (`virtual_evaluator.py`)

**双维度评分**：

| 维度 | 权重 | 核心算法 | 满分阈值 | 归零阈值 |
|------|------|----------|----------|----------|
| 法向平滑度 | 60% | P98分位数 + 滑动平均滤波 | 平均角 < 3°, 最大角 < 10° | 平均角 > 8°, 最大角 > 30° |
| 点均匀度 | 40% | 中位数3倍过滤 + 点数密度 | CV < 0.30, 点数 10000-15000 | CV > 0.60, 点数 < 5000 或 > 25000 |

**关键滤波技术**：
- **法向 P98 分位数**：过滤 Zig-zag 换行时的虚假突变（换行步占 < 2%）
- **距离中位数过滤**：剔除 `> median × 3` 的换行跨步距离
- **滑动平均滤波**：窗口=5，消除网格边界裁剪导致的局部法向高频噪声

### 14.3 LLM 客户端 (`llm_client.py`)

**类名**: `AutoCamAgent`

**API 配置**：
```python
self.client = OpenAI(
    api_key="YOUR_API_KEY_HERE",
    base_url="https://api.deepseek.com",
    timeout=60.0
)
self.model = "deepseek-v4-flash"
```

**核心方法**：

| 方法 | 功能 | 典型输入 | 输出 |
|------|------|----------|------|
| `suggest_next_parameters()` | 参数优化推理（含思考模式） | 当前参数 + 评分 + 反馈 | 建议参数字典 |
| `parse_voice_command()` | 自然语言意图解析 | 语音文本 + 当前全量参数 | 覆盖后的参数字典 |
| `run_optimization_loop()` | 全闭环优化（可选） | 点云路径 + 初始参数 | 最佳结果字典 |

**防错机制**：
1. 正则提取 JSON：`re.search(r'\{.*\}', response_text, re.DOTALL)`
2. 参数物理约束验证：voxel_size 1.0-10.0, smoothness 1-10, path_step 0.5-5.0
3. 枚举白名单验证：filter_type, fitting_algorithm, tool_type 必须匹配已有选项
4. 兜底默认参数：解析失败时返回安全值

**语音意图解析特性**：
- 自动收集 19 个参数（工艺参数 + 设备参数）作为上下文
- LLM 推断用户意图后返回完整参数字典，未提及参数保持原样
- 枚举项严格白名单防止幻觉（如"碗型砂轮"而非"碗形砂轮"）

### 14.4 无头管线 (`headless_pipeline.py`)

**同步执行流程**（无 Qt 依赖，适合 AI 脚本批量调用）：
```
点云读取 → 体素下采样 → 滤波 → B样条拟合 → Y轴切片 → 法向平滑 → 刀补 → KDTree孔洞过滤 → 跳跃检测/断线 → 返回 PolyData (含 IsJump)
```

**关键增强**：
- `extract_surface(algorithm='dataset_surface')` - 消除 PyVista Future Warning
- 滑动平均法向滤波 - 在切片循环内，X 排序后、Zig-zag 翻转前执行

### 14.5 自动寻优闭环 (`auto_research_worker.py`)

**QThread 信号定义**：
```python
progress = Signal(str)                # 进度日志
iteration = Signal(int, float, str)   # 迭代信息（轮次, 分数, 反馈）
finished = Signal(dict)               # 完成信号（最佳参数）
error = Signal(str)                   # 错误信号
```

**执行流程**：
```
循环 MAX_EPOCHS 轮:
  1. run_virtual_grinding(pointcloud, params) → trajectory
  2. TrajectoryEvaluator.evaluate(trajectory) → score, feedback
  3. 若 score >= TARGET_SCORE → 达标退出
  4. AutoCamAgent.suggest_next_parameters() → next_params
  5. 更新 params，继续循环
```

---

## 15. AI 寻优 UI 集成

### 15.1 按钮位置

`btn_auto_research` 位于 `robot_manufacturing_ui.py` 顶部系统栏（紫色醒目），在 `btn_undo` 之后。

**启用条件**：`current_original is not None`（需先加载点云）

### 15.2 UI 参数传递

`on_auto_research()` 从 UI 提取当前参数作为优化起点：
```python
current_ui_params = {
    "voxel_size": float(self.main.ui.spin_voxel_size.value()),
    "filter_type": self.main.ui.combo_filter_algorithm.currentText(),
    "smoothness": int(self.main.ui.slider_smoothness.value()),
    "tool_radius": float(self.main.ui.spin_tool_radius.value()),
    "path_step": float(self.main.ui.spin_path_step.value()),
    "invert_normal": self.main.ui.check_invert_normal.isChecked()
}
self.auto_research_worker = AutoResearchWorker(pointcloud_path, initial_params=current_ui_params)
```

### 15.3 自动 3D 重建链条（状态机）

**状态机流程**：
```
AI寻优完成 → _on_ai_research_finished → _start_ai_auto_apply()
    ↓ (_ai_auto_apply_stage = 1)
on_pointcloud_finished → on_fit_surface()
    ↓ (_ai_auto_apply_stage = 2)
on_surface_fitted → on_plan_trajectory()
    ↓ (_ai_auto_apply_stage = 3)
_finish_plan_trajectory → 清理临时文件，恢复按钮，完成提示
```

**钩子代码模式**：
```python
if getattr(self, '_ai_auto_apply_stage', 0) == N:
    self._ai_auto_apply_stage = N+1
    self.main.log_message("系统", "自动重建场景...")
    self.on_next_step()
```

---

## 16. 法向平滑滤波算法

### 16.1 算法位置

同步修改于：
- `ai_agent/headless_pipeline.py` - `_run_trajectory_generation()`
- `workers.py` - `TrajectoryWorker.run()`

### 16.2 算法代码

在 Y 轴切片循环内，X 排序后、Zig-zag 翻转前插入：
```python
# 滑动平均滤波（窗口=5，消除边界高频突变）
window_size = 5
pad_size = window_size // 2
padded_normals = np.pad(normals, ((pad_size, pad_size), (0, 0)), mode='edge')
smoothed_normals = np.zeros_like(normals)

for idx in range(len(normals)):
    window = padded_normals[idx : idx + window_size]
    avg_normal = np.sum(window, axis=0)
    norm = np.linalg.norm(avg_normal)
    if norm > 1e-6:
        smoothed_normals[idx] = avg_normal / norm
    else:
        smoothed_normals[idx] = normals[idx]

normals = smoothed_normals
```

---

## 17. 孔洞过滤与轨迹打断

### 17.1 问题背景

B 样条曲面拟合会在工件孔洞区域拟合出**不存在的虚假曲面**，导致 Y 轴切片法生成的轨迹穿越空洞、产生连续的假轨迹线。机器人若沿此轨迹执行，刀具会切削空区域甚至撞件。

**KISS 策略**：不对曲面网格做破坏性裁剪，仅在轨迹生成完毕后对轨迹点做后处理过滤。

### 17.2 算法位置

同步实现于两处：
- `workers.py` - `TrajectoryWorker.run()` (L253-285)
- `ai_agent/headless_pipeline.py` - `_run_trajectory_generation()` (L453-485)

### 17.3 完整算法代码

```python
# ===== Step 6: 2D KDTree 紧凑过滤 =====
# 构建 XY 平面 KDTree，用原始点云的真实分布区域做空间遮罩
from scipy.spatial import cKDTree
kdtree = cKDTree(self.inliers[:, :2])
dists, _ = kdtree.query(points_compensated[:, :2])

# 5.0mm 遮罩阈值：包容下采样网格空隙，精准掏空 >10mm 的物理孔洞
valid_mask = dists < 5.0
points_compensated = points_compensated[valid_mask]
normals_array = normals_array[valid_mask]

if len(points_compensated) < 2:
    raise ValueError("生成的有效轨迹点过少（KDTree 过滤后不足 2 点）")

# ===== Step 7: 断点与跳跃检测 =====
diffs = points_compensated[1:] - points_compensated[:-1]
dists_between_points = np.linalg.norm(diffs, axis=1)

is_jump = np.zeros(len(points_compensated), dtype=bool)
is_jump[0] = True                                       # 起始点必为下刀点
is_jump[1:][dists_between_points > 8.0] = True          # 8.0mm 跳跃阈值

# ===== Step 8: 构建断开的 3D 线条 =====
lines = []
for i in range(len(points_compensated) - 1):
    if not is_jump[i+1]:  # 跳跃目标点不连线，3D 渲染为物理断开
        lines.extend([2, i, i + 1])

trajectory = pv.PolyData(points_compensated)
trajectory.lines = np.hstack(lines) if lines else np.array([])
trajectory['Normals'] = normals_array
trajectory['IsJump'] = is_jump   # 埋入标签，供后处理器消费
```

### 17.4 关键阈值

| 参数 | 值 | 作用 | 调参方向 |
|------|-----|------|----------|
| KDTree 遮罩半径 | `5.0 mm` | 距离原始点云超过此值的轨迹点被剔除 | 太小→误删边缘合法点；太大→孔洞漏网 |
| 跳跃检测间距 | `8.0 mm` | 相邻轨迹点间距超过此值判定为跨越孔洞 | 太小→正常切片点被误判为跳跃；太大→小孔洞不断开 |

**调参约束**：遮罩半径 < 跳跃检测间距，确保孔洞边缘被遮罩剔除后产生的间隙能被跳跃检测捕获。

### 17.5 IsJump 标签传递链路

```
┌─────────────────────┐
│  TrajectoryWorker   │  trajectory['IsJump'] = is_jump (bool 数组)
└────────┬────────────┘
         │ finished.emit(trajectory)
         ▼
┌─────────────────────┐
│ ProcessController   │  self.main.planned_trajectory = trajectory
└────────┬────────────┘
         │ on_robot_grinding()
         ▼
┌─────────────────────┐
│ PostProcessorWorker │  is_jumps = self.trajectory.get('IsJump', ...)
│                     │  waypoints.append({..., 'is_jump': bool(is_jumps[i])})
└────────┬────────────┘
         │ finished.emit(code)
         ▼
┌─────────────────────┐
│  Jinja2 模板        │  {% if wp.is_jump %} → 抬刀指令
│  ur.script.j2       │  {% else %}        → 加工指令
│  kuka.src.j2        │
└─────────────────────┘
```

### 17.6 模板实现

**UR/AUBO** (`ur.script.j2`)：
```jinja2
{% if wp.is_jump %}
  # 抬刀到安全高度 Z+50mm，再下刀到目标点
  movej(p[... z+0.050 ...], a=tcp_accel*2, v=tcp_speed*2)
  movel(p[... z ...], a=tcp_accel, v=tcp_speed)
{% else %}
  movel(p[...], a=tcp_accel, v=tcp_speed)
{% endif %}
```

**KUKA** (`kuka.src.j2`)：
```jinja2
{% if wp.is_jump %}
  ; 抬刀到安全高度 Z+50mm，再下刀到目标点
  PTP {X ... Z ... Z+50.0 ...}
  LIN {X ... Z ...}
{% else %}
  LIN {X ... Z ...}
{% endif %}
```

### 17.7 依赖关系

- `scipy.spatial.cKDTree` — 轨迹过滤和 headless pipeline 都需要
- 传入的 `inliers` 必须是未经旋转的原始点云（`backup_inliers` / `current_inliers`），与铁律一一致

---

## 18. AI Agent 依赖（已合并至 Section 24）

```bash
pip install openai     # DeepSeek OpenAI SDK
pip install anthropic  # 已弃用，保留备用
```

---

## 19. AI 模块核心准则

### 准则一：评分器阈值必须符合工业实际

法向突变和 CV 的阈值设定必须基于真实机器人容忍度，而非理论理想值：
- 平均突变角 3°-8° 是可接受范围（非 0°-2°）
- P98 最大突变角 10°-30° 可容忍（B样条边缘畸变）
- CV 0.30-0.60 是网格切片的正常波动

### 准则二：换行过渡步必须过滤

Zig-zag 弓字型轨迹的换行点是数学必然，不是质量缺陷：
- 法向：使用 P98 分位数而非 max()
- 距离：使用中位数 3 倍过滤而非全量统计

### 准则三：UI 参数必须传递给 AI Worker

AI 寻优的起点参数应读取 UI 当前值，而非代码硬编码的默认值，让大模型负责优化而非兜底。

---

## 20. 本地语音交互 (Voice Copilot)

### 19.1 架构

```
btn_voice_cmd → VoiceCommandWorker (QThread) → Whisper medium (离线 STT)
    → _on_voice_text → AutoCamAgent.parse_voice_command() → 覆盖 UI 参数
```

### 19.2 语音识别 Worker (`voice_worker.py`)

**类名**: `VoiceCommandWorker(QThread)`

| 信号 | 类型 | 说明 |
|------|------|------|
| `finished` | `Signal(str)` | 识别出的文本 |
| `error` | `Signal(str)` | 错误信息 |
| `progress` | `Signal(str)` | 状态提示 |

**技术细节**：
- 引擎：`SpeechRecognition` + Whisper medium 模型（本地离线）
- 语言：`language="zh"` 中文识别
- 工业提示词：`initial_prompt` 预加载 "工业机器人打磨工艺参数指令" 专业词汇
- 超时：等待 5s，最长录音 8s

### 19.3 UI 集成

- 按钮：`btn_voice_cmd`（青色 #00838f），位于打磨工艺参数布局
- 按钮三态：初始 → 聆听中（红色 #d84315）→ 识别完成 → 恢复
- 参数收集：收集 19 个参数传递给 LLM 解析
- 参数应用：LLM 返回完整参数字典后逐项应用到 UI 控件

### 19.4 枚举白名单

为防止 LLM 幻觉，在 `parse_voice_command()` prompt 中硬编码白名单：
```python
- filter_type 只能选: ["统计滤波 (SOR)", "半径滤波 (ROR)"]
- fitting_algorithm 只能选: ["B样条曲面拟合", "最小二乘法平面拟合"]
- tool_type 只能选: ["球头铣刀", "碗型砂轮", "百叶轮"]
```

---

## 21. 全自主工业智能体 (Auto-CAM Agent Chat)

### 20.1 架构

```
btn_send_chat → ChatAgentWorker (QThread) → DeepSeek API (deepseek-chat)
    → 解析 JSON → _on_chat_finished() → Action Router → 执行命令
```

### 20.2 聊天 Worker (`chat_worker.py`)

**类名**: `ChatAgentWorker(QThread)`

| 信号 | 类型 | 说明 |
|------|------|------|
| `finished` | `Signal(str, list)` | 回复文本 + 动作指令列表 |
| `error` | `Signal(str)` | 错误信息 |

**API 配置**：
```python
client = OpenAI(
    api_key="YOUR_API_KEY_HERE",
    base_url="https://api.deepseek.com",
    timeout=30.0
)
model = "deepseek-chat"
```

### 20.3 支持的 7 种动作命令

| 命令 | 功能 | 需要 args |
|------|------|-----------|
| `SET_PARAMS` | 修改工艺/设备参数 | 参数字典 |
| `LOAD_CLOUD` | 自动扫描根目录找点云并加载 | 无 |
| `FIT_SURFACE` | 执行曲面拟合 | 无 |
| `PLAN_TRAJECTORY` | 规划打磨轨迹 | 无 |
| `AUTO_RESEARCH` | 启动 AI 自动寻优 | 无 |
| `GENERATE_CODE` | 静默生成脚本保存到根目录 | `robot_brand` (默认 "UR5") |
| `AUTO_END_TO_END` | 全自动端到端管线 | `robot_brand` (默认 "UR5") |

### 20.4 动作路由器 (Action Router)

在 `process_controller.py` 的 `_on_chat_finished()` 中实现：

```python
if cmd == "SET_PARAMS":       → _apply_params(args)
elif cmd == "LOAD_CLOUD":     → auto_load_pointcloud()
elif cmd == "FIT_SURFACE":    → on_fit_surface()
elif cmd == "PLAN_TRAJECTORY": → on_plan_trajectory()
elif cmd == "AUTO_RESEARCH":  → on_auto_research()
elif cmd == "GENERATE_CODE":  → auto_generate_robot_code(args.get("robot_brand"))
elif cmd == "AUTO_END_TO_END": → run_agent_end_to_end(args.get("robot_brand"))
```

### 20.5 UI 集成

- Dock：`create_agent_dock()` 在 `robot_manufacturing_ui.py` 中
- 位置：`Qt.RightDockWidgetArea`
- 组件：`chat_history`(QTextEdit 只读) + `chat_input`(QLineEdit) + `btn_send_chat`(QPushButton)
- 信号：`btn_send_chat.clicked` 和 `chat_input.returnPressed` 连接到 `on_chat_send()`

### 20.6 时序约束

为防止异步多线程冲突，在 SYSTEM_PROMPT 中硬编码时序警告：
- 跨步骤需求（如"加载点云并输出代码"）**必须**使用单一 `AUTO_END_TO_END` 命令
- **严格禁止** 拼接基础命令（如 LOAD_CLOUD + GENERATE_CODE），这将导致系统崩溃

---

## 22. 自主工具与端到端管线

### 21.1 自动点云加载 (`auto_load_pointcloud`)

扫描工作目录根路径的 `.ply` 或 `.npy` 文件（排除 `temp_` 前缀），自动创建 `PointCloudWorker` 并启动处理。支持 `callback` 参数串联状态机。

### 21.2 静默代码输出 (`auto_generate_robot_code`)

- 自动识别品牌后缀：UR/AUBO → `.script`，KUKA → `.src`
- 文件名：`Auto_Generated_Grinding_Code.{ext}`
- 保存路径：`os.getcwd()` 即软件运行根目录
- 依赖：需 `self.main.planned_trajectory` 已就绪

### 21.3 端到端全自动管线 (`run_agent_end_to_end`)

**流程**：
```
auto_load_pointcloud() 
    ↓ (callback 串联)
on_auto_research() → AI 寻优闭环
    ↓ (状态机: stage 1→2→3)
点云滤波 → 曲面拟合 → 轨迹规划
    ↓ (钩子: _agent_auto_export_brand)
auto_generate_robot_code() → 脚本保存到根目录
```

**关键实现**：
- `_agent_auto_export_brand` 标记：跨回调传递品牌信息
- 在 `_finish_plan_trajectory` 末尾检测标记，若存在则自动导出

---

## 23. 工艺记忆库与实时监控

### 22.1 工艺记忆库 (`memory_bank.py`)

**类名**: `ProcessMemoryBank`

RAG（检索增强生成）风格的历史配方管理：
- 存储每次 AI 寻优的成功参数组合
- 支持基于当前参数的相似历史检索
- 为大模型提供历史参考，加速收敛

### 22.2 实时监控面板 (`monitor_dialog.py`)

**类名**: `AiMonitorDialog(QDialog)`

- 在 `on_auto_research()` 启动时弹出
- 图表实时更新：折线图显示逐轮得分趋势
- 信号连接：`AutoResearchWorker.epoch_update.connect(monitor_dialog.update_data)`
- 优化完成时调用 `finish_optimization()` 停止图表

---

## 24. 更新依赖

```bash
pip install openai            # DeepSeek OpenAI SDK（AI Agent）
pip install SpeechRecognition # 离线语音识别框架
pip install whisper           # OpenAI Whisper 模型（本地 STT）
pip install pyaudio           # 麦克风音频采集
```

**完整依赖清单**：
```bash
pip install PySide6 qt-material pyvista pyvistaqt
pip install numpy scipy open3d Jinja2
pip install openai SpeechRecognition whisper pyaudio
```