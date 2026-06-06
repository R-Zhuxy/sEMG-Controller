import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from scipy import signal

# ==========================================
# 1. 全局图表与美学配置 (科研级扁平化风格)
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS'] # 兼容多平台中文
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 300  # 高分辨率输出
plt.rcParams['savefig.bbox'] = 'tight' # 防止保存时边缘文字被裁切

# 现代配色卡
C_RAW = '#95a5a6'      # 原始信号 - 灰
C_FILTER = '#3498db'   # 滤波信号 - 科技蓝
C_ENVELOPE = '#e67e22' # 包络线 - 活力橙
C_TRIGGER = '#e74c3c'  # 触发状态 - 警示红
C_BG = '#f8f9fa'       # 浅灰背景，提升质感

# ==========================================
# 2. 数据读取与核心信号处理算法
# ==========================================
def process_emg_data(file_path, fs=500):
    """读取并处理 sEMG 信号，严格匹配报告中的流式与 SOS 处理逻辑"""
    df = pd.read_csv(file_path, header=None)
    raw_sig = df.values.flatten()
    
    # 消除初始直流偏置
    raw_sig = raw_sig - np.mean(raw_sig)
    t = np.arange(len(raw_sig)) / fs
    
    # ---------------------------------------------------------
    # 阶段 1：滤波处理
    # ---------------------------------------------------------
    # a. 带通滤波 (20-200Hz，使用 SOS 二阶截面结构保证稳定性)
    sos_bp = signal.butter(4, [20, 200], btype='bandpass', fs=fs, output='sos')
    filtered_sig = signal.sosfiltfilt(sos_bp, raw_sig)
    
    # b. 陷波滤波 (50Hz, Q=15)
    b_notch, a_notch = signal.iirnotch(50, 15, fs=fs)
    filtered_sig = signal.filtfilt(b_notch, a_notch, filtered_sig)
    
    # ---------------------------------------------------------
    # 阶段 2：包络特征提取 (滑动 RMS + 滑动平滑)
    # ---------------------------------------------------------
    def sliding_rms(data, window_size):
        # 均方根计算：先平方，再求滑动平均，最后开方
        squared = data ** 2
        window = np.ones(window_size) / window_size
        rms = np.sqrt(np.convolve(squared, window, mode='same'))
        return rms
        
    # N_rms = 25 样本滑动窗口
    rms_sig = sliding_rms(filtered_sig, 25)
    
    # N_smooth = 10 样本滑动平滑窗口
    smooth_window = np.ones(10) / 10
    envelope = np.convolve(rms_sig, smooth_window, mode='same')
    
    # ---------------------------------------------------------
    # 阶段 3：自适应校准与防抖施密特触发
    # ---------------------------------------------------------
    # 强制执行 3.0s (1500 样本) 校准
    calib_samples = int(3.0 * fs)
    base_mean = np.mean(envelope[:calib_samples])
    base_std = np.std(envelope[:calib_samples])
    
    # 动态阈值线生成 (此处系数可根据实际情况微调以匹配你的SBR)
    th_high = base_mean + 3.0 * base_std 
    th_low = base_mean + 1.0 * base_std
    
    # 带有 20ms (10 样本) 防抖的施密特触发器
    debounce_samples = int(0.020 * fs) 
    trigger_state = np.zeros_like(envelope)
    
    current_state = 0
    hold_counter = 0
    
    for i in range(len(envelope)):
        if current_state == 0:
            if envelope[i] > th_high:
                hold_counter += 1
                if hold_counter >= debounce_samples: # 满足持续时间才触发
                    current_state = 1
                    hold_counter = 0
            else:
                hold_counter = 0 # 跌落则重新计数
        else:
            # 激活状态下，跌落至低阈值直接释放 (通常释放不需要太长防抖，保证响应速度)
            if envelope[i] < th_low:
                current_state = 0
                hold_counter = 0
                
        trigger_state[i] = current_state
        
    return t, raw_sig, filtered_sig, envelope, trigger_state

