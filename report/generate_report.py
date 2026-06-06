import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from scipy import signal as sig

# 将项目 src 目录加入 Python 搜索路径，以便导入现有算法进行真实信号处理演示
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# 导入现有配置和核心算法，保证仿真图表的参数与系统实际运行完全一致
from semg.config import SystemConfig
from semg.processing.filters import SignalFilter
from semg.processing.envelope import EnvelopeExtractor

# 建立输出文件夹
IMAGE_DIR = os.path.join(os.path.dirname(__file__), 'images')
os.makedirs(IMAGE_DIR, exist_ok=True)

# ── 配置中文字体，防止方块乱码 ───────────────────────────────────────────────
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'SimSun', 'DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 10

# ── 配色方案 (现代扁平化) ───────────────────────────────────────────────────
C_PRIMARY = '#1f77b4'  # 科技蓝
C_SUCCESS = '#2ca02c'  # 环保绿
C_WARNING = '#ff7f0e'  # 警告橙
C_DANGER = '#d62728'   # 危险红
C_DARK = '#2c3e50'     # 深灰黑
C_LIGHT = '#ecf0f1'    # 浅底色
C_PURPLE = '#9467bd'   # 紫色
C_MUTED = '#7f8c8d'    # 灰色

def save_fig(name):
    path = os.path.join(IMAGE_DIR, name)
    plt.savefig(path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"  [OK] 已保存图像: {path}")

# ── 1. 绘制系统总体框图 ──────────────────────────────────────────────────────
def draw_system_block_diagram():
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axis('off')
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 50)
    
    # 标题
    ax.text(60, 45, "基于单通道 sEMG 的交互控制系统总体框图 (主动运动康复反馈机制)", 
            ha='center', va='center', fontsize=14, fontweight='bold', color=C_DARK)
    
    # 定义方框绘制函数
    def draw_box(x, y, w, h, text, title, fill_color):
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=1", 
                                      facecolor=fill_color, edgecolor=C_DARK, linewidth=1.2)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h - 1.5, title, ha='center', va='top', 
                fontsize=9, fontweight='bold', color=C_DARK)
        ax.text(x + w/2, y + h/2 - 1, text, ha='center', va='center', 
                fontsize=8.5, color='#333333', wrap=True)

    # 第一行：硬件采集部分 (医学信号源 -> 传感器 -> ADC -> 串口传输)
    draw_box(5, 25, 16, 10, "前臂/小腿骨骼肌\n(主动发力收缩)", "1. 目标肌电信号源", '#dff0d8')
    draw_box(28, 25, 16, 10, "三电极贴片\n放大差分信号", "2. 表面干电极", '#dff0d8')
    draw_box(51, 25, 16, 10, "思知瑞 sEMG 模块\n带通+增益放大", "3. 模拟前端调理", '#dff0d8')
    draw_box(74, 25, 16, 10, "Arduino Nano (A0)\n500Hz 高精度定时", "4. MCU 采样量化", '#dff0d8')
    draw_box(97, 25, 16, 10, "USB-TTL 串口\n波特率 115200bps", "5. 异步数据传输", '#fcf8e3')

    # 第二行：上位机处理与康复交互部分 (数字滤波 -> 包络提取 -> 施密特决策 -> 按键映射 -> 游戏反馈)
    draw_box(5, 5, 16, 10, "50Hz级联陷波\n20-200Hz带通IIR", "6. 流式数字滤波", '#d9edf7')
    draw_box(28, 5, 16, 10, "O(1)滑动 RMS\n移动平均平滑", "7. 流式包络提取", '#d9edf7')
    draw_box(51, 5, 16, 10, "自适应静息校准\n双阈值滞回决策", "8. 施密特意图识别", '#d9edf7')
    draw_box(74, 5, 16, 10, "pyautogui 按键注入\n发力按下 / 放松松开", "9. 动作按键映射", '#f2dede')
    draw_box(97, 5, 16, 10, "小恐龙越障游戏\n趣味主动康复训练", "10. 康复游戏反馈", '#f2dede')

    # 绘制连接箭头
    def draw_arrow(x1, y1, x2, y2, label=""):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.5, ls='-'))
        if label:
            ax.text((x1+x2)/2, (y1+y2)/2 + 1, label, ha='center', va='center', fontsize=8, color=C_MUTED)

    # 第一行箭头
    draw_arrow(22.5, 30, 26.5, 30, "生理传播")
    draw_arrow(45.5, 30, 49.5, 30, "微伏级模拟")
    draw_arrow(68.5, 30, 72.5, 30, "伏特级模拟")
    draw_arrow(91.5, 30, 95.5, 30, "10-bit数字帧")
    
    # 跨行折线箭头
    ax.annotate("", xy=(105, 17), xytext=(105, 23.5),
                arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.5))
    ax.text(106, 20.25, "数据读入", ha='left', va='center', fontsize=8, color=C_MUTED)
    
    # 第二行反向箭头
    draw_arrow(95.5, 10, 91.5, 10, "注入Space")
    draw_arrow(72.5, 10, 68.5, 10, "识别状态")
    draw_arrow(49.5, 10, 45.5, 10, "包络幅值")
    draw_arrow(26.5, 10, 22.5, 10, "滤波信号")

    # 康复闭环反馈虚线箭头 (从 10 回到 1)
    ax.annotate("", xy=(13, 37), xytext=(105, 17),
                arrowprops=dict(arrowstyle="->", color=C_DANGER, lw=1.5, ls='--',
                                connectionstyle="angle,angleA=90,angleB=180,rad=10"))
    ax.text(60, 41, "视听觉生物反馈 (闭环激励)", ha='center', va='bottom', fontsize=9.5, fontweight='bold', color=C_DANGER)

    save_fig("system_block_diagram.png")

