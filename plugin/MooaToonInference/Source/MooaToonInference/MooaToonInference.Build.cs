using UnrealBuildTool;

public class MooaToonInference : ModuleRules
{
	public MooaToonInference(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"NNE",
			"UMG",
			"Slate",
			"SlateCore",
			"HTTP",
			"Json",
			"JsonUtilities",
			"WebSockets"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"NNERuntimeORT",
			"ImageWrapper",
			"HTTPServer",
			"WebSocketServer",
			"WebSocketNetworking"
		});
	}
}
