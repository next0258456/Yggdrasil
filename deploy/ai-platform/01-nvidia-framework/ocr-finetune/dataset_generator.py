"""
dataset_generator.py
Bộ sinh dữ liệu text-line Tiếng Việt tổng hợp và Dataset Loader cho huấn luyện CTCLoss:
- Sinh ảnh chữ tiếng Việt có dấu ngẫu nhiên (từ vựng tài chính, kế toán, hóa đơn, văn bản hành chính)
- Data augmentation: làm mờ nhẹ, thêm nhiễu giấy cũ, vạch kẻ ô bảng biểu
- Tokenizer mã hóa ký tự thành chuỗi chỉ số tương ứng charset
"""

import os
import random
import torch
from torch.utils.data import Dataset
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from typing import List, Dict, Tuple, Optional

# Danh mục từ vựng tài chính, kế toán, ngân hàng tiếng Việt phong phú để sinh mẫu tổng hợp
FINANCE_WORDS = [
    "Doanh thu", "Lợi nhuận", "Thuế TNDN", "Khấu hao", "Dòng tiền", "Tài sản", "Nợ phải trả",
    "Vốn chủ sở hữu", "Chi phí bán hàng", "Chi phí quản lý", "Giá vốn", "Định khoản", "Nợ TK 111",
    "Có TK 112", "Hóa đơn giá trị gia tăng", "Số tiền bằng chữ", "Tổng thanh toán", "Chiết khấu",
    "Tiền gửi ngân hàng", "Trái phiếu", "Cổ tức", "Tỷ suất hoàn vốn", "Dự toán CAPEX", "Chi phí OPEX",
    "Phương Trang", "FUTA Bus Lines", "Trạm sạc xe điện", "Chi phí giải phóng mặt bằng", "Kéo điện",
    "Bảo hiểm xã hội", "Kế toán trưởng", "Giám đốc tài chính", "Biên bản bàn giao", "Hợp đồng dịch vụ",
    "Quyết toán thuế", "Kiểm toán độc lập", "Báo cáo tài chính năm 2026", "Tạm ứng tiền mặt"
]

COMMON_VI_SYMBOLS = ["-", "+", "/", "%", "₫", "VNĐ", "USD", ".", ",", "(", ")", ":"]

class VietnameseTextGenerator:
    """Sinh chuỗi văn bản tiếng Việt ngẫu nhiên chuyên đề tài chính / hóa đơn."""
    @staticmethod
    def sample_line() -> str:
        pattern = random.choice([
            "words_only",
            "word_with_number",
            "financial_row",
            "account_entry"
        ])

        if pattern == "words_only":
            return " ".join(random.sample(FINANCE_WORDS, k=random.randint(1, 3)))
        elif pattern == "word_with_number":
            word = random.choice(FINANCE_WORDS)
            amount = f"{random.randint(10, 999):,}".replace(",", ".")
            unit = random.choice(["đồng", "₫", "VNĐ", "%", "triệu"])
            return f"{word}: {amount} {unit}"
        elif pattern == "financial_row":
            word = random.choice(FINANCE_WORDS)
            num1 = f"{random.randint(100, 9999):,}".replace(",", ".")
            num2 = f"{random.randint(100, 9999):,}".replace(",", ".")
            return f"{word} | {num1} | {num2}"
        else:
            acc1 = f"TK {random.choice([111, 112, 131, 154, 241, 331, 641, 642])}"
            acc2 = f"TK {random.choice([111, 112, 333, 511, 911])}"
            money = f"{random.randint(1, 500) * 1000000:,} ₫".replace(",", ".")
            return f"Nợ {acc1} / Có {acc2}: {money}"

