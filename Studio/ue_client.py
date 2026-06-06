"""
ue_client.py — UE5 HTTP 客户端
通过 HTTP 与 UE5 插件通信：健康检查 + 发送风格参数。
默认端口: 4848 (AutoToon)
"""
import json
import time

try:
    import requests
except ImportError:
    requests = None


class UE5Client:
    """UE5 HTTP 通信客户端"""

    def __init__(self, host: str = "127.0.0.1", port: int = 4848, timeout: float = 3.0):
        if requests is None:
            raise ImportError("requests 未安装，请运行: pip install requests")

        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"

    def health_check(self) -> dict:
        """
        GET /api/health
        Returns: {"ok": True, "status": "ok"} 或 {"ok": False, "error": "..."}
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/health",
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "status": data.get("status", "unknown")}
            else:
                return {"ok": False, "error": f"HTTP {resp.status_code}"}

        except requests.ConnectionError:
            return {"ok": False, "error": "连接失败 — UE5 未启动或插件未加载"}
        except requests.Timeout:
            return {"ok": False, "error": f"超时 ({self.timeout}s)"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def send_params(self, params: list[float]) -> dict:
        """
        POST /api/style
        发送 6 个风格参数到 UE5。

        Args:
            params: [shadow_r, shadow_g, shadow_b, specular, rim_light_width, width_scale]

        Returns: {"ok": True} 或 {"ok": False, "error": "..."}
        """
        if len(params) != 6:
            return {"ok": False, "error": f"参数数量应为 6，实际为 {len(params)}"}

        payload = {"params": [float(p) for p in params]}

        try:
            resp = requests.post(
                f"{self.base_url}/api/style",
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                return {"ok": True}
            else:
                return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}

        except requests.ConnectionError:
            return {"ok": False, "error": "连接失败 — UE5 未启动或插件未加载"}
        except requests.Timeout:
            return {"ok": False, "error": f"超时 ({self.timeout}s)"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @property
    def url(self) -> str:
        return self.base_url
