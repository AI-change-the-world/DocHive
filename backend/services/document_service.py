import json
from sqlalchemy import select
from typing import Any, AsyncGenerator, Optional, BinaryIO, List, Dict
from models.database_models import (
    ClassTemplateConfigs,
    Document,
    ClassTemplate,
    DocumentType,
    DocumentTypeField,
    TemplateDocumentMapping,
)
from schemas.api_schemas import DocumentCreate, DocumentUpdate, SSEEvent
from utils.storage import storage_client
from utils.parser import DocumentParser
import uuid
import time
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from utils.llm_client import llm_client
from loguru import logger
from typing_extensions import deprecated
from datetime import datetime

EXTRACT_FIELES_PROMPT = """
你是一名信息抽取专家。请从以下文档中提取指定字段的信息，并以 JSON 格式输出。

【字段定义】
{{field_definitions}}

每个字段包含以下信息：
- field_name：字段名（作为 JSON 的键）
- description：字段含义或提取说明
- field_type：字段类型（可为 text / date / array）

【输出要求】
1. 输出一个完整 JSON，键名与 field_name 对应。
2. 如果某个字段无法确定内容，请返回 null。
3. 各字段处理规范：
   - text：提取文中对应的文字内容。
   - date：识别并转换为 YYYY-MM-DD 格式。
   - array：提取多个相关项，以字符串数组形式返回。
4. 不要生成多余解释或说明，只输出 JSON。

【示例输出】
```
{
  "标题": "关于推进数字政务建设的若干意见",
  "发文单位": "国务院办公厅",
  "发文字号": "国办发〔2023〕12号",
  "发布日期": "2023-05-12"
}

【待提取文档内容】
{{document_content}}
"""


CODE_EXTRACTION_PROMPT = """
你是一个文本分析助理，用于从文档中提取业务编码信息。请仔细阅读以下业务编码配置：

JSON 配置：
{{JSON_CONFIG}}

说明：
1. level 表示编码层级，1 表示一级编码，2 表示二级编码。
2. name 是编码字段名称，description 是对该字段的简短描述。
3. code 是编码标识。
4. extraction_prompt（如果有）提供了可能值或匹配提示。
5. 如果 extraction_prompt 为 null，请根据文本内容直接提取对应值。

请你生成一个优化后的提取编码的指令模板（prompt），要求：
- 能明确告诉模型要提取哪些字段。
- 对每个字段提供提取规则或提示。
- 输出格式为 JSON 列表，示例：
[
  {"code":"YEAR", "value":"2025", "level":1},
  {"code":"REGION", "value":"JS", "level":2}
]
- 遇到无法提取的字段可以返回 null。
- 不要添加多余解释，直接生成可以直接用于调用模型的 prompt。

"""

TYPE_CLASSIFICATION_PROMPT = """
你是一个政府公文智能分类助手，请根据文档内容判断其所属的文档类型。

以下是文档类型定义表（type_code、type_name、description）：

{{type_code}}

请阅读以下文档内容，判断该文档最符合的类型，并输出结果。

要求：
1. 只能选择一个最合适的类型。
2. 输出格式为 JSON：
{
  "type_code": "XXX",
  "type_name": "XXX",
  "reason": "简要说明判断依据"
}

示例输入：
《关于印发〈市科技创新发展规划（2025-2030）〉的通知》

示例输出：
{
  "type_code": "GH",
  "type_name": "规划方案",
  "reason": "文中包含“发展规划”，属于计划类文件"
}

现在请判断以下文档的类型：

{{doc}}
"""


