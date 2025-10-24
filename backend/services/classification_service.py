from sqlalchemy.orm import Session
from typing import Dict, Optional, Any
from models.database_models import Document, ClassTemplate, DocumentType
from services.template_service import TemplateService
from services.document_service import DocumentService
from services.document_type_service import DocumentTypeService
from utils.llm_client import llm_client
from sqlalchemy.ext.asyncio import AsyncSession
import json


class ClassificationEngine:
    """智能分类引擎"""
    
    @staticmethod
    async def classify_document(
        db: AsyncSession,
        document_id: int,
        template_id: int,
        force_reclassify: bool = False,
    ) -> Dict[str, Any]:
        """
        对文档进行智能分类
        
        Args:
            db: 数据库会话
            document_id: 文档ID
            template_id: 分类模板ID
            force_reclassify: 是否强制重新分类
        
        Returns:
            分类结果字典
        """
        # 获取文档
        document = await DocumentService.get_document(db, document_id)
        if not document:
            raise ValueError("文档不存在")
        
        # 检查是否已分类
        if document.class_path and not force_reclassify:
            return {
                "document_id": document_id,
                "class_path": document.class_path,
                "class_code": document.class_code,
                "status": "already_classified",
            }
        
        # 获取分类模板
        template = await TemplateService.get_template(db, template_id)
        if not template:
            raise ValueError("分类模板不存在")
        
        # 检查文档是否已解析
        if not document.content_text:
            raise ValueError("文档尚未解析，无法进行分类")
        
        # 使用 LLM 进行分类
        class_path = await ClassificationEngine._llm_classify(
            document.content_text,
            document.summary or document.content_text[:500],
            template.levels,
            document.title,
        )
        
        # 识别文档类型（从 is_doc_type=True 的层级）
        doc_type_id = await ClassificationEngine._identify_document_type(
            db, template_id, template.levels, class_path
        )
        
        # 更新文档分类信息
        document.class_path = class_path
        document.template_id = template_id
        document.doc_type_id = doc_type_id
        
        await db.commit()
        await db.refresh(document)
        
        return {
            "document_id": document_id,
            "class_path": class_path,
            "class_code": document.class_code,
            "confidence": 0.85,  # 简化处理，实际应该由LLM返回
            "status": "success",
        }
    
    @staticmethod
    async def _llm_classify(
        content: str,
        summary: str,
        template_levels: list,
        title: str,
    ) -> Dict[str, str]:
        """
        使用 LLM 进行文档分类
        
        Args:
            content: 文档完整内容
            summary: 文档摘要
            template_levels: 模板层级定义
            title: 文档标题
        
        Returns:
            分类路径字典，如 {"年份": "2025", "部门": "研发部", ...}
        """
        # 构建层级说明
        levels_description = "\n".join(
            [f"{level['level']}. {level['name']}: {level.get('description', '无描述')}" 
             for level in template_levels]
        )
        
        # 构建 Prompt
        system_prompt = """你是一个专业的文档分类专家。你的任务是根据提供的分类模板和文档内容，为文档确定准确的分类路径。

请仔细分析文档内容，并严格按照模板层级结构返回分类结果。

要求：
1. 返回结果必须是有效的 JSON 格式
2. JSON 键名必须与模板层级名称完全一致
3. 每个层级都必须有明确的分类值
4. 如果无法确定某个层级，返回 "未分类"
5. 分类值应简洁明确，不要包含冗余信息"""

        user_prompt = f"""请对以下文档进行分类：

**文档标题**：{title}

**文档摘要**：
{summary}

**分类模板层级**：
{levels_description}

请严格按照模板层级，返回 JSON 格式的分类结果。

示例格式：
{{
    "年份": "2025",
    "地点": "上海",
    "部门": "研发部",
    "条线": "技术研发",
    "类型": "技术报告"
}}

请直接返回 JSON，不要包含其他内容。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        try:
            # 调用 LLM
            result = await llm_client.extract_json_response(messages)
            
            # 验证结果包含所有必需层级
            expected_keys = {level['name'] for level in template_levels}
            result_keys = set(result.keys())
            
            # 补充缺失的层级
            for key in expected_keys - result_keys:
                result[key] = "未分类"
            
            # 移除多余的层级
            for key in result_keys - expected_keys:
                del result[key]
            
            return result
        
        except Exception as e:
            # 分类失败时返回默认值
            return {level['name']: "未分类" for level in template_levels}
    
    @staticmethod
    async def _identify_document_type(
        db: AsyncSession,
        template_id: int,
        template_levels: list,
        class_path: Dict[str, str]
    ) -> Optional[int]:
        """
        识别文档类型
        
        从模板中找到 is_doc_type=True 的层级，根据 class_path 中对应的值，
        查找或创建 DocumentType。
        
        Args:
            db: 数据库会话
            template_id: 模板ID
            template_levels: 模板层级定义
            class_path: 分类路径
            
        Returns:
            文档类型ID，如果不存在则返回None
        """
        # 找到 is_doc_type=True 的层级
        doc_type_level = None
        for level in template_levels:
            if level.get('is_doc_type'):
                doc_type_level = level
                break
        
        if not doc_type_level:
            return None
        
        # 从 class_path 中获取类型名称
        level_name = doc_type_level['name']
        type_name = class_path.get(level_name)
        
        if not type_name or type_name == "未分类":
            return None
        
        # 生成 type_code（类型名转拼音大写）
        from pypinyin import lazy_pinyin
        type_code = '_'.join(lazy_pinyin(type_name)).upper()
        
        # 查找或创建 DocumentType
        doc_type = DocumentTypeService.get_document_type_by_code(
            db, template_id, type_code
        )
        
        if not doc_type:
            # 自动创建
            from schemas.api_schemas import DocumentTypeCreate
            doc_type_data = DocumentTypeCreate(
                template_id=template_id,
                type_code=type_code,
                type_name=type_name,
                description=f"自动创建的文档类型：{type_name}",
                extraction_prompt=doc_type_level.get('extraction_prompt'),
            )
            doc_type = DocumentTypeService.create_document_type(db, doc_type_data)
        
        return doc_type.id
    
    @staticmethod
    async def batch_classify_documents(
        db: AsyncSession,
        document_ids: list[int],
        template_id: int,
    ) -> list[Dict[str, Any]]:
        """
        批量分类文档
        
        Args:
            db: 数据库会话
            document_ids: 文档ID列表
            template_id: 分类模板ID
        
        Returns:
            分类结果列表
        """
        results = []
        
        for doc_id in document_ids:
            try:
                result = await ClassificationEngine.classify_document(
                    db, doc_id, template_id, force_reclassify=False
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "document_id": doc_id,
                    "status": "failed",
                    "error": str(e),
                })
        
        return results
