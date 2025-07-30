from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.routers.service import router as service_router
from app.routers.front import router as front_router
from app.routers.user import router as user_router



app = FastAPI()

app.include_router(service_router)
app.include_router(user_router)
app.include_router(front_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)
