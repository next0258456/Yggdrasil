"""
vietnamese_charset.py
Định nghĩa 67 ký tự tiếng Việt có dấu và tiện ích mở rộng từ điển giải mã (charset.txt)
cho Nemotron OCR v2 Recognizer.
"""

import os
from typing import List, Set, Tuple

# Danh sách 67 ký tự tiếng Việt có dấu (cả thường lẫn hoa) theo chuẩn Unicode dựng sẵn
VIETNAMESE_LOWERCASE = [
    # a
    'á', 'à', 'ả', 'ã', 'ạ',
    'ă', 'ắ', 'ằ', 'ẳ', 'ẵ', 'ặ',
    'â', 'ấ', 'ầ', 'ẩ', 'ẫ', 'ậ',
    # d
    'đ',
    # e
    'é', 'è', 'ẻ', 'ẽ', 'ẹ',
    'ê', 'ế', 'ề', 'ể', 'ễ', 'ệ',
    # i
    'í', 'ì', 'ỉ', 'ĩ', 'ị',
    # o
    'ó', 'ò', 'ỏ', 'õ', 'ọ',
    'ô', 'ố', 'ồ', 'ổ', 'ỗ', 'ộ',
    'ơ', 'ớ', 'ờ', 'ở', 'ỡ', 'ợ',
    # u
    'ú', 'ù', 'ủ', 'ũ', 'ụ',
    'ư', 'ứ', 'ừ', 'ử', 'ữ', 'ự',
    # y
    'ý', 'ỳ', 'ỷ', 'ỹ', 'ỵ'
]

VIETNAMESE_UPPERCASE = [
    # A
    'Á', 'À', 'Ả', 'Ã', 'Ạ',
    'Ă', 'Ắ', 'Ằ', 'Ẳ', 'Ẵ', 'Ặ',
    'Â', 'Ấ', 'Ầ', 'Ẩ', 'Ẫ', 'Ậ',
    # D
    'Đ',
    # E
    'É', 'È', 'Ẻ', 'Ẽ', 'Ẹ',
    'Ê', 'Ế', 'Ề', 'Ể', 'Ễ', 'Ệ',
    # I
    'Í', 'Ì', 'Ỉ', 'Ĩ', 'Ị',
    # O
    'Ó', 'Ò', 'Ỏ', 'Õ', 'Ọ',
    'Ô', 'Ố', 'Ồ', 'Ổ', 'Ỗ', 'Ộ',
    'Ơ', 'Ớ', 'Ờ', 'Ở', 'Ỡ', 'Ợ',
    # U
    'Ú', 'Ù', 'Ủ', 'Ũ', 'Ụ',
    'Ư', 'Ứ', 'Ừ', 'Ử', 'Ữ', 'Ự',
    # Y
    'Ý', 'Ỳ', 'Ỷ', 'Ỹ', 'Ỵ'
]

# Ký hiệu tiền tệ và đơn vị thông dụng trong hóa đơn/báo cáo tài chính tiếng Việt
VIETNAMESE_FINANCE_SYMBOLS = ['₫', 'đ', 'Đ']

ALL_VIETNAMESE_CHARS = sorted(list(set(VIETNAMESE_LOWERCASE + VIETNAMESE_UPPERCASE + VIETNAMESE_FINANCE_SYMBOLS)))

def get_vietnamese_characters() -> List[str]:
    """Trả về danh sách toàn bộ ký tự tiếng Việt mở rộng."""
    return ALL_VIETNAMESE_CHARS

def expand_charset_file(
    original_charset_path: str,
    output_charset_path: str
) -> Tuple[int, int, List[str]]:
    """
    Đọc file charset.txt gốc của Nemotron OCR v2 và ghép nối các ký tự tiếng Việt mới.
    Trả về: (số lượng token cũ, số lượng token mới, danh sách ký tự thêm vào)
    """
    existing_tokens: Set[str] = set()
    token_list: List[str] = []

    if os.path.exists(original_charset_path):
        with open(original_charset_path, 'r', encoding='utf-8') as f:
            for line in f:
                token = line.rstrip('\r\n')
                existing_tokens.add(token)
                token_list.append(token)
    else:
        # Khởi tạo mặc định nếu chưa có file gốc (chế độ demo/fallback)
        token_list = ['<blank>', '<unk>']
        existing_tokens = set(token_list)

    num_old = len(token_list)
    added_chars: List[str] = []

    for char in ALL_VIETNAMESE_CHARS:
        if char not in existing_tokens:
            token_list.append(char)
            existing_tokens.add(char)
            added_chars.append(char)

    os.makedirs(os.path.dirname(os.path.abspath(output_charset_path)), exist_ok=True)
    with open(output_charset_path, 'w', encoding='utf-8') as f:
        for token in token_list:
            f.write(f"{token}\n")

    num_new = len(token_list)
    return num_old, num_new, added_chars

if __name__ == "__main__":
    chars = get_vietnamese_characters()
    print(f"Tổng số ký tự tiếng Việt bổ sung: {len(chars)}")
    print("Mẫu:", "".join(chars[:25]), "...")
