from fastapi import FastAPI
from api.routes import router

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