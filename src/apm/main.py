import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pyotp
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select, text, update
from starlette.middleware.sessions import SessionMiddleware

from apm import __version__
from apm.config import Settings
from apm.db import (
    Audit,
    Database,
    Job,
    LoginSession,
    Resource,
    Revision,
    User,
    now,
    state_get,
    state_set,
)
from apm.i18n import dictionary
from apm.schemas import ADMIN_KINDS, SCHEMAS, LoginInput, ResourceInput, SetupInput, UserInput
from apm.security import Vault, digest, passwords, verify_password
from apm.services import (
    audit,
    bootstrap_token,
    enqueue,
    enqueue_apply,
    get_resource,
    require_role,
    save_resource,
    serialize,
)

PACKAGE = Path(__file__).parent
DUMMY_PASSWORD_HASH = passwords.hash(secrets.token_urlsafe(32))


def create_app(config=None):
    config = config or Settings()
    database = Database(config)
    vault = Vault(config.data_dir)

    @asynccontextmanager
    async def lifespan(app):
        import fcntl

        lock = (config.data_dir / "run/maintenance.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_SH)
        database.initialize()
        with database.session() as s:
            if not s.scalar(select(User.id).limit(1)):
                bootstrap_token(s, config.data_dir)
        yield
        database.engine.dispose()
        lock.close()

    app = FastAPI(
        title="Angie Proxy Manager",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.db, app.state.config, app.state.vault = database, config, vault
    app.add_middleware(
        SessionMiddleware,
        secret_key=vault.cookie_key,
        session_cookie="apm_oauth",
        https_only=config.cookie_secure,
        max_age=600,
        same_site="lax",
    )
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE / "templates")
    oauth = OAuth()
    if config.oidc_issuer:
        secret = config.oidc_client_secret_file.read_text().strip() if config.oidc_client_secret_file else ""
        oauth.register(
            "idp",
            client_id=config.oidc_client_id,
            client_secret=secret,
            server_metadata_url=config.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    def db():
        with database.session() as session:
            yield session

    def current(request: Request, session=Depends(db)):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            # Serialize read/check/write transactions, including domain ownership.
            session.execute(text("BEGIN IMMEDIATE"))
        token = request.cookies.get("apm_session", "")
        login = session.get(LoginSession, digest(token)) if token else None
        user = session.get(User, login.user_id) if login else None
        if not login or login.expires_at <= now() or not user or not user.enabled or not login.authenticated:
            raise HTTPException(401, "Authentication required")
        request.state.login = login
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), login.csrf):
                raise HTTPException(403, "Invalid CSRF token")
        return user

    def admin(user=Depends(current)):
        require_role(user, "admin")
        return user

    @app.middleware("http")
    async def security_headers(request, call_next):
        nonce = secrets.token_urlsafe(18)
        request.state.nonce = nonce
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.url.netloc:
                return JSONResponse({"detail": "Cross-origin requests are forbidden"}, status_code=403)
            length = request.headers.get("content-length", "0")
            if length.isdigit() and int(length) > 8 * 1024 * 1024:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def login_response(session, user, authenticated=True):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        session.add(
            LoginSession(
                token_hash=digest(token),
                user_id=user.id,
                csrf=csrf,
                expires_at=now() + (config.session_seconds if authenticated else 300),
                authenticated=authenticated,
            )
        )
        result = JSONResponse(
            {
                "csrf_token": csrf,
                "mfa_required": not authenticated,
                "user": {"id": user.id, "email": user.email, "role": user.role, "language": user.language},
            }
        )
        result.set_cookie(
            "apm_session",
            token,
            httponly=True,
            secure=config.cookie_secure,
            samesite="strict",
            max_age=config.session_seconds if authenticated else 300,
        )
        return result

    def throttle(session, request, email):
        key = "login:" + digest(f"{request.client.host if request.client else ''}:{email.lower()}")
        state = state_get(session, key, {"count": 0, "until": now() + 300})
        if state["until"] < now():
            state = {"count": 0, "until": now() + 300}
        if state["count"] >= 10:
            raise HTTPException(429, "Too many attempts; retry later")
        state_set(session, key, {**state, "count": state["count"] + 1})
        # Persist failures even when authentication later raises an HTTPException.
        session.commit()

    @app.get("/health/live")
    def live():
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready")
    def ready(session=Depends(db)):
        session.execute(text("SELECT 1"))
        agent = state_get(session, "agent_status", {})
        available = agent.get("available", False) and agent.get("collected_at", 0) > now() - 120
        return JSONResponse({"database": True, "agent": available}, status_code=200 if available else 503)

    @app.post("/api/v1/auth/setup")
    def setup(data: SetupInput, session=Depends(db)):
        session.execute(text("BEGIN IMMEDIATE"))
        if session.scalar(select(User.id).limit(1)):
            raise HTTPException(409, "Setup already completed")
        expected = state_get(session, "setup", {}).get("digest", "")
        if not expected or not secrets.compare_digest(digest(data.token), expected):
            raise HTTPException(403, "Invalid setup token")
        if len(data.password) < 12:
            raise HTTPException(422, "Password must contain at least 12 characters")
        user = User(
            email=data.email.strip().lower(),
            password_hash=passwords.hash(data.password),
            role="admin",
            language=data.language,
        )
        session.add(user)
        session.flush()
        state_set(session, "setup", {"completed": True})
        audit(session, user, "setup.completed")
        result = login_response(session, user)
        session.commit()
        (config.data_dir / "setup.token").unlink(missing_ok=True)
        return result

    @app.post("/api/v1/auth/login")
    def login(data: LoginInput, request: Request, session=Depends(db)):
        if config.oidc_only:
            raise HTTPException(403, "Use OIDC login")
        throttle(session, request, data.email)
        user = session.scalar(select(User).where(User.email == data.email.strip().lower()))
        valid = verify_password(data.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
        if not user or not valid or not user.enabled:
            raise HTTPException(401, "Invalid credentials")
        audit(session, user, "auth.login")
        return login_response(session, user, not bool(user.totp_secret))

    @app.post("/api/v1/auth/mfa/verify")
    def verify_mfa(data: dict, request: Request, session=Depends(db)):
        login = session.get(LoginSession, digest(request.cookies.get("apm_session", "")))
        if not login or login.expires_at <= now() or login.authenticated:
            raise HTTPException(401, "Pending MFA session required")
        user = session.get(User, login.user_id)
        if not user or not user.enabled:
            raise HTTPException(401, "Account disabled")
        throttle(session, request, user.email + ":mfa")
        code = str(data.get("code", ""))
        step = now() // 30
        valid = (
            user.totp_secret
            and pyotp.TOTP(vault.decrypt(user.totp_secret)).verify(code, valid_window=0)
            and step > user.last_totp_step
        )
        recovery = digest(code) in user.recovery_hashes
        if not valid and not recovery:
            raise HTTPException(401, "Invalid second factor")
        if recovery:
            remaining = [h for h in user.recovery_hashes if h != digest(code)]
            result = session.execute(
                update(User)
                .where(User.id == user.id, User.recovery_hashes == user.recovery_hashes)
                .values(recovery_hashes=remaining)
            )
            if not result.rowcount:
                raise HTTPException(401, "Recovery code already used")
        else:
            result = session.execute(
                update(User).where(User.id == user.id, User.last_totp_step < step).values(last_totp_step=step)
            )
            if not result.rowcount:
                raise HTTPException(401, "Code already used")
        session.delete(login)
        audit(session, user, "auth.mfa")
        return login_response(session, user)

    @app.post("/api/v1/auth/mfa/enroll")
    def enroll_mfa(data: dict, user=Depends(current), session=Depends(db)):
        if not verify_password(str(data.get("password", "")), user.password_hash):
            raise HTTPException(403, "Password confirmation required")
        secret = pyotp.random_base32()
        user.totp_pending = vault.encrypt(secret)
        return {
            "secret": secret,
            "uri": pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="Angie Proxy Manager"),
        }

    @app.post("/api/v1/auth/mfa/confirm")
    def confirm_mfa(data: dict, user=Depends(current), session=Depends(db)):
        if not user.totp_pending or not pyotp.TOTP(vault.decrypt(user.totp_pending)).verify(
            str(data.get("code", ""))
        ):
            raise HTTPException(422, "Invalid confirmation code")
        recovery = [secrets.token_hex(8) for _ in range(10)]
        user.totp_secret, user.totp_pending = user.totp_pending, None
        user.recovery_hashes = [digest(v) for v in recovery]
        audit(session, user, "auth.mfa.enabled")
        return {"recovery_codes": recovery}

    @app.get("/auth/oidc")
    async def oidc_login(request: Request):
        if not config.oidc_issuer:
            raise HTTPException(503, "OIDC not configured")
        return await oauth.idp.authorize_redirect(
            request, config.public_url.rstrip("/") + "/auth/oidc/callback"
        )

    @app.get("/auth/oidc/callback")
    async def oidc_callback(request: Request, session=Depends(db)):
        if not config.oidc_issuer:
            raise HTTPException(503, "OIDC not configured")
        try:
            token = await oauth.idp.authorize_access_token(request)
            info = token["userinfo"]
            if info.get("iss") != config.oidc_issuer or not info.get("sub"):
                raise ValueError("Invalid issuer or subject")
        except Exception:
            raise HTTPException(401, "OIDC verification failed") from None
        subject = config.oidc_issuer + "|" + info["sub"]
        user = session.scalar(select(User).where(User.oidc_subject == subject, User.enabled.is_(True)))
        if not user:
            raise HTTPException(403, "OIDC identity is not provisioned")
        result = login_response(session, user, not bool(user.totp_secret))
        response = RedirectResponse("/login?mfa=1" if user.totp_secret else "/", status_code=303)
        response.headers.append("set-cookie", result.headers["set-cookie"])
        audit(session, user, "auth.oidc")
        return response

    @app.get("/api/v1/auth/me")
    def me(request: Request, user=Depends(current)):
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "language": user.language,
            "csrf_token": request.state.login.csrf,
        }

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, user=Depends(current), session=Depends(db)):
        session.delete(request.state.login)
        response = JSONResponse({"ok": True})
        response.delete_cookie("apm_session")
        return response

    @app.get("/api/v1/dashboard")
    def dashboard(user=Depends(current), session=Depends(db)):
        counts = dict(session.execute(select(Resource.kind, func.count()).group_by(Resource.kind)).all())
        jobs = session.scalars(select(Job).order_by(Job.created_at.desc()).limit(10)).all()
        return {
            "counts": counts,
            "operations": [job_dict(j) for j in jobs],
            "applied": state_get(session, "applied", {}),
            "agent": state_get(session, "agent_status", {}),
            "capabilities": state_get(session, "capabilities", {"available": False}),
        }

    @app.get("/api/v1/capabilities")
    def capabilities(user=Depends(current), session=Depends(db)):
        return state_get(
            session, "capabilities", {"available": False, "reason": "Worker has not contacted Angie"}
        )

    @app.get("/api/v1/schemas/{kind}")
    def schema(kind: str, user=Depends(current)):
        if kind not in SCHEMAS:
            raise HTTPException(404)
        return SCHEMAS[kind].model_json_schema()

    def job_dict(job):
        return {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "error": job.error,
            "result": job.result,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    @app.get("/api/v1/operations")
    def operations(user=Depends(current), session=Depends(db)):
        return [job_dict(j) for j in session.scalars(select(Job).order_by(Job.created_at.desc()).limit(100))]

    @app.get("/api/v1/operations/{object_id}")
    def operation(object_id: str, user=Depends(current), session=Depends(db)):
        row = session.get(Job, object_id)
        if not row:
            raise HTTPException(404)
        return job_dict(row)

    @app.post("/api/v1/operations/reconcile")
    def discover(user=Depends(admin), session=Depends(db)):
        job = enqueue(session, "discovery.reconcile", {})
        audit(session, user, "discovery.requested", job.id)
        return {"operation_id": job.id}

    @app.post("/api/v1/operations/cloudflare-refresh")
    def cloudflare_refresh(user=Depends(admin), session=Depends(db)):
        return {"operation_id": enqueue(session, "cloudflare.refresh", {}).id}

    @app.get("/api/v1/revisions")
    def revisions(user=Depends(current), session=Depends(db)):
        return [
            {
                "id": r.id,
                "status": r.status,
                "generation": r.generation,
                "error": r.error,
                "created_at": r.created_at,
            }
            for r in session.scalars(select(Revision).order_by(Revision.created_at.desc()).limit(100))
        ]

    @app.post("/api/v1/revisions/apply")
    def apply_current(user=Depends(admin), session=Depends(db)):
        return enqueue_apply(session)

    @app.get("/api/v1/audit")
    def audit_log(user=Depends(admin), session=Depends(db)):
        return [
            {
                "id": a.id,
                "actor": a.actor,
                "action": a.action,
                "object_id": a.object_id,
                "detail": a.detail,
                "created_at": a.created_at,
            }
            for a in session.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200))
        ]

    @app.get("/api/v1/users")
    def users(user=Depends(admin), session=Depends(db)):
        return [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "enabled": u.enabled,
                "language": u.language,
                "mfa_enabled": bool(u.totp_secret),
                "oidc_subject": u.oidc_subject,
            }
            for u in session.scalars(select(User))
        ]

    @app.post("/api/v1/users", status_code=201)
    def create_user(data: UserInput, user=Depends(admin), session=Depends(db)):
        if len(data.password) < 12:
            raise HTTPException(422, "Password must contain at least 12 characters")
        if session.scalar(select(User.id).where(User.email == data.email.strip().lower())):
            raise HTTPException(409, "Email already exists")
        obj = User(
            email=data.email.strip().lower(),
            password_hash=passwords.hash(data.password),
            role=data.role,
            language=data.language,
        )
        session.add(obj)
        session.flush()
        audit(session, user, "user.create", obj.id)
        return {"id": obj.id}

    @app.patch("/api/v1/users/{object_id}")
    def update_user(object_id: str, data: dict, user=Depends(admin), session=Depends(db)):
        target = session.get(User, object_id)
        if not target:
            raise HTTPException(404)
        allowed = {"role", "enabled", "language", "oidc_subject"}
        if set(data) - allowed or data.get("role", target.role) not in ("admin", "operator", "observer"):
            raise HTTPException(422, "Invalid user fields")
        if data.get("language", target.language) not in ("ru", "en"):
            raise HTTPException(422, "Unsupported language")
        if target.role == "admin" and (data.get("role", "admin") != "admin" or not data.get("enabled", True)):
            count = session.scalar(
                select(func.count()).select_from(User).where(User.role == "admin", User.enabled.is_(True))
            )
            if count <= 1:
                raise HTTPException(409, "Cannot disable the last administrator")
        for key, value in data.items():
            setattr(target, key, value)
        session.execute(delete(LoginSession).where(LoginSession.user_id == target.id))
        audit(session, user, "user.update", target.id, fields=sorted(data))
        return {"ok": True}

    @app.get("/api/v1/resources/{kind}")
    def resources(kind: str, user=Depends(current), session=Depends(db)):
        if kind not in SCHEMAS:
            raise HTTPException(404)
        return [
            serialize(r, user.role)
            for r in session.scalars(select(Resource).where(Resource.kind == kind).order_by(Resource.name))
        ]

    @app.post("/api/v1/resources/{kind}", status_code=201)
    def create_resource(kind: str, data: ResourceInput, user=Depends(current), session=Depends(db)):
        return save_resource(session, config, user, kind, data)

    @app.put("/api/v1/resources/{kind}/{object_id}")
    def update_resource(
        kind: str,
        object_id: str,
        data: ResourceInput,
        request: Request,
        user=Depends(current),
        session=Depends(db),
    ):
        version = request.headers.get("if-match", "").strip('"')
        if version and not version.isdigit():
            raise HTTPException(422, "Invalid version")
        return save_resource(session, config, user, kind, data, object_id, int(version) if version else None)

    @app.delete("/api/v1/resources/{kind}/{object_id}")
    def delete_resource(
        kind: str, object_id: str, request: Request, user=Depends(admin), session=Depends(db)
    ):
        obj = get_resource(session, kind, object_id)
        if obj.source == "docker":
            raise HTTPException(409, "Remove source Docker labels instead")
        if request.headers.get("if-match", "").strip('"') != str(obj.version):
            raise HTTPException(409, "Resource version required")
        for other in session.scalars(select(Resource).where(Resource.id != object_id)):
            if object_id in json.dumps(other.data):
                raise HTTPException(409, "Resource is referenced")
        session.delete(obj)
        audit(session, user, "resource.delete", object_id, kind=kind)
        return enqueue_apply(session)

    @app.post("/api/v1/resources/dns-profiles/{object_id}/test")
    def test_dns(object_id: str, user=Depends(admin), session=Depends(db)):
        get_resource(session, "dns-profiles", object_id)
        return {"operation_id": enqueue(session, "dns.test", {"resource_id": object_id}).id}

    @app.post("/api/v1/resources/geo-policies/{object_id}/update-database")
    def update_geoip(object_id: str, user=Depends(admin), session=Depends(db)):
        get_resource(session, "geo-policies", object_id)
        return {"operation_id": enqueue(session, "geoip.update", {"resource_id": object_id}).id}

    @app.post("/api/v1/resources/certificates/{object_id}/upload")
    async def upload_certificate(
        object_id: str,
        certificate: UploadFile,
        private_key: UploadFile,
        user=Depends(admin),
        session=Depends(db),
    ):
        from apm.certificates import install_certificate

        obj = get_resource(session, "certificates", object_id)
        data = install_certificate(
            config,
            obj.id,
            await certificate.read(1024 * 1024),
            await private_key.read(1024 * 1024),
            obj.data.get("domains", []),
        )
        obj.data = {**obj.data, **data}
        obj.version += 1
        audit(session, user, "certificate.upload", obj.id)
        return enqueue_apply(session)

    @app.post("/api/v1/resources/client-cas/{object_id}/upload")
    async def upload_ca(
        object_id: str,
        certificate: UploadFile,
        crl: UploadFile | None = None,
        user=Depends(admin),
        session=Depends(db),
    ):
        from apm.certificates import install_ca

        obj = get_resource(session, "client-cas", object_id)
        obj.data = {
            **obj.data,
            **install_ca(
                config,
                obj.id,
                await certificate.read(1024 * 1024),
                await crl.read(1024 * 1024) if crl else None,
            ),
        }
        obj.version += 1
        return enqueue_apply(session)

    @app.post("/api/v1/resources/ech/{object_id}/generate")
    def ech_generate(object_id: str, user=Depends(admin), session=Depends(db)):
        get_resource(session, "ech", object_id)
        return {"operation_id": enqueue(session, "ech.generate", {"resource_id": object_id}).id}

    @app.post("/api/v1/resources/ech/{object_id}/confirm-dns")
    def ech_confirm(object_id: str, user=Depends(admin), session=Depends(db)):
        get_resource(session, "ech", object_id)
        return {"operation_id": enqueue(session, "ech.confirm", {"resource_id": object_id}).id}

    @app.post("/api/v1/imports/preview")
    async def preview_import(archive: UploadFile, user=Depends(admin), session=Depends(db)):
        from apm.transfers import preview

        return preview(config, await archive.read(8 * 1024 * 1024))

    @app.post("/api/v1/imports/{import_id}/activate")
    def activate_import(import_id: str, user=Depends(admin), session=Depends(db)):
        from apm.transfers import activate

        return activate(session, config, user, import_id)

    @app.post("/api/v1/imports/{import_id}/drafts")
    def import_drafts(import_id: str, user=Depends(admin), session=Depends(db)):
        from apm.transfers import activate

        return activate(session, config, user, import_id, drafts=True)

    @app.post("/api/v1/backups")
    def make_backup(user=Depends(admin), session=Depends(db)):
        from apm.db import uid

        backup_id = uid()
        return {
            "backup_id": backup_id,
            "operation_id": enqueue(session, "backup", {"backup_id": backup_id}).id,
        }

    @app.get("/api/v1/metrics")
    def metrics(user=Depends(current), session=Depends(db)):
        return {
            "latest": state_get(session, "metrics_latest", {}),
            **state_get(session, "metrics", {"points": []}),
        }

    @app.get("/analytics/goaccess", response_class=HTMLResponse)
    def goaccess(request: Request, user=Depends(current)):
        import re

        path = config.data_dir / "reports/goaccess.html"
        if not path.is_file():
            raise HTTPException(
                503, "Enable access logs and analytics, then start the GoAccess Compose profile"
            )
        document = re.sub(r"<script\b", f'<script nonce="{request.state.nonce}"', path.read_text())
        return HTMLResponse(document)

    @app.get("/api/v1/logs/{kind}")
    def logs(kind: str, user=Depends(current)):
        from apm.observability import tail

        if kind not in ("access", "error"):
            raise HTTPException(404)
        if kind == "error":
            require_role(user, "admin")
        return {"entries": tail(config.data_dir / "logs" / (kind + ".log"))}

    @app.get("/api/v1/backups/{backup_id}/download")
    def download_backup(backup_id: str, user=Depends(admin)):
        import uuid

        from fastapi.responses import FileResponse

        try:
            backup_id = str(uuid.UUID(backup_id))
        except ValueError:
            raise HTTPException(404) from None
        path = config.data_dir / "exports" / (backup_id + ".apm")
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, filename=backup_id + ".apm", media_type="application/octet-stream")

    @app.get("/fragments/operations", response_class=HTMLResponse)
    def recent_operations(request: Request, user=Depends(current), session=Depends(db)):
        language = request.cookies.get("apm_language", user.language)
        jobs = session.scalars(select(Job).order_by(Job.sequence.desc()).limit(8)).all()
        return templates.TemplateResponse(
            request, "operations.html", {"jobs": jobs, "t": dictionary(language)}
        )

    @app.get("/api/v1/openapi.json")
    def protected_openapi(user=Depends(admin)):
        return app.openapi()

    @app.get("/api/docs", response_class=HTMLResponse)
    def docs(request: Request, user=Depends(admin)):
        from fastapi.openapi.docs import get_swagger_ui_html

        response = get_swagger_ui_html(
            openapi_url="/api/v1/openapi.json",
            title="APM API",
            swagger_js_url="/static/vendor/swagger-ui-bundle.js",
            swagger_css_url="/static/vendor/swagger-ui.css",
            swagger_favicon_url="/static/favicon.svg",
        )
        return HTMLResponse(
            response.body.decode().replace("<script>", f'<script nonce="{request.state.nonce}">')
        )

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, session=Depends(db)):
        setup_needed = not session.scalar(select(User.id).limit(1))
        language = request.cookies.get("apm_language", config.default_language)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "t": dictionary(language),
                "language": language,
                "setup": setup_needed,
                "oidc": bool(config.oidc_issuer),
                "oidc_only": config.oidc_only,
            },
        )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return RedirectResponse("/ui/dashboard")

    @app.get("/ui/{page}", response_class=HTMLResponse)
    def ui(page: str, request: Request, session=Depends(db)):
        try:
            user = current(request, session)
        except HTTPException:
            return RedirectResponse("/login", status_code=303)
        if page not in (
            *SCHEMAS,
            "dashboard",
            "operations",
            "audit",
            "users",
            "imports",
            "security",
            "logs",
            "metrics",
        ):
            raise HTTPException(404)
        language = request.cookies.get("apm_language", user.language)
        return templates.TemplateResponse(
            request,
            "app.html",
            {
                "page": page,
                "user": user,
                "csrf": request.state.login.csrf,
                "t": dictionary(language),
                "language": language,
                "kinds": list(SCHEMAS),
                "admin_kinds": list(ADMIN_KINDS),
                "letsencrypt": config.acme_server.startswith(
                    (
                        "https://acme-v02.api.letsencrypt.org/",
                        "https://acme-staging-v02.api.letsencrypt.org/",
                    )
                ),
                "version": __version__,
            },
        )

    return app
