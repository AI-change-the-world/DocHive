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
        is_valid, validation_errors = AgentExecutionBuilder.validate_agent(
            result.agent)
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
    创建Agent并保存到数据库(V2:直接使用前端解析好的数据)

    前端流程:
    1. 调用parse-markdown接口解析Markdown -> 得到Agent定义
    2. 调用create接口,直接传递解析好的数据 -> 保存到DB

    这样避免了后端重复LLM解析,提升响应速度
    """
    try:
        logger.info(f"📝 创建Agent: {request.name}")

        # 直接使用前端传来的已解析数据,不再重复调用LLM
        db_agent = CustomAgent(
            name=request.name,
            description=request.description,
            template_id=request.template_id,
            markdown_content=request.markdown_content,
            execution_pattern=request.execution_pattern or "hybrid",
            # V2字段
            goals=request.goals,
            constraints=request.constraints,
            initial_plan=[
                s.model_dump() for s in request.initial_plan] if request.initial_plan else [],
            mermaid_diagram=request.mermaid_diagram,
            version="1.0",
            is_active=True,
            creator_id=1,  # TODO: 从认证信息获取
        )

        db.add(db_agent)
        await db.commit()
        await db.refresh(db_agent)

        logger.info(f"✅ Agent创建成功: {request.name}, ID={db_agent.id}")
        return ResponseBase(
            code=200,
            message="Agent创建成功",
            data={"agent": db_agent.to_dict()},
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
    执行自定义Agent(V2:动态规划)

    这是主要入口:根据Agent定义动态规划并执行工作流
    不再使用DB中的静态steps,而是每次执行时由LLM动态规划
    """
    import json

    from sse_starlette import EventSourceResponse

    # 使用新的V2执行器
    from core.agents.custom_agent_executor_v2 import CustomAgentExecutorV2

    try:
        logger.info(f"📝 执行自定义Agent V2: ID={agent_id}")

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
                detail="缺少template_id参数,请在请求中提供或确保Agent已关联模板",
            )

        # 3. 获取ES客户端和索引
        es_client = search_engine.client
        es_index = (
            request_body.get("es_index")
            or search_engine.index_name
            or config.ELASTICSEARCH_INDEX
        )

        # 4. 创建SSE生成器(使用V2执行器)
        async def event_generator():
            try:
                async for event in CustomAgentExecutorV2.execute(
                    agent=agent,
                    query=query,
                    template_id=template_id,
                    session_id=session_id,
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                ):
                    yield json.dumps(event, ensure_ascii=False)
            except Exception as e:
                logger.error(f"❌ 执行过程出错: {e}")
                import traceback

                logger.error(traceback.format_exc())
                error_event = {"event": "error", "data": {"error": str(e)}}
                yield json.dumps(error_event, ensure_ascii=False)

        # 5. 返回SSE响应
        return EventSourceResponse(event_generator())

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
    获取Agent Markdown模板(V2:能力导向)
    """
    template = """# Agent: 智能问答助手

## 描述
根据用户提问,智能检索相关文档并生成答案。支持多轮问答和上下文理解。

## 目标
- 快速检索相关文档
- 生成准确、完整的答案
- 支持引用来源

## 约束
- 检索文档数不超过50个
- 答案长度不超过1000字
- 必须基于检索的文档回答,不能编造

## 推荐工具
- retrieval_agent: 检索相关文档
- qa_agent: 生成答案

---

# Agent: 报表生成助手

## 描述
根据用户要求,自动检索相关数据、生成报表框架、填充内容并格式化输出。

## 目标
- 检索相关数据文档
- 生成结构化报表框架
- 填充关键数据和图表
- 格式化输出(Markdown或Excel)

## 约束
- 数据必须真实,不能传造
- 报表结构须清晰易读
- 执行时间不超过10分钟

## 推荐工具
- multi_query_search: 多维度检索数据
- get_template_statistics: 获取统计数据
- document_compose: 组装生成文档

---

# Agent: 文档分类助手

## 描述
自动对上传的文档进行分类和打标签,提高文档管理效率。

## 目标
- 读取文档内容
- 分析文档类型和主题
- 按照模板规则分类
- 自动生成标签

## 约束
- 支持PDF、Word、文本等格式
- 分类准确率高于85%
- 单个文档处理时间不超过30秒

## 推荐工具
- read_documents: 读取文档内容
- analyze_documents: 分析文档特征

---

**说明**:
1. 上面是几个示例,你可以参考编写
2. **不需要**写具体的执行步骤,只需描述目标和约束
3. 执行时系统会根据你的描述自动规划步骤
4. 可以推荐工具,但不是强制的
5. 系统会根据目标和约束智能选择工具
"""

    return ResponseBase(code=200, message="模板获取成功", data={"template": template})
