from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.routers.service import router as service_router
from app.routers.user import router as user_router
from app.routers.front import router as new_front_router



app = FastAPI()

app.include_router(service_router)
app.include_router(user_router)
app.include_router(new_front_router)
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")




app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)
