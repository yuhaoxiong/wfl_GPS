#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Management Module

Loads and validates configuration from YAML files and environment variables
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("PyYAML not found. Install with: pip install pyyaml")

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


@dataclass
class CameraConfig:
    """摄像头配置"""
    device: str = "/dev/video0"
    device2: Optional[str] = None  # 可选的第二路摄像头
    resolution: tuple = (1920, 1080)
    fps: int = 30
    jpeg_quality: int = 85


@dataclass
class GPSConfig:
    """GPS模块配置"""
    serial_port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    parity: str = "N"
    stopbits: int = 1
    timeout: float = 0.5
    slave_address: int = 1


@dataclass
class RetryConfig:
    """重试策略配置"""
    max_attempts: int = 5
    base_delay: float = 2.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


@dataclass
class OfflineQueueConfig:
    """离线队列配置"""
    enabled: bool = True
    max_size: int = 1000
    persist_path: str = "/var/lib/road-capture/queue.db"


@dataclass
class UploadConfig:
    """上传配置"""
    backend_url: str = "http://localhost:8000/api/upload"
    timeout: float = 10.0
    retry: RetryConfig = field(default_factory=RetryConfig)
    offline_queue: OfflineQueueConfig = field(default_factory=OfflineQueueConfig)


@dataclass
class SystemConfig:
    """系统配置"""
    device_id: str = "TERMINAL_001"
    log_level: str = "INFO"
    log_path: str = "/var/log/road-capture/app.log"
    capture_interval: float = 1.0  # 采集间隔(秒)


