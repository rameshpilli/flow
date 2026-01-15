# app/tools/cliet_orchestrator.py
import sys
import json
import asyncio
import logging
from mcp import types
from datetime import datetime
from typing import Optional, List, Union
from typing import List, Dict, Any, Optional, Callable
from app.config import config
from pydantic import ValidationError
from app.models import validate_orchestrator_input, format_validation_error

from app.processors import (
    RevenueProcessor,
    TrendsProcessor,
    ProductTrendsProcessor,
    CVFinancialProcessor,
    CVTrendByRegionProcessor,
    CVBreakdownByRegionProcessor,
    RWALeverageProcessor,
    LoanDetailsProcessor,
    CoverageProcessor,
    ContactsProcessor,
    MeetingCalendarProcessor,
    InteractionSummaryProcessor,
    TopTradesProcessor,
    AllTradesProcessor,
    LRPMProcessor
)

def get_mcp():
    from app.mcp_singleton import get_mcp_instance
    return get_mcp_instance()

# Runtime mcp resolve object
class MCPProxy:
    def __getattr__(self, name):
        mcp_instance = get_mcp()
        if mcp_instance is None:
            raise RuntimeError("MCP instance not yet initialized")
        return getattr(mcp_instance, name)

mcp = MCPProxy()


logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

