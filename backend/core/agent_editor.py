"""  
Agent编辑服务 - 使用大模型解析Markdown格式的Agent定义并验证流程
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

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
            from core.registry import get_agents_description
            from core.tools.base import get_state_keys_catalog, get_tools_catalog

            tools_catalog = get_tools_catalog()
            agents_desc = get_agents_description()
            state_keys_catalog = get_state_keys_catalog()

            system_prompt = """你是一个专业的Agent规划助手。

【任务】
用户会用Markdown描述他想要的Agent功能。你需要将其转换为结构化的Agent定义。

【Markdown格式说明】
用户的Markdown通常包含:
1. **标题**: Agent名称
2. **描述**: Agent的功能描述  
3. **目标**: Agent要达成的目标列表(可选)
4. **约束**: 执行时的约束条件(可选)
5. **推荐工具**: 用户推荐使用的工具(可选,仅作参考)

【核心原则】
1. **重点提取目标和约束**: 这是最重要的,执行时会基于目标和约束动态规划步骤
2. **不强制规划步骤**: 不需要在解析阶段规划详细步骤,执行时会动态规划
3. **理解用户意图**: 从描述中提取核心目标和关键约束
4. **工具仅作参考**: 推荐工具不是强制的,执行时会智能选择

【返回格式】
返回JSON:
{{
    "name": "Agent名称",
    "description": "详细描述",
    "goals": ["目标1", "目标2", ...],  # 从Markdown中提取
    "constraints": ["约束1", "约束2", ...],  # 从Markdown中提取
    "execution_pattern": "hybrid",  # 默认hybrid
    "initial_plan": null,  # 可选,通常为空,执行时动态规划
    "errors": [],
    "warnings": []
}}

【示例1 - 简单问答Agent】
输入Markdown:
```
# Agent: 智能问答助手

## 描述  
根据用户提问,检索相关文档并生成答案

## 目标
- 快速检索相关文档
- 生成准确答案

## 约束
- 检索文档数不超过50个
- 答案长度不超过1000字
```

输出JSON:
```json
{{
    "name": "智能问答助手",
    "description": "根据用户提问,检索相关文档并生成答案",
    "goals": [
        "快速检索相关文档",
        "生成准确答案"
    ],
    "constraints": [
        "检索文档数不超过50个",
        "答案长度不超过1000字"
    ],
    "execution_pattern": "hybrid",
    "initial_plan": null,
    "errors": [],
    "warnings": []
}}
```

【示例2 - 报表生成Agent】
输入Markdown:
```
# Agent: 报表生成助手

## 描述
根据要求自动生成数据报表

## 目标
- 检索相关数据
- 生成结构化报表
- 格式化输出

## 约束  
- 数据必须真实
- 执行时间不超过10分钟

## 推荐工具
- multi_query_search
- document_compose
```

输出JSON:
```json
{{
    "name": "报表生成助手",
    "description": "根据要求自动生成数据报表",
    "goals": [
        "检索相关数据",
        "生成结构化报表",
        "格式化输出"
    ],
    "constraints": [
        "数据必须真实",
        "执行时间不超过10分钟"
    ],
    "execution_pattern": "hybrid",
    "initial_plan": null,
    "errors": [],
    "warnings": ["推荐工具仅作参考,执行时会根据目标智能选择"]
}}
```

