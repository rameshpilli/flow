```
src/api/endpoints/chain_server.py

"""
Chain Server Endpoint
Single unified endpoint that orchestrates all chain modules.
"""

import traceback
import os
import hashlib
from fastapi import APIRouter, HTTPException

from src.api.models.chain_models import (
    ChainServerRequest, ChainServerResponse

)
from typing import Dict, Any
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput , ResponseBuilderOutput
from src.services.data_models.llm_schemas import FinancialMetricsResponse, StrategicAnalysisResponse
from src.services.context_builder_service import ContextBuilderService
from src.services.content_prioritization_service import ContentPrioritizationService
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator
from src.services.chain_orchestrator import ChainOrchestrator



router = APIRouter()



@router.post("/chain-server")
async def chain_server(request: ChainServerRequest) -> Dict[str, Any]:
    """
    Unified chain server endpoint that orchestrates all modules based on the request.
    Returns full response when verbose=True, filtered response when verbose=False.
    """
    try:
        response_dict_with_metadata = await ChainOrchestrator().execute_chain(request)

        if not request.verbose:
            rbg = response_dict_with_metadata.get("response_builder_and_generator", {})
            filtered_rbg = {
                k: v for k, v in rbg.items()
                if k in ("financial_metrics_result", "strategic_analysis_result")
            }
            return {"response_builder_and_generator": filtered_rbg}

        return response_dict_with_metadata

    except Exception as e:
        tb = traceback.format_exc()
        print(f"Chain execution failed: {e}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"Chain execution failed: {e}\nTraceback:\n{tb}"
        )

@router.post("/context-builder", response_model=ContextBuilderOutput)
async def context_builder_test(request: ChainServerRequest):
    """
    Endpoint to test individual steps of ContextBuilderService.
    """

    context_builder_output = await ContextBuilderService.execute(request)

    return context_builder_output

@router.post("/content-prioritization", response_model=ContentPrioritizationOutput)
async def content_prioritization_test(request: ChainServerRequest):
    """
    Endpoint to test individual steps of ContentPrioritizationService.
    """
    context_builder_output = await ContextBuilderService.execute(request)
    
    content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output) 

    return content_prioritization_output

@router.post("/response-builder", response_model=ResponseBuilderOutput)
async def response_builder_test(request: ChainServerRequest):
    
    
    context_builder_output = await ContextBuilderService.execute(request)
    
    content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
    
    response_builder_output = await ResponseBuilderAndGenerator.execute(context_builder_output,content_prioritization_output)

    return response_builder_output

@router.post("/agent-subqueries", response_model=Dict[str, Any])
async def get_agent_subqueries(request: ChainServerRequest):
    context_builder_output = await ContextBuilderService.execute(request)
    content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
    return content_prioritization_output.get('subqueries_from_engine')


src/api/models/chain_models.py

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class ChainServerRequest(BaseModel):
    """Unified request model for the chain-server endpoint"""
    
    corporate_client_email: Optional[str] = None
    corporate_client_names: Optional[str] = None
    rbc_employee_email: Optional[str] = None
    meeting_datetime: Optional[str] = None
    corporate_company_name: Optional[str] = None
    verbose: Optional[bool] = False




class ChainServerResponse(BaseModel):
    context_builder: Optional[Dict[str, Any]] = None
    content_prioritization: Optional[Dict[str, Any]] = None
    response_builder_and_generator: Optional[Dict[str, Any]] = None
    timings: Optional[Dict[str, float]] = None



src/utils/utils.py
import datetime
import logging
import os
import time
from functools import lru_cache, wraps
import functools
import asyncio
from base64 import b64encode
import json
from pydantic import BaseModel, Field, ValidationError
import jwt


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def timed_lru_cache(seconds: int, maxsize: int = 1):
    def wrapped_cache(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = datetime.timedelta(seconds=seconds)
        func.expiration = datetime.datetime.now() + func.lifetime

        @wraps(func)
        def wrapped_func(*args, **kwargs):
            if datetime.datetime.now() > func.expiration:
                logger.info(
                    "Cache expired for function '%s'. Clearing cache. New expiration: %s",
                    func.__name__,
                    (datetime.datetime.now() + func.lifetime).strftime("%Y-%m-%d %H:%M:%S")
                )
                func.cache_clear()
                func.expiration = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
            return func(*args, **kwargs)
        return wrapped_func

    return wrapped_cache


def async_timed_lru_cache(seconds: int, maxsize: int = 128):
    """
    Async LRU cache with TTL support.
    Returns (result, was_cached) tuple to track cache hits/misses.
    """
    def decorator(func):
        # Store cache and metadata
        cache = {}
        cache_times = {}
        cache_order = []  # For LRU tracking
        lifetime = datetime.timedelta(seconds=seconds)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal cache, cache_times, cache_order
            
            # Create cache key from args and kwargs
            key = str(args) + str(sorted(kwargs.items()))
            
            # Check if key exists and is not expired
            now = datetime.datetime.now()
            if key in cache:
                cache_time = cache_times.get(key)
                if cache_time and (now - cache_time) < lifetime:
                    # Move to end (most recently used)
                    if key in cache_order:
                        cache_order.remove(key)
                    cache_order.append(key)
                    logger.info(f"Cache HIT for {func.__name__} with key: {key[:50]}...")
                    return cache[key], True
                else:
                    # Expired, remove from cache
                    logger.info(f"Cache EXPIRED for {func.__name__} with key: {key[:50]}...")
                    del cache[key]
                    del cache_times[key]
                    if key in cache_order:
                        cache_order.remove(key)
            
            # Cache miss - execute function
            logger.info(f"Cache MISS for {func.__name__} with key: {key[:50]}...")
            result = await func(*args, **kwargs)
            
            # Store in cache
            cache[key] = result
            cache_times[key] = now
            cache_order.append(key)
            
            # Enforce maxsize (LRU eviction)
            while len(cache) > maxsize:
                oldest_key = cache_order.pop(0)
                del cache[oldest_key]
                del cache_times[oldest_key]
                logger.info(f"Cache EVICTED oldest entry for {func.__name__}")
            
            return result, False
        
        # Add cache_clear method for manual clearing
        def cache_clear():
            nonlocal cache, cache_times, cache_order
            cache.clear()
            cache_times.clear()
            cache_order.clear()
            logger.info(f"Cache CLEARED for {func.__name__}")
        
        wrapper.cache_clear = cache_clear
        
        return wrapper
    
    return decorator


def time_it(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        start_datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
        end_datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        logger.info(
            f"Execution time for {func.__name__}: {end_time - start_time:.2f} seconds"
        )
        logger.info(f"Start time: {start_datetime}, End time: {end_datetime}")
        return result

    return wrapper


def async_time_it(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time
        logger.info(f"Execution time for {func.__name__}: {elapsed:.2f} seconds")
        return result, elapsed
    return wrapper

class AuthHeaderTokens(BaseModel):
    server_secret: str | None
    user_id_token: str | None
    connector_access_tokens: dict[str, str] = Field(default_factory=dict)

def create_bearer_token( server_secret:str, email=''):
    user_id_token = jwt.encode(payload={"email": email}, key="does-not-matter")
    header = AuthHeaderTokens(
        server_secret=server_secret,
        user_id_token=user_id_token,
        connector_access_tokens={"google": "abc"},
    )
    header_as_json = json.dumps(header.model_dump())
    header_as_b64 = b64encode(header_as_json.encode()).decode()
    return header_as_b64


src/utils/validation_utils.py
"""
Validation utilities for LLM-extracted financial metrics.
Provides functions to verify that extracted data is grounded in source documents.
"""
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MetricsValidator:
    """Validates extracted financial metrics against source chunks"""
    
    @staticmethod
    def validate_financial_metrics(
        metrics: Any,  # FinancialMetricsResponse object
        source_chunks: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Validate extracted financial metrics against source chunks.
        
        Args:
            metrics: FinancialMetricsResponse object with extracted data
            source_chunks: Dictionary with agent names as keys and combined content as values
                          e.g., {"news_tool": "...", "earnings_tool": "...", "sec_tool": "..."}
        
        Returns:
            Dictionary with validation results including:
            - validation_summary: Overall stats
            - field_validations: Per-field validation results
            - warnings: List of validation warnings
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
        
        # Combine all source chunks into one searchable text
        all_sources = "\n\n".join(source_chunks.values())
        
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
            
            # Check if field has a value
            if field_value is not None:
                validation_results["validation_summary"]["fields_with_values"] += 1
            
            # Check if citation dictionary is provided
            if citation is not None:
                validation_results["validation_summary"]["fields_with_sources"] += 1
                
                # Handle both dict and Pydantic model
                if isinstance(citation, dict):
                    source_agents = citation.get('source_agent', [])
                    source_contents = citation.get('source_content', [])
                    reasoning = citation.get('reasoning', '')
                elif hasattr(citation, 'source_agent'):  # Pydantic model
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
                    warning = f"{value_field}: Citation missing required fields (source_agent, source_content, reasoning)"
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
                        # Determine which agent to check
                        agent_name = source_agents[i] if i < len(source_agents) else (source_agents[0] if source_agents else None)
                        
                        if agent_name and agent_name in source_chunks:
                            agent_content = source_chunks[agent_name]
                            
                            # Check if quote exists in agent content
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
                    
                    # Extract numbers from reasoning and source content
                    all_citation_text = reasoning + ' ' + ' '.join(source_contents)
                    numbers = MetricsValidator._extract_numbers_from_text(all_citation_text)
                    field_validation["extracted_numbers"] = numbers
                    
                    # For calculated fields, verify value appears in reasoning
                    if field_value is not None and reasoning:
                        # Handle both float values and dictionary values (like revenue_growth_trajectory)
                        if isinstance(field_value, dict):
                            # For dictionaries, check if any of the values appear in reasoning
                            dict_values = [str(v) for v in field_value.values() if v is not None]
                            reasoning_contains_value = any(val in reasoning for val in dict_values)
                            
                            if not reasoning_contains_value and dict_values:
                                warning = f"{value_field}: Dictionary values {dict_values[:3]} not found in citation reasoning"
                                validation_results["warnings"].append(warning)
                                field_validation["issues"].append(f"Dictionary values not in reasoning")
                                logger.warning(warning)
                        
                        elif isinstance(field_value, (int, float)):
                            # For numeric values, check various formatting variations
                            value_str = f"{field_value:.1f}" if isinstance(field_value, float) else str(field_value)
                            value_variations = [
                                value_str,
                                f"{field_value:.2f}" if isinstance(field_value, float) else str(field_value),
                                f"{field_value:.3f}" if isinstance(field_value, float) else str(field_value),
                                f"{field_value:,.1f}" if isinstance(field_value, float) else str(field_value),  # With commas: 1,114.4
                                f"${value_str}",
                                f"${field_value:,.1f}B" if isinstance(field_value, float) else f"${field_value}B",  # $1,114.4B
                                str(field_value)
                            ]
                            
                            reasoning_contains_value = any(var in reasoning for var in value_variations)
                            if not reasoning_contains_value:
                                warning = f"{value_field}: Value {field_value} not found in citation reasoning"
                                validation_results["warnings"].append(warning)
                                field_validation["issues"].append(f"Value {field_value} not in reasoning")
                                logger.warning(warning)
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
        
        # Step 1: Extract all numbers from citation and sources
        citation_numbers = MetricsValidator._extract_numbers_from_text(citation)
        sources_numbers = MetricsValidator._extract_numbers_from_text(sources)
        
        # Step 2: If citation has numbers, ALL must exist in sources
        if citation_numbers:
            for num in citation_numbers:
                # Check if this exact number exists in sources (with small tolerance for floats)
                number_found = any(abs(num - src_num) < 0.01 for src_num in sources_numbers)
                
                if not number_found:
                    logger.warning(f"Number {num} from citation not found in sources")
                    return False
        
        # Step 3: Normalize whitespace and case
        citation_clean = ' '.join(citation.lower().strip().split())
        sources_clean = ' '.join(sources.lower().split())
        
        # Step 4: Try exact substring match (70% threshold)
        min_match_length = int(len(citation_clean) * 0.70)
        
        for i in range(len(citation_clean) - min_match_length + 1):
            substring = citation_clean[i:i + min_match_length]
            if substring in sources_clean:
                return True
        
        # Step 5: Fallback to word overlap (75% threshold)
        citation_words = set(citation_clean.split())
        sources_words = set(sources_clean.split())
        
        if len(citation_words) > 0:
            overlap = len(citation_words & sources_words) / len(citation_words)
            if overlap >= 0.75:
                return True  
        
        return False 
    
    @staticmethod
    def _extract_numbers_from_text(text: str) -> List[float]:
        """Extract all numbers from text (useful for debugging)"""
        # Pattern to match numbers with optional dollar signs, commas, and decimal points
        pattern = r'\$?\d+(?:,\d{3})*(?:\.\d+)?'
        matches = re.findall(pattern, text)
        
        numbers = []
        for match in matches:
            try:
                # Remove dollar signs and commas
                clean_number = match.replace('$', '').replace(',', '')
                numbers.append(float(clean_number))
            except ValueError:
                continue
        
        return numbers
    
    @staticmethod
    def _run_sanity_checks(metrics: Any) -> Dict[str, Any]:
        """Run sanity checks on extracted metrics"""
        checks = {
            "passed": [],
            "failed": [],
            "warnings": []
        }
        
        # Check 1: Revenue should be positive
        if metrics.current_annual_revenue is not None:
            if metrics.current_annual_revenue > 0:
                checks["passed"].append("Revenue is positive")
            else:
                checks["failed"].append(f"Revenue is non-positive: {metrics.current_annual_revenue}")
        
        # Check 2: EBITDA margin should be between -100 and 100
        if metrics.ebitda_margin is not None:
            if -100 <= metrics.ebitda_margin <= 100:
                checks["passed"].append("EBITDA margin in reasonable range (-100% to 100%)")
            else:
                checks["failed"].append(f"EBITDA margin out of range: {metrics.ebitda_margin}%")
        
        # Check 3: Stock price should be positive
        if metrics.stock_price is not None:
            if metrics.stock_price > 0:
                checks["passed"].append("Stock price is positive")
            else:
                checks["failed"].append(f"Stock price is non-positive: {metrics.stock_price}")
        
        # Check 5: Date fields should be valid dates
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
    def print_validation_report(validation_results: Dict[str, Any]) -> None:
        """Pretty print validation results"""
        print("\n" + "="*80)
        print("FINANCIAL METRICS VALIDATION REPORT")
        print("="*80)
        
        summary = validation_results["validation_summary"]
        print(f"\n SUMMARY:")
        print(f"  Total fields checked: {summary['total_fields_checked']}")
        print(f"  Fields with values: {summary['fields_with_values']}")
        print(f"  Fields with source citations: {summary['fields_with_sources']}")
        print(f"  Citations verified in sources: {summary['sources_verified']}")
        print(f"  Citations NOT found: {summary['sources_not_found']}")
        print(f"  Total warnings: {summary['warnings_count']}")
        
        if validation_results["warnings"]:
            print(f"\n WARNINGS ({len(validation_results['warnings'])}):")
            for warning in validation_results["warnings"]:
                print(f"  - {warning}")
        
        print(f"\n🔍 FIELD-BY-FIELD VALIDATION:")
        for field_name, field_data in validation_results["field_validations"].items():
            status = "✓ Passed" if field_data["citation_verified"] else "✗ Failed"
            print(f"\n  {status} {field_name}:")
            print(f"      Has value: {field_data['has_value']}")
            print(f"      Has citation: {field_data['has_citation']}")
            print(f"      Citation verified: {field_data['citation_verified']}")
            if field_data["extracted_numbers"]:
                print(f"      Numbers in citation: {field_data['extracted_numbers'][:5]}")  # First 5
            if field_data["issues"]:
                print(f"      Issues: {', '.join(field_data['issues'])}")
        
        sanity = validation_results["sanity_checks"]
        print(f"\n✓ SANITY CHECKS:")
        print(f"  Passed: {len(sanity['passed'])}")
        print(f"  Failed: {len(sanity['failed'])}")
        print(f"  Warnings: {len(sanity['warnings'])}")
        
        if sanity["failed"]:
            print(f"\n  Failed checks:")
            for fail in sanity["failed"]:
                print(f"    - {fail}")
        
        if sanity["warnings"]:
            print(f"\n  Sanity warnings:")
            for warn in sanity["warnings"]:
                print(f"    - {warn}")
        
        print("\n" + "="*80 + "\n")




src/services/chain_orchestrator.py

import asyncio

from src.api.models.chain_models import (
    ChainServerRequest, 
    ChainServerResponse
)
from src.services.context_builder_service import ContextBuilderService
from src.services.content_prioritization_service import ContentPrioritizationService
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator


import time
import logging
logger = logging.getLogger("chain_orchestrator")

class ChainOrchestrator:
    """Orchestrates the execution of all chain modules"""


    async def execute_chain(self, request: ChainServerRequest) -> ChainServerResponse:
        total_start = time.perf_counter()
        try:
            # Step 1: Execute Context Builder
            logger.info("Executing Context Builder...")
            context_builder_output = await ContextBuilderService.execute(request)
            if context_builder_output.get("errors"):
                logger.warning(f"Context Builder errors: {context_builder_output['errors']}")

            # Step 2: Execute Content Prioritization
            logger.info("Executing Content Prioritization...")
            content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
            if content_prioritization_output.get("errors"):
                logger.warning(f"\n\n Content Prioritization errors: {content_prioritization_output['errors']} \n\n")

            # Step 3: Execute Response Builder and Generator
            logger.info("Executing Response Builder and Generator...")
            response_builder_output = await ResponseBuilderAndGenerator.execute(context_builder_output, content_prioritization_output)
            if response_builder_output.get("errors"):
                logger.warning(f"Response Builder errors: {response_builder_output['errors']}")

            total_time = time.perf_counter() - total_start

            # Build final response
            response_dic = {
                "context_builder": {
                    "corporate_client_firm_response": context_builder_output.get("corporate_client_firm_response"),
                    "temporal_content_response": context_builder_output.get("temporal_content_response"),
                    "rbc_persona": context_builder_output.get("rbc_persona"),
                    "corporate_client_persona": context_builder_output.get("corporate_client_persona"),
                    "timings": context_builder_output.get("timings", {}),
                    "cached": context_builder_output.get("cached"),
                    "errors": context_builder_output.get("errors", {}),
                },
                "content_prioritization": {
                    "temporal_source_prioritizer": content_prioritization_output.get("temporal_source_prioritizer"),
                    "subqueries_from_engine": content_prioritization_output.get("subqueries_from_engine"),
                    "topic_ranker_result": content_prioritization_output.get("topic_ranker_result"),
                    "timings": content_prioritization_output.get("timings", {}),
                    "errors": content_prioritization_output.get("errors", {}),
                },
                "response_builder_and_generator": {
                    "financial_metrics_result": response_builder_output.get("financial_metrics_result"),
                    "strategic_analysis_result": response_builder_output.get("strategic_analysis_result"),
                    "validation_results": response_builder_output.get("validation_results"),
                    "parsed_data_agent_chunks": response_builder_output.get("parsed_data_agent_chunks"),
                    "company_name": response_builder_output.get("company_name"),
                    "timings": response_builder_output.get("timings", {}),
                    "cached": response_builder_output.get("cached"),
                    "errors": response_builder_output.get("errors", {}),
                },
                "timings": {
                    "total_time": total_time
                }
            }

            return response_dic

        except Exception as e:
            logger.error(f"Chain execution failed: {e}", exc_info=True)
            raise

if __name__ == "__main__":
    request = ChainServerRequest(
            corporate_client_email="akinahan@k1ops.com",
            corporate_client_names="Allison Kinahan",
            rbc_employee_email="saqlain.shaik@sterbc.com",
            meeting_datetime="2025-10-30",
            corporate_company_name="BlackRock Inc.",
            #corporate_company_name="Tesla"
        )
    asyncio.run(ChainOrchestrator().execute_chain(request))


src/services/content_prioritization_service.py
"""
Content Prioritization Engine Service Module
Contains all the business logic from the content prioritization engine endpoints converted to service functions.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
from src.services.grid_config import GRID

from src.services.llm.client import get_openai_client
from src.utils.utils import async_time_it
from src.services.static_subquery_engine import StaticSubqueryEngine
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput
from src.api.models.chain_models import ChainServerRequest
from src.utils.utils import async_time_it

import logging

logger = logging.getLogger(__name__)


class ContentPrioritizationService:
    """Service class containing all content prioritization functionality"""

    @staticmethod
    async def temporal_source_prioritizer(
        company_type: str,
        meeting_date: str, 
        max_earnings_event_date: Optional[str] = None
    ) -> tuple:
        error = None
        result = None
        rule_errors = []
        try:
            config = GRID
            earnings_proximity_weeks = config.get("earnings_proximity_weeks")
            window = earnings_proximity_weeks * 7  # days

            meeting_datetime = datetime.strptime(meeting_date, "%Y-%m-%d")
            max_earnings_event_datetime = None
            if max_earnings_event_date:
                max_earnings_event_datetime = datetime.strptime(max_earnings_event_date, "%Y-%m-%d")

            context = {
                "company_type": company_type,
                "meeting_date": meeting_datetime,
                "max_earnings_event_date": max_earnings_event_datetime,
                "window": window
            }
            
            prioritizer_config = config["temporal_source_prioritizer"]
            rules = prioritizer_config["rules"]
            priority_profiles = config["priority_profiles"]
            default_profile = prioritizer_config["default_profile"]
            result = priority_profiles[default_profile]
            
            for rule in rules:
                try:
                    condition = rule["condition"]
                    if callable(condition) and condition(context):
                        profile_name = rule["priority_profile"]
                        result = priority_profiles[profile_name]
                        return result, None
                except Exception as e:
                    msg = f"Error evaluating rule '{rule.get('name')}': {e}"
                    logger.warning(msg)
                    rule_errors.append(msg)
            
        except Exception as e:
            error = str(e)
            logger.error(f"Error in temporal_source_prioritizer: {error}", exc_info=True)
        
        # If there were rule errors, include them in the error output
        if rule_errors:
            error = {"rule_errors": rule_errors, "final_error": error}
        
        return result, error
    
    @staticmethod
    async def subquery_engine(company_name: str, fiscal_year: str, fiscal_quarter: str) -> tuple:
        """
        Generate subqueries for data agents.
        Returns (result, error) tuple.
        """
        error = None
        result = None
        try:
            result = StaticSubqueryEngine.get_subquery_arguments(company_name, fiscal_year, fiscal_quarter)
        except Exception as e:
            error = str(e)
            logger.error(f"Error in subquery_engine: {error}", exc_info=True)
            result = None
        
        return result, error

    @staticmethod
    async def topic_ranker(subqueries):
        """
        Given the content from various data agents that each of the above sub-queries would generate, 
        rank them based on topics of interest as defined in the grid
        """
        return {"content_prioritization_topics": GRID["content_prioritization_topics"]}
    
    @staticmethod
    async def execute(
        context_builder_output: ContextBuilderOutput
    ) -> ContentPrioritizationOutput:
        """
        Execute the full content prioritization pipeline.
        """
        timings = {}
        result = {}
        errors = {}

        meeting_date = context_builder_output["request_meeting_date"]
        
        corporate_client_firm_response = context_builder_output["corporate_client_firm_response"]
        if corporate_client_firm_response:
            company_type = corporate_client_firm_response.get("company_type")
            company_name = corporate_client_firm_response.get("company_name")
        else:
            company_type = "PUB"
            company_name = context_builder_output["request_company_name"]

        temporal_content_response = context_builder_output["temporal_content_response"]
        if temporal_content_response:
            event_dt = temporal_content_response["event_dt"]
            fiscal_year = temporal_content_response.get("fiscal_year")
            fiscal_quarter = temporal_content_response.get("fiscal_period")
        else:
            event_dt = meeting_date
            fiscal_year = str(int(meeting_date[:4]))
            month = int(meeting_date[5:7])
            fiscal_quarter = str((month - 1) // 3 + 1)
        
        # Step 1: Temporal source prioritizer
        (temporal_source_prioritizer, temporal_source_error), timings["temporal_source_prioritizer"] = await async_time_it(
            ContentPrioritizationService.temporal_source_prioritizer
        )(
            company_type=company_type,
            meeting_date=meeting_date,
            max_earnings_event_date=event_dt
        )
        if temporal_source_error:
            errors["temporal_source_prioritizer"] = temporal_source_error
        
        # Step 2: Subquery engine
        (subqueries_from_engine, subquery_engine_error), timings["subquery_engine"] = await async_time_it(
            ContentPrioritizationService.subquery_engine
        )(
            company_name=company_name,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter
        )
        if subquery_engine_error:
            errors["subquery_engine"] = subquery_engine_error
        
        result["topic_ranker_result"] = None
        result["temporal_source_prioritizer"] = temporal_source_prioritizer
        result["subqueries_from_engine"] = subqueries_from_engine
        result["timings"] = timings
        result["errors"] = errors
        
        return result

if __name__ == "__main__":
    import asyncio

    async def main():
        print("Testing temporal_source_prioritizer V2...")
        try:
            # Test case 1: Public company with earnings in proximity
            raw = await ContentPrioritizationService.temporal_source_prioritizer(
                company_type="PUB",
                meeting_date="2025-11-01",
                max_earnings_event_date="2025-10-25"
            )
            print("Public with earnings nearby:", raw)
            
            # Test case 2: Public company without earnings in proximity
            raw = await ContentPrioritizationService.temporal_source_prioritizer(
                company_type="PUB",
                meeting_date="2025-11-01",
                max_earnings_event_date="2025-08-15"
            )
            print("Public without earnings nearby:", raw)
            
            # Test case 3: Private company
            raw = await ContentPrioritizationService.temporal_source_prioritizer(
                company_type="PRIV",
                meeting_date="2025-11-01",
                max_earnings_event_date=None
            )
            print("Private company:", raw)
            
        except Exception as e:
            print("Error:", e)

        print("\nTesting subquery_engine...")
        try:
            raw = await ContentPrioritizationService.subquery_engine(
                company_name="Tesla",
                meeting_date="2025-11-01"
            )
            print("RAW:", raw)
        except Exception as e:
            print("Error:", e)

    asyncio.run(main())


src/services/enums.py
from enum import Enum

class ToolName(Enum):
    EARNINGS_TOOL = "earnings_agent"
    NEWS_TOOL = "news_agent"
    SEC_TOOL = "SEC_agent"


src/services/grid_config.py
from src.services.enums import ToolName

GRID = {
    "earnings_proximity_weeks": 1,
    
    # Define priority profiles to avoid repetition
    "priority_profiles": {
        "earnings_dominant": {
            ToolName.EARNINGS_TOOL.value: 50,
            ToolName.NEWS_TOOL.value: 30,
            ToolName.SEC_TOOL.value: 20
        },
        "news_dominant": {
            ToolName.EARNINGS_TOOL.value: 20,
            ToolName.NEWS_TOOL.value: 60,
            ToolName.SEC_TOOL.value: 20
        }
    },
    
    # Rules reference the profiles
    "temporal_source_prioritizer": {
        "rules": [
            {
                "name": "non_public_company",
                "condition": lambda ctx: ctx["company_type"] not in ["PUB", "SUB"],
                "priority_profile": "news_dominant"
            },
            {
                "name": "earnings_proximity",
                "condition": lambda ctx: (
                    ctx["company_type"] in ["PUB", "SUB"] and
                    ctx.get("max_earnings_event_date") and
                    abs((ctx["max_earnings_event_date"] - ctx["meeting_date"]).days) <= ctx["window"]
                ),
                "priority_profile": "earnings_dominant"
            }
        ],
        "default_profile": "news_dominant"
    }
}

src/services/llm_prompts.py
DATA_FOR_FINANCIAL_METRICS_PROMPT = """
[SEC_AGENT]
Agent Guidance:
- Primary source for all financial metrics
- Extract precise numbers from financial statements
- Look for year-over-year comparisons in financial statements
{SEC_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Use for forward guidance and quarterly commentary
- Extract YoY growth rates mentioned in management discussion
{EARNINGS_AGENT_CONTENT}

[NEWS_AGENT]
Agent Guidance:
- Extract current stock price and today's price movement if mentioned in recent articles
- Look for daily price changes (e.g., "stock up $1.39 or 0.56% today")
{NEWS_AGENT_CONTENT}
"""

DATA_FOR_STRATEGIC_ANALYSIS_PROMPT = """
[NEWS_AGENT]
Agent Guidance:
- Include {NEWS_percentage}% of the response from this agent chunks
- Extract date, category, and source URL for each development
{NEWS_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Include {EARNINGS_percentage}% of the response from this agent chunks
{EARNINGS_AGENT_CONTENT}

[SEC_AGENT]
Agent Guidance:
- Include {SEC_percentage}% of the response from this agent chunks
"""

FINANCIAL_METRICS_PROMPT = """
## Task: Extract Financial Metrics

You are analyzing financial data for {COMPANY_NAME}. Extract precise financial metrics from SEC filings and earnings reports.

{DATA_FOR_FINANCIAL_METRICS}

## CRITICAL JSON FORMAT REQUIREMENT:
**For ALL numeric fields (float type):**
- Return actual numbers (e.g., 96.773, 25.5, 1.39) OR the JSON null value
- NEVER return strings like "<UNKNOWN>", "N/A", "null", "None", or any text placeholders
- If data is genuinely missing after exhausting all sources, return null (JSON null, not the string "null")

**Example - CORRECT:**
```json
{{
  "current_annual_revenue": 96.773,
  "ebitda_margin": null,
  "stock_price": 251.72
}}
```

**Example - WRONG (will cause errors):**
```json
{{
  "current_annual_revenue": "<UNKNOWN>",
  "ebitda_margin": "N/A",
  "stock_price": "null"
}}
```

## CRITICAL: Source Attribution (REQUIRED FOR VERIFICATION)
For ALL numeric fields, you MUST provide citations as dictionaries with these keys:
- **source_agent**: List of agent names (e.g., ["SEC_agent", "earnings_agent"])
- **source_content**: List of VERBATIM quotes from those agents (COPY-PASTE EXACTLY - DO NOT PARAPHRASE)
- **reasoning**: String explaining your extraction/calculation logic

**CRITICAL RULE FOR NULL VALUES:**
- If you return null for ANY numeric field, you MUST still provide a citation dictionary
- The citation MUST explain: (1) which specific sources you searched, (2) what keywords/sections you looked for, and (3) why data was unavailable
- Be SPECIFIC about what you searched: "Searched SEC 10-K 'Management Discussion' and 'Forward-Looking Statements' sections, earnings call transcript Q&A (pages 15-23), and 15 news articles from past 90 days. Found qualitative growth statements but no specific numerical revenue guidance for FY2026."
- DO NOT return citation as null - always provide a dictionary explaining your search process



**IMPORTANT CITATION RULES:**
1. **VERBATIM QUOTES ONLY**: Copy-paste the EXACT text from the source documents into source_content
   - CORRECT: "Total revenues were $25,182 million for the three months ended September 30, 2025"
   - WRONG: "Revenue was about $25 billion in Q3 2025" (paraphrased)
   
2. **QUOTE LENGTH**: Each quote should be 20-100 words (enough context to verify)
   - Too short: "Revenue: $25B" (not enough context)
   - Good: "During the three months ended September 30, 2025, total revenues were $25,182 million, compared to $23,350 million for the same period in 2024."

3. **SHOW YOUR WORK**: For calculated metrics (like EBITDA margin), include the actual calculation in reasoning
   - Must show: Formula + Numbers + Final result
   - Example: "EBITDA Margin = ($25.5B operating income + $2.1B D&A) / $96.8B revenue = 28.5%"
   - The final value MUST appear in the reasoning string

4. **STOCK PRICE**: Always include the date/timestamp in the quote
   - Correct: "On November 15, 2024, shares closed at $350.00"
   - Wrong:  "Stock price is $350" (no date)

**REQUIRED citation fields:**
- current_annual_revenue_citation
- current_annual_revenue_date_citation
- current_annual_revenue_yoy_change_citation
- estimated_annual_revenue_next_year_citation
- estimated_annual_revenue_next_year_date_citation
- ebitda_margin_citation
- ebitda_margin_yoy_change_citation
- stock_price_citation
- stock_price_daily_change_citation
- stock_price_daily_change_percent_citation
- stock_price_yoy_change_citation
- market_cap_citation
- market_cap_date_citation
- revenue_growth_trajectory_citation

**Format Example:**
```json
{{
  "current_annual_revenue": 96.773,
  "current_annual_revenue_citation": {{
    "source_agent": ["SEC_agent"],
    "source_content": [
      "Total revenues were $96,773 million for the twelve months ended September 30, 2025, compared to $81,462 million for the same period in 2024."
    ],
    "reasoning": "Extracted annual revenue from SEC 10-Q filing (Form 10-Q filed 2025-10-20). Used trailing twelve month (TTM) revenue of $96.773 billion."
  }},
  
  "ebitda_margin": 28.5,
  "ebitda_margin_citation": {{
    "source_agent": ["SEC_agent", "SEC_agent", "SEC_agent"],
    "source_content": [
      "Operating income was $25,500 million for the twelve months ended September 30, 2025.",
      "Depreciation and amortization expense was $2,100 million for the twelve months ended September 30, 2025.",
      "Total revenues were $96,773 million for the twelve months ended September 30, 2025."
    ],
    "reasoning": "Calculated EBITDA margin = ($25,500M operating income + $2,100M D&A) / $96,773M revenue = 28.5%. All components extracted from Form 10-Q Consolidated Statements."
  }},
  
  "stock_price": 350.0,
  "stock_price_citation": {{
    "source_agent": ["news_agent"],
    "source_content": [
      "Tesla shares closed at $350.00 on November 15, 2024, up $5.20 or 1.5% on the day, according to Bloomberg data."
    ],
    "reasoning": "Current stock price of $350.0 extracted from Bloomberg article dated November 15, 2024."
  }},
  
  "market_cap": 1114.4,
  "market_cap_citation": {{
    "source_agent": ["SEC_agent", "news_agent"],
    "source_content": [
      "Common stock outstanding: 3,183,666,092 shares as of September 30, 2025.",
      "Tesla shares closed at $350.00 on November 15, 2024."
    ],
    "reasoning": "Market cap = 3.184 billion shares × $350.00 per share = $1,114.4 billion."
  }}
}}
```

**IMPORTANT**: 
- source_agent: Use exact agent names from the data sources: "SEC_agent", "earnings_agent", "news_agent"
- source_content: Must be verbatim quotes (copy-paste) from agent content, not paraphrased
- reasoning: Explain where you found it and any calculations performed
- Each quote in source_content should map to the corresponding agent in source_agent (same index)
- If calculation spans multiple quotes, include all relevant quotes
- If you cannot find data in the provided documents, return null for BOTH the value AND the citation

## Extraction Guidelines:

**Revenue Metrics (REQUIRED - DO NOT SKIP):**
- Current annual revenue: Most recent 10-K or annualized 10-Q
- Next year estimate: Company guidance or extrapolate from growth trends
  - **CONFLICT RESOLUTION FOR GUIDANCE DATA**: When multiple Q4 guidance figures exist, prioritize:
    1. Direct company guidance from earnings release (look for "Nvidia forecast..." or "company guided...")
    2. Analyst consensus estimates
    3. Individual analyst projections
  - **If Q4 guidance exists but no annual guidance**: Sum actual Q1-Q3 revenue + Q4 guidance to estimate full-year revenue
    - In reasoning, state: "Estimated FY[YEAR] revenue = Q1-Q3 actual ($X) + Q4 guidance ($Y) = $Z"
    - For "next year" estimate beyond current fiscal year, note if extrapolation/calculation is required
- **Year-over-year change**: Calculate or extract YoY % change in revenue (e.g., "+9% YoY")
  - Search for: "compared to prior year", "year-over-year", "% increase from"
  - Formula: ((Current Year Revenue - Prior Year Revenue) / Prior Year Revenue) × 100
  - **MUST provide current_annual_revenue_yoy_change_citation with BOTH current and prior year revenue quotes AND calculation**
- Always include exact source dates
- **MUST provide current_annual_revenue_citation with VERBATIM quotes and detailed reasoning**
- **MUST provide current_annual_revenue_date_citation with VERBATIM quote showing filing date**
- **MUST provide estimated_annual_revenue_next_year_date_citation with VERBATIM quote showing document date**

**EBITDA Margin (REQUIRED - CALCULATE IF NEEDED):**
- First, search for explicit "EBITDA" in SEC_AGENT
- If not found, calculate: (Operating Income + Depreciation + Amortization) / Revenue × 100
- **ACCEPT trailing twelve-month (TTM) OR six-month figures if annual data unavailable**
  - For six-month data: Clearly label as "Six-Month EBITDA Margin" or "TTM EBITDA Margin" in reasoning
  - Formula: (6mo Operating Income + 6mo D&A) / 6mo Revenue × 100
- Search for "Operating Income", "D&A", "Depreciation", "Amortization" in financial statements

**CRITICAL: MATCHING TIME PERIODS**
- SEC filings often show multiple columns: "Three Months Ended", "Six Months Ended", "Nine Months Ended", "Twelve Months Ended"
- **YOU MUST USE THE SAME TIME PERIOD FOR ALL THREE COMPONENTS** (Operating Income, D&A, Revenue)
- Look for table headers like "Three Months Ended September 30, 2025" or "Nine Months Ended September 30, 2025"
- **PREFERRED PERIODS (in order)**:
  1. Trailing Twelve Months (TTM) or Annual (12 months)
  2. Nine Months Ended
  3. Six Months Ended
  4. Three Months Ended (only if no longer period available)
- **EXTRACTION STEPS**:
  1. Identify the longest period available in the filing (e.g., "Nine Months Ended")
  2. Extract Operating Income for that EXACT period
  3. Extract D&A for that EXACT period (look in same table or Cash Flow Statement)
  4. Extract Revenue for that EXACT period
  5. All three numbers MUST be from the same column/period
- **IN YOUR REASONING, STATE THE PERIOD**: "Calculated Nine-Month EBITDA Margin = ..."



- **Year-over-year change**: Calculate YoY change in margin percentage points (e.g., "+1% YoY")
  - Formula: Current Period EBITDA Margin - Prior Period EBITDA Margin
  - **MUST USE SAME PERIOD LENGTH FOR BOTH YEARS** (e.g., nine months vs nine months)
  - **MUST provide ebitda_margin_yoy_change_citation with BOTH periods' calculations AND comparison**
  - If only six-month data available for both periods, compare six-month margins
- If components scattered across tables, extract and calculate manually
- **MUST provide ebitda_margin_citation showing calculation with all component VERBATIM quotes**
- **In reasoning, MUST show: [Period] EBITDA Margin = (Operating Income $X + D&A $Y) / Revenue $Z = [final value]%**
- **DO NOT return null unless absolutely no financial data exists**

**Stock Price (REQUIRED - MULTIPLE SOURCES):**
1. Check NEWS_AGENT for recent price mentions
2. **RECENCY RULE - When multiple prices exist with timestamps**:
   - Prioritize: After-hours > Closing > Pre-market > Intraday
   - Use the price with the most recent date/time context
   - If timestamps conflict but one says "after-hours following earnings" or similar recent context, use that price
   - In reasoning, state: "Used [after-hours/closing] price of $X from [date] as most current available"
3. Check SEC filing cover pages for "Class A Common Stock" price
4. Check EARNINGS_AGENT transcript for price references
5. **Today's price movement**: Extract daily change in both dollars and percentage
   - Look for: "stock up/down $X.XX", "gained/lost X%", "closed at $XXX, up $X.XX (X%)"
   - Example: "$251.72, up $1.39 (0.56%) today"
   - Extract both absolute dollar change AND percentage change
   - **FALLBACK for dollar change**: If no explicit dollar change but you have:
     - Today's closing/current price AND
     - Yesterday's closing price OR percentage change stated
     - Calculate: Dollar change = Current price - Prior price, OR Current price × (Percentage change / 100)
     - Example: If stock at $142 and "up 5%", then prior price = $142 / 1.05 = $135.24, change = $142 - $135.24 = $6.76
   - **MUST provide stock_price_daily_change_citation with VERBATIM quote showing dollar change (or calculation if derived)**
   - **MUST provide stock_price_daily_change_percent_citation with VERBATIM quote showing percentage change**
6. **Year-over-year change (stock_price_yoy_change)**: Compare to price from one year ago
   - **PRIORITY 1 (PREFERRED)**: Find explicit "stock price on [date one year ago] was $XXX"
   - **PRIORITY 2 (ACCEPTABLE)**: Use Year-to-Date (YTD) performance as YoY proxy
     - If article states "YTD +29.10%" and today is Nov 19, 2024, this compares Jan 1, 2024 to Nov 19, 2024
     - For practical purposes, YTD ≈ YoY when comparing similar dates (late in calendar year)
     - Formula: stock_price_yoy_change = YTD percentage (e.g., 29.10 for +29.10%)
     - In reasoning: "Used YTD performance (+29.10%) as YoY proxy. YTD compares Jan 1, 2024 to Nov 19, 2024, which approximates YoY comparison for late-year dates."
   - **PRIORITY 3 (FALLBACK)**: Calculate backwards from current price and YTD
     - Prior year price ≈ Current price / (1 + YTD%/100)
     - Example: $338.74 / 1.291 = $262.43 (approx price on Jan 1, 2024)
     - YoY ≈ YTD for practical purposes
   - **MUST provide stock_price_yoy_change_citation** explaining which method you used
   - **DO NOT return null if you have YTD data** - use it as a reasonable approximation
7. **MUST provide stock_price_citation with VERBATIM quote including date/timestamp**
8. **In reasoning, MUST include the exact date of the stock price (e.g., "Stock price of $350.0 as of November 15, 2024")**
9. **DO NOT return null for stock_price - extract from ANY available source**

**Market Cap (CALCULATE IF NEEDED):**
- Formula: Stock Price × Outstanding Shares
- Find "Outstanding Shares" in SEC_AGENT (search: "shares outstanding", "common stock outstanding")
- If you have stock price but not shares, search harder in SEC balance sheet
- **MUST provide market_cap_citation with quotes for BOTH stock price AND share count AND calculation**
- **MUST provide market_cap_date_citation with VERBATIM quote showing the date context**
- **DO NOT return null if you have either component**

## Revenue Growth Trajectory (REQUIRED)

**GOAL**: Build a dictionary of the last 7 quarterly revenues using fiscal quarter notation (e.g., "Q1 FY2026", "Q3 FY2025").

**DATA SOURCES**:
- 10-Q filings contain Q1, Q2, Q3 data (look for "Three Months Ended [Date]")
- 10-K annual reports contain full fiscal year data
- Q4 is NOT in 10-Q filings - must be calculated from 10-K

**EXTRACTION STEPS**:
1. **Scan all SEC chunks** for 10-Q filings - look for "FORM 10-Q for Q[X], FY [YYYY]" in metadata
2. **Extract quarterly revenue** from financial tables with "Three Months Ended" column headers
   - Search for tables/sections with: "SUMMARY RESULTS OF OPERATIONS", "INCOME STATEMENTS", or similar financial statement headers
   - Look for the "Revenue" line item in these tables
   - Revenue may appear in columns formatted as: "| |$|XX,XXX| |" or "Revenue $ XX,XXX"
3. **Use the exact fiscal quarter label from the filing title** as your dictionary key
4. For Q4 quarters: Calculate Q4 = Annual (from 10-K) - Nine Months Ended (from Q3 10-Q)
   - Locate both values in financial statement tables, even if presented in multi-year or multi-column format
   - Match the correct fiscal year column for both annual and nine-month values
   - Only calculate Q4 if BOTH values are explicitly present for the same fiscal year
   - Show calculation: "Q4 FY[YEAR] = $XXXM annual - $XXXM nine months = $XXXM"
   - In your citation, include the full table row and specify which columns were used for each value

**Q4 CALCULATION TRIGGERS**:
- Any Q4 that falls within the last 7 quarters
- You have the annual 10-K AND the Q3 10-Q "Nine Months Ended" for that fiscal year

**CRITICAL RULES**:
- Use fiscal quarter format: "Q1 FY2026", "Q3 FY2025" (copy from filing titles)
- DO NOT duplicate quarters or copy values between quarters
- DO NOT estimate components - only calculate Q4 if you have exact figures
- Include ALL calculation steps in citation with verbatim quotes, including the full table row/context
- Return null for quarters where data is genuinely unavailable

**EXCEPTION**: If you cannot find "Nine Months Ended" data for Q4 calculation, return null for that Q4 and note in citation why calculation was not possible.


## CRITICAL INSTRUCTIONS:
1. **EXHAUST ALL SOURCES** before returning null
2. **CALCULATE** when direct values unavailable
3. **SEARCH MULTIPLE KEYWORDS** for each metric
4. **PROVIDE VERBATIM CITATIONS** for all critical metrics - NO PARAPHRASING
5. **SHOW YOUR CALCULATIONS** in reasoning with actual numbers and formulas
6. **EXTRACT YoY CHANGES**: Always look for year-over-year comparisons in financial statements
7. **EXTRACT DAILY CHANGES**: For stock price, get today's movement ($ and %)
8. For optional fields: null is acceptable ONLY if you've tried calculation/extraction from all sources
9. For EBITDA, stock price, revenue trajectory: **These are effectively required - try harder**

## Data Source Strategy:
- SEC_AGENT: Financial statements, balance sheet, cash flow (look in ALL sections for YoY comparisons)
- EARNINGS_AGENT: Management commentary, guidance, Q&A mentions, growth rate discussions
- NEWS_AGENT: Recent price action, market cap references, daily stock movements

**Your goal: Maximize data extraction with VERBATIM, VERIFIABLE citations. Every null is a failure. Every paraphrased quote is a validation error.**
"""

STRATEGIC_ANALYSIS_PROMPT = """
## Task: Strategic Analysis for Client Meeting

You are preparing a strategic briefing for {COMPANY_NAME} for an RBC Capital Markets client meeting.

{DATA_FOR_STRATEGIC_ANALYSIS}

**CRITICAL: You must fill ALL fields in the response schema. Do not skip any fields.**

## Required Output Structure (ALL FIELDS MANDATORY):

### 1. SWOT Analysis (strength, weakness, opportunity, threat)
- 4-6 bullets each
- Each bullet: 15-25 words, specific, data-backed

### 2. Investment Thesis (investment_thesis field - REQUIRED)
**Format**: List of 3-4 dictionaries, each with:
- Key: One subheading (e.g., "Growth Drivers", "Competitive Moat")
- Value: List of 2-4 bullet points (15-30 words each)

**Example**:
```json
[
  {{"Growth Drivers": ["Bullet 1...", "Bullet 2..."]}},
  {{"Competitive Moat": ["Bullet 1...", "Bullet 2..."]}}
]
```

### 3. Key Risk Highlights (key_risk_highlights field)
- 5-7 critical risks
- Each bullet: 15-30 words with impact and timeline

### 4. Strategic Opportunities (strategic_opportunities field - REQUIRED)
**Format**: List of 3-4 dictionaries with:
- Key: Category (e.g., "M&A Advisory", "Capital Raising")
- Value: List of 2-3 specific opportunities (15-30 words each)



### 5. Recent Developments (recent_developments field - REQUIRED)
**NEW FORMAT**: List of 4-6 dictionaries, each with these exact keys:
- **category**: ONE of: "News", "M&A", "Management", "Company", or "Industry"
- **header**: 5-10 word title/summary of the development (e.g., "Battery Tech Acquisition", "New CFO Appointed")
- **date**: Date in format "MMM DD YYYY" (e.g., "Sept 11 2025")
- **description**: 20-40 words describing what happened, including key figures/names
- **source_url**: Full URL to the source article/document

**Example**:
```json
[
  {{
    "category": "M&A",
    "header": "Battery Tech Startup Acquisition",
    "date": "Sept 11 2025",
    "description": "Acquired battery tech startup for $2B to expand EV supply chain capabilities. Deal expected to close Q4 2025.",
    "source_url": "https://..."
  }},
  {{
    "category": "Management",
    "header": "New CFO Appointed",
    "date": "Aug 15 2025",
    "description": "Appointed Jane Doe as new CFO. She brings 20 years of experience from Fortune 500 companies.",
    "source_url": "https://..."
  }}
]
```

**IMPORTANT**: 
- Each development MUST include category, header, date, description, and source_url
- Use exact date from news article (extract from NEWS_AGENT)
- Categories must be one of the 5 specified options
- Maximum 4-6 total developments

### 6. Sources (sources field)
- 8-12 minimum
- Format: "Source Name - URL - Date Accessed (YYYY-MM-DD)"

## Data Sources:
- **NEWS_AGENT**: Recent developments, strategic moves, M&A - **EXTRACT dates and URLs**
- **EARNINGS_AGENT**: Management commentary, guidance, risks, **latest quarter highlights**

## Compliance Check:
Before submitting, verify you have filled:
✓ strength (4-6 items)
✓ weakness (4-6 items)
✓ opportunity (4-6 items)
✓ threat (4-6 items)
✓ investment_thesis (3-4 dictionaries)
✓ key_risk_highlights (5-7 items)
✓ strategic_opportunities (3-4 dictionaries)
✓ recent_developments (4-6 dictionaries with category, date, description, source_url)
✓ sources (8-12 items)
✓ news_summary (3-5 dictionaries)
✓ key_highlights (3-4 dictionaries)

### 7. News Summary (news_summary field - REQUIRED)
**Format**: List of 3-5 dictionaries, each with:
- Key: Thematic heading
- Value: List of 2-4 news bullet points (15-30 words each)

**Example**:
```json
[
  {{"Product Launches": ["Launched new AI chip series with 50% performance improvement over previous generation", "Announced partnership with major cloud provider for next-gen data centers"]}},
  {{"Market Expansion": ["Expanded operations into Southeast Asia with new manufacturing facility in Vietnam", "Secured $5B contract with European automotive consortium"]}}
]
```
**IMPORTANT**:
- Extract from NEWS_AGENT content primarily
- Group related news items under logical themes
- Focus on material news from last 6-12 months
- Each bullet should be concise but informative
- Prioritize news that impacts company , sector and others,  in this order

### 8. Key Highlights from Latest Quarter (key_highlights field - REQUIRED)
**Format**: List of 3-4 dictionaries, each with:
- Key: Thematic heading (e.g., "Financial Performance", "Operational Milestones", "Strategic Initiatives", "Guidance Updates")
- Value: List of 2-4 highlight bullet points (15-30 words each)

**Example**:
```json
[
  {{"Financial Performance": ["Record quarterly revenue of $X.XB, up X% YoY, driven by strong demand in key segments", "Operating margin expanded to X%, reflecting operational efficiency improvements"]}},
  {{"Strategic Initiatives": ["Announced $XB investment in AI infrastructure expansion over next 24 months", "Launched new product line expected to generate $XB in annual revenue"]}}
]
```

**IMPORTANT**:
- Extract from EARNINGS_AGENT content primarily (latest quarterly earnings call/report)
- Focus on most recent quarter's key developments
- Group related highlights under logical themes
- Each bullet should be specific, data-backed, and concise
- Prioritize material financial results, operational achievements, and forward-looking statements

**DO NOT skip any field. If data is limited, synthesize from available information.**
"""

# System prompts remain the same
FINANCIAL_METRICS_SYSTEM_PROMPT = """
You are a financial data extraction specialist. Your task is to extract precise financial metrics from SEC filings and financial documents with 100% accuracy. Always cite your sources and use exact figures from the documents provided. If you need to calculate a metric, show your work. Never estimate or guess - use only data present in the documents.
"""

STRATEGIC_ANALYSIS_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing strategic briefings for client meetings. Your analysis must be concise, data-driven, and actionable. Focus on insights that help bankers engage effectively with clients. Eliminate generic observations - every point should be specific to this company and backed by evidence from the provided documents. Prioritize material information that impacts business decisions.
"""


src/services/response_builder_and_generator.py
"""
Response Builder and Generator Service Module
Contains all the business logic for response building and generation.
"""
from src.utils.utils import async_time_it
import json
from typing import Dict, Any, List
from typing import Optional
from pydantic import BaseModel, Field
import ast
import re
import os 
import asyncio
import time
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from src.services.enums import ToolName
from src.utils.utils import async_timed_lru_cache
from rbc_security import enable_certs
from src.utils.utils import create_bearer_token
enable_certs()


from src.services.llm.client import call_llm_raw, get_oauth_token
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput, ResponseBuilderOutput

from src.utils.utils import async_time_it
from src.services.llm_prompts import (
            DATA_FOR_FINANCIAL_METRICS_PROMPT,
            DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
            FINANCIAL_METRICS_PROMPT,
            STRATEGIC_ANALYSIS_PROMPT,
            FINANCIAL_METRICS_SYSTEM_PROMPT,
            STRATEGIC_ANALYSIS_SYSTEM_PROMPT
        )
from src.services.data_models.llm_schemas import (
            FinancialMetricsResponse,
            StrategicAnalysisResponse
        )
from src.utils.validation_utils import MetricsValidator


import logging

logger = logging.getLogger(__name__)


class ResponseBuilderAndGenerator:
    """Service class containing all response builder and generator functionality"""


    @staticmethod
    def sanitize_prompt_for_guardrails(text: str) -> str:
        """Remove patterns that trigger false positive guardrail blocks"""
        # Remove chunk IDs that look like crypto addresses
        text = re.sub(r'chunk_id:\s*[A-Z0-9]{20,}', 'chunk_id: REDACTED', text)
        text = re.sub(r"chunk_id=['\"][A-Z0-9]{20,}['\"]", "chunk_id='REDACTED'", text)
        
        # Remove document IDs
        text = re.sub(r'document_id:\s*[A-Z0-9]{15,}', 'document_id: REDACTED', text)
        
        # Shorten URLs (keep domain but remove paths/parameters)
        text = re.sub(r'(https?://[^/\s]+)/[^\s]*', r'\1', text)
        
        # Remove long alphanumeric strings that look like account numbers
        text = re.sub(r'\b[A-Z0-9]{15,}\b', 'REDACTED', text)
        
        return text
      

    @staticmethod
    def _get_agent_cache_config(agent_name: str) -> dict:
        """
        Dynamically get cache configuration for an agent from environment variables.
        
        Expected env vars:
        - {AGENT_PREFIX}_AGENT_CACHE=True/False
        - {AGENT_PREFIX}_AGENT_CACHE_SECONDS=3600
        - {AGENT_PREFIX}_AGENT_CACHE_SIZE=128
        
        Example: For "news_agent", looks for NEWS_AGENT_CACHE, NEWS_AGENT_CACHE_SECONDS, etc.
        """
        
        # Get cache settings from env vars with sensible defaults
        cache_enabled = os.getenv(f"{agent_name}_CACHE").lower() == "true"
        cache_seconds = int(os.getenv(f"{agent_name}_CACHE_SECONDS"))
        cache_maxsize = int(os.getenv(f"{agent_name}_CACHE_SIZE"))
        
        return {
            "enabled": cache_enabled,
            "seconds": cache_seconds,
            "maxsize": cache_maxsize
        }

    # Cached version of the function
    @staticmethod
    @async_timed_lru_cache(
        seconds=int(os.getenv("DATA_AGENT_CACHE_SECONDS", "1800")),
        maxsize=int(os.getenv("DATA_AGENT_CACHE_SIZE", "256"))
    )
    async def _execute_agent_subqueries_cached(agent_name: str, subqueries: tuple):
        """Cached version - used for agents with caching enabled."""
        result = await ResponseBuilderAndGenerator._execute_agent_subqueries_impl(agent_name, subqueries)
        return result

    @staticmethod
    async def _execute_agent_subqueries_impl(agent_name: str, subqueries: tuple):
        """
        Core implementation of agent subquery execution (no caching).
        
        Args:
            agent_name: Name of the agent (e.g., "news_agent", "earnings_agent")
            subqueries: Tuple of subquery tuples (converted from dicts for hashability)
            
        Returns:
            List of content chunks from the agent
            
        Raises:
            Exception if agent execution fails (prevents caching of errors)
        """
        parsed_agent_name = agent_name.upper().split("_")[0]
        server_token = os.getenv(f"{parsed_agent_name}_AGENT_MCP_SECRET")
        bearer_token = create_bearer_token(server_token)
        server_url = os.getenv(f"{parsed_agent_name}_AGENT_MCP_URL")
        tool_name = os.getenv(f"{parsed_agent_name}_AGENT_MCP_TOOL")
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

        agent_chunks = []
        subquery_errors = []  # Track errors
        
        try:
            # Create MCP session for this agent
            async with streamablehttp_client(server_url, headers=headers) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    # Execute all subqueries for this agent
                    for subquery_tuple in subqueries:
                        try:
                            # Convert tuple back to dict for MCP call
                            subquery_dict = dict(subquery_tuple)
                            
                            chunks_for_subquery = await session.call_tool(
                                name=tool_name,
                                arguments=subquery_dict
                            )
                            content = chunks_for_subquery.model_dump()["content"] if chunks_for_subquery else None
                            if content:
                                agent_chunks.extend(content)
                            else:
                                error_msg = f"No content returned for subquery: {subquery_dict}"
                                logger.warning(f"{agent_name}: {error_msg}")
                                subquery_errors.append(error_msg)
                        except Exception as e:
                            error_msg = f"Error for subquery {subquery_dict if 'subquery_dict' in locals() else subquery_tuple}: {e}"
                            logger.error(f"{agent_name}: {error_msg}", exc_info=True)
                            subquery_errors.append(error_msg)
                            
        except Exception as e:
            error_msg = f"Error initializing MCP session for {agent_name}: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)
        
        # If ANY errors occurred, raise exception to prevent caching
        if subquery_errors:
            error_summary = f"{agent_name} had {len(subquery_errors)} subquery error(s): {subquery_errors}"
            logger.warning(error_summary)
            raise ValueError(error_summary)
        
        # If no chunks were retrieved at all, raise exception
        if not agent_chunks:
            raise ValueError(f"No chunks retrieved for agent {agent_name} with subqueries {subqueries}")
        
        return agent_chunks

    @staticmethod
    async def _execute_agent_subqueries(agent_name: str, subqueries: tuple):
        """
        Router function that decides whether to use cached or non-cached version
        based on agent configuration from environment variables.
        Returns (result, was_cached) tuple.
        """
        # Dynamically get cache config from env vars
        cache_config = ResponseBuilderAndGenerator._get_agent_cache_config(agent_name)
        
        if cache_config["enabled"]:
            logger.info(f"Using CACHED execution for {agent_name} (TTL: {cache_config['seconds']}s, Size: {cache_config['maxsize']})")
            # Cached version returns (result, was_cached) from decorator
            return await ResponseBuilderAndGenerator._execute_agent_subqueries_cached(agent_name, subqueries)
        else:
            logger.info(f"Using NON-CACHED execution for {agent_name}")
            # Non-cached version returns just result, add False for cache status
            result = await ResponseBuilderAndGenerator._execute_agent_subqueries_impl(agent_name, subqueries)
            return result, False

    @staticmethod
    async def execute_subqueries_on_data_agents(subqueries_by_agent: dict):
        """
        Execute subqueries on data agents with caching per agent.
        Returns data_agent_chunks, errors, and cache_info.
        
        Uses cached _execute_agent_subqueries for each agent to avoid redundant API calls.
        """
        data_agent_chunks = {
            ToolName.NEWS_TOOL.value: [], 
            ToolName.EARNINGS_TOOL.value: [], 
            ToolName.SEC_TOOL.value: []
        }
        errors = {}
        cache_info = {}

        # Create tasks for all agents to run concurrently
        agent_tasks = []
        agent_names = []
        
        for agent_name, subqueries in subqueries_by_agent.items():
            # Convert subqueries list to tuple for hashability (required for cache key)
            subqueries_tuple = tuple(
                tuple(sorted(sq.items())) if isinstance(sq, dict) else sq 
                for sq in subqueries
            )
            
            # Create task for this agent
            task = ResponseBuilderAndGenerator._execute_agent_subqueries(
                agent_name=agent_name,
                subqueries=subqueries_tuple
            )
            agent_tasks.append(task)
            agent_names.append(agent_name)
        
        # Execute all agents concurrently
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        
        # Process results
        for agent_name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                # Agent failed - log error but don't cache
                error_msg = str(result)
                errors[agent_name] = [error_msg]
                cache_info[agent_name] = False
                logger.error(f"Agent {agent_name} failed: {error_msg}")
            else:
                # Agent succeeded - unpack (chunks, was_cached) tuple
                chunks, was_cached = result
                data_agent_chunks[agent_name] = chunks
                cache_info[agent_name] = was_cached
                logger.info(f"Agent {agent_name} returned {len(chunks)} chunks (cached: {was_cached})")

        return data_agent_chunks, errors, cache_info
    
    @staticmethod
    async def parse_earnings_agent_response(text_field):
        chunks = []
    
        # Split by RetrievedChunkExtended and process each
        chunk_strings = re.split(r'RetrievedChunkExtended\(', text_field)
        
        for chunk_str in chunk_strings:
            try:
                # Extract key fields using regex
                chunk_id_match = re.search(r"chunk_id='([^']*)'", chunk_str)
                score_match = re.search(r"score=([\d.]+)", chunk_str)
                
                # Extract the content dict text
                text_match = re.search(r"'text':\s*'((?:[^'\\]|\\.)*)'", chunk_str, re.DOTALL)
                if not text_match:
                    text_match = re.search(r"'text':\s*\"((?:[^\"\\]|\\.)*?)\"", chunk_str, re.DOTALL)
                
                # Extract metadata
                ticker_match = re.search(r"'TICKER':\s*'([^']*)'", chunk_str)
                date_match = re.search(r"'EVENT_DT':\s*'([^']*)'", chunk_str)
                title_match = re.search(r"'TITLE':\s*'([^']*)'", chunk_str)
                
                chunk_data = {
                    'chunk_id': chunk_id_match.group(1) if chunk_id_match else None,
                    'score': float(score_match.group(1)) if score_match else None,
                    'text': text_match.group(1) if text_match else None,
                    'ticker': ticker_match.group(1) if ticker_match else None,
                    'event_date': date_match.group(1) if date_match else None,
                    'title': title_match.group(1) if title_match else None
                }
                
                chunks.append(chunk_data)
            except Exception as e:
                print(f"Error parsing chunk: {e}")
                continue
        
        return chunks

    @staticmethod
    async def context_parser(data_agent_chunks: Dict[str, Any]) -> tuple:
        """
        Parses and processes the content prioritization data to extract relevant context.
        Returns (parsed_result, errors) tuple.
        """
        resp = {}
        errors = {}

        for agent, agent_mcp_chunks_raw in data_agent_chunks.items():
            try:
                if agent == ToolName.EARNINGS_TOOL.value:
                    agent_chunks = []
                    for chunk in agent_mcp_chunks_raw:

                        text_field = chunk.get("text", "")

                        chunks = await ResponseBuilderAndGenerator.parse_earnings_agent_response(text_field)
                        formatted_output = []
        
                        for idx, chunk in enumerate(chunks, 1):
                            # Skip chunks without text
                            if not chunk.get('text'):
                                continue
                            
                            # Build the chunk header
                            chunk_header = f"CHUNK-{idx}\n\n"
                            
                            # Build metadata section
                            metadata_lines = ["METADATA"]
                            if chunk.get('title'):
                                metadata_lines.append(f"title: {chunk['title']}")
                            if chunk.get('ticker'):
                                metadata_lines.append(f"ticker: {chunk['ticker']}")
                            if chunk.get('event_date'):
                                metadata_lines.append(f"event_date: {chunk['event_date']}")
                            if chunk.get('score') is not None:
                                metadata_lines.append(f"relevancy: {chunk['score']:.5f}")
                            if chunk.get('chunk_id'):
                                metadata_lines.append(f"chunk_id: {chunk['chunk_id']}")
                            
                            metadata_section = "\n".join(metadata_lines) + "\n\n\n"
                            
                            # Build content section
                            content_section = f"CHUNK-CONTENT\n{chunk['text']}\n\n\n"
                            
                            # Combine all parts
                            formatted_chunk = chunk_header + metadata_section + content_section
                            formatted_output.append(formatted_chunk)
                            
                    resp[agent] = "\n\n\n".join(formatted_output)

                elif agent == ToolName.NEWS_TOOL.value or agent == ToolName.SEC_TOOL.value:
                    agent_chunks = []
                    for chunk in agent_mcp_chunks_raw:
                        text_field = chunk.get("text", "")
                        
                        # Skip JSON parsing if already formatted text
                        # if text_field.startswith("CHUNK-"):
                        #     agent_chunks.append(text_field)
                        #     continue
                        
                        try:
                            parsed = json.loads(text_field)
                        except Exception:
                            try:
                                parsed = ast.literal_eval(text_field)
                            except Exception as e:
                                errors.setdefault(agent, []).append(f"Parsing failed: {e}")
                                parsed = []
                        if isinstance(parsed, list):
                            for idx, article in enumerate(parsed):
                                if not isinstance(article, dict):
                                    continue
                                main_text = article.get("text", "")
                                metadata = {k: v for k, v in article.items() if k != "text"}
                                if "_north_metadata" in metadata and isinstance(metadata["_north_metadata"], dict):
                                    for mk, mv in metadata["_north_metadata"].items():
                                        metadata[mk] = mv
                                    del metadata["_north_metadata"]
                                chunk_number = str(idx + 1)
                                metadata_lines = [f"{k}: {v}" for k, v in metadata.items()]
                                chunk_str = f"CHUNK-{chunk_number}\n\n"
                                chunk_str += "METADATA\n"
                                if metadata_lines:
                                    chunk_str += "\n".join(metadata_lines) + "\n"
                                chunk_str += "\n\nCHUNK-CONTENT\n"
                                chunk_str += main_text if isinstance(main_text, str) else str(main_text)
                                agent_chunks.append(chunk_str)
                        elif isinstance(parsed, dict):
                            main_text = parsed.get("text", "")
                            metadata = {k: v for k, v in parsed.items() if k != "text"}
                            if "_north_metadata" in metadata and isinstance(metadata["_north_metadata"], dict):
                                for mk, mv in metadata["_north_metadata"].items():
                                    metadata[mk] = mv
                                del metadata["_north_metadata"]
                            chunk_number = "1"
                            metadata_lines = [f"{k}: {v}" for k, v in metadata.items()]
                            chunk_str = f"CHUNK-{chunk_number}\n\n"
                            chunk_str += "METADATA\n"
                            if metadata_lines:
                                chunk_str += "\n".join(metadata_lines) + "\n"
                            chunk_str += "\n\nCHUNK-CONTENT\n"
                            chunk_str += main_text if isinstance(main_text, str) else str(main_text)
                            agent_chunks.append(chunk_str)
                    resp[agent] = "\n\n\n".join(agent_chunks)
            except Exception as e:
                errors.setdefault(agent, []).append(f"Agent-level parsing failed: {e}")

        return resp, errors

       

    @staticmethod
    async def prompt_builder(
        
        parsed_data_agent_chunks,
        company_name, 
        FINANCIAL_METRICS_PROMPT,
        STRATEGIC_ANALYSIS_PROMPT,
        DATA_FOR_FINANCIAL_METRICS_PROMPT,
        DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
        content_prioritization_data_distribution
    ):
        """
        Builds prompts based on the content prioritization data.
        """

        parsed_DATA_FOR_FINANCIAL_METRICS_PROMPT = DATA_FOR_FINANCIAL_METRICS_PROMPT.format(
        EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value),
        SEC_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.SEC_TOOL.value),
        NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value)
        )

        parsed_DATA_FOR_STRATEGIC_ANALYSIS_PROMPT = DATA_FOR_STRATEGIC_ANALYSIS_PROMPT.format(
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value),
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value),
            SEC_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.SEC_TOOL.value),
            NEWS_percentage=content_prioritization_data_distribution[ToolName.NEWS_TOOL.value],
            EARNINGS_percentage=content_prioritization_data_distribution[ToolName.EARNINGS_TOOL.value],
            SEC_percentage=content_prioritization_data_distribution[ToolName.SEC_TOOL.value]
        )

        parsed_FINANCIAL_METRICS_PROMPT = FINANCIAL_METRICS_PROMPT.format(
            DATA_FOR_FINANCIAL_METRICS=parsed_DATA_FOR_FINANCIAL_METRICS_PROMPT,
            COMPANY_NAME=company_name
        )

        parsed_STRATEGIC_ANALYSIS_PROMPT = STRATEGIC_ANALYSIS_PROMPT.format(
            DATA_FOR_STRATEGIC_ANALYSIS=parsed_DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
            COMPANY_NAME=company_name
        )

        # Sanitize ONLY strategic analysis (it's longer and triggers guardrails)
        parsed_STRATEGIC_ANALYSIS_PROMPT = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(
            parsed_STRATEGIC_ANALYSIS_PROMPT
        )

        return parsed_FINANCIAL_METRICS_PROMPT, parsed_STRATEGIC_ANALYSIS_PROMPT
    

    @staticmethod
    async def get_structured_response(
        user_prompt, 
        system_prompt, 
        response_obj, 
        name, 
        description
    ):
        """Extract financial metrics using structured output. Returns (result, error) tuple."""
        error = None
        result = None
        try:
            schema = response_obj.model_json_schema()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            tools = [{
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": schema
                }
            }]
            response = await call_llm_raw(
                messages=messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": name}}
            )

            

            try:
                tool_call = response["choices"][0]["message"]["tool_calls"][0]
            
            except Exception as e:
                # DEBUG: Print full response structure
                print(f"\n\n=== FULL LLM RESPONSE for {name} ===")
                print(json.dumps(response, indent=2, default=str))
                print("=== END ===\n\n")

            arguments = json.loads(tool_call["function"]["arguments"])

            # DEBUG: Print what LLM returned
            print("\n\n=== LLM RESPONSE ===")
            print(json.dumps(arguments, indent=2))
            print("\n=== MISSING/NULL FIELDS ===")
            required_fields = response_obj.model_fields.keys()
            for field in required_fields:
                if field not in arguments:
                    print(f"MISSING: {field}")
                elif arguments[field] is None:
                    print(f"NULL: {field}")
            print("=== END ===\n\n")


            # Clean up string placeholders for numeric fields
            for k, v in arguments.items():
                if isinstance(v, str) and v.strip().upper() in {"<UNKNOWN>", "N/A", "NULL", "NONE"}:
                    arguments[k] = None

            result = response_obj(**arguments)
        except Exception as e:
            error = str(e)
            logger.error(f"Error in get_structured_response: {error}", exc_info=True)
            result = None
        return result, error
    

    @staticmethod
    async def response_builder(
        financial_metrics_prompt,
        strategic_analysis_prompt,
        financial_metrics_system_prompt,
        strategic_analysis_system_prompt,
        FinancialMetricsResponse,
        StrategicAnalysisResponse
    ):
        financial_metrics_response_name = "extract_financial_metrics"
        financial_metrics_response_description = "Extract precise financial metrics from SEC filings and earnings reports"

        strategic_analysis_response_name = "generate_strategic_analysis"
        strategic_analysis_response_description = "Generate comprehensive strategic analysis for investment banking client meeting"

        # Start BOTH calls concurrently using asyncio.gather
        fm_tuple, sa_tuple = await asyncio.gather(
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=financial_metrics_prompt,
                system_prompt=financial_metrics_system_prompt,
                response_obj=FinancialMetricsResponse,
                name=financial_metrics_response_name,
                description=financial_metrics_response_description
            ),
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=strategic_analysis_prompt,
                system_prompt=strategic_analysis_system_prompt,
                response_obj=StrategicAnalysisResponse,
                name=strategic_analysis_response_name,
                description=strategic_analysis_response_description
            )
        )

        financial_metrics_result, financial_metrics_error = fm_tuple
        strategic_analysis_result, strategic_analysis_error = sa_tuple

        return (
            (financial_metrics_result, financial_metrics_error),
            (strategic_analysis_result, strategic_analysis_error)
        )
    

    @staticmethod
    async def execute(
        context_builder_output: ContextBuilderOutput,
        content_prioritization_output: ContentPrioritizationOutput
    ) -> ResponseBuilderOutput:
        """
        Execute the full response builder and generator pipeline.
        """
        timings = {}
        errors = {}

        corporate_client_firm_response = context_builder_output["corporate_client_firm_response"]
        if corporate_client_firm_response:
            company_name = corporate_client_firm_response.get("company_name")
        else:
            company_name = context_builder_output["request_company_name"]

        temporal_source_prioritizer = content_prioritization_output["temporal_source_prioritizer"]
        subqueries_from_engine = content_prioritization_output["subqueries_from_engine"]

        # Step 1: Execute subqueries on data agents
        (data_agent_chunks, data_agent_errors, agent_cache_info), timings["execute_subqueries_on_data_agents"] = await async_time_it(
            ResponseBuilderAndGenerator.execute_subqueries_on_data_agents
        )(subqueries_by_agent=subqueries_from_engine)
        if data_agent_errors:
            errors["execute_subqueries_on_data_agents"] = data_agent_errors
        

        # Step 2: Context parser
        (parsed_data_agent_chunks, context_parser_errors), timings["context_parser"] = await async_time_it(
            ResponseBuilderAndGenerator.context_parser
        )(data_agent_chunks=data_agent_chunks)
        if context_parser_errors:
            errors["context_parser"] = context_parser_errors

        logger.info(f"\n\n\n Parsed Data Agent Chunks Character Lengths: {[(agent, len(content)) for agent, content in parsed_data_agent_chunks.items()]} \n\n\n")

        # Check if all data agent chunks are empty
        total_content_length = sum(len(content) for content in parsed_data_agent_chunks.values())
        if total_content_length == 0:
            logger.warning("All data agent chunks are empty - skipping LLM calls")
            errors["data_agents"] = "All data agents returned empty results"
            result = {
                "financial_metrics_result": None,
                "strategic_analysis_result": None,
                "timings": timings,
                "cached": {"data_agents": agent_cache_info},
                "errors": errors,
                "parsed_data_agent_chunks": parsed_data_agent_chunks,
                "company_name": company_name,
            }
            return result

        # Step 3: Prompt builder
        (parsed_FINANCIAL_METRICS_PROMPT, parsed_STRATEGIC_ANALYSIS_PROMPT), timings["prompt_builder"] = await async_time_it(
            ResponseBuilderAndGenerator.prompt_builder
        )(
            parsed_data_agent_chunks=parsed_data_agent_chunks,
            company_name=company_name,
            FINANCIAL_METRICS_PROMPT=FINANCIAL_METRICS_PROMPT,
            STRATEGIC_ANALYSIS_PROMPT=STRATEGIC_ANALYSIS_PROMPT,
            DATA_FOR_FINANCIAL_METRICS_PROMPT=DATA_FOR_FINANCIAL_METRICS_PROMPT,
            DATA_FOR_STRATEGIC_ANALYSIS_PROMPT=DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
            content_prioritization_data_distribution=temporal_source_prioritizer
        )

        # Step 4: Response builder
        (financial_metrics_tuple, strategic_analysis_tuple), timings["response_builder"] = await async_time_it(
            ResponseBuilderAndGenerator.response_builder
        )(
            financial_metrics_prompt=parsed_FINANCIAL_METRICS_PROMPT,
            strategic_analysis_prompt=parsed_STRATEGIC_ANALYSIS_PROMPT,
            financial_metrics_system_prompt=FINANCIAL_METRICS_SYSTEM_PROMPT,
            strategic_analysis_system_prompt=STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
            FinancialMetricsResponse=FinancialMetricsResponse,
            StrategicAnalysisResponse=StrategicAnalysisResponse
        )

        financial_metrics_result, financial_metrics_error = financial_metrics_tuple
        strategic_analysis_result, strategic_analysis_error = strategic_analysis_tuple

        if financial_metrics_error:
            errors["financial_metrics_response"] = financial_metrics_error
        if strategic_analysis_error:
            errors["strategic_analysis_response"] = strategic_analysis_error

        # Step 5: Validate financial metrics extraction
        validation_results = None
        if financial_metrics_result:
            try:
                start_time = time.perf_counter()
                validation_results = MetricsValidator.validate_financial_metrics(
                    metrics=financial_metrics_result,
                    source_chunks=parsed_data_agent_chunks
                )
                timings["validate_financial_metrics"] = time.perf_counter() - start_time
                logger.info(f"Execution time for validate_financial_metrics: {timings['validate_financial_metrics']:.2f} seconds")
                
                # Log validation summary
                logger.info(f"Validation Summary: {validation_results['validation_summary']}")
                
                # Print detailed validation report (optional - can be controlled by config)
                if logger.isEnabledFor(logging.DEBUG):
                    MetricsValidator.print_validation_report(validation_results)
                
                # Add warnings to errors dict if any validation issues found
                if validation_results["warnings"]:
                    errors["validation_warnings"] = validation_results["warnings"]
                    
            except Exception as e:
                logger.error(f"Error during metrics validation: {e}", exc_info=True)
                errors["validation_error"] = str(e)

        result = {
            "financial_metrics_result": financial_metrics_result,
            "strategic_analysis_result": strategic_analysis_result,
            "validation_results": validation_results,
            "timings": timings,
            "cached": {"data_agents": agent_cache_info},
            "errors": errors,
            "parsed_data_agent_chunks": parsed_data_agent_chunks,
            "company_name": company_name,
        }

        return result

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    async def test_earnings_agent():
        """Test earnings agent MCP tool call"""
        
        # Set up environment variables (or load from .env)
        server_url = os.getenv("EARNINGS_AGENT_MCP_URL", "https://tg40-earnings-mcp.cfkqa.saifg.rbc.com/mcp/")
        server_secret = os.getenv("EARNINGS_AGENT_MCP_SECRET", "2110abc96")
        tool_name = os.getenv("EARNINGS_AGENT_MCP_TOOL", "_advanced_search_earnings_call_analyzer")
        
        bearer_token = create_bearer_token(server_secret)
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
        
        print(f"Server URL: {server_url}")
        print(f"Tool Name: {tool_name}")
        
        # Test query
        test_query = {
            "query": "Give me the earnings transcript for Tesla for fiscal year: 2025 and quarter: Q1."
        }
        
        try:
            async with streamablehttp_client(server_url, headers=headers) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    
                    # List available tools
                    tools = await session.list_tools()
                    print(f"\nAvailable tools: {[tool.name for tool in tools.tools]}")
                    
                    # Call the earnings tool
                    print(f"\nCalling earnings tool with query: {test_query}")
                    result = await session.call_tool(
                        name=tool_name,
                        arguments=test_query
                    )
                    
                    # Print raw response
                    print("\n=== RAW RESPONSE ===")
                    print(result)
                    
                    # Extract and print content
                    if result.content:
                        print("\n=== CONTENT ===")
                        for idx, content_item in enumerate(result.content):
                            print(f"\nContent Item {idx + 1}:")
                            if hasattr(content_item, 'text'):
                                print(content_item.text[:500])  # First 500 chars
                            else:
                                print(content_item)
                    
                    # Parse using the earnings parser
                    print("\n=== PARSED CHUNKS ===")
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            chunks = await ResponseBuilderAndGenerator.parse_earnings_agent_response(content_item.text)
                            print(f"\nFound {len(chunks)} chunks")
                            for i, chunk in enumerate(chunks[:3]):  # Show first 3
                                print(f"\nChunk {i + 1}:")
                                print(f"  Title: {chunk.get('title')}")
                                print(f"  Ticker: {chunk.get('ticker')}")
                                print(f"  Date: {chunk.get('event_date')}")
                                print(f"  Score: {chunk.get('score')}")
                                print(f"  Text preview: {chunk.get('text', '')[:200]}")
                    
        except Exception as e:
            print(f"\nError during MCP call: {e}")
            import traceback
            traceback.print_exc()
    
    # Run the test
    asyncio.run(test_earnings_agent())



src/services/static_subquery_engine.py
from datetime import datetime, timedelta
from src.services.enums import ToolName
    

class StaticSubqueryEngine:

    @staticmethod
    def get_SEC_agent_query_argument(company_name) -> dict:
        """
        Args:
            meeting_date: Optional date string in 'YYYY-MM-DD' format. 
                        If None, uses today's date.
        """
        
        return [
                
    
                {
        "reporting_entity": f"{company_name}",
        "search_queries": [
            "consolidated statements of operations","statements of income","total revenue"
        ],
        "keywords": [
            "net sales",
            "total revenue",
            "net product sales",
            "net service sales",
            "three months ended",
            "quarterly revenue",
            "consolidated statements of operations",
            "total net sales",
            "revenue",
        ],
        "retrieve": 8,
                },
                {
                "reporting_entity": f"{company_name}",
      "search_queries": [
        "consolidated balance sheets",
        "stockholders equity",
        "common stock outstanding shares"
      ],
      "keywords": [
        "outstanding shares",
        "common stock",
        "shares outstanding",
        "issued shares",
        "share capital",
        "stockholders equity",
        "equity structure",
        "shares issued",
        "capital stock",
        "basic shares"
      ],
      "retrieve": 1
                } 


        ]

    @staticmethod
    def get_earnings_agent_query_argument(company_name: str, fiscal_year: str, fiscal_quarter: str) -> dict:
        return [
            {
                "query": f"Give me the earnings transcript for {company_name} for fiscal year: {fiscal_year} and quarter: {fiscal_quarter}.",
            }
        ]
    

    @staticmethod
    def get_news_agent_query_argument(company_name: str) -> list[dict]:
        end_date = datetime.now().strftime('%Y-%m-%d')
        once_month_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=31)).strftime('%Y-%m-%d')
        five_days_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
        absolute_date_range = {"start_date": once_month_ago, "end_date": end_date}
        one_year_and_five_days_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=365+5)).strftime('%Y-%m-%d')
        one_year_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
        one_year_and_a_day_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=366)).strftime('%Y-%m-%d')
        return [
            {

             "search_query": f"{company_name} stock price performance",
            "relative_date_range": "last_24_hours",
            "entities": [f"{company_name}"]
            },

            {
            "search_query": f"{company_name} stock price performance",
            "topics": [
                "stock price",
                "share price",
                "stock performance",
                "share performance",
                "price change",
                "price movement"
            ],
            "entities": [
                f"{company_name}"
            ],
            "absolute_date_range": {
                "start_date": one_year_and_a_day_ago,
                "end_date": one_year_ago
                }
            },

            {
                    "search_query": f"{company_name} executive leadership changes appointments departures CEO CFO senior management hires",
                    "topics": [
                        "executive",
                        "CEO",
                        "CFO",
                        "leadership",
                        "appointment",
                        "hire",
                        "departure"
                    ],
                    "entities": [
                        f"{company_name}"
                    ]
            },

            {
                "search_query": f"{company_name} mergers acquisitions M&A strategic transactions deal announced acquired acquiring",
                "topics": [
                    "merger",
                    "acquisition",
                    "M&A",
                    "deal",
                    "transaction"
                ],
                "entities": [
                    f"{company_name}"
                ]
            },



            {
                "search_query": f"{company_name} regulatory issues lawsuit litigation investigation antitrust compliance controversy",
                "topics": [
                    "regulatory",
                    "lawsuit",
                    "litigation",
                    "investigation",
                    "compliance"
                ],
                "entities": [
                    f"{company_name}"
                ]
            },



            {
                "search_query": f"{company_name} strategic pivot restructuring expansion office opening closing organizational changes credit rating investor relations",
                "topics": [
                    "restructuring",
                    "expansion",
                    "strategic pivot",
                    "office",
                    "credit rating",
                    "investor relations",
                    "AGM"
                ],
                "entities": [
                    f"{company_name}"
            ]
            },
            
        ]
    @staticmethod
    def get_subquery_arguments(company_name: str, fiscal_year: str, fiscal_quarter: str):
        return  {
            ToolName.EARNINGS_TOOL.value: StaticSubqueryEngine.get_earnings_agent_query_argument(company_name, fiscal_year, fiscal_quarter),
            ToolName.NEWS_TOOL.value: StaticSubqueryEngine.get_news_agent_query_argument(company_name),
             ToolName.SEC_TOOL.value: StaticSubqueryEngine.get_SEC_agent_query_argument(company_name),
        }


if __name__=="__main__":
    import os 
    import asyncio
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from rbc_security import enable_certs
    enable_certs()

    async def make_tool_call():
        server_url = os.environ["NEWS_AGENT_MCP_URL"]
        bearer_token = os.environ["NEWS_AGENT_MCP_BEARER_TOKEN"]
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
        print(server_url)
        async with streamablehttp_client(server_url, headers=headers) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"Available tools: {[tool.name for tool in tools.tools]}")

                news_args = StaticSubqueryEngine.get_news_agent_query_argument("BlackRock, Inc.", "2025-11-29")
                for idx, arg in enumerate(news_args):
                    print(f"\nCalling tool with news argument {idx+1}: {arg}\n")
                    result = await session.call_tool(
                        name=os.environ["NEWS_AGENT_MCP_TOOL"], 
                        arguments=arg
                    )
                    response_text = "".join([doc.text for doc in result.content])
                    print(response_text)
                    print(f"Response length for argument {idx+1}: {len(response_text)} \n\n\n")

    asyncio.run(make_tool_call())



src/services/data_models/llm_schemas.py
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class CitationDict(BaseModel):
    """Structured citation with source tracking and reasoning"""
    source_agent: List[str] = Field(
        description="List of data agents used. Valid values: 'SEC_agent', 'earnings_agent', 'news_agent'. Example: ['SEC_agent'] or ['SEC_agent', 'earnings_agent']"
    )
    source_content: List[str] = Field(
        description="List of verbatim quotes/phrases from source chunks. Each quote should be 10-200 words, directly copy-pasted from agent content. DO NOT paraphrase."
    )
    reasoning: str = Field(
        description="Explanation of how you derived this metric. For extracted values: 'Extracted from [document] [section]'. For calculated values: show step-by-step math with actual numbers. Example: 'Calculated EBITDA: (Operating Income $1.6B + D&A $1.0B) / Revenue $28.1B = 9.25%'"
    )

class StrategicAnalysisResponse(BaseModel):
    strength: List[str] = Field(
        description="List of 4-6 key competitive strengths from SWOT analysis. Each bullet should be specific, data-backed, and 15-25 words. Focus on: market position, financial health, operational advantages, brand strength, or proprietary capabilities. Cite metrics where possible."
    )
    weakness: List[str] = Field(
        description="List of 4-6 key vulnerabilities from SWOT analysis. Each bullet should be specific, data-backed, and 15-25 words. Focus on: competitive disadvantages, financial constraints, operational challenges, regulatory risks, or market exposure issues."
    )
    opportunity: List[str] = Field(
        description="List of 4-6 growth opportunities from SWOT analysis. Each bullet should be specific, actionable, and 15-25 words. Focus on: market expansion, new products/services, M&A targets, regulatory changes, or emerging trends that benefit the company."
    )
    threat: List[str] = Field(
        description="List of 4-6 external threats from SWOT analysis. Each bullet should be specific, data-backed, and 15-25 words. Focus on: competitive pressures, regulatory headwinds, market disruption, economic conditions, or technological changes threatening the business."
    )
    
    investment_thesis: List[Dict[str, List[str]]] = Field(
        description="Investment thesis structured as a list of dictionaries. Each dictionary has ONE subheading as key (e.g., 'Growth Drivers', 'Competitive Moat', 'Valuation Opportunity') and a list of 2-4 supporting bullet points as value. Each bullet should be 15-30 words. Total: 3-4 subheadings maximum."
    )
    
    key_risk_highlights: List[str] = Field(
        description="List of 5-7 critical risks that could impact investment thesis or business operations. Each bullet should be 15-30 words and include: specific risk factor, potential impact magnitude, and timeline if relevant. Prioritize material risks from SEC filings and recent news."
    )
    
    strategic_opportunities: List[Dict[str, List[str]]] = Field(
        description="Strategic opportunities for the company AND for RBC Capital Markets engagement, structured as list of dictionaries. Each dictionary has ONE subheading as key (e.g., 'M&A Advisory', 'Capital Raising', 'Strategic Repositioning') and 2-3 specific opportunity bullets as value. Each bullet: 15-30 words. Total: 3-4 subheadings maximum."
    )
    
    recent_developments: List[Dict[str, Any]] = Field(
        description="Recent FIRM-LEVEL developments (last 12 months) structured as list of dictionaries. Each dictionary must have: 'category' (one of: 'News', 'M&A', 'Management', 'Company', 'Industry'), 'header' (5-10 word title/summary of the development), 'date' (format: 'MMM DD YYYY' e.g., 'Sept 11 2025'), 'description' (20-40 words including what happened, key figures/names), and 'source_url' (hyperlink). Maximum 4-6 total developments. EXCLUDE portfolio company news unless it signals major strategic shift."
    )
    
    sources: List[str] = Field(
        description="Comprehensive list of all sources cited in the analysis. Format each as: 'Source Name - URL - Date Accessed (YYYY-MM-DD)'. Include: SEC filings, news articles, earnings transcripts, press releases. Minimum 8-12 sources for thorough analysis."
    )

    news_summary: List[Dict[str, List[str]]] = Field(
        description="Summary of recent news organized by theme/category, structured as list of dictionaries. Each dictionary has ONE thematic heading as key (e.g., 'Product Launches', 'Market Expansion', 'Regulatory Updates', 'Competitive Landscape') and 2-4 news bullet points as value. Each bullet: 15-30 words summarizing key news items. Total: 3-5 thematic categories maximum. Focus on material news from the last 6-12 months."
    )

    key_highlights: List[Dict[str, List[str]]] = Field(
        description="Key highlights from the latest quarterly earnings report, structured as list of dictionaries. Each dictionary has ONE thematic heading as key (e.g., 'Financial Performance', 'Operational Milestones', 'Strategic Initiatives', 'Guidance Updates') and 2-4 highlight bullet points as value. Each bullet: 15-30 words summarizing notable achievements, announcements, or developments from the most recent earnings call/report. Total: 3-4 thematic categories maximum. Prioritize EARNINGS_AGENT content."
    )

class FinancialMetricsResponse(BaseModel):
    current_annual_revenue: Optional[float] = Field(
        description="Current annual revenue of the company in billions USD, extracted from most recent SEC filing (10-K or 10-Q). This should be the total revenue/sales figure from the income statement."
    )
    current_annual_revenue_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for current annual revenue including source agents, verbatim quotes, and extraction reasoning."
    )
    
    current_annual_revenue_date: Optional[str] = Field(
        description="Date of the SEC filing from which current annual revenue was extracted (format: YYYY-MM-DD). Use the filing date, not the period end date."
    )
    current_annual_revenue_date_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for current annual revenue date including source agents, verbatim quotes showing filing date, and extraction reasoning."
    )
   
    current_annual_revenue_yoy_change: Optional[float] = Field(
        default=None,
        description="Year-over-year percentage change in annual revenue (e.g., 9.0 for +9% YoY). Compare current period revenue to same period prior year. Return null if insufficient data."
    )
    current_annual_revenue_yoy_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for YoY revenue change including source agents, verbatim quotes showing both current and prior year revenue figures, and calculation formula with actual numbers."
    )

    estimated_annual_revenue_next_year: Optional[float] = Field(
        description="Projected annual revenue for next fiscal year in billions USD, based on company guidance from SEC filings, earnings calls, or analyst estimates mentioned in the documents. If unavailable, extrapolate from current growth trends."
    )
    estimated_annual_revenue_next_year_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for estimated annual revenue including source agents, verbatim quotes, and reasoning/calculation method. REQUIRED even if value is null - explain which sources were checked (SEC forward guidance, earnings outlook, analyst estimates) and why no data was found."
    )

    estimated_annual_revenue_next_year_date: Optional[str] = Field(
        description="Date of the source document (SEC filing or earnings report) from which the revenue estimate was derived (format: YYYY-MM-DD)."
    )
    estimated_annual_revenue_next_year_date_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for estimated annual revenue date including source agents, verbatim quotes showing document date, and extraction reasoning."
    )
    
    ebitda_margin: Optional[float] = Field(
        default=None,
        description="EBITDA margin as a percentage (e.g., 25.5 for 25.5%), calculated from most recent SEC filing. Preferred: Annual or TTM data. If unavailable, use most recent nine-month, six-month, or quarterly data and CLEARLY STATE THE PERIOD in citation reasoning (e.g., 'Nine-Month EBITDA Margin'). Calculate as (Operating Income + Depreciation + Amortization) / Revenue * 100. CRITICAL: All three components (Operating Income, D&A, Revenue) MUST be from the same time period (e.g., all from 'Nine Months Ended September 30, 2025'). Return null ONLY if no financial data exists."
    )
    ebitda_margin_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for EBITDA margin including source agents, verbatim quotes of calculation components (Operating Income, D&A, Revenue) ALL from the SAME TIME PERIOD, and step-by-step calculation reasoning. MUST state the time period used (e.g., 'Nine Months Ended', 'Six Months Ended') in reasoning."
    )

    ebitda_margin_yoy_change: Optional[float] = Field(
        default=None,
        description="Year-over-year change in EBITDA margin as percentage points (e.g., 1.0 for +1% YoY). Compare current period margin to same period prior year. Return null if insufficient data."
    )
    ebitda_margin_yoy_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for YoY EBITDA margin change including source agents, verbatim quotes showing both current and prior period margin calculations, and step-by-step comparison."
    )

    stock_price: Optional[float] = Field(
        default=None,
        description="Most recent stock price in USD from news articles or market data. Use the latest available closing price mentioned in the documents. Return null if not available."
    )
    stock_price_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for stock price including source agents, verbatim quote with price and date/time context, and extraction reasoning."
    )

    stock_price_daily_change: Optional[float] = Field(
        default=None,
        description="Today's stock price change in USD (e.g., 1.39 for +$1.39 today). This is the absolute dollar change from previous close to current price. Return null if not available."
    )
    stock_price_daily_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for daily stock price change including source agents, verbatim quote with dollar change and date/time context, and extraction reasoning."
    )

    stock_price_daily_change_percent: Optional[float] = Field(
        default=None,
        description="Today's stock price percentage change (e.g., 0.56 for +0.56% today). This is the percentage change from previous close to current price. Return null if not available."
    )
    stock_price_daily_change_percent_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for daily stock price percentage change including source agents, verbatim quote with percentage change and date/time context, and extraction reasoning."
    )

    stock_price_yoy_change: Optional[float] = Field(
        default=None,
        description="Year-over-year percentage change in stock price (e.g., 15.5 for +15.5%, -8.2 for -8.2%). PREFERRED: Compare current price to price from same date one year prior. ACCEPTABLE: Use Year-to-Date (YTD) performance as proxy when exact YoY unavailable (e.g., if YTD = +29.10%, use 29.10 as approximate YoY). Return null only if no YoY or YTD data available."
    )
    stock_price_yoy_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for YoY stock price change including source agents, verbatim quotes showing both current and prior year prices with dates (if available), and calculation formula. If using YTD as proxy, explain in reasoning: 'Used YTD performance as YoY approximation' and include verbatim YTD quote. REQUIRED even if value is null - explain what sources were checked."
    )

    market_cap: Optional[float] = Field(
        default=None,
        description="Current market capitalization in billions USD, calculated as stock price × outstanding shares. Use most recent figures from SEC filings or news articles. Return null if insufficient data."
    )
    market_cap_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for market cap including source agents, verbatim quotes showing stock price and outstanding shares, and calculation formula (price × shares = market cap)."
    )

    market_cap_date: Optional[str] = Field(
        default=None,
        description="Date when market cap was calculated or reported (format: YYYY-MM-DD). Should match the stock price date. Return null if not available."
    )
    market_cap_date_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for market cap date including source agents, verbatim quote showing the date context, and extraction reasoning."
    )

    revenue_growth_trajectory: Optional[Dict[str, Optional[float]]] = Field(
    default=None,
    description="""

    Quarterly revenue in billions USD for the last 7 quarters, using fiscal quarter notation.

    **EXTRACTION APPROACH**:
    - Scan SEC chunks for 10-Q filings (contain Q1, Q2, Q3 data)
    - Look for "FORM 10-Q for Q[X], FY [YYYY]" in chunk metadata
    - Extract revenue from financial statement tables with "Three Months Ended [Date]" column headers
    - Search for: "SUMMARY RESULTS OF OPERATIONS", "INCOME STATEMENTS", or similar headers
    - Find "Revenue" line item in these tables (may appear as: "| |$|XX,XXX| |" or "Revenue $ XX,XXX")
    - Use fiscal quarter label from filing title as dictionary key (e.g., "Q1 FY2026")

    **Q4 CALCULATION**:
    - Formula: Q4 = Annual Revenue (10-K) - Nine Months Ended (Q3 10-Q)
    - Only calculate if BOTH components are explicitly present in the documents
    - When extracting annual and nine-month values, match the correct fiscal year column in multi-year tables
    - In your citation, specify the table row and the exact columns used for each value
    - Do NOT estimate any missing components
    - Show full calculation in citation with verbatim quotes from both sources

    **KEY FORMAT**: "Q[1-4] FY[YYYY]" matching the fiscal year from SEC filing titles

    **QUALITY RULES**:
    - Each quarter should appear ONCE (no duplicates)
    - Only use quarters with actual filing data or valid Q4 calculations
    - Use null for individual quarters where data is unavailable
    - Do NOT return null for the entire field if any quarterly data exists

    Example: {"Q1 FY2026": 77.673, "Q4 FY2025": 76.441, "Q3 FY2025": 70.066, "Q2 FY2025": 64.727, ...}
    """
    )
    revenue_growth_trajectory_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for quarterly revenue including verbatim quotes with EXACT filing references (e.g., '10-Q for Q3 FY2025 filed Apr 30, 2025') and explanation of fiscal quarter mapping."
    )


src/services/data_models/models.py
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class ContextBuilderOutput(BaseModel):
    corporate_client_firm_response: Optional[Dict[str, Any]] = None
    temporal_content_response: Optional[Dict[str, Any]] = None
    rbc_persona: Optional[Any] = None
    corporate_client_persona: Optional[Any] = None
    request_meeting_date: Optional[str] = None
    request_company_name: Optional[str] = None
    timings: Optional[Dict[str, float]] = None
    cached: Optional[bool] = None
    errors: Optional[Dict[str, Any]] = None

class ContentPrioritizationOutput(BaseModel):
    temporal_source_prioritizer: Optional[Dict[str, Any]] = None
    subqueries_from_engine: Optional[Dict[str, Any]] = None
    topic_ranker_result: Optional[Any] = None
    timings: Optional[Dict[str, float]] = None
    errors: Optional[Dict[str, Any]] = None

class ResponseBuilderOutput(BaseModel):
    financial_metrics_result: Optional[Any] = None
    strategic_analysis_result: Optional[Any] = None
    parsed_data_agent_chunks: Optional[Dict[str, Any]] = None
    company_name: Optional[str] = None
    timings: Optional[Dict[str, float]] = None
    cached: Optional[Dict[str, Any]] = None
    errors: Optional[Dict[str, Any]] = None



src/services/ldap_service/ldap_service.py
import logging
import os
import datetime

from ldap3 import Server, Connection, ALL, NTLM

from src.services.ldap_service.lookup_service_interface import LookupServiceInterface
from src.services.ldap_service.ldap_search_strategy.ldap_search_strategy_Interface import LDAPSearchStrategyInterface
from src.services.ldap_service.user_profile import UserProfile
from src.utils.utils import timed_lru_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)

logger = logging.getLogger(__name__)

class LDAPService(LookupServiceInterface):
    def __init__(self, ldap_search_strategy: LDAPSearchStrategyInterface):
        self.ldap_search_strategy = ldap_search_strategy

    @staticmethod
    @timed_lru_cache(seconds=60, maxsize=1)
    def build_ldap_connection():
        logger.info("Building LDAP connection")
        ldap_user = os.getenv("LDAP_USERNAME")
        ldap_password = os.getenv("LDAP_PASSWORD")
        logger.info(f"LDAP user: {ldap_user}")
        # logger.info(f"LDAP password: {ldap_password}")

        server = Server("ldaps://" + os.getenv("LDAP_SERVER"), get_info=ALL)
        conn = Connection(
            server, user=ldap_user, password=ldap_password, authentication=NTLM
        )
        return conn

    @staticmethod
    def parse_user_entry( user_entry):
        logger.info(f"Parsing user entry with username: {user_entry.name.values[0]} ")
        first_last_name=user_entry.name.values[0].split(" ",1)
        if len(first_last_name) == 1:
            first_name=first_last_name[0]
            last_name=first_last_name[0]
        else:
            first_name, last_name= first_last_name

        # first_name, last_name = user_entry.name.values[0].split(" ",1)
        first_name, last_name = first_name.strip(" ,"), last_name.strip(" ,")
        user_profile = UserProfile(
            id=user_entry.sAMAccountName.values[0],
            name=f"{first_name} {last_name}",
            first_name=first_name,
            last_name=last_name,
            email=user_entry.mail.values[0] if 'mail' in user_entry else '',
            employeeId=user_entry.employeeID.values[0] if 'employeeID' in user_entry else '',
            intraId=user_entry.sAMAccountName.values[0],
            internal_flag=True,
            department=user_entry.department.values[0] if 'department' in user_entry else '',
            division=user_entry.division.value if 'division' in user_entry else '',
            role=user_entry.title.values[0] if 'title' in user_entry else '',
            last_update_time=str(datetime.datetime.now(datetime.timezone.utc)),
        )
        return user_profile.__dict__


    def lookup(self,values: list[str])->list:
        logger.info(f"Looking up {len(values)} LDAP entries")
        profiles = []
        conn = self.build_ldap_connection()
        for val in values:
            try:
                user_profile_entries=self.ldap_search_strategy.run(conn,val)
                if user_profile_entries and len(user_profile_entries)>0:
                    for profile in user_profile_entries:
                        user_profile=self.parse_user_entry(profile)
                        profiles.append(user_profile)
            except Exception as e:
                logger.error(f"LDAP profile lookup failed: {e}")

        return profiles


src/services/ldap_service/lookup_service_interface.py
import abc


class LookupServiceInterface(metaclass=abc.ABCMeta):

    @classmethod
    def __subclasshook__(cls, subclass):
        return (
            hasattr(subclass, "lookup") and
            callable(subclass.lookup) or
            NotImplemented
        )

    @abc.abstractmethod
    def lookup(self, emails:list[str])-> list:
        raise NotImplementedError()



src/services/ldap_service/user_profile.py
from dataclasses import dataclass


@dataclass
class UserProfile:
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    employeeId: str
    intraId: str
    internal_flag: bool
    department: str
    division: str
    role: str
    last_update_time: str
    company: str = ""  # Add company field for ZoomInfo company data


src/services/ldap_service/zoom_info_service.py
import datetime
import json
import logging
import os
import jwt
from datetime import datetime, timedelta, timezone
import requests
import json

import requests

from rbc_security import enable_certs


from src.services.ldap_service.user_profile import UserProfile

from src.utils.utils import timed_lru_cache, time_it

enable_certs()

from src.services.ldap_service.lookup_service_interface import LookupServiceInterface
from src.config.configuration import app_config

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)
logger = logging.getLogger(__name__)

class ZoomInfoService(LookupServiceInterface):

    def __init__(self):
        self.user_name = os.environ.get("ZOOM_INFO_USERNAME")
        self.audience = 'enterprise_api'
        self.issuer = 'api-client@zoominfo.com'
        self.authenticate_url = "https://api.zoominfo.com/authenticate"
        self.expiry_time_in_seconds = 300
        self.hashing_algorithm = 'RS256'

    def user_name_pwd_authentication(self, password):
        headers = {'Accept': "application/json", 'user-agent': ""}
        request_body = {'username': self.user_name, 'password': password}
        response = requests.post(self.authenticate_url, headers=headers, data=request_body)
        if not response.ok:
            response.reason = response.text
            return response.raise_for_status()
        return self._extract_jwt_from_text(response.text)

    def pki_authentication(self, client_id, private_key):
        return self._post_and_get_jwt(client_id, private_key)

    def _post_and_get_jwt(self, client_id, private_key):
        client_jwt = self._get_client_jwt(client_id, private_key)
        headers = {'Authorization': f"Bearer {client_jwt}", 'Accept': "application/json", 'user-agent': ""}
        response = requests.post(self.authenticate_url, headers=headers)
        if not response.ok:
            response.reason = response.text
            return response.raise_for_status()
        return self._extract_jwt_from_text(response.text)

    def _get_client_jwt(self, client_id, private_key):
        current_time = datetime.utcnow()
        claims = {
            'aud': self.audience,
            'iss': self.issuer,
            'iat': current_time,
            'exp': current_time + timedelta(seconds=self.expiry_time_in_seconds),
            'client_id': client_id,
            'username': self.user_name
        }
        encoded_jwt = jwt.encode(claims, private_key, algorithm=self.hashing_algorithm)
        # `PyJWT` switched to returning a string in v2.0.0
        return encoded_jwt.decode("utf-8") if isinstance(encoded_jwt, bytes) else encoded_jwt

    def _extract_jwt_from_text(self, text_input):
        json_response = json.loads(text_input)
        return json_response["jwt"]

    @time_it
    @timed_lru_cache(seconds=5 * 60, maxsize=1)
    def _get_jwt_token(self):
        password=os.environ.get("ZOOM_INFO_PASSWORD")
        return self.user_name_pwd_authentication(password)


    def parse_response(self,email,zoom_info_response):
        logger.debug("Parsing Zoom Info response")
        if(zoom_info_response.ok):
            data_json = zoom_info_response.json()
            data=data_json['data'][0]
            try:
                user_profile = UserProfile(
                    id=data['id'],
                    name=f"{data['firstName']} {data['lastName']}".strip(),
                    first_name=data['firstName'],
                    last_name=data['lastName'],
                    email=email,
                    employeeId='',
                    intraId=data['id'],
                    internal_flag=False,
                    department='',  # Keep empty - no department info from ZoomInfo
                    division='',
                    role=data['jobTitle'],
                    last_update_time=str(datetime.now(timezone.utc)),
                    company=data['company']['name'],  # Use the new company field
                )
                return user_profile.__dict__
            except Exception as e:
                logger.error(f"Failed to parse zoom user response: {e}")
                raise
        else:
            return None

    def parse_response_for_name(self, name_info: dict, zoom_info_response):
        """Enhanced response parsing that returns ALL matches, not just the first one"""
        logger.debug("Parsing Zoom Info response for name search")
        
        if not zoom_info_response.ok:
            logger.error(f"ZoomInfo API error {zoom_info_response.status_code}: {zoom_info_response.text}")
            return []
        
        try:
            data_json = zoom_info_response.json()
            results = []
            
            if 'data' in data_json and len(data_json['data']) > 0:
                # Process ALL results, not just the first one
                for data in data_json['data']:
                    # Handle company info - might be in 'company' object or 'companyName' field
                    company_name = ''
                    company_id = ''
                    
                    if 'company' in data and isinstance(data['company'], dict):
                        company_name = data['company'].get('name', '')
                        company_id = data['company'].get('id', '')
                    elif 'companyName' in data:
                        company_name = data.get('companyName', '')
                    
                    user_profile = UserProfile(
                        id=data.get('id', ''),
                        name=f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
                        first_name=data.get('firstName', name_info['first_name']),
                        last_name=data.get('lastName', name_info['last_name']),
                        email='',  # Not available in name-based search
                        employeeId='',
                        intraId=str(data.get('id', '')),
                        internal_flag=False,
                        department='',  # Keep empty - no department info from ZoomInfo
                        division='',
                        role=data.get('jobTitle', ''),
                        last_update_time=str(datetime.now(timezone.utc)),
                        company=company_name,  # Use the new company field
                    )
                    
                    profile_dict = user_profile.__dict__
                    
                    # Add additional fields
                    profile_dict['middle_name'] = data.get('middleName', '')
                    profile_dict['company_id'] = company_id
                    profile_dict['zoominfo_id'] = data.get('id', '')
                    
                    results.append(profile_dict)
                
                logger.info(f"Found {len(results)} matches for {name_info['full_name']}")
                return results
                    
            else:
                logger.info(f"No data found in ZoomInfo response for {name_info['full_name']}")
                return []
                    
        except Exception as e:
            logger.error(f"Failed to parse ZoomInfo response for {name_info['full_name']}: {e}")
            return []

    def parse_names_string(self, names_string: str) -> list[dict]:
        """
        Simple robust name parsing - just clean and split names
        """
        names = []
        individual_names = [name.strip() for name in names_string.split(',')]
        
        for name in individual_names:
            # Remove anything in parentheses (company info, titles, etc.)
            clean_name = name.split('(')[0].strip()
            
            # Remove common prefixes/suffixes that might interfere
            clean_name = clean_name.replace('Mr.', '').replace('Ms.', '').replace('Dr.', '').strip()
            
            # Split into parts
            name_parts = clean_name.split()
            
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])  # Everything after first name
                
                names.append({
                    'first_name': first_name,
                    'last_name': last_name,
                    'full_name': clean_name,
                    'original': name.strip()
                })
            elif len(name_parts) == 1:
                # Single name - could be first or last
                names.append({
                    'first_name': name_parts[0],
                    'last_name': '',
                    'full_name': clean_name,
                    'original': name.strip()
                })
        
        return names

    @time_it
    def get_user_details_from_zoominfo(self, email: str):
        zoom_info_url=os.environ.get("ZOOM_INFO_URL")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_jwt_token()}"
        }

        # data = {
        #     "emailAddress": "akinahan@k1ops.com"
        # }

        data = {
                "emailAddress": email ,
            "outputFields": [
                "id", "firstName", "middleName", "lastName", "jobTitle", "companyName"]
        }



        response = requests.post(zoom_info_url, headers=headers, json=data)
        # print(response.status_code)
        # print(response.json())
        return response

    @time_it
    def get_user_details_from_zoominfo_by_name(self, first_name: str, last_name: str = None, full_name: str = None):
        """
        Name search without company filtering - get ALL matches for the name
        """
        zoom_info_url = os.environ.get("ZOOM_INFO_URL")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_jwt_token()}"
        }

        # Remove company filtering - get all matches for the name
        data = {
            "outputFields": [
                "id", "firstName", "middleName", "lastName", "jobTitle", "companyName"
            ]
        }
        
        # Add search criteria (no company filter)
        if first_name and last_name:
            data["firstName"] = first_name
            data["lastName"] = last_name
        elif full_name:
            name_parts = full_name.split()
            if len(name_parts) >= 2:
                data["firstName"] = name_parts[0]
                data["lastName"] = " ".join(name_parts[1:])
            else:
                data["firstName"] = full_name
        elif first_name:
            data["firstName"] = first_name
        
        logger.debug(f"ZoomInfo API payload: {data}")
        
        response = requests.post(zoom_info_url, headers=headers, json=data)
        
        if response.status_code != 200:
            logger.error(f"ZoomInfo API error {response.status_code}: {response.text}")
        
        return response



    def lookup(self, emails:list[str]) -> list:
        # Implement Zoom lookup logic here
        logger.info(f"Looking up {len(emails)} Zoom entries")
        result = []
        for email in emails:
            try:
                zoom_user_response = self.get_user_details_from_zoominfo(email)
                user_details = self.parse_response(email,zoom_user_response)
                if user_details and len(user_details) > 0:
                    result.append(user_details)
            except Exception as e:
                logger.error(f"Failed to get user details: {e}")

        return result

    def lookup_by_names(self, names_string: str) -> list:
        """
        Simplified name lookup - just get ALL matches for each name
        """
        logger.info(f"Looking up ZoomInfo entries for names: {names_string}")
        
        result = []
        
        try:
            parsed_names = self.parse_names_string(names_string)
            
            for name_info in parsed_names:
                try:
                    logger.debug(f"Searching for all matches: {name_info['full_name']}")
                    zoom_user_response = self.get_user_details_from_zoominfo_by_name(
                        first_name=name_info['first_name'],
                        last_name=name_info['last_name']
                    )
                    
                    all_matches = self.parse_response_for_name(name_info, zoom_user_response)
                    
                    if all_matches:
                        logger.info(f"Found {len(all_matches)} total matches for {name_info['full_name']}")
                        result.extend(all_matches)
                    else:
                        logger.warning(f"No results found for: {name_info['original']}")
                            
                except Exception as e:
                    logger.error(f"Failed to process {name_info['full_name']}: {e}")
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse names string '{names_string}': {e}")
            return []


if __name__ == "__main__":

    from dotenv import load_dotenv
    load_dotenv()

    async def debug_field_comparison():
        """
        Experiment to compare email vs name search API responses
        """
        zoom_service = ZoomInfoService()
        
        print("=== EXPERIMENT: EMAIL vs NAME SEARCH COMPARISON ===\n")
        
        # Test 1: Email search for Allison Kinahan
        print("1. EMAIL SEARCH for akinahan@k1ops.com")
        print("-" * 50)
        try:
            email_response = zoom_service.get_user_details_from_zoominfo("akinahan@k1ops.com")
            print(f"Status: {email_response.status_code}")
            if email_response.ok:
                email_data = email_response.json()
                if 'data' in email_data and email_data['data']:
                    person = email_data['data'][0]
                    print(f"ID: {person.get('id', 'N/A')}")
                    print(f"Name: {person.get('firstName', '')} {person.get('lastName', '')}")
                    print(f"Job Title: {person.get('jobTitle', 'N/A')}")
                    print(f"Company: {person.get('company', {}).get('name', 'N/A') if 'company' in person else person.get('companyName', 'N/A')}")
                    print(f"All available fields: {list(person.keys())}")
                else:
                    print("No data in response")
            else:
                print(f"Error: {email_response.text}")
        except Exception as e:
            print(f"Exception: {e}")
        
        print("\n" + "="*60 + "\n")
        
        # Test 2: Name search for the same person
        print("2. NAME SEARCH for Allison Kinahan")
        print("-" * 50)
        try:
            name_response = zoom_service.get_user_details_from_zoominfo_by_name("Allison", "Kinahan")
            print(f"Status: {name_response.status_code}")
            if name_response.ok:
                name_data = name_response.json()
                if 'data' in name_data and name_data['data']:
                    person = name_data['data'][0]
                    print(f"ID: {person.get('id', 'N/A')}")
                    print(f"Name: {person.get('firstName', '')} {person.get('lastName', '')}")
                    print(f"Job Title: {person.get('jobTitle', 'N/A')}")
                    print(f"Company: {person.get('company', {}).get('name', 'N/A') if 'company' in person else person.get('companyName', 'N/A')}")
                    print(f"All available fields: {list(person.keys())}")
                else:
                    print("No data in response")
            else:
                print(f"Error: {name_response.text}")
        except Exception as e:
            print(f"Exception: {e}")
        
        print("\n" + "="*60 + "\n")
        
        # Test 3: Compare the output fields being requested
        print("3. COMPARING API PAYLOADS")
        print("-" * 50)
        
        # Email search payload
        email_payload = {
            "emailAddress": "akinahan@k1ops.com",
            "outputFields": ["id", "firstName", "middleName", "lastName", "jobTitle", "companyName"]
        }
        print(f"Email search requests fields: {email_payload['outputFields']}")
        
        # Name search payload  
        name_payload = {
            "firstName": "Allison",
            "lastName": "Kinahan",
            "outputFields": ["id", "firstName", "middleName", "lastName", "jobTitle", "companyName"]
        }
        print(f"Name search requests fields: {name_payload['outputFields']}")
        
        print(f"Fields are identical: {email_payload['outputFields'] == name_payload['outputFields']}")
        
        print("\n" + "="*60 + "\n")
        print("CONCLUSION:")
        print("- If IDs are the same but jobTitle differs: Same person, different data sources")
        print("- If fields are identical but responses differ: API endpoint behavior difference")
        print("- If fields differ: Request payload issue")

    import asyncio
    asyncio.run(debug_field_comparison())



src/services/ldap_service/ldap_search_strategy/ldap_email_strategy.py
import logging
import os

from ldap3 import SUBTREE, ALL_ATTRIBUTES

from src.services.ldap_service.ldap_search_strategy.ldap_search_strategy_Interface import LDAPSearchStrategyInterface


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)

logger = logging.getLogger(__name__)


class LDAPEmailStrategy(LDAPSearchStrategyInterface):

    def run(self, conn, value: str):
        logger.info(f"Authenticating email via LDAP: {value}")
        # conn = self.build_ldap_connection()
        if not conn.bind():
            logger.error(f"LDAP server bind failed")
            return {}

        user_dn = os.getenv("LDAP_USER_DN")
        rsp = conn.search(
            user_dn,
            f"(mail={value})",
            search_scope=SUBTREE,
            # attributes=["name", "mail", "sAMAccountName", "department","title"],
            attributes=ALL_ATTRIBUTES,
        )
        logger.info(f"LDAP search response: {rsp}")
        if rsp and conn.entries:
            user_entry = conn.entries
            return user_entry

        else:
            if not rsp:
                logger.info(f"LDAP profile lookup returned false for user : {value}")
            if not conn.entries:
                logger.info(f"No LDAP profile entries for user  : {value}")
            return {}


src/services/ldap_service/ldap_search_strategy/ldap_search_strategy_Interface.py
from abc import ABC, abstractclassmethod, abstractmethod
from typing import List


class LDAPSearchStrategyInterface(ABC):

    @abstractmethod
    def run(self, conn, value: str):
        pass


src/services/ldap_service/ldap_search_strategy/ldap_username_strategy.py
import logging
import os

from ldap3 import SUBTREE, ALL_ATTRIBUTES

from src.services.ldap_service.ldap_search_strategy.ldap_search_strategy_Interface import LDAPSearchStrategyInterface


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)

logger = logging.getLogger(__name__)


class LDAPUsernameStrategy(LDAPSearchStrategyInterface):

    def run(self, conn, value: str):
        logger.info(f"Authenticating name via LDAP: {value}")
        # conn = self.build_ldap_connection()
        if not conn.bind():
            logger.error(f"LDAP server bind failed")
            return {}

        user_dn = os.getenv("LDAP_USER_DN")
        rsp = conn.search(
            user_dn,
            f"(cn={value})",
            search_scope=SUBTREE,
            # attributes=["name", "mail", "sAMAccountName", "department","title"],
            attributes=ALL_ATTRIBUTES,
        )
        if rsp and conn.entries:
            user_entry = conn.entries
            return user_entry

        else:
            if not rsp:
                logger.info(f"LDAP profile lookup returned false for user : {value}")
            if not conn.entries:
                logger.info(f"No LDAP profile entries for user  : {value}")
            return {}


src/services/llm/client.py
"""
LLM Client for reference_mcp_client - loads config from .env using os.getenv.
"""

# --- REFACTORED TO USE oauth_client.py LOGIC ---
import os
import json
from typing import Dict, Any, List
from dotenv import load_dotenv
import asyncio
from .oauth_client import get_env, get_oauth_token
import httpx
from src.config.configuration import get_config
from llama_index.llms.openai import OpenAI

from rbc_security import enable_certs
enable_certs()
load_dotenv()

async def call_llm(messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> str:
    """
    Call the LLM using the new company-standard approach (see llm_call.py).
    Accepts OpenAI-style messages and optional tools.
    Returns the main content string or tool call summary.
    """
    token = await get_oauth_token()
    llm_model = os.getenv('LLM_MODEL_NAME')
    llm_base_url = os.getenv('LLM_SERVER_URL')
    max_tokens = int(os.getenv('LLM_MAX_TOKENS'))
    temperature = os.getenv('LLM_TEMPERATURE')
    supports_temperature = temperature is not None

    payload = {
        "model": llm_model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    if supports_temperature:
        payload["temperature"] = float(temperature)
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient( timeout=60.0) as client:
        response = await client.post(
            llm_base_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        response.raise_for_status()
        data = response.json()
        try:
            choice = data["choices"][0]
            # OpenAI format: either {"message": {"content": ...}} or {"content": ...}
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
            elif "content" in choice:
                return choice["content"]
            elif "message" in choice and "tool_calls" in choice["message"]:
                tool_calls = choice["message"]["tool_calls"]
                tool_call_strs = []
                for tc in tool_calls:
                    name = tc.get("function", {}).get("name", tc.get("name", "<unknown>"))
                    args = tc.get("function", {}).get("arguments", tc.get("arguments", ""))
                    tool_call_strs.append(f"Tool call: {name} with arguments {args}")
                return "\n".join(tool_call_strs)
            else:
                return f"LLM response did not contain content or tool_calls. Raw: {json.dumps(choice)}"
        except Exception as e:
            return f"Error parsing LLM response: {e}. Raw: {json.dumps(data)}"

async def call_llm_raw(messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None, tool_choice: Dict[str, Any] = None) -> dict:
    """
    Same as call_llm, but returns the full LLM response dict for advanced routing.
    """
    token = await get_oauth_token()
    llm_model = os.getenv('LLM_MODEL_NAME')
    llm_base_url = os.getenv('LLM_SERVER_URL')
    max_tokens = int(os.getenv('LLM_MAX_TOKENS'))
    temperature = os.getenv('LLM_TEMPERATURE')
    supports_temperature = temperature is not None

    payload = {
        "model": llm_model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    if supports_temperature:
        payload["temperature"] = float(temperature)
    if tools:
        payload["tools"] = tools
    if tool_choice:  # Add this
        payload["tool_choice"] = tool_choice

    async with httpx.AsyncClient( timeout=60.0) as client:
        response = await client.post(
            llm_base_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        response.raise_for_status()
        return response.json()

async def get_openai_client():
    token = await get_oauth_token()

    llm_model = os.getenv('LLM_MODEL_NAME')
    llm_base_url = os.getenv('LLM_SERVER_URL')
    temperature = os.getenv('LLM_TEMPERATURE')


    return OpenAI(model=llm_model, 
                 api_base=llm_base_url,
                 api_key=token,
                 temperature=temperature)
    




src/services/llm/oauth_client.py
import os
import httpx
import asyncio
from dotenv import load_dotenv
from src.config.configuration import get_config

load_dotenv()

def get_env(key, default=None, required=False):
    """Get environment variable with optional default and required validation"""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

async def get_oauth_token():
    """Get OAuth token for LLM API authentication"""
    config = get_config().llm_chat_model
    oauth_endpoint = config.oauth_endpoint
    client_id = config.client_id
    client_secret = os.getenv('LLM_CLIENT_SECRET')
    grant_type = "client_credentials"
    scope = "read"

    data = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            oauth_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        result = response.json()
        return result["access_token"]
    
if __name__=="__main__":
    token = asyncio.run(get_oauth_token()   )
    print("\n\n\n\n\n\n")

    print(token)
```


