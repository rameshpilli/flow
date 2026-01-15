# app/resources/client_360_apis.py
import os
import sys
import json
import logging
import httpx
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from app.config import config
from app.utils.precision_guard import add_data_integrity_check

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


######################################################
############### CUSTOM-API-TIMEOUTS  #################
######################################################
API_TIMEOUTS = {
    "revenue_overview": httpx.Timeout(15.0, connect=5.0),
    "cv_trend": httpx.Timeout(15.0, connect=5.0),
    "product_trend": httpx.Timeout(20.0, connect=5.0),
    "region_trend": httpx.Timeout(15.0, connect=5.0),
    "rwa_leverage": httpx.Timeout(15.0, connect=5.0),
    "financial_resources": httpx.Timeout(15.0, connect=5.0),
    "top_trades": httpx.Timeout(60.0, connect=10.0),  # Increased: Large clients with 90-day data can be slow
    "all_trades": httpx.Timeout(30.0, connect=5.0),  # Increased: Large trade lists
    "interactions": httpx.Timeout(10.0, connect=5.0),
    "contacts": httpx.Timeout(10.0, connect=5.0),

    # SLOW APIs
    "coverage": httpx.Timeout(20.0, connect=10.0),
    "meeting_reports": httpx.Timeout(30.0, connect=10.0),
    "lrpm": httpx.Timeout(15.0, connect=5.0),
}

_http_client: Optional[httpx.AsyncClient] = None

async def get_http_client() -> httpx.AsyncClient:
    """Get or create shared HTTP client with connection pooling"""
    global _http_client

    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(30.0, connect=10.0),  # Default fallback (overridden per-API)
            limits=httpx.Limits(
                max_keepalive_connections=50,   # Increased from 20 (2.5x more reusable connections)
                max_connections=100,             # Increased from 50 (handle more concurrent requests)
                keepalive_expiry=30.0           # Keep connections alive for 30 seconds
            ),
            follow_redirects=True
        )
        logger.info(" HTTP client initialized with optimized connection pool (50 keepalive, 100 max)")

    return _http_client

async def close_http_client():
    """Close the shared HTTP client"""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


