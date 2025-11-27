"""
Agent编辑服务 - 使用大模型解析Markdown格式的Agent定义并验证流程
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.agent_schemas import (
    AgentDefinitionSchema,
    AgentMarkdownParseResponse,
    AgentStepSchema,
)
from utils.llm_client import get_llm_client


class AgentMarkdownParser:
    """使用大模型解析Markdown格式的Agent定义"""

    @staticmethod
    async def parse(
        content: str,
        template_id: Optional[int],
        db: AsyncSession,
    ) -> AgentMarkdownParseResponse:
        """
        使用大模型解析Markdown格式的Agent定义
        """
        errors = []
        warnings = []

        try:
            llm_client = get_llm_client()

            # 构建系统能力描述
            from services.registry import get_agents_description, get_tools_description

            tools_desc = get_tools_description()
            agents_desc = get_agents_description()

            system_prompt = f"""你是一个专业的Agent流程规划器。

【系统能力清单】

## 可用工具
{tools_desc}

## 可用智能体
{agents_desc}

【任务说明】
用户会用Markdown描述他想要实现的Agent功能和意图。你的任务是：

1. **理解意图**：理解用户想要实现什么功能
2. **自主规划**：根据系统能力清单，自己规划出完整的执行步骤
3. **可行性判断**：判断系统中是否有足够的工具/智能体来实现这个流程

**重要原则**：
- 不要直接解析用户写的步骤，而是自己思考并规划
- 用户可能只描述了大致意图，你需要补充完整的步骤
- 用户也可能描述了具体步骤，但你需要验证和优化
- 只有当系统中缺少关键工具/智能体时，才判定为不可执行

【规划流程】

1. **分析意图**：用户想实现什么？
2. **拆解任务**：完成这个任务需要哪些关键步骤？
3. **匹配能力**：系统中有哪些工具/智能体可以实现这些步骤？
4. **检查缺失**：是否缺少关键能力？

【返回格式】

**情况1：可以实现**
返回JSON格式：
{{
    "name": "Agent名称",
    "description": "Agent描述",
    "execution_pattern": "tool_only | agent_only | agent_chain | hybrid",
    "steps": [
        {{
            "step": 1,
            "type": "tool | agent",
            "name": "系统中存在的工具/智能体名称",
            "description": "这一步做什么"
        }}
    ],
    "errors": [],
    "warnings": []
}}

**情况2：缺少关键能力，无法实现**
返回JSON格式：
{{
    "name": "Agent名称",
    "description": "Agent描述",
    "errors": [
        "缺少关键能力：需要[具体功能]，但系统中没有对应的工具/智能体",
        "建议：添加[具体工具名]来实现[具体功能]"
    ]
    // 注意：不要包含steps字段
}}

【示例】

**示例1 - 用户只描述意图**
用户输入：
```markdown
# Agent: 文档问答助手
**描述**: 根据用户问题，找到相关文档并回答
```

你的分析：
- 意图：用户想实现问答功能
- 关键步骤：需要先检索文档，再生成答案
- 系统能力：有retrieval_agent和qa_agent

返回：
```json
{{
    "name": "文档问答助手",
    "description": "根据用户问题，找到相关文档并回答",
    "execution_pattern": "agent_chain",
    "steps": [
        {{
            "step": 1,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索与问题相关的文档"
        }},
        {{
            "step": 2,
            "type": "agent",
            "name": "qa_agent",
            "description": "基于检索到的文档生成答案"
        }}
    ],
    "errors": [],
    "warnings": []
}}
```

**示例2 - 用户描述了步骤但不完整**
用户输入：
```markdown
# Agent: 文档分析
**描述**: 分析所有文档的内容
## 执行步骤
### 步骤1：分析文档
- 类型: tool
- 名称: analyze_documents
```

你的分析：
- 意图：分析所有文档
- 问题：analyze_documents需要文档作为输入，但用户没有提及怎么获取文档
- 解决：需要先获取文档列表，再读取内容，最后分析

返回：
```json
{{
    "name": "文档分析",
    "description": "分析所有文档的内容",
    "execution_pattern": "tool_only",
    "steps": [
        {{
            "step": 1,
            "type": "tool",
            "name": "search_documents_by_classification",
            "description": "获取所有文档ID列表"
        }},
        {{
            "step": 2,
            "type": "tool",
            "name": "get_document_contents",
            "description": "读取文档完整内容"
        }},
        {{
            "step": 3,
            "type": "tool",
            "name": "analyze_documents",
            "description": "分析文档内容"
        }}
    ],
    "errors": [],
    "warnings": []
}}
```

