"""
本地语音命令识别 Worker
使用 SpeechRecognition 采集音频 + faster-whisper GPU 加速推理
"""

import os
import numpy as np
import speech_recognition as sr
from PySide6.QtCore import QThread, Signal

# 使用国内 HuggingFace 镜像（解决墙体问题）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# faster-whisper 模型单例（懒加载，避免每次识别重新加载模型）
_model = None


def _get_model():
    """懒加载 faster-whisper medium 模型（int8 量化，~3GB 显存）"""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            "medium",
            device="cuda",
            compute_type="int8_float16",
            num_workers=2
        )
    return _model


class VoiceCommandWorker(QThread):
    """
    语音命令识别工作线程

    音频采集：speech_recognition (PyAudio)
    语音识别：faster-whisper (CTranslate2 + CUDA 加速)

    RTX 4060 Laptop 8GB：medium + int8_float16 约占用 3GB 显存
    """

    finished = Signal(str)      # 识别出的文本
    error = Signal(str)         # 错误信息
    progress = Signal(str)      # 状态提示

    # 工业场景专业提示词（提升中文术语识别准确率）
    INITIAL_PROMPT = (
        "工业机器人打磨工艺参数指令：体素下采样尺寸，曲面拟合平滑度，"
        "打磨头类型，刀具半径，路径生成步距，恒力，转速，强制翻转法向量。"
    )

    def run(self):
        """
        线程执行体

        流程：
        1. 打开麦克风采集音频（speech_recognition）
        2. 转换为 numpy 数组
        3. 使用 faster-whisper GPU 推理转写
        4. 发送识别结果
        """
        recognizer = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                self.progress.emit("🎤 请说话，正在聆听指令...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)

                self.progress.emit("⏳ 录音结束，GPU 引擎识别中 (faster-whisper medium + CUDA)...")

                # 将 AudioData 转为 16kHz float32 numpy 数组
                raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

                # GPU 推理
                model = _get_model()
                segments, _ = model.transcribe(
                    samples,
                    language="zh",
                    beam_size=5,
                    initial_prompt=self.INITIAL_PROMPT,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=300,
                    )
                )

                # 拼接所有片段
                text = "".join(segment.text for segment in segments).strip()

                if not text:
                    raise ValueError("未能识别出有效声音")

                self.progress.emit(f"✅ 识别完成：{text}")
                self.finished.emit(text)

        except sr.WaitTimeoutError:
            self.error.emit("未检测到声音，已超时退出。")
        except Exception as e:
            self.error.emit(f"语音识别异常: {str(e)}")
