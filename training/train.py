"""
train.py — MooaToon 材质参数回归训练脚本
输入: 224x224 图片
输出: 6个材质参数 [shadow_r, shadow_g, shadow_b, specular, rim_light_width, width_scale]
训练完成后自动导出 mooatoon_model.onnx
"""
import os
import torch
import torch.nn as nn
import pandas as pd
from PIL import Image
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as T
import torchvision.models as models

# ─── 配置 ──────────────────────────────────────────────────────────────────────
IMAGES_DIR  = "../data/images"
LABELS_CSV  = "labels.csv"
EPOCHS      = 20
BATCH_SIZE  = 4
LR          = 1e-4
IMG_SIZE    = 224
# 6个输出参数（顺序必须与 UE C++ 推理解析顺序一致）
LABEL_COLS  = ["ShadowR", "ShadowG", "ShadowB", "Specular", "RimLightWidth", "WidthScale"]
ONNX_PATH   = "mooatoon_model.onnx"
DEVICE      = "cuda" if torch.cuda.is_available() else "cpu"

# ─── Dataset ───────────────────────────────────────────────────────────────────
class MooaToonDataset(Dataset):
    def __init__(self, csv_path, images_dir, transform=None):
        self.df = pd.read_csv(csv_path)
        self.images_dir = images_dir
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img_path = os.path.join(self.images_dir, os.path.basename(row["ImagePath"].strip('"')))
        img = Image.open(img_path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        labels = torch.tensor(row[LABEL_COLS].values.astype("float32"))
        return img, labels

# ─── 数据增强 ──────────────────────────────────────────────────────────────────
transform = T.Compose([
    T.Resize((IMG_SIZE, IMG_SIZE)),
    T.RandomHorizontalFlip(),
    T.ColorJitter(brightness=0.1, contrast=0.1),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# ─── 模型 ──────────────────────────────────────────────────────────────────────
def build_model(num_outputs=6):
    model = models.resnet18(weights=None)
    model.fc = nn.Sequential(
        nn.Linear(model.fc.in_features, 128),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(128, num_outputs),
        nn.Sigmoid(),  # 所有输出压到 [0,1]，width_scale 在 UE 端反归一化
    )
    return model

# ─── 训练 ──────────────────────────────────────────────────────────────────────
def train():
    print(f"Device: {DEVICE}")
    print(f"输出参数: {LABEL_COLS}")

    dataset = MooaToonDataset(LABELS_CSV, IMAGES_DIR, transform=transform)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, drop_last=False)
    print(f"数据集: {len(dataset)} 张图片, {len(loader)} 个 batch")

    model = build_model(num_outputs=len(LABEL_COLS)).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.MSELoss()

    print(f"\n开始训练 ({EPOCHS} epochs)...\n")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss = 0.0
        for imgs, labels in loader:
            imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad()
            preds = model(imgs)
            loss = criterion(preds, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(loader)
        print(f"Epoch [{epoch:02d}/{EPOCHS}]  Loss: {avg_loss:.6f}")

    # 保存权重
    torch.save(model.state_dict(), "mooatoon_model.pth")
    print("\n模型已保存: mooatoon_model.pth")

    # 导出 ONNX
    model.eval()
    dummy_input = torch.randn(1, 3, IMG_SIZE, IMG_SIZE).to(DEVICE)
    with torch.no_grad():
        torch.onnx.export(
            model,
            dummy_input,
            ONNX_PATH,
            input_names=["image"],
            output_names=["params"],
            opset_version=12,
            dynamo=False,
        )
    print(f"ONNX exported: {ONNX_PATH}")
    print(f"\n输出顺序: {LABEL_COLS}")
    print(">>> 训练完成 <<<")

if __name__ == "__main__":
    train()