class SyntheticVietnameseOCRDataset(Dataset):
    """
    Dataset tự sinh ảnh text-line tiếng Việt phục vụ huấn luyện Recognizer.
    Không yêu cầu tải trước dataset ngoài, sẵn sàng chạy ngay lập tức.
    """
    def __init__(
        self,
        char2idx: Dict[str, int],
        num_samples: int = 5000,
        img_height: int = 32,
        max_width: int = 512
    ):
        self.char2idx = char2idx
        self.num_samples = num_samples
        self.img_height = img_height
        self.max_width = max_width
        self.generator = VietnameseTextGenerator()

    def __len__(self) -> int:
        return self.num_samples

    def _render_text(self, text: str) -> Image.Image:
        """Render text tiếng Việt thành ảnh PIL với phông chữ hệ thống."""
        font_size = 20
        # Cố gắng load phông chữ tiếng Việt trên Windows
        font = None
        for font_name in ["arial.ttf", "times.ttf", "segoeui.ttf", "calibri.ttf"]:
            try:
                font = ImageFont.truetype(font_name, font_size)
                break
            except Exception:
                continue

        if font is None:
            font = ImageFont.load_default()

        # Tính toán kích thước chữ
        dummy_img = Image.new('RGB', (10, 10))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = max(bbox[2] - bbox[0] + 16, 64)
        text_h = max(bbox[3] - bbox[1] + 8, self.img_height)

        # Tạo ảnh nền trắng (hoặc ngả xám nhẹ như giấy in)
        bg_color = (random.randint(245, 255), random.randint(245, 255), random.randint(245, 255))
        img = Image.new('RGB', (text_w, text_h), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Màu chữ (đen hoặc xanh mực nhẹ)
        text_color = (random.randint(0, 35), random.randint(0, 35), random.randint(0, 45))
        draw.text((8, (text_h - (bbox[3] - bbox[1])) // 2), text, font=font, fill=text_color)

        # Augmentation nhẹ: vạch kẻ ô bảng biểu ngẫu nhiên
        if random.random() < 0.3:
            draw.line([(0, text_h - 1), (text_w, text_h - 1)], fill=(200, 200, 200), width=1)
        if random.random() < 0.2:
            img = img.filter(ImageFilter.GaussianBlur(radius=0.4))

        # Scale về img_height chuẩn (32px), giữ tỷ lệ
        aspect_ratio = text_w / text_h
        target_w = int(self.img_height * aspect_ratio)
        target_w = min(target_w, self.max_width)
        img = img.resize((target_w, self.img_height), Image.Resampling.BILINEAR)

        # Pad về max_width bằng màu nền trắng
        final_img = Image.new('RGB', (self.max_width, self.img_height), color=(255, 255, 255))
        final_img.paste(img, (0, 0))
        return final_img

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, int, int]:
        text = self.generator.sample_line()
        pil_img = self._render_text(text)

        # Chuẩn hóa ảnh về Tensor: (3, H, W) trong khoảng [-1, 1]
        img_np = np.array(pil_img, dtype=np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1)
        img_tensor = (img_tensor - 0.5) / 0.5

        # Mã hóa text thành token indices
        target_indices = []
        for char in text:
            if char in self.char2idx:
                target_indices.append(self.char2idx[char])
            else:
                target_indices.append(self.char2idx.get('<unk>', 1))

        target_tensor = torch.tensor(target_indices, dtype=torch.long)
        input_length = self.max_width // 4  # Do pool qua CNN 4 lần
        target_length = len(target_indices)

        return img_tensor, target_tensor, input_length, target_length

def ocr_collate_fn(batch):
    """Gom nhóm batch cho CTCLoss (ghép phẳng targets tensor)."""
    images, targets, input_lengths, target_lengths = zip(*batch)

    images = torch.stack(images, dim=0)
    input_lengths = torch.tensor(input_lengths, dtype=torch.long)
    target_lengths = torch.tensor(target_lengths, dtype=torch.long)
    targets_concat = torch.cat(targets, dim=0)

    return images, targets_concat, input_lengths, target_lengths

if __name__ == "__main__":
    from vietnamese_charset import get_vietnamese_characters
    chars = ['<blank>', '<unk>'] + get_vietnamese_characters()
    char2idx = {c: i for i, c in enumerate(chars)}

    dataset = SyntheticVietnameseOCRDataset(char2idx=char2idx, num_samples=10)
    img, target, in_len, tgt_len = dataset[0]
    print(f"Sample ảnh shape: {img.shape}, Số lượng ký tự target: {tgt_len}")
