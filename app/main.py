import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import config
from app.channels import webhook
from app.db import init_db, make_engine, make_session_factory


def create_app(database_url: str | None = None, validate: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if validate:
            config.validate()
        engine = make_engine(database_url or config.DATABASE_URL)
        init_db(engine)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Agente de seguimiento de chats", lifespan=lifespan)
    app.include_router(webhook.router)

    @app.get("/health")
    def health():
        return {"ok": True}

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
