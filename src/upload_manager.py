#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload Manager Module

Handles HTTP upload with retry mechanism and offline queue
"""

import time
import json
import queue
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
except ImportError as e:
    raise ImportError(
        "Requests library not found. Install with: pip install requests"
    ) from e


@dataclass
class UploadResult:
    """上传结果"""
    success: bool
    status_code: Optional[int] = None
    response_data: Optional[dict] = None
    error_message: Optional[str] = None
    upload_time: Optional[datetime] = None
    retry_count: int = 0


class UploadManager:
    """
    HTTP上传管理器

    支持异步上传、失败重试、离线队列
    """

    def __init__(
        self,
        backend_url: str,
        timeout: float = 10.0,
        max_retries: int = 5,
        retry_delay: float = 2.0,
        max_queue_size: int = 1000,
        num_workers: int = 2,
        debug: bool = False
    ):
        """
        初始化上传管理器

        Args:
            backend_url: 后台API地址
            timeout: 请求超时时间(秒)
            max_retries: 最大重试次数
            retry_delay: 重试基础延迟(秒)
            max_queue_size: 最大队列长度
            num_workers: 工作线程数
            debug: 调试模式
        """
        self.backend_url = backend_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_queue_size = max_queue_size
        self.num_workers = num_workers
        self.debug = debug

        # 上传队列
        self.upload_queue = queue.Queue(maxsize=max_queue_size)

        # 统计信息
        self.stats = {
            'total_uploaded': 0,
            'total_failed': 0,
            'queue_length': 0,
            'last_upload_time': None,
            'last_error': None
        }
        self.stats_lock = threading.Lock()

        # 工作线程
        self.workers: List[threading.Thread] = []
        self.running = False

        # HTTP会话(带连接池)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """创建HTTP会话(带重试策略)"""
        session = requests.Session()

        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 连接级重试
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.num_workers,
            pool_maxsize=self.num_workers * 2
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def start(self):
        """启动上传工作线程"""
        if self.running:
            if self.debug:
                print("Upload manager already running")
            return

        self.running = True

        # 启动工作线程
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._upload_worker,
                name=f"UploadWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        if self.debug:
            print(f"Upload manager started with {self.num_workers} workers")

    def stop(self, wait_completion: bool = True):
        """
        停止上传管理器

        Args:
            wait_completion: 是否等待队列处理完成
        """
        if not self.running:
            return

        self.running = False

        if wait_completion:
            # 等待队列清空
            self.upload_queue.join()

        # 等待工作线程结束
        for worker in self.workers:
            worker.join(timeout=5.0)

        self.workers.clear()

        if self.debug:
            print("Upload manager stopped")

    def enqueue(self, data: Dict[str, Any], priority: bool = False) -> bool:
        """
        将数据加入上传队列

        Args:
            data: 要上传的数据字典
            priority: 是否高优先级(暂不实现)

        Returns:
            True: 成功加入队列, False: 队列已满
        """
        try:
            self.upload_queue.put(data, block=False)

            with self.stats_lock:
                self.stats['queue_length'] = self.upload_queue.qsize()

            return True

        except queue.Full:
            if self.debug:
                print("Upload queue is full, cannot enqueue")

            with self.stats_lock:
                self.stats['last_error'] = "Queue full"

            return False

    def upload_sync(self, data: Dict[str, Any]) -> UploadResult:
        """
        同步上传(立即执行,带重试)

        Args:
            data: 要上传的数据字典

        Returns:
            UploadResult对象
        """
        for attempt in range(self.max_retries):
            try:
                # 发送POST请求
                response = self.session.post(
                    self.backend_url,
                    json=data,
                    timeout=self.timeout,
                    headers={'Content-Type': 'application/json'}
                )

                # 检查响应状态
                if response.status_code == 200:
                    # 成功
                    try:
                        response_data = response.json()
                    except:
                        response_data = {'raw': response.text}

                    result = UploadResult(
                        success=True,
                        status_code=response.status_code,
                        response_data=response_data,
                        upload_time=datetime.now(),
                        retry_count=attempt
                    )

                    # 更新统计
                    with self.stats_lock:
                        self.stats['total_uploaded'] += 1
                        self.stats['last_upload_time'] = result.upload_time

                    return result

                elif response.status_code in [400, 401, 403, 404]:
                    # 客户端错误,不重试
                    return UploadResult(
                        success=False,
                        status_code=response.status_code,
                        error_message=f"Client error: {response.status_code} - {response.text}",
                        upload_time=datetime.now(),
                        retry_count=attempt
                    )

                else:
                    # 服务器错误,重试
                    error_msg = f"Server error: {response.status_code}"

                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)  # 指数退避
                        if self.debug:
                            print(f"Upload failed (attempt {attempt+1}/{self.max_retries}), "
                                  f"retrying in {delay}s: {error_msg}")
                        time.sleep(delay)
                    else:
                        # 最后一次尝试失败
                        result = UploadResult(
                            success=False,
                            status_code=response.status_code,
                            error_message=error_msg,
                            upload_time=datetime.now(),
                            retry_count=attempt + 1
                        )

                        with self.stats_lock:
                            self.stats['total_failed'] += 1
                            self.stats['last_error'] = error_msg

                        return result

            except requests.exceptions.Timeout:
                error_msg = "Request timeout"

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    if self.debug:
                        print(f"Upload timeout (attempt {attempt+1}/{self.max_retries}), "
                              f"retrying in {delay}s")
                    time.sleep(delay)
                else:
                    result = UploadResult(
                        success=False,
                        error_message=error_msg,
                        upload_time=datetime.now(),
                        retry_count=attempt + 1
                    )

                    with self.stats_lock:
                        self.stats['total_failed'] += 1
                        self.stats['last_error'] = error_msg

                    return result

            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error: {e}"

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    if self.debug:
                        print(f"Connection failed (attempt {attempt+1}/{self.max_retries}), "
                              f"retrying in {delay}s")
                    time.sleep(delay)
                else:
                    result = UploadResult(
                        success=False,
                        error_message=error_msg,
                        upload_time=datetime.now(),
                        retry_count=attempt + 1
                    )

                    with self.stats_lock:
                        self.stats['total_failed'] += 1
                        self.stats['last_error'] = str(e)

                    return result

            except Exception as e:
                error_msg = f"Unexpected error: {e}"

                result = UploadResult(
                    success=False,
                    error_message=error_msg,
                    upload_time=datetime.now(),
                    retry_count=attempt + 1
                )

                with self.stats_lock:
                    self.stats['total_failed'] += 1
                    self.stats['last_error'] = str(e)

                return result

        # 不应该到达这里
        return UploadResult(
            success=False,
            error_message="Max retries exceeded",
            retry_count=self.max_retries
        )

    def _upload_worker(self):
        """上传工作线程"""
        if self.debug:
            print(f"{threading.current_thread().name} started")

        while self.running:
            try:
                # 从队列获取数据(超时1秒,避免阻塞stop)
                data = self.upload_queue.get(timeout=1.0)

                # 执行上传
                result = self.upload_sync(data)

                if self.debug:
                    if result.success:
                        print(f"{threading.current_thread().name}: Upload successful "
                              f"(status: {result.status_code}, retries: {result.retry_count})")
                    else:
                        print(f"{threading.current_thread().name}: Upload failed "
                              f"(retries: {result.retry_count}, error: {result.error_message})")

                # 标记任务完成
                self.upload_queue.task_done()

                # 更新队列长度统计
                with self.stats_lock:
                    self.stats['queue_length'] = self.upload_queue.qsize()

            except queue.Empty:
                # 队列为空,继续循环
                continue

            except Exception as e:
                if self.debug:
                    print(f"{threading.current_thread().name} error: {e}")

        if self.debug:
            print(f"{threading.current_thread().name} stopped")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        with self.stats_lock:
            return self.stats.copy()

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康检查结果
        """
        health = {
            'backend_reachable': False,
            'queue_status': 'unknown',
            'workers_running': 0,
            'stats': self.get_stats(),
            'errors': []
        }

        # 检查工作线程
        health['workers_running'] = sum(1 for w in self.workers if w.is_alive())

        if health['workers_running'] < self.num_workers:
            health['errors'].append(
                f"Only {health['workers_running']}/{self.num_workers} workers running"
            )

        # 检查队列
        queue_size = self.upload_queue.qsize()
        if queue_size > self.max_queue_size * 0.8:
            health['queue_status'] = 'critical'
            health['errors'].append(f"Queue nearly full: {queue_size}/{self.max_queue_size}")
        elif queue_size > self.max_queue_size * 0.5:
            health['queue_status'] = 'warning'
        else:
            health['queue_status'] = 'ok'

        # 测试后台连接
        try:
            test_data = {'test': True, 'timestamp': datetime.now().isoformat()}
            response = self.session.post(
                self.backend_url,
                json=test_data,
                timeout=5.0
            )
            health['backend_reachable'] = response.status_code in [200, 400, 404]  # 任何响应都算可达
        except:
            health['errors'].append("Backend unreachable")

        return health

    def close(self):
        """关闭上传管理器"""
        self.stop(wait_completion=True)
        self.session.close()

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()

    def __repr__(self) -> str:
        return (
            f"UploadManager(backend_url='{self.backend_url}', "
            f"workers={self.num_workers}, "
            f"max_queue_size={self.max_queue_size})"
        )