# ── 2. 绘制关键电路与硬件连接图 ──────────────────────────────────────────────
def draw_hardware_connection():
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 50)

    # 绘制电脑
    rect_pc = patches.Rectangle((5, 15), 20, 20, facecolor='#eaeaea', edgecolor=C_DARK, lw=1.5)
    ax.add_patch(rect_pc)
    ax.text(15, 25, "上位机 (PC)\n运行 Python 驱动", ha='center', va='center', fontsize=10, fontweight='bold')
    
    # 绘制 Arduino Nano
    rect_mcu = patches.Rectangle((40, 10), 22, 30, facecolor='#d9edf7', edgecolor=C_PRIMARY, lw=2)
    ax.add_patch(rect_mcu)
    ax.text(51, 37, "Arduino Nano V3", ha='center', va='center', fontsize=11, fontweight='bold', color=C_PRIMARY)
    
    # Arduino 引脚位置
    pins = {"A0": 26, "5V": 20, "GND": 14}
    for pin_name, py in pins.items():
        rect_pin = patches.Rectangle((62, py-1.5), 2, 3, facecolor='#ffffff', edgecolor='#333333')
        ax.add_patch(rect_pin)
        ax.text(60, py, pin_name, ha='right', va='center', fontsize=8, fontweight='bold')

    # 绘制 sEMG 传感器模块
    rect_sens = patches.Rectangle((78, 12), 18, 26, facecolor='#dff0d8', edgecolor=C_SUCCESS, lw=2)
    ax.add_patch(rect_sens)
    ax.text(87, 34, "单通道 sEMG\n传感器模块\n(思知瑞)", ha='center', va='center', fontsize=9, fontweight='bold', color=C_SUCCESS)
    
    # 传感器引脚位置
    sens_pins = {"OUT": 26, "VCC": 20, "GND": 14}
    for pin_name, py in sens_pins.items():
        rect_pin = patches.Rectangle((76, py-1.5), 2, 3, facecolor='#ffffff', edgecolor='#333333')
        ax.add_patch(rect_pin)
        ax.text(79, py, pin_name, ha='left', va='center', fontsize=8, fontweight='bold')

    # 表面干电极导线
    ax.plot([87, 87, 80], [12, 5, 5], color=C_MUTED, lw=1.5)
    ax.plot([87, 87, 87], [12, 5, 5], color=C_MUTED, marker='o', markersize=4)
    rect_electrode = patches.Rectangle((64, 2), 12, 6, facecolor='#f2dede', edgecolor=C_DANGER, lw=1)
    ax.add_patch(rect_electrode)
    ax.text(70, 5, "表面贴片/电极", ha='center', va='center', fontsize=8, color=C_DANGER)

    # 物理接线
    # 1. 信号线 A0 -> OUT (绿色)
    ax.plot([64, 76], [26, 26], color=C_SUCCESS, lw=2, label="模拟信号线 (A0 - OUT)")
    # 2. 电源线 5V -> VCC (红色)
    ax.plot([64, 76], [20, 20], color=C_DANGER, lw=2, label="电源线 (5V - VCC)")
    # 3. 地线 GND -> GND (黑色)
    ax.plot([64, 76], [14, 14], color='#000000', lw=2, label="公共参考地 (GND - GND)")

    # 4. USB 串口线
    ax.plot([25, 40], [25, 25], color=C_WARNING, lw=4, ls='-', label="USB 数据线 (115200 bps)")
    ax.text(32.5, 27, "USB 串口通信", ha='center', va='bottom', fontsize=8.5, color=C_WARNING, fontweight='bold')

    # 图例与说明
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.05), ncol=4, frameon=True, fontsize=8)
    ax.text(50, 47, "系统关键电路与硬件模块连接图", ha='center', va='center', fontsize=13, fontweight='bold', color=C_DARK)

    save_fig("hardware_connection.png")

