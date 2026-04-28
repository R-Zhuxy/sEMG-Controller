/*
 * sEMG 信号采集固件
 * 
 * 硬件: Arduino Nano V3 (ATmega328P) + 单通道干电极 sEMG 模块 (思知瑞)
 * 功能: 以 500Hz 固定采样率读取 A0 引脚的 ADC 值，通过串口发送至上位机
 * 
 * 串口格式: 每行一个整数 (0-1023)，以 '\n' 结尾
 * 波特率: 115200
 * 采样率: 500 Hz (2000μs 间隔)
 */

// ── 配置参数 ──────────────────────────────────────────
const int SENSOR_PIN = A0;              // sEMG 传感器模拟输入引脚
const unsigned long BAUD_RATE = 115200; // 串口波特率
const unsigned long SAMPLE_INTERVAL_US = 2000;  // 采样间隔 (μs) = 1/500Hz

// ── 全局变量 ──────────────────────────────────────────
unsigned long lastSampleTime = 0;       // 上次采样时间戳 (μs)

void setup() {
    // 初始化串口
    Serial.begin(BAUD_RATE);
    
    // 配置 ADC 引脚
    pinMode(SENSOR_PIN, INPUT);
    
    // 设置 ADC 参考电压为默认 (5V)
    analogReference(DEFAULT);
    
    // 预热: 丢弃前几次 ADC 读数 (消除启动瞬态)
    for (int i = 0; i < 10; i++) {
        analogRead(SENSOR_PIN);
        delayMicroseconds(100);
    }
    
    // 初始化计时器
    lastSampleTime = micros();
}

void loop() {
    unsigned long currentTime = micros();
    
    // 精确定时: 仅在达到采样间隔时执行
    if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_US) {
        lastSampleTime += SAMPLE_INTERVAL_US;  // 累加而非赋值，避免时间漂移
        
        // 读取 ADC 值 (10-bit: 0-1023)
        int adcValue = analogRead(SENSOR_PIN);
        
        // 通过串口发送 (纯文本，一行一个值)
        Serial.println(adcValue);
    }
}
