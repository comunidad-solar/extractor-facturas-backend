# api/main.py
# FastAPI app principal. Registra routers y configura CORS.
# Arrancar con: uvicorn api.main:app --reload --port 8000
#
# Modificado: 2026-02-27 | Rodrigo Costa

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.facturas  import router as facturas_router
from api.routes.cups      import router as cups_router
from api.routes.enviar    import router as enviar_router
from api.routes.contrato  import router as contrato_router
from api.routes.sesion    import router as sesion_router

app = FastAPI(
    title="Extractor Facturas Luz",
    description="API para extraer campos de facturas eléctricas españolas.",
    version="1.0.0",
)

# CORS — permite peticiones desde el frontend React
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,https://master.dsg7um3zm296x.amplifyapp.com").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(facturas_router)
app.include_router(cups_router)
app.include_router(enviar_router)
app.include_router(contrato_router)
app.include_router(sesion_router)


@app.get("/")
def root():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "extractor-facturas"}