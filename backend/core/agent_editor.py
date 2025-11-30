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
            from core.registry import get_agents_description, get_tools_description

            tools_desc = get_tools_description()
            agents_desc = get_agents_description()

            system_prompt = f"""你是一个专业的Agent流程规划器和工具验证专家。

【系统能力清单】

## 可用工具
{tools_desc}

## 可用智能体
{agents_desc}

【任务说明】
用户会用Markdown描述他想要实现的Agent功能。你的核心任务是：

1. **深度理解意图**：理解用户的真实需求和业务目标
2. **智能规划流程**：根据系统能力，设计最优的执行步骤
3. **精准验证工具**：逐一验证每个步骤所需的工具/智能体是否存在
4. **明确指出缺失**：准确列出缺少的工具，并给出具体建议

【重要原则】

1. **理解优先于解析**
   - 不要死板地按照用户写的步骤来，而是理解其意图后重新规划
   - 用户描述可能不完整或不准确，你需要补充和优化
   - 如果用户只说了目标（如"写文章"），你要拆解成具体步骤

2. **严格验证工具存在性**
   - 必须逐个检查步骤中提到的每个功能
   - 对比【系统能力清单】，确认是否有对应的工具/智能体
   - 如果找不到精确匹配的工具，看是否有类似功能的工具可替代
   - **不要假设或猜测**：如果没有对应的工具，必须明确指出

3. **清晰的缺失反馈**
   - 缺少工具时，要准确说明：缺少什么功能、用来做什么
   - 给出建议的工具名称（符合命名规范）
   - 说明为什么需要这个工具

【规划流程】

**第一步：深度分析意图**
- 用户想要实现什么最终目标？
- 这个目标涉及哪些业务环节？
- 典型的使用场景是什么？

**第二步：拆解关键步骤**
- 实现这个目标需要哪些不可或缺的步骤？
- 每个步骤的输入输出是什么？
- 步骤之间的依赖关系如何？

**第三步：精确匹配工具**
对于每个步骤：
1. 明确这一步需要什么能力（如：规划结构、检索文档、提取信息等）
2. 在【系统能力清单】中查找对应的工具/智能体
3. 如果有多个可选工具，选择最匹配的
4. 如果没有任何匹配的工具，记录缺失项

**第四步：验证完整性**
- 所有关键步骤都有对应的工具吗？
- 是否存在无法实现的步骤？
- 能否用现有工具的组合达到目的？

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
        "缺少工具：需要[规划文章结构]功能，但系统中没有对应的工具",
        "缺少工具：需要[提取关键信息]功能，但系统中没有对应的工具",
        "详细说明：[规划文章结构]用于分析主题并生成文章大纲，当前系统只有文档检索和问答能力",
        "建议方案1：添加 plan_article_structure 工具，接收主题参数，返回文章结构",
        "建议方案2：添加 extract_key_points 工具，从文档中提取关键信息点"
    ],
    "warnings": [
        "可以使用现有的 retrieval_agent 检索相关文档",
        "可以使用现有的 qa_agent 生成内容，但缺少结构规划能力"
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

**示例2 - 用户描述了步骤但工具不存在**
用户输入：
```markdown
# Agent: 邮件发送助手
**描述**: 根据文档内容自动发送邮件通知
## 执行步骤
### 步骤1：检索文档
### 步骤2：提取邮件内容
### 步骤3：发送邮件
```

你的深度分析：

**步骤1：检索文档**
- 需要的能力：文档检索
- 系统中的工具：✅ retrieval_agent 可以检索文档

**步骤2：提取邮件内容**  
- 需要的能力：从文档中提取特定内容
- 系统中的工具：⚠️ qa_agent 可以基于文档生成内容，但不是专门的提取工具

**步骤3：发送邮件**
- 需要的能力：邮件发送
- 系统中的工具：❌ 完全没有邮件相关的工具

返回：
```json
{{
    "name": "邮件发送助手",
    "description": "根据文档内容自动发送邮件通知",
    "errors": [
        "缺少工具：[发送邮件] - 系统中没有任何邮件发送相关的工具",
        "详细说明：系统当前只支持文档检索、问答、统计和分析功能，不具备外部系统集成能力",
        "建议添加工具：send_email(to, subject, content, attachments) → 发送邮件",
        "还需考虑：邮件模板、收件人管理、发送日志等功能"
    ],
    "warnings": [
        "可以使用 retrieval_agent 检索文档",
        "可以使用 qa_agent 生成邮件内容",
        "但最关键的邮件发送功能缺失，无法完成整个流程"
    ]
}}
```

**示例3 - 缺少关键能力（写文章场景）**
用户输入：
```markdown
# Agent: 写文章助手
**描述**: 根据主题自动规划文章结构、查询关键信息、摘取要素、组合内容并排版

## 执行步骤
### 步骤1: 规划文章结构
### 步骤2: 查询关键信息  
### 步骤3: 摘取要素
### 步骤4: 组合内容
### 步骤5: 排版优化
```

你的深度分析：

**意图理解**：
- 用户想要一个能够自动创作文章的AI助手
- 核心诉求是结构化的写作流程

**步骤拆解与工具匹配**：
1. 规划文章结构 → ❌ 系统中没有文章规划工具
2. 查询关键信息 → ✅ 可以用 retrieval_agent 检索相关文档
3. 摘取要素 → ❌ 系统中没有信息提取工具
4. 组合内容 → ⚠️ qa_agent 可以生成内容，但不是专门的组合工具
5. 排版优化 → ❌ 系统中没有排版工具

**缺失分析**：
- 核心缺失：缺少文章结构规划能力
- 关键缺失：缺少信息提取和要素摘取能力  
- 辅助缺失：缺少专门的排版工具

返回：
```json
{{
    "name": "写文章助手",
    "description": "根据主题自动规划文章结构、查询关键信息、摘取要素、组合内容并排版",
    "errors": [
        "缺少工具：[规划文章结构] - 系统需要能够根据主题生成文章大纲的工具",
        "缺少工具：[摘取要素] - 系统需要能够从文档中提取关键信息点的工具",
        "缺少工具：[排版优化] - 系统需要能够优化文章格式的工具",
        "详细说明：虽然系统有 retrieval_agent（检索）和 qa_agent（问答），但这两个工具主要用于问答场景，不适合结构化的文章创作流程",
        "建议添加工具1：plan_article_structure(topic, requirements) → 生成文章结构大纲",
        "建议添加工具2：extract_key_points(documents, focus) → 从文档中提取关键要点",
        "建议添加工具3：compose_article(outline, key_points) → 按大纲组织内容",
        "建议添加工具4：format_article(content) → 格式化和排版文章"
    ],
    "warnings": [
        "可以临时使用 retrieval_agent 检索主题相关的文档",
        "可以尝试用 qa_agent 生成部分内容，但效果可能不理想",
        "建议：如果只是想基于现有文档回答问题，使用标准的检索+问答流程即可"
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
        from core.registry import get_agents_description, get_tools_description

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
