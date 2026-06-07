"""Tool for visualizing DataFrame data from CSV files."""

from typing import Optional, Type
import logging
import pandas as pd
from pydantic import BaseModel, Field

from vanna.core.tool import Tool, ToolContext, ToolResult
from vanna.components import (
    UiComponent,
    ChartComponent,
    NotificationComponent,
    ComponentType,
    SimpleTextComponent,
)

from .file_system import FileSystem, LocalFileSystem
from vanna.integrations.plotly import PlotlyChartGenerator

logger = logging.getLogger(__name__)


class VisualizeDataArgs(BaseModel):
    """Arguments for visualize_data tool."""

    filename: str = Field(description="要可视化的 CSV 文件名称")
    title: Optional[str] = Field(
        default=None, description="图表的可选标题"
    )


class VisualizeDataTool(Tool[VisualizeDataArgs]):
    """Tool that reads CSV files and generates visualizations using dependency injection."""

    def __init__(
        self,
        file_system: Optional[FileSystem] = None,
        plotly_generator: Optional[PlotlyChartGenerator] = None,
    ):
        """Initialize the tool with FileSystem and PlotlyChartGenerator.

        Args:
            file_system: FileSystem implementation for reading CSV files (defaults to LocalFileSystem)
            plotly_generator: PlotlyChartGenerator for creating Plotly charts (defaults to PlotlyChartGenerator())
        """
        self.file_system = file_system or LocalFileSystem()
        self.plotly_generator = plotly_generator or PlotlyChartGenerator()

    @property
    def name(self) -> str:
        return "visualize_data"

    @property
    def description(self) -> str:
        return "从 CSV 文件创建可视化图表。该工具会根据数据自动选择合适的图表类型。"

    def get_args_schema(self) -> Type[VisualizeDataArgs]:
        return VisualizeDataArgs

    async def execute(
        self, context: ToolContext, args: VisualizeDataArgs
    ) -> ToolResult:
        """Read CSV file and generate visualization."""
        try:
            logger.info(f"Starting visualization for file: {args.filename}")

            # Read the CSV file using FileSystem
            csv_content = await self.file_system.read_file(args.filename, context)
            logger.info(f"Read {len(csv_content)} bytes from CSV file")

            # Parse CSV into DataFrame
            import io

            df = pd.read_csv(io.StringIO(csv_content))
            logger.info(
                f"Parsed DataFrame with shape {df.shape}, columns: {df.columns.tolist()}, dtypes: {df.dtypes.to_dict()}"
            )

            # Generate title
            title = args.title or f"{args.filename} 的可视化"

            # Generate chart using PlotlyChartGenerator
            logger.info("Generating chart...")
            chart_dict = self.plotly_generator.generate_chart(df, title)
            logger.info(
                f"Chart generated, type: {type(chart_dict)}, keys: {list(chart_dict.keys()) if isinstance(chart_dict, dict) else 'N/A'}"
            )

            # Create result message
            row_count = len(df)
            col_count = len(df.columns)
            result = f"已从 '{args.filename}' 创建可视化图表（{row_count} 行，{col_count} 列）。"

            # Create ChartComponent
            logger.info("Creating ChartComponent...")
            chart_component = ChartComponent(
                chart_type="plotly",
                data=chart_dict,
                title=title,
                config={
                    "data_shape": {"rows": row_count, "columns": col_count},
                    "source_file": args.filename,
                },
            )
            logger.info("ChartComponent created successfully")

            logger.info("Creating ToolResult...")
            tool_result = ToolResult(
                success=True,
                result_for_llm=result,
                ui_component=UiComponent(
                    rich_component=chart_component,
                    simple_component=SimpleTextComponent(text=result),
                ),
                metadata={
                    "filename": args.filename,
                    "rows": row_count,
                    "columns": col_count,
                    "chart": chart_dict,
                },
            )
            logger.info("ToolResult created successfully")
            return tool_result

        except FileNotFoundError as e:
            logger.error(f"File not found: {args.filename}", exc_info=True)
            error_message = f"文件未找到：{args.filename}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        type=ComponentType.NOTIFICATION,
                        level="error",
                        message=error_message,
                    ),
                    simple_component=SimpleTextComponent(text=error_message),
                ),
                error=str(e),
                metadata={"error_type": "file_not_found"},
            )
        except pd.errors.ParserError as e:
            logger.error(f"CSV parse error for {args.filename}", exc_info=True)
            error_message = f"解析 CSV 文件 '{args.filename}' 失败：{str(e)}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        type=ComponentType.NOTIFICATION,
                        level="error",
                        message=error_message,
                    ),
                    simple_component=SimpleTextComponent(text=error_message),
                ),
                error=str(e),
                metadata={"error_type": "csv_parse_error"},
            )
        except ValueError as e:
            logger.error(f"Visualization error for {args.filename}", exc_info=True)
            error_message = f"无法可视化数据：{str(e)}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        type=ComponentType.NOTIFICATION,
                        level="error",
                        message=error_message,
                    ),
                    simple_component=SimpleTextComponent(text=error_message),
                ),
                error=str(e),
                metadata={"error_type": "visualization_error"},
            )
        except Exception as e:
            logger.error(
                f"Unexpected error creating visualization for {args.filename}",
                exc_info=True,
            )
            error_message = f"创建可视化时出错：{str(e)}"
            return ToolResult(
                success=False,
                result_for_llm=error_message,
                ui_component=UiComponent(
                    rich_component=NotificationComponent(
                        type=ComponentType.NOTIFICATION,
                        level="error",
                        message=error_message,
                    ),
                    simple_component=SimpleTextComponent(text=error_message),
                ),
                error=str(e),
                metadata={"error_type": "general_error"},
            )
