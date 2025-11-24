# 道路拍照上传系统 (Road Photo Capture System)

基于Debian 11的终端设备道路拍照与GPS定位系统,实现每秒自动拍照并上传至后台服务器。

## 系统特性

- ✅ **1Hz精确采集**: 每秒触发一次摄像头拍照+GPS定位
- ✅ **RS485 GPS模块**: 支持HS6602 GPS/北斗双模定位模块(Modbus RTU协议)
- ✅ **HTTP上传**: JSON格式数据上传,图片Base64编码
- ✅ **离线队列**: 网络中断时自动缓存,恢复后重传
- ✅ **健壮设计**: 完善的错误处理、重试机制、健康检查
- ✅ **生产就绪**: Systemd服务支持,适合24/7运行

## 系统架构

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Camera    │  │ GPS Module  │  │   Upload    │
│  Manager    │  │  (RS485)    │  │   Manager   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┴────────────────┘
                        │
            ┌───────────▼───────────┐
            │  Main Controller      │
            │  (1Hz Scheduler)      │
            └───────────┬───────────┘
                        │
            ┌───────────▼───────────┐
            │  Data Processor       │
            │  (JSON + Base64)      │
            └───────────────────────┘
```

## 硬件要求

- **处理器**: ARM/x86, 推荐树莓派4或同等性能
- **系统**: Debian 11 (Bullseye) 或兼容发行版
- **内存**: 最低256MB,推荐512MB+
- **摄像头**: USB摄像头或CSI摄像头模块
- **GPS模块**: HS6602-485 (RS485接口,Modbus RTU)
- **串口**: USB转RS485转换器或板载RS485接口

## 快速开始

### 1. 系统依赖安装

```bash
# 更新包管理器
sudo apt update

# 安装系统依赖
sudo apt install -y \
    python3.9 \
    python3-pip \
    python3-dev \
    v4l-utils \
    libopencv-dev \
    build-essential

# 配置串口权限
sudo usermod -a -G dialout $USER
sudo usermod -a -G video $USER

# 注销并重新登录以应用组权限
```

### 2. Python依赖安装

```bash
# 克隆或下载项目
cd /opt
sudo git clone <repo_url> road-photo-capture
cd road-photo-capture

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 硬件测试

```bash
# 测试GPS模块连接
python scripts/test_hardware.py /dev/ttyUSB0 9600

# 快速测试模式
python scripts/test_hardware.py /dev/ttyUSB0 --quick

# Windows COM口测试
python scripts/test_hardware.py COM3 9600
```

预期输出:
```
======================================================================
GPS Module Hardware Test
======================================================================
...
✓ Communication OK
✓ Module version: 1.0
✓ Antenna status: GOOD
✓ Positioning: VALID
...
✓ All tests passed! GPS module is working correctly.
```

### 4. 配置系统

```bash
# 生成示例配置文件
python src/config.py example config/config.yaml

# 编辑配置
nano config/config.yaml
```

关键配置项:
```yaml
camera:
  device: "/dev/video0"        # 摄像头设备路径
  resolution: [1920, 1080]     # 分辨率
  jpeg_quality: 85             # JPEG压缩质量

gps:
  serial_port: "/dev/ttyUSB0"  # GPS串口设备
  baudrate: 9600               # 波特率
  slave_address: 1             # Modbus从站地址

upload:
  backend_url: "http://192.168.1.100:8000/api/upload"  # 后台URL

system:
  device_id: "TERMINAL_001"    # 设备唯一标识
  log_level: "INFO"            # 日志级别
```

### 5. 运行单元测试

```bash
# 运行GPS模块测试
python -m pytest tests/test_gps.py -v

# 运行所有测试
python -m pytest tests/ -v --cov=src
```

## 项目结构

```
road-photo-capture/
├── src/                      # 源代码
│   ├── gps_reader.py        # GPS模块通信 ✅
│   ├── camera_manager.py    # 摄像头管理 ✅
│   ├── upload_manager.py    # HTTP上传 ✅
│   ├── main_controller.py   # 主控制器 ✅
│   ├── config.py            # 配置管理 ✅
│   └── utils/               # 工具模块
├── tests/                   # 单元测试
│   └── test_gps.py         # GPS测试 ✅
├── scripts/                 # 脚本工具
│   ├── test_hardware.py    # 硬件测试 ✅
│   └── install.sh          # 安装脚本 ✅
├── config/                  # 配置文件
│   ├── config.yaml         # 主配置
│   └── .env.example        # 环境变量模板 ✅
├── systemd/                 # Systemd服务
│   └── road-photo-capture.service ✅
├── main.py                 # 主入口脚本 ✅
├── requirements.txt         # Python依赖 ✅
└── README.md               # 项目文档 ✅
```

