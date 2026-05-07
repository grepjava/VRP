import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from api.models import DemoGenerateRequestModel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/vrp/generate-demo")
async def generate_demo(request: DemoGenerateRequestModel):
    """Generate realistic demo data for a given city using OpenStreetMap geocoding."""
    try:
        from core.demo_generator import generate_demo_data
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, generate_demo_data, request.city, request.num_orders, request.num_technicians
        )
        return data
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Demo generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Demo generation failed — upstream geocoding service may be unavailable"
        )
