# Yggdrasil AI Platform — Triad Architecture

> **Một bài toán Data Lakehouse AI — Ba trường phái kỹ thuật thực chiến.**

Hệ thống AI Platform của Yggdrasil được phân tách thành 3 nhánh độc lập, mỗi nhánh đại diện cho một triết lý thiết kế và tập hợp công nghệ riêng biệt:

1. 🏛️ [**01-nvidia-framework**](./01-nvidia-framework/README.md)
   * **Định vị:** Enterprise Titan — Chuẩn giải pháp chính hãng NVIDIA.
   * **Cốt lõi:** Nemotron Voice Agent (Pipecat WebRTC/WebSocket, Talker/Thinker Cascaded Voice, VAD Barge-in), NeMo-Relay, NeMo-Retriever, Auto-Ontology, NemoClaw/OpenShell, SkillEvaluator & Arize Phoenix OTLP.

2. 📊 [**02-langfuse**](./02-langfuse/README.md)
   * **Định vị:** Production LLMOps & FinOps Governance — Vận hành thực chiến, kiểm soát chất lượng và cầu dao cắt tiền tự động.
   * **Cốt lõi:** LiteLLM Proxy (Hard Spend Limit `max_budget`, RPM/TPM Rate-Limiting, 1-click API Key Block/Revocation), Langfuse Native AI Gateway (Rust), ClickHouse OLAP Backend, Prompt Versioning, Automated Evals (LLM-as-a-Judge).

3. ⚔️ [**03-y7l-native**](./03-y7l-native/README.md)
   * **Định vị:** The Y7L Way — Bản sắc tối giản cực đoan, Single-Node Hacker.
   * **Cốt lõi:** n8n Ingress, Redpanda 7-day Buffer, FastMCP, Obsidian Zero-Chunking, Single-Hop Circuit Breaker, Superset RLS, Embedded DuckDB, Bifrost Proxy, Valkyrie.
