"""
test_ws_link.py — WebSocket 通信链路测试
测试 Python Studio ↔ UE5 插件的 WebSocket 实时通信。

使用方法:
1. 确保 UE5 项目已启动并加载 MooaToonInference 插件
2. 运行此脚本: python test_ws_link.py
"""
import sys
import asyncio
import json
import time

try:
    import websockets
except ImportError:
    print("[ERROR] websockets 未安装，请运行: pip install websockets")
    sys.exit(1)


WEBSOCKET_URL = "ws://127.0.0.1:4849"


async def test_connection():
    """测试基本 WebSocket 连接"""
    print("\n[TEST 1] WebSocket 连接测试")
    print("-" * 40)

    try:
        async with websockets.connect(WEBSOCKET_URL, close_timeout=5) as ws:
            print(f"✅ 成功连接到 {WEBSOCKET_URL}")

            # 等待欢迎消息
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(message)

                if data.get("type") == "welcome":
                    print(f"✅ 收到欢迎消息")
                    print(f"   Client ID: {data.get('client_id', 'N/A')}")
                    return True
                else:
                    print(f"⚠️  收到意外消息类型: {data.get('type')}")
                    return True  # 连接成功也算通过

            except asyncio.TimeoutError:
                print("⚠️  未收到欢迎消息（超时 5 秒）")
                return True  # 连接成功但可能服务器未发送欢迎消息

    except ConnectionRefusedError:
        print(f"❌ 连接被拒绝 - UE5 WebSocket 服务器可能未启动")
        print(f"   请确认 UE5 正在运行且插件已加载")
        return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


async def test_send_params():
    """测试发送材质参数"""
    print("\n[TEST 2] 发送材质参数测试")
    print("-" * 40)

    try:
        async with websockets.connect(WEBSOCKET_URL, close_timeout=5) as ws:
            # 跳过欢迎消息
            try:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            # 发送参数
            params = {
                "type": "params_update",
                "params": {
                    "shadow_r": 0.8,
                    "shadow_g": 0.6,
                    "shadow_b": 0.4,
                    "specular": 0.5,
                    "rim": 0.3,
                    "outline": 1.5,
                    "sss": 0.2,
                    "aniso": 0.1,
                    "metallic": 0.0,
                    "roughness": 0.5
                },
                "source": "test_script",
                "timestamp": int(time.time() * 1000)
            }

            print("发送参数: Shadow=(0.8, 0.6, 0.4) Spec=0.5 Rim=0.3")
            await ws.send(json.dumps(params))
            print("✅ 参数已发送")

            # 等待可能的响应（可选）
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print(f"   收到响应: {response[:100]}...")
            except asyncio.TimeoutError:
                print("   (无响应消息，这是正常的)")

            return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_ping_pong():
    """测试心跳机制"""
    print("\n[TEST 3] Ping/Pong 心跳测试")
    print("-" * 40)

    try:
        async with websockets.connect(WEBSOCKET_URL, close_timeout=5) as ws:
            # 跳过欢迎消息
            try:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            # 发送 ping
            ping_msg = {
                "type": "ping",
                "timestamp": int(time.time() * 1000)
            }

            start_time = time.time()
            await ws.send(json.dumps(ping_msg))
            print("发送 ping...")

            # 等待 pong
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                latency = (time.time() - start_time) * 1000

                data = json.loads(response)
                if data.get("type") == "pong":
                    print(f"✅ 收到 pong")
                    print(f"   延迟: {latency:.1f}ms")
                    return True
                else:
                    print(f"⚠️  收到意外响应: {data.get('type')}")
                    return False

            except asyncio.TimeoutError:
                print("❌ 未收到 pong 响应（超时 5 秒）")
                return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_multiple_params():
    """测试多次发送不同参数"""
    print("\n[TEST 4] 多次发送参数测试")
    print("-" * 40)

    test_cases = [
        ("冷色调", {"shadow_r": 0.2, "shadow_g": 0.3, "shadow_b": 0.5}),
        ("暖色调", {"shadow_r": 0.9, "shadow_g": 0.7, "shadow_b": 0.3}),
        ("中性灰", {"shadow_r": 0.5, "shadow_g": 0.5, "shadow_b": 0.5}),
    ]

    try:
        async with websockets.connect(WEBSOCKET_URL, close_timeout=5) as ws:
            # 跳过欢迎消息
            try:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            success_count = 0
            for name, colors in test_cases:
                params = {
                    "type": "params_update",
                    "params": {
                        **colors,
                        "specular": 0.5,
                        "rim": 0.3,
                        "outline": 1.0
                    },
                    "source": "test_script",
                    "timestamp": int(time.time() * 1000)
                }

                await ws.send(json.dumps(params))
                print(f"  ✅ '{name}' 已发送")
                success_count += 1
                await asyncio.sleep(0.3)  # 避免发送过快

            print(f"\n结果: {success_count}/{len(test_cases)} 成功")
            return success_count == len(test_cases)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def test_reconnection():
    """测试断线重连"""
    print("\n[TEST 5] 断线重连测试")
    print("-" * 40)

    # 第一次连接
    try:
        print("第一次连接...")
        async with websockets.connect(WEBSOCKET_URL, close_timeout=5) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print("✅ 第一次连接成功")
            except asyncio.TimeoutError:
                pass
        print("断开连接...")
    except Exception as e:
        print(f"❌ 第一次连接失败: {e}")
        return False

    # 等待 1 秒
    await asyncio.sleep(1)

    # 第二次连接
    try:
        print("重新连接...")
        async with websockets.connect(WEBSOCKET_URL, close_timeout=5) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print("✅ 重连成功")
                return True
            except asyncio.TimeoutError:
                print("✅ 重连成功（无欢迎消息）")
                return True
    except Exception as e:
        print(f"❌ 重连失败: {e}")
        return False


async def main():
    """主测试流程"""
    print("=" * 50)
    print("AutoToon WebSocket 通信链路测试")
    print("=" * 50)

    print(f"\n目标: {WEBSOCKET_URL}")

    # 提示
    print("\n⚠️  请确保:")
    print("   1. UE5 项目已启动")
    print("   2. MooaToonInference 插件已加载")
    print("   3. WebSocket 服务器在端口 4849 运行")
    print("\n按 Enter 开始测试...")
    input()

    # 运行测试
    results = []

    results.append(("WebSocket 连接", await test_connection()))
    results.append(("发送参数", await test_send_params()))
    results.append(("Ping/Pong", await test_ping_pong()))
    results.append(("多次发送", await test_multiple_params()))
    results.append(("断线重连", await test_reconnection()))

    # 总结
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过! WebSocket 通信链路正常工作。")
    else:
        print("\n⚠️  部分测试失败。请检查:")
        print("   - UE5 是否正在运行")
        print("   - 插件是否正确编译并加载")
        print("   - 端口 4849 是否被占用")
        print("   - 查看 UE5 输出日志中的 [WS] 消息")


if __name__ == "__main__":
    asyncio.run(main())
