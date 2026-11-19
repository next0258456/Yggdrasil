"""FastAPI Track-B Sidecar server for n8n-centric 03-y7l-native."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from y7l_tools.auth import AuthError, AuthService, SessionStore
from y7l_tools.config import Settings, get_settings
from y7l_tools.guard import SQLSecurityError, mask_pii, validate_readonly_sql
from y7l_tools.pricing import estimate_cost_usd
from y7l_tools.sql_executor import MetricNotFoundError, SQLExecutor
from y7l_tools.vault import lint_vault, list_entities, read_context
from y7l_tools.voice_ocr import extract_document_text, synthesize_tts, transcribe_stt


class LoginRequest(BaseModel):
    username: str
    password: str
    chat_user_id: str | None = None


class VerifyTokenRequest(BaseModel):
    token: str | None = None


class RevokeSessionRequest(BaseModel):
    chat_user_id: str


class DeactivateUserRequest(BaseModel):
    chat_user_id: str | None = None


class ProvisionUserRequest(BaseModel):
    username: str
    password: str | None = None
    department: str = "general"
    region: str = "North"
    role: str = "sales"
    is_active: bool = True


class VaultContextRequest(BaseModel):
    query: str = ""
    entities: list[str] | None = None
    max_depth: int = Field(default=1, ge=0, le=3)
    max_bytes: int = Field(default=12000, ge=500, le=50000)


class MaskPIIRequest(BaseModel):
    text: str


class ValidateSQLRequest(BaseModel):
    sql: str


class ExecuteSQLRequest(BaseModel):
    sql: str
    export_format: str = "csv"


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None


class CostEstimateRequest(BaseModel):
    model: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory enabling isolated test configurations."""
    cfg = settings or get_settings()
    session_store = SessionStore(cfg.redis_url)
    auth_service = AuthService(cfg, session_store=session_store)
    sql_executor = SQLExecutor(cfg)

    app = FastAPI(
        title="Y7L Native Track-B Sidecar",
        version="0.1.0",
        description="Thin Track-B execution, Zero-Chunking Obsidian Vault, DuckDB RLS, and minimal Voice/OCR sidecar for n8n.",
    )
    app.state.settings = cfg
    app.state.auth = auth_service
    app.state.executor = sql_executor

    def _extract_bearer(authorization: str | None = Header(default=None)) -> tuple[str, dict[str, Any]]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Thiếu header Authorization: Bearer <JWT>.")
        raw_token = authorization.split(" ", 1)[1].strip()
        try:
            claims = auth_service.verify_token(raw_token)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        return raw_token, claims

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "y7l-tools",
            "vault_exists": cfg.vault_dir.exists(),
            "data_exists": cfg.data_path.exists(),
            "superset_mode": bool(cfg.superset_url.strip()),
        }

    # --- Auth & IAM Kill-Switch ---
    @app.post("/auth/login")
    def auth_login(req: LoginRequest) -> dict[str, Any]:
        try:
            return auth_service.login(req.username, req.password, req.chat_user_id)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    @app.post("/auth/verify")
    def auth_verify(
        req: VerifyTokenRequest | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        token = req.token if (req and req.token) else None
        if not token and authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        try:
            claims = auth_service.verify_token(token or "")
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        return {"valid": True, "claims": claims}

    @app.post("/auth/session/revoke")
    def auth_revoke_session(req: RevokeSessionRequest) -> dict[str, Any]:
        return auth_service.revoke_session(req.chat_user_id)

    @app.post("/auth/users/{username}/deactivate")
    def auth_deactivate_user(username: str, req: DeactivateUserRequest | None = None) -> dict[str, Any]:
        try:
            return auth_service.deactivate_user(username, req.chat_user_id if req else None)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    @app.post("/auth/users/provision")
    def auth_provision_user(req: ProvisionUserRequest) -> dict[str, Any]:
        return auth_service.provision_user(
            username=req.username,
            password=req.password,
            department=req.department,
            region=req.region,
            role=req.role,
            is_active=req.is_active,
        )

    # --- Obsidian Vault (Zero-Chunking) ---
    @app.get("/vault/entities")
    def vault_entities() -> dict[str, Any]:
        entities = list_entities(cfg.vault_dir)
        return {"count": len(entities), "entities": entities}

    @app.post("/vault/context")
    def vault_context(req: VaultContextRequest) -> dict[str, Any]:
        return read_context(
            vault_root=cfg.vault_dir,
            query=req.query,
            entities=req.entities,
            max_depth=req.max_depth,
            max_bytes=req.max_bytes,
        )

    @app.get("/vault/lint")
    def vault_lint() -> dict[str, Any]:
        return lint_vault(cfg.vault_dir)

    # --- Safety Relay Guard ---
    @app.post("/guard/mask-pii")
    def guard_mask_pii(req: MaskPIIRequest) -> dict[str, Any]:
        masked, types = mask_pii(req.text)
        return {"masked_text": masked, "masked_types": types}

    @app.post("/guard/validate-sql")
    def guard_validate_sql(req: ValidateSQLRequest) -> dict[str, Any]:
        try:
            clean_sql = validate_readonly_sql(req.sql)
        except SQLSecurityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"valid": True, "clean_sql": clean_sql}

    # --- Flow 1 Saved Metrics & Flow 2 Single-Hop RLS SQL Execution ---
    @app.get("/metrics/saved")
    def list_metrics() -> dict[str, Any]:
        return {"metrics": sql_executor.list_saved_metrics()}

    @app.post("/metrics/saved/{metric_name}")
    def run_saved_metric(
        metric_name: str,
        export_format: str = "csv",
        auth_ctx: tuple[str, dict[str, Any]] = Depends(_extract_bearer),
    ) -> dict[str, Any]:
        _, claims = auth_ctx
        try:
            return sql_executor.execute_saved_metric(
                metric_name=metric_name,
                claims=claims,
                export_format=export_format,
            )
        except MetricNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/sql/execute-rls")
    def execute_sql(
        req: ExecuteSQLRequest,
        auth_ctx: tuple[str, dict[str, Any]] = Depends(_extract_bearer),
    ) -> dict[str, Any]:
        raw_jwt, claims = auth_ctx
        try:
            return sql_executor.execute_sql_rls(
                sql=req.sql,
                claims=claims,
                raw_jwt=raw_jwt,
                export_format=req.export_format,
            )
        except SQLSecurityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"SQL execution failed: {exc}") from exc

    @app.get("/artifacts/{filename}")
    def download_artifact(filename: str) -> FileResponse:
        if Path(filename).name != filename or ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid artifact filename.")
        exports_root = cfg.exports_dir.resolve()
        candidate = (exports_root / filename).resolve()
        if not candidate.is_relative_to(exports_root) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found.")
        return FileResponse(path=candidate, filename=filename)

    # --- Minimal Voice (STT/TTS) & Lightweight OCR/PDF Extractor ---
    @app.post("/voice/tts")
    async def voice_tts(req: TTSRequest) -> dict[str, Any]:
        try:
            out_path = await synthesize_tts(
                text=req.text,
                voice=req.voice or cfg.tts_voice,
                out_dir=cfg.exports_dir,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "artifact_filename": out_path.name,
            "artifact_url": f"/artifacts/{out_path.name}",
            "voice": req.voice or cfg.tts_voice,
        }

    @app.post("/voice/stt")
    async def voice_stt(file: UploadFile = File(...)) -> dict[str, Any]:
        audio_bytes = await file.read()
        try:
            transcript = await transcribe_stt(
                audio_bytes=audio_bytes,
                filename=file.filename or "voice.ogg",
                llm_api_base=cfg.llm_api_base,
                llm_api_key=cfg.llm_api_key,
                model=cfg.stt_model,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"text": transcript, "model": cfg.stt_model}

    @app.post("/ocr/extract")
    async def ocr_extract(file: UploadFile = File(...)) -> dict[str, Any]:
        payload = await file.read()
        try:
            return extract_document_text(payload, file.filename or "document.txt")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- FinOps Cost Estimator ---
    @app.post("/finops/estimate-cost")
    def finops_estimate(req: CostEstimateRequest) -> dict[str, Any]:
        cost = estimate_cost_usd(
            model=req.model,
            prompt_tokens=req.prompt_tokens,
            completion_tokens=req.completion_tokens,
        )
        return {
            "model": req.model,
            "prompt_tokens": req.prompt_tokens,
            "completion_tokens": req.completion_tokens,
            "total_tokens": req.prompt_tokens + req.completion_tokens,
            "estimated_cost_usd": cost,
        }

    return app


app = create_app()
