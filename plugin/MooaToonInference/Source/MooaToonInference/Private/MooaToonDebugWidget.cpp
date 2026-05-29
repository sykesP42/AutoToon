// MooaToon Inference Plugin

#include "MooaToonDebugWidget.h"
#include "MooaToonInferenceLibrary.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/FileManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogMooaToonUI, Log, All);

// =============================================================================
// 生命周期
// =============================================================================

void UMooaToonDebugWidget::NativeConstruct()
{
    Super::NativeConstruct();

    // ── 绑定滑条 ──────────────────────────────────────────────────────────────
    if (Slider_R)             Slider_R->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_R_Changed);
    if (Slider_G)             Slider_G->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_G_Changed);
    if (Slider_B)             Slider_B->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_B_Changed);
    if (Slider_Specular)      Slider_Specular->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_Specular_Changed);
    if (Slider_RimLightWidth) Slider_RimLightWidth->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_RimLightWidth_Changed);
    if (Slider_WidthScale)    Slider_WidthScale->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_WidthScale_Changed);
    if (Slider_StyleIntensity) Slider_StyleIntensity->OnValueChanged.AddDynamic(this, &UMooaToonDebugWidget::OnSlider_StyleIntensity_Changed);

    // ── 绑定按钮 ──────────────────────────────────────────────────────────────
    if (Btn_Apply)        Btn_Apply->OnClicked.AddDynamic(this, &UMooaToonDebugWidget::OnBtn_Apply_Clicked);
    if (Btn_Reset)        Btn_Reset->OnClicked.AddDynamic(this, &UMooaToonDebugWidget::OnBtn_Reset_Clicked);
    if (Btn_RunInference) Btn_RunInference->OnClicked.AddDynamic(this, &UMooaToonDebugWidget::OnBtn_RunInference_Clicked);
    if (Btn_ExportCSV)    Btn_ExportCSV->OnClicked.AddDynamic(this, &UMooaToonDebugWidget::OnBtn_ExportCSV_Clicked);
    if (Btn_AnalyzeStyle) Btn_AnalyzeStyle->OnClicked.AddDynamic(this, &UMooaToonDebugWidget::OnBtn_AnalyzeStyle_Clicked);

    // ── 绑定路径输入框 ────────────────────────────────────────────────────────
    if (TextBox_ImagePath)
    {
        TextBox_ImagePath->OnTextChanged.AddDynamic(this, &UMooaToonDebugWidget::OnTextBox_ImagePath_Changed);
        if (!ImagePath.IsEmpty())
            TextBox_ImagePath->SetText(FText::FromString(ImagePath));
    }

    // ── 初始化滑条范围与默认值 ────────────────────────────────────────────────
    auto InitSlider = [](USlider* S, float Min, float Max, float Val, float Step = 0.01f)
    {
        if (!S) return;
        S->SetMinValue(Min);
        S->SetMaxValue(Max);
        S->SetStepSize(Step);
        S->SetValue(Val);
    };

    InitSlider(Slider_R,             0.f,  1.f, ShadowR);
    InitSlider(Slider_G,             0.f,  1.f, ShadowG);
    InitSlider(Slider_B,             0.f,  1.f, ShadowB);
    InitSlider(Slider_Specular,      0.f,  1.f, Specular);
    InitSlider(Slider_RimLightWidth, 0.f,  1.f, RimLightWidth);
    InitSlider(Slider_WidthScale,    0.5f, 3.f, WidthScale, 0.05f);
    InitSlider(Slider_StyleIntensity, 0.f, 1.f, StyleIntensity);

    Internal_RefreshUI();
    Internal_SetStatus(TEXT("就绪。拖动滑条实时预览效果。"));
}

