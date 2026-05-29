"""
main.py — HybriToon Studio 入口
启动 Dear PyGui 界面，加载 ONNX 模型。
"""
import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="HybriToon Studio — AI 风格化实时预览工具")
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="ONNX 模型路径（默认自动查找 mooatoon_model.onnx）"
    )
    parser.add_argument(
        "--ue-host",
        type=str,
        default="127.0.0.1",
        help="UE5 HTTP 服务地址（默认 127.0.0.1）"
    )
    parser.add_argument(
        "--ue-port",
        type=int,
        default=8080,
        help="UE5 HTTP 服务端口（默认 8080）"
    )

    args = parser.parse_args()

    # 自动查找 ONNX 模型
    onnx_path = args.model
    if onnx_path is None:
        # 按优先级搜索
        search_paths = [
            os.path.join(os.path.dirname(__file__), "..", "training", "mooatoon_model.onnx"),
            "mooatoon_model.onnx",
        ]
        for p in search_paths:
            if os.path.exists(p):
                onnx_path = os.path.abspath(p)
                break

    # 启动 UI
    from ui import run, state
    from ue_client import UE5Client

    # 配置 UE5 客户端
    try:
        state.ue_client = UE5Client(host=args.ue_host, port=args.ue_port)
    except Exception:
        pass

    run(onnx_path=onnx_path)


if __name__ == "__main__":
    main()
