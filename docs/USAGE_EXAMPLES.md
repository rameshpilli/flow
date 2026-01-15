# Usage Examples

This document provides practical examples of using the Databricks SQL MCP Server with an LLM client.

## Basic Query Patterns

### Example 1: Simple Count Query

**User Request:** "How many customers do we have?"

**LLM Workflow:**

1. List available tables:
```python
databricks_list_tables()
# Returns: "customers, orders, products, regions"
```

2. Get schema for customers table:
```python
databricks_get_schema(table_names="customers")
# Returns:
# Table: main.default.customers
# Columns:
#   - customer_id: BIGINT (NOT NULL)
#   - customer_name: STRING (NULL)
#   - email: STRING (NULL)
#   - created_date: DATE (NULL)
#   - status: STRING (NULL)
```

3. Execute count query:
```python
databricks_execute_query(
    query="SELECT COUNT(*) as customer_count FROM customers WHERE status = 'active'"
)
# Returns: "Query returned 1 row(s): [(5432,)]"
```

**LLM Response:** "You have 5,432 active customers."

---

### Example 2: Aggregation Query

**User Request:** "What were our total sales by region last month?"

**LLM Workflow:**

1. List tables to find relevant data:
```python
databricks_list_tables()
# Returns: "customers, orders, products, regions, order_items"
```

2. Get schema for orders and regions:
```python
databricks_get_schema(table_names="orders, regions")
# Returns schema showing:
# - orders: order_id, customer_id, region_id, order_date, total_amount
# - regions: region_id, region_name, country
```

3. Execute aggregation query:
```python
databricks_execute_query(query="""
    SELECT 
        r.region_name,
        SUM(o.total_amount) as total_sales,
        COUNT(o.order_id) as order_count
    FROM orders o
    JOIN regions r ON o.region_id = r.region_id
    WHERE o.order_date >= '2025-12-01' 
    AND o.order_date < '2026-01-01'
    GROUP BY r.region_name
    ORDER BY total_sales DESC
""")
# Returns:
# Query returned 4 row(s):
# [('North America', 2543210.50, 1523),
#  ('Europe', 1876543.25, 987),
#  ('Asia Pacific', 1234567.75, 756),
#  ('Latin America', 876543.00, 432)]
```

**LLM Response:**
"Here are the total sales by region for last month:
- North America: $2,543,210.50 (1,523 orders)
- Europe: $1,876,543.25 (987 orders)
- Asia Pacific: $1,234,567.75 (756 orders)
- Latin America: $876,543.00 (432 orders)"

---

### Example 3: Top N Query

**User Request:** "Show me the top 10 customers by total purchase amount."

**LLM Workflow:**

1. Get schema to understand relationships:
```python
databricks_get_schema(table_names="customers, orders")
```

2. Execute top N query:
```python
databricks_execute_query(query="""
    SELECT 
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) as order_count,
        SUM(o.total_amount) as total_spent
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id, c.customer_name
    ORDER BY total_spent DESC
    LIMIT 10
""")
```

**LLM Response:** Formats the top 10 customers in a readable format.

---

### Example 4: Time Series Analysis

**User Request:** "Show me daily order trends for the past week."

```python
databricks_execute_query(query="""
    SELECT 
        order_date,
        COUNT(*) as order_count,
        SUM(total_amount) as daily_revenue,
        AVG(total_amount) as avg_order_value
    FROM orders
    WHERE order_date >= DATE_SUB(CURRENT_DATE(), 7)
    GROUP BY order_date
    ORDER BY order_date
""")
```

---

### Example 5: Complex Join with Filtering

**User Request:** "Which products in the Electronics category sold more than 100 units last quarter?"

```python
databricks_execute_query(query="""
    SELECT 
        p.product_name,
        p.category,
        SUM(oi.quantity) as total_units_sold,
        SUM(oi.quantity * oi.unit_price) as total_revenue
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    JOIN orders o ON oi.order_id = o.order_id
    WHERE p.category = 'Electronics'
    AND o.order_date >= DATE_SUB(CURRENT_DATE(), 90)
    GROUP BY p.product_id, p.product_name, p.category
    HAVING SUM(oi.quantity) > 100
    ORDER BY total_units_sold DESC
""")
```

---

## Working with Different Catalogs/Schemas

