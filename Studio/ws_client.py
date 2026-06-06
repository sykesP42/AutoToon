"""
ws_client.py — UE5 WebSocket 客户端
实现与 UE5 插件的实时双向通信。
默认端口: 4849 (AutoToon WebSocket)
"""
import asyncio
import json
import time
import threading
from typing import Callable, Optional

try:
    import websockets
except ImportError:
    websockets = None


class UE5WebSocketClient:
    """UE5 WebSocket 客户端

    负责与 UE5 插件的 WebSocket 服务器建立连接，
    发送材质参数，接收参数更新。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4849):
        if websockets is None:
            raise ImportError("websockets 未安装，请运行: pip install websockets")

        self.host = host
        self.port = port
        self.url = f"ws://{host}:{port}"

        self.connected = False
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

        # 回调列表
        self._on_params_callbacks: list[Callable[[dict], None]] = []
        self._on_connected_callbacks: list[Callable[[], None]] = []
        self._on_disconnected_callbacks: list[Callable[[], None]] = []

        # 异步循环和线程
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # 最后一次 ping 时间（用于计算延迟）
        self._last_ping_time: float = 0
        self.latency_ms: float = 0

    @property
    def status_text(self) -> str:
        """获取状态文本"""
        if self.connected:
            return f"Connected ({self.latency_ms:.0f}ms)"
        return "Disconnected"

    def on_params_received(self, callback: Callable[[dict], None]):
        """注册参数接收回调"""
        self._on_params_callbacks.append(callback)

    def on_connected(self, callback: Callable[[], None]):
        """注册连接成功回调"""
        self._on_connected_callbacks.append(callback)

    def on_disconnected(self, callback: Callable[[], None]):
        """注册断开连接回调"""
        self._on_disconnected_callbacks.append(callback)

    def start(self):
        """启动 WebSocket 客户端（在后台线程中运行）"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止 WebSocket 客户端"""
        self._running = False
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        """异步事件循环入口"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._connect_loop())
        finally:
            self._loop.close()

    async def _connect_loop(self):
        """连接循环，包含断线重连"""
        while self._running:
            try:
                await self._connect_and_run()
            except Exception as e:
                print(f"[WS] 连接错误: {e}")

            if self._running:
                # 断线后等待 5 秒重连
                await asyncio.sleep(5)

    async def _connect_and_run(self):
        """建立连接并运行消息循环"""
        print(f"[WS] 尝试连接: {self.url}")

        try:
            async with websockets.connect(
                self.url,
                ping_interval=5,
                ping_timeout=3
            ) as ws:
                self.ws = ws
                self.connected = True
                print(f"[WS] 已连接: {self.url}")

                # 触发连接回调
                for cb in self._on_connected_callbacks:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[WS] 连接回调错误: {e}")

                # 运行消息循环
                await self._message_loop()

        except Exception as e:
            self.connected = False
            print(f"[WS] 连接失败: {e}")
            raise

    async def _disconnect(self):
        """断开连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.connected = False

        # 触发断开回调
        for cb in self._on_disconnected_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[WS] 断开回调错误: {e}")

    async def _message_loop(self):
        """消息接收循环"""
        try:
            async for message in self.ws:
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            print("[WS] 连接已关闭")
        except Exception as e:
            print(f"[WS] 消息循环错误: {e}")
        finally:
            self.connected = False

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "params_update":
                params = data.get("params", {})
                source = data.get("source", "unknown")

                # 触发参数回调
                for cb in self._on_params_callbacks:
                    try:
                        cb(params)
                    except Exception as e:
                        print(f"[WS] 参数回调错误: {e}")

            elif msg_type == "pong":
                # 计算延迟
                self.latency_ms = (time.time() - self._last_ping_time) * 1000

        except json.JSONDecodeError:
            print(f"[WS] JSON 解析失败: {message[:100]}")
        except Exception as e:
            print(f"[WS] 消息处理错误: {e}")

    def send_params(self, params: dict):
        """发送材质参数（线程安全）

        Args:
            params: 材质参数字典
        """
        if not self.connected or not self.ws or not self._loop:
            return

        message = {
            "type": "params_update",
            "params": params,
            "source": "studio",
            "timestamp": int(time.time() * 1000)
        }

        try:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps(message)),
                self._loop
            )
        except Exception as e:
            print(f"[WS] 发送失败: {e}")

    def send_ping(self):
        """发送心跳（用于测量延迟）"""
        if not self.connected or not self.ws or not self._loop:
            return

        self._last_ping_time = time.time()
        message = {"type": "ping", "timestamp": int(time.time() * 1000)}

        try:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps(message)),
                self._loop
            )
        except Exception as e:
            print(f"[WS] Ping 发送失败: {e}")