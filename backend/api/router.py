from fastapi import APIRouter

from api.v1 import (
    auth,
    document_types,
    documents,
    llm_logs,
    qa,
    sys_config,
    template_configs,
    templates,
)

# 创建 v1 版本路由
api_v1_router = APIRouter(prefix="/api/v1")

# 注册各模块路由
api_v1_router.include_router(auth.router)
api_v1_router.include_router(templates.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(sys_config.router)
api_v1_router.include_router(
    document_types.router, prefix="/document-types", tags=["document-types"]
)
api_v1_router.include_router(qa.router)
api_v1_router.include_router(llm_logs.router)
api_v1_router.include_router(template_configs.router)
