import uvicorn
import uvloop
import asyncio

from app.main import app

if __name__ == "__main__":
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    uvicorn.run(app, host="127.0.0.1", port=8000)

