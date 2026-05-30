"""Router 組み立てと re-export。"""

from ._shared import _dataclass_to_json, _job_to_api_data, _job_to_payload
from .api_v1 import api_v1_router
from .html import router
from .internal import router as internal_router
from .ws import router as ws_router
from .ws import ws_jobs

router.include_router(internal_router)
router.include_router(ws_router)
router.include_router(api_v1_router)

__all__ = ["router", "api_v1_router", "_job_to_payload", "_dataclass_to_json", "_job_to_api_data", "ws_jobs"]
