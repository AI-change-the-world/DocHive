"""
智能体工具函数集合

提供各种查询和统计功能，支持 Function Calling
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import (
    ClassTemplate,
    Document,
    DocumentType,
    TemplateDocumentMapping,
)

# ==================== 工具函数定义 ====================


def to_iso(t):
    if t is None:
        return None

    if isinstance(t, int):
        # 自动判断是秒还是毫秒
        if t > 1e12:  # 毫秒级
            t = datetime.fromtimestamp(t / 1000)
        else:  # 秒级
            t = datetime.fromtimestamp(t)
        return t.isoformat()

    if hasattr(t, "isoformat"):
        return t.isoformat()

    return None


async def get_template_statistics(db: AsyncSession, template_id: int) -> Dict[str, Any]:
    """
    获取指定模板的统计信息

    包括：文档总数、各分类文档数量、文档类型分布等

    Args:
        db: 数据库会话
        template_id: 模板ID

    Returns:
        统计信息字典
    """
    try:
        # 1. 获取模板信息
        template_result = await db.execute(
            select(ClassTemplate).where(ClassTemplate.id == template_id)
        )
        template = template_result.scalar_one_or_none()

        if not template:
            return {
                "success": False,
                "error": f"模板ID {template_id} 不存在",
            }

        # 2. 获取该模板下的文档总数
        total_docs_result = await db.execute(
            select(func.count(TemplateDocumentMapping.document_id)).where(
                TemplateDocumentMapping.template_id == template_id
            )
        )
        total_docs = total_docs_result.scalar() or 0

        # 3. 获取各分类编码的文档数量分布
        class_code_stats_result = await db.execute(
            select(
                TemplateDocumentMapping.class_code,
                func.count(TemplateDocumentMapping.document_id).label("count"),
            )
            .where(TemplateDocumentMapping.template_id == template_id)
            .group_by(TemplateDocumentMapping.class_code)
        )
        class_code_stats = [
            {"class_code": row.class_code, "count": row.count}
            for row in class_code_stats_result.all()
        ]

        # 4. 获取文档类型分布（如果有）
        doc_type_stats_result = await db.execute(
            select(
                DocumentType.type_name,
                DocumentType.type_code,
                func.count(TemplateDocumentMapping.document_id).label("count"),
            )
            .join(
                TemplateDocumentMapping,
                and_(
                    TemplateDocumentMapping.template_id == template_id,
                    TemplateDocumentMapping.class_code.like(
                        func.concat("%", DocumentType.type_code, "%")
                    ),
                ),
            )
            .where(DocumentType.template_id == template_id)
            .group_by(DocumentType.type_name, DocumentType.type_code)
        )
        doc_type_stats = [
            {
                "type_name": row.type_name,
                "type_code": row.type_code,
                "count": row.count,
            }
            for row in doc_type_stats_result.all()
        ]

        # 5. 获取最近上传的文档（前5个）
        recent_docs_result = await db.execute(
            select(Document.id, Document.title, Document.upload_time)
            .join(
                TemplateDocumentMapping,
                TemplateDocumentMapping.document_id == Document.id,
            )
            .where(TemplateDocumentMapping.template_id == template_id)
            .order_by(Document.upload_time.desc())
            .limit(5)
        )
        recent_docs = [
            {
                "document_id": row.id,
                "title": row.title,
                "upload_time": to_iso(row.upload_time),
            }
            for row in recent_docs_result.all()
        ]

        return {
            "success": True,
            "template_name": template.name,
            "template_id": template_id,
            "total_documents": total_docs,
            "class_code_distribution": class_code_stats,
            "document_type_distribution": doc_type_stats,
            "recent_documents": recent_docs,
        }

    except Exception as e:
        logger.error(f"获取模板统计信息失败: {str(e)}")
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }


async def search_documents_by_classification(
    db: AsyncSession, template_id: int, class_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    根据分类编码搜索文档

    Args:
        db: 数据库会话
        template_id: 模板ID
        class_code: 分类编码（可选，不提供则返回所有）

    Returns:
        文档列表
    """
    try:
        query = (
            select(
                Document.id,
                Document.title,
                Document.original_filename,
                TemplateDocumentMapping.class_code,
                Document.upload_time,
            )
            .join(
                TemplateDocumentMapping,
                TemplateDocumentMapping.document_id == Document.id,
            )
            .where(TemplateDocumentMapping.template_id == template_id)
        )

        if class_code:
            query = query.where(TemplateDocumentMapping.class_code == class_code)

        query = query.order_by(Document.upload_time.desc()).limit(20)

        result = await db.execute(query)
        documents = [
            {
                "document_id": row.id,
                "title": row.title,
                "filename": row.original_filename,
                "class_code": row.class_code,
                "upload_time": to_iso(row.upload_time),
            }
            for row in result.all()
        ]

        return {
            "success": True,
            "template_id": template_id,
            "class_code": class_code,
            "total_found": len(documents),
            "documents": documents,
        }

    except Exception as e:
        logger.error(f"搜索文档失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}",
        }


