"""FastAPI app entrypoint. No business logic — just app wiring."""

from fastapi import FastAPI

from api.routes import router

app = FastAPI(title="CAPA AI Assist")
app.include_router(router)
