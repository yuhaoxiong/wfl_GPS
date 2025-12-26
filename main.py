#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Road Photo Capture System - Main Entry Point

Usage:
  python main.py                    # Run with default config
  python main.py --config path.yaml # Run with custom config
  python main.py --debug            # Run in debug mode
"""

import sys
import signal
import argparse
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import load_config, Config
from main_controller import MainController


def signal_handler(signum, frame):
    """信号处理器(用于优雅退出)"""
    print("\n\nReceived signal, shutting down gracefully...")
    sys.exit(0)


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="Road Photo Capture System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                         # Run with default config
  python main.py --config config/config.yaml
  python main.py --debug                 # Enable debug output
  python main.py --test                  # Test mode (run 30 seconds)
        """
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )

    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode (run for 30 seconds then exit)'
    )

    parser.add_argument(
        '--health-check',
        action='store_true',
        help='Perform health check and exit'
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['normal', 'nogps'],
        default='normal',
        help='运行模式: normal (需要GPS), nogps (无GPS模式，位置和速度默认为0)'
    )

    args = parser.parse_args()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 打印启动信息
    print("=" * 70)
    print("Road Photo Capture System v1.0.0")
    print("=" * 70)

    try:
        # 加载配置
        print("\n[1/3] Loading configuration...")
        config = load_config(args.config)
        
        # 设置运行模式
        config.system.no_gps_mode = (args.mode == 'nogps')
        
        print(f"✓ Configuration loaded")
        print(f"    Device ID: {config.system.device_id}")
        print(f"    Mode: {args.mode}")
        print(f"    GPS Port: {config.gps.serial_port}")
        print(f"    Camera: {config.camera.device}")
        print(f"    Backend: {config.upload.backend_url}")
        print(f"    Interval: {config.system.capture_interval}s")

        # 创建主控制器
        print("\n[2/3] Initializing components...")
        controller = MainController(config, debug=args.debug)

        # 仅健康检查模式
        if args.health_check:
            print("\n[3/3] Performing health check...")
            if controller._health_check_all():
                print("\n✓ All systems healthy!")
                controller.close()
                return 0
            else:
                print("\n✗ Health check failed!")
                controller.close()
                return 1

        # 启动控制器
        print("\n[3/3] Starting capture system...")
        controller.start()

        print("\n" + "=" * 70)
        print("System running - Press Ctrl+C to stop")
        print("=" * 70)

        # 测试模式
        if args.test:
            print("\nTest mode: Running for 30 seconds...")
            import time
            time.sleep(30)
            print("\nTest completed!")
            controller.print_stats()
            controller.close()
            return 0

        # 正常运行模式
        try:
            # 定期打印统计信息
            import time
            while True:
                time.sleep(60)  # 每分钟打印一次
                if args.debug:
                    controller.print_stats()

        except KeyboardInterrupt:
            print("\n\nShutting down...")
            controller.print_stats()
            controller.close()
            print("\n✓ System stopped successfully")
            return 0

    except KeyboardInterrupt:
        print("\n\nShutdown requested during initialization")
        return 130

    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