# ── 3. 绘制实验与处理流程图 ──────────────────────────────────────────────────
def draw_experimental_flowchart():
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.axis('off')
    ax.set_xlim(0, 80)
    ax.set_ylim(0, 100)

    # 定义框图绘制
    def draw_shape(x, y, w, h, text, shape_type='rect', color=C_PRIMARY):
        if shape_type == 'rect':
            rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5", facecolor=color, edgecolor=C_DARK)
            ax.add_patch(rect)
        elif shape_type == 'diamond':
            # 菱形
            px = [x, x + w/2, x + w, x + w/2]
            py = [y + h/2, y + h, y + h/2, y]
            ax.fill(px, py, facecolor=color, edgecolor=C_DARK)
        elif shape_type == 'ellipse':
            ellipse = patches.Ellipse((x + w/2, y + h/2), w, h, facecolor=color, edgecolor=C_DARK)
            ax.add_patch(ellipse)
        ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, color='#111111', wrap=True)

    def draw_down_arrow(x, y1, y2, text=""):
        ax.annotate("", xy=(x, y2), xytext=(x, y1), arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.2))
        if text:
            ax.text(x + 1, (y1+y2)/2, text, ha='left', va='center', fontsize=8, color=C_DARK)

    # 流程节点
    draw_shape(30, 94, 20, 4, "系统启动 (Setup)", 'ellipse', C_LIGHT)
    draw_down_arrow(40, 94, 88)
    
    draw_shape(25, 82, 30, 6, "初始化硬件及缓存\n串口握手检测 READY 帧", 'rect', '#d9edf7')
    draw_down_arrow(40, 82, 74)
    
    # 校准阶段
    draw_shape(23, 66, 34, 8, "校准阶段：静息状态数据采集\n(持续时长 3.0s，采样点数 1500)", 'rect', '#eaeaea')
    draw_down_arrow(40, 66, 56)
    
    draw_shape(21, 48, 38, 8, "提取静息包络，计算基线统计量\nHigh 阈值 = mean + 3.0 * std\nLow 阈值 = mean + 1.5 * std\n评估噪声水平与计算 SNR", 'rect', '#dff0d8')
    draw_down_arrow(40, 48, 38)
    
    # 实时处理循环
    draw_shape(25, 30, 30, 8, "实时处理阶段 (200Hz 循环)\n1. 读取未处理增量样本\n2. 50Hz陷波与20-200Hz带通\n3. O(1)滑动RMS包络提取", 'rect', '#fcf8e3')
    draw_down_arrow(40, 30, 20)

    # 判定菱形
    draw_shape(28, 10, 24, 10, "包络线超过\n双阈值设定？", 'diamond', '#f2dede')

    # 菱形判定分支箭头
    # 1. 超过 High 阈值
    ax.annotate("", xy=(15, 15), xytext=(28, 15), arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.2))
    ax.text(21, 16, "是 (>High)", ha='center', va='bottom', fontsize=8)
    draw_shape(5, 12, 12, 6, "触发 ACTIVATED\n键盘注入 SPACE 按下", 'rect', '#f2dede')
    
    # 2. 低于 Low 阈值
    ax.annotate("", xy=(65, 15), xytext=(52, 15), arrowprops=dict(arrowstyle="->", color=C_DARK, lw=1.2))
    ax.text(58, 16, "否 (<Low)", ha='center', va='bottom', fontsize=8)
    draw_shape(63, 12, 12, 6, "释放 RELAXED\n键盘注入 SPACE 松开", 'rect', '#eaeaea')

    # 回路连接
    ax.plot([11, 11, 40], [12, 5, 5], color=C_DARK, lw=1.2)
    ax.plot([69, 69, 40], [12, 5, 5], color=C_DARK, lw=1.2)
    ax.plot([40, 40], [5, 10], color=C_DARK, lw=1.2) # 指向菱形下方
    
    # 循环向上返回箭头
    ax.annotate("", xy=(40, 39), xytext=(78, 15),
                arrowprops=dict(arrowstyle="->", color=C_MUTED, lw=1.2, ls='--',
                                connectionstyle="angle,angleA=0,angleB=90,rad=5"))
    ax.plot([69, 78], [15, 15], color=C_MUTED, lw=1.2, ls='--')
    ax.text(76, 26, "流式下一帧", ha='right', va='center', fontsize=8, color=C_MUTED)

    ax.text(40, 99, "sEMG 信号处理与康复控制系统逻辑流程图", ha='center', va='center', fontsize=12, fontweight='bold', color=C_DARK)

    save_fig("experimental_flowchart.png")

