#pragma once

#include "Modules/ModuleManager.h"
#include "MooaToonHttpServer.h"

class FMooaToonInferenceModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	TUniquePtr<FMooaToonHttpServer> HttpServer;
};