######################################################
############# CLIENT-REVENUE-OVERVIEW ################
######################################################
async def get_revenue_client_overview(
    cdrid: str,
    # employee_id: int = None,
    employee_id: Optional[int] = None,
    currency: str = "USD",
    hierarchy_depth: str = "1",
    metric: str = "CV",
    period_type: str = "fiscal",
    reportable_mask: int = 1
) -> Dict[str, Any]:
    """Get client revenue overview"""
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getRevenueClient_Overview"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json",
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}

    payload = {
        "appCode": "tb20",
        "values": [
            employee_id,
            json.dumps({
                "cdrId": cdrid,
                "currency": currency,
                "hierarchyDepth": hierarchy_depth,
                "metric": metric,
                "periodType": period_type,
                "reportable-mask": reportable_mask
            })
        ]
    }

    try:
        logger.info(f"[Overview-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["revenue_overview"])
        response.raise_for_status()

        # Parse JSON preserving numeric precision (prevents float conversion)
        from app.utils.precision_guard import parse_response_preserving_numbers
        result = parse_response_preserving_numbers(response)

        if isinstance(result, dict) and 'data' in result and isinstance(result['data'], list) and not result['data']:
            return {"status": "error", "message": "User does not have access to this client data."}

        # Wrap with integrity check (numbers already preserved from parsing)
        return add_data_integrity_check(result, api_name="get_revenue_client_overview")

    except httpx.TimeoutException as e:
        logger.error(f"[Overview-API] Timeout after 30s for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out after 30 seconds"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[Overview-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except httpx.RequestError as e:
        error_detail = f"{type(e).__name__}"
        if str(e):
            error_detail += f": {str(e)}"
        logger.error(f"[Overview-API] Network error for CDRID={cdrid}: {error_detail}")
        return {"status": "error", "message": f"Network error: {error_detail}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[Overview-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
################ CLIENT-CV-TRED  #####################
######################################################
async def get_client_cv_trend(
    cdrid: str,
    employee_id: Optional[int] = None,
    timeperiod: str = "YR",
    currency: str = "USD",
    period_type: str = "fiscal",
    hierarchy_depth: str = "1",
    hierarchy_filter: str = "client",
    metric: str = "CV",
    reportable_mask: str = "1"
) -> Dict[str, Any]:
    """Get client CV trend over time

    NOTE: Backend API only accepts timeperiod='YR'. We always pass 'YR' to the API
    and filter client-side in TrendsProcessor based on the user's requested timeperiod.
    - timeperiod='YR' → Processor filters for TimePeriod=='FY' (5 records)
    - timeperiod='MT' → Processor filters for TimePeriod=='CM' (60 records)
    """
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getRevenueClient_TimePeriod"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    # IMPORTANT: Backend API only accepts "YR" - always send "YR" regardless of user's request
    # Client-side filtering happens in TrendsProcessor based on actual timeperiod parameter
    payload = {
        "appCode": "tb20",
        "values": [
            employee_id,
            json.dumps({
                "cdrId": cdrid,
                "client-hierarchy-depth": hierarchy_depth,
                "client-hierarchy-filter": hierarchy_filter,
                "currency": currency,
                "metric": metric,
                "periodType": period_type,
                "reportable-mask": reportable_mask,
                "timeperiod": "YR"  # Always send 'YR' - processor filters based on user's timeperiod
            })
        ]
    }

    try:
        logger.info(f"[CVTrend-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["cv_trend"])
        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict) and 'data' in result and isinstance(result['data'], list) and not result['data']:
            return {"status": "error", "message": "User does not have access to this client data."}

        # Preserve numbers for exact precision
        return add_data_integrity_check(result, api_name="get_client_cv_trend")

    except httpx.TimeoutException as e:
        logger.error(f"[CVTrend-API] Timeout after 30s for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out after 30 seconds"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[CVTrend-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except httpx.RequestError as e:
        error_detail = f"{type(e).__name__}"
        if str(e):
            error_detail += f": {str(e)}"
        logger.error(f"[CVTrend-API] Network error for CDRID={cdrid}: {error_detail}")
        return {"status": "error", "message": f"Network error: {error_detail}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[CVTrend-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
############# CLIENT-CV-PRODUCT-TREND ################
######################################################
async def get_client_cv_by_product_trend(
    cdrid: str,
    employee_id: Optional[int] = None,
    currency: str = "USD",
    period_type: str = "fiscal",
    metric: str = "CV",
    hierarchy_depth: str = "1",
    hierarchy_filter: str = "children",
    reportable_mask: int = 1
) -> Dict[str, Any]:
    """Get client CV trend by product"""
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getRevenueClient_Product"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    payload = {
        "appCode": "tb20",
        "values": [
            employee_id,
            json.dumps({
                "cdrId": cdrid,
                "currency": currency,
                "periodType": period_type,
                "metric": metric,
                "client-hierarchy-depth": hierarchy_depth,
                "client-hierarchy-filter": hierarchy_filter,
                "reportable-mask": reportable_mask
            })
        ]
    }

    try:
        logger.info(f"[ProductTrend-API] CDRID={cdrid}, URL={url}")
        logger.info(f"[ProductTrend-API] Payload: {json.dumps(payload)}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["product_trend"])
        response.raise_for_status()

        # Parse JSON preserving numeric precision (prevents float conversion)
        from app.utils.precision_guard import parse_response_preserving_numbers
        result = parse_response_preserving_numbers(response)

        # DIAGNOSTIC: Log response structure for debugging
        logger.info(f"[ProductTrend-API] Response status: {response.status_code}")
        logger.info(f"[ProductTrend-API] Response keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
        if isinstance(result, dict) and 'data' in result:
            data_keys = list(result['data'].keys()) if isinstance(result['data'], dict) else f"data is {type(result['data'])}"
            logger.info(f"[ProductTrend-API] Data keys: {data_keys}")
            if isinstance(result['data'], dict) and 'ResultSet[1]' in result['data']:
                resultset_len = len(result['data']['ResultSet[1]']) if isinstance(result['data']['ResultSet[1]'], list) else 'not a list'
                logger.info(f"[ProductTrend-API] ResultSet[1] length: {resultset_len}")
            else:
                logger.warning(f"[ProductTrend-API] No ResultSet[1] found in response for CDRID={cdrid}")
        else:
            logger.warning(f"[ProductTrend-API] Response missing 'data' key for CDRID={cdrid}, response: {str(result)[:500]}")

        if isinstance(result, dict) and 'data' in result and isinstance(result['data'], list) and not result['data']:
            return {"status": "error", "message": "User does not have access to this client data."}

        # Preserve numbers for exact precision
        return add_data_integrity_check(result, api_name="get_client_cv_by_product_trend")

    except httpx.TimeoutException as e:
        logger.error(f"[ProductTrend-API] Timeout after 30s for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out after 30 seconds"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[ProductTrend-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except httpx.RequestError as e:
        error_detail = f"{type(e).__name__}"
        if str(e):
            error_detail += f": {str(e)}"
        logger.error(f"[ProductTrend-API] Network error for CDRID={cdrid}: {error_detail}")
        return {"status": "error", "message": f"Network error: {error_detail}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[ProductTrend-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
############# UNIFIED-CLIENT-REVENUE  ################
######################################################
async def get_unified_client_revenue(
    cdrid: str,
    employee_id: Optional[int] = None,
    currency: str = "USD",
    period_type: str = "fiscal",
    metric: str = "CV",
    hierarchy_depth: str = "1"
) -> Dict[str, Any]:
    """
    Get unified client revenue - runs Overview + Product in PARALLEL
    """
    import asyncio

    logger.info(f"[UnifiedRevenue-API] CDRID={cdrid} (parallel)")

    try:
        # Run both in PARALLEL 
        logger.info(f"[UnifiedRevenue-API] STEP 1: Calling overview and product APIs in parallel")
        results = await asyncio.gather(
            get_revenue_client_overview(
                cdrid=cdrid,
                employee_id=employee_id,
                currency=currency,
                period_type=period_type,
                metric=metric,
                hierarchy_depth=hierarchy_depth,
                reportable_mask=1,
            ),
            get_client_cv_by_product_trend(
                cdrid=cdrid,
                employee_id=employee_id,
                currency=currency,
                period_type=period_type,
                metric=metric,
                hierarchy_depth=hierarchy_depth,
                hierarchy_filter="client",
                reportable_mask=1,
            ),
            return_exceptions=True  
        )

        overview_result = results[0]
        product_result = results[1]

        # Check for exceptions and handle 
        if isinstance(overview_result, Exception):
            logger.error(f"[UnifiedRevenue-API] Overview API failed: {type(overview_result).__name__} - {overview_result}")
            overview_result = {"status": "error", "message": f"Overview API failed: {str(overview_result)}"}
        else:
            logger.info(f"[UnifiedRevenue-API] Overview API success: {overview_result.get('status', 'ok')}")

        if isinstance(product_result, Exception):
            logger.error(f"[UnifiedRevenue-API] Product API failed: {type(product_result).__name__} - {product_result}")
            product_result = {"status": "error", "message": f"Product API failed: {str(product_result)}"}
        else:
            logger.info(f"[UnifiedRevenue-API] Product API success: {product_result.get('status', 'ok')}")

        # Return combined data (even with partial failures)
        logger.info(f"[UnifiedRevenue-API] Returning combined results for CDRID={cdrid}")
        combined_result = {
            "status": "success",  # Top-level status for test script compatibility
            "overview_data": overview_result,
            "product_data": product_result,
            "metadata": {
                "status": "success",
                "cdrid": cdrid,
                "currency": currency,
                "period_type": period_type,
                "metric": metric,
                "hierarchy_depth": hierarchy_depth
            }
        }

        # Preserve numbers for exact precision
        return add_data_integrity_check(combined_result, api_name="get_unified_client_revenue")

    except Exception as e:
        logger.error(f"[UnifiedRevenue-API] Unexpected error for CDRID={cdrid}: {type(e).__name__} - {e}")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}

######################################################
############# CLIENT-CV-BY-REGION  ###################
######################################################
async def get_client_cv_by_region(
    cdrid: str,
    employee_id: Optional[int] = None,
    currency: str = "USD",
    metric: str = "CV",
    period_type: str = "fiscal",
    reportable_mask: int = 1,
    hierarchy_depth: str = "1",
    hierarchy_filter: str = "children",
    timeperiod: str = "YR"
) -> Dict[str, Any]:
    """Get client CV trend by region"""
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getRevenueClient_Region"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    inner_payload = json.dumps({
        "cdrId": cdrid,
        "client-hierarchy-depth": hierarchy_depth,
        "client-hierarchy-filter": hierarchy_filter,
        "currency": currency,
        "metric": metric,
        "periodType": period_type,
        "reportable-mask": reportable_mask,
        "timeperiod": timeperiod,
        "product": None,
        "selectedCdrId": None
    })

    payload = {
        "appCode": "tb20",
        "values": [employee_id, inner_payload]
    }

    try:
        logger.info(f"[RegionTrend-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["region_trend"])
        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict) and 'data' in result and isinstance(result['data'], list) and not result['data']:
            return {"status": "error", "message": "User does not have access to this client data."}

        # Preserve numbers for exact precision
        return add_data_integrity_check(result, api_name="get_client_cv_by_region")

    except Exception as e:
        logger.error(f"[RegionTrend-API] Error: {e}")
        return {"status": "error", "message": str(e)}

######################################################
############# CLIENT-RWA-LEVERAGE  ###################
######################################################
async def get_client_rwa_leverage(
    cdrid: str,
    employee_id: Optional[int] = None,
    currency: str = "USD",
    metric: str = "CV",
    period_type: str = "fiscal",
    reportable_mask: int = 1
) -> Dict[str, Any]:
    """Get client RWA and leverage footprint"""
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getRevenueClient_RWALeverageFootprint"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    inner_payload = json.dumps({
        "cdrId": cdrid,
        "currency": currency,
        "metric": metric,
        "periodType": period_type,
        "reportable-mask": reportable_mask
    })

    payload = {
        "appCode": "tb20",
        "values": [employee_id, inner_payload]
    }

    try:
        logger.info(f"[RWALeverage-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["rwa_leverage"])
        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict) and 'data' in result and isinstance(result['data'], list) and not result['data']:
            return {"status": "error", "message": "User does not have access to this client data."}

        # Preserve numbers for exact precision
        return add_data_integrity_check(result, api_name="get_client_rwa_leverage")

    except httpx.TimeoutException as e:
        logger.error(f"[RWALeverage-API] Timeout after 30s for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out after 30 seconds"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[RWALeverage-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except httpx.RequestError as e:
        error_detail = f"{type(e).__name__}"
        if str(e):
            error_detail += f": {str(e)}"
        logger.error(f"[RWALeverage-API] Network error for CDRID={cdrid}: {error_detail}")
        return {"status": "error", "message": f"Network error: {error_detail}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[RWALeverage-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
############ CLIENT-RESOURCES BY PRODUCT  ############
######################################################
async def get_client_cv_financial_resources_by_product(
    cdrid: str,
    employee_id: Optional[int] = None,
    currency: str = "CAD",
    metric: str = "CV",
    period_type: str = "fiscal",
    hierarchy_depth: str = "1",
    hierarchy_filter: str = "children",
    reportable_mask: int = 1
) -> Dict[str, Any]:
    """Get client CV and financial resources by product (CAD only)"""
    if currency.upper() != "CAD":
        logger.warning(f"Forcing currency to CAD")
        currency = "CAD"

    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getRevenueClient_RWALeverageByProduct"

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    inner_payload = json.dumps({
        "cdrId": cdrid,
        "client-hierarchy-depth": hierarchy_depth,
        "client-hierarchy-filter": hierarchy_filter,
        "currency": currency,
        "metric": metric,
        "periodType": period_type,
        "reportable-mask": reportable_mask
    })

    payload = {
        "appCode": "tb20",
        "values": [employee_id, inner_payload]
    }

    try:
        logger.info(f"[FinancialResources-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["financial_resources"])
        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict) and 'data' in result and isinstance(result['data'], list) and not result['data']:
            return {"status": "error", "message": "User does not have access to this client data."}

        # Preserve numbers for exact precision
        return add_data_integrity_check(result, api_name="get_client_cv_financial_resources_by_product")

    except Exception as e:
        logger.error(f"[FinancialResources-API] Error: {e}")
        return {"status": "error", "message": str(e)}

######################################################
################## CLIENT-CONTACTS  ##################
######################################################
async def get_client_contacts(
    cdrid: str,
    employee_id: Optional[int] = None,
    hierarchy_depth: str = "0",
    hierarchy_type: str = "CLIENT",
    desk_id: Optional[List[str]] = None, 
    role_id: Optional[List[int]] = None,
    page_size: int = 100,
    start_row: int = 0,
    fields_order: Optional[List[str]] = None,
    filter_model: Optional[Dict[str, Any]] = None,
    order: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get client contacts

    Parameters:
    - cdrid: Client CDRID
    - employee_id: Employee ID for authentication
    - hierarchy_depth: "0" for Relationship level, "1" for Client level
    - hierarchy_type: "CLIENT" (default)
    - desk_id: Optional list of desk IDs to filter
    - role_id: Optional list of role IDs to filter
    - page_size: Number of records to return (default: 100)
    - start_row: Starting row for pagination (default: 0)
    - fields_order: Order of fields in response
    - filter_model: Additional filters
    - order: Sort order

    Returns:
    - JSON response with client contact data
    """
    if not config.CLIENT_CONTACT_SERVICE_URL:
        logger.error("[Contacts-API] CLIENT_CONTACT_SERVICE_URL not configured")
        return {"status": "error", "message": "CLIENT_CONTACT_SERVICE_URL not configured"}
    url = config.CLIENT_CONTACT_SERVICE_URL


    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    headers = {
        "impersonated-employee-number": str(employee_id),
        "Content-Type": "application/json"
    }

    payload = {
        "criteria": {
            "cdr-id": [cdrid],
            "desk-id": desk_id or [],
            "employee-id": [employee_id],
            "hierarchy-depth": [hierarchy_depth],
            "hierarchy-type": [hierarchy_type],
            "role-id": role_id or []
        },
        "fields-order": fields_order or [],
        "filter-model": filter_model or {},
        "order": order or [],
        "page-size": page_size,
        "start-row": start_row
    }

    try:
        logger.info(f"[Contacts-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["contacts"])
        response.raise_for_status()
        result = response.json()

        # Preserve numbers for exact precision
        return add_data_integrity_check(result, api_name="get_client_contacts")

    except httpx.TimeoutException as e:
        logger.error(f"[Contacts-API] Timeout after 30s for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out after 30 seconds: {str(e)}"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[Contacts-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except httpx.RequestError as e:
        error_detail = f"{type(e).__name__}"
        if str(e):
            error_detail += f": {str(e)}"
        logger.error(f"[Contacts-API] Network error for CDRID={cdrid}: {error_detail}")
        return {"status": "error", "message": f"Network error: {error_detail}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[Contacts-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
################## CLIENT-COVERAGE  ##################
######################################################
async def get_client_coverage(
    cdrid: str,
    employee_id: Optional[int] = None,
    hierarchy_depth: str = "0",
    hierarchy_type: str = "CLIENT",
    desk_id: Optional[List[str]] = None,
    role_id: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Get client coverage team
    """
    if not config.CLIENT_COVERAGE_SERVICE_URL:
        logger.error("[Coverage-API] CLIENT_COVERAGE_SERVICE_URL not configured")
        return {"status": "error", "message": "CLIENT_COVERAGE_SERVICE_URL not configured"}
    url = config.CLIENT_COVERAGE_SERVICE_URL

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    payload = {
        "criteria": {
            "cdr-id": [cdrid],
            "desk-id": desk_id or [],
            "employee-id": [employee_id],
            "hierarchy-depth": [hierarchy_depth],
            "hierarchy-type": [hierarchy_type],
            "role-id": role_id or []
        },
        "fields": ["*"],
        "fields-order": [],
        "order": [],
        "page-size": 1000,
        "start-row": 0
    }

    try:
        logger.info(f"[Coverage-API] CDRID={cdrid}, employee_id={employee_id}, timeout=45s")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["coverage"])
        response.raise_for_status()
        result = response.json()

        if isinstance(result, dict) and 'client-coverage' in result:
            coverage_data = result.get('client-coverage', {}).get('data', [])
            if not coverage_data:
                logger.warning(f"[Coverage-API] No coverage data found for CDRID={cdrid}")
                return {"status": "error", "message": "No coverage data found"}
            logger.info(f"[Coverage-API] Success: {len(coverage_data)} coverage records found")

            # Skip integrity check for Coverage API (large responses, performance-sensitive)
            # Coverage data doesn't have numeric precision issues (names, emails, roles)
            return {"status": "success", "data": result}

        logger.warning(f"[Coverage-API] Unexpected response format for CDRID={cdrid}")
        return {"status": "error", "message": "Unexpected response format"}

    except httpx.TimeoutException as e:
        logger.error(f"[Coverage-API] Timeout after 30s for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out after 30 seconds: {str(e)}"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[Coverage-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[Coverage-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
#################### TOP-TRADES  #####################
######################################################
async def get_client_top_trades(
    cdrid: str,
    employee_id: Optional[int] = None,
    hierarchy_depth: str = "0",
    start_date: Optional[str] = None,  # Will default to 90 days ago
    end_date: Optional[str] = None,    # Will default to today
    sort_by: str = "Client Value",
    currency: str = "USD",
    reportable_mask: int = 1,
    metric: str = "CV"
) -> Dict[str, Any]:
    """
    Get client top trades
    
    Parameters:
    - sort_date/end_date: Date range for trades (YYYY-MM-DD format). Defaults to last 90 days.
    - sort_by: "Client Value" or "Notional" (Volume/Deal Size)
    - hierarchy_depth: "0" for Relationship level, "1" for Client level
    """
    
    # Default to last 90 days if dates not provided
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getTopTrades"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    payload = {
        "appCode": "tb20",
        "values": [
            employee_id,
            cdrid,
            hierarchy_depth,
            start_date,
            end_date,
            sort_by,
            currency,
            reportable_mask,
            metric
        ]
    }

    try:
        logger.info(f"[TopTrades-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["top_trades"])
        response.raise_for_status()
        result = response.json()

        # Preserve numbers for exact precision
        return add_data_integrity_check({"status": "success", "data": result}, api_name="get_client_top_trades")

    except Exception as e:
        logger.error(f"[TopTrades-API] Error: {type(e).__name__}: {e}")
        logger.error(f"[TopTrades-API] Payload: {payload}")
        return {"status": "error", "message": str(e)}


######################################################
##################### ALL-TRADES  ####################
######################################################
async def get_client_all_trades(
    cdrid: str,
    employee_id: Optional[int] = None,
    currency: str = "USD",
    hierarchy_depth: str = "0",
    time_period: str = "L30",
    limit_row_count: int = 1000,
    reportable_mask: int = 1,
    product: str = "1,320,-1",
    book_code: Optional[str] = None,
    market: Optional[str] = None,
    desk_with_salespersons: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    trade_currency: Optional[str] = None,
    filter_model: Optional[Dict[str, Any]] = None,
    sort_model: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Get all client trades with filtering
    
    CRITICAL PARAMETERS:
    - currency: Display currency (USD, CAD)
    - hierarchy_depth: "0" for Relationship, "1" for Client
    - time_period: L30, YTD, L90, L12M
    - limit_row_count: Max trades to return
    
    OPTIONAL PARAMETERS:
    - product, book_code, market, desk_with_salespersons
    - start_date, end_date (override time_period)
    - trade_currency, filter_model, sort_model
    """
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/procedure/memsql__client1__getTradeDetail"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    config_dict = {
        "bookCode": book_code,
        "cdrId": cdrid,
        "currency": currency,
        "deskWithSalespersons": desk_with_salespersons or [],
        "endDate": end_date,
        "ev": None,
        "filterModel": filter_model or {},
        "hierarchyDepth": hierarchy_depth,
        "limitRowCount": limit_row_count,
        "market": market,
        "product": product,
        "reportable-mask": reportable_mask,
        "sortModel": sort_model or {},
        "startDate": start_date,
        "timePeriod": time_period,
        "tradeCurrency": trade_currency
    }
    config_json = json.dumps(config_dict)

    payload = {
        "appCode": "tb20",
        "values": [employee_id, config_json]
    }

    try:
        logger.info(f"[AllTrades-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["all_trades"])
        response.raise_for_status()
        result = response.json()

        # Preserve numbers for exact precision
        return add_data_integrity_check({"status": "success", "data": result}, api_name="get_client_all_trades")

    except Exception as e:
        logger.error(f"[AllTrades-API] Error: {e}")
        return {"status": "error", "message": str(e)}


######################################################
################ CLIENT-INTERACTIONS  ################
######################################################
async def get_client_interactions(
    cdrid: str,
    employee_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    aggregation_by: Optional[List[str]] = None,
    desk_id: Optional[List[str]] = None,
    role_id: Optional[List[int]] = None,
    fields: Optional[List[str]] = None,
    fields_order: Optional[List[str]] = None,
    order: Optional[List[str]] = None,
    page_size: int = 1000
) -> Dict[str, Any]:
    """
    Get client interactions (meeting calendar)

    Parameters:
    - cdrid: Client CDRID
    - employee_id: Employee ID for authentication
    - from_date: Start date (YYYY-MM-DD format, defaults to 1 year ago)
    - to_date: End date (YYYY-MM-DD format, defaults to today)
    - aggregation_by: List of fields to aggregate by
    - desk_id: Optional list of desk IDs to filter
    - role_id: Optional list of role IDs to filter
    - fields: Fields to return (default: all)
    - fields_order: Order of fields in response
    - order: Sort order
    - page_size: Number of records to return (default: 1000)

    Returns:
    - JSON response with interaction/meeting data
    """
    if not config.INTERACTION_SERVICE_URL:
        logger.error("[Interactions-API] INTERACTION_SERVICE_URL not configured")
        return {"status": "error", "message": "INTERACTION_SERVICE_URL not configured"}
    url = config.INTERACTION_SERVICE_URL


    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    # Default date range: 1 year from today
    if to_date is None:
        to_date = datetime.now().strftime("%Y-%m-%d")
    if from_date is None:
        from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    headers = {
        "impersonated-employee-number": str(employee_id),
        "Content-Type": "application/json"
    }

    payload = {
        "criteria": {
            "aggregation-by": aggregation_by or [],
            "cdr-id": [cdrid],
            "desk-id": desk_id or [],
            "employee-id": [employee_id],
            "role-id": role_id or []
        },
        "fields": fields or [],
        "fields-order": fields_order or [],
        "filter-model": {
            "date": [
                {
                    "from-date": from_date,
                    "to-date": to_date
                }
            ]
        },
        "order": order or [],
        "page-size": page_size
    }

    try:
        logger.info(f"[Interactions-API] CDRID={cdrid}, date_range={from_date} to {to_date}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["interactions"])
        response.raise_for_status()
        result = response.json()

        # Preserve numbers for exact precision
        return add_data_integrity_check({"status": "success", "data": result}, api_name="get_client_interactions")

    except httpx.TimeoutException as e:
        logger.error(f"[Interactions-API] Timeout for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out: {str(e)}"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[Interactions-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[Interactions-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}

######################################################
################## MEETING-REPORTS  ##################
######################################################
async def get_client_meeting_reports(
    cdrid: str,
    employee_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    desk_id: Optional[List[str]] = None,
    role_id: Optional[List[int]] = None,
    fields: Optional[List[str]] = None,
    fields_order: Optional[List[str]] = None,
    order: Optional[str] = "",
    page_size: int = 0
) -> Dict[str, Any]:
    """
    Get client meeting reports

    Parameters:
    - cdrid: Client CDRID
    - employee_id: Employee ID for authentication
    - from_date: Start date (YYYY-MM-DD format, defaults to 30 days ago)
    - to_date: End date (YYYY-MM-DD format, defaults to today)
    - desk_id: Optional list of desk IDs to filter
    - role_id: Optional list of role IDs to filter
    - fields: Fields to return (default: all fields with ["*"])
    - fields_order: Order of fields in response
    - order: Sort order (default: empty string)
    - page_size: Number of records to return (0 = all, default)

    Returns:
    - JSON response with meeting report data
    """
    if not config.MEETING_REPORTS_SERVICE_URL:
        logger.error("[MeetingReports-API] MEETING_REPORTS_SERVICE_URL not configured")
        return {"status": "error", "message": "MEETING_REPORTS_SERVICE_URL not configured"}
    url = config.MEETING_REPORTS_SERVICE_URL


    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    # Default date range: 30 days
    if to_date is None:
        to_date = datetime.now().strftime("%Y-%m-%d")
    if from_date is None:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    headers = {
        "impersonated-employee-number": str(employee_id),
        "Content-Type": "application/json"
    }

    payload = {
        "criteria": {
            "cdr-id": [cdrid],
            "desk-id": desk_id or [],
            "employee-id": [employee_id],
            "role-id": role_id or []
        },
        "fields": fields or ["*"],  # Default to all fields
        "fields-order": fields_order or [],
        "filter-model": {
            "date": [
                {
                    "from-date": from_date,
                    "to-date": to_date
                }
            ]
        },
        "order": order,
        "page-size": str(page_size)  # API expects string
    }

    try:
        logger.info(f"[MeetingReports-API] CDRID={cdrid}, date_range={from_date} to {to_date}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=API_TIMEOUTS["meeting_reports"])
        response.raise_for_status()
        result = response.json()

        # Preserve numbers for exact precision
        return add_data_integrity_check({"status": "success", "data": result}, api_name="get_client_meeting_reports")

    except httpx.TimeoutException as e:
        logger.error(f"[MeetingReports-API] Timeout for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out: {str(e)}"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[MeetingReports-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[MeetingReports-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}
    

######################################################
############# LENDING RELATIONSHIP PROFITABILITY #####
######################################################
async def get_client_lrpm(
    cdrid: str,
    employee_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Get Lending Relationship Profitability Model (LRPM) data

    Calculates costs based on utilization of balance sheet and liquidity requirements.
    Returns revenue over:
    - LTM (Last Twelve Months) - short term
    - OTL (Over The Life - 5 years) - long term

    Data available in CAD only, sourced via CSI.

    Parameters:
    - cdrid: Client CDRID
    - employee_id: Employee ID (for appCode authentication)

    Note: Uses hardcoded CLIENT_HIERARCHY_TYPE_ID=2 and HIERARCHY_DEPTH=2
    """
    base_url = config.QUERY_SERVICES_BASE_URL
    url = f"{base_url}/query"

    headers = {
        "Authorization": config.QUERY_SERVICES_AUTH_TOKEN,
        "Content-Type": "text/plain"
    }

    if employee_id is None:
        # employee_id = int(config.IMPERSONATED_EMPLOYEE_ID)
        return {"status": "error", "message": "Employee ID must be provided"}


    # GraphQL-style query for LRPM data
    query = f"""{{
        getData(appCode:"TB20", where: "CDR_CLIENT_ID={cdrid} and CLIENT_HIERARCHY_TYPE_ID = 2 and HIERARCHY_DEPTH = 2")
        {{
            vw_cprof_client_consumer
            {{
                rwaLendingLtm: LENDING_RWA_LTM,
                rwaNonLendingLtm: NON_LENDING_RWA_LTM,
                currentQuadrant: QUADRANT_FINAL,
                currentQuadrantDesc: QUADRANT_FINAL_DESC,
                previousQuadrant: QUADRANT_PREVIOUS,
                previousQuadrantDesc: QUADRANT_PREVIOUS_DESC,
                totalRwaOtl: TOTAL_RWA_OTL,
                totalRwaLtm: TOTAL_RWA_LTM,
                rregLendingLtm: LN_RREG_LTM,
                rregRelationshipLtm: RL_RREG_LTM,
                revenueLendingLtm: GROSS_LN_REV_LTM,
                revenueNonLendingLtm: TOTAL_NLN_REV_LTM,
                revenueTotalLtm: TOTAL_REVENUE_LTM,
                otherRevenueNonLendingLtm: BNK_REV_LTM,
                totalRelationshipRevenueLtm: TOTAL_RELATIONSHIP_REVENUE_LTM,
                shortfallLtm: TG_SF_LTM,
                rwaLendingOtl: LENDING_RWA_OTL,
                rwaNonLendingOtl: NON_LENDING_RWA_OTL,
                rregLendingOtl: LN_RREG_OTL,
                rregRelationshipOtl: RL_RREG_OTL,
                revenueLendingOtl: GROSS_LN_REV_OTL,
                revenueNonLendingOtl: TOTAL_NLN_REV_OTL,
                revenueTotalOtl: TOTAL_REVENUE_OTL,
                otherRevenueNonLendingOtl: BNK_REV_OTL,
                totalRelationshipRevenueOtl: TOTAL_RELATIONSHIP_REVENUE_OTL,
                shortfallOtl: TG_SF_OTL,
                loanAuthorized: LN_AUTHORIZED_LME,
                loanOnBalance: LN_ON_BALANCE_SHEET_LME,
                loanOffBalance: LN_OFF_BALANCE_SHEET_LME
            }}
        }}
    }}"""

    try:
        logger.info(f"[LRPM-API] CDRID={cdrid}")
        client = await get_http_client()
        response = await client.post(url, headers=headers, data=query, timeout=API_TIMEOUTS["lrpm"])
        response.raise_for_status()

        # Parse JSON preserving numeric precision
        from app.utils.precision_guard import parse_response_preserving_numbers
        result = parse_response_preserving_numbers(response)

        # Integrity check 
        return add_data_integrity_check(result, api_name="get_client_lrpm")

    except httpx.TimeoutException as e:
        logger.error(f"[LRPM-API] Timeout for CDRID={cdrid}: {e}")
        return {"status": "error", "message": f"Request timed out: {str(e)}"}
    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:200] if hasattr(e.response, 'text') else str(e)
        logger.error(f"[LRPM-API] HTTP {e.response.status_code} for CDRID={cdrid}: {error_text}")
        return {"status": "error", "message": f"HTTP {e.response.status_code}: {error_text}"}
    except Exception as e:
        error_msg = str(e) or f"{type(e).__name__}: Unknown error"
        logger.error(f"[LRPM-API] Error for CDRID={cdrid}: {type(e).__name__} - {error_msg}")
        return {"status": "error", "message": error_msg}