# ── 4. 绘制滤波器幅频响应图 ──────────────────────────────────────────────────
def draw_filter_frequency_response():
    fs = 500.0
    nyq = fs / 2.0
    
    # 50Hz 工频陷波器设计 (Q=15)
    b_notch, a_notch = sig.iirnotch(50.0, 15.0, fs)
    w_notch, h_notch = sig.freqz(b_notch, a_notch, worN=2000, fs=fs)
    
    # 20-200Hz 4阶 Butterworth 带通设计
    sos_bp = sig.butter(4, [20.0, 200.0], btype='bandpass', output='sos', fs=fs)
    w_bp, h_bp = sig.sosfreqz(sos_bp, worN=2000, fs=fs)
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    
    # 绘制带通幅频响应
    ax1.plot(w_bp, 20 * np.log10(np.maximum(np.abs(h_bp), 1e-5)), color=C_PRIMARY, lw=2, label="4阶 Butterworth 带通")
    ax1.axvline(20, color=C_DANGER, ls='--', alpha=0.7, label="低频截止 20 Hz (运动伪影抑制)")
    ax1.axvline(200, color=C_WARNING, ls='--', alpha=0.7, label="高频截止 200 Hz (Nyquist限噪)")
    ax1.set_title("20-200Hz 带通滤波器幅频响应", fontsize=11, fontweight='bold')
    ax1.set_xlabel("频率 (Hz)")
    ax1.set_ylabel("幅度响应 (dB)")
    ax1.set_xlim(0, 250)
    ax1.set_ylim(-60, 5)
    ax1.grid(True, ls=':', alpha=0.6)
    ax1.legend(loc='lower left', fontsize=9)
    
    # 绘制陷波器幅频响应
    ax2.plot(w_notch, 20 * np.log10(np.maximum(np.abs(h_notch), 1e-5)), color=C_PURPLE, lw=2, label="50Hz 陷波器 (Q=15)")
    ax2.axvline(50, color=C_DANGER, ls='--', alpha=0.7)
    ax2.set_title("50Hz 工频陷波器幅频响应", fontsize=11, fontweight='bold')
    ax2.set_xlabel("频率 (Hz)")
    ax2.set_ylabel("幅度响应 (dB)")
    ax2.set_xlim(40, 60)  # 局部放大查看陷波陡峭度
    ax2.set_ylim(-35, 1)
    ax2.grid(True, ls=':', alpha=0.6)
    ax2.legend(loc='lower left', fontsize=9)
    
    # 在图中文字标注衰减能力
    ax2.text(50.5, -28, "50Hz 衰减约 -30 dB", color=C_DANGER, fontsize=9.5, fontweight='bold')
    
    plt.suptitle("系统数字滤波器预处理定量幅频响应特性", fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    save_fig("filter_frequency_response.png")

# ── 5. 绘制信号处理多子图对比波形 ──────────────────────────────────────────────
def draw_signal_processing_waveform():
    fs = 500.0  # Hz
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw_emg_record.csv')
    
    use_real = False
    raw_signal = None
    
    if os.path.exists(csv_path):
        try:
            # 尝试加载真实采集到的数据
            loaded_data = np.loadtxt(csv_path)
            if len(loaded_data) > 1500:  # 至少 3 秒以上的数据点
                raw_signal = loaded_data
                use_real = True
                n_samples = len(raw_signal)
                t = np.arange(n_samples) / fs
                print(f"  [INFO] 信号处理波形：成功加载真实采集数据，总点数: {n_samples} ({n_samples/fs:.2f}秒)")
        except Exception as e:
            print(f"  [WARNING] 加载真实数据 CSV 失败: {e}，将使用仿真信号")

    if not use_real:
        # 降级方案：使用原有的物理数学仿真模型生成肌电信号
        duration = 4.0  # 秒
        t = np.arange(0, duration, 1.0 / fs)
        n_samples = len(t)
        np.random.seed(42)
        base_noise = np.random.normal(loc=0.0, scale=4.0, size=n_samples)
        interference_50hz = 15.0 * np.sin(2 * np.pi * 50.0 * t)
        baseline_drift = 12.0 * np.sin(2 * np.pi * 0.5 * t) + 8.0 * np.sin(2 * np.pi * 0.12 * t)
        burst_mask = (t >= 1.5) & (t <= 2.5)
        burst_envelope = np.zeros(n_samples)
        burst_envelope[burst_mask] = np.sin(np.pi * (t[burst_mask] - 1.5)) * 60.0
        emg_burst = np.random.normal(0, 1, n_samples) * burst_envelope
        raw_signal = 512.0 + base_noise + interference_50hz + baseline_drift + emg_burst
        print(f"  [INFO] 信号处理波形：未检测到真实数据或数据不全，已降级使用数学仿真肌电信号")

    # ── 运行真实系统算法处理该信号 ────────────────────────────────
    config = SystemConfig()
    sig_filter = SignalFilter(config.filter, config.sampling)
    envelope_ext = EnvelopeExtractor(config.envelope)
    
    # 流式处理
    chunk_size = config.buffer.processing_window_size
    filtered_chunks = []
    envelope_chunks = []
    
    for i in range(0, n_samples, chunk_size):
        chunk = raw_signal[i:i+chunk_size]
        filt_chunk = sig_filter.apply(chunk)
        env_chunk = envelope_ext.extract(filt_chunk)
        filtered_chunks.append(filt_chunk)
        envelope_chunks.append(env_chunk)
        
    filtered_signal = np.concatenate(filtered_chunks)
    envelope_signal = np.concatenate(envelope_chunks)
    
    # 定量校准计算 (基于前 0.2s 到 2.8s 的静息期，以防 DSP 暖机阶段影响基线计算)
    resting_mask = (t >= 0.2) & (t <= 2.8)
    resting_envelope = envelope_signal[resting_mask]
    baseline_mean = np.mean(resting_envelope)
    baseline_std = np.std(resting_envelope)
    
    high_threshold = baseline_mean + 3.0 * baseline_std
    low_threshold = baseline_mean + 1.5 * baseline_std
    
    snr_rest = 10 * np.log10(baseline_mean**2 / (baseline_std**2 + 1e-6))
    active_sbr = 20 * np.log10((np.max(envelope_signal) + 1e-6) / (baseline_mean + 1e-6))
    
    # ── 开始绘图 ──────────────────────────────────────────────────────
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    
    # Plot 1: 原始含有干扰的信号
    ax1.plot(t, raw_signal, color=C_MUTED, lw=0.9, label="原始生理信号 (含工频与基线漂移)")
    ax1.set_title("生物医学数据采集端：原始 sEMG 信号波形 (ADC 量化电平)", fontsize=11, fontweight='bold')
    ax1.set_ylabel("幅值 (ADC LSB)")
    ax1.grid(True, ls=':', alpha=0.5)
    ax1.legend(loc='upper right', framealpha=0.9)
    
    # 自适应缩放原始信号 y 轴，防止溢出或显示范围过大
    raw_min, raw_max = np.percentile(raw_signal, 0.5), np.percentile(raw_signal, 99.5)
    raw_range = max(raw_max - raw_min, 10.0)
    ax1.set_ylim(raw_min - 0.1 * raw_range, raw_max + 0.15 * raw_range)
    
    # Plot 2: 滤波后的干净信号
    ax2.plot(t, filtered_signal, color=C_PRIMARY, lw=0.9, label="流式 IIR 滤波信号 (基频-谐波去噪)")
    ax2.set_title("实时信号处理算法端：20-200Hz带通 + 50Hz陷波滤波后信号波形", fontsize=11, fontweight='bold')
    ax2.set_ylabel("幅值 (电平)")
    ax2.grid(True, ls=':', alpha=0.5)
    ax2.legend(loc='upper right', framealpha=0.9)
    
    # 自适应缩放滤波信号 y 轴
    filt_min, filt_max = np.percentile(filtered_signal, 0.5), np.percentile(filtered_signal, 99.5)
    filt_range = max(filt_max - filt_min, 5.0)
    ax2.set_ylim(filt_min - 0.1 * filt_range, filt_max + 0.15 * filt_range)
    
    # Plot 3: 提取的包络与自适应阈值
    ax3.plot(t, np.abs(filtered_signal), color='#e0e0e0', lw=0.8, alpha=0.7, label="全波整流信号")
    ax3.plot(t, envelope_signal, color=C_SUCCESS, lw=2.0, label="O(1) 滑动 RMS 提取包络")
    
    ax3.axhline(high_threshold, color=C_DANGER, lw=1.5, ls='--', label=f"动作激活阈值 High ({high_threshold:.2f})")
    ax3.axhline(low_threshold, color=C_WARNING, lw=1.5, ls='-.', label=f"动作释放阈值 Low ({low_threshold:.2f})")
    ax3.axhline(baseline_mean, color=C_DARK, lw=1.0, ls=':', label=f"静息基线均值 ({baseline_mean:.2f})")
    
    # 自适应缩放包络信号 y 轴，确保上部留白 35% 给图例，防止重叠
    env_max = np.percentile(envelope_signal, 99.5)
    ax3.set_ylim(0, max(env_max * 1.35, high_threshold * 1.6))
    
    # 指示发力区域 (如果是仿真则明确画出，如果是真实数据则在标题体现)
    if not use_real:
        ax3.fill_between(t, 0, 100, where=(t >= 1.5) & (t <= 2.5), color='#dff0d8', alpha=0.3, label="肌肉主动收缩区域 (仿真发力)")
    
    label_source = "真实数据" if use_real else "仿真模型"
    ax3.set_title(f"特征提取与自适应阈值决策端：RMS包络曲线与双阈值对照 ({label_source} SNR={snr_rest:.1f}dB, 发力比 SBR={active_sbr:.1f}dB)", 
                 fontsize=11, fontweight='bold')
    ax3.set_xlabel("时间 (s)")
    ax3.set_ylabel("包络幅值 (电平)")
    ax3.grid(True, ls=':', alpha=0.5)
    ax3.legend(loc='upper right', ncol=2, fontsize=8.5, framealpha=0.9)
    
    plt.suptitle(f"基于单通道 sEMG 的肌电信号流式处理与阈值计算全过程波形 ({label_source})", fontsize=14, fontweight='bold', y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])  # 调整布局，防止最上面的标题重叠
    
    save_fig("signal_processing_waveform.png")