# ==========================================
# 3. 绘制与保存图表
# ==========================================
def plot_full_pipeline(t, raw, filtered, envelope, save_dir="."):
    """图一：系统级信号处理管线全景图"""
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.patch.set_facecolor(C_BG)
    
    # 子图1：原始信号
    axes[0].plot(t, raw, color=C_RAW, linewidth=0.5, alpha=0.8)
    axes[0].set_title("原始 sEMG 信号 (含基线漂移与工频噪声)", fontweight='bold')
    axes[0].set_ylabel("幅值 (ADC)")
    
    # 子图2：滤波后信号
    axes[1].plot(t, filtered, color=C_FILTER, linewidth=0.5, alpha=0.9)
    axes[1].set_title("预处理后信号 (带通 20-450Hz + 50Hz 陷波)", fontweight='bold')
    axes[1].set_ylabel("幅值")
    
    # 子图3：包络特征
    axes[2].plot(t, np.abs(filtered), color=C_RAW, linewidth=0.3, alpha=0.4, label="整流信号")
    axes[2].plot(t, envelope, color=C_ENVELOPE, linewidth=2, label="平滑包络线 (5Hz 低通)")
    axes[2].set_title("特征提取：绝对值整流与线性包络", fontweight='bold')
    axes[2].set_xlabel("时间 (s)", fontweight='bold')
    axes[2].set_ylabel("幅值")
    axes[2].legend(loc="upper right")
    
    for ax in axes:
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, "fig1_signal_pipeline.png"))
    print("已生成: fig1_signal_pipeline.png")
    plt.close()

def plot_latency_evaluation(t, envelope, trigger_state, save_dir="."):
    """图二：发力瞬间局部放大与施密特判定图 (解决图线挤作一团的问题)"""
    # 自动寻找第一次发力的位置，进行局部放大 (前后各取 1.5 秒)
    active_indices = np.where(trigger_state == 1)[0]
    if len(active_indices) > 0:
        first_active_idx = active_indices[0]
        fs = int(1 / (t[1] - t[0]))
        start_idx = max(0, first_active_idx - int(1.5 * fs))
        end_idx = min(len(t), first_active_idx + int(1.5 * fs))
    else:
        # 如果没有触发，就展示前 3 秒
        start_idx, end_idx = 0, int(3 * (1 / (t[1] - t[0])))

    t_zoom = t[start_idx:end_idx]
    env_zoom = envelope[start_idx:end_idx]
    trig_zoom = trigger_state[start_idx:end_idx]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [2, 1]}, sharex=True)
    fig.patch.set_facecolor(C_BG)

    # 子图1：放大的包络线
    ax1.plot(t_zoom, env_zoom, color=C_ENVELOPE, linewidth=2.5, label="特征包络幅值")
    ax1.fill_between(t_zoom, 0, env_zoom, color=C_ENVELOPE, alpha=0.1)
    ax1.set_title("肌肉发力瞬间：流式信号特征与判定剖析 (局部放大)", fontweight='bold', fontsize=12)
    ax1.set_ylabel("信号包络幅值")
    ax1.grid(True, ls=':', alpha=0.7)
    ax1.legend(loc='upper left')

    # 子图2：触发器状态
    ax2.plot(t_zoom, trig_zoom, color=C_TRIGGER, linewidth=2, drawstyle='steps-pre', label="施密特触发状态")
    ax2.fill_between(t_zoom, 0, trig_zoom, color=C_TRIGGER, alpha=0.1, step='pre')
    ax2.set_ylabel("决策状态")
    ax2.set_ylim(-0.2, 1.2)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["Relaxed (放松)", "Activated (激活)"], fontsize=10, fontweight='bold')
    ax2.set_xlabel("时间 (s)", fontsize=11, fontweight='bold')
    ax2.grid(True, ls=':', alpha=0.7)
    
    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, "fig2_schmitt_latency_eval.png"))
    print("已生成: fig2_schmitt_latency_eval.png")
    plt.close()

if __name__ == "__main__":
    # 1. 获取当前脚本（本文件）所在的绝对路径 (即 report 文件夹)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. 定位并列的 data 文件夹下的目标文件路径
    # ".." 表示返回上一级（根目录），然后进入 "data" 并指向 "raw_emg_record.csv"
    file_path = os.path.normpath(os.path.join(current_dir, "..", "data", "raw_emg_record.csv"))
    
    # 3. 检查文件是否存在并执行处理
    if os.path.exists(file_path):
        print(f"成功定位数据文件: {file_path}")
        print("正在处理肌电数据...")
        
        # 传入计算得到的绝对路径
        t_seq, raw, filtered, env, trigger = process_emg_data(file_path, fs=500)
        
        plot_full_pipeline(t_seq, raw, filtered, env, save_dir=current_dir)
        plot_latency_evaluation(t_seq, env, trigger, save_dir=current_dir)
        
        print("所有学术级图表已成功生成并保存在 report 文件夹中。")
    else:
        print(f"路径解析错误: 无法在以下位置找到文件:\n{file_path}")
        print("请检查根目录下的文件夹名称是否准，且文件名拼写无误。")