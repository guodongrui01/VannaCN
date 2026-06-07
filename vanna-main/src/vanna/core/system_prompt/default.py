"""
Default system prompt builder implementation with memory workflow support.

This module provides a default implementation of the SystemPromptBuilder interface
that automatically includes memory workflow instructions when memory tools are available.
"""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime

from .base import SystemPromptBuilder

if TYPE_CHECKING:
    from ..tool.models import ToolSchema
    from ..user.models import User


class DefaultSystemPromptBuilder(SystemPromptBuilder):
    """Default system prompt builder with automatic memory workflow integration.

    Dynamically generates system prompts that include memory workflow
    instructions when memory tools (search_saved_correct_tool_uses and
    save_question_tool_args) are available.
    """

    def __init__(self, base_prompt: Optional[str] = None):
        """Initialize with an optional base prompt.

        Args:
            base_prompt: Optional base system prompt. If not provided, uses a default.
        """
        self.base_prompt = base_prompt

    async def build_system_prompt(
        self, user: "User", tools: List["ToolSchema"]
    ) -> Optional[str]:
        """
        Build a system prompt with memory workflow instructions.

        Args:
            user: The user making the request
            tools: List of tools available to the user

        Returns:
            System prompt string with memory workflow instructions if applicable
        """
        if self.base_prompt is not None:
            return self.base_prompt

        # Check which memory tools are available
        tool_names = [tool.name for tool in tools]
        has_search = "search_saved_correct_tool_uses" in tool_names
        has_save = "save_question_tool_args" in tool_names
        has_text_memory = "save_text_memory" in tool_names

        # Get today's date
        today_date = datetime.now().strftime("%Y-%m-%d")

        # Base system prompt
        prompt_parts = [
            f"你是 Vanna，一个 AI 数据分析师助手，旨在帮助用户完成数据分析任务。今天的日期是 {today_date}。",
            "",
            "回复指南：",
            "- 你必须始终使用中文与用户交流。",
            "- 任何关于你做了什么或观察结果的总结应该是最后一步。",
            "- 使用可用的工具来帮助用户实现他们的目标。",
            "- 当你执行查询时，原始结果会在你的回复之外显示给用户，所以你不需要在回复中包含它。专注于总结和解释结果。",
        ]

        if tools:
            prompt_parts.append(
                f"\n你可以使用以下工具：{', '.join(tool_names)}"
            )

        # Add memory workflow instructions based on available tools
        if has_search or has_save or has_text_memory:
            prompt_parts.append("\n" + "=" * 60)
            prompt_parts.append("记忆系统：")
            prompt_parts.append("=" * 60)

        if has_search or has_save:
            prompt_parts.append("\n1. 工具使用记忆（结构化工作流）：")
            prompt_parts.append("-" * 50)

        if has_search:
            prompt_parts.extend(
                [
                    "",
                    "• 在执行任何工具（run_sql、visualize_data 或 calculator）之前，你必须先调用 search_saved_correct_tool_uses 并传入用户的问题，以检查是否存在类似问题的成功模式。",
                    "",
                    "• 在继续其他工具调用之前，查看搜索结果（如果有）来指导你的方法。",
                ]
            )

        if has_save:
            prompt_parts.extend(
                [
                    "",
                    "• 成功执行产生正确且有用结果的工具后，你必须调用 save_question_tool_args 来保存成功的模式以供将来使用。",
                ]
            )

        if has_search or has_save:
            prompt_parts.extend(
                [
                    "",
                    "工作流示例：",
                    "  • 用户提出问题",
                    f'  • 首先：调用 search_saved_correct_tool_uses(question="用户的问题")'
                    if has_search
                    else "",
                    "  • 然后：根据搜索结果和问题执行适当的工具",
                    f'  • 最后：如果成功，调用 save_question_tool_args(question="用户的问题", tool_name="使用的工具", args={{你使用的参数}})'
                    if has_save
                    else "",
                    "",
                    "不要跳过搜索步骤，即使你认为你知道如何回答。不要忘记保存成功的执行结果。"
                    if has_search
                    else "",
                    "",
                    "唯一不需要先搜索的例外情况是：",
                    '  • 当用户明确询问工具本身时（如"列出工具"）',
                    "  • 当用户正在测试或要求你演示保存/搜索功能本身时",
                ]
            )

        if has_text_memory:
            prompt_parts.extend(
                [
                    "",
                    "2. 文本记忆（领域知识和上下文）：",
                    "-" * 50,
                    "",
                    "• save_text_memory：保存关于数据库、架构或领域的重要上下文",
                    "",
                    "使用文本记忆保存：",
                    "  • 数据库架构详情（列含义、数据类型、关系）",
                    "  • 公司特定的术语和定义",
                    "  • 此数据库的查询模式或最佳实践",
                    "  • 关于业务或数据的领域知识",
                    "  • 用户对查询或可视化的偏好",
                    "",
                    "不要保存：",
                    "  • 已在工具使用记忆中捕获的信息",
                    "  • 一次性查询结果或临时观察",
                    "",
                    "示例：",
                    '  • save_text_memory(content="status 列使用 1 表示活跃，0 表示非活跃")',
                    '  • save_text_memory(content="MRR 在我们的架构中表示月度经常性收入")',
                    "  • save_text_memory(content=\"始终排除邮箱包含 'test' 的测试账户\")",
                ]
            )

        if has_search or has_save or has_text_memory:
            # Remove empty strings from the list
            prompt_parts = [part for part in prompt_parts if part != ""]

        return "\n".join(prompt_parts)
