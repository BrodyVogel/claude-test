"""Pydantic models for request/response validation."""

from pydantic import BaseModel
from typing import Optional


class CompanyCreate(BaseModel):
    name: str
    ticker: str
    exchange: Optional[str] = None
    currency: str
    current_rating: str
    current_price: Optional[float] = None
    blended_price_target: float
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    current_rating: Optional[str] = None
    current_price: Optional[float] = None
    blended_price_target: Optional[float] = None
    notes: Optional[str] = None


class ScenarioCreate(BaseModel):
    name: str
    raw_weight: Optional[float] = None
    effective_weight: Optional[float] = None
    implied_price: float
    contribution: Optional[float] = None
    fy_revenue: Optional[str] = None
    fy_ebitda: Optional[str] = None
    fy_eps: Optional[str] = None
    fy_fcf: Optional[str] = None
    narrative_summary: Optional[str] = None
    trigger_conditions: Optional[str] = None
    sort_order: Optional[int] = None


class ScenarioUpdate(BaseModel):
    name: Optional[str] = None
    raw_weight: Optional[float] = None
    effective_weight: Optional[float] = None
    implied_price: Optional[float] = None
    contribution: Optional[float] = None
    fy_revenue: Optional[str] = None
    fy_ebitda: Optional[str] = None
    fy_eps: Optional[str] = None
    fy_fcf: Optional[str] = None
    narrative_summary: Optional[str] = None
    trigger_conditions: Optional[str] = None
    sort_order: Optional[int] = None


class IndicatorCreate(BaseModel):
    name: str
    current_value: Optional[str] = None
    current_value_numeric: Optional[float] = None
    bear_threshold: Optional[str] = None
    bear_threshold_numeric: Optional[float] = None
    bull_threshold: Optional[str] = None
    bull_threshold_numeric: Optional[float] = None
    check_frequency: str
    data_source: str
    added_from: Optional[str] = None
    is_shared: Optional[int] = 0
    shared_indicator_group: Optional[str] = None
    status: Optional[str] = "green"


class IndicatorUpdate(BaseModel):
    name: Optional[str] = None
    current_value: Optional[str] = None
    current_value_numeric: Optional[float] = None
    bear_threshold: Optional[str] = None
    bear_threshold_numeric: Optional[float] = None
    bull_threshold: Optional[str] = None
    bull_threshold_numeric: Optional[float] = None
    check_frequency: Optional[str] = None
    data_source: Optional[str] = None
    added_from: Optional[str] = None
    is_shared: Optional[int] = None
    shared_indicator_group: Optional[str] = None
    status: Optional[str] = None


class ReadingCreate(BaseModel):
    value_text: str
    value_numeric: Optional[float] = None
    source_url: Optional[str] = None
    source_snippet: Optional[str] = None
    checked_at: str
    status_at_reading: Optional[str] = None
    notes: Optional[str] = None
