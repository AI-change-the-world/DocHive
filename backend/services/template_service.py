import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import ClassTemplate, ClassTemplateConfigs, DocumentType
from schemas.api_schemas import (
    ClassTemplateCreate,
    ClassTemplateUpdate,
    DocumentTypeCreate,
    SSEEvent,
    TemplateSelection,
)
from utils.llm_client import get_llm_client


class TemplateService:
    """分类模板服务层"""

    @staticmethod
    async def create_template_stream(
        db: AsyncSession, template_data: ClassTemplateCreate, creator_id: int
    ) -> AsyncGenerator[str, None]:
        """创建分类模板(流式)"""
        task_id = f"template_create_{int(time.time() * 1000)}"
        template: Optional[ClassTemplate] = None

        try:
            # 1. 开始创建模板
            yield SSEEvent(
                event="stage_start",
                data={"stage": "create_template", "message": "开始创建模板..."},
                id=task_id,
            ).model_dump_json()
            await asyncio.sleep(0.1)

            levels_data = [level.model_dump() for level in template_data.levels]

            template = ClassTemplate(
                name=template_data.name,
                description=template_data.description,
                levels=levels_data,
                version=template_data.version,
                creator_id=creator_id,
            )

            db.add(template)
            await db.commit()
            await db.refresh(template)

            yield SSEEvent(
                event="stage_complete",
                data={
                    "stage": "create_template",
                    "message": "模板基础信息创建成功",
                    "template_id": template.id,
                },
                id=task_id,
            ).model_dump_json()
            await asyncio.sleep(0.1)

            # 2. 生成层级值域选项
            try:
                async for event in TemplateService._generate_level_options_stream(
                    db, template, levels_data, task_id
                ):
                    yield event
            except Exception as e:
                logger.error(f"生成层级值域选项失败: {e}")
                # 回滚模板创建
                await db.delete(template)
                await db.commit()
                yield SSEEvent(
                    event="error",
                    data={
                        "stage": "generate_options",
                        "message": f"生成层级选项失败: {str(e)}",
                    },
                    id=task_id,
                    done=True,
                ).model_dump_json()
                return

            # 3. 自动处理文档类型层级
            try:
                async for event in TemplateService._process_doc_type_level_stream(
                    db, template, task_id
                ):
                    yield event
            except Exception as e:
                logger.error(f"处理文档类型失败: {e}")
                # 回滚模板创建
                await db.delete(template)
                await db.commit()
                yield SSEEvent(
                    event="error",
                    data={
                        "stage": "process_doc_type",
                        "message": f"处理文档类型失败: {str(e)}",
                    },
                    id=task_id,
                    done=True,
                ).model_dump_json()
                return

            await asyncio.sleep(0.5)

            # 4. 完成
            yield SSEEvent(
                event="complete",
                data={
                    "message": "模板创建成功",
                    "template_id": template.id,
                    "template_name": template.name,
                },
                id=task_id,
                done=True,
            ).model_dump_json()

        except Exception as e:
            logger.error(f"创建模板失败: {e}")
            # 如果模板已创建,回滚
            if template:
                try:
                    await db.delete(template)
                    await db.commit()
                except Exception:
                    await db.rollback()

            yield SSEEvent(
                event="error",
                data={"stage": "create_template", "message": f"创建模板失败: {str(e)}"},
                id=task_id,
                done=True,
            ).model_dump_json()

    @staticmethod
    async def get_template(
        db: AsyncSession, template_id: int
    ) -> Optional[ClassTemplate]:
        """获取单个模板"""
        result = await db.execute(
            select(ClassTemplate).filter(ClassTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_templates(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        is_active: Optional[bool] = None,
    ) -> tuple[List[ClassTemplate], int]:
        """获取模板列表"""
        query = select(ClassTemplate)

        if is_active is not None:
            query = query.filter(ClassTemplate.is_active == is_active)

        # 获取总数
        count_result = await db.execute(
            select(ClassTemplate).filter(*query.whereclause.clauses)
            if query.whereclause is not None
            else select(ClassTemplate)
        )
        total = len(count_result.all())

        # 获取分页数据
        query = (
            query.order_by(ClassTemplate.created_at.desc()).offset(skip).limit(limit)
        )
        result = await db.execute(query)
        templates = list(result.scalars().all())

        return templates, total

    @staticmethod
    async def list_all_templates(
        db: AsyncSession,
    ) -> List[TemplateSelection]:
        """获取所有模板列表"""

        templates = await db.execute(
            select(ClassTemplate.id, ClassTemplate.name).where(
                ClassTemplate.is_active == 1
            )
        )
        template_selections = []
        for template in templates.all():
            logger.debug(f"🛑 Template: {template}")
            template_selections.append(
                TemplateSelection(
                    template_id=template.id,
                    template_name=template.name,
                )
            )

        return template_selections

    @staticmethod
    async def update_template(
        db: AsyncSession, template_id: int, template_data: ClassTemplateUpdate
    ) -> Optional[ClassTemplate]:
        """更新模板， 每次更新，需要把configs也都置为inactive"""
        template = await TemplateService.get_template(db, template_id)
        if not template:
            return None

        update_data = template_data.model_dump(exclude_unset=True)

        # 处理 levels 字段：直接传入 list，setter 会自动转为 JSON 字符串
        levels_data = None
        if "levels" in update_data and template_data.levels:
            levels_data = [level.model_dump() for level in template_data.levels]
            update_data["levels"] = levels_data

        for field, value in update_data.items():
            setattr(template, field, value)

        # 使用 setattr 避免类型检查错误
        setattr(template, "updated_at", int(time.time()))

        # 将所有相关的ClassTemplateConfigs设置为inactive
        await db.execute(
            select(ClassTemplateConfigs).where(
                and_(
                    ClassTemplateConfigs.template_id == template_id,
                    ClassTemplateConfigs.is_active == True,
                )
            )
        )

        await db.commit()
        await db.refresh(template)

        # 如果更新了 levels，重新生成层级值域选项
        if levels_data:
            await TemplateService._generate_level_options(db, template, levels_data)

        # 自动处理文档类型层级（更新时重新解析）
        # 如果解析过一次，就不再解析了，可以手动添加类型，不然太浪费时间
        # 而且也是避免文档类别错漏出现问题
        doc_types = await db.execute(
            select(DocumentType).where(DocumentType.template_id == template_id)
        )
        if not doc_types.scalars().all():
            await TemplateService._process_doc_type_level(db, template)

        return template

    @staticmethod
    async def delete_template(db: AsyncSession, template_id: int) -> bool:
        """删除模板（软删除）"""
        template = await TemplateService.get_template(db, template_id)
        if not template:
            return False

        # 使用 setattr 避免类型检查错误
        setattr(template, "is_active", False)
        await db.commit()
        return True

    @staticmethod
    async def _process_doc_type_level_stream(
        db: AsyncSession, template: ClassTemplate, task_id: str
    ) -> AsyncGenerator[str, None]:
        """处理模板中的文档类型层级，自动创建/更新 DocumentType(流式)"""
        # 获取 levels 列表
        levels_list = template.levels if isinstance(template.levels, list) else []

        # 查找 is_doc_type 层级
        doc_type_level: Optional[Dict[str, Any]] = None
        for level in levels_list:
            if isinstance(level, dict) and level.get("is_doc_type"):
                doc_type_level = level
                break

        if doc_type_level is None:
            # 没有文档类型层级，跳过
            yield SSEEvent(
                event="stage_skip",
                data={
                    "stage": "process_doc_type",
                    "message": "无文档类型层级，跳过处理",
                },
                id=task_id,
            ).model_dump_json()
            return

        extraction_prompt = doc_type_level.get("extraction_prompt")
        if not extraction_prompt:
            yield SSEEvent(
                event="stage_skip",
                data={
                    "stage": "process_doc_type",
                    "message": "未配置提取prompt，跳过处理",
                },
                id=task_id,
            ).model_dump_json()
            return

        yield SSEEvent(
            event="stage_start",
            data={"stage": "process_doc_type", "message": "开始解析文档类型..."},
            id=task_id,
        ).model_dump_json()
        await asyncio.sleep(0.1)

        # 使用大模型解析 prompt，识别文档类型
        doc_types_data = await TemplateService._parse_doc_types_from_prompt(
            extraction_prompt
        )

        yield SSEEvent(
            event="thinking",
            data={
                "stage": "process_doc_type",
                "message": f"识别到 {len(doc_types_data)} 个文档类型，开始创建...",
            },
            id=task_id,
        ).model_dump_json()
        await asyncio.sleep(0.1)

        # 为每个识别出的文档类型创建/更新记录
        for type_data in doc_types_data:
            await TemplateService._create_or_update_doc_type(db, template.id, type_data)

        yield SSEEvent(
            event="stage_complete",
            data={
                "stage": "process_doc_type",
                "message": f"文档类型处理完成，共 {len(doc_types_data)} 个",
            },
            id=task_id,
        ).model_dump_json()
        await asyncio.sleep(0.1)

    @staticmethod
    async def _parse_doc_types_from_prompt(
        extraction_prompt: str,
    ) -> List[Dict[str, Any]]:
        """使用大模型解析 extraction_prompt，提取文档类型列表（不包含字段，字段由用户在前端手动配置）"""
        system_prompt = """你是一个文档分类专家。用户会提供一个用于文档类型分类的prompt。
请分析这个prompt，识别出其中定义的所有文档类型，并为每个类型提取以下信息：
1. type_code: 类型编码（简短英文或拼音，如 dev_doc, design_doc）
2. type_name: 类型名称（中文，如 开发文档、设计文档）
3. description: 类型描述（简要说明）

注意：只需要识别文档类型本身，不需要识别字段信息。

请以JSON格式返回，格式如下：
{
  "document_types": [
    {
      "type_code": "dev_doc",
      "type_name": "开发文档",
      "description": "软件开发过程文档"
    }
  ]
}"""
        llm_client = get_llm_client()

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"请分析以下文档类型分类prompt：\n\n{extraction_prompt}",
            },
        ]

        result = await llm_client.extract_json_response(messages)
        logger.info(f"文档类型自动创建结果：{result}")
        return result.get("document_types", [])

    @staticmethod
    async def _create_or_update_doc_type(
        db: AsyncSession, template_id: int, type_data: Dict[str, Any]
    ) -> None:
        """创建或更新文档类型"""
        type_code = type_data.get("type_code")
        if not type_code:
            return

        # 检查是否已存在
        result = await db.execute(
            select(DocumentType).filter(
                DocumentType.template_id == template_id,
                DocumentType.type_code == type_code,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # 更新现有记录
            existing.type_name = type_data.get("type_name", existing.type_name)
            existing.description = type_data.get("description", existing.description)
        else:
            # 创建新记录（不创建字段，字段由用户在前端手动配置）
            new_doc_type = DocumentType(
                template_id=template_id,
                type_code=type_code,
                type_name=type_data.get("type_name", ""),
                description=type_data.get("description", ""),
                is_active=True,
            )
            db.add(new_doc_type)

        await db.commit()

    @staticmethod
    async def _generate_level_options_stream(
        db: AsyncSession,
        template: ClassTemplate,
        levels_data: List[Dict[str, Any]],
        task_id: str,
    ) -> AsyncGenerator[str, None]:
        """使用大模型生成层级值域选项(流式)"""
        llm_client = get_llm_client()
        # 过滤掉 is_doc_type 的层级
        normal_levels = [
            level for level in levels_data if not level.get("is_doc_type", False)
        ]

        if not normal_levels:
            yield SSEEvent(
                event="stage_skip",
                data={"stage": "generate_options", "message": "无需生成层级选项"},
                id=task_id,
            ).model_dump_json()
            return

        yield SSEEvent(
            event="stage_start",
            data={"stage": "generate_options", "message": "开始生成层级值域选项..."},
            id=task_id,
        ).model_dump_json()
        await asyncio.sleep(0.1)

        # 构建 prompt
        prompt = """你是一个文档分类系统的助手。请为每个层级生成合理的可选值列表。

层级定义：
{levels_json}

请以JSON格式返回，格式：
{{
  "YEAR": null,
  "DEPT": [
    {{"name": "BGT", "description": "办公厅"}},
    {{"name": "FGW", "description": "发展和改革委员会"}}
  ]
}}

规则：
1. 键名使用层级的code字段
2. 时间类型（年/月/日）设为null
3. 有明确值域的返回数组，每项包含name和description
4. 优先使用extraction_prompt中的值域映射
5. 无明确值域且非时间类型设为null
6. 只输出JSON，不要其他内容
7. 每个层级的选项数量不要超过50个，选择最常用的
""".replace(
            "{levels_json}", json.dumps(normal_levels, ensure_ascii=False, indent=2)
        )

        yield SSEEvent(
            event="thinking",
            data={
                "stage": "generate_options",
                "message": "正在调用大模型分析层级结构...",
            },
            id=task_id,
        ).model_dump_json()
        await asyncio.sleep(0.1)

        # 调用 LLM 生成值域选项
        level_options = await llm_client.extract_json_response(
            prompt, db=db, max_tokens=4096 * 2
        )

        # 保存到模板
        template.level_options = level_options
        await db.commit()

        logger.info(f"模板 {template.id} 的层级值域选项生成成功: {level_options}")

        yield SSEEvent(
            event="stage_complete",
            data={
                "stage": "generate_options",
                "message": f"层级值域选项生成完成，共 {len(level_options)} 个层级",
            },
            id=task_id,
        ).model_dump_json()
        await asyncio.sleep(0.1)
