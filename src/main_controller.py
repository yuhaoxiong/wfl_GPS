#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Controller Module

Coordinates camera capture, GPS reading, and HTTP upload with 1Hz scheduling
"""

import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError as e:
    raise ImportError(
        "APScheduler not found. Install with: pip install APScheduler"
    ) from e

from gps_reader import GPSReader, GPSPosition
from camera_manager import CameraManager, CaptureResult
from upload_manager import UploadManager
from config import Config


class MainController:
    """
    主控制器

    负责1Hz定时调度,协调相机采集、GPS读取和数据上传
    """

    def __init__(self, config: Config, debug: bool = False):
        """
        初始化主控制器

        Args:
            config: 配置对象
            debug: 调试模式
        """
        self.config = config
        self.debug = debug

        # 组件
        self.gps_reader: Optional[GPSReader] = None
        self.camera_manager: Optional[CameraManager] = None  # 主摄像头(向后兼容引用)
        self.camera_managers: List[CameraManager] = []       # 支持多摄像头轮询
        self.camera_index: int = 0
        self.upload_manager: Optional[UploadManager] = None

        # 调度器
        self.scheduler: Optional[BackgroundScheduler] = None

        # 运行状态
        self.running = False
        self.paused = False

        # 统计信息
        self.stats = {
            'total_captures': 0,
            'successful_captures': 0,
            'failed_captures': 0,
            'gps_valid_count': 0,
            'gps_invalid_count': 0,
            'upload_count': 0,
            'start_time': None,
            'last_capture_time': None,
            'last_error': None
        }
        self.stats_lock = threading.Lock()

        # 初始化组件
        self._init_components()

    def _init_components(self):
        """初始化各组件"""
        try:
            # 初始化GPS读取器
            if self.debug:
                print("Initializing GPS reader...")

            self.gps_reader = GPSReader(
                port=self.config.gps.serial_port,
                slave_address=self.config.gps.slave_address,
                baudrate=self.config.gps.baudrate,
                timeout=self.config.gps.timeout,
                debug=self.debug
            )

            # 初始化摄像头管理器
            if self.debug:
                print("Initializing camera manager...")

            primary_cam = CameraManager(
                device=self.config.camera.device,
                resolution=self.config.camera.resolution,
                fps=self.config.camera.fps,
                jpeg_quality=self.config.camera.jpeg_quality,
                auto_reconnect=True,
                debug=self.debug
            )
            self.camera_managers.append(primary_cam)
            self.camera_manager = primary_cam  # 保留旧引用
            
            if self.config.camera.device2:
                try:
                    secondary_cam = CameraManager(
                        device=self.config.camera.device2,
                        resolution=self.config.camera.resolution,
                        fps=self.config.camera.fps,
                        jpeg_quality=self.config.camera.jpeg_quality,
                        auto_reconnect=True,
                        debug=self.debug
                    )
                    self.camera_managers.append(secondary_cam)
                except Exception as cam_err:
                    # 第二路是可选的, 打印警告但不阻塞主流程
                    print(f"⚠ Warning: failed to init secondary camera ({self.config.camera.device2}): {cam_err}")


            # 初始化上传管理器
            if self.debug:
                print("Initializing upload manager...")

            self.upload_manager = UploadManager(
                backend_url=self.config.upload.backend_url,
                timeout=self.config.upload.timeout,
                max_retries=self.config.upload.retry.max_attempts,
                retry_delay=self.config.upload.retry.base_delay,
                max_queue_size=self.config.upload.offline_queue.max_size,
                num_workers=2,
                debug=self.debug
            )

            # 初始化调度器
            self.scheduler = BackgroundScheduler()

            if self.debug:
                print("✓ All components initialized successfully")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize components: {e}")

    def _capture_task(self):
        """1Hz采集任务"""
        if self.paused:
            return

        capture_start = time.time()

        try:
            # 1. 采集图像
            if self.debug:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting capture cycle...")

            #capture_result = self.camera_manager.capture()
            if not self.camera_managers:
                raise RuntimeError("No camera managers initialized")

            # 轮询当前摄像头
            current_cam = self.camera_managers[self.camera_index]
            capture_result = current_cam.capture()
            # 下次切换到下一路
            self.camera_index = (self.camera_index + 1) % len(self.camera_managers)


            if not capture_result.success:
                if self.debug:
                    print(f"  ✗ Camera capture failed: {capture_result.error_message}")

                with self.stats_lock:
                    self.stats['failed_captures'] += 1
                    self.stats['total_captures'] += 1
                    self.stats['last_error'] = capture_result.error_message

                return

            if self.debug:
                print(f"  ✓ Camera captured: {capture_result.file_size/1024:.1f} KB")

            # 2. 读取GPS数据
            gps_data = self.gps_reader.get_position_dict()

            if gps_data['valid']:
                if self.debug:
                    loc = gps_data['location']
                    print(f"  ✓ GPS valid: {loc['latitude']:.5f}°, {loc['longitude']:.5f}°")

                with self.stats_lock:
                    self.stats['gps_valid_count'] += 1
            else:
                if self.debug:
                    print(f"  ⚠ GPS invalid: {gps_data['error']}")

                with self.stats_lock:
                    self.stats['gps_invalid_count'] += 1

            # 3. 打包数据
            location = gps_data.get('location') or {}
            lng_value = location.get('longitude') if gps_data['valid'] else None
            lat_value = location.get('latitude') if gps_data['valid'] else None
            speed_knots = location.get('speed_knots') if gps_data['valid'] else None
            speed_kmh = speed_knots * 1.852 if isinstance(speed_knots, (int, float)) else None
            payload = {
                "deviceCode": self.config.system.device_id,
                "lng": f"{lng_value:.6f}" if isinstance(lng_value, (int, float)) else "",
                "lat": f"{lat_value:.6f}" if isinstance(lat_value, (int, float)) else "",
                "img": capture_result.image_base64,
                "algTime": capture_result.timestamp.isoformat().replace("T", " "),
                "speed": f"{speed_kmh:.2f}" if isinstance(speed_kmh, (int, float)) else ""
            }

            # 4. 异步上传
            # 如果速度为0,不上传
            if speed_kmh is None or speed_kmh == 0:
                if self.debug:
                    print(f"  ⚠ Speed is 0, skipping upload")
            elif self.upload_manager.enqueue(payload):
                if self.debug:
                    print(f"  ✓ Enqueued for upload")

                with self.stats_lock:
                    self.stats['upload_count'] += 1
            else:
                if self.debug:
                    print(f"  ✗ Upload queue full")

                with self.stats_lock:
                    self.stats['last_error'] = "Upload queue full"

            # 更新统计
            with self.stats_lock:
                self.stats['successful_captures'] += 1
                self.stats['total_captures'] += 1
                self.stats['last_capture_time'] = datetime.now()

            # 计算耗时
            elapsed = time.time() - capture_start
            if self.debug:
                print(f"  ⏱ Cycle completed in {elapsed:.3f}s")

        except Exception as e:
            if self.debug:
                print(f"  ✗ Capture cycle error: {e}")

            with self.stats_lock:
                self.stats['failed_captures'] += 1
                self.stats['total_captures'] += 1
                self.stats['last_error'] = str(e)

    def start(self):
        """启动主控制器"""
        if self.running:
            if self.debug:
                print("Controller already running")
            return

        # 健康检查
        if not self._health_check_all():
            raise RuntimeError("Health check failed, cannot start controller")

        # 启动上传管理器
        self.upload_manager.start()

        # 配置调度器
        interval = self.config.system.capture_interval
        self.scheduler.add_job(
            self._capture_task,
            trigger=IntervalTrigger(seconds=interval),
            id='capture_job',
            name='1Hz Capture Task',
            max_instances=1  # 确保不会并发执行
        )

        # 启动调度器
        self.scheduler.start()

        self.running = True
        self.paused = False

        with self.stats_lock:
            self.stats['start_time'] = datetime.now()

        if self.debug:
            print(f"✓ Controller started (interval: {interval}s)")

    def stop(self):
        """停止主控制器"""
        if not self.running:
            return

        self.running = False

        # 停止调度器
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)

        # 停止上传管理器
        if self.upload_manager:
            self.upload_manager.stop(wait_completion=True)

        if self.debug:
            print("✓ Controller stopped")

    def pause(self):
        """暂停采集(不停止上传)"""
        self.paused = True
        if self.debug:
            print("Controller paused")

    def resume(self):
        """恢复采集"""
        self.paused = False
        if self.debug:
            print("Controller resumed")

    def _health_check_all(self) -> bool:
        """
        全面健康检查

        Returns:
            True: 健康, False: 不健康
        """
        if self.debug:
            print("\nPerforming health check...")

        all_healthy = True

        # 检查GPS
        if self.debug:
            print("  Checking GPS module...")

        gps_health = self.gps_reader.health_check()
        if not gps_health['communication']:
            print("  ✗ GPS communication failed")
            all_healthy = False
        elif self.debug:
            print(f"  ✓ GPS OK (version: {gps_health['version']})")

        # 检查摄像头(轮询所有已配置的摄像头)
        for idx, cam in enumerate(self.camera_managers, start=1):
            if self.debug:
                print(f"  Checking camera #{idx} ({cam.device})...")

            camera_health = cam.health_check()
            if not camera_health['camera_opened']:
                print(f"  ✗ Camera #{idx} not opened")
                all_healthy = False
            elif not camera_health['test_capture']:
                print(f"  ✗ Camera #{idx} test capture failed")
                all_healthy = False
            elif self.debug:
                print(f"  ✓ Camera #{idx} OK (resolution: {camera_health['resolution']})")

        # 检查上传管理器
        if self.debug:
            print("  Checking upload manager...")

        upload_health = self.upload_manager.health_check()
        if upload_health['errors']:
            print(f"  ⚠ Upload warnings: {upload_health['errors']}")
        elif self.debug:
            print(f"  ✓ Upload OK (backend reachable: {upload_health['backend_reachable']})")

        return all_healthy

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        with self.stats_lock:
            stats = self.stats.copy()

        # 添加上传统计
        upload_stats = self.upload_manager.get_stats()
        stats['upload_stats'] = upload_stats

        # 计算运行时间
        if stats['start_time']:
            uptime = datetime.now() - stats['start_time']
            stats['uptime_seconds'] = uptime.total_seconds()

        # 计算成功率
        if stats['total_captures'] > 0:
            stats['capture_success_rate'] = (
                stats['successful_captures'] / stats['total_captures'] * 100
            )
            stats['gps_valid_rate'] = (
                stats['gps_valid_count'] / stats['total_captures'] * 100
            )

        return stats

    def print_stats(self):
        """打印统计信息"""
        stats = self.get_stats()

        print("\n" + "=" * 70)
        print("Road Photo Capture System - Statistics")
        print("=" * 70)

        print(f"\nCapture Statistics:")
        print(f"  Total captures: {stats['total_captures']}")
        print(f"  Successful: {stats['successful_captures']}")
        print(f"  Failed: {stats['failed_captures']}")
        if 'capture_success_rate' in stats:
            print(f"  Success rate: {stats['capture_success_rate']:.1f}%")

        print(f"\nGPS Statistics:")
        print(f"  Valid: {stats['gps_valid_count']}")
        print(f"  Invalid: {stats['gps_invalid_count']}")
        if 'gps_valid_rate' in stats:
            print(f"  Valid rate: {stats['gps_valid_rate']:.1f}%")

        print(f"\nUpload Statistics:")
        upload_stats = stats.get('upload_stats', {})
        print(f"  Enqueued: {stats.get('upload_count', 0)}")
        print(f"  Uploaded: {upload_stats.get('total_uploaded', 0)}")
        print(f"  Failed: {upload_stats.get('total_failed', 0)}")
        print(f"  Queue length: {upload_stats.get('queue_length', 0)}")

        if stats.get('uptime_seconds'):
            uptime = stats['uptime_seconds']
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)
            print(f"\nUptime: {hours:02d}:{minutes:02d}:{seconds:02d}")

        if stats.get('last_capture_time'):
            print(f"Last capture: {stats['last_capture_time'].strftime('%Y-%m-%d %H:%M:%S')}")

        if stats.get('last_error'):
            print(f"\nLast error: {stats['last_error']}")

        print("=" * 70)

    def close(self):
        """关闭所有组件"""
        self.stop()

        if self.gps_reader:
            self.gps_reader.close()

        for cam in self.camera_managers:
            cam.close()

        if self.upload_manager:
            self.upload_manager.close()

        if self.debug:
            print("✓ All components closed")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __repr__(self) -> str:
        return f"MainController(running={self.running}, paused={self.paused})"


if __name__ == "__main__":
    """测试代码"""
    import sys
    from config import load_config

    print("Testing Main Controller")
    print("-" * 70)

    try:
        # 加载配置
        print("\nLoading configuration...")
        config = load_config()
        print(f"✓ Configuration loaded")
        print(f"  Device ID: {config.system.device_id}")
        print(f"  Capture interval: {config.system.capture_interval}s")

        # 创建控制器
        print("\nInitializing controller...")
        with MainController(config, debug=True) as controller:
            # 启动
            print("\nStarting controller...")
            controller.start()

            # 运行10秒
            print("\nRunning for 10 seconds (press Ctrl+C to stop)...")
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                print("\n\nInterrupted by user")

            # 打印统计
            controller.print_stats()

            print("\n✓ Controller test completed!")

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
