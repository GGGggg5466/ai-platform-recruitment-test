from fastapi import FastAPI
from app.api import router as api_router

app = FastAPI(title="IDP S+ Blueprint", version="0.1.0")
app.include_router(api_router, prefix="/v1")