class ClientOverviewOrchestrator:
    """
    Orchestrates multiple client data resources using MCP resources
    and applies the same processing logic as individual tools.
    """

    def __init__(self):
        # Initialize processors
        self.revenue_processor = RevenueProcessor()
        self.trends_processor = TrendsProcessor()
        self.product_trends_processor = ProductTrendsProcessor()
        self.cv_financial_processor = CVFinancialProcessor()
        self.region_trends_processor = CVTrendByRegionProcessor()
        self.region_product_breakdown_processor = CVBreakdownByRegionProcessor()
        self.rwa_leverage_processor = RWALeverageProcessor()
        self.loan_details_processor = LoanDetailsProcessor()
        self.coverage_processor = CoverageProcessor()
        self.contacts_processor = ContactsProcessor()
        self.meeting_calendar_processor = MeetingCalendarProcessor()
        self.interaction_summary_processor = InteractionSummaryProcessor()
        self.top_trades_processor = TopTradesProcessor()
        self.all_trades_processor = AllTradesProcessor()
        self.lrpm_processor = LRPMProcessor()

        self.tool_registry: Dict[str, Dict[str, Any]] = {
            "revenue": {
                "uri_template": (
                    "clientview://client_revenue/"
                    "{cdrid}/{employee_id}/{currency}/{period_type}/{metric}/{hierarchy_depth}"
                ),
                "processor": self.revenue_processor.process,
                "description": (
                    "COMPREHENSIVE client revenue metrics: Includes FYTD/CYTD, Historical 5-year trends, Primary/Secondary CV values with growth rates, current average RWA/leverage metrics, Internal rankings and Senior Executive Interactions "
                    "hierarchy_depth: (0=Relationship Level and 1=Client Level information) + basic main product data, NOT USED for detailed product breakdown information. "
                    "Single source for ALL revenue-related questions. and ANSWERS QUESTIONS LIKE: 'What is BlackRock's FYTD revenue?', 'How did revenue grow vs last year?', "
                    "'What's the primary vs secondary revenue split?', 'How does BlackRock rank in Capital Markets?', "
                    "'Show 5-year revenue trends', 'What's the YTD growth percentage?', 'Avg RWA and Avg leverage metrics?' "
                    "NOTE: For detailed product breakdowns by specific business lines, use product_breakdown_trends tool instead."
                ),
            },
            "revenue_trends": {
                "uri_template": (
                    "clientview://client_cv_trend/"
                    "{cdrid}/{employee_id}/{timeperiod}/{currency}/{period_type}/{hierarchy_depth}/{hierarchy_filter}/{metric}"
                ),
                "processor": self.trends_processor.process,
                "description": (
                    "Historical CV trends over time periods (yearly or monthly). "
                    "Use for questions about revenue trends, growth patterns, and time-series analysis. "
                    "Supports both yearly (YR) and monthly (MT) granularity with fiscal/calendar periods. "
                    "ANSWERS QUESTIONS LIKE: 'Show monthly revenue trends', 'What's the yearly CV progression?', "
                    "'How has revenue changed over the last 5 years?', 'Give me month-by-month breakdown'."
                ),
            },
            "product_breakdown_trends": {
                "uri_template": (
                    "clientview://client_cv_by_product_trend/"
                    "{cdrid}/{employee_id}/{currency}/{period_type}/{metric}/{hierarchy_depth}/{hierarchy_filter}"
                ),
                "processor": self.product_trends_processor.process,
                "description": "Complete product breakdown hierarchy breakdown with 3-level depth showing client revenue by product line. "
                "Returns Level 1 divisions (Capital Markets, Non-Capital Markets), Level 2 business lines (Global Markets Products, Corporate Banking, Investment Banking), and Level 3 products (Spread, Equities, Central Funding, Macro, etc.). "
                "Use this for product performance analysis, revenue attribution questions, and business line comparisons.",
            },
            "region_trends": {
                "uri_template": (
                    "clientview://client_cv_by_region_trend/"
                    "{cdrid}/{employee_id}/{currency}/{metric}/{period_type}/{timeperiod}/{hierarchy_depth}/{hierarchy_filter}"
                ),
                "processor": self.region_trends_processor.process,
                "description": (
                    "Client Value Trend By Region: Regional revenue aggregates showing total revenue by geography "
                    "(CAN, USA, EUR, APAC, LATAM, OTHER) with multi-year trends (2022-2026) and YTD analysis. "
                    "Use for high-level regional performance questions: 'How much revenue from USA?', "
                    "'Which region performs best?', 'Show revenue by region', 'Regional breakdown over time'. "
                    "Returns pre-aggregated regional totals (no product details)."
                ),
            },
            "region_product_breakdown": {
                "uri_template": (
                    "clientview://client_cv_by_region_breakdown/"
                    "{cdrid}/{employee_id}/{currency}/{metric}/{period_type}/{timeperiod}/{hierarchy_depth}/{hierarchy_filter}"
                ),
                "processor": self.region_product_breakdown_processor.process,
                "description": (
                    "Client Value Breakdown By Region: Detailed product-level revenue distributed across regions. "
                    "Shows hierarchical product structure (Capital Markets > Global Markets Products > Spread/Equities/Macro, etc.) "
                    "with regional breakdown for each product. Use for product-geography analysis: "
                    "'Which products drive USA revenue?', 'Show Capital Markets by region', "
                    "'How is Spread product distributed geographically?', 'Product performance by country'. "
                    "Returns full product hierarchy with regional metrics for each product."
                ),
            },
            "rwa_leverage": {
                "uri_template": (
                    "clientview://client_rwa_leverage_footprint/"
                    "{cdrid}/{employee_id}/{currency}/{metric}/{period_type}/{reportable_mask}"
                ),
                "processor": self.rwa_leverage_processor.process,
                "description": "Client RWA and Leverage Footprint including risk-weighted assets, balance sheet leverage, product-level breakdown, and CV/RWA & CV/Leverage efficiency ratios",
            },
            "cv_financial_resources_by_product": {
                "uri_template": (
                    "clientview://client_cv_financial_resources_by_product/"
                    "{cdrid}/{employee_id}/{currency}/{metric}/{period_type}/{hierarchy_depth}/{hierarchy_filter}"
                ),
                "processor": self.cv_financial_processor.process,
                "description": (
                    "CV and Financial Resources by Product (LTM): "
                    "Last Twelve Months average revenue and capital resource consumption across "
                    "Capital Markets Products. Provides hierarchical product breakdown with "
                    "RWA, Leverage, and efficiency metrics. Focus on resource-intensive products "
                    "and capital allocation analysis. Data available in CAD only. "
                    "Missing products: Metals, CFG, TRS, Bond Forwards, AAG, Alternate Finance"
                ),
            },
            "loan_details": {
                "uri_template": (
                    "clientview://client_hierarchy_loan_details/"
                    "{cdrid}"
                ),
                "processor": self.loan_details_processor.process,
                "description": "Client loan authorized and outstanding amounts, classification, and hierarchy information at both relationship (L1) and client (L2) levels",
            },
            "client_coverage": {
                "uri_template": (
                    "clientview://client_coverage/"
                    "{cdrid}/{employee_id}/{hierarchy_depth}/{hierarchy_type}"
                ),
                "processor": self.coverage_processor.process,
                "description": (
                    "Client coverage team showing who covers this client across LOB, Product, and Region. "
                    "Returns team member details (name, title, role, email) organized by business line "
                    "and regional coverage (APAC, Australia, Canada, Europe, US). "
                    "Use for questions about: 'Who covers this client?', 'Who is the relationship manager?', "
                    "'What is the coverage team structure?', 'Who handles FX in Europe for this client?'"
                ),
            },
            "client_contacts": {
                "uri_template": (
                    "clientview://client_contacts/"
                    "{cdrid}/{employee_id}/{hierarchy_depth}/{hierarchy_type}/{page_size}"
                ),
                "processor": self.contacts_processor.process,
                "description": (
                    "Client Contacts: Complete contact information for client personnel including names, titles, "
                    "email addresses, phone numbers, locations (city, state, country), and organizational hierarchy. "
                    "Returns contact details with links to call reports, Research One, and 6ix Degrees. "
                    "Use for questions about: 'Who are the contacts at this client?', 'Show me contact information', "
                    "'Who is the CFO/CEO?', 'What are the email addresses?', 'Show contacts in Toronto', "
                    "'How many C-level contacts do we have?', 'Show contact details with phone numbers'. "
                    "Default: Returns up to 100 contacts at relationship level (hierarchy_depth=0)."
                ),
            },
            "meeting_calendar": {
                "uri_template": (
                    "clientview://meeting_calendar/"
                    "{cdrid}/{employee_id}/{from_date}/{to_date}/{limit}"
                ),
                "processor": self.meeting_calendar_processor.process,
                "description": (
                    "Meeting Calendar: Upcoming and past meetings with the client. "
                    "Automatically splits meetings into upcoming (future) and past (completed) with comprehensive summaries. "
                    "Returns counts by meeting type, LOB, C-level attendance, and meeting details (subject, attendees, location, dates). "
                    "Use for questions about: 'What meetings do we have with this client?', 'Show upcoming meetings', "
                    "'Who met with the client last month?', 'How many C-level meetings did we have?', "
                    "'What was discussed in recent meetings?', 'Show past meetings in Q3'. "
                    "Default: Last 6 months, limited to 20 most recent. Set limit=0 for all meetings."
                ),
            },
            "interaction_summary": {
                "uri_template": (
                    "clientview://interaction_summary/"
                    "{cdrid}/{employee_id}/{from_date}/{to_date}/{limit}"
                ),
                "processor": self.interaction_summary_processor.process,
                "description": (
                    "Interaction Summary: Comprehensive aggregated view of ALL client interactions (meetings, conferences, call reports). "
                    "Provides detailed breakdowns: by interaction type (Meeting/Conference), by LOB (FICC/GIB/CM), "
                    "by internal attendee (top RBC employees), by external contact (top client contacts). "
                    "Returns total interaction counts, C-level engagement stats, and most recent interactions with full details. "
                    "Use for questions about: 'Summarize interactions with this client', 'Who are the top contacts?', "
                    "'How many meetings did Charlie Cifrino have?', 'Show interaction breakdown by type', "
                    "'What's our engagement level with this client?', 'Who are the most active internal attendees?', "
                    "'How many C-level interactions occurred?'. "
                    "Default: Last 1 year, limited to 20 most recent. Set limit=0 for all interactions."
                ),
            },
            "top_trades": {
                "uri_template": (
                    "clientview://client_top_trades/"
                    "{cdrid}/{employee_id}/{hierarchy_depth}/{start_date}/{end_date}/{sort_by}/{currency}/{reportable_mask}/{metric}"
                ),
                "processor": self.top_trades_processor.process,
                "description": (
                    "Top Trades: Client's highest-value trades sorted by Client Value or Notional. "
                    "Shows individual trade details including date, product (L3/L4, Product Type), financial metrics "
                    "(Client Value, Notional), trade currency, region, and salesperson. "
                    "Use for questions about: 'What are the top trades?', 'Show largest trades by value', "
                    "'Which trades generated most revenue?', 'Show top trades in Q3', "
                    "'What products are in the biggest trades?', 'Top trades by notional'. "
                    "Default: Last 90 days, sorted by Client Value, reportable trades only."
                ),
            },
            "all_trades": {
                "uri_template": (
                    "clientview://client_all_trades/"
                    "{cdrid}/{employee_id}/{config_json}"
                ),
                "processor": self.all_trades_processor.process,
                "description": (
                    "All Trades: Complete trade list with advanced filtering. "
                    "Returns all client trades matching criteria with full trade details: date, client hierarchy, "
                    "product hierarchy (L3-L6), financial metrics (revenue, quantity), salesperson, desk, region, "
                    "trade characteristics (primary/secondary, voice/electronic, risk quality). "
                    "Supports flexible filtering by product, book code, desk, and time period. "
                    "Use for questions about: 'Show all trades', 'List trades in last 30 days', "
                    "'What trades did we do?', 'Show trade details by product', 'All trades by salesperson', "
                    "'Trade history with filters', 'Detailed trade breakdown'. "
                    "Default: Last 30 days (L30), up to 5000 trades, all products, reportable trades only."
                ),
            },
            "lrpm": {
                "uri_template": (
                    "clientview://client_lrpm/"
                    "{cdrid}/{employee_id}"
                ),
                "processor": self.lrpm_processor.process,
                "description": (
                    "LRPM (Lending Relationship Profitability Model): Calculates costs based on balance sheet "
                    "and liquidity utilization. Returns profitability metrics over two time periods: "
                    "LTM (Last Twelve Months - short term) and OTL (Over The Life - 5 years long term). "
                    "Includes RWA metrics (lending/non-lending), RREG ratios (return on regulatory capital), "
                    "revenue breakdown, loan amounts (authorized, on/off balance sheet), quadrant positioning, "
                    "and shortfall analysis (capital, liquidity, RWA, revenue). "
                    "Use for questions about: 'What is the lending profitability?', 'Show LRPM metrics', "
                    "'What is the client quadrant?', 'Regulatory capital return', 'RWA analysis', "
                    "'Balance sheet utilization', 'Profitability over time', 'Shortfall analysis'. "
                    "Note: Data available in CAD only, sourced via CSI."
                ),
            },
        }

    # ---------- Normalization helpers ----------

    async def _fetch_resource(self, name: str, uri: str) -> Dict[str, Any]:
        """Call an MCP resource by URI with error handling"""
        try:
            logger.info(f"Fetching resource {name} -> {uri}")
            
            # Fix: read_resource returns an Iterable[ReadResourceContents]
            resource_contents = await mcp._read_resource(uri)
            
            resource_list = list(resource_contents)
            if not resource_list:
                return {"status": "error", "tool_name": name, "error": "No resource content returned", "data": None}

            first_resource = resource_list[0]
            if hasattr(first_resource, 'content'):
                
                content_data = json.loads(first_resource.content)
                return {"status": "success", "tool_name": name, "data": content_data}
            else:
                # Direct data
                return {"status": "success", "tool_name": name, "data": first_resource}
                
        except Exception as e:
            logger.error(f"Resource {name} failed: {e}", exc_info=True)
            return {"status": "error", "tool_name": name, "error": str(e), "data": None}

    # ---------- Orchestration ----------
    async def _execute_tool_safe(
        self,
        tool_name: str,
        tool_config: Dict[str, Any],
        params: Dict[str, Any],
        rounding: bool = False,
    ) -> Dict[str, Any]:
        try:
            logger.info(f"Executing tool: {tool_name}")
            logger.info(f"Parameters passed: {params}")
            start_time = datetime.now()

            tool_params = params.copy()
            if tool_name == "client_coverage":
                tool_params.setdefault("hierarchy_type", "CLIENT")

            if tool_name == "client_contacts":
                tool_params.setdefault("hierarchy_type", "CLIENT")
                tool_params.setdefault("page_size", "100")

            # Set defaults for date-based tools
            if tool_name in ["meeting_calendar", "interaction_summary", "top_trades"]:
                from datetime import timedelta
                today = datetime.now()

                # meeting_calendar defaults: last 6 months
                if tool_name == "meeting_calendar":
                    tool_params.setdefault("from_date", (today - timedelta(days=180)).strftime("%Y-%m-%d"))
                    tool_params.setdefault("to_date", today.strftime("%Y-%m-%d"))
                    tool_params.setdefault("limit", "20")

                # interaction_summary defaults: last 1 year
                elif tool_name == "interaction_summary":
                    tool_params.setdefault("from_date", (today - timedelta(days=365)).strftime("%Y-%m-%d"))
                    tool_params.setdefault("to_date", today.strftime("%Y-%m-%d"))
                    tool_params.setdefault("limit", "20")

                # top_trades defaults: last 30 days
                elif tool_name == "top_trades":
                    tool_params.setdefault("start_date", (today - timedelta(days=30)).strftime("%Y-%m-%d"))
                    tool_params.setdefault("end_date", today.strftime("%Y-%m-%d"))
                    tool_params.setdefault("sort_by", "Client Value")
                    tool_params.setdefault("reportable_mask", params.get("reportable_mask", 1))
                    tool_params.setdefault("metric", params.get("metric", "CV"))

            # Set defaults for all_trades (config_json based)
            if tool_name == "all_trades":
                import json
                config = {
                    "hierarchyDepth": tool_params.get("hierarchy_depth", "0"),
                    "currency": tool_params.get("currency", "USD"),
                    "timePeriod": "L30",  # Last 30 days default
                    # "limitRowCount": 5000
                    "limitRowCount": 1000

                }
                tool_params["config_json"] = json.dumps(config)

            # GET URI from template
            uri = tool_config["uri_template"].format(**tool_params)
            logger.info(f"Resource URI: {uri}")

            # Call MCP resource
            fetch_res = await self._fetch_resource(tool_name, uri)
            raw_data = fetch_res["data"] if fetch_res["status"] == "success" else None

            processor = tool_config["processor"]

            if tool_name == "revenue":
                processed_data = processor(
                    raw_data, 
                    params["cdrid"], 
                    params["period_type"],
                    params["currency"],
                    rounding
                )
                logger.info(f"Calling revenue processor with: cdrid={params['cdrid']}, period_type={params['period_type']}, currency={params['currency']}")
            elif tool_name == "revenue_trends":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params["timeperiod"],  # time_period parameter (YR or MT)
                    params["period_type"],
                    params["currency"],
                    params["metric"],
                    rounding
                )
                logger.info(f"Calling revenue trends processor with: cdrid={params['cdrid']}, time_period={params['timeperiod']}, period_type={params['period_type']}, currency={params['currency']}")
            elif tool_name == "product_breakdown_trends":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params["currency"],
                    params["period_type"],
                    params["metric"],
                    params["hierarchy_depth"],
                    params["hierarchy_filter"],
                    rounding,
                )
            elif tool_name == "region_trends":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params["currency"],
                    params["period_type"],
                    params["timeperiod"],
                    params["metric"],
                    params["hierarchy_depth"],
                    params["hierarchy_filter"],
                    rounding,
                )
            elif tool_name == "region_product_breakdown":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params["currency"],
                    params["period_type"],
                    params["timeperiod"],
                    params["metric"],
                    params["hierarchy_depth"],
                    params["hierarchy_filter"],
                    rounding,
                )
            elif tool_name == "rwa_leverage":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params["currency"],
                    params["period_type"],
                    params["metric"],
                    rounding,
                )
            elif tool_name == "cv_financial_resources_by_product":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params["currency"],
                    params["metric"],
                    params["period_type"],
                    params["hierarchy_depth"],
                    params["hierarchy_filter"],
                    rounding,
                )
            elif tool_name == "loan_details":
                processed_data = processor(
                    raw_data,
                    params["cdrid"]
                )
            elif tool_name == "client_coverage":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params.get("hierarchy_depth", "0")
                )
            elif tool_name == "meeting_calendar":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params.get("from_date"),
                    params.get("to_date"),
                    int(params.get("limit", 20))
                )
            elif tool_name == "interaction_summary":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params.get("from_date"),
                    params.get("to_date"),
                    int(params.get("limit", 20))
                )
            elif tool_name == "client_contacts":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params.get("hierarchy_depth", "0"),
                    int(params.get("page_size", 100))
                )
            elif tool_name == "top_trades":
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params.get("start_date"),
                    params.get("end_date"),
                    params.get("sort_by", "Client Value"),
                    params.get("currency", "USD"),
                    params.get("hierarchy_depth", "0"),
                    rounding
                )
            elif tool_name == "all_trades":
                # config_json is already set in tool_params
                processed_data = processor(
                    raw_data,
                    params["cdrid"],
                    params.get("currency", "USD"),
                    params.get("hierarchy_depth", "0"),
                    "L30",  # time_period
                    5000,  # limit_row_count
                    rounding
                )
            elif tool_name == "lrpm":
                processed_data = processor(
                    raw_data,
                    params["cdrid"]
                )
            else:
                processed_data = {"status": "error", "message": f"Unknown tool: {tool_name}"}

            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Tool {tool_name} completed in {execution_time:.2f}s")

            return {
                "status": "success",
                "data": processed_data,
                "execution_time": execution_time,
                "tool_name": tool_name,
            }

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {str(e)}", exc_info=True)
            return {"status": "error", "error": str(e), "tool_name": tool_name, "data": None}

    async def execute_overview(
        self,
        client_id: str,
        employee_id: int,
        tools: Optional[List[str]],
        currency: str = "USD", # USD or CAD
        period_type: str = "fiscal", # fiscal or calendar
        time_period: str = "YR",
        metric: str = "CV",
        hierarchy_depth: str = "1",
        hierarchy_filter: str = "client",
        reportable_mask: int = 1,
        rounding: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute multiple tools using MCP resources and apply tool processing logic.
        - If tools is None → run ALL tools.
        - If tools is []  → error (explicit empty selection).
        - Else            → run only the valid ones (preserve order); error if none valid.
        """
        logger.info(f"Starting client overview for CDRID {client_id} with tools: {tools}")

        if tools is None:
            selected_tools = list(self.tool_registry.keys())
            invalid_tools: List[str] = []
        else:
            invalid_tools = [t for t in tools if t not in self.tool_registry]
            selected_tools = [t for t in tools if t in self.tool_registry]

        if tools == []:
            return {
                "status": "error",
                "message": "No tools selected (empty list provided). Provide a list like ['revenue'] or omit the field to run all.",
                "available_tools": list(self.tool_registry.keys()),
            }

        if not selected_tools:
            return {
                "status": "error",
                "message": "No valid tools specified",
                "invalid_tools": invalid_tools,
                "available_tools": list(self.tool_registry.keys()),
            }

        base_params = {
            "cdrid": client_id,
            "employee_id": employee_id,
            "currency": currency,
            "period_type": period_type,
            "timeperiod": time_period,
            "metric": metric,
            "hierarchy_depth": hierarchy_depth,
            "hierarchy_filter": hierarchy_filter,
            "reportable_mask": reportable_mask,
        }

        logger.info(f"Base parameters for tools execution: {base_params}")
        logger.info(f"Selected tools for execution: {selected_tools}")

        tasks = []
        for tool_name in selected_tools:
            tool_config = self.tool_registry[tool_name]
            tasks.append(self._execute_tool_safe(tool_name, tool_config, base_params, rounding))

        start_time = datetime.now()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_execution_time = (datetime.now() - start_time).total_seconds()

        successful_tools: List[str] = []
        failed_tools: List[Dict[str, Any]] = []
        tool_data: Dict[str, Any] = {}

        for result in results:
            if isinstance(result, dict):
                tool_name: str = result.get("tool_name", "unknown")
                if result.get("status") == "success":
                    successful_tools.append(tool_name)
                    tool_data[tool_name] = result["data"]
                else:
                    failed_tools.append({"tool": tool_name, "error": result.get("error")})
            else:
                logger.error(f"Unexpected exception in tool execution: {result}")
                failed_tools.append({"tool": "unknown", "error": str(result)})

        overview_response = {
            "status": "success" if successful_tools else ("partial" if tool_data else "failed"),
            "client_id": client_id,
            "_NOTE": "FINANCIAL DATA: All numbers are exact. Present raw API backend responses as-is on the UI. Do not round or modify values.",
            "execution_summary": {
                "total_time_seconds": round(total_execution_time, 3),
                "successful_tools": successful_tools,
                "failed_tools": failed_tools,
                "requested_tools": selected_tools if tools is not None else "all",
                "execution_params": {
                    "currency": currency,
                    "period_type": period_type,
                    "time_period": time_period,
                    "metric": metric,
                },
            },
            "dashboard_data": tool_data,
        }

        logger.info(f"Overview completed: {len(successful_tools)} successful, {len(failed_tools)} failed")
        return overview_response

orchestrator = ClientOverviewOrchestrator()

##################################
# GET CLIENT OVERVIEW - TOOL
##################################
@mcp.tool(
    name="get_client_overview",
    description=(
        "STEP 4: Dashboard Execution Tool - FINAL step that generates comprehensive client analysis. "
        "INTELLIGENT STREAMING: Automatically uses progressive streaming for 6+ tools (better UX), regular response for 1-5 tools. "
        "REQUIRED WORKFLOW: "
        "1. STEP 1: Call get_clients_cdrid to get client_id "
        "2. STEP 2: Call user_info_tool to get employee_id from user authentication "
        "3. STEP 3: Call list_available_resources to see available tools "
        "4. STEP 4: Call this tool with client_id AND employee_id AND available tool from previous steps "
        "SIGNATURE REQUIREMENTS (Only these inputs are required in function signature): "
        "- client_id: Client CDRID from step 1 (get_clients_cdrid) - REQUIRED "
        "- employee_id: User employee ID for authentication and access control - REQUIRED from step 2 (get_user_info tool) "
        "- tools: Resource names from step 3 (list_available_resources) - OPTIONAL, defaults to all tools if omitted "
        "OPTIONAL PARAMETERS (Include only when user specifies, with valid options): "
        "- currency: 'USD' (default) or 'CAD' "
        "- period_type: 'fiscal' (default) or 'calendar' "
        "- time_period: 'YR' (default) for yearly, 'MT' for monthly "
        "- metric: 'CV' (default) or 'CV_RBCCM' "
        "- hierarchy_depth: '1' (default, Client L2 level) or '0' (Relationship L1 level) "
        "- hierarchy_filter: 'client' (default) or 'children' "
        "- reportable_mask: 1 (default, normal) or 129 (for PTV) "
        "- rounding: false (default), set to true ONLY when user explicitly asks for rounded numbers "
        "- streaming: Auto-detects (None). Set true for progressive results, false for single response (rarely needed). "
        "HIERARCHY MAPPING (only specify if user mentions level): "
        "- 'Client Relationship L1 level' or 'relationship level' → hierarchy_depth='0' "
        "- 'Client L2 level' or 'client level' → hierarchy_depth='1' (default) "
        "EXECUTION: For ANY client analysis question, you MUST first call list_available_resources to see available tools and their descriptions, "
        "then select the appropriate tool(s) based on what the user is asking for. "
        "EXAMPLES: revenue questions, current Avg Leverage and Avg RWA questions (NOT for complete breakdown) → tools=['revenue'], and revenue trends year over year questions → tools=['revenue'], product breakdown → tools=['product_breakdown_trends'], CV and financial resources analysis → tools=['cv_financial_resources_by_product'], "
        "Questions about capital allocation, resource efficiency, RWA/Leverage breakdown by product → tools=['cv_financial_resources_by_product']. "
        "Questions about Last Twelve Months (LTM) financial performance by business line → tools=['cv_financial_resources_by_product']. and questions about who covers a client or company → tools=['client_coverage']."
        "OUTPUT: Complete client overview with revenue, trends, rankings, and performance metrics. Auto-streams for 6+ tools."
        "IMPORTANT: Return all numeric values exactly as provided in the API response - do NOT round, format, or modify numbers unless the user explicitly requests rounding."
        "Preserve full precision (e.g., Show 32.2323 million not 32.23 million). Financial accuracy is CRITICAL."
    ),
    tags=["dashboard", "execution", "step3"],
    annotations={
        "execution_order": 3,
        "requires_output_from": ["get_clients_cdrid", "list_available_resources"],
        "inputs": {"client_id": "Client CDRID from get_clients_cdrid", "tools": "Resource names from list_available_resources (optional)"},
        "outputs": {"client_dashboard": "Complete dashboard analysis"},
        "repeatable": True
    },
    enabled=True
)
async def get_client_overview(
    client_id: str,
    employee_id: int,
    tools: Optional[Union[str, List[str]]] = None,  # accept string OR list OR None
    currency: str = "USD", # or CAD
    period_type: str = "fiscal", # or calendar
    time_period: str = "YR", # "YR" for yearly, "MT" for monthly (Not "MO")
    metric: str = "CV", # or CV_RBCCM
    hierarchy_depth: str = "1", # 0=(Relationship - L1) & 1=(Client - L2)
    hierarchy_filter: str = "client",
    reportable_mask: int = 1,
    rounding: bool = False, # Set to True only when user requests rounded values.
    streaming: Optional[bool] = None,  # Auto-detect if None: True for 6+ tools, False otherwise
) -> str:
    # ) -> types.CallToolResult:
    """
    Execute comprehensive client overview using MCP resources with tool processing logic.
    Automatically uses streaming for 6+ tools for better perceived performance.

    Args:
        client_id: Client CDRID (e.g., "31768")
        employee_id: User employee ID for authentication and access control
        tools: List of tools to execute (e.g., ["revenue", "product_breakdown_trends"]).
               If omitted or empty, all tools will be executed. Accepts a list, a single string,
               or a stringified list (e.g. "['revenue']").
        currency: "USD" or "CAD"
        period_type: "fiscal" or "calendar"
        time_period: "YR" for yearly, "MT" for monthly
        metric: "CV" or "CV_RBCCM"
        hierarchy_depth: "0" or "1"
        hierarchy_filter: "client" or "children"
        reportable_mask: 1 for normal, 129 for PTV
        rounding: Whether to round decimal values
        streaming: If None (default), auto-selects based on tool count:
                  - 6+ tools → streaming=True (progressive results)
                  - 1-5 tools → streaming=False (regular response)
                  Can be explicitly set to True/False to override auto-detection.

    Returns:
        JSON string with comprehensive dashboard data.
        If streaming=True, returns newline-delimited JSON (NDJSON) with progressive results.
        If streaming=False, returns single JSON object with all results.
    """

    # Log the request details for debugging
    logger.info("="*80)
    logger.info(f"[CLIENT OVERVIEW REQUEST]")
    logger.info(f"   Client ID: {client_id}")
    logger.info(f"   Employee ID: {employee_id}")
    logger.info(f"   Tools Requested: {tools}")
    logger.info(f"   Currency: {currency}, Period: {period_type}, Metric: {metric}")
    logger.info("="*80)

    # ========== EMPLOYEE ID VALIDATION ==========
    # Enforce the workflow: user_info_tool MUST be called first to get employee_id
    if employee_id is None or employee_id == 0:
        error_msg = (
            "Missing required employee_id. "
            "\n\nREQUIRED WORKFLOW:"
            "\n1. FIRST: Call user_info_tool to get your employee_id"
            "\n2. THEN: Call get_client_overview with the employee_id from step 1"
            "\n\nExample:"
            '\n  Step 1: user_info_tool() → returns {"employeeId": 12345, ...}'
            '\n  Step 2: get_client_overview(client_id="34960", employee_id=12345, ...)'
        )
        logger.error(f"[VALIDATION ERROR]: {error_msg}")
        return json.dumps({
            "status": "error",
            "message": error_msg,
            "client_id": client_id,
            "required_action": "Call user_info_tool first to get employee_id"
        }, indent=2)

    # ========== PYDANTIC VALIDATION & AUTO-CORRECTION ==========
    try:
        validated_input = validate_orchestrator_input(
            client_id=client_id,
            employee_id=employee_id,
            tools=tools,
            currency=currency,
            period_type=period_type,
            time_period=time_period,
            metric=metric,
            hierarchy_depth=hierarchy_depth,
            hierarchy_filter=hierarchy_filter,
            reportable_mask=reportable_mask,
            rounding=rounding,
            streaming=streaming
        )

        # Log auto-corrections if any occurred
        corrections = []
        if currency != validated_input.currency:
            corrections.append(f"currency: '{currency}' → '{validated_input.currency}'")
        if period_type != validated_input.period_type:
            corrections.append(f"period_type: '{period_type}' → '{validated_input.period_type}'")
        if time_period != validated_input.time_period:
            corrections.append(f"time_period: '{time_period}' → '{validated_input.time_period}'")
        if metric != validated_input.metric:
            corrections.append(f"metric: '{metric}' → '{validated_input.metric}'")
        if hierarchy_depth != validated_input.hierarchy_depth:
            corrections.append(f"hierarchy_depth: '{hierarchy_depth}' → '{validated_input.hierarchy_depth}'")
        if hierarchy_filter != validated_input.hierarchy_filter:
            corrections.append(f"hierarchy_filter: '{hierarchy_filter}' → '{validated_input.hierarchy_filter}'")
        if reportable_mask != validated_input.reportable_mask:
            corrections.append(f"reportable_mask: {reportable_mask} → {validated_input.reportable_mask}")

        if corrections:
            logger.info(f"[AUTO-CORRECTED]: {', '.join(corrections)}")

        # Use validated values from here on
        currency = validated_input.currency
        period_type = validated_input.period_type
        time_period = validated_input.time_period
        metric = validated_input.metric
        hierarchy_depth = validated_input.hierarchy_depth
        hierarchy_filter = validated_input.hierarchy_filter
        reportable_mask = validated_input.reportable_mask
        rounding = validated_input.rounding
        streaming = validated_input.streaming
        tools = validated_input.tools

    except ValidationError as e:
        # Return user-friendly error message
        error_msg = format_validation_error(e)
        logger.error(f"[VALIDATION ERROR]: {error_msg}")
        error_result = {
            "status": "error",
            "message": f"Invalid input parameters:\n{error_msg}",
            "client_id": client_id
        }
        return json.dumps(error_result, indent=2, default=str)

    if employee_id is None:
        if config.IMPERSONATED_EMPLOYEE_ID is not None:
            employee_id = config.IMPERSONATED_EMPLOYEE_ID
            logger.info(f"Using IMPERSONATED EMPLOYEE ID {employee_id} for testing.")
        else:
            raise ValueError("Employee ID is required.")


    # normalize tools into a proper list or None
    norm_tools: Optional[List[str]]
    if tools is None:
        norm_tools = None  # → orchestrator will run ALL
    elif isinstance(tools, str):
        t = tools.strip()
        if not t:
            norm_tools = None
        elif t.startswith("["):
            try:
                parsed = json.loads(t.replace("'", '"'))  # handle both JSON + Python-style
                norm_tools = parsed if isinstance(parsed, list) else [str(parsed)]
            except Exception:
                norm_tools = [t]
        else:
            norm_tools = [t]
    else:
        norm_tools = tools or None  # [] → None → all

    # Auto-detect streaming based on tool count if not explicitly set
    actual_tools = norm_tools if norm_tools else list(orchestrator.tool_registry.keys())
    tool_count = len(actual_tools)

    if streaming is None:
        # Auto-select: 6+ tools → streaming, otherwise regular
        streaming = tool_count >= 6
        logger.info(f" AUTO-DETECT: {tool_count} tools detected → streaming={streaming}")
    else:
        logger.info(f" EXPLICIT: User set streaming={streaming}")

    # Route to streaming or regular execution
    if streaming:
        logger.info(f" STREAMING MODE: Progressive results for {tool_count} tools")
        return await _execute_streaming(
            client_id=client_id,
            employee_id=employee_id,
            tools=norm_tools,
            currency=currency,
            period_type=period_type,
            time_period=time_period,
            metric=metric,
            hierarchy_depth=hierarchy_depth,
            hierarchy_filter=hierarchy_filter,
            reportable_mask=reportable_mask,
            rounding=rounding,
        )

    # Regular execution (non-streaming)
    try:
        logger.info("=== TOOL CALLED: get_client_overview (REGULAR MODE) ===")
        logger.info(f"Parameters: client_id={client_id}, employee_id={employee_id}, tools={norm_tools}, "
                f"currency={currency}, period_type={period_type}, time_period={time_period}, metric={metric}, "
                f"hierarchy_depth={hierarchy_depth}, hierarchy_filter={hierarchy_filter}, reportable_mask={reportable_mask}")

        result = await orchestrator.execute_overview(
            client_id=client_id,
            employee_id=employee_id,
            tools=norm_tools,
            currency=currency,
            period_type=period_type,
            time_period=time_period,
            metric=metric,
            hierarchy_depth=hierarchy_depth,
            hierarchy_filter=hierarchy_filter,
            reportable_mask=reportable_mask,
            rounding=rounding,
        )

        logger.info(f"Tool Output: {json.dumps(result, indent=2, default=str)}")

        result_json = json.dumps(result, indent=2, default=str)
        return result_json
    
    except Exception as e:
        logger.error(f"Error in get_client_overview: {str(e)}", exc_info=True)
        error_result = {
            "status": "error",
            "message": f"Overview execution failed: {str(e)}",
            "client_id": client_id,
            "requested_tools": norm_tools if norm_tools is not None else "all",
        }
        # return types.CallToolResult(
        #     content=[types.TextContent(type="text", text=json.dumps(error_result, indent=2, default=str))],
        #     structuredContent=error_result
        # )
        return json.dumps(error_result, indent=2, default=str)


##################################
# STREAMING EXECUTION HELPER
##################################
async def _execute_streaming(
    client_id: str,
    employee_id: int,
    tools: Optional[List[str]],
    currency: str,
    period_type: str,
    time_period: str,
    metric: str,
    hierarchy_depth: str,
    hierarchy_filter: str,
    reportable_mask: int,
    rounding: bool,
) -> str:
    """
    Internal helper for streaming execution.
    Returns newline-delimited JSON (NDJSON) with progressive results.
    """
    # Normalize tools
    norm_tools: List[str]
    if tools is None:
        norm_tools = list(orchestrator.tool_registry.keys())
    else:
        norm_tools = tools

    logger.info(f"=== STREAMING EXECUTION: {len(norm_tools)} tools ===")
    logger.info(f"Client: {client_id}, Tools: {norm_tools}")

    results = []

    # Start message
    start_msg = {
        "status": "started",
        "client_id": client_id,
        "total_tools": len(norm_tools),
        "timestamp": datetime.now().isoformat()
    }
    results.append(json.dumps(start_msg))
    logger.info(f" STREAM: Started streaming {len(norm_tools)} tools")

    # Process tools one by one (streaming fashion)
    base_params = {
        "cdrid": client_id,
        "employee_id": employee_id,
        "currency": currency,
        "period_type": period_type,
        "timeperiod": time_period,
        "metric": metric,
        "hierarchy_depth": hierarchy_depth,
        "hierarchy_filter": hierarchy_filter,
        "reportable_mask": reportable_mask,
    }

    for i, tool_name in enumerate(norm_tools):
        logger.info(f" STREAM: Processing tool {i+1}/{len(norm_tools)}: {tool_name}")

        tool_config = orchestrator.tool_registry.get(tool_name)
        if not tool_config:
            # Tool not found
            error_msg = {
                "tool": tool_name,
                "index": i,
                "status": "error",
                "error": f"Tool '{tool_name}' not found"
            }
            results.append(json.dumps(error_msg))
            continue

        # Execute single tool
        start_time = datetime.now()
        try:
            tool_result = await orchestrator._execute_tool_safe(
                tool_name,
                tool_config,
                base_params,
                rounding
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            # Stream this result immediately
            stream_msg = {
                "tool": tool_name,
                "index": i,
                "status": tool_result.get("status", "unknown"),
                "data": tool_result.get("data"),
                "execution_time": round(execution_time, 3)
            }
            results.append(json.dumps(stream_msg))
            logger.info(f" STREAM: Completed {tool_name} in {execution_time:.3f}s")

        except Exception as e:
            error_msg = {
                "tool": tool_name,
                "index": i,
                "status": "error",
                "error": str(e)
            }
            results.append(json.dumps(error_msg))
            logger.error(f" STREAM: Error in {tool_name}: {e}")

    # Completion message
    complete_msg = {
        "status": "complete",
        "timestamp": datetime.now().isoformat(),
        "total_tools": len(norm_tools)
    }
    results.append(json.dumps(complete_msg))
    logger.info(f" STREAM: Completed all {len(norm_tools)} tools")

    return "\n".join(results)