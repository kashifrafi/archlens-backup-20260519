from fastapi import APIRouter, HTTPException
from app.models.schemas import AnalyzeRequest, DiagramAnalysisResponse
from app.services.diagram_analyzer import analyze_diagram
import asyncio
from functools import partial

router = APIRouter()


@router.post("/analyze", response_model=DiagramAnalysisResponse)
async def analyze_architecture_diagram(request: AnalyzeRequest):
    """
    Analyze an architecture diagram.
    Accepts either:
      - image_base64 (PNG/JPG/WEBP/SVG, base64-encoded), or
      - drawio_xml (raw .drawio / .xml mxfile content)
    Returns extracted components with cloud service mappings.
    """
    if not request.image_base64 and not request.drawio_xml:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'image_base64' or 'drawio_xml'.",
        )
    try:
        # Run the blocking LLM call in a thread so it doesn't block the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                analyze_diagram,
                image_base64=request.image_base64,
                mime_type=request.mime_type,
                drawio_xml=request.drawio_xml,
                source_filename=request.source_filename,
                user_context=request.user_context,
            ),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
