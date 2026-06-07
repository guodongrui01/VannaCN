"""
Agent memory tools.

This module provides agent memory operations through an abstract AgentMemory interface,
allowing for different implementations (local vector DB, remote cloud service, etc.).
The tools access AgentMemory via ToolContext, which is populated by the Agent.
"""

import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from vanna.core.tool import Tool, ToolContext, ToolResult
from vanna.core.agent.config import UiFeature
from vanna.capabilities.agent_memory import AgentMemory
from vanna.components import (
    UiComponent,
    StatusBarUpdateComponent,
    CardComponent,
)


class SaveQuestionToolArgsParams(BaseModel):
    """Parameters for saving question-tool-argument combinations."""

    question: str = Field(description="被问到的原始问题")
    tool_name: str = Field(
        description="成功使用的工具名称"
    )
    args: Dict[str, Any] = Field(
        description="传递给工具的参数"
    )


class SearchSavedCorrectToolUsesParams(BaseModel):
    """Parameters for searching saved tool usage patterns."""

    question: str = Field(
        description="要查找相似工具使用模式的问题"
    )
    limit: Optional[int] = Field(
        default=10, description="返回结果的最大数量"
    )
    similarity_threshold: Optional[float] = Field(
        default=0.7, description="结果的最小相似度分数（0.0-1.0）"
    )
    tool_name_filter: Optional[str] = Field(
        default=None, description="筛选特定工具名称的结果"
    )


class SaveTextMemoryParams(BaseModel):
    """Parameters for saving free-form text memories."""

    content: str = Field(description="要保存为记忆的文本内容")


class SaveQuestionToolArgsTool(Tool[SaveQuestionToolArgsParams]):
    """Tool for saving successful question-tool-argument combinations."""

    @property
    def name(self) -> str:
        return "save_question_tool_args"

    @property
    def description(self) -> str:
        return (
            "保存成功的问题-工具-参数组合以供将来参考"
        )

    def get_args_schema(self) -> Type[SaveQuestionToolArgsParams]:
        return SaveQuestionToolArgsParams

    async def execute(
        self, context: ToolContext, args: SaveQuestionToolArgsParams
    ) -> ToolResult:
        """Save the tool usage pattern to agent memory."""
        try:
            await context.agent_memory.save_tool_usage(
                question=args.question,
                tool_name=args.tool_name,
                args=args.args,
                context=context,
                success=True,
            )

            success_msg = (
                f"成功保存 '{args.tool_name}' 工具的使用模式"
            )
            return ToolResult(
                success=True,
                result_for_llm=success_msg,
                ui_component=UiComponent(
                    rich_component=StatusBarUpdateComponent(
                        status="success",
                        message="已保存到记忆",
                        detail=f"已保存 '{args.tool_name}' 的模式",
                    ),
                    simple_component=None,
                ),
            )

        except Exception as e:
            error_message = f"保存记忆失败：{str(e)}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=StatusBarUpdateComponent(
                        status="error", message="保存记忆失败", detail=str(e)
                    ),
                    simple_component=None,
                ),
                error=str(e),
            )