class DocumentService:
    """文档服务层"""

    @staticmethod
    async def upload_file_stream(
        db: AsyncSession,
        file_data: BinaryIO,
        filename: str,
        document_data: DocumentCreate,
        user_id: int,
    ) -> AsyncGenerator[str, Any]:
        """
        上传并解析文档（流式处理）
        """

        event = SSEEvent(event="process document content", data=None, id=None, done=False)

        file_extension = Path(filename).suffix
        object_name = f"{uuid.uuid4()}{file_extension}"

        # 1️⃣ 读取文件内容（只读一次）
        file_bytes = file_data.read()
        if hasattr(file_data, "seek"):
            file_data.seek(0)

        # 2️⃣ 模拟上传（此处省略实际上传）
        file_path = f"{object_name}"
        event.data = "[info] 上传文件成功"
        yield event.model_dump_json(ensure_ascii=False)

        # 3️⃣ 解析文本内容
        # ⚠️ 注意这里不要再 .read()，因为流已经读过，直接用 file_bytes
        doc = await DocumentParser.parse_file(file_bytes, file_extension)

        # 4️⃣ 获取模板
        template_id = document_data.template_id
        result = await db.execute(
            select(ClassTemplate).where(ClassTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            event.done = True
            event.data = "[error] 模板不存在"
            yield event.model_dump_json(ensure_ascii=False)
            return

        # 5️⃣ 获取文档类型
        doc_type_result = await db.execute(
            select(DocumentType).where(DocumentType.template_id == template_id)
        )
        doc_types = doc_type_result.scalars().all()

        if not doc_types:
            event.done = True
            event.data = "[error] 文档类型不存在"
            yield event.model_dump_json(ensure_ascii=False)
            return

        # 6️⃣ 获取模板的层级定义
        template_json_list: List[Dict[str, Any]] = getattr(template, "levels") or []

        # 7️⃣ 检查并生成编码提取提示
        class_template_config_result = await db.execute(
            select(ClassTemplateConfigs).where(
                ClassTemplateConfigs.template_id == template_id,
                ClassTemplateConfigs.config_name == "code_extraction_prompt",
            )
        )
        class_template_config = class_template_config_result.scalar_one_or_none()

        type_level = -1
        new_list = []
        for i in template_json_list:
            if i.get("is_doc_type", False):
                type_level = i.get("level", -1)
                continue
            new_list.append(i)

        if class_template_config:
            code_prompt = class_template_config.config_value
            event.data = "[info] 使用自定义的编码提取提示"
            yield event.model_dump_json(ensure_ascii=False)
        else:
            event.data = "[info] 重新构造编码提取提示"
            yield event.model_dump_json(ensure_ascii=False)

            prompt = CODE_EXTRACTION_PROMPT.replace(
                "{{JSON_CONFIG}}", json.dumps(new_list, ensure_ascii=False)
            )
            code_prompt = await llm_client.chat_completion(prompt, db=db)

            # 保存配置
            new_config = ClassTemplateConfigs(
                template_id=template_id,
                config_name="code_extraction_prompt",
                config_value=code_prompt,
            )
            db.add(new_config)
            await db.commit()

        # 8️⃣ 提取编码结果
        # 构造一个合适的提示消息
        prompt_message = str(code_prompt) + "\n\n以下为文档内容，请帮我提取：" + str(doc)
        code_json_result = await llm_client.extract_json_response(
            prompt_message,
            db=db,
        )
        # 确保code_json是一个列表
        if isinstance(code_json_result, dict):
            code_json: List[Dict[str, Any]] = [code_json_result]
        elif isinstance(code_json_result, list):
            code_json = code_json_result
        else:
            code_json = []
        
        logger.info("👓️ 编码结果：" + str(code_json))
        event.data = f"[info] 提取编码结果： {code_json}"
        yield event.model_dump_json(ensure_ascii=False)

        # 9️⃣ 提取文档类型
        type_list = [
            {
                "type_code": getattr(i, "type_code"),
                "type_name": getattr(i, "type_name"),
                "description": getattr(i, "description"),
            }
            for i in doc_types
        ]

        type_prompt = TYPE_CLASSIFICATION_PROMPT.replace(
            "{{type_code}}", json.dumps(type_list, ensure_ascii=False)
        ).replace("{{doc}}", doc)
        type_json = await llm_client.extract_json_response(type_prompt, db=db)
        logger.info("🩱 文档类型：" + str(type_json))
        event.data = f"[info] 文档类型： {type_json}"
        yield event.model_dump_json(ensure_ascii=False)

        # 10️⃣ 合并编码和分类结果
        type_value = type_json.get("type_code", "UNKNOWN") if isinstance(type_json, dict) else "UNKNOWN"
        type_json_into_code_json = {
            "code": "TYPE",
            "value": type_value,
            "level": type_level,
        }

        code_json.append(type_json_into_code_json)
        # 确保列表中的元素是字典类型
        dict_items = [item for item in code_json if isinstance(item, dict)]
        sorted_code_json = sorted(dict_items, key=lambda x: x.get("level", 0) if isinstance(x, dict) else 0)

        logger.info(
            "✅ 合并编码和分类结果： "
            + json.dumps(sorted_code_json, ensure_ascii=False)
        )

        # 11️⃣ 获取对应 DocumentType
        type_code = type_json.get("type_code", "UNKNOWN") if isinstance(type_json, dict) else "UNKNOWN"
        doc_type_result = await db.execute(
            select(DocumentType).where(
                DocumentType.type_code == type_code,
                DocumentType.template_id == template_id,
            )
        )
        doc_type = doc_type_result.scalar_one_or_none()

        # 12️⃣ 构造文件编码 TODO 有时候Sector无法正确识别，需要处理
        file_code_id_prefix = "-".join(
            str(i.get("value")) if isinstance(i, dict) and i.get("value") is not None else "UNKNOWN"
            for i in sorted_code_json
        )
        logger.info("✅ 编码结果：" + file_code_id_prefix)
        event.data = f"[info] 编码结果： {file_code_id_prefix}"
        yield event.model_dump_json(ensure_ascii=False)

        final_code_id = file_code_id_prefix + "-" + str(uuid.uuid4())

        # 13️⃣ 查询类型字段定义
        doc_type_fields_result = await db.execute(
            select(DocumentTypeField).where(
                DocumentTypeField.doc_type_id == (doc_type.id if doc_type else None)
            )
        )
        doc_type_fields = doc_type_fields_result.scalars().all()

        _extracted_data = {}

        if not doc_type_fields:
            event.data = "[info] 文档类型字段不存在,不提取内容"
            yield event.model_dump_json(ensure_ascii=False)
        else:
            event.data = "[info] 文档类型字段存在，开始提取内容"
            yield event.model_dump_json(ensure_ascii=False)

            _fields = [i.to_dict() for i in doc_type_fields]
            field_definitions = "\n".join(
                f"{i+1}. {f['field_name']}（{f['field_type']}）：{f['description']}"
                for i, f in enumerate(_fields)
            )
            prompt = EXTRACT_FIELES_PROMPT.replace(
                "{{field_definitions}}", field_definitions
            ).replace("{{document_content}}", doc)
            _extracted_data = await llm_client.extract_json_response(prompt, db=db)

        # 14️⃣ 保存文档信息
        document = Document(
            title=document_data.title,
            original_filename=filename,
            file_path=file_path,
            file_type=file_extension.lstrip("."),
            file_size=len(file_bytes),
            template_id=document_data.template_id,
            doc_metadata=document_data.metadata or {},
            uploader_id=user_id,
            content_text=doc,
            doc_type_id=doc_type.id if doc_type else 0,
        )

        db.add(document)
        await db.flush()  # 获取文档ID

        # 创建模板和文档的映射记录
        mapping = TemplateDocumentMapping(
            template_id=document_data.template_id,
            document_id=document.id,
            class_code=final_code_id,
            status="completed",
            processed_time=int(time.time()),
            extracted_data=json.dumps(_extracted_data, ensure_ascii=False) if _extracted_data else None,
        )
        db.add(mapping)
        
        await db.commit()

        # 将文档索引到Elasticsearch
        try:
            from utils.search_engine import search_client
            # 获取upload_time的值
            upload_time = getattr(document, "upload_time", None)
            
            document_data_for_es = {
                "document_id": document.id,
                "title": document.title,
                "content": doc,
                "summary": doc[:500] if len(doc) > 500 else doc,
                "template_id": document.template_id,
                "file_type": document.file_type,
                "upload_time": datetime.fromtimestamp(upload_time).isoformat() if upload_time else None,
                "metadata": _extracted_data  # 将extracted_data存储在metadata字段中
            }
            await search_client.index_document(document_data_for_es)
            logger.info(f"文档 {document.id} 已成功索引到Elasticsearch")
        except Exception as e:
            logger.error(f"文档 {document.id} 索引到Elasticsearch失败: {e}")

        event.data = "[info] 文档创建成功"
        event.done = True
        yield event.model_dump_json(ensure_ascii=False)

    @deprecated("使用upload_file_stream代替")
    @staticmethod
    async def upload_document(
        db: AsyncSession,
        file_data: BinaryIO,
        filename: str,
        document_data: DocumentCreate,
        user_id: int,
    ) -> Document:
        """
        上传并解析文档

        Args:
            db: 数据库会话
            file_data: 文件数据流
            filename: 原始文件名
            document_data: 文档创建数据
            user_id: 上传用户ID

        Returns:
            创建的文档记录
        """
        # 获取文件扩展名
        file_extension = Path(filename).suffix

        # 生成唯一对象名
        import datetime

        object_name = f"{datetime.datetime.utcnow().strftime('%Y/%m/%d')}/{uuid.uuid4()}{file_extension}"

        # 读取文件数据
        file_bytes = file_data.read()
        file_data.seek(0)

        # 上传到对象存储
        file_path = await storage_client.upload_file(
            file_data,
            object_name,
            content_type=DocumentService._get_content_type(file_extension),
        )

        # 创建文档记录
        document = Document(
            title=document_data.title,
            original_filename=filename,
            file_path=file_path,
            file_type=file_extension.lstrip("."),
            file_size=len(file_bytes),
            template_id=document_data.template_id,
            doc_metadata=document_data.metadata or {},
            uploader_id=user_id,
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        # 异步解析文档（实际应该使用 Celery 任务队列）
        # REPLACE: 流式接口更好
        try:
            await DocumentService.parse_document(
                db, int(getattr(document, "id")), file_bytes, file_extension
            )
        except Exception as e:
            # 更新映射表中的错误信息
            result = await db.execute(
                select(TemplateDocumentMapping).where(
                    TemplateDocumentMapping.document_id == getattr(document, "id")
                )
            )
            mapping = result.scalar_one_or_none()
            if mapping:
                setattr(mapping, "status", "failed")
                setattr(mapping, "error_message", str(e))
                await db.commit()
            else:
                # 如果映射表记录不存在，创建一个新的
                mapping = TemplateDocumentMapping(
                    template_id=document_data.template_id,
                    document_id=getattr(document, "id"),
                    status="failed",
                    error_message=str(e),
                )
                db.add(mapping)
                await db.commit()

        return document

    @deprecated("已弃用")
    @staticmethod
    async def parse_document(
        db: AsyncSession,
        document_id: int,
        file_data: bytes,
        file_extension: str,
    ):
        """解析文档内容"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return

        # 更新映射表状态为处理中
        result = await db.execute(
            select(TemplateDocumentMapping).where(
                TemplateDocumentMapping.document_id == document_id
            )
        )
        mapping = result.scalar_one_or_none()
        if mapping:
            setattr(mapping, "status", "processing")
            await db.commit()

        try:
            # 解析文本内容
            content_text = await DocumentParser.parse_file(file_data, file_extension)

            # 提取元信息
            metadata = DocumentParser.extract_metadata(file_data, file_extension)

            # 生成摘要（这里简化处理，实际应该调用 LLM）
            summary = content_text[:500] if len(content_text) > 500 else content_text

            # 更新文档
            setattr(document, "content_text", content_text)
            setattr(document, "summary", summary)
            # 合并 doc_metadata
            current_metadata = getattr(document, "doc_metadata") or {}
            current_metadata.update(metadata)
            setattr(document, "doc_metadata", current_metadata)
            
            await db.commit()

            # 更新映射表状态为完成
            if mapping:
                setattr(mapping, "status", "completed")
                setattr(mapping, "processed_time", int(time.time()))
                await db.commit()

        except Exception as e:
            # 更新映射表中的错误信息
            if mapping:
                setattr(mapping, "status", "failed")
                setattr(mapping, "error_message", str(e))
                await db.commit()
            raise

    @staticmethod
    async def get_document(db: AsyncSession, document_id: int) -> Optional[Document]:
        """获取文档"""
        result = await db.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        template_id: Optional[int] = None,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> tuple[list[Document], int]:
        """获取文档列表"""
        query = select(Document)
        count_query = select(Document)

        if template_id:
            query = query.where(Document.template_id == template_id)
            count_query = count_query.where(Document.template_id == template_id)

        if status:
            query = query.where(Document.status == status)
            count_query = count_query.where(Document.status == status)

        if user_id:
            query = query.where(Document.uploader_id == user_id)
            count_query = count_query.where(Document.uploader_id == user_id)

        query = query.order_by(Document.upload_time.desc()).offset(skip).limit(limit)

        result = await db.execute(query)
        documents = result.scalars().all()

        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        return list(documents), total

    @staticmethod
    async def update_document(
        db: AsyncSession,
        document_id: int,
        document_data: DocumentUpdate,
    ) -> Optional[Document]:
        """更新文档"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return None

        update_data = document_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(document, field, value)

        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def delete_document(db: AsyncSession, document_id: int) -> bool:
        """删除文档"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return False

        # 从对象存储删除文件
        file_path = getattr(document, "file_path")
        object_name = (
            file_path.split("/", 1)[1]
            if "/" in file_path
            else file_path
        )
        await storage_client.delete_file(object_name)

        # 从数据库删除
        await db.delete(document)
        await db.commit()
        return True

    @staticmethod
    async def get_download_url(db: AsyncSession, document_id: int) -> Optional[str]:
        """获取文档下载链接"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return None

        # 提取对象名
        file_path = getattr(document, "file_path")
        object_name = (
            file_path.split("/", 1)[1]
            if "/" in file_path
            else file_path
        )

        return storage_client.get_presigned_url(object_name)

    @staticmethod
    def _get_content_type(file_extension: str) -> str:
        """获取文件 MIME 类型"""
        content_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        return content_types.get(file_extension.lower(), "application/octet-stream")
