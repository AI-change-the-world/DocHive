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
6. **固定步骤/Pinned Steps**: 用户明确指定的工具调用及参数(关键功能!)

【核心原则】
1. **重点提取目标和约束**: 这是最重要的,执行时会基于目标和约束动态规划步骤
2. **识别固定步骤的两种模式**:
   - `[固定]`/`[pinned]`: 参数完全固定,不经过LLM推断
   - `[模板]`/`[template]`: 参数结构固定,但包含占位符(如$TOPIC),由LLM从用户输入推断填充
3. **工具仅作参考**: 推荐工具部分不是固定的,执行时会智能选择

【固定步骤语法示例】

**模式1: 完全固定参数**
```
## 固定步骤
1. [固定] es_fulltext_search | 搜索财务类文档
   ```json
   {{"must_match": [{{"field": "category", "value": "财务"}}], "size": 30}}
   ```
```
解析为: is_pinned=true, pinned_parameters有值, parameter_template=null

**模式2: 模板化固定参数(关键新功能！)**
```
## 固定步骤
1. [模板] es_fulltext_search | 按用户指定的主题检索
   ```json
   {{"must_match": [{{"field": "category", "value": "$TOPIC"}}], "size": 30}}
   ```
   - $TOPIC: 从用户输入中提取的主题关键词,如"财务"、"合同"等
```
解析为:
```json
{{
  "is_pinned": true,
  "pinned_parameters": null,
  "parameter_template": {{"must_match": [{{"field": "category", "value": "$TOPIC"}}], "size": 30}},
  "template_variables": {{"$TOPIC": "从用户输入中提取的主题关键词,如财务、合同等"}}
}}
```

【返回格式】
返回JSON:
{{
    "name": "Agent名称",
    "description": "详细描述",
    "goals": ["目标1", "目标2", ...],
    "constraints": ["约束1", "约束2", ...],
    "execution_pattern": "hybrid",
    "pinned_steps": [  // 用户固定的步骤
        {{
            "step": 1,
            "type": "tool",
            "name": "工具名称",
            "description": "步骤描述",
            "is_pinned": true,
            "pinned_parameters": {{}},  // 完全固定时有值
            "parameter_template": {{}},  // 模板化时有值
            "template_variables": {{}}   // 模板变量说明
        }}
    ],
    "initial_plan": null,
    "errors": [],
    "warnings": []
}}

【示例1 - 简单问答Agent(无固定步骤)】
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
```

输出JSON:
```json
{{
    "name": "智能问答助手",
    "description": "根据用户提问,检索相关文档并生成答案",
    "goals": ["快速检索相关文档", "生成准确答案"],
    "constraints": ["检索文档数不超过50个"],
    "execution_pattern": "hybrid",
    "pinned_steps": [],
    "initial_plan": null,
    "errors": [],
    "warnings": []
}}
```

【示例2 - 带模板化固定步骤的Agent】
输入Markdown:
```
# Agent: 主题检索助手

## 描述  
根据用户指定的主题检索文档

## 目标
- 理解用户想查询的主题
- 精确检索对应分类的文档

## 固定步骤
1. [模板] es_fulltext_search | 按用户指定的主题检索
   ```json
   {{"must_match": [{{"field": "category", "value": "$TOPIC"}}], "size": 30}}
   ```
   - $TOPIC: 从用户输入中提取的主题关键词
