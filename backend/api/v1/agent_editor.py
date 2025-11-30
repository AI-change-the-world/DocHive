"""
Agent编辑API端点
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_config, get_db, get_search_engine
from core.agent_editor import (
    AgentExecutionBuilder,
    AgentLLMValidator,
    AgentMarkdownParser,
)
from models.database_models import CustomAgent
from schemas.agent_schemas import (
    AgentCreateRequest,
    AgentMarkdownRequest,
    AgentResponse,
)
from schemas.api_schemas import ResponseBase

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


@router.get("/{agent_id}", response_model=ResponseBase)
async def get_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseBase:
    """
    获取单个Agent详情
    """
    try:
        result = await db.execute(select(CustomAgent).where(CustomAgent.id == agent_id))
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent不存在")

        return ResponseBase(
            code=200,
            message="获取成功",
            data={"agent": agent.to_dict()},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取Agent失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/execute/{agent_id}")
async def execute_agent(
    agent_id: int,
    request_body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    search_engine=Depends(get_search_engine),
    config=Depends(get_config),
):
    """
    执行自定义Agent

    这是主要入口：根据已保存的Agent定义执行工作流
    """
    import json

    from fastapi.responses import StreamingResponse

    from core.agents.custom_agent_executor import CustomAgentExecutor

    try:
        logger.info(f"📝 执行自定义Agent: ID={agent_id}")

        # 1. 获取Agent定义
        result = await db.execute(
            select(CustomAgent).where(
                CustomAgent.id == agent_id,
                CustomAgent.is_active == True,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent不存在或未激活")

        # 2. 提取请求参数
        query = request_body.get("query", "")
        template_id = request_body.get("template_id") or agent.template_id
        session_id = request_body.get("session_id")

        if not query:
            raise HTTPException(status_code=400, detail="缺少query参数")

        if template_id is None:
            raise HTTPException(
                status_code=400,
                detail="缺少template_id参数，请在请求中提供或确保Agent已关联模板",
            )

        # 3. 获取ES客户端和索引
        # 使用 SearchEngine 的 client 属性（AsyncElasticsearch 实例）
        es_client = search_engine.client
        # 从配置或 SearchEngine 获取索引名称
        es_index = (
            request_body.get("es_index")
            or search_engine.index_name
            or config.ELASTICSEARCH_INDEX
        )

        # 4. 创建SSE生成器
        async def event_generator():
            try:
                async for event in CustomAgentExecutor.execute(
                    agent=agent,
                    query=query,
                    template_id=template_id,
                    session_id=session_id,
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"❌ 执行过程出错: {e}")
                import traceback

                logger.error(traceback.format_exc())
                error_event = {"event": "error", "data": {"error": str(e)}}
                yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

        # 5. 返回SSE响应
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 执行Agent失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"执行失败: {str(e)}")


@router.post("/markdown-template")
async def get_markdown_template() -> ResponseBase:
    """
    获取Agent Markdown模板
    """
    template = """# Agent: 写文章助手

**描述**: 根据主题自动规划文章结构、查询关键信息、摘取要素、组合内容并排版

## 执行步骤

### 步骤1: 规划文章结构
- **描述**: 分析主题,规划文章需要几个章节,每个章节写什么

### 步骤2: 查询关键信息
- **描述**: 检索与主题相关的文档和资料

### 步骤3: 摘取要素
- **描述**: 从文档中提取关键信息点

### 步骤4: 组合内容
- **描述**: 将信息按照规划的结构组织成文章

### 步骤5: 排版优化
- **描述**: 优化文章格式和排版
"""

    return ResponseBase(code=200, message="模板获取成功", data={"template": template})
