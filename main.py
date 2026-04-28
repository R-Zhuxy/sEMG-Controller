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

import numpy as np

# Windows 终端强制 UTF-8 输出，防止 GBK 编码错误
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace',
        line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding='utf-8', errors='replace',
        line_buffering=True
    )

from src.semg.config import SystemConfig
from src.semg.core.ring_buffer import RingBuffer
from src.semg.communication.serial_reader import SerialReader
from src.semg.processing.filters import SignalFilter
from src.semg.processing.envelope import EnvelopeExtractor
from src.semg.processing.calibration import Calibrator
from src.semg.classification.schmitt_trigger import SchmittTrigger, MuscleState
from src.semg.action.key_mapper import KeyMapper


def setup_logging() -> None:
    """配置日志系统"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('semg_session.log', encoding='utf-8'),
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
    3. 对数据进行滤波 + 包络提取
    4. 计算阈值
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

    # 取出校准数据并处理
    raw_data = buffer.get_latest(samples_needed)
    filtered_data = sig_filter.apply_batch(raw_data)
    envelope_data = envelope_ext.extract(filtered_data)

    # 重置流式滤波器状态（校准用了 batch 模式，不影响流式状态）
    sig_filter.reset()

    # 计算阈值
    return calibrator.compute_thresholds(envelope_data)


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

    # 优雅退出处理
    shutdown_flag = False

    def signal_handler(signum, frame):
        nonlocal shutdown_flag
        shutdown_flag = True
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

        window_size = config.buffer.processing_window_size
        last_status_time = time.time()
        cycle_count = 0

        while not shutdown_flag:
            # 检查是否有足够的新数据
            if buffer.count < window_size:
                time.sleep(0.01)
                continue

            # 取最新窗口数据
            raw_window = buffer.get_latest(window_size)

            # 滤波
            filtered = sig_filter.apply(raw_window)

            # 包络提取 (取最后一个值作为当前包络)
            envelope = envelope_ext.extract(filtered)
            current_envelope = float(envelope[-1]) if len(envelope) > 0 else 0.0

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
                    f"cycles={cycle_count}"
                )
                last_status_time = now

            # 控制处理频率 (~100Hz 处理循环)
            time.sleep(0.01)

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