void UMooaToonDebugWidget::NativeDestruct()
{
    if (Slider_R)             Slider_R->OnValueChanged.RemoveAll(this);
    if (Slider_G)             Slider_G->OnValueChanged.RemoveAll(this);
    if (Slider_B)             Slider_B->OnValueChanged.RemoveAll(this);
    if (Slider_Specular)      Slider_Specular->OnValueChanged.RemoveAll(this);
    if (Slider_RimLightWidth) Slider_RimLightWidth->OnValueChanged.RemoveAll(this);
    if (Slider_WidthScale)    Slider_WidthScale->OnValueChanged.RemoveAll(this);
    if (Slider_StyleIntensity) Slider_StyleIntensity->OnValueChanged.RemoveAll(this);

    if (Btn_Apply)        Btn_Apply->OnClicked.RemoveAll(this);
    if (Btn_Reset)        Btn_Reset->OnClicked.RemoveAll(this);
    if (Btn_RunInference) Btn_RunInference->OnClicked.RemoveAll(this);
    if (Btn_ExportCSV)    Btn_ExportCSV->OnClicked.RemoveAll(this);
    if (Btn_AnalyzeStyle) Btn_AnalyzeStyle->OnClicked.RemoveAll(this);

    if (TextBox_ImagePath) TextBox_ImagePath->OnTextChanged.RemoveAll(this);

    Super::NativeDestruct();
}

// =============================================================================
// 滑条回调
// =============================================================================

void UMooaToonDebugWidget::OnSlider_R_Changed(float Value)
{
    ShadowR = Value;
    Internal_RefreshUI();
    Internal_ApplyToMaterial();
}

void UMooaToonDebugWidget::OnSlider_G_Changed(float Value)
{
    ShadowG = Value;
    Internal_RefreshUI();
    Internal_ApplyToMaterial();
}

void UMooaToonDebugWidget::OnSlider_B_Changed(float Value)
{
    ShadowB = Value;
    Internal_RefreshUI();
    Internal_ApplyToMaterial();
}

void UMooaToonDebugWidget::OnSlider_Specular_Changed(float Value)
{
    Specular = Value;
    Internal_RefreshUI();
    Internal_ApplyToMaterial();
}

void UMooaToonDebugWidget::OnSlider_RimLightWidth_Changed(float Value)
{
    RimLightWidth = Value;
    Internal_RefreshUI();
    Internal_ApplyToMaterial();
}

void UMooaToonDebugWidget::OnSlider_WidthScale_Changed(float Value)
{
    WidthScale = Value;
    Internal_RefreshUI();
    Internal_ApplyToMaterial();
}

void UMooaToonDebugWidget::OnSlider_StyleIntensity_Changed(float Value)
{
    StyleIntensity = Value;
    Internal_RefreshUI();
    Internal_ApplyStyle();
}

// =============================================================================
// 按钮回调
// =============================================================================

void UMooaToonDebugWidget::OnBtn_Apply_Clicked()
{
    ApplyCurrentParams();
}

void UMooaToonDebugWidget::OnBtn_Reset_Clicked()
{
    SetAndApply(0.3f, 0.3f, 0.3f, 0.5f, 0.5f, 1.0f);
    Internal_SetStatus(TEXT("参数已重置为默认值。"));
}

void UMooaToonDebugWidget::OnBtn_RunInference_Clicked()
{
    RunInference();
}

void UMooaToonDebugWidget::OnBtn_ExportCSV_Clicked()
{
    ExportParamsToCSV();
}