async def get_document_types_info(db: AsyncSession, template_id: int) -> Dict[str, Any]:
    """
    获取模板下的所有文档类型定义

    Args:
        db: 数据库会话
        template_id: 模板ID

    Returns:
        文档类型列表及其字段配置
    """
    try:
        result = await db.execute(
            select(DocumentType).where(
                and_(
                    DocumentType.template_id == template_id,
                    DocumentType.is_active == True,
                )
            )
        )
        doc_types = result.scalars().all()

        types_info = []
        for doc_type in doc_types:
            types_info.append(
                {
                    "type_code": doc_type.type_code,
                    "type_name": doc_type.type_name,
                    "description": doc_type.description,
                }
            )

        return {
            "success": True,
            "template_id": template_id,
            "total_types": len(types_info),
            "document_types": types_info,
        }

    except Exception as e:
        logger.error(f"获取文档类型信息失败: {str(e)}")
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }


async def list_all_templates(db: AsyncSession) -> Dict[str, Any]:
    """
    列出所有可用的模板

    Args:
        db: 数据库会话

    Returns:
        模板列表
    """
    try:
        result = await db.execute(
            select(ClassTemplate).where(ClassTemplate.is_active == True)
        )
        templates = result.scalars().all()

        templates_info = []
        for template in templates:
            # 获取该模板下的文档数量
            count_result = await db.execute(
                select(func.count(TemplateDocumentMapping.document_id)).where(
                    TemplateDocumentMapping.template_id == template.id
                )
            )
            doc_count = count_result.scalar() or 0

            templates_info.append(
                {
                    "template_id": template.id,
                    "template_name": template.name,
                    "description": template.description,
                    "version": template.version,
                    "document_count": doc_count,
                }
            )

        return {
            "success": True,
            "total_templates": len(templates_info),
            "templates": templates_info,
        }

    except Exception as e:
        logger.error(f"列出模板失败: {str(e)}")
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }


# ==================== 工具注册表（OpenAI Function Calling 格式） ====================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_template_statistics",
            "description": "获取指定模板的统计信息，包括文档总数、分类分布、文档类型分布、最近上传的文档等",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "模板ID",
                    }
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents_by_classification",
            "description": "根据分类编码搜索文档，可以查找特定分类下的文档列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "模板ID",
                    },
                    "class_code": {
                        "type": "string",
                        "description": "分类编码，如果不提供则返回所有文档",
                    },
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_types_info",
            "description": "获取模板下的所有文档类型定义及其说明",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "模板ID",
                    }
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_templates",
            "description": "列出系统中所有可用的模板及其基本信息，包括模板名称、描述、版本、文档数量等",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# 工具函数映射表
TOOLS_MAP = {
    "get_template_statistics": get_template_statistics,
    "search_documents_by_classification": search_documents_by_classification,
    "get_document_types_info": get_document_types_info,
    "list_all_templates": list_all_templates,
}


# ==================== 工具调用执行器 ====================


async def execute_tool_call(
    tool_name: str, arguments: Dict[str, Any], db: AsyncSession
) -> Dict[str, Any]:
    """
    执行工具调用

    Args:
        tool_name: 工具名称
        arguments: 工具参数
        db: 数据库会话

    Returns:
        工具执行结果
    """
    if tool_name not in TOOLS_MAP:
        return {
            "success": False,
            "error": f"未知的工具: {tool_name}",
        }

    tool_function = TOOLS_MAP[tool_name]

    try:
        logger.info(f"执行工具: {tool_name}, 参数: {arguments}")
        result = await tool_function(db, **arguments)
        logger.info(f"工具执行成功: {tool_name}")
        return result
    except Exception as e:
        logger.error(f"执行工具 {tool_name} 失败: {str(e)}")
        return {
            "success": False,
            "error": f"工具执行失败: {str(e)}",
        }
