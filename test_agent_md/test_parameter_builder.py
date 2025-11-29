"""
测试 CustomAgentExecutor 的参数构造机制
"""
import sys
sys.path.append("../backend")

from core.agents.custom_agent_executor import CustomAgentExecutor, get_nested_value


def test_get_nested_value():
    """测试嵌套值获取"""
    print("=== 测试 get_nested_value ===")

    data = {
        "outline": {
            "title": "测试文档",
            "sections": [
                {"title": "第一部分", "data_requirements": "查询1"},
                {"title": "第二部分", "data_requirements": "查询2"},
            ]
        },
        "documents": [{"id": 1, "title": "文档1"}]
    }

    # 测试1: 简单路径
    result = get_nested_value(data, "outline.title")
    print(f"outline.title = {result}")
    assert result == "测试文档", "简单路径测试失败"

    # 测试2: 数组路径
    result = get_nested_value(data, "outline.sections")
    print(f"outline.sections = {result}")
    assert len(result) == 2, "数组路径测试失败"

    # 测试3: 不存在的路径
    result = get_nested_value(data, "not.exist.path", default="默认值")
    print(f"not.exist.path = {result}")
    assert result == "默认值", "默认值测试失败"

    print("✅ get_nested_value 测试通过\n")


def test_build_tool_arguments():
    """测试参数构造"""
    print("=== 测试 build_tool_arguments ===")

    # 准备测试数据
    intermediate_data = {
        "outline": {
            "title": "测试文档",
            "sections": [
                {"title": "第一部分", "data_requirements": "产品介绍"},
                {"title": "第二部分", "data_requirements": "技术规格"},
                {"title": "第三部分", "data_requirements": "价格信息"},
            ]
        },
        "document_ids": [1, 2, 3],
        "documents": [
            {"id": 1, "title": "文档1"},
            {"id": 2, "title": "文档2"},
        ],
        "last_result": {
            "success": True,
            "data": {"key": "value"}
        }
    }

    # 测试1: generate_outline - 使用内置规则
    print("\n测试1: generate_outline (内置规则)")
    step = {
        "step": 1,
        "type": "tool",
        "name": "generate_outline",
        "description": "生成文档大纲"
    }
    args = CustomAgentExecutor.build_tool_arguments(
        step=step,
        query="请写一份产品介绍文档",
        template_id=100,
        intermediate_data=intermediate_data
    )
    print(f"构造的参数: {args}")
    assert args["query"] == "请写一份产品介绍文档"
    assert args["template_id"] == 100
    print("✅ generate_outline 测试通过")

    # 测试2: multi_query_search - 使用内置规则自动提取
    print("\n测试2: multi_query_search (内置规则 - 自动提取)")
    step = {
        "step": 2,
        "type": "tool",
        "name": "multi_query_search",
        "description": "多查询检索"
    }
    args = CustomAgentExecutor.build_tool_arguments(
        step=step,
        query="请写一份产品介绍文档",
        template_id=100,
        intermediate_data=intermediate_data
    )
    print(f"构造的参数: {args}")
    assert "queries" in args
    assert len(args["queries"]) == 3
    assert args["queries"][0] == "产品介绍"
    print("✅ multi_query_search (内置规则) 测试通过")

    # 测试3: multi_query_search - 使用配置的参数映射
    print("\n测试3: multi_query_search (配置映射)")
    step = {
        "step": 2,
        "type": "tool",
        "name": "multi_query_search",
        "description": "多查询检索",
        "parameter_mappings": {
            "queries": {
                "source": "intermediate",
                "path": "outline.sections"
            },
            "template_id": {
                "source": "context"
            },
            "top_k_per_query": {
                "source": "value",
                "value": 10
            }
        }
    }
    args = CustomAgentExecutor.build_tool_arguments(
        step=step,
        query="请写一份产品介绍文档",
        template_id=100,
        intermediate_data=intermediate_data
    )
    print(f"构造的参数: {args}")
    assert "queries" in args
    assert args["template_id"] == 100
    assert args["top_k_per_query"] == 10
    print("✅ multi_query_search (配置映射) 测试通过")

    # 测试4: get_document_contents - 使用内置规则
    print("\n测试4: get_document_contents (内置规则)")
    step = {
        "step": 3,
        "type": "tool",
        "name": "get_document_contents",
        "description": "获取文档内容"
    }
    args = CustomAgentExecutor.build_tool_arguments(
        step=step,
        query="请写一份产品介绍文档",
        template_id=100,
        intermediate_data=intermediate_data
    )
    print(f"构造的参数: {args}")
    assert args["document_ids"] == [1, 2, 3]
    print("✅ get_document_contents 测试通过")

    # 测试5: 从 previous (last_result) 获取
    print("\n测试5: 从 last_result 获取参数")
    step = {
        "step": 4,
        "type": "tool",
        "name": "custom_tool",
        "description": "自定义工具",
        "parameter_mappings": {
            "data_key": {
                "source": "previous",
                "path": "data.key"
            },
            "query_text": {
                "source": "query"
            }
        }
    }
    args = CustomAgentExecutor.build_tool_arguments(
        step=step,
        query="测试查询",
        template_id=100,
        intermediate_data=intermediate_data
    )
    print(f"构造的参数: {args}")
    assert args["data_key"] == "value"
    assert args["query_text"] == "测试查询"
    print("✅ 从 last_result 获取参数测试通过")

    print("\n✅ 所有 build_tool_arguments 测试通过\n")


if __name__ == "__main__":
    try:
        test_get_nested_value()
        test_build_tool_arguments()
        print("\n🎉 所有测试通过！")
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
