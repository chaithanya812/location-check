"""HTTP API. Run from the backend folder with:  uvicorn app.main:app --reload

Endpoints are plain `def` (not `async def`) on purpose: `requests` is a
blocking library, and FastAPI runs plain `def` endpoints in a thread pool, so
one slow data source does not freeze the server for everyone else.
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from . import db, sources
from .scoring import RULES, Fact, score_facts


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # creates the tables on first start
    yield


app = FastAPI(title="Location Check", lifespan=lifespan)


class AssessmentIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    address: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)

    @field_validator("label", "address")
    @classmethod
    def strip_blank(cls, v):
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def address_or_coordinates(self):
        if self.label is None:
            raise ValueError("label is required")
        has_coords = self.lat is not None and self.lon is not None
        if (self.lat is None) != (self.lon is None):
            raise ValueError("give both latitude and longitude, or neither")
        if not self.address and not has_coords:
            raise ValueError("give an address or a latitude and longitude")
        return self


def run_assessment(assessment: dict) -> None:
    """Locate the point, fetch every fact, score it, and save it as a new run."""
    if assessment["input_lat"] is not None:
        location = {"lat": assessment["input_lat"], "lon": assessment["input_lon"]}
    else:
        found, error = sources.geocode(assessment["address"])
        location = found if found else {"error": error}

    if "error" in location:
        # Without coordinates no other source can be asked; every factor is
        # unavailable, and the assessment is still saved so the user sees why.
        facts = {rule.name: Fact(error=f"skipped, location unknown ({location['error']})") for rule in RULES}
    else:
        facts = sources.fetch_all_facts(location["lat"], location["lon"])

    db.save_run(assessment["id"], location, score_facts(facts))


@app.post("/api/assessments", status_code=201)
def create_assessment(body: AssessmentIn):
    # If both are given, the coordinates win and the address is kept as a note.
    use_coords = body.lat is not None
    assessment_id = db.create_assessment(
        body.label, body.address,
        body.lat if use_coords else None, body.lon if use_coords else None,
    )
    run_assessment(db.get_assessment(assessment_id))
    return db.get_assessment(assessment_id)


@app.get("/api/assessments")
def list_assessments():
    return db.list_assessments()


@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: int):
    assessment = db.get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return assessment


@app.post("/api/assessments/{assessment_id}/retry")
def retry_assessment(assessment_id: int):
    """Optional feature: fetch again. The earlier runs are kept, not overwritten."""
    assessment = db.get_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    run_assessment(assessment)
    return db.get_assessment(assessment_id)


@app.get("/api/rules")
def get_rules():
    """The scoring rules, so the frontend can show them without copying them."""
    return [
        {"name": r.name, "label": r.label, "source": r.source,
         "max_points": r.max_points, "rule": r.description}
        for r in RULES
    ]
