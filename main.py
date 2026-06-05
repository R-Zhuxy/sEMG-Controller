"""
sEMG 体感交互控制系统 - 主程序入口

组装并运行完整的信号处理流水线 (Pipeline):
  串口读取 → 滤波 → 包络提取 → 校准 → 施密特触发 → 键盘注入
"""

import io
import sys
import time
import signal
import logging
import threading
from logging.handlers import RotatingFileHandler

import numpy as np

# Windows 终端强制 UTF-8 输出，防止 GBK 编码错误
if sys.platform == 'win32' and __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace',
        line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding='utf-8', errors='replace',
        line_buffering=True
    )

import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from semg.config import SystemConfig
from semg.core.ring_buffer import RingBuffer
from semg.communication.serial_reader import SerialReader
from semg.processing.filters import SignalFilter
from semg.processing.envelope import EnvelopeExtractor
from semg.processing.calibration import Calibrator
from semg.classification.schmitt_trigger import SchmittTrigger, MuscleState
from semg.action.key_mapper import KeyMapper


def setup_logging() -> None:
    """配置日志系统，限制日志文件大小并自动轮转，防止无限增长 (F-13)"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            # 使用 RotatingFileHandler 限制单个文件最大 5MB，保留最多 3 个备份
            RotatingFileHandler(
                'semg_session.log',
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding='utf-8'
            ),
        ]
    )


def print_banner() -> None:
    """打印系统启动横幅"""
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║                                                      ║
    ║   sEMG 体感交互控制系统  v0.1.0                      ║
    ║   Single-Channel sEMG Interactive Control System     ║
    ║                                                      ║
    ║   模式: 持续按住 (keyDown / keyUp)                   ║
    ║   按键: [SPACE]                                      ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
    """)


def run_calibration(
    buffer: RingBuffer,
    sig_filter: SignalFilter,
    envelope_ext: EnvelopeExtractor,
    calibrator: Calibrator,
    config: SystemConfig
):
    """
    执行自适应校准流程

    1. 提示用户保持放松
    2. 等待采集足够的静息数据
    3. 对数据进行流式滤波 + 流式包络提取 (与实时处理完全一致的相位)
    4. 计算阈值

    重要设计决策:
      校准使用流式 apply() 而非 apply_batch(filtfilt)，确保阈值基准
      与实时运行完全一致 (相同的群延迟和相位特性)。
      校准结束后不重置滤波器状态，使主循环自然衔接。
    """
    samples_needed = int(
        config.calibration.calibration_duration * config.sampling.sample_rate
    )

    print(f"\n  [*] 正在采集校准数据...")
    print(f"     请保持肌肉完全放松 {config.calibration.calibration_duration} 秒")
    print(f"     需要采集 {samples_needed} 个采样点\n")

    # 等待足够的样本
    start_time = time.time()
    while buffer.count < samples_needed:
        elapsed = time.time() - start_time
        if elapsed > config.calibration.calibration_duration + 10.0:
            raise TimeoutError(
                f"校准超时: 期望 {samples_needed} 个采样点, "
                f"仅收到 {buffer.count} 个"
            )
        # 显示进度
        progress = min(buffer.count / samples_needed * 100, 100)
        print(f"\r     进度: {progress:5.1f}% ({buffer.count}/{samples_needed})", end="")
        time.sleep(0.2)

    print(f"\r     进度: 100.0% ({samples_needed}/{samples_needed})")

    # 取出校准数据并用流式滤波处理 (与实时 apply 相位一致)
    raw_data = buffer.get_latest(samples_needed)
    filtered_data = sig_filter.apply(raw_data)
    envelope_data = envelope_ext.extract(filtered_data)

    # 推进 read_new 读指针，跳过校准期间已处理的数据
    buffer.read_new()

    # F-08: 裁掉 DSP 暖机暂态 (滤波器 settling + RMS滑窗 + 平滑滑窗)
    # 避免开头由于滑动窗口未填满造成的低瞬态包络值污染基线计算 (拉低 mean 且拉高 std)
    warmup_samples = max(
        config.envelope.rms_window_size + config.envelope.smoothing_window_size,
        int(0.1 * config.sampling.sample_rate)  # 至少保证 100ms 暖机切除
    )
    envelope_steady = envelope_data[warmup_samples:]

    # 注意：不重置滤波器/包络状态！
    # 校准数据就是实际信号流的开头，后续主循环的 apply() 自然衔接此处的 zi 状态。

    # 计算阈值 (使用已裁去暖机暂态的稳态包络数据)
    return calibrator.compute_thresholds(envelope_steady)


