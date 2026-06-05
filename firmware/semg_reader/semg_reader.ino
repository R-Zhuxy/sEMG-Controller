/*
 * sEMG 信号采集固件 v0.3
 *
 * 硬件: Arduino Nano V3 (ATmega328P) + 单通道干电极 sEMG 模块 (思知瑞)
 * 功能: 以 500Hz 固定采样率读取 A0 引脚的真实 ADC 值，通过串口发送至上位机
 *
 * 串口协议 (文本格式):
 *   - 启动完成后发送一行 "READY\n" 哨兵帧，标志数据流开始
 *   - 随后每行一个整数 (0-1023)，以 '\n' 结尾
 *   - 波特率: 115200
 *   - 采样率: 500 Hz (间隔 2000μs)
 *
 * 带宽估算: max 6 bytes/sample × 500 Hz = 3000 B/s ≈ 26% 带宽占用，
 *           文本格式安全可靠，无需二进制帧同步协议。
 *
 * 严格遵守非阻塞原则: 全程使用 micros() 计时，禁止 delay()。
 */

// ── 配置参数 ──────────────────────────────────────────────────────────────────
const int          SENSOR_PIN         = A0;     // sEMG 传感器模拟输入引脚
const unsigned long BAUD_RATE         = 115200; // 串口波特率 (与上位机 config.py 一致)
const unsigned long SAMPLE_INTERVAL_US = 2000;  // 采样间隔 (μs) = 1/500Hz
const int          WARMUP_READS       = 16;     // 预热 ADC 读数次数 (消除启动瞬态)

// ── 全局变量 ──────────────────────────────────────────────────────────────────
unsigned long lastSampleTime = 0;   // 上次采样时间戳 (μs)，累加式防止时间漂移

void setup() {
    // 初始化串口
    Serial.begin(BAUD_RATE);

    // 配置 ADC：使用默认 5V 参考电压，引脚设为输入
    analogReference(DEFAULT);
    pinMode(SENSOR_PIN, INPUT);

    // 预热 ADC：连续读取并丢弃，稳定内部电容充电状态
    // 注意：此处使用 delayMicroseconds 仅用于 ADC 预热，
    //       不在主采样循环中使用，不违反非阻塞原则。
    for (int i = 0; i < WARMUP_READS; i++) {
        analogRead(SENSOR_PIN);
        delayMicroseconds(200);
    }

    // 发送哨兵帧：通知上位机固件已就绪，数据流即将开始
    // 上位机收到 "READY" 后可立即启动数据接收，无需盲等固定时长
    Serial.println("READY");

    // 初始化计时器（在 println 之后，避免首帧时间偏差）
    lastSampleTime = micros();
}

void loop() {
    unsigned long currentTime = micros();

    // 非阻塞精确定时：仅在达到采样间隔时采样一次
    if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_US) {
        // 累加而非赋值，防止因 loop() 执行耗时导致的长期时间漂移
        lastSampleTime += SAMPLE_INTERVAL_US;

        // F-01: 增加追赶保护（anti-windup guard），防范阻塞解除后产生采样风暴
        // 如果落后时间超过 10 个采样周期（约 20ms），直接跳跃重置到当前时间，重新对齐
        if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_US * 10) {
            lastSampleTime = currentTime;
        }

        // 读取真实传感器 ADC 值 (10-bit: 0-1023)
        int adcValue = analogRead(SENSOR_PIN);

        // F-02: 发送前校验 FIFO 发送缓冲区空闲字节数，防止缓冲区满时导致 micros() 采样定时停滞
        // 每一帧文本格式的数据长度最大为: "1023\r\n" = 6 字节
        if (Serial.availableForWrite() >= 6) {
            Serial.println(adcValue);
        }
        // 如果 FIFO 空间不足，则丢弃本帧数据，优先保证采样定时的绝对精准
    }
}
