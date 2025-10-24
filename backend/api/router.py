from fastapi import APIRouter
from api.v1 import (
    auth,
    templates,
    documents,
    classification,
    extraction,
    numbering,
    search,
    config,
    document_types,
)

# 创建 v1 版本路由
api_v1_router = APIRouter(prefix="/api/v1")

# 注册各模块路由
api_v1_router.include_router(auth.router)
api_v1_router.include_router(templates.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(classification.router)
api_v1_router.include_router(extraction.router)
api_v1_router.include_router(numbering.router)
api_v1_router.include_router(search.router)
api_v1_router.include_router(config.router)
api_v1_router.include_router(document_types.router, prefix="/document-types", tags=["document-types"])