@dataclass
class Config:
    """应用配置"""
    camera: CameraConfig = field(default_factory=CameraConfig)
    gps: GPSConfig = field(default_factory=GPSConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    system: SystemConfig = field(default_factory=SystemConfig)


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_file: 配置文件路径,如果为None则使用默认路径
        """
        self.config_file = config_file or self._find_config_file()
        self.config = Config()

        # 加载.env文件(如果存在)
        if load_dotenv:
            env_file = Path(os.getcwd()) / ".env"
            if env_file.exists():
                load_dotenv(env_file)

    def _find_config_file(self) -> Optional[str]:
        """
        查找配置文件

        搜索顺序:
        1. ./config/config.yaml
        2. /etc/road-photo-capture/config.yaml
        3. ~/.config/road-photo-capture/config.yaml
        """
        search_paths = [
            Path(os.getcwd()) / "config" / "config.yaml",
            Path("/etc/road-photo-capture/config.yaml"),
            Path.home() / ".config" / "road-photo-capture" / "config.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        return None

    def load(self) -> Config:
        """
        加载配置

        优先级(从高到低):
        1. 环境变量
        2. YAML配置文件
        3. 默认值

        Returns:
            Config对象
        """
        # 1. 加载YAML文件
        if self.config_file and os.path.exists(self.config_file):
            self._load_from_yaml()

        # 2. 从环境变量覆盖
        self._load_from_env()

        # 3. 验证配置
        self._validate()

        return self.config

    def _load_from_yaml(self):
        """从YAML文件加载配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                return

            # 摄像头配置
            if 'camera' in data:
                cam = data['camera']
                self.config.camera.device = cam.get('device', self.config.camera.device)
                self.config.camera.device2 = cam.get('device2', self.config.camera.device2)
                if 'resolution' in cam:
                    self.config.camera.resolution = tuple(cam['resolution'])
                self.config.camera.fps = cam.get('fps', self.config.camera.fps)
                self.config.camera.jpeg_quality = cam.get('jpeg_quality', self.config.camera.jpeg_quality)

            # GPS配置
            if 'gps' in data:
                gps = data['gps']
                self.config.gps.serial_port = gps.get('serial_port', self.config.gps.serial_port)
                self.config.gps.baudrate = gps.get('baudrate', self.config.gps.baudrate)
                self.config.gps.parity = gps.get('parity', self.config.gps.parity)
                self.config.gps.stopbits = gps.get('stopbits', self.config.gps.stopbits)
                self.config.gps.timeout = gps.get('timeout', self.config.gps.timeout)
                self.config.gps.slave_address = gps.get('slave_address', self.config.gps.slave_address)

            # 上传配置
            if 'upload' in data:
                upload = data['upload']
                self.config.upload.backend_url = upload.get('backend_url', self.config.upload.backend_url)
                self.config.upload.timeout = upload.get('timeout', self.config.upload.timeout)

                # 重试配置
                if 'retry' in upload:
                    retry = upload['retry']
                    self.config.upload.retry.max_attempts = retry.get('max_attempts', self.config.upload.retry.max_attempts)
                    self.config.upload.retry.base_delay = retry.get('base_delay', self.config.upload.retry.base_delay)
                    self.config.upload.retry.max_delay = retry.get('max_delay', self.config.upload.retry.max_delay)
                    self.config.upload.retry.exponential_base = retry.get('exponential_base', self.config.upload.retry.exponential_base)

                # 离线队列配置
                if 'offline_queue' in upload:
                    queue = upload['offline_queue']
                    self.config.upload.offline_queue.enabled = queue.get('enabled', self.config.upload.offline_queue.enabled)
                    self.config.upload.offline_queue.max_size = queue.get('max_size', self.config.upload.offline_queue.max_size)
                    self.config.upload.offline_queue.persist_path = queue.get('persist_path', self.config.upload.offline_queue.persist_path)

            # 系统配置
            if 'system' in data:
                sys = data['system']
                self.config.system.device_id = sys.get('device_id', self.config.system.device_id)
                self.config.system.log_level = sys.get('log_level', self.config.system.log_level)
                self.config.system.log_path = sys.get('log_path', self.config.system.log_path)
                self.config.system.capture_interval = sys.get('capture_interval', self.config.system.capture_interval)

        except Exception as e:
            raise RuntimeError(f"Failed to load config from {self.config_file}: {e}")

    def _load_from_env(self):
        """从环境变量加载配置"""
        # 后台URL
        if 'BACKEND_API_URL' in os.environ:
            self.config.upload.backend_url = os.environ['BACKEND_API_URL']

        # GPS串口
        if 'GPS_SERIAL_PORT' in os.environ:
            self.config.gps.serial_port = os.environ['GPS_SERIAL_PORT']

        # 摄像头设备
        if 'CAMERA_DEVICE' in os.environ:
            self.config.camera.device = os.environ['CAMERA_DEVICE']
        if 'CAMERA_DEVICE2' in os.environ:
            self.config.camera.device2 = os.environ['CAMERA_DEVICE2']
            
        # 设备ID
        if 'DEVICE_ID' in os.environ:
            self.config.system.device_id = os.environ['DEVICE_ID']

        # 日志级别
        if 'LOG_LEVEL' in os.environ:
            self.config.system.log_level = os.environ['LOG_LEVEL'].upper()

        # 日志路径
        if 'LOG_PATH' in os.environ:
            self.config.system.log_path = os.environ['LOG_PATH']

        # GPS波特率
        if 'GPS_BAUDRATE' in os.environ:
            try:
                self.config.gps.baudrate = int(os.environ['GPS_BAUDRATE'])
            except ValueError:
                pass

        # 采集间隔
        if 'CAPTURE_INTERVAL' in os.environ:
            try:
                self.config.system.capture_interval = float(os.environ['CAPTURE_INTERVAL'])
            except ValueError:
                pass

    def _validate(self):
        """验证配置有效性"""
        errors = []

        # 验证摄像头分辨率
        if len(self.config.camera.resolution) != 2:
            errors.append("Camera resolution must be (width, height)")

        # 验证JPEG质量
        if not 1 <= self.config.camera.jpeg_quality <= 100:
            errors.append("JPEG quality must be between 1 and 100")

        # 验证GPS波特率
        valid_baudrates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
        if self.config.gps.baudrate not in valid_baudrates:
            errors.append(f"GPS baudrate must be one of {valid_baudrates}")

        # 验证GPS从站地址
        if not 1 <= self.config.gps.slave_address <= 254:
            errors.append("GPS slave address must be between 1 and 254")

        # 验证日志级别
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.config.system.log_level.upper() not in valid_log_levels:
            errors.append(f"Log level must be one of {valid_log_levels}")

        # 验证采集间隔
        if self.config.system.capture_interval <= 0:
            errors.append("Capture interval must be positive")

        # 验证后台URL
        if not self.config.upload.backend_url.startswith(('http://', 'https://')):
            errors.append("Backend URL must start with http:// or https://")

        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    def save_example_config(self, output_path: str):
        """
        保存示例配置文件

        Args:
            output_path: 输出文件路径
        """
        example_config = {
            'camera': {
                'device': self.config.camera.device,
                'resolution': list(self.config.camera.resolution),
                'fps': self.config.camera.fps,
                'jpeg_quality': self.config.camera.jpeg_quality,
            },
            'gps': {
                'serial_port': self.config.gps.serial_port,
                'baudrate': self.config.gps.baudrate,
                'parity': self.config.gps.parity,
                'stopbits': self.config.gps.stopbits,
                'timeout': self.config.gps.timeout,
                'slave_address': self.config.gps.slave_address,
            },
            'upload': {
                'backend_url': self.config.upload.backend_url,
                'timeout': self.config.upload.timeout,
                'retry': {
                    'max_attempts': self.config.upload.retry.max_attempts,
                    'base_delay': self.config.upload.retry.base_delay,
                    'max_delay': self.config.upload.retry.max_delay,
                    'exponential_base': self.config.upload.retry.exponential_base,
                },
                'offline_queue': {
                    'enabled': self.config.upload.offline_queue.enabled,
                    'max_size': self.config.upload.offline_queue.max_size,
                    'persist_path': self.config.upload.offline_queue.persist_path,
                },
            },
            'system': {
                'device_id': self.config.system.device_id,
                'log_level': self.config.system.log_level,
                'log_path': self.config.system.log_path,
                'capture_interval': self.config.system.capture_interval,
            },
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(example_config, f, default_flow_style=False, allow_unicode=True, indent=2)

        print(f"Example config saved to: {output_path}")


def load_config(config_file: Optional[str] = None) -> Config:
    """
    便捷函数: 加载配置

    Args:
        config_file: 配置文件路径

    Returns:
        Config对象
    """
    loader = ConfigLoader(config_file)
    return loader.load()


if __name__ == "__main__":
    """生成示例配置文件"""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "example":
        output = sys.argv[2] if len(sys.argv) > 2 else "config/config.yaml"
        os.makedirs(os.path.dirname(output), exist_ok=True)

        loader = ConfigLoader()
        loader.save_example_config(output)
    else:
        # 测试配置加载
        print("Testing configuration loader...")
        try:
            config = load_config()
            print("\nLoaded configuration:")
            print(f"  Camera: {config.camera.device} @ {config.camera.resolution}")
            print(f"  GPS: {config.gps.serial_port} @ {config.gps.baudrate} baud")
            print(f"  Upload: {config.upload.backend_url}")
            print(f"  Device ID: {config.system.device_id}")
            print(f"  Log level: {config.system.log_level}")
            print("\nConfiguration loaded successfully!")
        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)
