"""API router - aggregates all route modules."""

from fastapi import APIRouter
from backend.api import dashboard, funds, holdings, imports, nav, analysis

api_router = APIRouter(prefix="/api")

api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(funds.router, prefix="/funds", tags=["funds"])
api_router.include_router(holdings.router, prefix="/holdings", tags=["holdings"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(nav.router, prefix="/nav", tags=["nav"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
