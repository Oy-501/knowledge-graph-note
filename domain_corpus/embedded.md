# domain: embedded

## 微控制器
别名: MCU, 单片机, Microcontroller
关系: STM32, ESP32, Arduino, GPIO, 嵌入式, ARM
微控制器简称 MCU，是嵌入式系统的核心芯片。STM32 和 ESP32 是两款主流微控制器。微控制器通过 GPIO 与外部设备通信。ARM 架构是大多数微控制器的核心架构。微控制器在物联网中广泛应用。

## STM32
别名: stm32
关系: 微控制器, ARM, C语言, HAL, 嵌入式, RTOS, GPIO
STM32 是意法半导体推出的 ARM 架构微控制器系列。STM32 使用 C语言开发，配合 HAL 库简化编程。STM32 在嵌入式领域应用广泛，常运行 RTOS。STM32 的 GPIO 引脚支持多种外设接口。STM32 与 ESP32 是两种不同的微控制器方案。

## ESP32
别名: esp32
关系: 微控制器, 物联网, WiFi, 蓝牙, FreeRTOS, GPIO
ESP32 是乐鑫科技推出的 Wi-Fi 蓝牙双模微控制器。ESP32 内置 WiFi 和蓝牙，非常适合物联网应用。ESP32 可运行 FreeRTOS 实现多任务。ESP32 的 GPIO 支持丰富的外设。ESP32 与 STM32 是嵌入式领域常见选型。

## Arduino
别名: arduino
关系: 微控制器, GPIO, 嵌入式, 传感器
Arduino 是开源微控制器平台，入门简单。Arduino 通过 GPIO 连接各种传感器。Arduino 适合嵌入式原型开发。Arduino 与 STM32 相比更偏教学和原型。

## Raspberry Pi
别名: 树莓派, raspberry, rpi
关系: 嵌入式Linux, 物联网, Python, GPIO, Linux
Raspberry Pi 树莓派是微型单板计算机，运行嵌入式Linux。Raspberry Pi 支持 Python 编程，GPIO 可连接传感器。Raspberry Pi 常用于物联网项目。Raspberry Pi 与 Arduino 不同，它运行完整的 Linux 操作系统。

## ARM
别名: ARM架构
关系: STM32, 微控制器, 嵌入式, C语言
ARM 是精简指令集架构，广泛用于微控制器。STM32 基于 ARM 架构设计。ARM 在嵌入式领域占主导地位。ARM 与 C语言配合开发嵌入式软件。ARM 的低功耗特性适合微控制器。

## RTOS
别名: 实时操作系统, Real-time OS
关系: FreeRTOS, 嵌入式, 任务调度, 中断
RTOS 是实时操作系统，保证任务在确定时间内完成。FreeRTOS 是最流行的开源 RTOS。RTOS 通过任务调度管理多个并发任务。RTOS 的中断处理对实时性至关重要。RTOS 广泛用于嵌入式系统。

## FreeRTOS
别名: freertos
关系: RTOS, ESP32, STM32, 任务调度, 中断
FreeRTOS 是开源 RTOS，广泛用于嵌入式。FreeRTOS 可运行在 ESP32 和 STM32 上。FreeRTOS 提供任务调度和中断管理。FreeRTOS 是 RTOS 的事实标准。FreeRTOS 与 RTOS 密不可分。

## GPIO
别名: 通用输入输出
关系: 微控制器, STM32, Arduino, Raspberry Pi, 嵌入式, PWM, ADC
GPIO 是通用输入输出引脚，是微控制器的核心接口。STM32 和 Arduino 通过 GPIO 连接外部设备。GPIO 可配置为输入或输出模式。PWM 和 ADC 功能可复用 GPIO 引脚。GPIO 是嵌入式硬件交互的基础。

## I2C
别名: IIC, TWI
关系: SPI, UART, 传感器, 嵌入式, GPIO
I2C 是两线串行通信协议，常连接传感器。I2C 与 SPI 和 UART 同为嵌入式常用总线。I2C 支持多设备挂载，地址区分。I2C 比 SPI 慢但引脚更少。I2C 通过 GPIO 引脚实现。

## SPI
别名: 
关系: I2C, UART, 传感器, 嵌入式, GPIO
SPI 是高速串行通信协议，用于连接传感器和外设。SPI 比 I2C 速度更快但需要更多引脚。SPI 与 I2C 和 UART 是嵌入式三大总线。SPI 常用于连接显示屏和存储器。SPI 通过 GPIO 实现通信。

