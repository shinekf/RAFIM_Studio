# RAFIM Studio — 机器人智能制造智能体平台

AI 驱动的工业机器人打磨/焊缝检测全流程自动编程系统。

## 项目结构

```
├── RAFIM_Portal.py              # 桌面门户启动器（多进程架构）
├── 打磨/                        # 智能打磨模块（完整独立可运行）
│   ├── robot_manufacturing_ui.py  # 主界面入口
│   ├── workers.py                 # 4 个后台运算线程（点云/曲面/轨迹/后处理）
│   ├── controllers/               # MVC 控制器
│   ├── hardware/                  # 相机+机器人硬件抽象层
│   ├── ai_agent/                  # AI 引擎（LLM推理/语音/自动寻优）
│   └── templates/                 # KUKA KRL / UR URScript 模板
├── 线激光寻缝/                  # 线激光焊缝检测模块（UI 框架就绪）
│   ├── main.py
│   └── seam_tracking_ui.py
└── RAFIM_Studio/                # 模块化重构（进行中）
```

## 核心功能

### 智能打磨系统
- **3D 视觉采集**：梅卡曼德结构光相机 + 本地点云文件导入
- **曲面拟合**：B 样条曲面 / 最小二乘平面拟合
- **轨迹规划**：Y 轴切片法 + 刀具半径补偿 + KDTree 孔洞过滤 + Zigzag 弓字型路径
- **AI 自动寻优**：LLM 闭环优化（DeepSeek API），双维度轨迹评分（法向平滑度+点均匀度）
- **机器人代码生成**：KUKA KRL / UR URScript 模板渲染，含抬刀跨越逻辑
- **自然语言交互**：中文语音指令（Whisper）+ Chat Agent（7 种动作指令）
- **工艺记忆库**：RAG 检索历史成功配方

### 线激光焊缝检测
- 5 步流程导航（连接→粗扫→框选→规划→高精扫描）
- 3D 视口 + 2D 激光截面实时显示（pyqtgraph）
- 支持 V/U 型坡口、搭接、对接接头类型

## 技术栈

| 层级 | 技术 |
|------|------|
| UI | PySide6 + qt-material + PyVista + pyqtgraph |
| 数据处理 | NumPy + SciPy + Open3D |
| AI | DeepSeek API + Whisper + RAG |
| 机器人 | TCP Socket (KUKA/UR) + Jinja2 |
| 架构 | 多进程隔离 + MVC + KISS 原则 |

## 快速开始

```bash
# 安装依赖
pip install PySide6 qt-material pyvista pyvistaqt pyqtgraph
pip install numpy scipy open3d Jinja2 openai

# 启动桌面门户
python RAFIM_Portal.py

# 或直接启动各模块
cd 打磨 && python robot_manufacturing_ui.py
cd 线激光寻缝 && python main.py
```

## 配置 API Key

将 `打磨/ai_agent/llm_client.example.py` 和 `chat_worker.example.py` 复制为 `.py` 文件，填入你的 DeepSeek API Key。

## 架构铁律

1. **计算-显示解耦**：轨迹规划必须基于未旋转的原始数据（`backup_surface` / `backup_inliers`）
2. **KISS 优先**：能后处理就不预处理，修改集最小化
3. **进程隔离**：Portal 通过 `subprocess.Popen` + `sys.executable` + `cwd` 启动各模块
