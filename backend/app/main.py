"""
Application entry point: creates the FastAPI app, wires up middleware and
routers, and serves the static frontend.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CLAVE_SECRETA_DE_DESARROLLO, settings
from app.database import create_db_and_tables
from app.routers import auth, candidaturas, cv_base


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()

    if not settings.debug and settings.secret_key == CLAVE_SECRETA_DE_DESARROLLO:
        print(
            "WARNING: running with debug=False but SECRET_KEY still has its "
            "default development value. Set a unique, secret value in the "
            "deployment environment before exposing this instance publicly."
        )

    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

# CORS is intentionally open to every origin. This is safe because
# authentication is stateless (a JWT sent in the Authorization header,
# never a cookie): a request without a valid token gets 401 regardless of
# its origin, so there is no CSRF surface to protect against. It is also
# a practical necessity — each unpacked install of the Chrome extension
# gets its own extension id (chrome-extension://<id>), so there is no
# fixed set of origins to allow-list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(candidaturas.router)
app.include_router(cv_base.router)

# Served from the same origin as the API, so the panel's fetch() calls
# never need to deal with CORS themselves.
app.mount("/panel", StaticFiles(directory="frontend", html=True), name="panel")


@app.get("/health")
def health():
    """Health check used by the hosting platform's readiness probes."""
    return {"status": "ok", "app": settings.app_name}
