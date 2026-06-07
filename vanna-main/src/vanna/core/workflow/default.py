"""
Default workflow handler implementation with setup health checking.

This module provides a default implementation of the WorkflowHandler interface
that provides a smart starter UI based on available tools and setup status.
"""

from typing import TYPE_CHECKING, List, Optional, Dict, Any
import traceback
import uuid
from .base import WorkflowHandler, WorkflowResult

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..user.models import User
    from ..storage import Conversation

# Import components at module level to avoid circular imports
from vanna.components import (
    UiComponent,
    RichTextComponent,
    StatusCardComponent,
    ButtonComponent,
    ButtonGroupComponent,
    SimpleTextComponent,
    CardComponent,
)

# Note: StatusCardComponent and ButtonGroupComponent are kept for /status command compatibility


class DefaultWorkflowHandler(WorkflowHandler):
    """Default workflow handler that provides setup health checking and starter UI.

    This handler provides a starter UI that:
    - Checks if run_sql tool is available (critical)
    - Checks if memory tools are available (warning if missing)
    - Checks if visualization tools are available
    - Provides appropriate setup guidance based on what's missing
    """

    def __init__(self, welcome_message: Optional[str] = None):
        """Initialize with optional custom welcome message.

        Args:
            welcome_message: Optional custom welcome message. If not provided,
                           generates one based on available tools.
        """
        self.welcome_message = welcome_message

    async def try_handle(
        self, agent: "Agent", user: "User", conversation: "Conversation", message: str
    ) -> WorkflowResult:
        """Handle basic commands, but mostly passes through to LLM."""

        # Handle basic help command
        if message.strip().lower() in ["/help", "help", "/h"]:
            # Check if user is admin
            is_admin = "admin" in user.group_memberships

            help_content = (
                "## 🤖 Vanna AI 助手\n\n"
                "我是您的 AI 数据分析助手！以下是我能帮助您的功能：\n\n"
                "**💬 自然语言查询**\n"
                '- "显示上季度的销售数据"\n'
                '- "哪些客户订单量最高？"\n'
                '- "创建月度收入图表"\n\n'
                "**🔧 命令**\n"
                "- `/help` - 显示此帮助信息\n"
            )

            if is_admin:
                help_content += (
                    "\n**🔒 管理员命令**\n"
                    "- `/status` - 检查系统设置状态\n"
                    "- `/memories` - 查看和管理最近的记忆\n"
                    "- `/delete [id]` - 根据ID删除记忆\n"
                )

            help_content += "\n\n用简单的中文问我任何关于您数据的问题！"

            return WorkflowResult(
                should_skip_llm=True,
                components=[
                    UiComponent(
                        rich_component=RichTextComponent(
                            content=help_content,
                            markdown=True,
                        ),
                        simple_component=None,
                    )
                ],
            )

        # Handle status check command (admin-only)
        if message.strip().lower() in ["/status", "status"]:
            # Check if user is admin
            if "admin" not in user.group_memberships:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# 🔒 访问被拒绝\n\n"
                                "`/status` 命令仅对管理员可用。\n\n"
                                "如果您需要访问系统状态信息，请联系您的系统管理员。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )
            return await self._generate_status_check(agent, user)

        # Handle get recent memories command (admin-only)
        if message.strip().lower() in [
            "/memories",
            "memories",
            "/recent_memories",
            "recent_memories",
        ]:
            # Check if user is admin
            if "admin" not in user.group_memberships:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# 🔒 访问被拒绝\n\n"
                                "`/memories` 命令仅对管理员可用。\n\n"
                                "如果您需要访问记忆管理功能，请联系您的系统管理员。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )
            return await self._get_recent_memories(agent, user, conversation)

        # Handle delete memory command (admin-only)
        if message.strip().lower().startswith("/delete "):
            # Check if user is admin
            if "admin" not in user.group_memberships:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# 🔒 访问被拒绝\n\n"
                                "`/delete` 命令仅对管理员可用。\n\n"
                                "如果您需要访问记忆管理功能，请联系您的系统管理员。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )
            memory_id = message.strip()[8:].strip()  # Extract ID after "/delete "
            return await self._delete_memory(agent, user, conversation, memory_id)

        # Don't handle other messages, pass to LLM
        return WorkflowResult(should_skip_llm=False)

    async def get_starter_ui(
        self, agent: "Agent", user: "User", conversation: "Conversation"
    ) -> Optional[List[UiComponent]]:
        """Generate starter UI based on available tools and setup status."""

        # Get available tools
        tools = await agent.tool_registry.get_schemas(user)
        tool_names = [tool.name for tool in tools]

        # Analyze setup
        setup_analysis = self._analyze_setup(tool_names)

        # Check if user is admin (has 'admin' in group memberships)
        is_admin = "admin" in user.group_memberships

        # Generate single concise card
        if self.welcome_message:
            # Use custom welcome message
            return [
                UiComponent(
                    rich_component=RichTextComponent(
                        content=self.welcome_message, markdown=True
                    ),
                    simple_component=None,
                )
            ]
        else:
            # Generate role-aware welcome card
            return [self._generate_starter_card(setup_analysis, is_admin)]

    def _generate_starter_card(
        self, analysis: Dict[str, Any], is_admin: bool
    ) -> UiComponent:
        """Generate a single concise starter card based on role and setup status."""

        if is_admin:
            # Admin view: includes setup status and memory management
            return self._generate_admin_starter_card(analysis)
        else:
            # User view: simple welcome message
            return self._generate_user_starter_card(analysis)

    def _generate_admin_starter_card(self, analysis: Dict[str, Any]) -> UiComponent:
        """Generate admin starter card with setup info and memory management."""

        # Build concise content
        if not analysis["has_sql"]:
            title = "管理员：需要设置"
            content = "**🔒 管理员视图** - 您拥有管理员权限，可以查看额外的系统信息。\n\n**Vanna AI** 需要 SQL 连接才能运行。\n\n请配置 SQL 工具开始使用。"
            status = "error"
            icon = "⚠️"
        elif analysis["is_complete"]:
            title = "管理员：系统就绪"
            content = "**🔒 管理员视图** - 您拥有管理员权限，可以查看额外的系统信息。\n\n**Vanna AI** 已完全配置并就绪。\n\n"
            content += "**设置状态:** SQL ✓ | 记忆 ✓ | 可视化 ✓"
            status = "success"
            icon = "✅"
        else:
            title = "管理员：系统就绪"
            content = "**🔒 管理员视图** - 您拥有管理员权限，可以查看额外的系统信息。\n\n**Vanna AI** 已准备好查询您的数据库。\n\n"
            setup_items = []
            setup_items.append("SQL ✓")
            setup_items.append("记忆 ✓" if analysis["has_memory"] else "记忆 ✗")
            setup_items.append("可视化 ✓" if analysis["has_viz"] else "可视化 ✗")
            content += f"**设置状态:** {' | '.join(setup_items)}"
            status = "warning" if not analysis["has_memory"] else "success"
            icon = "⚠️" if not analysis["has_memory"] else "✅"

        # Add memory management info for admins
        actions: List[Dict[str, Any]] = []
        if analysis["has_sql"]:
            actions.append(
                {
                    "label": "💡 帮助",
                    "action": "/help",
                    "variant": "secondary",
                }
            )

        if analysis["has_memory"]:
            content += "\n\n**记忆管理:** 工具和文本记忆功能已启用。作为管理员，您可以查看和管理这些记忆，帮助我从成功的查询中学习。"
            actions.append(
                {
                    "label": "🧠 查看记忆",
                    "action": "/memories",
                    "variant": "secondary",
                }
            )

        return UiComponent(
            rich_component=CardComponent(
                title=title,
                content=content,
                icon=icon,
                status=status,
                actions=actions,
                markdown=True,
            ),
            simple_component=None,
        )

    def _generate_user_starter_card(self, analysis: Dict[str, Any]) -> UiComponent:
        """Generate simple user starter view using RichTextComponent."""

        if not analysis["has_sql"]:
            content = (
                "`/help` - 显示此帮助信息"
            )
        else:
            content = (
                "# 👋 欢迎使用 Vanna AI\n\n"
                "我是您的 AI 数据分析助手。用简单的中文问我任何关于您数据的问题！\n\n"
                "输入 `/help` 查看我能做什么。"
            )

        return UiComponent(
            rich_component=RichTextComponent(content=content, markdown=True),
            simple_component=None,
        )

    def _analyze_setup(self, tool_names: List[str]) -> Dict[str, Any]:
        """Analyze the current tool setup and return status."""

        # Critical tools
        has_sql = any(
            name in tool_names
            for name in ["run_sql", "sql_query", "execute_sql", "query_sql"]
        )

        # Memory tools (important but not critical)
        has_search = "search_saved_correct_tool_uses" in tool_names
        has_save = "save_question_tool_args" in tool_names
        has_memory = has_search and has_save

        # Visualization tools (nice to have)
        has_viz = any(
            name in tool_names
            for name in [
                "visualize_data",
                "create_chart",
                "plot_data",
                "generate_chart",
            ]
        )

        # Other useful tools
        has_calculator = any(
            name in tool_names for name in ["calculator", "calc", "calculate"]
        )

        # Determine overall status
        is_complete = has_sql and has_memory and has_viz
        is_functional = has_sql

        return {
            "has_sql": has_sql,
            "has_memory": has_memory,
            "has_search": has_search,
            "has_save": has_save,
            "has_viz": has_viz,
            "has_calculator": has_calculator,
            "is_complete": is_complete,
            "is_functional": is_functional,
            "tool_count": len(tool_names),
            "tool_names": tool_names,
        }

    def _generate_setup_status_cards(
        self, analysis: Dict[str, Any]
    ) -> List[UiComponent]:
        """Generate status cards showing setup health (used by /status command)."""

        cards = []

        # SQL Tool Status (Critical)
        if analysis["has_sql"]:
            sql_card = StatusCardComponent(
                title="SQL 连接",
                status="success",
                description="数据库连接已配置就绪",
                icon="✅",
            )
        else:
            sql_card = StatusCardComponent(
                title="SQL 连接",
                status="error",
                description="未检测到 SQL 工具 - 数据分析需要此功能",
                icon="❌",
            )
        cards.append(UiComponent(rich_component=sql_card, simple_component=None))

        # Memory Tools Status (Important)
        if analysis["has_memory"]:
            memory_card = StatusCardComponent(
                title="记忆系统",
                status="success",
                description="搜索和保存工具已配置 - 我可以从成功的查询中学习",
                icon="🧠",
            )
        elif analysis["has_search"] or analysis["has_save"]:
            memory_card = StatusCardComponent(
                title="记忆系统",
                status="warning",
                description="记忆设置不完整 - 建议同时配置搜索和保存工具",
                icon="⚠️",
            )
        else:
            memory_card = StatusCardComponent(
                title="记忆系统",
                status="warning",
                description="未配置记忆工具 - 我无法记住成功的模式",
                icon="⚠️",
            )
        cards.append(UiComponent(rich_component=memory_card, simple_component=None))

        # Visualization Status (Nice to have)
        if analysis["has_viz"]:
            viz_card = StatusCardComponent(
                title="可视化",
                status="success",
                description="图表创建工具可用",
                icon="📊",
            )
        else:
            viz_card = StatusCardComponent(
                title="可视化",
                status="info",
                description="无可视化工具 - 结果将仅显示文本/表格",
                icon="📋",
            )
        cards.append(UiComponent(rich_component=viz_card, simple_component=None))

        return cards

    def _generate_setup_guidance(
        self, analysis: Dict[str, Any]
    ) -> Optional[UiComponent]:
        """Generate setup guidance based on what's missing (used by /status command)."""

        if not analysis["has_sql"]:
            # Critical guidance - need SQL
            content = (
                "## 🚨 需要设置\n\n"
                "要开始使用 Vanna AI，您需要配置 SQL 连接工具：\n\n"
                "```python\n"
                "from vanna.tools import RunSqlTool\n\n"
                "# 向代理添加 SQL 工具\n"
                "tool_registry.register(RunSqlTool(\n"
                '    connection_string="您的数据库连接字符串"\n'
                "))\n"
                "```\n\n"
                "**下一步:**\n"
                "1. 配置数据库连接\n"
                "2. 添加记忆工具用于学习\n"
                "3. 添加可视化工具用于图表"
            )

        else:
            # Improvement suggestions
            suggestions = []

            if not analysis["has_memory"]:
                suggestions.append(
                    "**🧠 添加记忆工具** - 帮助我从成功的查询中学习：\n"
                    "```python\n"
                    "from vanna.tools import SearchSavedCorrectToolUses, SaveQuestionToolArgs\n"
                    "tool_registry.register(SearchSavedCorrectToolUses())\n"
                    "tool_registry.register(SaveQuestionToolArgs())\n"
                    "```"
                )

            if not analysis["has_viz"]:
                suggestions.append(
                    "**📊 添加可视化** - 创建图表和图形：\n"
                    "```python\n"
                    "from vanna.tools import VisualizeDataTool\n"
                    "tool_registry.register(VisualizeDataTool())\n"
                    "```"
                )

            if suggestions:
                content = "## 💡 建议改进\n\n" + "\n\n".join(suggestions)
            else:
                return None  # No guidance needed

        return UiComponent(
            rich_component=RichTextComponent(content=content, markdown=True),
            simple_component=None,
        )

    async def _generate_status_check(
        self, agent: "Agent", user: "User"
    ) -> WorkflowResult:
        """Generate a detailed status check response."""

        # Get available tools
        tools = await agent.tool_registry.get_schemas(user)
        tool_names = [tool.name for tool in tools]
        analysis = self._analyze_setup(tool_names)

        # Generate status report
        status_content = "# 🔍 设置状态报告\n\n"

        if analysis["is_complete"]:
            status_content += (
                "🎉 **非常好！** 您的 Vanna AI 设置已完成并优化。\n\n"
            )
        elif analysis["is_functional"]:
            status_content += (
                "✅ **不错！** 您的设置可以正常工作，但还有改进空间。\n\n"
            )
        else:
            status_content += (
                "⚠️ **需要操作** - 您的设置需要配置。\n\n"
            )

        status_content += f"**检测到的工具数量:** {analysis['tool_count']} 个\n\n"

        # Tool breakdown
        status_content += "## 工具状态\n\n"
        status_content += f"- **SQL 连接:** {'✅ 可用' if analysis['has_sql'] else '❌ 缺失 (必需)'}\n"
        status_content += f"- **记忆系统:** {'✅ 完整' if analysis['has_memory'] else '⚠️ 不完整' if analysis['has_search'] or analysis['has_save'] else '❌ 缺失'}\n"
        status_content += f"- **可视化:** {'✅ 可用' if analysis['has_viz'] else '📋 仅文本/表格'}\n"
        status_content += f"- **计算器:** {'✅ 可用' if analysis['has_calculator'] else '➖ 不可用'}\n\n"

        if analysis["tool_names"]:
            status_content += (
                f"**可用工具:** {', '.join(sorted(analysis['tool_names']))}"
            )

        components = [
            UiComponent(
                rich_component=RichTextComponent(content=status_content, markdown=True),
                simple_component=None,
            )
        ]

        # Add status cards
        components.extend(self._generate_setup_status_cards(analysis))

        # Add guidance if needed
        guidance = self._generate_setup_guidance(analysis)
        if guidance:
            components.append(guidance)

        return WorkflowResult(should_skip_llm=True, components=components)

    async def _get_recent_memories(
        self, agent: "Agent", user: "User", conversation: "Conversation"
    ) -> WorkflowResult:
        """Get and display recent memories from agent memory."""
        try:
            # Check if agent has memory capability
            if not hasattr(agent, "agent_memory") or agent.agent_memory is None:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# ⚠️ 无记忆系统\n\n"
                                "代理记忆功能未配置。无法获取最近记忆。\n\n"
                                "要启用记忆功能，请在代理设置中配置 AgentMemory 实现。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )

            # Create tool context
            from vanna.core.tool import ToolContext

            context = ToolContext(
                user=user,
                conversation_id=conversation.id,
                request_id=str(uuid.uuid4()),
                agent_memory=agent.agent_memory,
            )

            # Get both tool memories and text memories
            tool_memories = await agent.agent_memory.get_recent_memories(
                context=context, limit=10
            )

            # Try to get text memories (may not be implemented in all memory backends)
            text_memories = []
            try:
                text_memories = await agent.agent_memory.get_recent_text_memories(
                    context=context, limit=10
                )
            except (AttributeError, NotImplementedError):
                # Text memories not supported by this implementation
                pass

            if not tool_memories and not text_memories:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# 🧠 最近记忆\n\n"
                                "未找到最近记忆。当您使用工具和提问时，\n"
                                "成功的模式将被保存到这里供将来参考。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )

            components = []

            # Header
            total_count = len(tool_memories) + len(text_memories)
            header_content = f"# 🧠 最近记忆\n\n找到 {total_count} 条最近记忆"
            components.append(
                UiComponent(
                    rich_component=RichTextComponent(
                        content=header_content, markdown=True
                    ),
                    simple_component=None,
                )
            )

            # Display text memories
            if text_memories:
                components.append(
                    UiComponent(
                        rich_component=RichTextComponent(
                            content=f"## 📝 文本记忆 ({len(text_memories)})",
                            markdown=True,
                        ),
                        simple_component=None,
                    )
                )

                for memory in text_memories:
                    # Create card with delete button
                    card_content = f"**内容:** {memory.content}\n\n"
                    if memory.timestamp:
                        card_content += f"**时间戳:** {memory.timestamp}\n\n"
                    card_content += f"**ID:** `{memory.memory_id}`"

                    card = CardComponent(
                        title="文本记忆",
                        content=card_content,
                        icon="📝",
                        actions=[
                            {
                                "label": "🗑️ 删除",
                                "action": f"/delete {memory.memory_id}",
                                "variant": "error",
                            }
                        ],
                    )
                    components.append(
                        UiComponent(rich_component=card, simple_component=None)
                    )

            # Display tool memories
            if tool_memories:
                components.append(
                    UiComponent(
                        rich_component=RichTextComponent(
                            content=f"## 🔧 工具记忆 ({len(tool_memories)})",
                            markdown=True,
                        ),
                        simple_component=None,
                    )
                )

                for tool_memory in tool_memories:
                    # Create card with delete button
                    card_content = f"**问题:** {tool_memory.question}\n\n"
                    card_content += f"**工具:** {tool_memory.tool_name}\n\n"
                    card_content += f"**参数:** `{tool_memory.args}`\n\n"
                    card_content += f"**成功:** {'✅ 是' if tool_memory.success else '❌ 否'}\n\n"
                    if tool_memory.timestamp:
                        card_content += f"**时间戳:** {tool_memory.timestamp}\n\n"
                    card_content += f"**ID:** `{tool_memory.memory_id}`"

                    card = CardComponent(
                        title=f"工具: {tool_memory.tool_name}",
                        content=card_content,
                        markdown=True,
                        icon="🔧",
                        status="success" if tool_memory.success else "error",
                        actions=[
                            {
                                "label": "🗑️ 删除",
                                "action": f"/delete {tool_memory.memory_id}",
                                "variant": "error",
                            }
                        ],
                    )
                    components.append(
                        UiComponent(rich_component=card, simple_component=None)
                    )

            return WorkflowResult(should_skip_llm=True, components=components)

        except Exception as e:
            traceback.print_exc()
            return WorkflowResult(
                should_skip_llm=True,
                components=[
                    UiComponent(
                        rich_component=RichTextComponent(
                            content=f"# ❌ 获取记忆失败\n\n"
                            f"获取最近记忆失败: {str(e)}\n\n"
                            f"这可能表示代理记忆配置有问题。",
                            markdown=True,
                        ),
                        simple_component=None,
                    )
                ],
            )

    async def _delete_memory(
        self, agent: "Agent", user: "User", conversation: "Conversation", memory_id: str
    ) -> WorkflowResult:
        """Delete a memory by its ID."""
        try:
            # Check if agent has memory capability
            if not hasattr(agent, "agent_memory") or agent.agent_memory is None:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# ⚠️ No Memory System\n\n"
                                "Agent memory is not configured. Cannot delete memories.",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )

            if not memory_id:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content="# ⚠️ 无效命令\n\n"
                                "请提供要删除的记忆ID。\n\n"
                                "用法: `/delete [memory_id]`",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )

            # Create tool context
            from vanna.core.tool import ToolContext

            context = ToolContext(
                user=user,
                conversation_id=conversation.id,
                request_id=str(uuid.uuid4()),
                agent_memory=agent.agent_memory,
            )

            # Try to delete as a tool memory first
            deleted = await agent.agent_memory.delete_by_id(context, memory_id)

            # If not found as tool memory, try as text memory
            if not deleted:
                try:
                    deleted = await agent.agent_memory.delete_text_memory(
                        context, memory_id
                    )
                except (AttributeError, NotImplementedError):
                    # Text memory deletion not supported by this implementation
                    pass

            if deleted:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content=f"# ✅ 记忆已删除\n\n"
                                f"成功删除ID为 `{memory_id}` 的记忆\n\n"
                                f"您可以使用 `/memories` 查看剩余记忆。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )
            else:
                return WorkflowResult(
                    should_skip_llm=True,
                    components=[
                        UiComponent(
                            rich_component=RichTextComponent(
                                content=f"# ❌ 记忆未找到\n\n"
                                f"未找到ID为 `{memory_id}` 的记忆\n\n"
                                f"使用 `/memories` 查看可用的记忆ID。",
                                markdown=True,
                            ),
                            simple_component=None,
                        )
                    ],
                )

        except Exception as e:
            traceback.print_exc()
            return WorkflowResult(
                should_skip_llm=True,
                components=[
                    UiComponent(
                        rich_component=RichTextComponent(
                            content=f"# ❌ 删除记忆失败\n\n"
                            f"删除记忆失败: {str(e)}\n\n"
                            f"这可能表示代理记忆配置有问题。",
                            markdown=True,
                        ),
                        simple_component=None,
                    )
                ],
            )
