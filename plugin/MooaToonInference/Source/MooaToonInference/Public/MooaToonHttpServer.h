// MooaToon HTTP Server
// 在 127.0.0.1:4848 启动本地 HTTP 服务,供 AutoToonStudio 发送风格参数。

#pragma once

#include "CoreMinimal.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "HttpRouteHandle.h"
#include "IHttpRouter.h"

class MOOATOONINFERENCE_API FMooaToonHttpServer
{
public:
	/** 启动 HTTP 服务（绑定端口） */
	bool Start(int32 Port = 4848);

	/** 停止 HTTP 服务 */
	void Stop();

	/** 是否正在运行 */
	bool IsRunning() const { return bRunning; }

private:
	/** 路由回调 */
	bool HandleHealthCheck(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
	bool HandleStyleApply(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);

	/** 辅助：创建 JSON 响应 */
	TUniquePtr<FHttpServerResponse> MakeJsonResponse(int32 StatusCode, const FString& JsonBody);

	TSharedPtr<IHttpRouter> Router;
	FHttpRouteHandle HealthRouteHandle;
	FHttpRouteHandle StyleRouteHandle;
	bool bRunning = false;
};
