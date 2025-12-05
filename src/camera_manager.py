#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Camera Manager Module

Handles camera initialization, image capture, and Base64 encoding
"""

import base64
import io
import time
from typing import Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as e:
    raise ImportError(
        "OpenCV not found. Install with: pip install opencv-python"
    ) from e

try:
    from PIL import Image
except ImportError as e:
    raise ImportError(
        "Pillow not found. Install with: pip install Pillow"
    ) from e


@dataclass
class CaptureResult:
    """图像采集结果"""
    success: bool
    image_data: Optional[bytes] = None  # JPEG格式图像数据
    image_base64: Optional[str] = None  # Base64编码字符串
    timestamp: Optional[datetime] = None
    resolution: Optional[Tuple[int, int]] = None  # (width, height)
    file_size: int = 0  # 字节
    error_message: Optional[str] = None


class CameraManager:
    """
    摄像头管理器

    使用OpenCV进行摄像头控制和图像采集
    """

    def __init__(
        self,
        device: str = '/dev/video0',
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
        jpeg_quality: int = 85,
        auto_reconnect: bool = True,
        reconnect_delay: float = 3.0,
        max_reconnect_attempts: int = 3,
        debug: bool = False
    ):
        """
        初始化摄像头管理器

        Args:
            device: 摄像头设备路径 (Linux: /dev/videoX, Windows: 0/1/2)
            resolution: 分辨率 (width, height)
            fps: 帧率
            jpeg_quality: JPEG压缩质量 (1-100)
            auto_reconnect: 自动重连
            reconnect_delay: 重连延迟时间(秒)
            max_reconnect_attempts: 最大重连尝试次数
            debug: 调试模式
        """
        self.device = device
        self.resolution = resolution
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.debug = debug

        self.camera = None
        self._is_opened = False

        # 初始化摄像头
        self._init_camera()

    def _init_camera(self):
        """初始化摄像头"""
        try:
            # 解析设备路径
            device_index = self._parse_device()

            # 打开摄像头
            self.camera = cv2.VideoCapture(device_index)

            if not self.camera.isOpened():
                raise RuntimeError(f"Failed to open camera: {self.device}")

            # 设置分辨率
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])

            # 设置帧率
            self.camera.set(cv2.CAP_PROP_FPS, self.fps)

            # 验证实际分辨率
            actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(self.camera.get(cv2.CAP_PROP_FPS))

            if self.debug:
                print(f"Camera initialized: {self.device}")
                print(f"  Requested: {self.resolution[0]}x{self.resolution[1]} @ {self.fps}fps")
                print(f"  Actual: {actual_width}x{actual_height} @ {actual_fps}fps")

            # 预热摄像头(读取并丢弃前几帧)
            for _ in range(5):
                self.camera.read()

            self._is_opened = True

        except Exception as e:
            self._is_opened = False
            raise RuntimeError(f"Failed to initialize camera {self.device}: {e}")

    def _parse_device(self) -> Union[int, str]:
        """
        解析设备路径

        Returns:
            设备索引 (OpenCV使用整数索引)
        """
        # Windows: 直接使用数字索引
        if isinstance(self.device, int):
            return self.device

        # Linux: 从/dev/videoX提取索引
        if self.device.startswith('/dev/video'):
            try:
                return int(self.device.replace('/dev/video', ''))
            except ValueError:
                pass
                
        # 其他/dev/* 路径(如udev自定义别名)直接返回字符串
        if self.device.startswith('/dev/') and Path(self.device).exists():
            return self.device
            
        # 尝试直接转换为整数
        try:
            return int(self.device)
        except ValueError:
            pass

        # 默认使用0
        if self.debug:
            print(f"Warning: Could not parse device '{self.device}', using device string as fallback")
        return self.device

    def is_opened(self) -> bool:
        """
        检查摄像头是否已打开

        Returns:
            True: 已打开, False: 未打开
        """
        return self._is_opened and self.camera is not None and self.camera.isOpened()

    def capture(self) -> CaptureResult:
        """
        采集单帧图像

        Returns:
            CaptureResult对象
        """
        timestamp = datetime.now()
        
        # 尝试拍照，如果失败则进行重连
        for attempt in range(self.max_reconnect_attempts + 1):
            # 检查摄像头状态
            if not self.is_opened():
                if self.auto_reconnect and attempt < self.max_reconnect_attempts:
                    try:
                        if self.debug:
                            print(f"摄像头断开连接，尝试重连 (第 {attempt + 1}/{self.max_reconnect_attempts} 次)...")
                        
                        # 延迟后重连
                        if attempt > 0:  # 第一次检测到断开时不延迟，后续重试才延迟
                            if self.debug:
                                print(f"等待 {self.reconnect_delay} 秒后重试...")
                            time.sleep(self.reconnect_delay)
                        
                        # 关闭旧连接
                        if self.camera is not None:
                            try:
                                self.camera.release()
                            except:
                                pass
                        
                        # 重新初始化
                        self._init_camera()
                        
                        if self.debug:
                            print("摄像头重连成功")
                        
                    except Exception as e:
                        if self.debug:
                            print(f"重连失败: {e}")
                        
                        # 如果这是最后一次尝试，返回错误
                        if attempt >= self.max_reconnect_attempts - 1:
                            return CaptureResult(
                                success=False,
                                timestamp=timestamp,
                                error_message=f"重连失败 (尝试 {attempt + 1} 次): {e}"
                            )
                        # 否则继续下一次重试
                        continue
                else:
                    return CaptureResult(
                        success=False,
                        timestamp=timestamp,
                        error_message="摄像头未打开且自动重连已禁用"
                    )

            # 读取帧
            try:
                ret, frame = self.camera.read()

                if not ret or frame is None:
                    # 标记摄像头为断开状态
                    self._is_opened = False
                    
                    if self.auto_reconnect and attempt < self.max_reconnect_attempts:
                        if self.debug:
                            print(f"读取帧失败，尝试重连 (第 {attempt + 1}/{self.max_reconnect_attempts} 次)...")
                        
                        # 延迟后重试
                        if self.debug:
                            print(f"等待 {self.reconnect_delay} 秒后重试...")
                        time.sleep(self.reconnect_delay)
                        
                        # 继续下一次重试
                        continue
                    else:
                        return CaptureResult(
                            success=False,
                            timestamp=timestamp,
                            error_message=f"读取帧失败 (尝试 {attempt + 1} 次)"
                        )

                # 获取实际分辨率
                height, width = frame.shape[:2]

                # 压缩为JPEG
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                success, buffer = cv2.imencode('.jpg', frame, encode_params)

                if not success:
                    return CaptureResult(
                        success=False,
                        timestamp=timestamp,
                        error_message="图像JPEG编码失败"
                    )

                # 转换为bytes
                image_bytes = buffer.tobytes()

                # Base64编码
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')

                return CaptureResult(
                    success=True,
                    image_data=image_bytes,
                    image_base64=image_base64,
                    timestamp=timestamp,
                    resolution=(width, height),
                    file_size=len(image_bytes)
                )

            except cv2.error as e:
                # OpenCV 特定错误
                self._is_opened = False
                
                if self.auto_reconnect and attempt < self.max_reconnect_attempts:
                    if self.debug:
                        print(f"OpenCV错误: {e}，尝试重连 (第 {attempt + 1}/{self.max_reconnect_attempts} 次)...")
                    
                    # 延迟后重试
                    if self.debug:
                        print(f"等待 {self.reconnect_delay} 秒后重试...")
                    time.sleep(self.reconnect_delay)
                    
                    continue
                else:
                    return CaptureResult(
                        success=False,
                        timestamp=timestamp,
                        error_message=f"OpenCV错误 (尝试 {attempt + 1} 次): {e}"
                    )
                    
            except Exception as e:
                # 其他异常
                self._is_opened = False
                
                if self.auto_reconnect and attempt < self.max_reconnect_attempts:
                    if self.debug:
                        print(f"拍照异常: {e}，尝试重连 (第 {attempt + 1}/{self.max_reconnect_attempts} 次)...")
                    
                    # 延迟后重试
                    if self.debug:
                        print(f"等待 {self.reconnect_delay} 秒后重试...")
                    time.sleep(self.reconnect_delay)
                    
                    continue
                else:
                    return CaptureResult(
                        success=False,
                        timestamp=timestamp,
                        error_message=f"拍照异常 (尝试 {attempt + 1} 次): {e}"
                    )
        
        # 理论上不应该到这里
        return CaptureResult(
            success=False,
            timestamp=timestamp,
            error_message="拍照失败：超过最大重试次数"
        )

    def capture_to_file(self, filename: str) -> bool:
        """
        采集图像并保存到文件

        Args:
            filename: 输出文件路径

        Returns:
            True: 成功, False: 失败
        """
        result = self.capture()

        if result.success:
            try:
                with open(filename, 'wb') as f:
                    f.write(result.image_data)
                return True
            except Exception as e:
                if self.debug:
                    print(f"Failed to save image to {filename}: {e}")
                return False
        return False

    def test_capture(self, num_frames: int = 3) -> dict:
        """
        测试采集功能

        Args:
            num_frames: 测试帧数

        Returns:
            测试结果字典
        """
        results = {
            'success_count': 0,
            'fail_count': 0,
            'total_size': 0,
            'avg_size': 0,
            'resolutions': set(),
            'errors': []
        }

        for i in range(num_frames):
            result = self.capture()

            if result.success:
                results['success_count'] += 1
                results['total_size'] += result.file_size
                results['resolutions'].add(result.resolution)
            else:
                results['fail_count'] += 1
                results['errors'].append(result.error_message)

        if results['success_count'] > 0:
            results['avg_size'] = results['total_size'] / results['success_count']

        results['resolutions'] = list(results['resolutions'])

        return results

    def health_check(self) -> dict:
        """
        健康检查

        Returns:
            健康检查结果字典
        """
        health = {
            'camera_opened': False,
            'test_capture': False,
            'resolution': None,
            'fps': None,
            'errors': []
        }

        # 检查摄像头状态
        health['camera_opened'] = self.is_opened()

        if not health['camera_opened']:
            health['errors'].append("Camera is not opened")
            return health

        # 获取配置信息
        try:
            width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(self.camera.get(cv2.CAP_PROP_FPS))

            health['resolution'] = (width, height)
            health['fps'] = fps
        except Exception as e:
            health['errors'].append(f"Failed to get camera properties: {e}")

        # 测试采集
        result = self.capture()
        health['test_capture'] = result.success

        if not result.success:
            health['errors'].append(f"Test capture failed: {result.error_message}")

        return health

    def close(self):
        """关闭摄像头"""
        if self.camera is not None:
            self.camera.release()
            self._is_opened = False
            if self.debug:
                print("Camera closed")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __repr__(self) -> str:
        return (
            f"CameraManager(device='{self.device}', "
            f"resolution={self.resolution}, "
            f"jpeg_quality={self.jpeg_quality})"
        )


if __name__ == "__main__":
    """测试代码"""
    import sys
    import time

    # 命令行参数: python camera_manager.py [device] [output_file]
    device = sys.argv[1] if len(sys.argv) > 1 else '/dev/video0'
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Testing Camera Manager with device: {device}")
    print("-" * 70)

    try:
        with CameraManager(device=device, debug=True) as camera:
            # 健康检查
            print("\n1. Health Check:")
            health = camera.health_check()
            for key, value in health.items():
                print(f"   {key}: {value}")

            # 测试采集
            print("\n2. Test Capture (5 frames):")
            test_results = camera.test_capture(num_frames=5)
            print(f"   Success: {test_results['success_count']}/5")
            print(f"   Failed: {test_results['fail_count']}/5")
            print(f"   Avg size: {test_results['avg_size']/1024:.1f} KB")
            print(f"   Resolutions: {test_results['resolutions']}")

            if test_results['errors']:
                print(f"   Errors: {test_results['errors']}")

            # 单次采集演示
            print("\n3. Single Capture Demo:")
            result = camera.capture()

            if result.success:
                print(f"   ✓ Capture successful")
                print(f"   Timestamp: {result.timestamp}")
                print(f"   Resolution: {result.resolution}")
                print(f"   File size: {result.file_size/1024:.1f} KB")
                print(f"   Base64 length: {len(result.image_base64)} chars")

                # 保存到文件
                if output_file:
                    if camera.capture_to_file(output_file):
                        print(f"   ✓ Saved to: {output_file}")
                    else:
                        print(f"   ✗ Failed to save to: {output_file}")
                else:
                    # 保存默认文件
                    default_file = f"test_capture_{int(time.time())}.jpg"
                    if camera.capture_to_file(default_file):
                        print(f"   ✓ Saved to: {default_file}")
            else:
                print(f"   ✗ Capture failed: {result.error_message}")

            print("\n✓ Camera test completed successfully!")

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
