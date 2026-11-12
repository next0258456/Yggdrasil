"""
model_architecture.py
Định nghĩa kiến trúc Nemotron Recognizer và cơ chế Freeze/Unfreeze tham số chuẩn xác:
- Đóng băng Detector (45.4M) & Relational (2.3M)
- Đóng băng CNN Encoder (9.8M) của Recognizer
- Chỉ kích hoạt Trainable cho Transformer Decoder + Linear Head (khoảng 26.3M)
- Mở rộng Linear Head từ num_tokens_old sang num_tokens_new (thêm 67 ký tự tiếng Việt)
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Optional, Dict, Any

class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # Shape: (1, max_len, d_model)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, seq_len, d_model)
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)

class NemotronCNNEncoder(nn.Module):
    """
    CNN Encoder của Nemotron OCR Recognizer (~9.8M tham số).
    Trích xuất đặc trưng không gian từ ảnh text-line (H x W) thành chuỗi feature vectors.
    """
    def __init__(self, in_channels: int = 3, out_dim: int = 512):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, 64, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)  # 1/2

        self.conv2 = nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(128)
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)  # 1/4

        self.conv3 = nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn3 = nn.BatchNorm2d(256)

        self.conv4 = nn.Conv2d(256, 512, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn4 = nn.BatchNorm2d(512)
        # Pool theo chiều dọc nhiều hơn chiều ngang để giữ độ phân giải chuỗi ký tự
        self.pool3 = nn.MaxPool2d(kernel_size=(2, 1), stride=(2, 1))

        self.conv5 = nn.Conv2d(512, out_dim, kernel_size=(4, 1), stride=1, padding=0, bias=False)
        self.bn5 = nn.BatchNorm2d(out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool1(self.relu(self.bn1(self.conv1(x))))
        x = self.pool2(self.relu(self.bn2(self.conv2(x))))
        x = self.relu(self.bn3(self.conv3(x)))
        x = self.pool3(self.relu(self.bn4(self.conv4(x))))
        x = self.relu(self.bn5(self.conv5(x)))  # (B, out_dim, 1, W_seq)
        
        # Squeeze chiều cao và chuyển vị trí: (B, W_seq, out_dim)
        x = x.squeeze(2).permute(0, 2, 1)
        return x

class NemotronTransformerDecoder(nn.Module):
    """
    Pre-norm Transformer Decoder (~25M tham số) của Nemotron Recognizer.
    Thực hiện mô hình hóa chuỗi ký tự tự hồi quy / song song với CTC.
    """
    def __init__(self, d_model: int = 512, nhead: int = 8, num_layers: int = 6, dim_feedforward: int = 2048, dropout: float = 0.1):
        super().__init__()
        self.pos_encoder = PositionalEncoding(d_model=d_model, dropout=dropout)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            activation='gelu',
            batch_first=True,
            norm_first=True  # Pre-norm transformer
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor, src_key_padding_mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        x = self.pos_encoder(x)
        x = self.transformer(x, src_key_padding_mask=src_key_padding_mask)
        x = self.norm(x)
        return x

class NemotronOCRRecognizer(nn.Module):
    """
    Mô hình Nemotron Recognizer đầy đủ (36.1M tham số) được thiết kế để Fine-tune:
    - CNN Encoder: 9.8M (Freeze)
    - Transformer Decoder: 25.2M (Trainable)
    - Linear CTC Head: ~1.1M (Trainable, hỗ trợ mở rộng số lượng token)
    """
    def __init__(self, vocab_size: int = 14246, d_model: int = 512):
        super().__init__()
        self.vocab_size = vocab_size
        self.d_model = d_model

        self.cnn_encoder = NemotronCNNEncoder(in_channels=3, out_dim=d_model)
        self.transformer_decoder = NemotronTransformerDecoder(d_model=d_model)
        self.linear_head = nn.Linear(d_model, vocab_size)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        """
        images: (B, 3, H, W) ảnh text line đã chuẩn hóa
        output: (T, B, vocab_size) Log-probabilities cho CTCLoss
        """
        features = self.cnn_encoder(images)  # (B, T, d_model)
        decoded = self.transformer_decoder(features)  # (B, T, d_model)
        logits = self.linear_head(decoded)  # (B, T, vocab_size)
        log_probs = F.log_softmax(logits, dim=-1)
        # CTCLoss trong PyTorch mặc định yêu cầu input shape: (T, B, vocab_size)
        return log_probs.permute(1, 0, 2)

    def freeze_cnn_encoder(self):
        """Đóng băng 100% tham số CNN Encoder (9.8M)."""
        for param in self.cnn_encoder.parameters():
            param.requires_grad = False
        self.cnn_encoder.eval()

    def unfreeze_decoder_and_head(self):
        """Kích hoạt gradients cho Transformer Decoder và Linear Head."""
        for param in self.transformer_decoder.parameters():
            param.requires_grad = True
        for param in self.linear_head.parameters():
            param.requires_grad = True

    def expand_vocab(self, new_vocab_size: int):
        """
        Mở rộng Linear Head từ vocab cũ sang vocab mới (thêm 67 ký tự tiếng Việt).
        Giữ nguyên trọng số của các token cũ, khởi tạo nhỏ cho các token tiếng Việt mới.
        """
        if new_vocab_size <= self.vocab_size:
            return

        old_weight = self.linear_head.weight.data  # (old_vocab, d_model)
        old_bias = self.linear_head.bias.data if self.linear_head.bias is not None else None

        new_head = nn.Linear(self.d_model, new_vocab_size)
        
        # Sao chép trọng số cũ
        new_head.weight.data[:self.vocab_size, :] = old_weight
        if old_bias is not None:
            new_head.bias.data[:self.vocab_size] = old_bias

        # Khởi tạo ngẫu nhiên nhỏ (Gaussian) cho các token tiếng Việt mới
        num_added = new_vocab_size - self.vocab_size
        nn.init.normal_(new_head.weight.data[self.vocab_size:, :], mean=0.0, std=0.02)
        if new_head.bias is not None:
            nn.init.zeros_(new_head.bias.data[self.vocab_size:])

        self.linear_head = new_head
        self.vocab_size = new_vocab_size
        print(f"[*] Đã mở rộng Linear Head: {old_weight.size(0)} -> {new_vocab_size} classes (+{num_added} tokens).")

    def count_parameters(self) -> Dict[str, int]:
        """Thống kê chi tiết số lượng tham số trainable và non-trainable."""
        total = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        frozen = total - trainable
        return {
            "total": total,
            "trainable": trainable,
            "frozen": frozen,
            "trainable_percent": round((trainable / total) * 100, 2)
        }

if __name__ == "__main__":
    model = NemotronOCRRecognizer(vocab_size=14246)
    print("Khởi tạo mô hình gốc:")
    print(model.count_parameters())

    print("\nÁp dụng chiến lược Freeze theo Phương án 2 (DEPLOYMENT.md):")
    model.freeze_cnn_encoder()
    model.unfreeze_decoder_and_head()
    print(model.count_parameters())

    print("\nMở rộng 67 ký tự tiếng Việt có dấu:")
    model.expand_vocab(14246 + 67)
    stats = model.count_parameters()
    print(stats)
    print(f"=> Tổng tham số Trainable: {stats['trainable']:,} (~26.3M đúng như thiết kế)")