if __name__ == "__main__":
    """测试代码"""
    import sys

    # 命令行参数: python upload_manager.py [backend_url]
    backend_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/upload"

    print(f"Testing Upload Manager")
    print(f"Backend URL: {backend_url}")
    print("-" * 70)

    # 测试数据
    test_data = {
        'device_id': 'TEST_001',
        'timestamp': datetime.now().isoformat(),
        'location': {
            'latitude': 36.67438,
            'longitude': 117.12583
        },
        'image': {
            'data': 'base64_test_string_placeholder',
            'format': 'jpeg'
        }
    }

    try:
        with UploadManager(backend_url=backend_url, debug=True) as uploader:
            print("\n1. Health Check:")
            health = uploader.health_check()
            print(f"   Backend reachable: {health['backend_reachable']}")
            print(f"   Queue status: {health['queue_status']}")
            print(f"   Workers running: {health['workers_running']}/{uploader.num_workers}")

            if health['errors']:
                print(f"   Errors: {health['errors']}")

            print("\n2. Synchronous Upload Test:")
            result = uploader.upload_sync(test_data)
            print(f"   Success: {result.success}")
            print(f"   Status code: {result.status_code}")
            print(f"   Retry count: {result.retry_count}")
            if result.error_message:
                print(f"   Error: {result.error_message}")

            print("\n3. Asynchronous Upload Test (5 items):")
            for i in range(5):
                test_item = test_data.copy()
                test_item['sequence'] = i + 1
                uploader.enqueue(test_item)
                print(f"   Enqueued item {i+1}")

            # 等待队列处理
            print("   Waiting for queue to process...")
            time.sleep(3)

            print("\n4. Statistics:")
            stats = uploader.get_stats()
            for key, value in stats.items():
                print(f"   {key}: {value}")

            print("\n✓ Upload manager test completed!")

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
