下面是一份面向“整个框架”的优化版 Markdown，完全按你提出的两阶段思路设计，强调：先用大模型做能力匹配与流程规划，再在执行阶段由大模型对 state 进行期望判定与控制流监控。你可以把它作为框架级的约定文档，用于驱动解析、验证与执行器的统一升级。

# Agent框架优化方案（两阶段：规划 → 执行）

## 目标与原则
- 目标：将用户的自然语言智能体描述转化为“可执行的、可监控的”步骤计划；执行过程中对 state 持续评估，具备重试、回退、跳转与兜底能力。
- 原则：
  - 使用统一的 state dict 管理步骤间的数据流；在初始化时预定义核心字段，并允许按工具元数据动态扩展。
  - 动态工具选择：由大模型基于“工具能力目录”自主选择合适工具，生成步骤与控制规则。
  - 每一步必须定义“期望（expectations）”与“失败处置（on_fail）”，通过 checkpoint 结构表达，确保可执行与可验证。

---

## 阶段一：规划（LLM 对智能体描述进行能力匹配与流程生成）

### 输入
- 用户的智能体描述（Markdown，含目标、约束、偏好、示例等）
- 系统能力目录：
  - Tools Catalog（从工具注册表动态拼装）：每个工具的
    - name / description / capabilities
    - input_schema（参数）与 output_schema（输出字段，包括将写入的状态键与摘要）
  - State Keys Catalog（动态汇总）：所有工具声明可能写入的状态键（含来源工具与类型），与框架预定义核心键合并去重

### 规划规则（LLM必须遵守）
1. 能力匹配：仅使用目录中存在的工具；若能力缺失，返回 errors 并给出新增工具建议（含输入/输出设计）。
2. 步骤生成：输出“可执行计划（JSON）”，每步包含
   - step（序号，从1开始）
   - type（tool | agent）
   - name（工具/智能体名，必须存在于目录）
   - description（这一步做什么）
   - parameters（工具参数的核心子集，参照 input_schema）
   - checkpoint（期望与失败处置，详见下文）
3. 状态键声明：每步应明确期望写入/读取的状态键，且必须属于工具 output_schema 或 State Keys Catalog。
4. 执行模式：execution_pattern ∈ [tool_only | agent_only | agent_chain | hybrid | llm_direct]，与步骤类型相匹配。
5. Mermaid流程图：基于 checkpoint 生成带分支/循环的流程图（仅用于展示，不影响执行）。

### 规划输出（JSON结构）
```json
{
  "name": "智能体名称",
  "description": "智能体描述",
  "execution_pattern": "hybrid",
  "steps": [
    {
      "step": 1,
      "type": "tool",
      "name": "generate_outline",
      "description": "生成大纲",
      "parameters": { "query": "<from user or state>" },
      "checkpoint": {
        "expectations": [
          { "left": "summary.sections_count", "op": ">", "right": 0 }
        ],
        "on_fail": { "retry_limit": 2, "set_state": { "outline": { "title": "fallback", "sections": [] } } }
      }
    }
  ],
  "errors": [],
  "warnings": []
}
```

---

## 阶段二：执行（LLM对state进行分析与监控，每步有期望与控制）

### 统一的 state dict（可扩展）
- 核心预定义键（初始化时存在）：
  - outline: { title, sections[] }
  - document_ids: string[]
  - documents: [{ id, title, content? }]
  - extracted_content: { sectionKey: content[] }
  - composed_document: { title, content, word_count, sections_count }
  - reviewed_document: { ... }
  - metrics: { outlineComplete?, searchCoverage?, extractionMissing?, composeQuality?, reviewIssues? }
  - retry_counts: { [stepName]: number }
- 动态扩展键：
  - 从 Tools Catalog 的 output_schema 聚合出的所有键，按工具执行写入 state；摘要统一写入 result.summary（或工具直接提供）。

### 执行控制模型（通用）
- 指针模型：执行器采用 while 指针 i（从0开始对应 step=1），支持 goto 跳转、重试循环、兜底写入。
- 期望评估（checkpoint）：
  - expectations: 数组；每项为 { left, op, right }
    - left：点路径，优先从 result.summary 查找，找不到再从 state 查找（例如 "summary.document_count" 或 "documents.length"）
    - op：支持 ==, !=, >, >=, <, <=, truthy, falsy
    - right：常量值或缺省（truthy/falsy不需要right）
  - on_fail：失败处置
    - retry_limit: number（未达上限则重做当前步）
    - goto: number（跳到指定步骤序号；支持 if/else 分支落点）
    - set_state: object（兜底写入 state 若期望长期无法满足）
- 监控与事件：
  - stage_start / stage_complete / stage_error
  - stage_retry（附重试计数），stage_jump（附跳转目标），stage_fallback（兜底写入详情）

### 示例：通用步骤定义（用于所有智能体）
```json
{
  "step": 2,
  "type": "tool",
  "name": "<tool_from_catalog>",
  "description": "在目录中声明的能力",
  "parameters": {
    // 仅包含 input_schema 中允许的参数
  },
  "checkpoint": {
    "expectations": [
      { "left": "summary.document_count", "op": ">", "right": 0 },
      { "left": "documents.length", "op": ">=", "right": 3 }
    ],
    "on_fail": {
      "retry_limit": 2,
      "goto": 1,
      "set_state": { "metrics": { "searchCoverage": 0.5 } }
    }
  }
}
```

### LLM在执行阶段的作用
- 读取压缩后的 state（含历史摘要与关键字段），辅助构造下一步工具参数（与工具 input_schema 对齐）。
- 当期望未满足时，依据 checkpoint 自动决策：重试、回退（goto）、或兜底写入；避免“自由发挥”的不确定性。

---

## Mermaid流程图（展示规范）
- 每个含 checkpoint 的步骤生成一个决策节点，明确“满足/不满足”的分支与可能的循环（重试）和回退（goto）。
- 不使用样式；只用 graph TD 基本语法。
- 用于前端展示与调试，不作为执行源。

---

## 错误与建议返回
- 当能力缺失或输出键不被任何工具生成：
  - errors：详细列出缺失能力与工具，并给出“新增工具建议”（含输入/输出设计）。
  - warnings：可替代方案或质量风险说明。
- 当存在可能的无限循环（无 retry_limit 且闭环存在）：
  - warnings：提示增加 retry_limit 或设置全局最大迭代次数。

---

## 接口约定（摘要）
- 规划接口（parse）：输入用户Markdown + Tools/State目录，输出JSON计划（steps含checkpoint），并给出 errors/warnings 与 Mermaid。
- 验证接口（validate）：校验工具存在性、输出键合法性、顺序合理性、控制流可行性；输出 is_valid 与 Mermaid。
- 执行接口（execute）：按 JSON计划 + checkpoint 控制运行；对 state 进行动态更新与监控，SSE流输出各阶段事件。

---

## 说明
- 该方案适配所有智能体：LLM先“选工具+定步骤”，再“盯state做控制”。框架侧统一管理 state 与控制流，避免在执行阶段让 LLM自由决定跳转路径而失控。
- 预定义 state dict 满足项目规范；动态扩展键从工具 output_schema 聚合，兼容不断新增的工具与能力。
- 只要各工具声明清晰的 input/output schema，LLM即可在规划阶段做出稳健选择；执行器在运行阶段严格依据 checkpoint 实施控制。