void UMooaToonDebugWidget::OnBtn_AnalyzeStyle_Clicked()
{
    // 同步 TextBox 里的最新路径（与 RunInference 行为保持一致）
    if (TextBox_ImagePath && !TextBox_ImagePath->GetText().IsEmpty())
        ImagePath = TextBox_ImagePath->GetText().ToString();

    ImagePath.TrimStartAndEndInline();
    if (ImagePath.StartsWith(TEXT("\"")) && ImagePath.EndsWith(TEXT("\"")))
        ImagePath = ImagePath.Mid(1, ImagePath.Len() - 2);

    if (ImagePath.IsEmpty())
    {
        Internal_SetStatus(TEXT("错误：ImagePath 为空，无法分析风格。"), true);
        return;
    }

    if (!UMooaToonInferenceLibrary::AnalyzeImageStyle(ImagePath, CachedStyle))
    {
        Internal_SetStatus(TEXT("错误：风格分析失败，请检查图片路径与格式。"), true);
        return;
    }

    Internal_ApplyStyle();

    const FString Msg = FString::Printf(
        TEXT("风格分析完成\nDom=(%.2f,%.2f,%.2f) Sat=%.2f Con=%.2f\nIntensity=%.2f"),
        CachedStyle.DominantColor.R, CachedStyle.DominantColor.G, CachedStyle.DominantColor.B,
        CachedStyle.TargetSaturation, CachedStyle.TargetContrast, StyleIntensity);
    Internal_SetStatus(Msg);
    UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] %s"), *Msg);
}

void UMooaToonDebugWidget::OnTextBox_ImagePath_Changed(const FText& Text)
{
    ImagePath = Text.ToString();
}

// =============================================================================
// 公开接口实现
// =============================================================================

void UMooaToonDebugWidget::SetAndApply(float R, float G, float B, float Spec, float RimWidth, float OutlineWidth)
{
    ShadowR       = FMath::Clamp(R,            0.f, 1.f);
    ShadowG       = FMath::Clamp(G,            0.f, 1.f);
    ShadowB       = FMath::Clamp(B,            0.f, 1.f);
    Specular      = FMath::Clamp(Spec,         0.f, 1.f);
    RimLightWidth = FMath::Clamp(RimWidth,     0.f, 1.f);
    WidthScale    = FMath::Clamp(OutlineWidth, 0.5f, 3.f);

    // 同步滑条位置
    if (Slider_R)             Slider_R->SetValue(ShadowR);
    if (Slider_G)             Slider_G->SetValue(ShadowG);
    if (Slider_B)             Slider_B->SetValue(ShadowB);
    if (Slider_Specular)      Slider_Specular->SetValue(Specular);
    if (Slider_RimLightWidth) Slider_RimLightWidth->SetValue(RimLightWidth);
    if (Slider_WidthScale)    Slider_WidthScale->SetValue(WidthScale);

    Internal_RefreshUI();
    Internal_ApplyToMaterial();

    OnParamsUpdated(ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale);
}

void UMooaToonDebugWidget::ApplyCurrentParams()
{
    Internal_ApplyToMaterial();

    const FString Msg = FString::Printf(
        TEXT("手动应用: Shadow=(%.3f,%.3f,%.3f) Spec=%.3f Rim=%.3f Width=%.3f"),
        ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale);

    Internal_SetStatus(Msg);
    UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] %s"), *Msg);
}

