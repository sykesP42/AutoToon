#pragma once

#include "Modules/ModuleManager.h"
#include "MooaToonHttpServer.h"
#include "MooaToonWebSocketServer.h"

class FMooaToonInferenceModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

	/** 获取 WebSocket 服务器实例 */
	static FMooaToonWebSocketServer* GetWebSocketServer();

private:
	TUniquePtr<FMooaToonHttpServer> HttpServer;
	TUniquePtr<FMooaToonWebSocketServer> WebSocketServer;

	/** 模块实例指针（用于静态访问） */
	static FMooaToonInferenceModule* ModuleInstance;
};
