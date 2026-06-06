"""
sEMG 体感交互控制与数据录制包装脚本

运行此脚本可同步进行小恐龙体感游戏演示，并在后台自动记录完整的原始 sEMG 数据流。
退出 (Ctrl+C) 后，数据将自动导出为 data/raw_emg_record.csv 供报告绘图系统读取。
"""

import io
import os
import sys
import time
import signal
import logging
import threading
from logging.handlers import RotatingFileHandler
import numpy as np

# Windows 终端强制 UTF-8 输出，防止编码错误
if sys.platform == 'win32' and __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace',
        line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding='utf-8', errors='replace',
        line_buffering=True
    )

# 将项目 src 目录和项目根目录加入 Python 搜索路径，以便能导入 src 下的代码和 main.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from semg.config import SystemConfig
from semg.core.ring_buffer import RingBuffer
from semg.communication.serial_reader import SerialReader
from semg.processing.filters import SignalFilter
from semg.processing.envelope import EnvelopeExtractor
from semg.processing.calibration import Calibrator
from semg.classification.schmitt_trigger import SchmittTrigger, MuscleState
from semg.action.key_mapper import KeyMapper

# 复用 main.py 中的日志和校准方法
from main import setup_logging, print_banner, run_calibration

def main() -> None:
    setup_logging()
    logger = logging.getLogger('run_with_recording')
    print_banner()
    
    print("""
    * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
    *  [数据录制模式启动]                                    *
    *  本会话将录制您完整的原始肌电信号，并在退出时自动保存！   *
    *  请确保在启动的前 3 秒校准期内，肌肉保持完全放松。      *
    * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
    """)

    config = SystemConfig()
    
    # 建立保存数据的文件夹
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, 'raw_emg_record.csv')

    # 初始化系统组件
    buffer = RingBuffer(capacity=config.buffer.ring_buffer_size)
    reader = SerialReader(config=config.serial, buffer=buffer)
    sig_filter = SignalFilter(config.filter, config.sampling)
    envelope_ext = EnvelopeExtractor(config.envelope)
    calibrator = Calibrator(config.calibration, config.schmitt)
    key_mapper = KeyMapper(config.action)

    shutdown_event = threading.Event()
    recorded_samples = []  # 用于保存整个会话的所有原始 ADC 样本

    def signal_handler(signum, frame):
        shutdown_event.set()
        print("\n\n  [!] 收到中断信号，正在退出并保存数据...")

    signal.signal(signal.SIGINT, signal_handler)

    try:
        print("  [>] 正在连接 Arduino...")
        print(f"     端口: {config.serial.port} (波特率: {config.serial.baud_rate})")
        reader.start()

        if not reader.wait_for_connection(timeout=15.0):
            print("\n  [X] 无法连接到 Arduino，请检查物理连接和端口设置")
            return

        print("  [OK] Arduino 已连接\n")

        # ── 1. 自适应校准 ────────────────────────────────
        cal_result = run_calibration(
            buffer, sig_filter, envelope_ext, calibrator, config
        )

        # 记录校准期间的原始数据样本
        # 由于主循环尚未开始，当前缓冲区中的样本对应校准期数据
        samples_needed = int(config.calibration.calibration_duration * config.sampling.sample_rate)
        cal_raw_samples = buffer.get_latest(samples_needed)
        recorded_samples.extend(cal_raw_samples)
        logger.info(f"已录制校准期间原始数据点数: {len(cal_raw_samples)}")

        # 初始化触发器
        trigger = SchmittTrigger(
            high_threshold=cal_result.high_threshold,
            low_threshold=cal_result.low_threshold,
            debounce_time=config.schmitt.debounce_time,
            min_activation_time=config.schmitt.min_activation_time
        )

        # ── 2. 主控制与录制循环 ──────────────────────────
        print("  [OK] 系统就绪! 开始实时控制并同步录制")
        print("       发力时自动按下 [SPACE]，放松时自动松开")
        print("       现在您可以按照自己的意志自由操作，按 Ctrl+C 退出并保存波形")
        print(f"  {'-' * 50}")

        last_status_time = time.time()
        cycle_count = 0

        while not shutdown_event.is_set():
            new_samples = buffer.read_new()
            if len(new_samples) == 0:
                shutdown_event.wait(timeout=0.005)
                continue

            # 同步录制当前周期的原始 ADC 数值
            recorded_samples.extend(new_samples)

            # 流式处理
            filtered = sig_filter.apply(new_samples)
            envelope = envelope_ext.extract(filtered)
            current_envelope = float(envelope[-1])

            # 触发判定与键盘注入
            state_change = trigger.update(current_envelope)
            if state_change is not None:
                key_mapper.on_state_change(state_change)

            cycle_count += 1

            # 每 2 秒控制台打印一次状态
            now = time.time()
            if now - last_status_time >= 2.0:
                state_str = (
                    ">> ACTIVATED" if trigger.state == MuscleState.ACTIVATED
                    else "-- RELAXED  "
                )
                print(
                    f"  [{state_str}] "
                    f"envelope={current_envelope:.4f} "
                    f"threshold=[{cal_result.low_threshold:.4f}, {cal_result.high_threshold:.4f}] "
                    f"total_recorded={len(recorded_samples)} "
                    f"errors={reader.error_count}"
                )
                last_status_time = now

            shutdown_event.wait(timeout=0.005)

    except TimeoutError as e:
        logger.error(f"超时错误: {e}")
        print(f"\n  [X] {e}")
    except Exception as e:
        logger.exception(f"运行时错误: {e}")
        print(f"\n  [X] 运行时发生错误: {e}")
    finally:
        # 安全退出
        print(f"\n  {'-' * 50}")
        print("  [..] 正在安全关闭控制连接...")
        key_mapper.release_all()
        reader.stop()
        
        # 写入 CSV 文件保存原始信号数据
        if len(recorded_samples) > 0:
            print(f"  [..] 正在将 {len(recorded_samples)} 个原始 ADC 样本保存到 CSV...")
            try:
                np.savetxt(csv_path, recorded_samples, fmt='%d')
                print(f"  [OK] 数据成功保存至: {os.path.abspath(csv_path)}")
                print("       您现在可以运行 python report/generate_report.py 来更新报告图表了！")
            except Exception as e:
                logger.error(f"保存 CSV 失败: {e}")
                print(f"  [X] 保存数据失败: {e}")
        else:
            print("  [!] 未录制到有效数据点，未生成 CSV 文件")
            
        print("  [OK] 演示与录制会话已安全退出\n")

if __name__ == "__main__":
    main()