```

输出JSON:
```json
{{
    "name": "主题检索助手",
    "description": "根据用户指定的主题检索文档",
    "goals": ["理解用户想查询的主题", "精确检索对应分类的文档"],
    "constraints": [],
    "execution_pattern": "hybrid",
    "pinned_steps": [
        {{
            "step": 1,
            "type": "tool",
            "name": "es_fulltext_search",
            "description": "按用户指定的主题检索",
            "is_pinned": true,
            "pinned_parameters": null,
            "parameter_template": {{"must_match": [{{"field": "category", "value": "$TOPIC"}}], "size": 30}},
            "template_variables": {{"$TOPIC": "从用户输入中提取的主题关键词"}}
        }}
    ],
    "initial_plan": null,
    "errors": [],
    "warnings": []
}}
```

【注意】
1. `[固定]`标记 → pinned_parameters有值, parameter_template为null
2. `[模板]`标记 → pinned_parameters为null, parameter_template有值
3. 模板变量以$开头,如$TOPIC, $CATEGORY, $DATE_RANGE等
4. template_variables字段说明每个变量的含义,帮助LLM推断
5. 执行时,LLM会根据用户输入和变量说明,推断变量值并填充到模板中
6. 如果没有固定步骤,pinned_steps为空数组[]
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

            # 提取解析结果(新结构:goals/constraints/pinned_steps/initial_plan)
            name = response.get("name", "")
            description = response.get("description", "")
            execution_pattern = response.get("execution_pattern", "hybrid")
            goals = response.get("goals", [])
            constraints = response.get("constraints", [])
            pinned_steps_data = response.get("pinned_steps", [])
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

            # 构建pinned_steps
            pinned_steps = []
            if pinned_steps_data:
                for step_data in pinned_steps_data:
                    try:
                        step = AgentStepSchema(
                            step=step_data.get("step", len(pinned_steps) + 1),
                            type=step_data.get("type", "tool").lower(),
                            name=step_data.get("name", ""),
                            description=step_data.get("description", ""),
                            parameters=step_data.get("parameters"),
                            is_pinned=step_data.get("is_pinned", True),
                            pinned_parameters=step_data.get(
                                "pinned_parameters"),
                            parameter_template=step_data.get(
                                "parameter_template"),
                            template_variables=step_data.get(
                                "template_variables"),
                            read_fields=step_data.get("read_fields"),
                            write_fields=step_data.get("write_fields"),
                            expectations=step_data.get("expectations"),
                            on_fail_strategy=step_data.get("on_fail_strategy"),
                        )
                        pinned_steps.append(step)
                    except Exception as e:
                        warnings.append(
                            f"固定步骤{step_data.get('step', '?')}格式错误: {str(e)}"
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
                            is_pinned=step_data.get("is_pinned", False),
                            pinned_parameters=step_data.get(
                                "pinned_parameters"),
                            parameter_template=step_data.get(
                                "parameter_template"),
                            template_variables=step_data.get(
                                "template_variables"),
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

            # 合并 pinned_steps 到 initial_plan（pinned_steps 优先）
            if pinned_steps:
                if not initial_plan:
                    initial_plan = pinned_steps
                else:
                    # 将固定步骤放到初始计划开头
                    initial_plan = pinned_steps + initial_plan
                    # 重新编号
                    for i, step in enumerate(initial_plan):
                        step.step = i + 1

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

**⭐⭐⭐ 参数自动补充机制(极其重要!) ⭐⭐⭐**:
系统支持参数自动补充,因此:
1. 步骤的 parameters/pinned_parameters 可以为空
2. 执行时系统会自动从 state 中获取所需参数(如 template_id, document_ids, outline 等)
3. 如果 state 中没有,系统会使用 LLM 智能推断参数
4. **不要因为参数未定义而判定失败!** 这是系统的正常设计

**验证规则**:
- 如果Agent有**goals**:
  - 只需验证goals是否清晰、可实现
  - 检查系统工具是否足以支持这些目标
  - 不需要验证步骤(因为执行时动态规划)
  - Mermaid图只需展示高层逻辑流程
  
- 如果Agent有**steps**:
  1. **工具/智能体存在性**: 所有用到的工具/智能体是否都在系统中存在？
  2. **步骤顺序**: 步骤顺序是否大致合理？
  3. **逻辑连贯性**: 每个步骤之间的数据流转是否合理？
  
  **不需要验证**:
  - 参数是否完整(系统会自动补充)
  - read_fields/write_fields 是否定义(可选字段)
  - template_id 等必需参数(系统自动提供)

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
    "mermaid_diagram": "graph TD\n    A[...]"
}}

**判定为失败(is_valid=false)的情况**:
- 使用了不存在的工具或智能体
- 步骤顺序严重不合理(如先写文档再检索)
- 目标与系统能力完全不匹配

**不应该判定为失败的情况**:
- 参数未定义(系统自动补充)
- 缺少某个中间步骤(可以作为建议提出)
- read_fields/write_fields 未定义

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
    "mermaid_diagram": "graph TD\n    Start[[开始]] --> G1[目标: 快速检索相关文档]\n    G1 --> G2[目标: 生成准确答案]\n    G2 --> End[[结束]]"
}}
```

【示例2 - 步骤导向的Agent(参数未定义也应通过)】

输入的Agent定义：
```json
{{
    "name": "文档写作助手",
    "steps": [
        {{"step": 1, "name": "analyze_input", "description": "分析用户意图", "parameters": null}},
        {{"step": 2, "name": "es_fulltext_search", "description": "检索相关内容", "parameters": null}},
        {{"step": 3, "name": "generate_outline", "description": "生成大纲", "parameters": null}},
        {{"step": 4, "name": "document_compose", "description": "撰写文档", "parameters": null}}
    ]
}}
```

正确的输出(参数未定义不影响验证):
```json
{{
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "suggestions": ["建议在步骤2和3之间添加document_extraction步骤以提取内容"],
    "mermaid_diagram": "graph TD\n    Start[[开始]] --> Step1[步骤1: 分析用户意图]\n    Step1 --> Step2[步骤2: 检索相关内容]\n    Step2 --> Step3[步骤3: 生成大纲]\n    Step3 --> Step4[步骤4: 撰写文档]\n    Step4 --> End[[结束]]"
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
