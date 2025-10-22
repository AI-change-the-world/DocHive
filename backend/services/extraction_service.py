from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List, Optional
import re
from models.database_models import ExtractionConfig, Document
from services.document_service import DocumentService
from utils.llm_client import llm_client


class ExtractionEngine:
    """信息抽取引擎"""
    
    @staticmethod
    async def extract_document_info(
        db: AsyncSession,
        document_id: int,
        config_id: int,
    ) -> Dict[str, Any]:
        """
        从文档中抽取结构化信息
        
        Args:
            db: 数据库会话
            document_id: 文档ID
            config_id: 抽取配置ID
        
        Returns:
            抽取结果
        """
        # 获取文档
        document = await DocumentService.get_document(db, document_id)
        if not document:
            raise ValueError("文档不存在")
        
        if not document.content_text:
            raise ValueError("文档尚未解析")
        
        # 获取抽取配置
        config = await ExtractionEngine.get_extraction_config(db, config_id)
        if not config:
            raise ValueError("抽取配置不存在")
        
        # 执行抽取
        extracted_data = {}
        success_fields = []
        failed_fields = []
        
        for field_config in config.extract_fields:
            field_name = field_config.get("name")
            try:
                value = await ExtractionEngine._extract_field(
                    document.content_text,
                    field_config,
                )
                extracted_data[field_name] = value
                success_fields.append(field_name)
            except Exception as e:
                failed_fields.append(field_name)
                extracted_data[field_name] = None
        
        # 更新文档抽取数据
        if document.extracted_data:
            document.extracted_data.update(extracted_data)
        else:
            document.extracted_data = extracted_data
        
        await db.commit()
        
        return {
            "document_id": document_id,
            "extracted_data": extracted_data,
            "success_fields": success_fields,
            "failed_fields": failed_fields,
        }
    
    @staticmethod
    async def _extract_field(
        content: str,
        field_config: Dict[str, Any],
    ) -> Any:
        """
        抽取单个字段
        
        Args:
            content: 文档内容
            field_config: 字段配置
        
        Returns:
            抽取的值
        """
        method = field_config.get("method", "llm")
        field_name = field_config.get("name")
        field_type = field_config.get("type", "text")
        
        if method == "regex":
            # 正则表达式抽取
            pattern = field_config.get("pattern")
            if not pattern:
                raise ValueError(f"正则抽取缺少 pattern 配置: {field_name}")
            
            match = re.search(pattern, content)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                return ExtractionEngine._convert_type(value, field_type)
            else:
                return None
        
        elif method == "llm":
            # LLM 抽取
            return await ExtractionEngine._llm_extract_field(
                content, field_name, field_type, field_config.get("prompt")
            )
        
        elif method == "rule":
            # 规则抽取（可扩展）
            return await ExtractionEngine._rule_extract_field(content, field_config)
        
        else:
            raise ValueError(f"不支持的抽取方法: {method}")
    
    @staticmethod
    async def _llm_extract_field(
        content: str,
        field_name: str,
        field_type: str,
        custom_prompt: Optional[str] = None,
    ) -> Any:
        """使用 LLM 抽取字段"""
        system_prompt = """你是一个专业的信息抽取专家。你的任务是从文档内容中准确提取指定的字段信息。

要求：
1. 仔细分析文档内容
2. 提取准确的信息
3. 如果找不到相关信息，返回 null
4. 返回结果必须是有效的 JSON 格式
5. 严格按照字段类型返回数据"""

        type_hints = {
            "text": "文本字符串",
            "number": "数值（整数或浮点数）",
            "array": "数组（JSON 数组格式）",
            "date": "日期（YYYY-MM-DD 格式）",
            "boolean": "布尔值（true 或 false）",
        }
        
        type_hint = type_hints.get(field_type, "文本")
        
        user_prompt = custom_prompt or f"""请从以下文档中提取「{field_name}」字段。

**字段类型**：{type_hint}

**文档内容**：
{content[:2000]}  

请返回 JSON 格式，格式如下：
{{
    "{field_name}": <提取的值或null>
}}

只返回 JSON，不要包含其他内容。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        try:
            result = await llm_client.extract_json_response(messages)
            value = result.get(field_name)
            return ExtractionEngine._convert_type(value, field_type)
        except Exception as e:
            return None
    
    @staticmethod
    async def _rule_extract_field(
        content: str,
        field_config: Dict[str, Any],
    ) -> Any:
        """基于规则抽取字段（可扩展自定义规则）"""
        # 这里可以实现各种自定义规则
        # 例如：根据关键词位置、段落结构等
        return None
    
    @staticmethod
    def _convert_type(value: Any, field_type: str) -> Any:
        """类型转换"""
        if value is None:
            return None
        
        try:
            if field_type == "number":
                return float(value) if "." in str(value) else int(value)
            elif field_type == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ["true", "1", "yes", "是"]
            elif field_type == "array":
                if isinstance(value, list):
                    return value
                return [value]
            else:
                return str(value)
        except:
            return value
    
    @staticmethod
    async def get_extraction_config(
        db: AsyncSession,
        config_id: int,
    ) -> Optional[ExtractionConfig]:
        """获取抽取配置"""
        result = await db.execute(
            select(ExtractionConfig).where(ExtractionConfig.id == config_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_extraction_configs(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        doc_type: Optional[str] = None,
    ) -> tuple[List[ExtractionConfig], int]:
        """获取抽取配置列表"""
        query = select(ExtractionConfig)
        count_query = select(ExtractionConfig)
        
        if doc_type:
            query = query.where(ExtractionConfig.doc_type == doc_type)
            count_query = count_query.where(ExtractionConfig.doc_type == doc_type)
        
        query = query.where(ExtractionConfig.is_active == True)
        count_query = count_query.where(ExtractionConfig.is_active == True)
        
        query = query.order_by(ExtractionConfig.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        configs = result.scalars().all()
        
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())
        
        return list(configs), total
    
    @staticmethod
    async def create_extraction_config(
        db: AsyncSession,
        name: str,
        doc_type: str,
        extract_fields: List[Dict[str, Any]],
    ) -> ExtractionConfig:
        """创建抽取配置"""
        config = ExtractionConfig(
            name=name,
            doc_type=doc_type,
            extract_fields=extract_fields,
        )
        
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config