### Example 6: Query Specific Catalog

**User Request:** "Show me tables in the analytics catalog, finance schema."

```python
# List tables in specific catalog/schema
databricks_list_tables(catalog="analytics", schema="finance")
# Returns: "revenue_report, expense_report, budget_tracking"

# Get schema for specific table
databricks_get_schema(
    table_names="revenue_report",
    catalog="analytics",
    schema="finance"
)
```

---

## Cache Management

### Example 7: Using Cache for Repeated Queries

```python
# First query - hits database
databricks_execute_query(
    query="SELECT COUNT(*) FROM orders",
    use_cache=True
)
# Execution time: 2.5s

# Same query again - uses cache
databricks_execute_query(
    query="SELECT COUNT(*) FROM orders",
    use_cache=True
)
# Execution time: 0.05s (from cache)
```

### Example 8: Getting Fresh Data

```python
# User says "ignore cache" or "get fresh data"

# Clear cache first
databricks_clear_cache()

# Then execute query
databricks_execute_query(
    query="SELECT COUNT(*) FROM orders",
    use_cache=False  # Explicitly bypass cache
)
```

### Example 9: Checking Cache Performance

```python
databricks_cache_stats()
# Returns:
# Cache Statistics:
#   Status: Connected
#   Keys: 42
#   Memory Used: 2.3MB
#   Hits: 1523
#   Misses: 387
#   Hit Rate: 79.74%
```

---

## Error Handling Examples

### Example 10: Handling Invalid Queries

**User Request:** "Delete all old orders" (attempting modification)

```python
databricks_execute_query(query="DELETE FROM orders WHERE order_date < '2020-01-01'")
# Returns: "Query validation failed: Query contains forbidden keyword: DELETE. 
#           Only SELECT queries are allowed."
```

**LLM Response:** "I'm unable to delete data as this server only supports read-only SELECT queries for safety. If you need to delete data, please use the Databricks SQL editor directly."

### Example 11: Handling Table Not Found

```python
databricks_execute_query(query="SELECT * FROM non_existent_table")
# Returns: "Error: Table or column not found. Use databricks_list_tables 
#           to see available tables."
```

**LLM Recovery:**
```python
# Automatically suggests checking available tables
databricks_list_tables()
```

---

## Advanced Patterns

### Example 12: CTE (Common Table Expression)

```python
databricks_execute_query(query="""
    WITH monthly_sales AS (
        SELECT 
            DATE_TRUNC('month', order_date) as month,
            SUM(total_amount) as monthly_total
        FROM orders
        WHERE order_date >= '2025-01-01'
        GROUP BY DATE_TRUNC('month', order_date)
    )
    SELECT 
        month,
        monthly_total,
        LAG(monthly_total) OVER (ORDER BY month) as previous_month,
        monthly_total - LAG(monthly_total) OVER (ORDER BY month) as growth
    FROM monthly_sales
    ORDER BY month
""")
```

### Example 13: Window Functions

```python
databricks_execute_query(query="""
    SELECT 
        customer_id,
        customer_name,
        total_spent,
        RANK() OVER (ORDER BY total_spent DESC) as spending_rank,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_spent) 
            OVER () as median_spending
    FROM (
        SELECT 
            c.customer_id,
            c.customer_name,
            SUM(o.total_amount) as total_spent
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY c.customer_id, c.customer_name
    )
    WHERE total_spent > 10000
    ORDER BY spending_rank
    LIMIT 20
""")
```

### Example 14: Exploring Schema Incrementally

**User Request:** "I want to analyze customer purchase patterns."

**LLM Strategy:**

1. Start broad:
```python
databricks_list_tables()
```

2. Identify relevant tables:
```python
databricks_get_schema(table_names="customers")
databricks_get_schema(table_names="orders")
databricks_get_schema(table_names="order_items")
```

3. Build query incrementally based on available columns

4. Execute analytical query

---

## Best Practices for LLM Integration

### 1. Always Check Schema First
Before building queries, inspect table structures:
```python
databricks_get_schema(table_names="target_table")
```

### 2. Use Explicit Column Names
Avoid `SELECT *`, always specify columns:
```python
# Good
"SELECT customer_id, customer_name, total_spent FROM ..."

# Avoid
"SELECT * FROM ..."
```

