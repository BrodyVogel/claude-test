import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import init_db
from routers import companies, indicators, alerts, dashboard

app = FastAPI(title="Coverage Monitoring App", version="0.1.0")

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Include routers
app.include_router(companies.router)
app.include_router(indicators.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/onboard", response_class=HTMLResponse)
async def onboard(request: Request):
    return templates.TemplateResponse("onboard.html", {"request": request})


@app.get("/company/{company_id}", response_class=HTMLResponse)
async def company_detail(request: Request, company_id: int):
    return templates.TemplateResponse("company.html", {"request": request, "company_id": company_id})