**示例3 - 缺少关键能力**
用户输入：
```markdown
# Agent: 邮件发送助手
**描述**: 根据文档内容自动发送邮件
```

你的分析：
- 意图：需要发送邮件功能
- 关键能力：需要邮件发送工具
- 系统检查：系统中没有邮件发送相关的工具

返回：
```json
{{
    "name": "邮件发送助手",
    "description": "根据文档内容自动发送邮件",
    "errors": [
        "缺少关键能力：需要邮件发送功能，但系统中没有对应的工具",
        "系统当前只支持文档检索、问答、统计和分析功能",
        "建议：需要先添加send_email工具才能实现此Agent"
    ]
}}
```
"""

            user_prompt = f"""请解析以下Markdown格式的Agent定义：

```markdown
{content}
```

请返回结构化的JSON数据。
"""

            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                db=db,
            )

            # 提取解析结果
            name = response.get("name", "")
            description = response.get("description", "")
            execution_pattern = response.get("execution_pattern", "hybrid")
            steps_data = response.get("steps", [])
            errors = response.get("errors", [])
            warnings = response.get("warnings", [])

            if not name:
                errors.append("缺少Agent名称")
                return AgentMarkdownParseResponse(success=False, errors=errors)

            if not steps_data:
                errors.append("未找到任何执行步骤")
                return AgentMarkdownParseResponse(success=False, errors=errors)

            # 构建步骤列表
            steps = []
            for step_data in steps_data:
                try:
                    step = AgentStepSchema(
                        step=step_data.get("step", 0),
                        type=step_data.get("type", "").lower(),
                        name=step_data.get("name", ""),
                        description=step_data.get("description", ""),
                        parameters=step_data.get("parameters"),
                        condition=step_data.get("condition"),
                    )
                    steps.append(step)
                except Exception as e:
                    errors.append(f"步骤{step_data.get('step', '?')}格式错误: {str(e)}")

            if errors:
                return AgentMarkdownParseResponse(
                    success=False, errors=errors, warnings=warnings
                )

            # 构建Agent定义
            agent = AgentDefinitionSchema(
                name=name,
                description=description,
                template_id=template_id,
                execution_pattern=execution_pattern,
                steps=steps,
                version="1.0",
                is_active=True,
            )

            return AgentMarkdownParseResponse(
                success=True, agent=agent, warnings=warnings
            )

        except Exception as e:
            logger.error(f"解析Agent Markdown失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
            errors.append(f"解析失败: {str(e)}")
            return AgentMarkdownParseResponse(success=False, errors=errors)

    @staticmethod
    def to_markdown(agent: AgentDefinitionSchema) -> str:
        """将Agent定义转换为Markdown格式"""
        lines = [
            f"# Agent: {agent.name}",
            "",
            f"**描述**: {agent.description}",
            "",
        ]

        if agent.template_id:
            lines.append(f"**模板ID**: {agent.template_id}")
            lines.append("")

        lines.extend(
            [
                f"**执行模式**: {agent.execution_pattern}",
                "",
                "## 执行步骤",
                "",
            ]
        )

        for step in agent.steps:
            lines.extend(
                [
                    f"### 步骤{step.step}: {step.description}",
                    f"- **类型**: {step.type}",
                    f"- **名称**: {step.name}",
                    f"- **描述**: {step.description}",
                ]
            )

            if step.condition:
                lines.append(f"- **条件**: {step.condition}")

            if step.parameters:
                lines.extend(
                    [
                        "- **参数**:",
                        "```json",
                        json.dumps(step.parameters, ensure_ascii=False, indent=2),
                        "```",
                    ]
                )

            lines.append("")

        return "\n".join(lines)


class AgentExecutionBuilder:
    """Agent执行计划构建器"""

    @staticmethod
    def build_execution_plan(agent: AgentDefinitionSchema) -> List[Dict[str, Any]]:
        """根据Agent定义构建执行计划"""
        plan = []

        for step in agent.steps:
            plan_item = {
                "step": step.step,
                "type": step.type,
                "name": step.name,
                "description": step.description,
            }

            if step.parameters:
                plan_item["parameters"] = step.parameters

            if step.condition:
                plan_item["condition"] = step.condition

            plan.append(plan_item)

        return plan

    @staticmethod
    def validate_agent(agent: AgentDefinitionSchema) -> Tuple[bool, List[str]]:
        """验证Agent定义的有效性"""
        errors = []

        # 验证执行模式
        valid_patterns = [
            "tool_only",
            "agent_only",
            "agent_chain",
            "hybrid",
            "llm_direct",
        ]
        if agent.execution_pattern not in valid_patterns:
            errors.append(
                f"无效的执行模式: {agent.execution_pattern}，有效值: {valid_patterns}"
            )

        # 验证步骤
        if not agent.steps:
            errors.append("Agent必须包含至少一个执行步骤")
            return False, errors

        # 验证步骤序号连续性
        step_nums = [s.step for s in agent.steps]
        if step_nums != list(range(1, len(step_nums) + 1)):
            errors.append(f"步骤序号不连续")

        # 验证步骤类型
        valid_types = ["tool", "agent"]
        for step in agent.steps:
            if step.type not in valid_types:
                errors.append(
                    f"步骤{step.step}的类型无效: {step.type}，有效值: {valid_types}"
                )

        # 验证step_chain模式必须至少有两个步骤
        if agent.execution_pattern == "agent_chain":
            agent_steps = [s for s in agent.steps if s.type == "agent"]
            if len(agent_steps) < 2:
                errors.append("agent_chain模式必须至少包含两个智能体步骤")

        return len(errors) == 0, errors


class AgentLLMValidator:
    """使用大模型验证Agent定义的可行性"""

    @staticmethod
    async def validate_with_llm(
        agent: AgentDefinitionSchema,
        db: AsyncSession,
    ) -> Tuple[bool, List[str], List[str], str]:
        """
        使用大模型验证Agent流程是否可行

        Returns:
            Tuple[is_valid, errors, warnings, mermaid_diagram]
        """
        llm_client = get_llm_client()

        # 构建验证prompt
        from services.registry import get_agents_description, get_tools_description

        tools_desc = get_tools_description()
        agents_desc = get_agents_description()

        system_prompt = f"""你是一个专业的Agent流程验证器。

