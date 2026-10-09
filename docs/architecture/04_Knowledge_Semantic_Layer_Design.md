# Tầng 4: Thiết Kế Lớp Ngữ Nghĩa & Tri Thức (Knowledge & Semantic Layer)

## 1. Sự "Phá Cách" Trong Tư Duy Kiến Trúc
Trong các nền tảng dữ liệu truyền thống (Kỷ nguyên BI-First), Lớp Ngữ Nghĩa (Semantic Layer) thường bị ép phải là một khối Code trung tâm duy nhất (YAML/JSON như Cube.dev, dbt Semantic Layer) ôm đồm cả Công thức tính toán lẫn Định nghĩa kinh doanh. Điều này tạo ra rào cản kỹ thuật khổng lồ cho vận hành và cực kỳ nghèo nàn khi dùng làm ngữ cảnh (Context) cho AI.

Hệ thống Yggdrasil chọn một hướng đi phản nghịch (Kỷ nguyên AI-First): **"Xé xác Lớp Ngữ Nghĩa" (Deconstructing the Semantic Layer)** làm hai nửa chuyên biệt:
1. **Phần "Thể xác" (Công thức Toán học & BI):** Bàn giao hoàn toàn cho giao diện Native của BI Tool (Saved Metrics trong Superset). Đội Data Analyst tự do kéo thả, loại bỏ hoàn toàn nợ kỹ thuật phải duy trì file YAML bên ngoài.
2. **Phần "Linh hồn" (Ngữ cảnh & Bẫy Dữ liệu):** Sử dụng **Obsidian (Markdown Knowledge Graph)** làm trung tâm. Lớp này không chứa lệnh SQL khô khan, mà dùng văn xuôi để làm "Sách hướng dẫn sử dụng" dạy cho AI (Mimir) cách tư duy và né bẫy dữ liệu trước khi sinh code.
### 1.1. Tại sao Obsidian thay vì hệ thống Vector RAG truyền thống?
Thay vì đi theo lối mòn của ngành AI hiện tại là nhồi nhét tài liệu vào Vector Database (Pinecone, Milvus) để làm RAG (Retrieval-Augmented Generation), Yggdrasil chọn Đồ thị tri thức Obsidian vì 3 lý do sống còn:

1. **Sự mơ hồ (Fuzzy) vs Logic tuyệt đối:** Tìm kiếm Vector (Cosine Similarity) dựa trên khoảng cách ngữ nghĩa, dễ bốc nhầm hoặc bốc thiếu dữ liệu do khác biệt từ ngữ. Đối với việc sinh mã SQL, LLM cần **Logic tuyệt đối** (Khóa ngoại, quy tắc tính toán). Obsidian với các liên kết cứng (Hard-links [[Wikilinks]]) cho phép LLM duyệt đồ thị (Graph Traversal) 100% chính xác theo quy tắc nghiệp vụ.
2. **Khả năng Bảo trì (Human-in-the-loop):** Vector DB là một "Hộp đen" (Black Box) đối với dân kinh tế. Nếu định nghĩa "Doanh thu" bị sai, việc sửa trong Vector DB đòi hỏi Engineer phải chạy lại luồng Embedding rất phức tạp. Với Obsidian, Kế toán trưởng chỉ việc mở phần mềm, sửa file Doanh_Thu.md bằng tiếng Việt, nhấn Save. AI lập tức cập nhật luật mới.
3. **Kỷ nguyên Long-Context (Tận dụng sức mạnh LLM thế hệ mới):** RAG ra đời để lách luật giới hạn bộ nhớ (4K-8K tokens) của LLM đời cũ bằng cách "băm nhỏ" tài liệu (Chunking). Ngày nay, với sự tiến hóa của các mô hình như 3.1 Pro, 3.8 Flash, 3.5 Flash Lite hay con Gemini 4 Agon sắp mở, cửa sổ ngữ cảnh (Context Window) đã lên tới hàng triệu tokens. Thay vì băm nhỏ và tìm kiếm mạo hiểm bằng Vector, ta có thể bơm toàn bộ thư mục Từ điển dữ liệu của Obsidian (vài trăm KB Markdown) thẳng vào Prompt, LLM sẽ tự xâu chuỗi một cách hoàn hảo.

## 2. Kiến Trúc Obsidian Vault (Hệ Não Bộ)
Tầng 4 không chứa dữ liệu số, mà chứa "Ý nghĩa" của dữ liệu số đó. Obsidian Vault được cấu trúc thành các thư mục cốt lõi:

### 2.1. Business Glossary (Từ điển Nghiệp vụ)
Chứa các định nghĩa quy chuẩn bằng ngôn ngữ tự nhiên (Markdown).
- *Ví dụ file [[Doanh Thu Thuần]].md:*
  > "Doanh thu thuần là tổng giá trị bán hàng (gross_sales) trừ đi thuế (	ax) và chiết khấu (discount). Được tính toán dựa trên bảng ct_sales."