bool UMooaToonDebugWidget::RunInference()
{
    if (!ModelData)
    {
        const FString Msg = TEXT("错误：ModelData 未设置，请在 Details 面板指定 ONNX 资产。");
        Internal_SetStatus(Msg, true);
        OnInferenceResult(Msg, false);
        return false;
    }

    if (TextBox_ImagePath && !TextBox_ImagePath->GetText().IsEmpty())
        ImagePath = TextBox_ImagePath->GetText().ToString();

    // 去掉用户粘贴路径时可能携带的首尾引号
    ImagePath.TrimStartAndEndInline();
    if (ImagePath.StartsWith(TEXT("\"")) && ImagePath.EndsWith(TEXT("\"")))
        ImagePath = ImagePath.Mid(1, ImagePath.Len() - 2);

    // 每次推理都重新扫描 example/ 目录，确保图片切换后能读到最新文件
    {
        const FString ExampleDir = FPaths::ConvertRelativePathToFull(
            FPaths::Combine(FPaths::ProjectDir(), TEXT("example")));

        UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] 扫描 example 目录: %s"), *ExampleDir);

        // 用 IterateDirectory 代替 FindFiles 通配符（Windows 兼容性更好）
        TArray<FString> Found;
        IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
        PF.IterateDirectory(*ExampleDir, [&Found](const TCHAR* Path, bool bIsDir) -> bool
        {
            if (!bIsDir)
            {
                const FString Ext = FPaths::GetExtension(FString(Path)).ToLower();
                if (Ext == TEXT("png") || Ext == TEXT("jpg") || Ext == TEXT("jpeg"))
                    Found.Add(FString(Path));
            }
            return true;
        });

        UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] example/ 找到 %d 个图片"), Found.Num());

        if (Found.Num() > 0)
        {
            Found.Sort();
            const FString AutoPath = Found[0];  // IterateDirectory 已返回全路径
            if (AutoPath != ImagePath)
            {
                UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] example/ 图片: %s"), *AutoPath);
            }
            ImagePath = AutoPath;
            if (TextBox_ImagePath)
                TextBox_ImagePath->SetText(FText::FromString(ImagePath));
        }
        else
        {
            UE_LOG(LogMooaToonUI, Warning,
                TEXT("[MooaToonUI] example/ 目录为空或不存在: %s"), *ExampleDir);
        }
    }

    if (ImagePath.IsEmpty())
    {
        const FString Msg = TEXT("错误：ImagePath 为空，请填写参考图绝对路径。");
        Internal_SetStatus(Msg, true);
        OnInferenceResult(Msg, false);
        return false;
    }

    Internal_SetStatus(TEXT("正在加载图片…"));

    // 先确认文件存在，给出明确的路径错误提示
    if (!IFileManager::Get().FileExists(*ImagePath))
    {
        const FString Msg = FString::Printf(
            TEXT("错误：文件不存在，请检查路径\n%s"), *ImagePath);
        Internal_SetStatus(Msg, true);
        OnInferenceResult(Msg, false);
        return false;
    }

    TArray<float> Pixels;
    if (!UMooaToonInferenceLibrary::LoadImageToPixels(ImagePath, Pixels))
    {
        const FString Msg = FString::Printf(
            TEXT("错误：图片解码失败（格式不支持或文件损坏）\n%s"), *ImagePath);
        Internal_SetStatus(Msg, true);
        OnInferenceResult(Msg, false);
        return false;
    }

    Internal_SetStatus(TEXT("图片加载完成，正在推理…"));

    FMooaToonParams Params;
    if (!UMooaToonInferenceLibrary::RunMooaToonInference(ModelData, Pixels, Params))
    {
        const FString Msg = TEXT("错误：ONNX 推理失败，请查看 Output Log。");
        Internal_SetStatus(Msg, true);
        OnInferenceResult(Msg, false);
        return false;
    }

    SetAndApply(Params.ShadowR, Params.ShadowG, Params.ShadowB,
                Params.Specular, Params.RimLightWidth, Params.WidthScale);

    const FString StatusText = FString::Printf(
        TEXT("推理成功\nShadow R=%.3f G=%.3f B=%.3f\nSpec=%.3f Rim=%.3f Width=%.3f"),
        ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale);

    Internal_SetStatus(StatusText);
    UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] %s"), *StatusText);
    OnInferenceResult(StatusText, true);

    return true;
}