## UART
别名: 串口, Serial
关系: I2C, SPI, 嵌入式, 调试, CAN
UART 是通用异步收发传输器，串口通信的基础。UART 用于嵌入式调试和通信。UART 比 I2C 和 SPI 更简单。UART 与 CAN 都是串行通信但用途不同。UART 是最基础的通信接口。

## CAN
别名: CAN总线, CAN bus
关系: UART, 嵌入式, 汽车电子
CAN 总线是工业和汽车电子常用的串行通信协议。CAN 比 UART 更可靠，支持差分传输。CAN 在嵌入式领域用于汽车电子系统。CAN 与 UART 是两种不同的串行通信方案。CAN 支持多主节点通信。

## PWM
别名: 脉宽调制
关系: GPIO, 电机, 嵌入式, Timer
PWM 脉宽调制通过 GPIO 输出可变占空比信号。PWM 常用于控制电机转速和亮度。PWM 依赖 Timer 定时器生成精确脉冲。PWM 是嵌入式控制的基础技术。PWM 与 ADC 互补，一个输出一个输入。

## ADC
别名: 模数转换, 模数转换器
关系: 传感器, 嵌入式, GPIO, DMA
ADC 模数转换器将模拟信号转为数字值。ADC 用于读取传感器数据。ADC 可通过 DMA 提高采样效率。ADC 与 GPIO 引脚复用。ADC 是嵌入式采集模拟量的核心。

## 中断
别名: Interrupt, IRQ
关系: Timer, DMA, RTOS, 嵌入式, GPIO
中断是嵌入式系统响应外部事件的核心机制。中断与 Timer 和 DMA 配合工作。RTOS 的任务调度依赖中断。GPIO 状态变化可触发外部中断。中断处理必须快速完成。

## Timer
别名: 定时器, 定时
关系: 中断, PWM, 嵌入式
Timer 定时器是嵌入式精确时间控制的基础。Timer 通过中断触发周期性任务。PWM 输出依赖 Timer 生成精确脉冲。Timer 是 RTOS 调度的底层支撑。Timer 与中断密不可分。

## DMA
别名: 直接内存访问
关系: 中断, 嵌入式, ADC
DMA 直接内存访问可不经 CPU 搬运数据。DMA 提高 ADC 采样效率，减轻 CPU 负担。DMA 与中断配合完成数据传输。DMA 是嵌入式高性能数据搬运的关键。DMA 减少 CPU 在数据搬运上的开销。

## 传感器
别名: Sensor
关系: ADC, I2C, SPI, 物联网, 嵌入式, Arduino
传感器是嵌入式系统感知外部环境的器件。传感器通过 ADC 输出模拟量或通过 I2C 和 SPI 输出数字量。Arduino 常连接各种传感器做原型。传感器是物联网的感知层。传感器数据采集是嵌入式的核心任务。

## 电机
别名: Motor, 马达
关系: PWM, 执行器, 嵌入式, GPIO
电机是嵌入式系统的执行器，将电信号转为机械运动。PWM 控制电机转速和方向。电机通过 GPIO 和驱动电路连接微控制器。电机与传感器配合实现闭环控制。电机是嵌入式控制的主要执行机构。

## 执行器
别名: Actuator
关系: 电机, 嵌入式, 传感器
执行器是嵌入式系统执行动作的器件，电机是最常见的执行器。执行器与传感器配合形成控制系统。执行器通过 GPIO 和 PWM 驱动。执行器是嵌入式输出层的核心。

## 固件
别名: Firmware
关系: Bootloader, 嵌入式, C语言, Flash
固件是嵌入式设备的底层软件，通常用 C语言编写。固件存储在 Flash 中，通过 Bootloader 加载。固件直接控制硬件资源。固件与 Bootloader 配合实现设备启动。固件更新是嵌入式维护的重要环节。

## Bootloader
别名: 引导加载程序
关系: 固件, 嵌入式, Flash, JTAG
Bootloader 是嵌入式设备上电后运行的第一段程序。Bootloader 负责加载固件到 Flash。Bootloader 可通过 JTAG 调试。Bootloader 与固件配合实现 OTA 升级。Bootloader 是嵌入式启动流程的核心。

## Flash
别名: 闪存
关系: Bootloader, 固件, 嵌入式
Flash 闪存是嵌入式设备存储固件的非易失性存储。Flash 存储 Bootloader 和固件代码。Flash 的擦写次数有限。Flash 与 Bootloader 配合实现程序加载。Flash 是嵌入式持久存储的基础。

