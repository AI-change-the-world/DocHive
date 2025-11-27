"""
Agent编辑API端点
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from models.database_models import CustomAgent
from schemas.agent_schemas import (
    AgentCreateRequest,
    AgentMarkdownRequest,
    AgentResponse,
)
from schemas.api_schemas import ResponseBase
from services.agent_editor import (
    AgentExecutionBuilder,
    AgentLLMValidator,
    AgentMarkdownParser,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/parse-markdown", response_model=ResponseBase)
async def parse_agent_markdown(
    request: AgentMarkdownRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseBase:
    """
    使用大模型解析Markdown格式的Agent定义，并验证可行性
    返回验证结果和Mermaid流程图
    """
    try:
        logger.info("🔍 开始解析Agent Markdown")

        # 1. 使用大模型解析Markdown
        result = await AgentMarkdownParser.parse(
            content=request.content,
            template_id=request.template_id,
            db=db,
        )

        if not result.success:
            return ResponseBase(
                code=400,
                message="Markdown解析失败",
                data={
                    "success": False,
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
            )

        # 2. 基础验证
        is_valid, validation_errors = AgentExecutionBuilder.validate_agent(result.agent)
        if not is_valid:
            result.errors.extend(validation_errors)
            return ResponseBase(
                code=200,
                message="解析成功但验证失败",
                data={
                    "success": False,
                    "agent": result.agent.model_dump() if result.agent else None,
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "mermaid_diagram": "",
                },
            )

        # 3. 使用LLM验证流程可行性并生成Mermaid图
        logger.info("🤖 调用LLM验证流程")
        llm_valid, llm_errors, llm_warnings, mermaid_diagram = (
            await AgentLLMValidator.validate_with_llm(
                agent=result.agent,
                db=db,
            )
        )

        # 合并验证结果
        all_errors = result.errors + llm_errors
        all_warnings = result.warnings + llm_warnings

        if llm_valid:
            logger.info(f"✅ Agent解析成功: {result.agent.name}")
            return ResponseBase(
                code=200,
                message="Agent解析成功",
                data={
                    "success": True,
                    "agent": result.agent.model_dump(),
                    "errors": all_errors,
                    "warnings": all_warnings,
                    "mermaid_diagram": mermaid_diagram,
                },
            )
        else:
            logger.warning(f"⚠️ LLM验证失败: {llm_errors}")
            return ResponseBase(
                code=200,
                message="Agent解析成功但LLM验证失败",
                data={
                    "success": False,
                    "agent": result.agent.model_dump(),
                    "errors": all_errors,
                    "warnings": all_warnings,
                    "mermaid_diagram": mermaid_diagram,
                },
            )

    except Exception as e:
        logger.error(f"❌ 解析Agent失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.post("/create")
async def create_agent(
    request: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseBase:
    """
    创建Agent并保存到数据库
    """
    try:
        logger.info(f"📝 创建Agent: {request.name}")

        # 1. 使用大模型解析Markdown
        parse_result = await AgentMarkdownParser.parse(
            content=request.markdown_content,
            template_id=request.template_id,
            db=db,
        )

        if not parse_result.success:
            raise HTTPException(
                status_code=400,
                detail=f"Agent定义解析失败: {'; '.join(parse_result.errors)}",
            )

        agent = parse_result.agent

        # 2. 基础验证
        is_valid, validation_errors = AgentExecutionBuilder.validate_agent(agent)
        if not is_valid:
            raise HTTPException(
                status_code=400, detail=f"Agent验证失败: {'; '.join(validation_errors)}"
            )

        # 3. LLM验证并生成Mermaid图
        llm_valid, llm_errors, llm_warnings, mermaid_diagram = (
            await AgentLLMValidator.validate_with_llm(
                agent=agent,
                db=db,
            )
        )

        if not llm_valid:
            raise HTTPException(
                status_code=400, detail=f"LLM验证失败: {'; '.join(llm_errors)}"
            )

        # 4. 保存到数据库
        db_agent = CustomAgent(
            name=request.name,
            description=request.description,
            template_id=request.template_id,
            markdown_content=request.markdown_content,
            execution_pattern=agent.execution_pattern,
            steps=[s.model_dump() for s in agent.steps],
            mermaid_diagram=mermaid_diagram,
            version=agent.version,
            is_active=True,
            metadata=agent.metadata or {},
            creator_id=1,  # TODO: 从认证信息获取
        )

        db.add(db_agent)
        await db.commit()
        await db.refresh(db_agent)

        logger.info(f"✅ Agent创建成功: {agent.name}, ID={db_agent.id}")
        return ResponseBase(
            code=200,
            message="Agent创建成功",
            data={
                "agent": db_agent.to_dict(),
                "execution_plan": AgentExecutionBuilder.build_execution_plan(agent),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 创建Agent失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/list", response_model=ResponseBase)
async def list_agents(
    template_id: int = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
) -> ResponseBase:
    """
    获取Agent列表
    """
    try:
        query = select(CustomAgent)

        if template_id is not None:
            query = query.where(CustomAgent.template_id == template_id)

        if is_active is not None:
            query = query.where(CustomAgent.is_active == is_active)

        query = query.order_by(CustomAgent.created_at.desc())

        result = await db.execute(query)
        agents = result.scalars().all()

        return ResponseBase(
            code=200,
            message="获取成功",
            data={
                "agents": [agent.to_dict() for agent in agents],
                "total": len(agents),
            },
        )

    except Exception as e:
        logger.error(f"❌ 获取Agent列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/markdown-template")
async def get_markdown_template() -> ResponseBase:
    """
    获取Agent Markdown模板
    """
    template = """# Agent: 我的Agent名称

**描述**: 这是一个Agent的描述，说明它的用途

**执行模式**: hybrid

## 执行步骤

### 步骤1: 获取统计信息
- **类型**: tool
- **名称**: get_template_statistics
- **描述**: 获取模板的统计信息

### 步骤2: 搜索文档
- **类型**: tool
- **名称**: search_documents_by_classification
- **描述**: 根据分类搜索文档

### 步骤3: 检索相关文档
- **类型**: agent
- **名称**: retrieval_agent
- **描述**: 检索与查询相关的文档

### 步骤4: 生成答案
- **类型**: agent
- **名称**: qa_agent
- **描述**: 基于检索结果生成答案
"""

    return ResponseBase(code=200, message="模板获取成功", data={"template": template})