bool UMooaToonDebugWidget::ExportParamsToCSV()
{
    FString Dir = ExportDir;
    if (Dir.IsEmpty())
    {
        Dir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("MooaToonParams"));
    }

    IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
    if (!PF.DirectoryExists(*Dir))
    {
        PF.CreateDirectoryTree(*Dir);
    }

    const FString FilePath = FPaths::Combine(Dir, TEXT("mooatoon_params.csv"));

    const bool bFileExists = PF.FileExists(*FilePath);
    FString Content;

    if (!bFileExists)
    {
        Content = TEXT("Timestamp,ImagePath,ShadowR,ShadowG,ShadowB,Specular,RimLightWidth,WidthScale\n");
    }

    const FDateTime Now = FDateTime::Now();
    const FString Timestamp = FString::Printf(TEXT("%04d%02d%02d_%02d%02d%02d"),
        Now.GetYear(), Now.GetMonth(), Now.GetDay(),
        Now.GetHour(), Now.GetMinute(), Now.GetSecond());

    const FString SafeImagePath = FString::Printf(TEXT("\"%s\""), *ImagePath);

    Content += FString::Printf(TEXT("%s,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n"),
        *Timestamp,
        *SafeImagePath,
        ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale);

    if (!FFileHelper::SaveStringToFile(
            Content, *FilePath,
            FFileHelper::EEncodingOptions::AutoDetect,
            &IFileManager::Get(),
            bFileExists ? FILEWRITE_Append : FILEWRITE_None))
    {
        const FString Msg = FString::Printf(TEXT("错误：CSV 写入失败\n%s"), *FilePath);
        Internal_SetStatus(Msg, true);
        UE_LOG(LogMooaToonUI, Error, TEXT("[MooaToonUI] %s"), *Msg);
        OnCSVExported(FilePath, false);
        return false;
    }

    const FString Msg = FString::Printf(
        TEXT("OK! CSV\n%s\nShadow=(%.3f,%.3f,%.3f) Spec=%.3f Rim=%.3f Width=%.3f"),
        *FilePath, ShadowR, ShadowG, ShadowB, Specular, RimLightWidth, WidthScale);

    Internal_SetStatus(Msg);
    UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] %s"), *Msg);
    OnCSVExported(FilePath, true);

    return true;
}

void UMooaToonDebugWidget::SetTargetActor(AActor* NewActor)
{
    TargetActor = NewActor;

    const FString Msg = NewActor
        ? FString::Printf(TEXT("目标角色已切换为：%s"), *NewActor->GetName())
        : TEXT("警告：TargetActor 已清空。");

    Internal_SetStatus(Msg, NewActor == nullptr);
    UE_LOG(LogMooaToonUI, Log, TEXT("[MooaToonUI] %s"), *Msg);

    if (NewActor)
        Internal_ApplyToMaterial();
}

// =============================================================================
// 私有辅助函数
// =============================================================================

void UMooaToonDebugWidget::Internal_ApplyToMaterial()
{
    if (!TargetActor)
    {
        UE_LOG(LogMooaToonUI, Verbose,
            TEXT("[MooaToonUI] TargetActor 未设置，跳过材质写入"));
        return;
    }

    FLinearColor ShadowColor(ShadowR, ShadowG, ShadowB, 1.f);

    UMooaToonInferenceLibrary::SetMooaToonParams(
        TargetActor,
        ShadowColor,
        Specular,
        RimLightWidth,
        WidthScale,
        /*ElementIndex=*/-1);
}

void UMooaToonDebugWidget::Internal_ApplyStyle()
{
    UMooaToonInferenceLibrary::ApplyStyleToWorld(this, CachedStyle, StyleIntensity);
}

void UMooaToonDebugWidget::Internal_RefreshUI()
{
    auto SetText = [](UTextBlock* TB, float Val)
    {
        if (TB) TB->SetText(FText::FromString(FString::Printf(TEXT("%.3f"), Val)));
    };

    SetText(Text_R,             ShadowR);
    SetText(Text_G,             ShadowG);
    SetText(Text_B,             ShadowB);
    SetText(Text_Specular,      Specular);
    SetText(Text_RimLightWidth, RimLightWidth);
    SetText(Text_WidthScale,    WidthScale);
    SetText(Text_StyleIntensity, StyleIntensity);

    if (Img_ColorPreview)
    {
        Img_ColorPreview->SetColorAndOpacity(
            FLinearColor(ShadowR, ShadowG, ShadowB, 1.f));
    }
}

void UMooaToonDebugWidget::Internal_SetStatus(const FString& Msg, bool bError)
{
    if (!Text_Status) return;

    Text_Status->SetText(FText::FromString(Msg));
    Text_Status->SetColorAndOpacity(
        bError
        ? FSlateColor(FLinearColor(1.f, 0.3f, 0.3f, 1.f))
        : FSlateColor(FLinearColor::White));
}
