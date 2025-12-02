"""
查询写作模板工具

根据query查询写作模板，为文档润色提供参考样本
写作模板是用户上传的优秀文章，每篇文章对应一个主题（可重复）
"""

from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import and_, or_, select

from core.tools.base import ToolContext, tool


@tool(
    name="search_writing_templates",
    description="""
    根据query查询写作模板库，查找与查询主题相关的优秀写作样本。
    写作模板是用户上传的优质文章，用于为后续文档润色提供参考。
    支持按主题、标签、关键词等多维度检索。
    适用于文档润色、风格参考、结构借鉴等场景。
    """,
    parameters={
        "query": {
            "type": "string",
            "description": "查询文本，描述需要的写作风格或主题",
        },
        "template_id": {
            "type": "integer",
            "description": "模板ID，用于限定检索范围",
        },
        "theme": {
            "type": "string",
            "description": "主题过滤（可选），如：报告、方案、总结等",
            "default": None,
        },
        "top_k": {
            "type": "integer",
            "description": "返回模板数量，默认3",
            "default": 3,
        },
    },
    required=["query", "template_id"],
    category="retrieval",
    tags=["检索", "写作模板", "文档润色", "参考样本"],
    validation_mode="loose",  # 宽松模式，查不到也不算失败
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "templates": {
            "type": "array",
            "description": "检索到的写作模板列表",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "模板ID"},
                    "title": {"type": "string", "description": "模板标题"},
                    "theme": {"type": "string", "description": "主题"},
                    "content": {"type": "string", "description": "模板内容"},
                    "tags": {
                        "type": "array",
                        "description": "标签列表",
                        "items": {"type": "string"},
                    },
                    "word_count": {"type": "integer", "description": "字数"},
                },
            },
        },
        "count": {"type": "integer", "description": "检索到的模板数量"},
        "error": {"type": "string", "description": "错误信息（仅在失败时返回）"},
    },
)
async def search_writing_templates(
    ctx: ToolContext,
    query: str,
    template_id: int,
    theme: str = None,
    top_k: int = 3,
) -> Dict[str, Any]:
    """
    查询写作模板工具

    Args:
        ctx: 工具上下文
        query: 查询文本
        template_id: 模板ID
        theme: 主题过滤
        top_k: 返回数量

    Returns:
        {
            "success": bool,
            "templates": List[Dict],  # 写作模板列表
            "count": int
        }
    """
    from models.database_models import WritingTemplate

    db = ctx.db

    try:
        # 构建查询条件
        stmt = select(WritingTemplate).where(
            and_(
                WritingTemplate.template_id == template_id,
                WritingTemplate.is_active == True,
            )
        )

        # 主题过滤
        if theme:
            stmt = stmt.where(WritingTemplate.theme.ilike(f"%{theme}%"))

        # 关键词匹配（简单实现：标题或标签包含query的关键词）
        if query and query.strip():
            # 简单的关键词分词（按空格）
            keywords = [k.strip() for k in query.split() if k.strip()]
            if keywords:
                # 匹配标题或标签
                conditions = []
                for keyword in keywords[:5]:  # 最多取前5个关键词
                    conditions.append(
                        WritingTemplate.title.ilike(f"%{keyword}%"))
                    conditions.append(
                        WritingTemplate.tags.ilike(f"%{keyword}%"))
                    conditions.append(
                        WritingTemplate.description.ilike(f"%{keyword}%"))

                if conditions:
                    stmt = stmt.where(or_(*conditions))

        # 排序：优先按创建时间倒序
        stmt = stmt.order_by(WritingTemplate.created_at.desc())

        # 限制数量
        stmt = stmt.limit(top_k)

        result = await db.execute(stmt)
        templates_db = result.scalars().all()

        # 转换为输出格式
        templates = []
        for tpl in templates_db:
            templates.append(
                {
                    "id": tpl.id,
                    "title": tpl.title,
                    "theme": tpl.theme,
                    "content": tpl.content,
                    "tags": tpl.tags_list if hasattr(tpl, "tags_list") else [],
                    "word_count": len(tpl.content) if tpl.content else 0,
                    "description": getattr(tpl, "description", ""),
                }
            )

        logger.info(f"✅ 查询写作模板成功: query={query}, 找到{len(templates)}个模板")

        return {
            "success": True,
            "templates": templates,
            "count": len(templates),
        }

    except Exception as e:
        import traceback

        logger.error(f"❌ 查询写作模板失败: {e}")
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": str(e),
            "templates": [],
            "count": 0,
        }
