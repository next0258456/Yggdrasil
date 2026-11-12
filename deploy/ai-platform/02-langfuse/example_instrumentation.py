"""
YGGDRASIL DATA PLATFORM — LANGFUSE INSTRUMENTATION BEST PRACTICES
Tài liệu mẫu chuẩn mực theo hướng dẫn chính thức từ `github.com/langfuse/skills`:
1. Span hierarchy: Trace -> Agent Span -> Retriever Span -> Generation
2. Observation Types: 'agent', 'retriever', 'generation'
3. Context: session_id, user_id, tags (department, environment)
4. Model & Token Tracking
"""

import os
from langfuse.decorators import observe, langfuse_context

# ------------------------------------------------------------------------------
# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG KẾT NỐI LANGFUSE LOCAL
# ------------------------------------------------------------------------------
# Sếp lấy Public Key và Secret Key sau khi tạo Project trên http://localhost:3100
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-local-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-local-test")
os.environ.setdefault("LANGFUSE_HOST", "http://localhost:3100")


# ------------------------------------------------------------------------------
# 2. RETRIEVER SPAN (Truy vấn tài liệu/bảng dữ liệu)
# ------------------------------------------------------------------------------
@observe(as_type="generation")  # hoặc retriever span
def retrieve_financial_context(query: str, department: str) -> list[str]:
    """
    Mô phỏng truy vấn từ NeMo-Retriever hoặc Auto-Ontology.
    Gắn nhãn observation type chuẩn là 'retriever'.
    """
    langfuse_context.update_current_observation(
        name="nemo-retriever-lookup",
        input={"query": query, "department": department},
        metadata={"engine": "NeMo-Retriever-v2", "top_k": 3}
    )
    
    # Kết quả tìm kiếm mẫu
    results = [
        "Chính sách phụ cấp quý 4/2026: Phòng Kế toán +15%, Marketing +10%.",
        "Ngân sách thưởng hoàn thành KPI vượt 120% cho khối Vận hành."
    ]
    
    langfuse_context.update_current_observation(output={"documents_found": len(results)})
    return results


# ------------------------------------------------------------------------------
# 3. GENERATION SPAN (Thực thi LLM sinh câu trả lời)
# ------------------------------------------------------------------------------
@observe(as_type="generation")
def generate_audit_report(user_query: str, context: list[str]) -> str:
    """
    Mô phỏng lượt gọi model qua Langfuse AI Gateway (:3031) hoặc OpenAI client.
    Theo dõi: model name, usage tokens, prompt.
    """
    prompt = f"Ngữ cảnh:\n{chr(10).join(context)}\n\nCâu hỏi: {user_query}"
    
    # Giả lập phản hồi từ LLM
    response = "Theo chính sách quý 4/2026, phòng Kế toán được áp dụng mức phụ cấp +15%."
    
    # Cập nhật metadata đo lường chất lượng & chi phí
    langfuse_context.update_current_observation(
        name="llm-payroll-synthesizer",
        model="nvidia/llama-3.1-nemotron-70b-instruct",
        input={"prompt": prompt},
        output={"completion": response},
        usage={
            "input": 128,
            "output": 42,
            "total": 170
        }
    )
    return response


# ------------------------------------------------------------------------------
# 4. ROOT TRACE (Toàn bộ vòng đời công việc của Agent)
# ------------------------------------------------------------------------------
@observe()
def run_payroll_agent_workflow(
    question: str,
    user_id: str = "accountant_chief_01",
    department: str = "Finance-Accounting",
    session_id: str = "session_payroll_2026_q4"
):
    """
    Root Trace: Đóng gói toàn bộ workflow của Agent.
    Bắt buộc có: trace name rõ ràng, user_id, session_id, tags phân quyền.
    """
    # Thiết lập Trace-level context chuẩn theo best practices
    langfuse_context.update_current_trace(
        name="autonomous-payroll-audit",
        user_id=user_id,
        session_id=session_id,
        tags=["production", "department:finance", "agent:payroll-auditor"],
        metadata={
            "app_version": "2026.11.10",
            "environment": "production",
            "department": department
        }
    )

    # Bước 1: Tra cứu ngữ cảnh (Retriever)
    docs = retrieve_financial_context(query=question, department=department)

    # Bước 2: Sinh báo cáo (LLM Generation)
    final_answer = generate_audit_report(user_query=question, context=docs)

    return final_answer


if __name__ == "__main__":
    print("🚀 Bắt đầu thực thi Agent Workflow với Langfuse Tracing...")
    result = run_payroll_agent_workflow("Kiểm tra mức phụ cấp áp dụng cho phòng Kế toán quý 4/2026")
    print(f"\n✅ Kết quả: {result}")
    print("\n👉 Mời sếp vào http://localhost:3100 -> Traces để xem sơ đồ phân cấp (Span Hierarchy)!")
