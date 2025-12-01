"""
Validation Utilities for CMPT Chain

Provides functions to verify that extracted financial metrics are grounded in source documents.
"""

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class MetricsValidator:
    """Validates extracted financial metrics against source chunks"""

    @staticmethod
    def validate_financial_metrics(
        metrics: Any,
        source_chunks: dict[str, str]
    ) -> dict[str, Any]:
        """
        Validate extracted financial metrics against source chunks.

        Args:
            metrics: FinancialMetricsResponse object with extracted data
            source_chunks: Dictionary with agent names as keys and combined content as values
                          e.g., {"news_agent": "...", "earnings_agent": "...", "SEC_agent": "..."}

        Returns:
            Dictionary with validation results
        """
        validation_results = {
            "validation_summary": {
                "total_fields_checked": 0,
                "fields_with_values": 0,
                "fields_with_sources": 0,
                "sources_verified": 0,
                "sources_not_found": 0,
                "warnings_count": 0
            },
            "field_validations": {},
            "warnings": []
        }

        # Critical fields that require source validation
        critical_fields = [
            ("current_annual_revenue", "current_annual_revenue_citation"),
            ("current_annual_revenue_date", "current_annual_revenue_date_citation"),
            ("current_annual_revenue_yoy_change", "current_annual_revenue_yoy_change_citation"),
            ("estimated_annual_revenue_next_year", "estimated_annual_revenue_next_year_citation"),
            ("estimated_annual_revenue_next_year_date", "estimated_annual_revenue_next_year_date_citation"),
            ("ebitda_margin", "ebitda_margin_citation"),
            ("ebitda_margin_yoy_change", "ebitda_margin_yoy_change_citation"),
            ("stock_price", "stock_price_citation"),
            ("stock_price_daily_change", "stock_price_daily_change_citation"),
            ("stock_price_daily_change_percent", "stock_price_daily_change_percent_citation"),
            ("stock_price_yoy_change", "stock_price_yoy_change_citation"),
            ("market_cap", "market_cap_citation"),
            ("market_cap_date", "market_cap_date_citation"),
            ("revenue_growth_trajectory", "revenue_growth_trajectory_citation")
        ]

        for value_field, citation_field in critical_fields:
            validation_results["validation_summary"]["total_fields_checked"] += 1

            field_value = getattr(metrics, value_field, None)
            citation = getattr(metrics, citation_field, None)

            field_validation = {
                "has_value": field_value is not None,
                "has_citation": citation is not None,
                "citation_verified": False,
                "extracted_numbers": [],
                "issues": []
            }

            if field_value is not None:
                validation_results["validation_summary"]["fields_with_values"] += 1

            if citation is not None:
                validation_results["validation_summary"]["fields_with_sources"] += 1

                # Handle both dict and Pydantic model
                if isinstance(citation, dict):
                    source_agents = citation.get('source_agent', [])
                    source_contents = citation.get('source_content', [])
                    reasoning = citation.get('reasoning', '')
                elif hasattr(citation, 'source_agent'):
                    source_agents = citation.source_agent
                    source_contents = citation.source_content
                    reasoning = citation.reasoning
                else:
                    warning = f"{value_field}: Citation is not a dictionary or valid object"
                    validation_results["warnings"].append(warning)
                    field_validation["issues"].append("Citation is not a dictionary or valid object")
                    logger.warning(warning)
                    validation_results["field_validations"][value_field] = field_validation
                    continue

                # Validate citation has required fields
                if not source_agents or not source_contents or not reasoning:
                    warning = f"{value_field}: Citation missing required fields"
                    validation_results["warnings"].append(warning)
                    field_validation["issues"].append("Citation missing required fields")
                    logger.warning(warning)
                else:
                    # Validate source_agent references
                    verified_agents = 0
                    for agent in source_agents:
                        if agent in source_chunks:
                            verified_agents += 1
                        else:
                            warning = f"{value_field}: Referenced agent '{agent}' not in source_chunks"
                            validation_results["warnings"].append(warning)
                            field_validation["issues"].append(f"Agent '{agent}' not found")
                            logger.warning(warning)

                    # Validate source_content quotes
                    verified_quotes = 0
                    for i, quote in enumerate(source_contents):
                        agent_name = source_agents[i] if i < len(source_agents) else (source_agents[0] if source_agents else None)

                        if agent_name and agent_name in source_chunks:
                            agent_content = source_chunks[agent_name]

                            if MetricsValidator._verify_citation_in_sources(quote, agent_content):
                                verified_quotes += 1
                            else:
                                warning = f"{value_field}: Quote #{i+1} not found in {agent_name} content"
                                validation_results["warnings"].append(warning)
                                field_validation["issues"].append(f"Quote #{i+1} not found in {agent_name}")
                                logger.warning(warning)
                        else:
                            warning = f"{value_field}: No agent specified for quote #{i+1}"
                            validation_results["warnings"].append(warning)
                            field_validation["issues"].append(f"No agent for quote #{i+1}")
                            logger.warning(warning)

                    # Mark as verified if all agents and quotes are valid
                    if verified_agents == len(source_agents) and verified_quotes == len(source_contents) and verified_quotes > 0:
                        validation_results["validation_summary"]["sources_verified"] += 1
                        field_validation["citation_verified"] = True
                    else:
                        validation_results["validation_summary"]["sources_not_found"] += 1

                    # Extract numbers from reasoning
                    all_citation_text = reasoning + ' ' + ' '.join(source_contents)
                    numbers = MetricsValidator._extract_numbers_from_text(all_citation_text)
                    field_validation["extracted_numbers"] = numbers
            else:
                # Has value but no citation
                if field_value is not None:
                    warning = f"{value_field}: Has value ({field_value}) but missing citation"
                    validation_results["warnings"].append(warning)
                    field_validation["issues"].append("Missing citation for non-null value")
                    logger.warning(warning)

            validation_results["field_validations"][value_field] = field_validation

        # Additional sanity checks
        validation_results["sanity_checks"] = MetricsValidator._run_sanity_checks(metrics)

        # Update warnings count
        validation_results["validation_summary"]["warnings_count"] = len(validation_results["warnings"])

        return validation_results

    @staticmethod
    def _verify_citation_in_sources(citation: str, sources: str) -> bool:
        """Check if citation exists in sources with fuzzy matching AND exact number matching"""
        if not citation or not sources:
            return False

        # Extract all numbers from citation and sources
        citation_numbers = MetricsValidator._extract_numbers_from_text(citation)
        sources_numbers = MetricsValidator._extract_numbers_from_text(sources)

        # If citation has numbers, ALL must exist in sources
        if citation_numbers:
            for num in citation_numbers:
                number_found = any(abs(num - src_num) < 0.01 for src_num in sources_numbers)
                if not number_found:
                    logger.warning(f"Number {num} from citation not found in sources")
                    return False

        # Normalize whitespace and case
        citation_clean = ' '.join(citation.lower().strip().split())
        sources_clean = ' '.join(sources.lower().split())

        # Try exact substring match (70% threshold)
        min_match_length = int(len(citation_clean) * 0.70)

        for i in range(len(citation_clean) - min_match_length + 1):
            substring = citation_clean[i:i + min_match_length]
            if substring in sources_clean:
                return True

        # Fallback to word overlap (75% threshold)
        citation_words = set(citation_clean.split())
        sources_words = set(sources_clean.split())

        if len(citation_words) > 0:
            overlap = len(citation_words & sources_words) / len(citation_words)
            if overlap >= 0.75:
                return True

        return False

    @staticmethod
    def _extract_numbers_from_text(text: str) -> list[float]:
        """Extract all numbers from text"""
        pattern = r'\$?\d+(?:,\d{3})*(?:\.\d+)?'
        matches = re.findall(pattern, text)

        numbers = []
        for match in matches:
            try:
                clean_number = match.replace('$', '').replace(',', '')
                numbers.append(float(clean_number))
            except ValueError:
                continue

        return numbers

    @staticmethod
    def _run_sanity_checks(metrics: Any) -> dict[str, Any]:
        """Run sanity checks on extracted metrics"""
        checks = {
            "passed": [],
            "failed": [],
            "warnings": []
        }

        # Check 1: Revenue should be positive
        if hasattr(metrics, 'current_annual_revenue') and metrics.current_annual_revenue is not None:
            if metrics.current_annual_revenue > 0:
                checks["passed"].append("Revenue is positive")
            else:
                checks["failed"].append(f"Revenue is non-positive: {metrics.current_annual_revenue}")

        # Check 2: EBITDA margin should be between -100 and 100
        if hasattr(metrics, 'ebitda_margin') and metrics.ebitda_margin is not None:
            if -100 <= metrics.ebitda_margin <= 100:
                checks["passed"].append("EBITDA margin in reasonable range (-100% to 100%)")
            else:
                checks["failed"].append(f"EBITDA margin out of range: {metrics.ebitda_margin}%")

        # Check 3: Stock price should be positive
        if hasattr(metrics, 'stock_price') and metrics.stock_price is not None:
            if metrics.stock_price > 0:
                checks["passed"].append("Stock price is positive")
            else:
                checks["failed"].append(f"Stock price is non-positive: {metrics.stock_price}")

        # Check 4: Date fields should be valid dates
        date_fields = ["current_annual_revenue_date", "estimated_annual_revenue_next_year_date", "market_cap_date"]
        for field_name in date_fields:
            date_value = getattr(metrics, field_name, None)
            if date_value:
                try:
                    datetime.strptime(date_value, "%Y-%m-%d")
                    checks["passed"].append(f"{field_name} is valid date format")
                except ValueError:
                    checks["failed"].append(f"{field_name} has invalid date format: {date_value}")

        return checks

    @staticmethod
    def print_validation_report(validation_results: dict[str, Any]) -> None:
        """Pretty print validation results"""
        print("\n" + "=" * 80)
        print("FINANCIAL METRICS VALIDATION REPORT")
        print("=" * 80)

        summary = validation_results["validation_summary"]
        print(f"\nSUMMARY:")
        print(f"  Total fields checked: {summary['total_fields_checked']}")
        print(f"  Fields with values: {summary['fields_with_values']}")
        print(f"  Fields with source citations: {summary['fields_with_sources']}")
        print(f"  Citations verified in sources: {summary['sources_verified']}")
        print(f"  Citations NOT found: {summary['sources_not_found']}")
        print(f"  Total warnings: {summary['warnings_count']}")

        if validation_results["warnings"]:
            print(f"\nWARNINGS ({len(validation_results['warnings'])}):")
            for warning in validation_results["warnings"]:
                print(f"  - {warning}")

        sanity = validation_results["sanity_checks"]
        print(f"\nSANITY CHECKS:")
        print(f"  Passed: {len(sanity['passed'])}")
        print(f"  Failed: {len(sanity['failed'])}")

        if sanity["failed"]:
            print(f"\n  Failed checks:")
            for fail in sanity["failed"]:
                print(f"    - {fail}")

        print("\n" + "=" * 80 + "\n")