## GPS模块使用

### 基本用法

```python
from src.gps_reader import GPSReader

# 初始化GPS读取器
with GPSReader(port='/dev/ttyUSB0', baudrate=9600) as gps:
    # 读取GPS数据
    position = gps.read_gps_data()

    if position.valid:
        print(f"位置: {position.latitude}°N, {position.longitude}°E")
        print(f"海拔: {position.altitude}m")
        print(f"时间: {position.timestamp}")
        print(f"卫星: GPS={position.gps_satellites}, 北斗={position.bds_satellites}")
    else:
        print(f"定位无效: {position.error_message}")
```

### 获取JSON格式数据

```python
# 获取字典格式(可直接序列化为JSON)
data = gps.get_position_dict()

import json
print(json.dumps(data, indent=2, ensure_ascii=False))
```

输出示例:
```json
{
  "valid": true,
  "timestamp": "2025-11-07T15:30:45+08:00",
  "location": {
    "latitude": 36.67438,
    "longitude": 117.12583,
    "altitude": 125.5,
    "direction": {
      "lat": "N",
      "lon": "E"
    }
  },
  "status": {
    "antenna": "good",
    "satellites": {
      "gps": 8,
      "beidou": 6
    }
  }
}
```

## GPS模块技术规格

- **型号**: HS6602-485
- **定位系统**: GPS + 北斗双模
- **通信接口**: RS485 (Modbus RTU协议)
- **默认配置**: 9600 baud, 无校验, 1停止位
- **定位精度**: 2.5米 (CEP50)
- **工作电压**: DC 5-30V
- **功耗**: ≤1W
- **工作温度**: -40℃ ~ 85℃

## 常见问题

### GPS模块无法通信

```bash
# 1. 检查设备是否被识别
ls -l /dev/ttyUSB*

# 2. 检查串口权限
groups  # 确认包含 dialout 组

# 3. 测试串口通信
sudo minicom -D /dev/ttyUSB0 -b 9600

# 4. 运行硬件测试
python scripts/test_hardware.py /dev/ttyUSB0 9600
```

### 定位一直无效

1. **检查天线连接**: 确保GPS天线正确连接
2. **室外测试**: GPS需要开阔天空,室内无法定位
3. **等待冷启动**: 首次启动可能需要5-10分钟获取卫星信号
4. **查看天线状态**:
   ```python
   antenna = gps.check_antenna_status()
   print(f"天线状态: {antenna}")  # 应为 'good'
   ```

### 摄像头打开失败

```bash
# 列出可用摄像头
v4l2-ctl --list-devices

# 测试摄像头
ffplay /dev/video0

# 检查权限
sudo usermod -a -G video $USER
```

## 系统运行

### 快速启动

```bash
# 1. 生成配置文件
python src/config.py example config/config.yaml

# 2. 编辑配置
nano config/config.yaml

# 3. 健康检查
python main.py --health-check

# 4. 测试运行(30秒)
python main.py --test

# 5. 正常运行
python main.py
```

### 生产部署

```bash
# 1. 运行安装脚本
sudo bash scripts/install.sh

# 2. 编辑配置
sudo nano /etc/road-photo-capture/config.yaml

# 3. 启动服务
sudo systemctl start road-photo-capture

# 4. 查看状态
sudo systemctl status road-photo-capture

# 5. 查看日志
sudo journalctl -u road-photo-capture -f
```

### 服务管理

```bash
# 启动服务
sudo systemctl start road-photo-capture

# 停止服务
sudo systemctl stop road-photo-capture

# 重启服务
sudo systemctl restart road-photo-capture

# 开机自启
sudo systemctl enable road-photo-capture

# 禁用自启
sudo systemctl disable road-photo-capture
```

## 后续开发建议

- [ ] 实现离线队列持久化(SQLite)
- [ ] 添加结构化日志系统 (Loguru)
- [ ] 编写集成测试与压力测试
- [ ] 添加Web监控界面
- [ ] 实现图像预处理(降噪、增强)
- [ ] 支持视频流采集模式

## 开发规范

### 代码风格
- 遵循PEP 8规范
- 使用类型注解
- 完善的文档字符串

### 测试要求
- 单元测试覆盖率 > 80%
- 硬件测试通过
- 集成测试通过

### Git提交
```bash
# 功能开发
git commit -m "feat: 实现摄像头管理模块"

# Bug修复
git commit -m "fix: 修复GPS超时问题"

# 文档更新
git commit -m "docs: 更新安装文档"
```

## 许可证

MIT License

## 联系方式

- 项目负责人: Road Capture Team
- 技术支持: [技术支持邮箱]
- 问题反馈: [GitHub Issues]

---

**当前状态**: 核心功能已完成 ✅ | 生产就绪 🚀
