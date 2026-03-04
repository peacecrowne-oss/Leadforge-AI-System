from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from core.logging import LoggingMiddleware, configure_logging
from db.sqlite import db_init
from routes.auth import router as auth_router
from routes.leads import router
from routes.system import router as system_router

# Configure logging before anything else so startup messages are captured.
configure_logging()

app = FastAPI()

origins = [
    "http://localhost:5173",
    "http://localhost:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# LoggingMiddleware registered last → becomes outermost user middleware,
# wrapping CORSMiddleware. Measures full request duration and stamps
# X-Request-Id on all responses including error responses.
app.add_middleware(LoggingMiddleware)

# Global exception handlers — must be registered before routes.
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Ensure DB tables exist on startup.
db_init()

# Register routes.
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(router)