【系统能力清单】

## 可用工具
{tools_desc}

## 可用智能体
{agents_desc}

【验证任务】
请验证用户定义的Agent流程是否可以正常执行，检查：

1. **步骤完整性**：是否缺少关键步骤？
2. **工具/智能体存在性**：所有用到的工具/智能体是否都在系统中存在？
3. **步骤顺序**：步骤顺序是否合理？比如，是否在没有检索文档的情况下直接进行问答？
4. **执行模式匹配**：执行模式和实际步骤是否匹配？
5. **逻辑连贯性**：每个步骤之间的数据流转是否合理？

【返回格式】
请返回JSON格式：
{{
    "is_valid": true | false,
    "errors": ["错误信息1", "错误信息2"],
    "warnings": ["警告信息1"],
    "suggestions": ["优化建议1"],
    "mermaid_diagram": "graph TD\\n    A[...]"
}}

mermaid_diagram必须是Mermaid语法的流程图代码，使用graph TD开头，不要添加任何样式定义。
示例：
graph TD
    Start[[开始]] --> Step1[步骤1: 获取统计信息]
    Step1 --> Step2[步骤2: 检索文档]
    Step2 --> Step3[步骤3: 生成答案]
    Step3 --> End[[结束]]
"""

        # 构建Agent信息
        agent_info = {
            "name": agent.name,
            "description": agent.description,
            "execution_pattern": agent.execution_pattern,
            "steps": [
                {
                    "step": s.step,
                    "type": s.type,
                    "name": s.name,
                    "description": s.description,
                }
                for s in agent.steps
            ],
        }

        user_prompt = f"""请验证以下Agent流程：

```json
{json.dumps(agent_info, ensure_ascii=False, indent=2)}
```

请仔细检查并生成验证结果和Mermaid流程图。
"""

        try:
            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                db=db,
            )

            is_valid = response.get("is_valid", False)
            errors = response.get("errors", [])
            warnings = response.get("warnings", [])
            mermaid_diagram = response.get("mermaid_diagram", "")

            logger.info(
                f"✅ LLM验证结果: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}"
            )

            return is_valid, errors, warnings, mermaid_diagram

        except Exception as e:
            logger.error(f"❌ LLM验证失败: {e}")
            return False, [f"LLM验证失败: {str(e)}"], [], ""