def main() -> None:
    """主函数 - 组装并运行 Pipeline"""
    setup_logging()
    logger = logging.getLogger('main')
    print_banner()

    config = SystemConfig()

    # ── 1. 初始化各组件 ──────────────────────────────────
    logger.info("初始化系统组件...")

    buffer = RingBuffer(capacity=config.buffer.ring_buffer_size)
    reader = SerialReader(config=config.serial, buffer=buffer)
    sig_filter = SignalFilter(config.filter, config.sampling)
    envelope_ext = EnvelopeExtractor(config.envelope)
    calibrator = Calibrator(config.calibration, config.schmitt)
    key_mapper = KeyMapper(config.action)

    # F-14: 优雅退出处理 (使用 Event 确保高并发和无 GIL 下的线程与写入原子性)
    shutdown_event = threading.Event()

    def signal_handler(signum, frame):
        shutdown_event.set()
        print("\n\n  [!] 收到中断信号，正在安全退出...")

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # ── 2. 启动串口读取 ──────────────────────────────
        print("  [>] 正在连接 Arduino...")
        print(f"     端口: {config.serial.port}")
        print(f"     波特率: {config.serial.baud_rate}")

        reader.start()

        if not reader.wait_for_connection(timeout=15.0):
            print("\n  [X] 无法连接到 Arduino，请检查:")
            print("    - USB 线是否连接")
            print(f"    - 端口 {config.serial.port} 是否正确")
            print("    - Arduino 是否已烧录固件")
            return

        print("  [OK] Arduino 已连接\n")

        # ── 3. 自适应校准 ────────────────────────────────
        cal_result = run_calibration(
            buffer, sig_filter, envelope_ext, calibrator, config
        )

        # 初始化施密特触发器 (使用校准得到的阈值)
        trigger = SchmittTrigger(
            high_threshold=cal_result.high_threshold,
            low_threshold=cal_result.low_threshold,
            debounce_time=config.schmitt.debounce_time,
            min_activation_time=config.schmitt.min_activation_time
        )

        # ── 4. 主处理循环 ────────────────────────────────
        print("  [OK] 系统就绪! 开始实时控制")
        print("       发力时自动按下 [SPACE]，放松时自动松开")
        print("       按 Ctrl+C 安全退出\n")
        print(f"  {'-' * 50}")

        last_status_time = time.time()
        cycle_count = 0
        current_envelope = 0.0

        while not shutdown_event.is_set():
            # 只读取未消费的全新样本 (不重叠！)
            new_samples = buffer.read_new()
            if len(new_samples) == 0:
                # 限制处理周期，并能在收到退出信号时立即响应
                shutdown_event.wait(timeout=0.005)
                continue

            # 流式滤波 (输入严格为新数据，IIR 状态正确累积)
            filtered = sig_filter.apply(new_samples)

            # 流式包络提取 (内部维护滑动 RMS + 平滑状态)
            envelope = envelope_ext.extract(filtered)
            current_envelope = float(envelope[-1])

            # 施密特触发器判定
            state_change = trigger.update(current_envelope)

            # 状态跳变时执行按键动作
            if state_change is not None:
                key_mapper.on_state_change(state_change)

            cycle_count += 1

            # 定期打印状态 (每 2 秒)
            now = time.time()
            if now - last_status_time >= 2.0:
                state_str = (
                    ">> ACTIVATED" if trigger.state == MuscleState.ACTIVATED
                    else "-- RELAXED  "
                )
                print(
                    f"  [{state_str}] "
                    f"envelope={current_envelope:.4f} "
                    f"threshold=[{cal_result.low_threshold:.4f}, "
                    f"{cal_result.high_threshold:.4f}] "
                    f"samples={reader.sample_count} "
                    f"errors={reader.error_count} "
                    f"cycles={cycle_count}"
                )
                last_status_time = now

            # 控制处理频率 (~200Hz 处理循环)，使用 wait 代替 sleep，提高响应及时性
            shutdown_event.wait(timeout=0.005)

    except TimeoutError as e:
        logger.error(f"超时错误: {e}")
        print(f"\n  [X] {e}")
    except Exception as e:
        logger.exception(f"未预期的错误: {e}")
        print(f"\n  [X] 系统错误: {e}")
    finally:
        # ── 5. 安全退出 ──────────────────────────────────
        print(f"\n  {'-' * 50}")
        print("  [..] 正在关闭系统...")
        key_mapper.release_all()
        reader.stop()
        print(f"  [OK] 本次会话共采集 {reader.sample_count} 个采样点")
        print("  [OK] 系统已安全退出\n")


if __name__ == "__main__":
    main()
