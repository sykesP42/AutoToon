// MooaToon WebSocket Server
// 在 127.0.0.1:4849 启动 WebSocket 服务，实现实时双向通信。
//
// 使用 UE5 原生 IWebSocketServer API 实现 WebSocket 服务器。

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Containers/Array.h"
#include "Interfaces/IWebSocketServer.h"
#include "Interfaces/IWebSocketNetworkingModule.h"

DECLARE_LOG_CATEGORY_EXTERN(LogMooaToonWS, Log, All);

/**
 * Per-client connection wrapper
 * 每个客户端连接的包装结构
 */
struct FMooaToonWSClient
{
	/** WebSocket connection instance */
	INetworkingWebSocket* WebSocket;

	/** Unique client identifier */
	FString ClientId;

	/** Connection timestamp */
	double ConnectTime;

	FMooaToonWSClient(INetworkingWebSocket* InSocket, const FString& InId)
		: WebSocket(InSocket)
		, ClientId(InId)
		, ConnectTime(FPlatformTime::Seconds())
	{}
};

/**
 * MooaToon WebSocket Server
 *
 * 提供与 Python Studio 的实时双向通信。
 *
 * 协议:
 * - 端口: 4849
 * - 消息格式: JSON
 *
 * 消息类型:
 * - params_update: 材质参数更新
 * - ping/pong: 心跳检测
 * - welcome: 连接欢迎消息
 */
class MOOATOONINFERENCE_API FMooaToonWebSocketServer
{
public:
	FMooaToonWebSocketServer();
	~FMooaToonWebSocketServer();

	// 禁用拷贝
	FMooaToonWebSocketServer(const FMooaToonWebSocketServer&) = delete;
	FMooaToonWebSocketServer& operator=(const FMooaToonWebSocketServer&) = delete;

	/** 启动 WebSocket 服务器 */
	bool Start(int32 Port = 4849);

	/** 停止服务器 */
	void Stop();

	/** 是否正在运行 */
	bool IsRunning() const { return bRunning; }

	/** 获取服务器端口 */
	int32 GetPort() const { return ServerPort; }

	/** 获取已连接客户端数量 */
	int32 GetClientCount() const;

	/** 发送参数到所有客户端 */
	void BroadcastParams(const TSharedPtr<FJsonObject>& Params);

	/** 发送消息到指定客户端 */
	bool SendToClient(const FString& ClientId, const FString& Message);

	/** 参数接收回调委托 */
	DECLARE_MULTICAST_DELEGATE_TwoParams(FOnParamsReceived, const TSharedPtr<FJsonObject>&, const FString& /*ClientId*/);
	FOnParamsReceived OnParamsReceived;

	/** 客户端连接回调委托 */
	DECLARE_MULTICAST_DELEGATE_OneParam(FOnClientConnected, const FString& /*ClientId*/);
	FOnClientConnected OnClientConnected;

	/** 客户端断开回调委托 */
	DECLARE_MULTICAST_DELEGATE_OneParam(FOnClientDisconnected, const FString& /*ClientId*/);
	FOnClientDisconnected OnClientDisconnected;

private:
	/** 处理新客户端连接 */
	void HandleClientConnected(INetworkingWebSocket* ClientSocket);

	/** 处理客户端断开连接 */
	void HandleClientDisconnected(INetworkingWebSocket* ClientSocket);

	/** 处理接收到的消息 */
	void HandleMessageReceived(INetworkingWebSocket* Socket, const TArray<uint8>& Data);

	/** 处理接收到的文本消息 */
	void HandleTextMessage(INetworkingWebSocket* Socket, const FString& Message);

	/** 处理二进制消息 */
	void HandleBinaryMessage(INetworkingWebSocket* Socket, const TArray<uint8>& Data);

	/** 解析并处理 JSON 消息 */
	void ProcessJsonMessage(const FString& JsonStr, const FString& ClientId);

	/** 应用材质参数到场景 */
	void ApplyMaterialParams(const TSharedPtr<FJsonObject>& Params);

	/** 构建 JSON 响应消息 */
	FString BuildParamsJson(const TSharedPtr<FJsonObject>& Params, const FString& Source);

	/** 构建心跳响应 */
	FString BuildPongJson(int64 Timestamp);

	/** 生成唯一客户端 ID */
	FString GenerateClientId() const;

	/** 查找客户端 */
	FMooaToonWSClient* FindClientBySocket(INetworkingWebSocket* Socket);
	FMooaToonWSClient* FindClientById(const FString& ClientId);

	/** 移除客户端 */
	void RemoveClient(INetworkingWebSocket* Socket);

	/** 发送 JSON 到客户端 */
	bool SendJsonToSocket(INetworkingWebSocket* Socket, const FString& JsonStr);

	/** 发送欢迎消息 */
	void SendWelcomeMessage(INetworkingWebSocket* Socket, const FString& ClientId);

	// ==========================================================================
	// 成员变量
	// ==========================================================================

	/** WebSocket 服务器实例 */
	TSharedPtr<IWebSocketServer> Server;

	/** 已连接的客户端列表 */
	TArray<FMooaToonWSClient> Clients;

	/** 客户端列表访问锁（线程安全） */
	FCriticalSection ClientsLock;

	/** 服务器运行状态 */
	bool bRunning = false;

	/** 服务器端口 */
	int32 ServerPort = 4849;

	/** 绑定地址 */
	FString BindAddress = TEXT("127.0.0.1");

	/** 连接回调句柄 */
	FDelegateHandle ClientConnectedHandle;
};