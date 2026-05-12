"""
AI 寻优实时监控可视化弹窗
使用 pyqtgraph 绘制折线图，实时显示得分上涨过程

科技感十足的深色主题界面，悬浮置顶显示。
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPen, QTextCursor

# 可选导入：pyqtgraph（如果未安装则使用简化版本）
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("[MonitorDialog] pyqtgraph 未安装，将使用简化文本监控模式")


class AiMonitorDialog(QDialog):
    """
    AI 寻优实时监控中心

    特性：
    - 深色科技感主题
    - 悬浮工具窗口，置顶显示
    - 实时折线图绘制得分曲线
    - 底部参数与反馈日志
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 AI 寻优实时监控中心")
        self.setMinimumSize(700, 500)

        # 悬浮工具窗口，置顶显示
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)

        # 深色科技感主题
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ==================== 顶部状态栏 ====================
        header_layout = QHBoxLayout()

        self.label_status = QLabel("正在连接大模型进行工艺寻优...")
        self.label_status.setStyleSheet("""
            color: #4fc3f7;
            font-size: 14px;
            font-weight: bold;
            padding: 5px;
        """)

        self.label_best_score = QLabel("当前最高分: 0.0")
        self.label_best_score.setStyleSheet("""
            color: #ffeb3b;
            font-size: 14px;
            font-weight: bold;
            padding: 5px;
        """)

        header_layout.addWidget(self.label_status)
        header_layout.addStretch()
        header_layout.addWidget(self.label_best_score)
        layout.addLayout(header_layout)

        # ==================== 中间：图表区域 ====================
        if PYQTGRAPH_AVAILABLE:
            # 使用 pyqtgraph 绘制专业折线图
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('#121212')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setYRange(0, 105)
            self.plot_widget.setLabel('left', '轨迹评分 (Score)', color='#888888')
            self.plot_widget.setLabel('bottom', '迭代轮次 (Epoch)', color='#888888')

            # 绘制目标线（95 分红线）- 使用 Qt.PenStyle 枚举
            dashed_pen = pg.mkPen(color='#f44336', width=2)
            dashed_pen.setStyle(Qt.DashLine)
            self.target_line = pg.InfiniteLine(pos=95.0, angle=0, pen=dashed_pen)
            self.plot_widget.addItem(self.target_line)

            # 绘制主曲线（高亮绿色）和散点
            self.score_line = self.plot_widget.plot(
                pen=pg.mkPen(color='#00e676', width=3),
                symbol='o',
                symbolSize=10,
                symbolBrush='#00e676',
                symbolPen=pg.mkPen(color='#00e676', width=1)
            )
            layout.addWidget(self.plot_widget, stretch=3)
        else:
            # pyqtgraph 未安装时，使用文本进度条替代
            self.text_progress = QLabel("📊 得分曲线图需要安装 pyqtgraph:\npip install pyqtgraph")
            self.text_progress.setStyleSheet("""
                QLabel {
                    background-color: #121212;
                    color: #888888;
                    font-size: 12px;
                    padding: 20px;
                    border: 1px solid #333;
                    border-radius: 4px;
                }
            """)
            self.text_progress.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.text_progress, stretch=3)

        # ==================== 底部：实时参数与反馈显示 ====================
        self.text_info = QTextEdit()
        self.text_info.setReadOnly(True)
        self.text_info.setMaximumHeight(150)
        self.text_info.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                color: #a5d6a7;
                font-family: 'Consolas', 'Microsoft YaHei Mono', monospace;
                font-size: 12px;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.text_info, stretch=1)

        # ==================== 底部按钮栏 ====================
        footer_layout = QHBoxLayout()

        self.btn_close = QPushButton("关闭窗口")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        self.btn_close.clicked.connect(self.close)
        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_close)
        layout.addLayout(footer_layout)

        # 数据存储
        self.epochs = []
        self.scores = []

    def update_data(self, epoch: int, score: float, best_score: float, params: dict, feedback: str):
        """
        更新图表数据和状态显示

        Args:
            epoch: 当前轮次 (0 表示记忆库命中)
            score: 当前得分
            best_score: 最佳得分
            params: 当前参数字典
            feedback: 评估器反馈文本
        """
        # 更新状态栏
        if epoch == 0:
            self.label_status.setText("💡 命中工艺记忆库，直接输出最佳结果！")
            self.label_status.setStyleSheet("""
                color: #ffeb3b;
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            """)
        else:
            self.label_status.setText(f"🚀 第 {epoch} 轮迭代寻优中...")

        self.label_best_score.setText(f"当前最高分: {best_score:.1f}")

        # 追加图表数据并刷新（仅在 pyqtgraph 可用时）
        self.epochs.append(epoch)
        self.scores.append(score)

        if PYQTGRAPH_AVAILABLE:
            self.score_line.setData(self.epochs, self.scores)
        else:
            # 简化模式：显示 ASCII 进度条
            bar_width = 20
            filled = int(score / 100 * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            progress_text = f"\n📊 第{epoch}轮得分: [{bar}] {score:.1f}分"
            self.text_info.append(progress_text)

        # 格式化参数显示
        param_str = "\n  ".join([f"{k}: {v}" for k, v in params.items()])
        info = f"━━━ [第 {epoch} 轮] ━━━\n尝试参数:\n  {param_str}\n[裁判反馈] {feedback}\n"
        self.text_info.append(info)

        # 自动滚动到底部
        cursor = self.text_info.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_info.setTextCursor(cursor)

    def update_progress(self, message: str):
        """
        更新进度日志（来自 Worker 的 progress 信号）

        Args:
            message: 进度消息文本
        """
        # 简洁显示关键信息
        if message.startswith("💡") or message.startswith("💾") or message.startswith("🏆"):
            self.text_info.append(message)
        elif message.startswith("=") or message.startswith("━"):
            self.text_info.append(message)

        # 自动滚动到底部
        cursor = self.text_info.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_info.setTextCursor(cursor)

    def finish_optimization(self):
        """
        寻优完成回调
        """
        self.label_status.setText("🎉 寻优结束！最佳参数已应用。")
        self.label_status.setStyleSheet("""
            color: #00e676;
            font-size: 14px;
            font-weight: bold;
            padding: 5px;
        """)
        self.text_info.append("\n✅ 优化完成！窗口可随时关闭。")


def test_dialog():
    """
    测试监控弹窗（需要 pyqtgraph）
    """
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    dialog = AiMonitorDialog()
    dialog.show()

    # 模拟数据更新
    test_params = {
        "voxel_size": 5.0,
        "filter_type": "统计滤波 (SOR)",
        "fitting_algorithm": "B样条曲面拟合",
        "smoothness": 5,
        "path_step": 2.0
    }

    dialog.update_data(1, 75.0, 75.0, test_params, "法向平滑度良好，均匀度待优化")
    dialog.update_data(2, 82.0, 82.0, test_params, "得分提升，继续优化")
    dialog.update_data(3, 91.0, 91.0, test_params, "接近目标，微调参数")
    dialog.update_data(4, 96.0, 96.0, test_params, "达标！轨迹质量优秀")
    dialog.finish_optimization()

    sys.exit(app.exec_())