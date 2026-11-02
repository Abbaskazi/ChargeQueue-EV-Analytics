"""ChargeQueue FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router


app = FastAPI(
    title="ChargeQueue API",
    version="0.1.0",
    description=(
        "Backend API for the academic ChargeQueue project. It exposes the "
        "verified processed dataset, station history, occupied-port forecasts, "
        "and provisional congestion alerts."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)
