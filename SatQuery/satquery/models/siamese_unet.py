"""Siamese U-Net with Spatial-Temporal Attention for Bi-Temporal Change Detection.

Implements the deep learning baseline documented in the ORBITRA synopsis and Satquery-1.O.
Features:
- Dual-stream weight-shared Siamese feature encoder (ResNet backbone)
- Multi-scale Spatial-Temporal Attention Difference Modules across feature levels
- U-Net style decoder with transposed convolutions and skip connections
- Output change probability logits
"""

from typing import Optional

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torchvision.models as models
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


if TORCH_AVAILABLE:
    class SpatialTemporalAttentionModule(nn.Module):
        """Suppresses seasonal/lighting noise and highlights genuine structural developments."""
        def __init__(self, in_channels: int):
            super().__init__()
            self.channel_attn = nn.Sequential(
                nn.AdaptiveAvgPool2d(1),
                nn.Conv2d(in_channels * 2, in_channels // 2, kernel_size=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(in_channels // 2, in_channels, kernel_size=1),
                nn.Sigmoid(),
            )
            self.spatial_attn = nn.Sequential(
                nn.Conv2d(2, 1, kernel_size=7, padding=3),
                nn.Sigmoid(),
            )

        def forward(self, feat_a: torch.Tensor, feat_b: torch.Tensor) -> torch.Tensor:
            diff = torch.abs(feat_a - feat_b)
            concat_feat = torch.cat([feat_a, feat_b], dim=1)
            c_weight = self.channel_attn(concat_feat)
            diff_c = diff * c_weight

            avg_out = torch.mean(diff_c, dim=1, keepdim=True)
            max_out, _ = torch.max(diff_c, dim=1, keepdim=True)
            s_weight = self.spatial_attn(torch.cat([avg_out, max_out], dim=1))

            return diff_c * s_weight


    class DecoderBlock(nn.Module):
        def __init__(self, in_channels: int, skip_channels: int, out_channels: int):
            super().__init__()
            self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, kernel_size=2, stride=2)
            self.conv = nn.Sequential(
                nn.Conv2d((in_channels // 2) + skip_channels, out_channels, kernel_size=3, padding=1),
                nn.BatchNorm2d(out_channels),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
                nn.BatchNorm2d(out_channels),
                nn.ReLU(inplace=True),
            )

        def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
            x = self.up(x)
            if x.shape[2:] != skip.shape[2:]:
                x = F.interpolate(x, size=skip.shape[2:], mode="bilinear", align_corners=True)
            x = torch.cat([x, skip], dim=1)
            return self.conv(x)


    class SiameseUNetAttention(nn.Module):
        """Temporal Siamese Convolutional Network with Spatial-Temporal Attention."""
        def __init__(self, pretrained: bool = False):
            super().__init__()
            resnet = models.resnet34(weights=models.ResNet34_Weights.DEFAULT if pretrained else None)

            self.initial = nn.Sequential(resnet.conv1, resnet.bn1, resnet.relu)
            self.maxpool = resnet.maxpool
            self.layer1 = resnet.layer1
            self.layer2 = resnet.layer2
            self.layer3 = resnet.layer3
            self.layer4 = resnet.layer4

            self.attn1 = SpatialTemporalAttentionModule(64)
            self.attn2 = SpatialTemporalAttentionModule(128)
            self.attn3 = SpatialTemporalAttentionModule(256)
            self.attn4 = SpatialTemporalAttentionModule(512)

            self.dec4 = DecoderBlock(512, 256, 256)
            self.dec3 = DecoderBlock(256, 128, 128)
            self.dec2 = DecoderBlock(128, 64, 64)
            self.dec1 = nn.Sequential(
                nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2),
                nn.BatchNorm2d(32),
                nn.ReLU(inplace=True),
                nn.Conv2d(32, 1, kernel_size=3, padding=1),
            )

        def forward_single(self, x: torch.Tensor):
            x0 = self.initial(x)
            x1 = self.layer1(self.maxpool(x0))
            x2 = self.layer2(x1)
            x3 = self.layer3(x2)
            x4 = self.layer4(x3)
            return x0, x1, x2, x3, x4

        def forward(self, img_a: torch.Tensor, img_b: torch.Tensor) -> torch.Tensor:
            a0, a1, a2, a3, a4 = self.forward_single(img_a)
            b0, b1, b2, b3, b4 = self.forward_single(img_b)

            d4 = self.attn4(a4, b4)
            d3 = self.attn3(a3, b3)
            d2 = self.attn2(a2, b2)
            d1 = self.attn1(a1, b1)

            x = self.dec4(d4, d3)
            x = self.dec3(x, d2)
            x = self.dec2(x, d1)
            out = self.dec1(x)
            # Interpolate to match original input dimension
            if out.shape[2:] != img_a.shape[2:]:
                out = F.interpolate(out, size=img_a.shape[2:], mode="bilinear", align_corners=True)
            return out
else:
    class SiameseUNetAttention:
        """Placeholder when PyTorch is not installed."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "PyTorch is not installed in the current environment. "
                "SatQuery provides its baseline differential change detector via BaselineChangeDetector."
            )
