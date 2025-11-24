#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地模拟后台服务器
用于监听上传通道并查看程序实际发送的HTTP请求内容。

用法示例:
    python scripts/mock_backend.py --port 9000 --save-dir logs/uploads --save-images
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


@dataclass
class ServerConfig:
    """服务器运行配置"""

    host: str
    port: int
    save_dir: Optional[Path]
    pretty: bool
    quiet: bool
    save_images: bool


def create_handler(config: ServerConfig):
    """根据配置构造HTTP处理器类"""

    class MockUploadHandler(BaseHTTPRequestHandler):
        server_version = "MockUploadServer/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - 覆盖父类方法
            if not config.quiet:
                super().log_message(format, *args)

        def do_POST(self) -> None:  # noqa: N802 - 遵循BaseHTTPRequestHandler接口
            """处理POST请求,输出上传内容"""
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            timestamp = datetime.now()

            try:
                payload = json.loads(raw_body)
                is_json = True
            except json.JSONDecodeError:
                payload = raw_body.decode("utf-8", errors="replace")
                is_json = False

            print("\n" + "=" * 70)
            print(f"[{timestamp.isoformat()}] {self.client_address[0]} -> {self.path}")
            print(f"Headers: Content-Length={content_length}, Content-Type={self.headers.get('Content-Type')}")

            if is_json:
                if config.pretty:
                    print("Payload:")
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    print(f"Payload: {payload}")
            else:
                print("Payload (raw):")
                print(payload)

            saved_files = self._persist_payload(payload, timestamp, is_json)

            response = {
                "status": "ok",
                "saved_files": saved_files,
                "received_at": timestamp.isoformat()
            }

            body = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _persist_payload(self, payload: Any, timestamp: datetime, is_json: bool):
            """根据配置将请求内容保存到磁盘"""
            if not config.save_dir:
                return None

            config.save_dir.mkdir(parents=True, exist_ok=True)
            prefix = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            saved_items: Dict[str, str] = {}

            payload_path = config.save_dir / f"{prefix}.json"
            with payload_path.open("w", encoding="utf-8") as fp:
                if is_json:
                    json.dump(payload, fp, ensure_ascii=False, indent=2)
                else:
                    fp.write(str(payload))
            saved_items["payload"] = str(payload_path)

            if config.save_images and is_json:
                image_info = _extract_image(payload)
                if image_info:
                    image_bytes, extension = image_info
                    image_path = config.save_dir / f"{prefix}.{extension}"
                    with image_path.open("wb") as img_fp:
                        img_fp.write(image_bytes)
                    saved_items["image"] = str(image_path)

            if saved_items:
                print(f"Saved files: {saved_items}")

            return saved_items

    return MockUploadHandler


def _extract_image(payload: Dict[str, Any]) -> Optional[tuple[bytes, str]]:
    """
    尝试从payload中提取Base64图片数据; 仅用于辅助保存。
    默认期望结构: {'image': {'data': '...', 'format': 'jpeg'}}
    """
    if not isinstance(payload, dict):
        return None

    image = payload.get("image")
    if not isinstance(image, dict):
        return None

    data = image.get("data")
    if not isinstance(data, str):
        return None

    fmt = str(image.get("format", "jpeg")).lower()
    extension = "jpg" if fmt in {"jpeg", "jpg"} else fmt

    try:
        return base64.b64decode(data), extension
    except (ValueError, base64.binascii.Error):
        print("Warning: failed to decode image data")
        return None


def parse_args() -> ServerConfig:
    parser = argparse.ArgumentParser(
        description="启动本地HTTP服务器以捕获Road Photo Capture程序上传的数据",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=9000, help="监听端口")
    parser.add_argument("--save-dir", type=Path, help="保存payload结果的目录(可选)")
    parser.add_argument("--quiet", action="store_true", help="减少日志输出")
    parser.add_argument(
        "--no-pretty",
        dest="pretty",
        action="store_false",
        help="禁用JSON缩进,直接输出原始对象"
    )
    parser.add_argument(
        "--save-images",
        action="store_true",
        help="若payload中包含Base64图片,额外解码并存储JPEG/PNG文件"
    )

    args = parser.parse_args()
    if args.save_images and not args.save_dir:
        parser.error("--save-images 需要同时指定 --save-dir")

    save_dir = Path(args.save_dir).resolve() if args.save_dir else None
    return ServerConfig(
        host=args.host,
        port=args.port,
        save_dir=save_dir,
        pretty=args.pretty,
        quiet=args.quiet,
        save_images=args.save_images
    )


def run_server(config: ServerConfig) -> None:
    handler = create_handler(config)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    print("=" * 70)
    print(f"Mock upload server listening on http://{config.host}:{config.port}")
    if config.save_dir:
        print(f"Payloads will be stored under: {config.save_dir}")
    print("Press Ctrl+C to stop")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down mock server...")
    finally:
        server.server_close()
        print("Server stopped.")


def main():
    config = parse_args()
    run_server(config)


if __name__ == "__main__":
    main()
