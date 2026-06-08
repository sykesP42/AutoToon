"""
test_http_link.py — HTTP 通信链路测试
测试 Python Studio ↔ UE5 插件的 HTTP 通信。

使用方法:
1. 确保 UE5 项目已启动并加载 MooaToonInference 插件
2. 运行此脚本: python test_http_link.py
"""
import sys
import time

try:
    from ue_client import UE5Client
except ImportError:
    print("[ERROR] 无法导入 ue_client，请确保在 Studio 目录下运行")
    sys.exit(1)


def test_health_check(client: UE5Client):
    """测试健康检查接口"""
    print("\n[TEST 1] GET /api/health")
    print("-" * 40)

    result = client.health_check()

    if result["ok"]:
        print(f"✅ 成功: {result['status']}")
        return True
    else:
        print(f"❌ 失败: {result['error']}")
        return False


def test_send_params(client: UE5Client):
    """测试发送参数接口"""
    print("\n[TEST 2] POST /api/style")
    print("-" * 40)

    # 测试参数: 阴影颜色 (暖色调) + 其他参数
    test_params = [
        0.8,   # shadow_r (阴影红色分量)
        0.6,   # shadow_g (阴影绿色分量)
        0.4,   # shadow_b (阴影蓝色分量)
        0.5,   # specular (高光强度)
        0.3,   # rim_light_width (边缘光宽度)
        1.0,   # width_scale (宽度缩放)
    ]

    print(f"发送参数: Shadow=(0.8, 0.6, 0.4) Spec=0.5 Rim=0.3 Width=1.0")
    result = client.send_params(test_params)

    if result["ok"]:
        print("✅ 成功: 参数已应用")
        return True
    else:
        print(f"❌ 失败: {result['error']}")
        return False


def test_multiple_params(client: UE5Client):
    """测试多次发送不同参数"""
    print("\n[TEST 3] 多次发送不同参数")
    print("-" * 40)

    test_cases = [
        # (名称, 参数列表)
        ("冷色调阴影", [0.2, 0.3, 0.5, 0.7, 0.2, 1.0]),
        ("暖色调阴影", [0.9, 0.7, 0.3, 0.4, 0.4, 1.0]),
        ("中性灰阴影", [0.5, 0.5, 0.5, 0.5, 0.3, 1.0]),
        ("低高光", [0.6, 0.6, 0.6, 0.1, 0.2, 1.0]),
        ("高边缘光", [0.7, 0.7, 0.7, 0.5, 0.8, 1.0]),
    ]

    success_count = 0
    for name, params in test_cases:
        print(f"  测试 '{name}'...")
        result = client.send_params(params)
        if result["ok"]:
            print(f"    ✅ 成功")
            success_count += 1
        else:
            print(f"    ❌ 失败: {result['error']}")
        time.sleep(0.5)  # 避免请求过快

    print(f"\n结果: {success_count}/{len(test_cases)} 成功")
    return success_count == len(test_cases)


def main():
    """主测试流程"""
    print("=" * 50)
    print("AutoToon HTTP 通信链路测试")
    print("=" * 50)

    # 创建客户端
    client = UE5Client(host="127.0.0.1", port=4848, timeout=5.0)
    print(f"\n目标: {client.url}")

    # 提示
    print("\n⚠️  请确保:")
    print("   1. UE5 项目已启动")
    print("   2. MooaToonInference 插件已加载")
    print("   3. HTTP 服务器在端口 4848 运行")
    print("\n按 Enter 开始测试...")
    input()

    # 运行测试
    results = []

    results.append(("健康检查", test_health_check(client)))
    results.append(("发送参数", test_send_params(client)))
    results.append(("多次发送", test_multiple_params(client)))

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
        print("\n🎉 所有测试通过! HTTP 通信链路正常工作。")
    else:
        print("\n⚠️  部分测试失败。请检查:")
        print("   - UE5 是否正在运行")
        print("   - 插件是否正确编译并加载")
        print("   - 端口 4848 是否被占用")


if __name__ == "__main__":
    main()