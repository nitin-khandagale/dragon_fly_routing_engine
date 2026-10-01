from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import router


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(
    title="DragonFly UTM Routing Engine",
    version="1.2",
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "dragonfly-routing-engine",
        "version": "1.2",
    }


app.mount(
    "/",
    StaticFiles(directory=STATIC_DIR, html=True),
    name="ui",
)