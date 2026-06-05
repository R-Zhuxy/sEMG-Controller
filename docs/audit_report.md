# sEMG Controller 深度工程审计报告

> **审计日期**: 2026-06-05  
> **审计范围**: 完整软硬件栈（Arduino 固件 + Python 上位机 + 测试套件）  
> **审计标准**: IEC 62304 / MISRA-C 思想下的工业级嵌入式实时系统标准  

---

## 审计总览

| 风险等级 | 数量 |
|---------|------|
| 🔴 致命 | 2 |
| 🟠 高危 | 5 |
| 🟡 中危 | 5 |
| 🔵 潜在技术债务 | 5 |

---

## 维度一：硬件时序与资源边界 (Arduino/MCU 端)

### 🟠 F-01: `micros()` 溢出导致采样定时崩溃（约 71.6 分钟后）

**【隐患位置】** [semg_reader.ino](file:///d:/HomeworkProjects/sEMG/firmware/semg_reader/semg_reader.ino#L53-L58) — `loop()` 主循环

**【风险等级】** 高危

**【缺陷机理】**

`micros()` 返回 `unsigned long`（ATmega328P 上为 32 位无符号），约 **71 分 35 秒**（2³² μs ≈ 4294.97 秒）后溢出归零。

当前代码：
```cpp
if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_US)
```

**好消息**：由于 C/C++ 无符号整数减法的模运算特性，`currentTime - lastSampleTime` 在溢出边界上**仍然正确**——只要两次读取间隔不超过 2³² μs（≈71 分钟），差值仍然给出正确的经过时间。所以 `if` 判断本身**不会出错**。

**但累加操作有隐患**：
```cpp
lastSampleTime += SAMPLE_INTERVAL_US;
```
如果 `loop()` 因某种原因（如串口 FIFO 满导致 `Serial.println()` 阻塞）被延迟了很长时间，`lastSampleTime` 会疯狂追赶，连续触发多次采样而不给串口发送留出时间，造成**采样风暴**（burst）。虽然 `analogRead()` + `Serial.println()` 的延迟会自然限流，但在溢出边界附近叠加这种追赶行为，可能导致系统进入亚稳态。

**【重构建议】**
增加追赶保护（anti-windup guard）：

```cpp
void loop() {
    unsigned long currentTime = micros();
    if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_US) {
        lastSampleTime += SAMPLE_INTERVAL_US;
        // 防止累加追赶风暴：如果已落后超过 N 个周期，直接跳到当前时间
        if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_US * 10) {
            lastSampleTime = currentTime;  // 放弃追赶，重新对齐
        }
        int adcValue = analogRead(SENSOR_PIN);
        Serial.println(adcValue);
    }
}
```

---

### 🟡 F-02: `Serial.println()` 在 FIFO 满时的隐式阻塞

**【隐患位置】** [semg_reader.ino](file:///d:/HomeworkProjects/sEMG/firmware/semg_reader/semg_reader.ino#L64) — `Serial.println(adcValue)`

**【风险等级】** 中危

**【缺陷机理】**

Arduino 的 `HardwareSerial` 使用 64 字节的发送缓冲区（`SERIAL_TX_BUFFER_SIZE`）。当缓冲区满时，`Serial.write()`（`println` 的底层调用）会**阻塞等待**直到缓冲区有空间。

带宽计算：
- 每帧最大长度："1023\r\n" = 6 字节
- 500 Hz × 6 B = 3000 B/s
- 115200 baud ÷ 10 bits/byte = 11520 B/s 有效吞吐
- 占用率 ≈ 26%，正常情况下绰绰有余

**但是**：如果上位机因任何原因暂停读取（如 Python GIL 长时间被占、处理循环卡在 GC 或 I/O 上），Arduino 的发送缓冲区会在 64 ÷ 6 ≈ 10 帧后填满（约 20ms），之后每次 `println()` 都会阻塞 `loop()`，导致**采样完全停滞**。恢复后会出现时间戳断裂（上位机无法感知这段丢失的时间）。

**【重构建议】**
1. 上位机层面：这本质上是 OK 的——文档中的注释已正确指出带宽余量足够。真正的防护应在上位机保证持续读取（当前已通过独立线程实现，见 `serial_reader.py`）。
2. 如需更高可靠性，可在固件中检测发送缓冲区可用空间：

```cpp
if (Serial.availableForWrite() >= 6) {
    Serial.println(adcValue);
} else {
    // 丢弃本帧，优先保证采样节奏
    // 可选：递增丢帧计数器
}
```

---

### 🔵 F-03: ADC 采样精度未优化——默认预分频器与通道切换噪声

**【隐患位置】** [semg_reader.ino](file:///d:/HomeworkProjects/sEMG/firmware/semg_reader/semg_reader.ino#L61) — `analogRead(SENSOR_PIN)`

**【风险等级】** 潜在技术债务

**【缺陷机理】**

Arduino 的 `analogRead()` 使用默认 ADC 预分频器（128 分频, ADC 时钟 = 16MHz/128 = 125kHz），单次转换约 **104μs**。在 2000μs 的采样周期内占比 5.2%，性能上是 OK 的。

但未做两点优化：
1. **未丢弃首次通道切换后的读数**：ATmega328P 的 ADC 多路复用器在切换通道后，采保电容需要时间稳定。虽然本项目只用 A0 一个通道，但如果未来扩展多通道，每次 `analogRead` 应先读一次丢弃。
2. **未使用 oversampling 提升有效分辨率**：以 500Hz 的采样率，在 2000μs 窗口内可以轻松做 4x oversampling（4 次读取取平均，有效分辨率从 10 bit 提升到 11 bit），代价仅 ~416μs，仍远低于周期。

**【重构建议】**
```cpp
// 4x oversampling (有效 11-bit 分辨率)
uint16_t sum = 0;
for (uint8_t i = 0; i < 4; i++) {
    sum += analogRead(SENSOR_PIN);
}
int adcValue = sum >> 2;  // 除以4取平均 (若要11bit精度则不右移，直接传sum)
Serial.println(adcValue);
```

---

## 维度二：通信协议与数据流解析 (Serial/UART 链路)

### 🔴 F-04: `_sample_count` 和 `_error_count` 非原子操作的线程竞态

**【隐患位置】** [serial_reader.py](file:///d:/HomeworkProjects/sEMG/src/semg/communication/serial_reader.py#L168) — `self._sample_count += 1` 及 [L211](file:///d:/HomeworkProjects/sEMG/src/semg/communication/serial_reader.py#L211) `self._error_count += 1`

**【风险等级】** 致命

**【缺陷机理】**

`_sample_count` 和 `_error_count` 在守护线程（`_read_loop`）中递增，同时在主线程（`main.py` L231-232）中读取：

```python
f"samples={reader.sample_count} "
f"errors={reader.error_count} "
```

在 CPython 中，由于 GIL 的存在，**简单的整数 `+=` 操作事实上是原子的**（`BINARY_ADD` + `STORE_ATTR` 虽然是两条字节码，但 GIL 保证了整数对象替换的原子性）。所以在 CPython 下这**目前不会出错**。

**但这是一个脆弱的假设**：
1. Python 3.13+ 引入了**自由线程模式（Free-threaded / no-GIL）**，用户的 `pyproject.toml` 指定了 `requires-python = ">=3.14"`。如果用户在 `python3.14t`（free-threaded 构建）下运行，`+=` 将不再是原子的，会产生**数据撕裂 (torn read/write)**。
2. 更关键的是，**这违反了 "显式优于隐式" 的 Python 哲学**——依赖 GIL 做线程安全是公认的反模式。

**【重构建议】**
使用线程安全的原子计数，或复用已有的锁：

```python
import threading

class SerialReader:
    def __init__(self, ...):
        ...
        self._stats_lock = threading.Lock()
        self._sample_count = 0
        self._error_count = 0
    
    def _parse_line(self, line: bytes) -> float | None:
        try:
            text = line.decode('ascii').strip()
            if text:
                return float(text)
            return None
        except (ValueError, UnicodeDecodeError) as e:
            with self._stats_lock:
                self._error_count += 1
                count = self._error_count
            if count <= 10 or count % 100 == 0:
                logger.warning(...)
            return None
```

或者更轻量的方案——使用 `threading.Lock` 保护，或改用无锁的 `queue.Queue` 报告统计数据。

---

### 🟠 F-05: 批量入队残余数据在断联时可能永久丢失

**【隐患位置】** [serial_reader.py](file:///d:/HomeworkProjects/sEMG/src/semg/communication/serial_reader.py#L162-L187) — `_read_loop` 中 `batch` 的生命周期

**【风险等级】** 高危

**【缺陷机理】**

当 `SerialException` 或 `OSError` 被捕获时（L182-187），代码调用 `self._close_serial()` 并**重新进入 while 循环顶部**。此时 `batch` 列表中可能还有 1~24 个未刷入的样本。这些样本**不会丢失**——`batch` 是局部变量，在下次循环迭代中继续累积。

**但真正的问题是时间断裂**：这些残余样本来自断联**之前**的数据流。当重连成功后，它们会与**新数据流的首批样本混在一起**被 `extend` 进缓冲区。对于 IIR 滤波器来说，时间轴上的跳跃会导致**巨大的阶跃响应**（瞬态振荡），可能持续数百个采样点。

**【重构建议】**
在断联时清空残余 batch，并在重连后通知上位机重置滤波器状态：

```python
except serial.SerialException as e:
    logger.error(f"串口读取错误: {e}")
    batch.clear()  # ← 关键：丢弃时间断裂的残余数据
    self._close_serial()
except OSError as e:
    logger.error(f"系统 I/O 错误: {e}")
    batch.clear()  # ← 同上
    self._close_serial()
```

更完整的方案是在 `SerialReader` 中增加一个 `on_reconnect` 回调，通知主循环重置全部 DSP 状态（滤波器 zi、包络累积器、施密特触发器）。

---

### 🟡 F-06: `_parse_line` 中 `decode('ascii')` 对脏字节的不完整处理

**【隐患位置】** [serial_reader.py](file:///d:/HomeworkProjects/sEMG/src/semg/communication/serial_reader.py#L206) — `line.decode('ascii').strip()`

**【风险等级】** 中危

**【缺陷机理】**

`_connect()` 中使用了 `decode('ascii', errors='ignore')`（L119），但 `_parse_line()` 中使用的是**无 `errors` 参数的** `decode('ascii')`，等同于 `errors='strict'`。

虽然 `except (ValueError, UnicodeDecodeError)` 已经兜底了，但 `_connect` 和 `_parse_line` 之间的处理策略不一致是一个设计问题——在 `_connect` 阶段认为乱码可以 `ignore`，但在正常运行阶段却触发异常路径。

实际影响：当 EMI 干扰导致串口接收到高位字节（>127）时，每个这样的字节都会走一次完整的异常处理路径（try→catch→log→return None），**即使这些字节本身无害**。在强干扰环境下，这可能显著增加 CPU 开销。

**【重构建议】**
统一使用 `errors='ignore'`，将异常路径仅留给真正的解析失败：

```python
def _parse_line(self, line: bytes) -> float | None:
    try:
        text = line.decode('ascii', errors='ignore').strip()
        if not text:
            return None
        return float(text)
    except ValueError as e:
        self._error_count += 1
        ...
```

---

### 🔵 F-07: 无帧序号/时间戳——上位机无法检测丢帧

**【隐患位置】** [semg_reader.ino](file:///d:/HomeworkProjects/sEMG/firmware/semg_reader/semg_reader.ino#L64) — 协议格式 & [serial_reader.py](file:///d:/HomeworkProjects/sEMG/src/semg/communication/serial_reader.py#L194-L218) — 解析逻辑

**【风险等级】** 潜在技术债务

**【缺陷机理】**

当前协议格式为纯文本 ADC 值（`"512\r\n"`），不含任何帧序号或时间戳。上位机**无法区分**：
1. 正常 500Hz 数据流
2. 期间丢失了 N 帧的数据流（如串口缓冲区溢出导致中间帧被覆盖）

对于 IIR 滤波器来说，**丢帧等于采样率突然降低**，会导致滤波器频率响应偏移。假设丢失了 10 帧，等效采样率从 500Hz 降到 ~455Hz，50Hz 陷波器的中心频率偏移约 5%，陷波深度显著恶化。

**【重构建议】**
在协议中增加递增帧序号（简单的 8 位循环计数器即可），上位机检测序号不连续时可以插入零值或触发滤波器重置：

```cpp
// 固件端
uint8_t frameSeq = 0;
void loop() {
    ...
    Serial.print(frameSeq++);
    Serial.print(',');
    Serial.println(adcValue);
    ...
}
```

---

## 维度三：信号处理与算法逻辑 (Python DSP)

### 🔴 F-08: 校准时 `sig_filter.apply()` 一次性处理 1500 个样本——IIR 暖机瞬态被计入阈值

**【隐患位置】** [main.py](file:///d:/HomeworkProjects/sEMG/main.py#L112-L116) — `run_calibration()` 中的 `sig_filter.apply(raw_data)` + `envelope_ext.extract(filtered_data)`

**【风险等级】** 致命

**【缺陷机理】**

校准流程中：
```python
raw_data = buffer.get_latest(samples_needed)  # 1500 samples (3s × 500Hz)
filtered_data = sig_filter.apply(raw_data)      # 一次性流式滤波
envelope_data = envelope_ext.extract(filtered_data)  # 一次性包络提取
return calibrator.compute_thresholds(envelope_data)  # 包含暖机段！
```

`sig_filter.apply()` 在 `_initialized = False` 时会用 `data[0]` 初始化滤波器状态（[filters.py L91-95](file:///d:/HomeworkProjects/sEMG/src/semg/processing/filters.py#L91-L95)）。4 阶 Butterworth 带通滤波器的暂态响应（settling time）约为 **4~5 个时间常数**，对于 20Hz 下限截止频率，τ ≈ 1/(2π×20) ≈ 8ms，settling ≈ 40ms ≈ 20 个采样点。

类似地，`EnvelopeExtractor` 的 RMS 窗口（50 点）和平滑窗口（20 点）也有暖机期，总计约 **50~70 个采样点**的暂态。

**问题核心**：`calibrator.compute_thresholds()` 对**整个 `envelope_data` 数组**（包括前 70 个暂态点）计算 `np.mean()` 和 `np.std()`：

```python
baseline_mean = float(np.mean(envelope_data))   # 被暖机瞬态拉偏
baseline_std = float(np.std(envelope_data))      # 被暖机瞬态放大
```

暖机期的包络值通常远低于稳态值（因为 RMS 窗口未填满，除数是 `_rms_fill` 而非 `_rms_window`），这会**人为拉低 baseline_mean 并放大 baseline_std**。后果：
- `high_threshold = mean + 3σ` 被放大，可能导致**系统灵敏度不足**（用户大力发力才能触发）
- `low_threshold = mean + 1.5σ` 也被放大，可能导致**释放不灵敏**

在 1500 个样本中有 70 个暖机样本，占比约 4.7%。对 std 的影响可能达到 10~30%（取决于真实信号幅度与暖机过渡幅度之比）。

**【重构建议】**
在校准计算中裁掉暖机暂态：

```python
def run_calibration(...):
    ...
    raw_data = buffer.get_latest(samples_needed)
    filtered_data = sig_filter.apply(raw_data)
    envelope_data = envelope_ext.extract(filtered_data)
    
    # 裁掉 DSP 暖机暂态 (滤波器 settling + RMS窗口 + 平滑窗口)
    warmup_samples = max(
        config.envelope.rms_window_size + config.envelope.smoothing_window_size,
        int(0.1 * config.sampling.sample_rate)  # 至少 100ms
    )
    envelope_steady = envelope_data[warmup_samples:]
    return calibrator.compute_thresholds(envelope_steady)
```

---

### 🟠 F-09: IIR 滤波器状态初始化用 `data[0]` 乘 `zi` ——对 raw ADC 值不合理

**【隐患位置】** [filters.py](file:///d:/HomeworkProjects/sEMG/src/semg/processing/filters.py#L91-L94)

**【风险等级】** 高危

**【缺陷机理】**

```python
if not self._initialized:
    for i, (b, a) in enumerate(self._notch_filters):
        self._notch_zis[i] = sig.lfilter_zi(b, a) * data[0]
    self._bp_zi = sig.sosfilt_zi(self._bp_sos) * data[0]
```

`sig.lfilter_zi(b, a)` 返回的是使滤波器在**恒定输入下达到稳态**的初始条件向量。将其乘以 `data[0]` 的含义是："假设在 `data[0]` 之前，信号一直是 `data[0]` 这个值"。

对于**陷波器**，这是合理的——如果输入是恒定的直流，陷波器的稳态输出就是该直流值。

**但对于带通滤波器**，恒定直流输入的稳态输出是 **0**（因为直流在通带之外）。所以 `sig.sosfilt_zi(self._bp_sos)` 的稳态增益本身就是 0 或接近 0，乘以 `data[0]` 后仍然是 0。**这意味着带通滤波器的初始化实际上等于零初始化**，暖机瞬态不可避免。

虽然这不是"错误"（只是暖机期更长），但存在一个**隐含的语义陷阱**：开发者可能认为 `* data[0]` 的初始化减少了暖机时间，但对于带通来说实际上没有任何效果。如果 `data[0]` 恰好是一个异常值（如 ADC 上电瞬间的毛刺），反而会导致陷波器产生不必要的瞬态。

**【重构建议】**
对陷波器和带通分别处理初始化逻辑，并加入文档说明：

```python
if not self._initialized:
    # 陷波器：用首样本初始化可减少 DC offset 导致的暂态
    for i, (b, a) in enumerate(self._notch_filters):
        self._notch_zis[i] = sig.lfilter_zi(b, a) * data[0]
    
    # 带通：zi 的稳态增益在直流处为 0，初始化为零即可
    # 无论 data[0] 是什么，带通的暖机暂态无法避免
    self._bp_zi = sig.sosfilt_zi(self._bp_sos) * 0.0
    self._initialized = True
```

---

### 🟠 F-10: 包络提取器的 RMS 滑窗 O(1) 累积在极端输入下的浮点漂移

**【隐患位置】** [envelope.py](file:///d:/HomeworkProjects/sEMG/src/semg/processing/envelope.py#L68-L77) — `_rms_sum_sq` 的累积更新

**【风险等级】** 高危

**【缺陷机理】**

```python
old_sq = self._rms_history[self._rms_idx]
self._rms_history[self._rms_idx] = new_sq
self._rms_sum_sq += new_sq - old_sq
```

这是经典的**滑动窗口增量求和**。但 IEEE 754 浮点运算不满足结合律：

$$(a + b) - b \neq a$$

每次 `+= new_sq - old_sq` 操作都会引入约 $\epsilon_{\text{mach}} \approx 2.2 \times 10^{-16}$（float64）的相对误差。经过 $N$ 次累积后，误差可达：

$$\text{error} \approx \sqrt{N} \cdot \epsilon_{\text{mach}} \cdot \text{max}(|x_i^2|)$$

以 500Hz 采样率运行 1 小时 = 1.8M 个样本，ADC 值 0~1023，$x_i^2$ 最大 ≈ $10^6$：

$$\text{error} \approx \sqrt{1.8 \times 10^6} \times 2.2 \times 10^{-16} \times 10^6 \approx 3 \times 10^{-7}$$

对于 float64 来说，**这个误差在实际使用场景下几乎可以忽略**。代码中已有 `if self._rms_sum_sq < 0.0: self._rms_sum_sq = 0.0` 保护负值。

**然而**：如果信号中出现**极端毛刺**（例如 ADC 断线返回 1023 的持续脉冲，或上游滤波器在状态重置时产生的发散振荡），`new_sq` 可以突然变得非常大。此时 `new_sq - old_sq` 中 `old_sq` 远小于 `new_sq`，执行 `+= (big - small)` 后再执行 `+= (small - big)`，由于浮点取消误差（catastrophic cancellation），累积和可能产生不可忽略的正偏差。

**更实际的风险**：如果 `_rms_sum_sq` 因某种原因变成 NaN（例如上游滤波器发散产生 `inf * inf = inf`，然后 `inf - inf = NaN`），则后续所有输出都将永久是 NaN，**系统将丧失触发功能而不报任何错误**。

**【重构建议】**
增加 NaN/inf 哨兵检测，并定期重新从环形历史数组精确求和（每 N 步做一次全量重算消除累积误差）：

```python
# 在 extract() 循环中，每 10000 个样本做一次精确重算
self._total_count += 1
if self._total_count % 10000 == 0:
    self._rms_sum_sq = float(np.sum(self._rms_history[:self._rms_fill] ** 2))
    # (注意: 当 fill == rms_window 时就是全部，否则只取已填充部分)

# NaN 哨兵
if not np.isfinite(self._rms_sum_sq):
    logger.error("RMS 累积和出现 NaN/inf，执行紧急重算")
    self._rms_sum_sq = float(np.sum(self._rms_history ** 2))
    if not np.isfinite(self._rms_sum_sq):
        self._rms_sum_sq = 0.0
        self._rms_history[:] = 0.0
```

---

### 🟡 F-11: 校准 SNR 计算的数学定义有误

**【隐患位置】** [calibration.py](file:///d:/HomeworkProjects/sEMG/src/semg/processing/calibration.py#L87-L92)

**【风险等级】** 中危

**【缺陷机理】**

```python
signal_power = np.mean(envelope_data ** 2)
noise_power = baseline_std ** 2
snr_db = float(10 * np.log10(signal_power / noise_power))
```

这里的 `signal_power` 是**整个包络数据的均方值**（包含均值+噪声），而 `noise_power` 是**仅噪声的方差**。

数学上，对于静息期数据 $x = \mu + n$（其中 $\mu$ 是基线均值，$n$ 是零均值噪声）：

$$\text{signal\_power} = E[x^2] = \mu^2 + \sigma^2$$

$$\text{noise\_power} = \sigma^2$$

$$\text{SNR} = 10 \log_{10}\left(\frac{\mu^2 + \sigma^2}{\sigma^2}\right) = 10 \log_{10}\left(1 + \frac{\mu^2}{\sigma^2}\right)$$

**这不是传统的信噪比定义**。传统 SNR 应为 $\mu^2 / \sigma^2$（或 $20\log_{10}(\mu/\sigma)$），即信号功率与噪声功率之比。当前定义在 $\mu \gg \sigma$ 时近似等价，但在 $\mu \approx \sigma$（即信号质量差）时会比真实 SNR 高约 3dB（因为分子多了一个 $\sigma^2$）。

**实际影响**：`snr_warning_threshold = 5.0 dB` 的阈值判断会被这个偏差影响——真实 SNR 可能只有 2dB（信号质量很差），但算出来是 5.6dB，跳过了警告。

**【重构建议】**
修正为标准 SNR 定义：

```python
signal_power = baseline_mean ** 2
noise_power = baseline_std ** 2
if noise_power > 0:
    snr_db = float(10 * np.log10(signal_power / noise_power))
else:
    snr_db = float('inf')
```

---

### 🟡 F-12: 施密特触发器使用 `time.time()` 而非 `time.monotonic()`

**【隐患位置】** [schmitt_trigger.py](file:///d:/HomeworkProjects/sEMG/src/semg/classification/schmitt_trigger.py#L83) — `now = time.time()`

**【风险等级】** 中危

**【缺陷机理】**

`time.time()` 返回的是**系统墙钟时间**，受 NTP 时间同步影响。当操作系统执行 NTP 校时（通常每小时或每天一次）时，时间可能向前或向后跳变数百毫秒甚至数秒。

- **向后跳变**：`now - self._pending_since` 变成负数或极小值，防抖计时器被重置，状态跳变被延迟。
- **向前跳变**：`now - self._pending_since` 突然变得很大，防抖计时器立即通过，可能误触发。

`debounce_time = 100ms` 和 `min_activation_time = 50ms` 的量级，与 NTP 跳变的量级（10~500ms）在同一数量级。

**注意**：`serial_reader.py` 中的 `_connect()` 已正确使用了 `time.monotonic()`（L110），但 `schmitt_trigger.py` 却用了 `time.time()`，**同一项目内的时间基准不一致**。

**【重构建议】**
将 `time.time()` 替换为 `time.monotonic()`（或 `time.perf_counter()`），后者不受系统时间调整影响：

```python
def update(self, envelope_value: float) -> MuscleState | None:
    now = time.monotonic()  # ← 单调时钟，不受 NTP 影响
    ...
```

---

## 维度四：内存管理与优雅降级 (System Stability)

### 🟠 F-13: 日志文件无限增长——58MB 日志文件已成现实

**【隐患位置】** [main.py](file:///d:/HomeworkProjects/sEMG/main.py#L42-L50) — `setup_logging()` & 根目录的 `semg_session.log`（当前 58,937,922 字节 ≈ **56.2 MB**）

**【风险等级】** 高危

**【缺陷机理】**

```python
logging.FileHandler('semg_session.log', encoding='utf-8')
```

使用的是 `FileHandler` 而非 `RotatingFileHandler`。每次运行都会向同一个文件追加日志。以当前的日志级别 `INFO` 和每 2 秒一次的状态打印，加上每秒 500 个潜在的 warning（解析错误时），长时间运行后日志文件将无限膨胀。

**当前已有 56MB 的日志文件佐证了这一问题**。

在 Windows 上，过大的日志文件还可能导致：
1. 文件系统碎片化，影响磁盘 I/O 性能
2. 文本编辑器/日志查看器无法打开
3. 如果磁盘空间不足，`FileHandler.emit()` 会抛出 `OSError`，但 Python logging 模块会默默吞掉这个错误（`handleError` 默认 silently ignore），导致**日志静默丢失而程序不知情**

**【重构建议】**
使用 `RotatingFileHandler` 或 `TimedRotatingFileHandler`：

```python
from logging.handlers import RotatingFileHandler

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                'semg_session.log',
                maxBytes=5 * 1024 * 1024,  # 5MB
                backupCount=3,
                encoding='utf-8'
            ),
        ]
    )
```

---

### 🟡 F-14: `signal.SIGINT` 处理器与 `shutdown_flag` 的非原子写入

**【隐患位置】** [main.py](file:///d:/HomeworkProjects/sEMG/main.py#L146-L153) — `signal_handler` + `shutdown_flag`

**【风险等级】** 中危

**【缺陷机理】**

```python
shutdown_flag = False

def signal_handler(signum, frame):
    nonlocal shutdown_flag
    shutdown_flag = True
```

`shutdown_flag` 是一个普通的 Python `bool`，在信号处理器中被设置，在主循环（L195 `while not shutdown_flag`）中被读取。

在 CPython 中，信号处理器在主线程的两条字节码之间被调用，写入 `bool` 值是原子的，所以**目前是安全的**。

**但 `shutdown_flag` 没有被声明为 `volatile` 的 Python 等价物**。在 CPython 中不存在编译器优化导致的缓存问题（因为 Python 变量是字典查找），但如果未来使用 JIT 编译（Python 3.13+ 的 JIT 实验性支持），理论上存在被优化掉的风险。

更实际的问题：**如果主循环在 `time.sleep(0.005)` 中被阻塞**，`SIGINT` 会打断 sleep 并抛出 `InterruptedError`（在 Windows 上会直接转换为 `KeyboardInterrupt`）。信号处理器设置了 `shutdown_flag = True`，但 `KeyboardInterrupt` 异常可能在 `time.sleep` 抛出后被 `except Exception` 捕获（L242），导致**非预期的退出路径**。

**【重构建议】**
使用 `threading.Event` 替代裸 `bool`，并在 except 中区分 `KeyboardInterrupt`：

```python
shutdown_event = threading.Event()

def signal_handler(signum, frame):
    shutdown_event.set()

# 主循环
while not shutdown_event.is_set():
    ...
    shutdown_event.wait(timeout=0.005)  # 替代 time.sleep，且可被 set() 立即唤醒
```

---

### 🔵 F-15: `pyautogui.keyDown/keyUp` 异常未被捕获

**【隐患位置】** [key_mapper.py](file:///d:/HomeworkProjects/sEMG/src/semg/action/key_mapper.py#L62-L71) — `_handle_hold()`

**【风险等级】** 潜在技术债务

**【缺陷机理】**

`pyautogui.keyDown()` / `keyUp()` 可能因以下原因抛出异常：
1. `pyautogui.FailSafeException`：当鼠标移到屏幕左上角时（`FAILSAFE = True`）
2. 在某些 Windows 环境下，如果焦点窗口是管理员权限进程，`keyDown` 可能静默失败或抛出异常

如果 `keyDown` 成功但后续的 `keyUp` 因 FailSafe 被触发而抛出异常，**按键将永远保持按下状态**（因为 `self._key_held = True` 但 `keyUp` 没有执行成功）。虽然 `finally` 块中有 `release_all()`，但如果 `release_all()` 自身也触发 FailSafe，按键就真的无法释放了。

**【重构建议】**
在 `keyDown`/`keyUp` 调用处增加异常保护，并在 `release_all` 中使用退避重试：

```python
def _handle_hold(self, state: MuscleState) -> None:
    try:
        if state == MuscleState.ACTIVATED and not self._key_held:
            pyautogui.keyDown(self._key)
            self._key_held = True
        elif state == MuscleState.RELAXED and self._key_held:
            pyautogui.keyUp(self._key)
            self._key_held = False
    except pyautogui.FailSafeException:
        logger.warning("pyautogui FailSafe 触发，松开所有按键")
        self._key_held = False  # 强制标记为已释放（即使 keyUp 未执行）
        raise  # 向上传播，让 main 退出
    except Exception as e:
        logger.error(f"键盘注入失败: {e}")
```

---

### 🔵 F-16: `main.py` 中的硬编码处理频率

**【隐患位置】** [main.py](file:///d:/HomeworkProjects/sEMG/main.py#L199-L237) — `time.sleep(0.005)` 和状态打印间隔 `2.0`

**【风险等级】** 潜在技术债务

**【缺陷机理】**

主处理循环中有两个硬编码的魔法数字：
- `time.sleep(0.005)` — 200Hz 处理循环频率
- `if now - last_status_time >= 2.0` — 每 2 秒打印状态

这些值没有在 `config.py` 中定义，也没有注释说明为什么选择这些特定值。

`5ms` 的 sleep 意味着每次处理循环最多等待 5ms 才消费新数据。在 500Hz 采样率下，5ms 内累积 2~3 个新样本。如果处理耗时抖动（如 numpy GC），可能偶尔积累到 5~10 个样本。这对于流式算法来说是完全安全的，但应该在配置中声明意图。

**【重构建议】**
将这些常量移入 `SystemConfig`：

```python
@dataclass
class SystemConfig:
    ...
    processing_interval: float = 0.005   # 主循环处理间隔 (s)
    status_print_interval: float = 2.0   # 状态打印间隔 (s)
```

---

### 🔵 F-17: 无硬件断联后的自动重连通知机制

**【隐患位置】** [serial_reader.py](file:///d:/HomeworkProjects/sEMG/src/semg/communication/serial_reader.py#L149-L192) — `_read_loop` + [main.py](file:///d:/HomeworkProjects/sEMG/main.py#L195-L237) — 主循环

**【风险等级】** 潜在技术债务

**【缺陷机理】**

当 USB 线被拔掉时，事件序列如下：
1. `_read_loop` 捕获 `SerialException` / `OSError`
2. `_close_serial()` 被调用，`_connected` 事件被清除
3. 循环重新进入，尝试 `_connect()`
4. 如果 USB 重新插入，连接恢复

**但主线程对此完全不知情**。主循环的 `while not shutdown_flag` 继续运行，`buffer.read_new()` 返回空数组，`time.sleep(0.005)` 继续循环。用户看到的是：
- 状态打印中 `samples=` 不再增长（但需要仔细观察才能发现）
- 包络值停留在最后一个有效值
- 没有任何明确的 "⚠️ 连接断开" 提示

更严重的是，当连接恢复后，滤波器状态（`zi`）仍然保持着断联前的值。新数据流的第一个样本与旧状态之间的不连续性会导致滤波器产生**巨大的阶跃瞬态**，可能误触发施密特触发器，产生一次虚假的按键事件。

**【重构建议】**
在 `SerialReader` 中增加状态变化回调：

```python
class SerialReader:
    def __init__(self, ..., on_disconnect=None, on_reconnect=None):
        self._on_disconnect = on_disconnect
        self._on_reconnect = on_reconnect
    
    def _read_loop(self):
        while self._running.is_set():
            if not self._connected.is_set():
                if self._on_disconnect:
                    self._on_disconnect()
                if not self._connect():
                    ...
                else:
                    if self._on_reconnect:
                        self._on_reconnect()
```

主程序中注册回调，在重连时重置全部 DSP 状态。

---

## 反思：第一反应遗漏的深层问题

经过上述逐文件审计后，我又从系统全局角度进行了二次反思，发现以下在初次扫描中可能被忽略的跨模块竞态/时序问题：

### 跨模块竞态 R-01: 校准期间 `read_new()` 和 `get_latest()` 的语义冲突

[main.py L113-118](file:///d:/HomeworkProjects/sEMG/main.py#L113-L118) 中校准流程是：
```python
raw_data = buffer.get_latest(samples_needed)  # 不推进 read_index
filtered_data = sig_filter.apply(raw_data)
envelope_data = envelope_ext.extract(filtered_data)
buffer.read_new()  # 推进 read_index 跳过已处理数据
```

**隐含假设**：在 `get_latest()` 和 `read_new()` 之间，串口线程没有写入新数据。但实际上串口线程是持续运行的！如果在这两个调用之间有新数据写入（高度可能，因为 `apply` 和 `extract` 有计算开销），那么 `read_new()` 会把这些新数据也标记为"已消费"，导致**主循环启动后丢失若干样本**。

丢失的样本数 ≈ 校准处理耗时 × 500Hz。如果处理耗时 10ms，则丢失约 5 个样本。对于流式系统来说这不会造成功能错误（滤波器状态连续），但在严格的数据完整性要求下是一个缺口。

### 跨模块竞态 R-02: `EnvelopeExtractor` 的 Python `for` 循环性能瓶颈

[envelope.py L63-88](file:///d:/HomeworkProjects/sEMG/src/semg/processing/envelope.py#L63-L88) 使用纯 Python `for` 循环逐样本处理：

```python
for i in range(len(data)):
    new_sq = data[i] * data[i]
    ...
```

在 500Hz 采样率、5ms 处理间隔下，每次处理 2~3 个样本，循环开销可忽略。但如果未来提升采样率到 2kHz 或更高，或处理间隔抖动导致单次处理积累大量样本（如 100+），纯 Python 循环的性能将成为瓶颈（CPython 的 `for` 循环约 30~50ns/迭代，100 个样本 ≈ 3~5μs，仍然远低于 5ms 的处理间隔）。

**目前不构成实际风险**，但如果需要扩展到高采样率，应考虑用 Cython 或向量化 numpy 实现替代。

---

## 审计总结优先级矩阵

| ID | 风险 | 模块 | 核心问题 | 修复工作量 |
|----|------|------|---------|-----------|
| F-08 | 🔴 致命 | calibration / main.py | 校准包含 DSP 暖机瞬态 | 小（加一行切片） |
| F-04 | 🔴 致命 | serial_reader.py | 计数器非原子操作（no-GIL 下致命）| 小（加锁） |
| F-13 | 🟠 高危 | main.py | 日志无限增长（已 56MB）| 小（换 RotatingFileHandler）|
| F-10 | 🟠 高危 | envelope.py | 浮点累积漂移 + NaN 传播 | 中（加哨兵 + 定期重算）|
| F-05 | 🟠 高危 | serial_reader.py | 断联时批量缓存未清空 | 小（加 batch.clear()）|
| F-09 | 🟠 高危 | filters.py | 滤波器初始化语义陷阱 | 小（修正文档/值）|
| F-01 | 🟠 高危 | semg_reader.ino | micros 累加追赶风暴 | 小（加 anti-windup）|
| F-12 | 🟡 中危 | schmitt_trigger.py | time.time() vs monotonic() | 小（一行替换）|
| F-11 | 🟡 中危 | calibration.py | SNR 数学定义偏差 | 小（修正公式）|
| F-06 | 🟡 中危 | serial_reader.py | decode 策略不一致 | 小 |
| F-14 | 🟡 中危 | main.py | SIGINT 信号处理器 | 中（改用 Event）|
| F-02 | 🟡 中危 | semg_reader.ino | println 隐式阻塞 | 中 |
| F-07 | 🔵 技术债 | 协议设计 | 无帧序号/丢帧检测 | 中（改协议）|
| F-03 | 🔵 技术债 | semg_reader.ino | ADC 未使用 oversampling | 小 |
| F-15 | 🔵 技术债 | key_mapper.py | pyautogui 异常未捕获 | 小 |
| F-16 | 🔵 技术债 | main.py | 魔法数字未配置化 | 小 |
| F-17 | 🔵 技术债 | 跨模块 | 无断联通知/自动状态重置 | 中 |

> [!IMPORTANT]
> **建议优先修复顺序**：F-08 → F-04 → F-13 → F-12 → F-05 → F-10 → F-11。前三个可在 30 分钟内完成，收益最高。
