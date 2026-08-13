from pathlib import Path
import traceback
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from backend import (
    run_travel_agent,
    resume_travel_agent,
)


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="TRAVEL.io",
    description="LangGraph Multi-Agent Travel Planner with FastAPI",
    version="1.0.0",
)


# ============================================================
# STATIC FILES
# ============================================================

app.mount(
    "/static",
    StaticFiles(
        directory=str(BASE_DIR / "static")
    ),
    name="static",
)


# ============================================================
# HTML TEMPLATES
# ============================================================

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)


# ============================================================
# REQUEST MODELS
# ============================================================

class TravelRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="User's travel query",
    )

    thread_id: str | None = Field(
        default=None,
        description="Optional conversation thread ID",
    )


class ApprovalRequest(BaseModel):
    thread_id: str = Field(
        ...,
        min_length=1,
        description="LangGraph conversation thread ID",
    )

    approved: bool = Field(
        ...,
        description="Whether the human approved the draft",
    )

    feedback: str = Field(
        default="",
        description="Optional human revision feedback",
    )


# ============================================================
# HOME PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request
        },
    )


# ============================================================
# START TRAVEL WORKFLOW
# ============================================================

@app.post("/api/travel")
def travel(request: TravelRequest):
    try:
        result = run_travel_agent(
            user_input=request.message,
            thread_id=request.thread_id,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
            },
        )


# ============================================================
# HUMAN APPROVAL / REVISION
# ============================================================

@app.post("/api/travel/approve")
def approve_travel(request: ApprovalRequest):
    try:
        result = resume_travel_agent(
            thread_id=request.thread_id,
            approved=request.approved,
            feedback=request.feedback,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
            },
        )


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )