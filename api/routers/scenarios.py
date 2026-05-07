import json
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from api.models import SaveScenarioRequestModel

router = APIRouter()
logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "data" / "scenarios"
SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return re.sub(r'-+', '-', s).strip('-')[:60]


def _safe_scenario_path(slug: str) -> Path:
    safe = _slugify(slug)
    if not safe or safe != slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scenario name")
    path = (SCENARIOS_DIR / f"{safe}.json").resolve()
    try:
        path.relative_to(SCENARIOS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scenario name")
    return path


@router.post("/vrp/scenarios", status_code=status.HTTP_201_CREATED)
async def save_scenario(req: SaveScenarioRequestModel):
    """Save the current technicians and work orders as a named scenario."""
    slug = _slugify(req.name)
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scenario name")
    path = SCENARIOS_DIR / f"{slug}.json"
    if path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A scenario named '{slug}' already exists")
    payload = {
        "slug": slug,
        "name": req.name,
        "city": req.city,
        "source": req.source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tech_count": len(req.technicians),
        "order_count": len(req.work_orders),
        "technicians": req.technicians,
        "work_orders": req.work_orders,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Scenario saved: {slug} ({len(req.technicians)} techs, {len(req.work_orders)} orders)")
    return {"slug": slug, "name": req.name, "created_at": payload["created_at"]}


@router.get("/vrp/scenarios")
async def list_scenarios():
    """List all saved scenarios (metadata only)."""
    scenarios = []
    for f in sorted(SCENARIOS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            scenarios.append({
                "slug": data.get("slug", f.stem),
                "name": data.get("name", f.stem),
                "city": data.get("city", ""),
                "source": data.get("source", "manual"),
                "created_at": data.get("created_at", ""),
                "tech_count": data.get("tech_count", 0),
                "order_count": data.get("order_count", 0),
            })
        except Exception as e:
            logger.warning(f"Could not read scenario {f.name}: {e}")
    return scenarios


@router.get("/vrp/scenarios/{slug}")
async def load_scenario(slug: str):
    """Load a saved scenario including full technician and work order data."""
    path = _safe_scenario_path(slug)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scenario '{slug}' not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception(f"Could not read scenario {slug}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not read scenario")


@router.delete("/vrp/scenarios/{slug}", status_code=status.HTTP_200_OK)
async def delete_scenario(slug: str):
    """Delete a saved scenario."""
    path = _safe_scenario_path(slug)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scenario '{slug}' not found")
    path.unlink()
    logger.info(f"Scenario deleted: {slug}")
    return {"ok": True}
