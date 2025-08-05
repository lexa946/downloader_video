from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware
from pathlib import Path

from app.routers.service import router as service_router
from app.routers.front import router as front_router
from app.routers.user import router as user_router
from app.routers.new_front import router as new_front_router



app = FastAPI()

app.include_router(service_router)
app.include_router(user_router)
app.include_router(front_router)
app.include_router(new_front_router)

# Global favicon handler
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Global favicon handler"""
    # Try new frontend first
    new_favicon = Path(__file__).parent / "new_frontend" / "static" / "images" / "favicon.png"
    if new_favicon.exists():
        return FileResponse(new_favicon, media_type="image/png")
    
    # Fallback to old frontend
    old_favicon = Path(__file__).parent / "front" / "static" / "images" / "favicon.png"
    if old_favicon.exists():
        return FileResponse(old_favicon, media_type="image/png")
    
    # If no favicon found, return 404
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Favicon not found")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "PUT", "DELETE"],
    allow_headers=["*"],
)