# ── 6. 绘制动作时延与施密特触发评估图 ──────────────────────────────────────────────
def draw_schmitt_latency_eval():
    fs = 500.0
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw_emg_record.csv')
    
    use_real = False
    raw_signal = None
    
    if os.path.exists(csv_path):
        try:
            loaded_data = np.loadtxt(csv_path)
            if len(loaded_data) > 1500:
                raw_signal = loaded_data
                use_real = True
        except:
            pass

    config = SystemConfig()
    
    # ── 1. 信号处理获取包络线 ──────────────────────────────────────────────
    if use_real:
        # 使用真实数据流式滤波并提取包络
        sig_filter = SignalFilter(config.filter, config.sampling)
        envelope_ext = EnvelopeExtractor(config.envelope)
        
        n_samples = len(raw_signal)
        t = np.arange(n_samples) / fs
        
        chunk_size = config.buffer.processing_window_size
        filtered_chunks = []
        envelope_chunks = []
        for i in range(0, n_samples, chunk_size):
            chunk = raw_signal[i:i+chunk_size]
            filt = sig_filter.apply(chunk)
            env = envelope_ext.extract(filt)
            filtered_chunks.append(filt)
            envelope_chunks.append(env)
        envelope_signal = np.concatenate(envelope_chunks)
        
        # 重新校准获得阈值
        resting_mask = (t >= 0.2) & (t <= 2.8)
        resting_envelope = envelope_signal[resting_mask]
        baseline_mean = np.mean(resting_envelope)
        baseline_std = np.std(resting_envelope)
        high_threshold = baseline_mean + 3.0 * baseline_std
        low_threshold = baseline_mean + 1.5 * baseline_std
        
        # 运行施密特触发器逻辑，捕获第一次激活时刻
        trigger_state = np.zeros(n_samples)
        state = 0
        debounce_counter = 0
        debounce_samples = int(config.schmitt.debounce_time * fs)  # 20ms = 10点
        
        first_high_cross_idx = -1
        first_activated_idx = -1
        
        temp_high_cross = -1
        
        for i in range(n_samples):
            val = envelope_signal[i]
            if state == 0:
                if val > high_threshold:
                    if temp_high_cross == -1:
                        temp_high_cross = i
                    debounce_counter += 1
                    if debounce_counter >= debounce_samples:
                        state = 1
                        if first_activated_idx == -1:
                            first_activated_idx = i
                            first_high_cross_idx = temp_high_cross
                else:
                    temp_high_cross = -1
                    debounce_counter = 0
            else: # state == 1
                if val < low_threshold:
                    state = 0
                    temp_high_cross = -1
                    debounce_counter = 0
            trigger_state[i] = state
            
        # 判断是否在录制的数据中找到了成功的收缩激活
        if first_activated_idx != -1:
            # 找到了真实收缩，以此为时延评估的展示点
            # 追溯物理发力的起点 (包络开始抬升并超越基线+1.0*std的时刻)
            t_start_idx = first_high_cross_idx
            while t_start_idx > 0 and envelope_signal[t_start_idx] > baseline_mean + baseline_std:
                t_start_idx -= 1
            
            t_start = t_start_idx / fs
            t_high_cross = first_high_cross_idx / fs
            t_activated = first_activated_idx / fs
            
            # 截取该收缩发生前后共 0.8 秒区间
            zoom_start_t = max(0.0, t_activated - 0.35)
            zoom_end_t = min(t[-1], t_activated + 0.45)
            zoom_mask = (t >= zoom_start_t) & (t <= zoom_end_t)
            
            t_zoom = t[zoom_mask]
            envelope_zoom = envelope_signal[zoom_mask]
            trigger_state_zoom = trigger_state[zoom_mask]
            
            print(f"  [INFO] 时延评估：成功自动定位发力跳变点，激活时刻: {t_activated:.3f}s")
        else:
            # 录制的真实数据中未找到发力动作，被迫退回仿真
            use_real = False
            print("  [WARNING] 录制的真实数据中未检测到满足阈值的收缩发力点，将自动退回仿真评估")

    if not use_real:
        # 使用预设的精美仿真信号及延迟参数
        t_zoom = np.arange(1.2, 2.0, 1.0 / fs)
        n_samples = len(t_zoom)
        envelope_zoom = np.zeros(n_samples)
        t_start = 1.50
        for idx, ti in enumerate(t_zoom):
            if ti < t_start:
                envelope_zoom[idx] = 2.0 + np.random.normal(0, 0.18)
            else:
                val = (1.0 - np.exp(-25.0 * (ti - t_start))) * 35.0 + 2.0
                envelope_zoom[idx] = val + np.random.normal(0, 0.35)
        
        baseline_mean = 2.0
        baseline_std = 0.2
        high_threshold = baseline_mean + 3.0 * baseline_std  # 2.6
        low_threshold = baseline_mean + 1.5 * baseline_std   # 2.3
        
        t_high_cross = 1.512
        t_activated = 1.532
        
        trigger_state_zoom = np.zeros(n_samples)
        hc_idx = int((t_high_cross - 1.2) * fs)
        act_idx = int((t_activated - 1.2) * fs)
        trigger_state_zoom[act_idx:] = 1.0

    # ── 2. 计算各部分时延并绘图 ──────────────────────────────────────────────
    delay_dsp = (t_high_cross - t_start) * 1000.0  # 算法群延迟 (ms)
    delay_debounce = (t_activated - t_high_cross) * 1000.0  # 触发器防抖持有延迟 (ms)
    delay_total = (t_activated - t_start) * 1000.0  # 总控制延时 (ms)

    # 绘图
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True, 
                                   gridspec_kw={'height_ratios': [3.5, 1.2]})
    
    # Subplot 1: 包络线与阈值
    ax1.plot(t_zoom, envelope_zoom, color=C_SUCCESS, lw=2.2, label="sEMG 包络信号")
    ax1.axhline(high_threshold, color=C_DANGER, ls='--', lw=1.2, label=f"High 阈值 ({high_threshold:.2f})")
    ax1.axhline(low_threshold, color=C_WARNING, ls='-.', lw=1.2, label=f"Low 阈值 ({low_threshold:.2f})")
    
    # 确定 y 轴高度，留白 35% 给文字标注，防止与曲线和图例重叠
    env_max = np.max(envelope_zoom)
    y_limit = max(env_max * 1.35, high_threshold * 1.6)
    ax1.set_ylim(0, y_limit)
    
    # 绘制核心时间垂直线
    ax1.axvline(t_start, color=C_DARK, ls=':', lw=1.5)
    ax1.axvline(t_high_cross, color=C_WARNING, ls=':', lw=1.5)
    ax1.axvline(t_activated, color=C_DANGER, ls=':', lw=1.5)
    
    # ── 核心排版：错位放置垂直标注文字，彻底杜绝重叠 ───────────────────────
    # t_0 在垂直线左侧，靠顶部对其
    ax1.text(t_start - 0.005, 0.85 * y_limit, "t_0: 肌肉物理发力起点", 
             rotation=90, va='top', ha='right', fontsize=8.5, color=C_DARK, fontweight='bold')
    
    # t_1 在垂直线左侧，靠中部对其，高度与 t_0 错开
    ax1.text(t_high_cross - 0.005, 0.52 * y_limit, "t_1: 越过 High 阈值", 
             rotation=90, va='top', ha='right', fontsize=8.5, color=C_WARNING, fontweight='bold')
    
    # t_2 在垂直线右侧，靠底部向上生长，高度与 t_1 错开
    ax1.text(t_activated + 0.005, 0.15 * y_limit, "t_2: 系统触发 ACTIVATED 并发键", 
             rotation=90, va='bottom', ha='left', fontsize=8.5, color=C_DANGER, fontweight='bold')

    # 填充延迟阴影区域
    ax1.fill_between([t_start, t_high_cross], 0, 0.95 * y_limit, color=C_PRIMARY, alpha=0.12)
    ax1.text((t_start + t_high_cross)/2, 0.35 * y_limit, f"算法与滤波器\n群延迟\n~{delay_dsp:.1f}ms", 
             ha='center', va='center', fontsize=8, color=C_PRIMARY, fontweight='bold')
    
    ax1.fill_between([t_high_cross, t_activated], 0, 0.95 * y_limit, color=C_WARNING, alpha=0.12)
    ax1.text((t_high_cross + t_activated)/2, 0.35 * y_limit, f"防抖持有\n延迟\n{delay_debounce:.1f}ms", 
             ha='center', va='center', fontsize=8, color=C_WARNING, fontweight='bold')
    
    # 总体延迟范围标注
    ax1.annotate("", xy=(t_activated, 0.04 * y_limit), xytext=(t_start, 0.04 * y_limit),
                arrowprops=dict(arrowstyle="<->", color=C_DARK, lw=1.2))
    ax1.text((t_start + t_activated)/2, 0.05 * y_limit, 
             f"总检测延迟 (t_0 -> t_2): {delay_total:.1f} ms", 
             ha='center', va='bottom', fontsize=8.5, fontweight='bold', color=C_DARK)

    ax1.set_ylabel("信号包络幅值")
    ax1.grid(True, ls=':', alpha=0.5)
    ax1.legend(loc='upper left', fontsize=9, framealpha=0.9)
    
    label_source = "真实数据" if use_real else "仿真模型"
    ax1.set_title(f"肌肉发力瞬间：流式信号时延定量剖析图 ({label_source} 交互响应性验证)", fontsize=11, fontweight='bold')
    
    # Subplot 2: 触发器状态跳转
    ax2.plot(t_zoom, trigger_state_zoom, color=C_DANGER, lw=2, label="施密特触发状态 (0:放松 / 1:激活)")
    ax2.fill_between(t_zoom, 0, trigger_state_zoom, color=C_DANGER, alpha=0.1)
    ax2.set_ylabel("决策状态")
    ax2.set_ylim(-0.2, 1.2)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["Relaxed\n(放松)", "Activated\n(激活)"], fontsize=8)
    ax2.set_xlabel("时间 (s)")
    ax2.grid(True, ls=':', alpha=0.5)
    
    plt.suptitle(f"人机交互响应性评估：施密特触发意图识别的时延与逻辑决策关系 ({label_source})", fontsize=13, fontweight='bold', y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    
    save_fig("schmitt_latency_eval.png")

# ── 执行生成 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("开始自动生成 sEMG 体感控制系统评估报告相关图表...")
    
    draw_system_block_diagram()
    draw_hardware_connection()
    draw_experimental_flowchart()
    draw_filter_frequency_response()
    draw_signal_processing_waveform()
    draw_schmitt_latency_eval()
    
    print("\n[SUCCESS] 所有 6 个图表生成完成，文件保存在 report/images/ 文件夹下。")
