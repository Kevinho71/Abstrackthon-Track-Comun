import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.channels import webhook
from app.channels.evolution import EvolutionClient
from app.db import init_db, make_engine, make_session_factory
from app.web import routes

SESSION_DAYS = 30


def create_app(
    database_url: str | None = None,
    validate: bool = True,
    evolution: EvolutionClient | None = None,
) -> FastAPI:
    """`evolution` permite inyectar un cliente falso en las pruebas."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if validate:
            config.validate()
        engine = make_engine(database_url or config.DATABASE_URL)
        init_db(engine)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        owns_client = evolution is None and bool(config.EVOLUTION_URL)
        app.state.evolution = evolution or (
            EvolutionClient(config.EVOLUTION_URL, config.EVOLUTION_API_KEY) if owns_client else None
        )
        yield
        if owns_client:
            await app.state.evolution.aclose()
        engine.dispose()

    app = FastAPI(title="Agente de seguimiento de chats", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.SESSION_SECRET or "solo-para-pruebas-sin-validar",
        max_age=SESSION_DAYS * 24 * 3600,
        same_site="lax",
        https_only=config.PUBLIC_URL.startswith("https://"),
    )

    @app.exception_handler(routes.NotLoggedIn)
    async def _not_logged_in(request: Request, exc: routes.NotLoggedIn):
        return RedirectResponse("/login", status_code=303)

    app.include_router(webhook.router)
    app.include_router(routes.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    return app


def app_factory() -> FastAPI:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # evita registrar claves en las URLs
    return create_app()


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app_factory(), host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
