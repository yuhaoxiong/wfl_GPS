#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPS Reader Module - HS6602 GPS/BeiDou Module via RS485 Modbus RTU

This module provides interface to HS6602 GPS/BeiDou positioning module
using RS485 serial communication with Modbus RTU protocol.

Hardware Specifications:
- Model: HS6602-485/232
- Protocol: Modbus RTU
- Interface: RS485
- Default: 9600 baud, No parity, 1 stop bit
- Default slave address: 0x01
"""

import struct
import time
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Optional, Dict, Any

try:
    import minimalmodbus
    import serial
except ImportError as e:
    raise ImportError(
        "Required dependencies not found. Install with: "
        "pip install minimalmodbus pyserial"
    ) from e


class PositioningStatus(IntEnum):
    """GPS定位状态"""
    INVALID = 0  # 定位无效
    VALID = 1    # 定位有效


class AntennaStatus(IntEnum):
    """天线状态"""
    GOOD = 0      # 良好
    OPEN = 1      # 开路
    SHORT = 2     # 短路


class DirectionCode(IntEnum):
    """方向代码"""
    EAST = 0x45   # 'E' - 东经
    WEST = 0x57   # 'W' - 西经
    NORTH = 0x4E  # 'N' - 北纬
    SOUTH = 0x53  # 'S' - 南纬


@dataclass
class GPSPosition:
    """GPS位置数据结构"""
    valid: bool                        # 定位是否有效
    latitude: Optional[float] = None   # 纬度 (度)
    longitude: Optional[float] = None  # 经度 (度)
    altitude: Optional[float] = None   # 海拔高度 (0.1米)
    lat_direction: Optional[str] = None  # 纬度方向 ('N'/'S')
    lon_direction: Optional[str] = None  # 经度方向 ('E'/'W')
    timestamp: Optional[datetime] = None  # 北京时间时间戳
    antenna_status: Optional[str] = None  # 天线状态
    gps_satellites: int = 0            # GPS定位卫星数
    bds_satellites: int = 0            # 北斗定位卫星数
    speed: Optional[float] = None      # 对地速度 (节)
    heading: Optional[float] = None    # 对地航向 (度)
    error_message: Optional[str] = None  # 错误信息


class GPSModbusRegisters:
    """HS6602 Modbus寄存器地址定义"""
    # 配置寄存器
    VERSION = 0x0001           # 版本号 (只读)
    SLAVE_ADDRESS = 0x0002     # 从站地址 (读写)
    BAUDRATE = 0x0003          # 波特率 (读写)
    PARITY = 0x0004            # 奇偶校验 (读写)
    POSITIONING_MODE = 0x0005  # 定位模式 (读写)
    UPDATE_RATE = 0x0006       # 更新频率 (读写)

    # 状态寄存器
    POSITIONING_STATUS = 0x000A  # 定位状态 (只读)
    ANTENNA_STATUS = 0x000B      # 天线状态 (只读)

    # UTC时间寄存器
    UTC_YEAR = 0x000C
    UTC_MONTH = 0x000D
    UTC_DAY = 0x000E
    UTC_HOUR = 0x000F
    UTC_MINUTE = 0x0010
    UTC_SECOND = 0x0011

    # 北京时间寄存器 (东八区)
    BEIJING_YEAR = 0x0012
    BEIJING_MONTH = 0x0013
    BEIJING_DAY = 0x0014
    BEIJING_HOUR = 0x0015
    BEIJING_MINUTE = 0x0016
    BEIJING_SECOND = 0x0017

    # 位置寄存器
    LONGITUDE_DIRECTION = 0x0018  # 经度方向
    LONGITUDE_VALUE = 0x0019      # 经度值 (Float, 2寄存器)
    LATITUDE_DIRECTION = 0x001B   # 纬度方向
    LATITUDE_VALUE = 0x001C       # 纬度值 (Float, 2寄存器)
    ALTITUDE = 0x001E             # 海拔高度 (Float, 2寄存器)

    # 运动参数
    GROUND_SPEED = 0x0020         # 对地速度 (Float, 2寄存器)
    GROUND_HEADING = 0x0022       # 对地航向 (Float, 2寄存器)

    # 卫星信息
    GPS_SATELLITES_USED = 0x0024    # GPS定位卫星数
    GPS_SATELLITES_VISIBLE = 0x0025 # GPS可见卫星数
    BDS_SATELLITES_USED = 0x0026    # 北斗定位卫星数
    BDS_SATELLITES_VISIBLE = 0x0027 # 北斗可见卫星数


class GPSReader:
    """
    HS6602 GPS/BeiDou模块读取器

    使用Modbus RTU协议通过RS485串口读取GPS定位数据
    """

    def __init__(
        self,
        port: str = '/dev/ttyUSB0',
        slave_address: int = 1,
        baudrate: int = 9600,
        timeout: float = 0.5,
        debug: bool = False
    ):
        """
        初始化GPS读取器

        Args:
            port: 串口设备路径 (例如: '/dev/ttyUSB0', 'COM3')
            slave_address: Modbus从站地址 (默认: 1)
            baudrate: 波特率 (默认: 9600)
            timeout: 串口读取超时时间(秒) (默认: 0.5)
            debug: 是否启用调试模式
        """
        self.port = port
        self.slave_address = slave_address
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug

        # 初始化Modbus仪表
        self.instrument = None
        self._init_instrument()

    def _init_instrument(self):
        """初始化Modbus通信"""
        try:
            self.instrument = minimalmodbus.Instrument(
                self.port,
                self.slave_address,
                mode=minimalmodbus.MODE_RTU
            )

            # 配置串口参数
            self.instrument.serial.baudrate = self.baudrate
            self.instrument.serial.bytesize = 8
            self.instrument.serial.parity = serial.PARITY_NONE
            self.instrument.serial.stopbits = 1
            self.instrument.serial.timeout = self.timeout

            # 配置Modbus参数
            self.instrument.clear_buffers_before_each_transaction = True
            self.instrument.close_port_after_each_call = False

            if self.debug:
                self.instrument.debug = True
                print(f"GPS Reader initialized: {self.port} @ {self.baudrate} baud")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize GPS module on {self.port}: {e}")

    def _read_register(self, register_address: int, retry: int = 3) -> Optional[int]:
        """
        读取单个16位寄存器

        Args:
            register_address: 寄存器地址
            retry: 重试次数

        Returns:
            寄存器值,失败返回None
        """
        for attempt in range(retry):
            try:
                value = self.instrument.read_register(
                    register_address,
                    functioncode=3  # 0x03: 读保持寄存器
                )
                return value
            except Exception as e:
                if attempt == retry - 1:
                    if self.debug:
                        print(f"Failed to read register 0x{register_address:04X}: {e}")
                    return None
                time.sleep(0.05)  # 重试前短暂延迟
        return None

    def _read_float(self, register_address: int, retry: int = 3) -> Optional[float]:
        """
        读取32位浮点数 (占用2个寄存器)

        Args:
            register_address: 起始寄存器地址
            retry: 重试次数

        Returns:
            浮点数值,失败返回None
        """
        for attempt in range(retry):
            try:
                # minimalmodbus的read_float默认使用大端序,占用2个寄存器
                value = self.instrument.read_float(
                    register_address,
                    functioncode=3,
                    number_of_registers=2
                )
                return value
            except Exception as e:
                if attempt == retry - 1:
                    if self.debug:
                        print(f"Failed to read float at 0x{register_address:04X}: {e}")
                    return None
                time.sleep(0.05)
        return None

    def read_version(self) -> Optional[str]:
        """
        读取模块版本号

        Returns:
            版本号字符串 (例如: "1.0"), 失败返回None
        """
        version_raw = self._read_register(GPSModbusRegisters.VERSION)
        if version_raw is None:
            return None

        # 版本号为BCD码格式: 高4位为主版本,低4位为次版本
        major = (version_raw >> 4) & 0x0F
        minor = version_raw & 0x0F
        return f"{major}.{minor}"

    def check_positioning_status(self) -> bool:
        """
        检查定位状态

        Returns:
            True: 定位有效, False: 定位无效
        """
        status = self._read_register(GPSModbusRegisters.POSITIONING_STATUS)
        return status == PositioningStatus.VALID if status is not None else False

    def check_antenna_status(self) -> Optional[str]:
        """
        检查天线状态

        Returns:
            天线状态字符串: 'good', 'open', 'short', 或None
        """
        status = self._read_register(GPSModbusRegisters.ANTENNA_STATUS)
        if status is None:
            return None

        status_map = {
            AntennaStatus.GOOD: 'good',
            AntennaStatus.OPEN: 'open',
            AntennaStatus.SHORT: 'short'
        }
        return status_map.get(status, 'unknown')

    def _read_beijing_time(self) -> Optional[datetime]:
        """
        读取北京时间 (东八区)

        Returns:
            datetime对象, 失败返回None
        """
        try:
            year = self._read_register(GPSModbusRegisters.BEIJING_YEAR)
            month = self._read_register(GPSModbusRegisters.BEIJING_MONTH)
            day = self._read_register(GPSModbusRegisters.BEIJING_DAY)
            hour = self._read_register(GPSModbusRegisters.BEIJING_HOUR)
            minute = self._read_register(GPSModbusRegisters.BEIJING_MINUTE)
            second = self._read_register(GPSModbusRegisters.BEIJING_SECOND)

            if None in (year, month, day, hour, minute, second):
                return None

            return datetime(year, month, day, hour, minute, second)
        except ValueError as e:
            if self.debug:
                print(f"Invalid time values: {e}")
            return None

    def read_gps_data(self) -> GPSPosition:
        """
        读取完整GPS定位数据

        Returns:
            GPSPosition对象,包含所有定位信息
        """
        # 1. 检查定位状态
        positioning_valid = self.check_positioning_status()

        if not positioning_valid:
            return GPSPosition(
                valid=False,
                error_message="Positioning invalid - waiting for GPS fix"
            )

        # 2. 检查天线状态
        antenna_status = self.check_antenna_status()
        if antenna_status in ('open', 'short'):
            return GPSPosition(
                valid=False,
                antenna_status=antenna_status,
                error_message=f"Antenna fault: {antenna_status}"
            )

        # 3. 读取经纬度
        lon_dir_code = self._read_register(GPSModbusRegisters.LONGITUDE_DIRECTION)
        lon_value = self._read_float(GPSModbusRegisters.LONGITUDE_VALUE)
        lat_dir_code = self._read_register(GPSModbusRegisters.LATITUDE_DIRECTION)
        lat_value = self._read_float(GPSModbusRegisters.LATITUDE_VALUE)

        if None in (lon_dir_code, lon_value, lat_dir_code, lat_value):
            return GPSPosition(
                valid=False,
                error_message="Failed to read position data"
            )

        # 解析方向
        lon_direction = 'E' if lon_dir_code == DirectionCode.EAST else 'W'
        lat_direction = 'N' if lat_dir_code == DirectionCode.NORTH else 'S'

        # 4. 读取其他数据
        altitude = self._read_float(GPSModbusRegisters.ALTITUDE)
        speed = self._read_float(GPSModbusRegisters.GROUND_SPEED)
        heading = self._read_float(GPSModbusRegisters.GROUND_HEADING)
        timestamp = self._read_beijing_time()

        # 5. 读取卫星信息
        gps_sats = self._read_register(GPSModbusRegisters.GPS_SATELLITES_USED) or 0
        bds_sats = self._read_register(GPSModbusRegisters.BDS_SATELLITES_USED) or 0

        return GPSPosition(
            valid=True,
            latitude=lat_value,
            longitude=lon_value,
            altitude=altitude,
            lat_direction=lat_direction,
            lon_direction=lon_direction,
            timestamp=timestamp,
            antenna_status=antenna_status,
            gps_satellites=gps_sats,
            bds_satellites=bds_sats,
            speed=speed,
            heading=heading
        )

    def get_position_dict(self) -> Dict[str, Any]:
        """
        读取GPS数据并转换为字典格式 (便于JSON序列化)

        Returns:
            包含GPS数据的字典
        """
        position = self.read_gps_data()

        result = {
            'valid': position.valid,
            'timestamp': position.timestamp.isoformat() if position.timestamp else None,
            'location': None,
            'status': {
                'antenna': position.antenna_status,
                'satellites': {
                    'gps': position.gps_satellites,
                    'beidou': position.bds_satellites
                }
            },
            'error': position.error_message
        }

        if position.valid:
            result['location'] = {
                'latitude': position.latitude,
                'longitude': position.longitude,
                'altitude': position.altitude,
                'direction': {
                    'lat': position.lat_direction,
                    'lon': position.lon_direction
                },
                'speed_knots': position.speed,
                'heading_degrees': position.heading
            }

        return result

    def health_check(self) -> Dict[str, Any]:
        """
        执行健康检查

        Returns:
            健康检查结果字典
        """
        health = {
            'communication': False,
            'version': None,
            'positioning': False,
            'antenna': None,
            'errors': []
        }

        # 测试通信
        try:
            version = self.read_version()
            if version:
                health['communication'] = True
                health['version'] = version
            else:
                health['errors'].append("Failed to read version")
        except Exception as e:
            health['errors'].append(f"Communication error: {e}")

        # 检查定位
        if health['communication']:
            health['positioning'] = self.check_positioning_status()
            health['antenna'] = self.check_antenna_status()

            if not health['positioning']:
                health['errors'].append("GPS positioning not ready")

            if health['antenna'] in ('open', 'short'):
                health['errors'].append(f"Antenna fault: {health['antenna']}")

        return health

    def close(self):
        """关闭串口连接"""
        if self.instrument and self.instrument.serial.is_open:
            self.instrument.serial.close()
            if self.debug:
                print("GPS Reader closed")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __repr__(self) -> str:
        return (
            f"GPSReader(port='{self.port}', "
            f"slave_address={self.slave_address}, "
            f"baudrate={self.baudrate})"
        )


if __name__ == "__main__":
    """测试代码"""
    import sys

    # 命令行参数: python gps_reader.py /dev/ttyUSB0
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'

    print(f"Testing GPS Reader on {port}")
    print("-" * 60)

    try:
        with GPSReader(port=port, debug=True) as gps:
            # 健康检查
            print("\n1. Health Check:")
            health = gps.health_check()
            for key, value in health.items():
                print(f"   {key}: {value}")

            # 读取GPS数据
            print("\n2. GPS Data (5 samples):")
            for i in range(5):
                data = gps.get_position_dict()
                print(f"\n   Sample {i+1}:")
                print(f"   Valid: {data['valid']}")
                print(f"   Timestamp: {data['timestamp']}")
                if data['valid']:
                    loc = data['location']
                    print(f"   Position: {loc['latitude']:.5f}°{loc['direction']['lat']}, "
                          f"{loc['longitude']:.5f}°{loc['direction']['lon']}")
                    print(f"   Altitude: {loc['altitude']:.1f}m")
                    print(f"   Satellites: GPS={data['status']['satellites']['gps']}, "
                          f"BeiDou={data['status']['satellites']['beidou']}")
                else:
                    print(f"   Error: {data['error']}")

                time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        sys.exit(1)