class SearchSavedCorrectToolUsesTool(Tool[SearchSavedCorrectToolUsesParams]):
    """Tool for searching saved tool usage patterns."""

    @property
    def name(self) -> str:
        return "search_saved_correct_tool_uses"

    @property
    def description(self) -> str:
        return "根据问题搜索相似的工具使用模式"

    def get_args_schema(self) -> Type[SearchSavedCorrectToolUsesParams]:
        return SearchSavedCorrectToolUsesParams

    async def execute(
        self, context: ToolContext, args: SearchSavedCorrectToolUsesParams
    ) -> ToolResult:
        """Search for similar tool usage patterns."""
        try:
            results = await context.agent_memory.search_similar_usage(
                question=args.question,
                context=context,
                limit=args.limit or 10,
                similarity_threshold=args.similarity_threshold or 0.7,
                tool_name_filter=args.tool_name_filter,
            )

            if not results:
                no_results_msg = (
                    "没有找到与此问题相似的工具使用模式。"
                )

                # Check if user has access to detailed memory results
                ui_features_available = context.metadata.get(
                    "ui_features_available", []
                )
                show_detailed_results = (
                    UiFeature.UI_FEATURE_SHOW_MEMORY_DETAILED_RESULTS
                    in ui_features_available
                )

                # Create UI component based on access level
                if show_detailed_results:
                    # Admin view: Show card indicating 0 results
                    ui_component = UiComponent(
                        rich_component=CardComponent(
                            title="🧠 记忆搜索：0 个结果",
                            content="没有找到与此问题相似的工具使用模式。\n\n搜索了代理记忆但未找到匹配项。",
                            icon="🔍",
                            status="info",
                            collapsible=True,
                            collapsed=True,
                            markdown=True,
                        ),
                        simple_component=None,
                    )
                else:
                    # Non-admin view: Simple status message
                    ui_component = UiComponent(
                        rich_component=StatusBarUpdateComponent(
                            status="idle",
                            message="未找到相似模式",
                            detail="已搜索代理记忆",
                        ),
                        simple_component=None,
                    )

                return ToolResult(
                    success=True,
                    result_for_llm=no_results_msg,
                    ui_component=ui_component,
                )

            # Format results for LLM
            results_text = f"找到了 {len(results)} 个相似的工具使用模式：\n\n"
            for i, result in enumerate(results, 1):
                memory = result.memory
                results_text += f"{i}. {memory.tool_name}（相似度：{result.similarity_score:.2f}）\n"
                results_text += f"   问题：{memory.question}\n"
                results_text += f"   参数：{memory.args}\n\n"

            logger.info(f"Agent memory search results: {results_text.strip()}")

            # Check if user has access to detailed memory results
            ui_features_available = context.metadata.get("ui_features_available", [])
            show_detailed_results = (
                UiFeature.UI_FEATURE_SHOW_MEMORY_DETAILED_RESULTS
                in ui_features_available
            )

            # Create UI component based on access level
            if show_detailed_results:
                # Admin view: Show detailed results in collapsible card
                detailed_content = "**传递给 LLM 的检索记忆：**\n\n"
                for i, result in enumerate(results, 1):
                    memory = result.memory
                    detailed_content += f"**{i}. {memory.tool_name}**（相似度：{result.similarity_score:.2f}）\n"
                    detailed_content += f"- **问题：** {memory.question}\n"
                    detailed_content += f"- **参数：** `{memory.args}`\n"
                    if memory.timestamp:
                        detailed_content += f"- **时间戳：** {memory.timestamp}\n"
                    if memory.memory_id:
                        detailed_content += f"- **ID：** `{memory.memory_id}`\n"
                    detailed_content += "\n"

                ui_component = UiComponent(
                    rich_component=CardComponent(
                        title=f"🧠 记忆搜索：{len(results)} 个结果",
                        content=detailed_content.strip(),
                        icon="🔍",
                        status="info",
                        collapsible=True,
                        collapsed=True,  # Start collapsed to avoid clutter
                        markdown=True,  # Render content as markdown
                    ),
                    simple_component=None,
                )
            else:
                # Non-admin view: Simple status message
                ui_component = UiComponent(
                    rich_component=StatusBarUpdateComponent(
                        status="success",
                        message=f"找到了 {len(results)} 个相似模式",
                        detail="从代理记忆中检索",
                    ),
                    simple_component=None,
                )

            return ToolResult(
                success=True,
                result_for_llm=results_text.strip(),
                ui_component=ui_component,
            )

        except Exception as e:
            error_message = f"搜索记忆失败：{str(e)}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=StatusBarUpdateComponent(
                        status="error", message="搜索记忆失败", detail=str(e)
                    ),
                    simple_component=None,
                ),
                error=str(e),
            )


class SaveTextMemoryTool(Tool[SaveTextMemoryParams]):
    """Tool for saving free-form text memories."""

    @property
    def name(self) -> str:
        return "save_text_memory"

    @property
    def description(self) -> str:
        return "保存自由格式的文本记忆，用于重要的见解、观察或上下文"

    def get_args_schema(self) -> Type[SaveTextMemoryParams]:
        return SaveTextMemoryParams

    async def execute(
        self, context: ToolContext, args: SaveTextMemoryParams
    ) -> ToolResult:
        """Save a text memory to agent memory."""
        try:
            text_memory = await context.agent_memory.save_text_memory(
                content=args.content, context=context
            )

            success_msg = (
                f"成功保存文本记忆，ID：{text_memory.memory_id}"
            )
            return ToolResult(
                success=True,
                result_for_llm=success_msg,
                ui_component=UiComponent(
                    rich_component=StatusBarUpdateComponent(
                        status="success",
                        message="已保存文本记忆",
                        detail=f"ID：{text_memory.memory_id}",
                    ),
                    simple_component=None,
                ),
            )

        except Exception as e:
            error_message = f"保存文本记忆失败：{str(e)}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=StatusBarUpdateComponent(
                        status="error",
                        message="保存文本记忆失败",
                        detail=str(e),
                    ),
                    simple_component=None,
                ),
                error=str(e),
            )