### 2.2. Data Dictionary (Từ điển Dữ liệu & Bẫy Dữ liệu)
Chứa siêu dữ liệu (Metadata) mô tả cấu trúc của các bảng trong Data Warehouse. Đặc biệt, đây là nơi chứa các **Data Traps (Cạm bẫy dữ liệu)** để cảnh báo AI.
- *Ví dụ file [[fct_sales]].md:* 
  Mô tả chi tiết từng cột. **CẢNH BÁO AI:** Cột otal_price trong bảng này có thể bị lỗi hệ thống chứa toàn số 0. Không được dùng SUM(total_price). Phải tự tính bằng SUM(quantity * unit_price).

### 2.3. Knowledge Graph (Đồ thị Tri thức)
Tính năng mạnh mẽ nhất của Obsidian là khả năng liên kết bằng [[Wikilinks]]. 
- Khi người dùng hỏi về "Doanh thu", hệ thống đồ thị tự động nhận diện mối liên kết giữa khái niệm [[Doanh Thu Thuần]], bảng [[fct_sales]], và chiều không gian [[dim_geography]]. LLM (Mimir) truy xuất dọc theo chuỗi liên kết này để lấy đủ ngữ cảnh trước khi viết code SQL.

## 3. Cơ Chế Tương Tác Giữa Mimir (Tầng 5) và Obsidian (Tầng 4)
Tầng 4 đóng vai trò là "Bộ nhớ dài hạn" (Long-term Memory) cho Mimir. Để đảm bảo không sinh ra các câu truy vấn ảo tưởng, luồng xử lý diễn ra theo cơ chế **Hybrid (Đọc Kép)**:

1. **User Prompt:** Người dùng yêu cầu "Tính doanh thu thuần tháng này".
2. **Graph Traversal (Duyệt đồ thị Obsidian):** Mimir phân tích câu hỏi, gọi Tool để tìm kiếm file tương ứng (VD: Doanh Thu Thuần.md). Mimir tự động đọc file này và đệ quy đọc tiếp các file liên quan (như fct_sales.md) để lấy Ngữ cảnh (Linh hồn) và Cạm bẫy dữ liệu (Data Traps).
3. **API Routing (Lấy Thể xác Toán học):** Mimir kiểm tra xem có Metric "Doanh thu thuần" nào đã được định nghĩa trên giao diện Superset hay không.
   - **Nhánh 1 (Happy Path - Có sẵn Metric):** Mimir hoạt động như một Intent Router, lấy thẳng công thức toán học từ API Superset, kết hợp với bộ lọc thời gian để trả về kết quả mà **không tự sinh SQL**.
   - **Nhánh 2 (Ad-hoc - Không có sẵn Metric):** Mimir áp dụng khả năng Text-to-SQL. Nó ghép cấu trúc bảng lấy từ Obsidian và tự sinh câu lệnh SQL thô, sau đó đẩy xuống Superset SQL Lab để tận dụng RLS. Ở luồng này, AI cũng né được 100% "Data Traps" nhờ đọc được cảnh báo trong Markdown.

## 4. Kết Luận: Cú Đặt Cược Chiến Lược (The Strategic Bet)
Thiết kế Tầng 4 của Yggdrasil không phải là một sự ngẫu hứng, mà là một cú **Đặt cược chiến lược (Strategic Bet)** vào tương lai của công nghệ. Chúng ta đang đặt cược vào 3 trụ cột:

1. **Cược vào sự tiến hóa của LLM (Định luật Moore cho Context Window):** 
   Chúng ta cược rằng giới hạn bộ nhớ (Context Window) của AI sẽ ngày càng khổng lồ. Việc băm nhỏ dữ liệu bằng Vector DB (RAG) sẽ sớm trở thành một di sản cồng kềnh, lỗi thời đối với dữ liệu có cấu trúc. 
2. **Cược vào sự tối giản vật lý của Markdown (Tối ưu chi phí tuyệt đối):**
   Thay vì phụ thuộc vào các công nghệ ngốn tiền như "Prompt Caching" của Google/OpenAI, chúng ta cược vào sự nhẹ bén nguyên thủy của Markdown. Mỗi định nghĩa, mỗi bảng chỉ là một file vài KB (vài trăm Tokens). Thông qua duyệt đồ thị cục bộ (Graph Traversal), AI chỉ gom đúng 3-4 file liên quan (dưới 10KB) cho mỗi truy vấn. Cấu trúc nguyên tử (Atomic) này bóp nghẹt bài toán "Chi phí API của Agent" xuống mức gần bằng 0 mà không cần phụ thuộc vào Vendor nào.
3. **Cược vào con người (Human-in-the-loop Maintainability):** 
   Chúng ta cược rằng một hệ thống mà **người dùng nghiệp vụ (Kế toán, Sale)** có thể trực tiếp mở ra, đọc hiểu và sửa luật bằng tiếng Việt (Markdown/Obsidian) sẽ sống dai hơn và ít nợ kỹ thuật (Technical Debt) hơn một hệ thống ép Data Engineer phải code YAML/Python.

Mimir và Obsidian không chỉ xử lý dữ liệu, mà chúng đang **dân chủ hóa** quyền sở hữu tri thức dữ liệu cho toàn doanh nghiệp.


