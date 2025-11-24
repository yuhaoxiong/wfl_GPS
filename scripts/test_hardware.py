#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Test Script for GPS Module

Tests GPS module connectivity and functionality
Usage: python test_hardware.py [port] [baudrate]
"""

import sys
import time
import argparse
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gps_reader import GPSReader


def print_separator(char="-", length=70):
    """打印分隔线"""
    print(char * length)


def test_communication(gps: GPSReader) -> bool:
    """测试通信连接"""
    print("\n1. Communication Test")
    print_separator()

    try:
        version = gps.read_version()
        if version:
            print(f"   ✓ Communication OK")
            print(f"   ✓ Module version: {version}")
            return True
        else:
            print(f"   ✗ Failed to read version")
            return False
    except Exception as e:
        print(f"   ✗ Communication error: {e}")
        return False


def test_positioning(gps: GPSReader, duration: int = 10) -> bool:
    """测试定位功能"""
    print(f"\n2. Positioning Test ({duration}s)")
    print_separator()

    valid_count = 0

    for i in range(duration):
        status = gps.check_positioning_status()
        if status:
            valid_count += 1
            print(f"   [{i+1:2d}/{duration}] ✓ Positioning: VALID")
        else:
            print(f"   [{i+1:2d}/{duration}] ✗ Positioning: INVALID (waiting for GPS fix...)")

        time.sleep(1)

    success_rate = (valid_count / duration) * 100
    print(f"\n   Success rate: {success_rate:.1f}% ({valid_count}/{duration})")

    return valid_count > 0


def test_antenna(gps: GPSReader) -> bool:
    """测试天线状态"""
    print("\n3. Antenna Test")
    print_separator()

    antenna = gps.check_antenna_status()
    if antenna:
        status_symbols = {
            'good': '✓',
            'open': '✗',
            'short': '✗'
        }
        symbol = status_symbols.get(antenna, '?')
        print(f"   {symbol} Antenna status: {antenna.upper()}")

        if antenna == 'good':
            return True
        else:
            print(f"   WARNING: Antenna fault detected!")
            return False
    else:
        print(f"   ✗ Failed to read antenna status")
        return False


def test_position_data(gps: GPSReader, samples: int = 5) -> bool:
    """测试位置数据读取"""
    print(f"\n4. Position Data Test ({samples} samples)")
    print_separator()

    valid_samples = 0

    for i in range(samples):
        position = gps.read_gps_data()

        print(f"\n   Sample {i+1}/{samples}:")
        print(f"   Valid: {position.valid}")

        if position.valid:
            valid_samples += 1
            print(f"   Timestamp: {position.timestamp}")
            print(f"   Position: {position.latitude:.6f}°{position.lat_direction}, "
                  f"{position.longitude:.6f}°{position.lon_direction}")
            print(f"   Altitude: {position.altitude:.1f}m")
            print(f"   Satellites: GPS={position.gps_satellites}, BeiDou={position.bds_satellites}")
            print(f"   Antenna: {position.antenna_status}")

            if position.speed is not None:
                print(f"   Speed: {position.speed:.2f} knots")
            if position.heading is not None:
                print(f"   Heading: {position.heading:.2f}°")
        else:
            print(f"   Error: {position.error_message}")

        if i < samples - 1:
            time.sleep(1)

    return valid_samples > 0


def test_data_format(gps: GPSReader) -> bool:
    """测试数据格式转换"""
    print("\n5. Data Format Test (JSON)")
    print_separator()

    try:
        data_dict = gps.get_position_dict()

        print(f"   Valid: {data_dict['valid']}")
        print(f"   Timestamp: {data_dict['timestamp']}")

        if data_dict['valid']:
            loc = data_dict['location']
            print(f"   Location:")
            print(f"     Lat: {loc['latitude']:.6f}° {loc['direction']['lat']}")
            print(f"     Lon: {loc['longitude']:.6f}° {loc['direction']['lon']}")
            print(f"     Alt: {loc['altitude']:.1f}m")

            sats = data_dict['status']['satellites']
            print(f"   Satellites: GPS={sats['gps']}, BeiDou={sats['beidou']}")

            return True
        else:
            print(f"   Error: {data_dict['error']}")
            return False

    except Exception as e:
        print(f"   ✗ Format conversion error: {e}")
        return False


def run_health_check(gps: GPSReader):
    """运行健康检查"""
    print("\n6. Health Check")
    print_separator()

    health = gps.health_check()

    print(f"   Communication: {'✓ OK' if health['communication'] else '✗ FAILED'}")
    if health['version']:
        print(f"   Version: {health['version']}")

    print(f"   Positioning: {'✓ VALID' if health['positioning'] else '✗ INVALID'}")

    if health['antenna']:
        antenna_ok = health['antenna'] == 'good'
        print(f"   Antenna: {'✓' if antenna_ok else '✗'} {health['antenna'].upper()}")

    if health['errors']:
        print(f"\n   Errors:")
        for error in health['errors']:
            print(f"     - {error}")


def main():
    """主测试函数"""
    parser = argparse.ArgumentParser(
        description="GPS Module Hardware Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_hardware.py                     # Default: /dev/ttyUSB0 @ 9600
  python test_hardware.py /dev/ttyUSB1        # Custom port
  python test_hardware.py /dev/ttyUSB0 115200 # Custom baudrate
  python test_hardware.py COM3 9600           # Windows COM port
        """
    )

    parser.add_argument(
        'port',
        nargs='?',
        default='/dev/ttyUSB0',
        help='Serial port (default: /dev/ttyUSB0)'
    )

    parser.add_argument(
        'baudrate',
        nargs='?',
        type=int,
        default=9600,
        help='Baudrate (default: 9600)'
    )

    parser.add_argument(
        '--slave-address',
        type=int,
        default=1,
        help='Modbus slave address (default: 1)'
    )

    parser.add_argument(
        '--timeout',
        type=float,
        default=0.5,
        help='Serial timeout in seconds (default: 0.5)'
    )

    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick test mode (shorter duration)'
    )

    args = parser.parse_args()

    # 测试参数
    positioning_duration = 5 if args.quick else 10
    position_samples = 3 if args.quick else 5

    # 打印测试信息
    print("=" * 70)
    print("GPS Module Hardware Test")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Port: {args.port}")
    print(f"  Baudrate: {args.baudrate}")
    print(f"  Slave address: {args.slave_address}")
    print(f"  Timeout: {args.timeout}s")
    print(f"  Mode: {'Quick' if args.quick else 'Standard'}")

    # 初始化GPS读取器
    try:
        print(f"\nInitializing GPS reader...")
        gps = GPSReader(
            port=args.port,
            slave_address=args.slave_address,
            baudrate=args.baudrate,
            timeout=args.timeout,
            debug=False
        )
        print("✓ GPS reader initialized")

    except Exception as e:
        print(f"✗ Failed to initialize GPS reader: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if the GPS module is connected")
        print("  2. Verify the serial port path")
        print("  3. Check serial port permissions (sudo usermod -a -G dialout $USER)")
        print("  4. Try a different baudrate")
        sys.exit(1)

    # 运行测试
    results = {}

    try:
        with gps:
            results['communication'] = test_communication(gps)

            if results['communication']:
                results['antenna'] = test_antenna(gps)
                results['positioning'] = test_positioning(gps, positioning_duration)
                results['position_data'] = test_position_data(gps, position_samples)
                results['data_format'] = test_data_format(gps)

                run_health_check(gps)

            # 测试总结
            print("\n" + "=" * 70)
            print("Test Summary")
            print("=" * 70)

            if results['communication']:
                passed = sum(1 for v in results.values() if v)
                total = len(results)

                print(f"\nTests passed: {passed}/{total}")
                print(f"\nResults:")
                for test_name, result in results.items():
                    status = "✓ PASS" if result else "✗ FAIL"
                    print(f"  {status}  {test_name.replace('_', ' ').title()}")

                if passed == total:
                    print("\n✓ All tests passed! GPS module is working correctly.")
                    return 0
                else:
                    print("\n⚠ Some tests failed. Check the results above.")
                    return 1
            else:
                print("\n✗ Communication test failed. Cannot proceed with other tests.")
                return 1

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 130

    except Exception as e:
        print(f"\n\nUnexpected error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