【注意】
1. goals和constraints从Markdown的## 目标和## 约束部分提取
2. 如果Markdown中没有明确的目标/约束,从描述中推断
3. 不需要规划具体步骤(initial_plan保持null)
4. execution_pattern通常设为"hybrid"
5. 如果用户描述过于模糊,在warnings中说明
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

            # 提取解析结果(新结构:goals/constraints/initial_plan)
            name = response.get("name", "")
            description = response.get("description", "")
            execution_pattern = response.get("execution_pattern", "hybrid")
            goals = response.get("goals", [])
            constraints = response.get("constraints", [])
            initial_plan_data = response.get("initial_plan", [])
            errors = response.get("errors", [])
            warnings = response.get("warnings", [])

            if not name:
                errors.append("缺少Agent名称")
                return AgentMarkdownParseResponse(success=False, errors=errors)

            # 如果有errors,表示缺少工具,返回验证失败
            if errors:
                return AgentMarkdownParseResponse(
                    success=False, errors=errors, warnings=warnings
                )

            # 构建initial_plan(如果有)
            initial_plan = []
            if initial_plan_data:
                for step_data in initial_plan_data:
                    try:
                        step = AgentStepSchema(
                            step=step_data.get("step", 0),
                            type=step_data.get("type", "").lower(),
                            name=step_data.get("name", ""),
                            description=step_data.get("description", ""),
                            parameters=step_data.get("parameters"),
                            read_fields=step_data.get("read_fields"),
                            write_fields=step_data.get("write_fields"),
                            expectations=step_data.get("expectations"),
                            on_fail_strategy=step_data.get("on_fail_strategy"),
                        )
                        initial_plan.append(step)
                    except Exception as e:
                        warnings.append(
                            f"步骤{step_data.get('step', '?')}格式错误: {str(e)}"
                        )

            # 构建Agent定义(新结构)
            agent = AgentDefinitionSchema(
                name=name,
                description=description,
                template_id=template_id,
                execution_pattern=execution_pattern,
                goals=goals,
                constraints=constraints,
                initial_plan=initial_plan if initial_plan else None,
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
                        json.dumps(step.parameters,
                                   ensure_ascii=False, indent=2),
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
        """验证Agent定义的有效性(V2:支持只有goals的Agent)"""
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

        # V2设计:允许只有goals而没有steps
        # 如果有goals,则不需要steps(执行时动态规划)
        # 如果有steps/initial_plan,则需要验证
        has_goals = agent.goals and len(agent.goals) > 0
        has_steps = (agent.steps and len(agent.steps) > 0) or (
            agent.initial_plan and len(agent.initial_plan) > 0)

        if not has_goals and not has_steps:
            errors.append("Agent必须包含目标(goals)或执行步骤(steps/initial_plan)")
            return False, errors

        # 如果有steps,验证步骤
        steps_to_validate = agent.steps or agent.initial_plan or []
        if steps_to_validate:
            # 验证步骤序号连续性
            step_nums = [s.step for s in steps_to_validate]
            if step_nums != list(range(1, len(step_nums) + 1)):
                errors.append(f"步骤序号不连续")

            # 验证步骤类型
            valid_types = ["tool", "agent"]
            for step in steps_to_validate:
                if hasattr(step, 'type') and step.type and step.type not in valid_types:
                    errors.append(
                        f"步骤{step.step}的类型无效: {step.type}，有效值: {valid_types}"
                    )

            # 验证step_chain模式必须至少有两个步骤
            if agent.execution_pattern == "agent_chain":
                agent_steps = [s for s in steps_to_validate if hasattr(
                    s, 'type') and s.type == "agent"]
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
        from core.registry import get_agents_description
        from core.tools.base import get_state_keys_catalog, get_tools_catalog

        tools_catalog = get_tools_catalog()
        agents_desc = get_agents_description()
        state_keys_catalog = get_state_keys_catalog()

        system_prompt = """你是一个专业的Agent流程验证器和流程图设计专家。

【系统能力清单】

## 工具能力目录
{TOOLS_CATALOG}

## 可用智能体
{AGENTS_DESC}

## 状态键目录
{STATE_KEYS_CATALOG}

【验证任务】
请验证用户定义的Agent是否可以正常执行。

**V2设计说明**:
Agent现在支持两种定义方式:
1. **能力导向**(V2推荐): 只定义goals和constraints,执行时动态规划步骤
2. **步骤导向**(兼容): 明确定义steps或initial_plan

**验证规则**:
- 如果Agent有**goals**:
  - 只需验证goals是否清晰、可实现
  - 检查系统工具是否足以支持这些目标
  - 不需要验证步骤(因为执行时动态规划)
  - Mermaid图只需展示高层逻辑流程
  
- 如果Agent有**steps**:
  1. **步骤完整性**: 是否缺少关键步骤？
  2. **工具/智能体存在性**: 所有用到的工具/智能体是否都在系统中存在？
  3. **步骤顺序**: 步骤顺序是否合理？
  4. **执行模式匹配**: 执行模式和实际步骤是否匹配？
  5. **逻辑连贯性**: 每个步骤之间的数据流转是否合理？
  6. **控制流可行性**: 如果有expectations/on_fail_strategy,执行器能否实现？

【Mermaid流程图设计原则】

**对于goals导向的Agent**:
- 简单展示高层目标流程
- 不需要详细步骤

示例:
```
graph TD
    Start[[开始]] --> G1[目标: 检索相关文档]
    G1 --> G2[目标: 生成准确答案]
    G2 --> End[[结束]]
```

**对于steps导向的Agent**:
- 详细展示每个步骤
- 体现控制流(重试/回退/兵底)

**图形元素规范**:
- 普通步骤: `Step1[步骤1: 描述]`
- 决策节点: `D1{{"判断条件？"}}`
- 开始/结束: `Start[[开始]]` `End[[结束]]`
- 分支标签: `-- "条件" -->`
- 不要使用任何样式定义(style、classDef、fill 等)

【返回格式】
请返回JSON格式：
{{
    "is_valid": true | false,
    "errors": ["错误信息1"],
    "warnings": ["警告信息1"],
    "suggestions": ["优化建议1"],
    "mermaid_diagram": "graph TD\\n    A[...]"
}}

**mermaid_diagram 要求**:
- 必须使用 graph TD 开头
- 对于goals导向的Agent,简单展示目标流程
- 对于steps导向的Agent,详细展示步骤和控制流
- 不要添加任何样式定义
- 确保语法正确

【示例1 - goals导向的Agent】

输入的Agent定义：
```json
{{
    "name": "智能问答助手",
    "goals": [
        "快速检索相关文档",
        "生成准确答案"
    ],
    "constraints": [
        "检索文档数不超过50个",
        "答案长度不超过1000字"
    ]
}}
```

正确的输出：
```json
{{
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "suggestions": ["建议在执行时动态规划检索和问答步骤"],
    "mermaid_diagram": "graph TD\\n    Start[[开始]] --> G1[目标: 快速检索相关文档]\\n    G1 --> G2[目标: 生成准确答案]\\n    G2 --> End[[结束]]"
}}
```
"""
        system_prompt = system_prompt.replace("{TOOLS_CATALOG}", tools_catalog).replace(
            "{AGENTS_DESC}", agents_desc).replace("{STATE_KEYS_CATALOG}", state_keys_catalog)

        # 构建Agent信息(V2:支持goals或steps)
        agent_info = {
            "name": agent.name,
            "description": agent.description,
            "execution_pattern": agent.execution_pattern,
        }

        # 如果有goals和constraints,添加到agent_info
        if agent.goals:
            agent_info["goals"] = agent.goals
        if agent.constraints:
            agent_info["constraints"] = agent.constraints

        # 如果有steps或initial_plan,添加到agent_info
        steps_data = agent.steps or agent.initial_plan
        if steps_data:
            agent_info["steps"] = [
                {
                    "step": s.step,
                    "type": getattr(s, 'type', 'tool'),
                    "name": s.name,
                    "description": s.description,
                    "read_fields": getattr(s, 'read_fields', None),
                    "write_fields": getattr(s, 'write_fields', None),
                    "expectations": getattr(s, 'expectations', None),
                    "on_fail_strategy": getattr(s, 'on_fail_strategy', None),
                    "parameters": getattr(s, 'parameters', None),
                }
                for s in steps_data
            ]

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
