from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dto.exceptions import RFC9457ErrorResponse
from fastapi.responses import JSONResponse
from src.claim.delivery import router as claim_router
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("vitera")

app = FastAPI(
    title="Vitera API",
    description="Hospital-side BPJS claim integrity engine",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claim_router)


@app.exception_handler(RFC9457ErrorResponse)
async def rfc9457_error_handler(request: Request, exc: RFC9457ErrorResponse):
    logger.error(
        f"RFC9457 Exception: {exc.__class__.__name__} | "
        f"Title: {exc.title} | "
        f"Status: {exc.status} | "
        f"Detail: {exc.detail} | "
        f"Instance: {exc.instance} | "
        f"Request Path: {request.url.path}"
    )

    return JSONResponse(
        status_code=exc.status,
        content={
            "title": exc.title,
            "status": exc.status,
            "detail": exc.detail,
            "instance": exc.instance,
            "type": exc.__class__.__name__,
        },
    )

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
