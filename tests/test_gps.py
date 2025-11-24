#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for GPS Reader Module

Tests GPS communication and data parsing functionality
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gps_reader import (
    GPSReader,
    GPSPosition,
    PositioningStatus,
    AntennaStatus,
    DirectionCode,
    GPSModbusRegisters
)


class TestGPSReader(unittest.TestCase):
    """GPS Reader模块测试"""

    def setUp(self):
        """测试前准备"""
        self.mock_instrument = Mock()
        self.patcher = patch('gps_reader.minimalmodbus.Instrument')
        self.mock_instrument_class = self.patcher.start()
        self.mock_instrument_class.return_value = self.mock_instrument

    def tearDown(self):
        """测试后清理"""
        self.patcher.stop()

    def test_initialization(self):
        """测试GPS Reader初始化"""
        gps = GPSReader(
            port='/dev/ttyUSB0',
            slave_address=1,
            baudrate=9600,
            timeout=0.5
        )

        self.assertEqual(gps.port, '/dev/ttyUSB0')
        self.assertEqual(gps.slave_address, 1)
        self.assertEqual(gps.baudrate, 9600)
        self.assertEqual(gps.timeout, 0.5)

    def test_read_version(self):
        """测试版本号读取"""
        # 模拟版本号0x0010 -> V1.0
        self.mock_instrument.read_register.return_value = 0x0010

        gps = GPSReader(port='/dev/ttyUSB0')
        version = gps.read_version()

        self.assertEqual(version, "1.0")
        self.mock_instrument.read_register.assert_called_with(
            GPSModbusRegisters.VERSION,
            functioncode=3
        )

    def test_check_positioning_status_valid(self):
        """测试定位状态检查 - 有效"""
        self.mock_instrument.read_register.return_value = PositioningStatus.VALID

        gps = GPSReader(port='/dev/ttyUSB0')
        status = gps.check_positioning_status()

        self.assertTrue(status)

    def test_check_positioning_status_invalid(self):
        """测试定位状态检查 - 无效"""
        self.mock_instrument.read_register.return_value = PositioningStatus.INVALID

        gps = GPSReader(port='/dev/ttyUSB0')
        status = gps.check_positioning_status()

        self.assertFalse(status)

    def test_check_antenna_status(self):
        """测试天线状态检查"""
        test_cases = [
            (AntennaStatus.GOOD, 'good'),
            (AntennaStatus.OPEN, 'open'),
            (AntennaStatus.SHORT, 'short'),
        ]

        for status_code, expected in test_cases:
            with self.subTest(status=expected):
                self.mock_instrument.read_register.return_value = status_code

                gps = GPSReader(port='/dev/ttyUSB0')
                status = gps.check_antenna_status()

                self.assertEqual(status, expected)

    def test_read_gps_data_invalid_positioning(self):
        """测试GPS数据读取 - 定位无效"""
        # 模拟定位状态无效
        self.mock_instrument.read_register.return_value = PositioningStatus.INVALID

        gps = GPSReader(port='/dev/ttyUSB0')
        position = gps.read_gps_data()

        self.assertFalse(position.valid)
        self.assertIsNotNone(position.error_message)

    def test_read_gps_data_antenna_fault(self):
        """测试GPS数据读取 - 天线故障"""
        # 模拟定位有效但天线开路
        def side_effect(register, *args, **kwargs):
            if register == GPSModbusRegisters.POSITIONING_STATUS:
                return PositioningStatus.VALID
            elif register == GPSModbusRegisters.ANTENNA_STATUS:
                return AntennaStatus.OPEN
            return 0

        self.mock_instrument.read_register.side_effect = side_effect

        gps = GPSReader(port='/dev/ttyUSB0')
        position = gps.read_gps_data()

        self.assertFalse(position.valid)
        self.assertEqual(position.antenna_status, 'open')
        self.assertIn('Antenna fault', position.error_message)

    def test_read_gps_data_valid(self):
        """测试GPS数据读取 - 有效定位"""
        # 模拟完整GPS数据
        def read_register_side_effect(register, *args, **kwargs):
            register_map = {
                GPSModbusRegisters.POSITIONING_STATUS: PositioningStatus.VALID,
                GPSModbusRegisters.ANTENNA_STATUS: AntennaStatus.GOOD,
                GPSModbusRegisters.LONGITUDE_DIRECTION: DirectionCode.EAST,
                GPSModbusRegisters.LATITUDE_DIRECTION: DirectionCode.NORTH,
                GPSModbusRegisters.BEIJING_YEAR: 2025,
                GPSModbusRegisters.BEIJING_MONTH: 11,
                GPSModbusRegisters.BEIJING_DAY: 7,
                GPSModbusRegisters.BEIJING_HOUR: 15,
                GPSModbusRegisters.BEIJING_MINUTE: 30,
                GPSModbusRegisters.BEIJING_SECOND: 45,
                GPSModbusRegisters.GPS_SATELLITES_USED: 8,
                GPSModbusRegisters.BDS_SATELLITES_USED: 6,
            }
            return register_map.get(register, 0)

        def read_float_side_effect(register, *args, **kwargs):
            float_map = {
                GPSModbusRegisters.LONGITUDE_VALUE: 117.12583,
                GPSModbusRegisters.LATITUDE_VALUE: 36.67438,
                GPSModbusRegisters.ALTITUDE: 125.5,
                GPSModbusRegisters.GROUND_SPEED: 0.0,
                GPSModbusRegisters.GROUND_HEADING: 0.0,
            }
            return float_map.get(register, 0.0)

        self.mock_instrument.read_register.side_effect = read_register_side_effect
        self.mock_instrument.read_float.side_effect = read_float_side_effect

        gps = GPSReader(port='/dev/ttyUSB0')
        position = gps.read_gps_data()

        # 验证结果
        self.assertTrue(position.valid)
        self.assertAlmostEqual(position.latitude, 36.67438, places=5)
        self.assertAlmostEqual(position.longitude, 117.12583, places=5)
        self.assertEqual(position.lat_direction, 'N')
        self.assertEqual(position.lon_direction, 'E')
        self.assertAlmostEqual(position.altitude, 125.5, places=1)
        self.assertEqual(position.gps_satellites, 8)
        self.assertEqual(position.bds_satellites, 6)
        self.assertEqual(position.antenna_status, 'good')
        self.assertIsNotNone(position.timestamp)
        self.assertEqual(position.timestamp.year, 2025)
        self.assertEqual(position.timestamp.month, 11)
        self.assertEqual(position.timestamp.day, 7)

    def test_get_position_dict(self):
        """测试GPS数据字典转换"""
        # 重用valid定位测试的mock
        def read_register_side_effect(register, *args, **kwargs):
            register_map = {
                GPSModbusRegisters.POSITIONING_STATUS: PositioningStatus.VALID,
                GPSModbusRegisters.ANTENNA_STATUS: AntennaStatus.GOOD,
                GPSModbusRegisters.LONGITUDE_DIRECTION: DirectionCode.EAST,
                GPSModbusRegisters.LATITUDE_DIRECTION: DirectionCode.NORTH,
                GPSModbusRegisters.BEIJING_YEAR: 2025,
                GPSModbusRegisters.BEIJING_MONTH: 11,
                GPSModbusRegisters.BEIJING_DAY: 7,
                GPSModbusRegisters.BEIJING_HOUR: 15,
                GPSModbusRegisters.BEIJING_MINUTE: 30,
                GPSModbusRegisters.BEIJING_SECOND: 45,
                GPSModbusRegisters.GPS_SATELLITES_USED: 8,
                GPSModbusRegisters.BDS_SATELLITES_USED: 6,
            }
            return register_map.get(register, 0)

        def read_float_side_effect(register, *args, **kwargs):
            float_map = {
                GPSModbusRegisters.LONGITUDE_VALUE: 117.12583,
                GPSModbusRegisters.LATITUDE_VALUE: 36.67438,
                GPSModbusRegisters.ALTITUDE: 125.5,
                GPSModbusRegisters.GROUND_SPEED: 0.0,
                GPSModbusRegisters.GROUND_HEADING: 0.0,
            }
            return float_map.get(register, 0.0)

        self.mock_instrument.read_register.side_effect = read_register_side_effect
        self.mock_instrument.read_float.side_effect = read_float_side_effect

        gps = GPSReader(port='/dev/ttyUSB0')
        data_dict = gps.get_position_dict()

        # 验证字典结构
        self.assertTrue(data_dict['valid'])
        self.assertIsNotNone(data_dict['timestamp'])
        self.assertIsNotNone(data_dict['location'])
        self.assertEqual(data_dict['location']['latitude'], 36.67438)
        self.assertEqual(data_dict['location']['longitude'], 117.12583)
        self.assertEqual(data_dict['location']['direction']['lat'], 'N')
        self.assertEqual(data_dict['location']['direction']['lon'], 'E')
        self.assertEqual(data_dict['status']['satellites']['gps'], 8)
        self.assertEqual(data_dict['status']['satellites']['beidou'], 6)

    def test_health_check(self):
        """测试健康检查"""
        # 模拟健康状态
        def read_register_side_effect(register, *args, **kwargs):
            register_map = {
                GPSModbusRegisters.VERSION: 0x0010,
                GPSModbusRegisters.POSITIONING_STATUS: PositioningStatus.VALID,
                GPSModbusRegisters.ANTENNA_STATUS: AntennaStatus.GOOD,
            }
            return register_map.get(register, 0)

        self.mock_instrument.read_register.side_effect = read_register_side_effect

        gps = GPSReader(port='/dev/ttyUSB0')
        health = gps.health_check()

        self.assertTrue(health['communication'])
        self.assertEqual(health['version'], '1.0')
        self.assertTrue(health['positioning'])
        self.assertEqual(health['antenna'], 'good')
        self.assertEqual(len(health['errors']), 0)

    def test_context_manager(self):
        """测试上下文管理器"""
        with GPSReader(port='/dev/ttyUSB0') as gps:
            self.assertIsNotNone(gps)
            self.assertIsNotNone(gps.instrument)

        # 验证close被调用
        # (实际串口在mock中,这里主要测试语法正确性)


class TestGPSPosition(unittest.TestCase):
    """GPS位置数据结构测试"""

    def test_gps_position_invalid(self):
        """测试无效定位数据"""
        pos = GPSPosition(
            valid=False,
            error_message="Test error"
        )

        self.assertFalse(pos.valid)
        self.assertEqual(pos.error_message, "Test error")
        self.assertIsNone(pos.latitude)
        self.assertIsNone(pos.longitude)

    def test_gps_position_valid(self):
        """测试有效定位数据"""
        timestamp = datetime(2025, 11, 7, 15, 30, 45)
        pos = GPSPosition(
            valid=True,
            latitude=36.67438,
            longitude=117.12583,
            altitude=125.5,
            lat_direction='N',
            lon_direction='E',
            timestamp=timestamp,
            antenna_status='good',
            gps_satellites=8,
            bds_satellites=6
        )

        self.assertTrue(pos.valid)
        self.assertAlmostEqual(pos.latitude, 36.67438)
        self.assertAlmostEqual(pos.longitude, 117.12583)
        self.assertEqual(pos.lat_direction, 'N')
        self.assertEqual(pos.lon_direction, 'E')
        self.assertEqual(pos.timestamp, timestamp)


if __name__ == '__main__':
    unittest.main(verbosity=2)