### 3. Add Reasonable Limits
Even though the server adds automatic limits, include them in your queries:
```python
"SELECT ... FROM ... ORDER BY ... LIMIT 100"
```

### 4. Handle Errors Gracefully
When a query fails, use the error message to recover:
- "Table not found" → Call `databricks_list_tables()`
- "Permission denied" → Inform user of access restrictions
- "Timeout" → Suggest simplifying the query

### 5. Leverage Caching
For repeated or similar queries, use caching:
```python
# Use cache by default
databricks_execute_query(query="...", use_cache=True)

# Only bypass for "fresh data" requests
databricks_execute_query(query="...", use_cache=False)
```

### 6. Build Complex Queries Incrementally
Test simple queries first, then add complexity:
```python
# Step 1: Basic count
"SELECT COUNT(*) FROM orders"

# Step 2: Add filtering
"SELECT COUNT(*) FROM orders WHERE order_date >= '2025-01-01'"

# Step 3: Add grouping
"SELECT region_id, COUNT(*) FROM orders WHERE ... GROUP BY region_id"
```

---

## Common Query Templates

### Count Records
```sql
SELECT COUNT(*) as total_count 
FROM {table} 
WHERE {conditions}
```

### Aggregate by Group
```sql
SELECT 
    {group_column},
    COUNT(*) as count,
    SUM({metric_column}) as total,
    AVG({metric_column}) as average
FROM {table}
WHERE {conditions}
GROUP BY {group_column}
ORDER BY total DESC
```

### Time-based Analysis
```sql
SELECT 
    DATE_TRUNC('{period}', {date_column}) as period,
    COUNT(*) as count,
    SUM({metric}) as total
FROM {table}
WHERE {date_column} >= DATE_SUB(CURRENT_DATE(), {days})
GROUP BY DATE_TRUNC('{period}', {date_column})
ORDER BY period
```

### Top N
```sql
SELECT {columns}
FROM {table}
WHERE {conditions}
ORDER BY {sort_column} DESC
LIMIT {n}
```

### Join Pattern
```sql
SELECT 
    {table1_columns},
    {table2_columns}
FROM {table1} t1
JOIN {table2} t2 ON t1.{key} = t2.{key}
WHERE {conditions}
```

---

## Interactive Session Example

Here's a complete example of an interactive session:

**User:** "I want to understand our sales performance."

**Assistant:** Let me help you analyze sales. First, let me see what tables are available.

```python
databricks_list_tables()
# Returns: "customers, orders, products, regions, order_items"
```

Great! I see we have orders and related tables. Let me check the structure of the orders table.

```python
databricks_get_schema(table_names="orders")
# Returns full schema...
```

Perfect! Now let me get you some key sales metrics.

```python
databricks_execute_query(query="""
    SELECT 
        COUNT(DISTINCT order_id) as total_orders,
        SUM(total_amount) as total_revenue,
        AVG(total_amount) as avg_order_value,
        COUNT(DISTINCT customer_id) as unique_customers
    FROM orders
    WHERE order_date >= DATE_SUB(CURRENT_DATE(), 30)
""")
```

**User:** "How does this compare to last month?"

```python
databricks_execute_query(query="""
    SELECT 
        CASE 
            WHEN order_date >= DATE_SUB(CURRENT_DATE(), 30) THEN 'This Month'
            ELSE 'Last Month'
        END as period,
        COUNT(*) as order_count,
        SUM(total_amount) as revenue
    FROM orders
    WHERE order_date >= DATE_SUB(CURRENT_DATE(), 60)
    GROUP BY CASE 
        WHEN order_date >= DATE_SUB(CURRENT_DATE(), 30) THEN 'This Month'
        ELSE 'Last Month'
    END
""")
```

---

## Tips for Optimal Performance

1. **Use cache for dashboard queries** - Queries that power dashboards should use cache
2. **Clear cache when data updates** - After data loads, clear relevant caches
3. **Add date filters** - Always filter large tables by date when possible
4. **Monitor cache hit rates** - Use `databricks_cache_stats()` to optimize TTLs
5. **Test queries incrementally** - Build from simple to complex

---

## Conclusion

The Databricks SQL MCP Server provides a safe, cached, and production-ready way to query Databricks from LLMs. By following these patterns and examples, you can build powerful data exploration and analysis capabilities into your LLM applications.