## PCB
别名: 印制电路板, Printed Circuit Board
关系: 电路, 嵌入式, 硬件设计
PCB 印制电路板是嵌入式硬件的物理载体。PCB 上焊接电路元器件。PCB 设计是嵌入式硬件开发的关键。PCB 与电路设计密不可分。PCB 的布线影响信号完整性。

## 电路
别名: Circuit
关系: PCB, 嵌入式, 示波器
电路是电子元件的连接网络，PCB 的基础。电路设计是嵌入式硬件的核心。电路通过示波器调试和测量。电路与 PCB 共同构成硬件平台。电路分析是嵌入式工程师的基本功。

## 示波器
别名: Oscilloscope
关系: 电路, 调试, 嵌入式, UART
示波器是测量电信号的仪器，嵌入式调试必备。示波器用于观察电路波形。示波器可分析 UART 和 SPI 等通信信号。示波器与电路调试密不可分。示波器是硬件工程师的核心工具。

## 嵌入式Linux
别名: Embedded Linux
关系: Linux, Raspberry Pi, 嵌入式, Yocto, GPIO
嵌入式Linux 是运行在嵌入式设备上的 Linux 操作系统。Raspberry Pi 运行嵌入式Linux。嵌入式Linux 基于 Linux 内核裁剪。Yocto 是构建嵌入式Linux 的工具。嵌入式Linux 与 RTOS 是两种嵌入式 OS 方案。

## Yocto
别名: Yocto Project
关系: 嵌入式Linux, Linux, 嵌入式
Yocto 是构建嵌入式Linux 发行版的工具集。Yocto 基于 Linux 内核定制系统镜像。Yocto 让嵌入式Linux 构建更标准化。Yocto 与嵌入式Linux 密不可分。Yocto 简化了嵌入式Linux 定制。

## 物联网
别名: IoT
关系: ESP32, Raspberry Pi, 传感器, WiFi, 蓝牙, 嵌入式
物联网 IoT 将物理设备通过网络连接。ESP32 和 Raspberry Pi 是物联网常用平台。传感器是物联网的感知层。WiFi 和蓝牙是物联网通信方式。物联网与嵌入式技术密不可分。

## WiFi
别名: Wi-Fi, WLAN
关系: 物联网, ESP32, 蓝牙
WiFi 是无线局域网技术，物联网的主要通信方式。ESP32 内置 WiFi 模块。WiFi 与蓝牙是两种无线方案。WiFi 适合高速数据传输。WiFi 在物联网中用于设备联网。

## 蓝牙
别名: Bluetooth, BLE
关系: 物联网, ESP32, WiFi
蓝牙是短距离无线通信技术。ESP32 支持蓝牙 BLE。蓝牙与 WiFi 是两种物联网通信方案。蓝牙功耗低适合电池设备。蓝牙在物联网中用于低功耗连接。

## 调试
别名: Debug, debug
关系: UART, 示波器, JTAG, 嵌入式
调试是嵌入式开发发现和修复问题的过程。UART 串口是嵌入式调试的基础手段。示波器用于硬件电路调试。JTAG 用于固件级调试。调试贯穿嵌入式开发全流程。

## JTAG
别名: 
关系: 调试, 嵌入式, Bootloader, Flash
JTAG 是边界扫描和调试接口标准。JTAG 用于嵌入式固件烧录和调试。JTAG 可通过 Bootloader 进行 Flash 编程。JTAG 与调试密不可分。JTAG 是嵌入式底层调试的标准接口。

## 任务调度
别名: 调度, Scheduling
关系: RTOS, FreeRTOS, 中断, Timer
任务调度是 RTOS 管理多个任务的核心机制。FreeRTOS 提供抢占式任务调度。任务调度依赖 Timer 和中断。任务调度确保高优先级任务及时执行。任务调度是实时系统的关键。

## 汽车电子
别名: Automotive
关系: CAN, 嵌入式, RTOS
汽车电子是嵌入式在汽车领域的应用。CAN 总线是汽车电子的核心通信协议。汽车电子系统常运行 RTOS 保证实时性。汽车电子对嵌入式可靠性要求极高。汽车电子与 CAN 总线密不可分。

## 硬件设计
别名: Hardware Design
关系: PCB, 电路, 嵌入式
硬件设计是嵌入式开发的前端环节。硬件设计包括 PCB 和电路设计。硬件设计决定嵌入式系统的物理基础。硬件设计与嵌入式软件配合完成产品。硬件设计需要示波器等工具验证。
