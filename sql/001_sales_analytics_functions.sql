-- ============================================================================
-- SALES ANALYTICS — Postgres functions (stored procedures)
-- Called from Django via raw SQL for speed (avoids heavy ORM aggregation).
-- p_branch_id = NULL means "chain-wide" (owner view across all branches).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fn_sales_summary: headline KPIs for a date range (owner/accountant dashboard)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_sales_summary(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    total_invoices BIGINT,
    total_units_sold BIGINT,
    gross_sales NUMERIC,
    total_discount NUMERIC,
    total_tax NUMERIC,
    net_sales NUMERIC,
    total_cost NUMERIC,
    gross_profit NUMERIC,
    total_returns_amount NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT s.id)::BIGINT,
        COALESCE(SUM(si.quantity - si.quantity_returned), 0)::BIGINT,
        COALESCE(SUM(s.subtotal), 0)::NUMERIC,
        COALESCE(SUM(s.discount_amount), 0)::NUMERIC,
        COALESCE(SUM(s.tax_amount), 0)::NUMERIC,
        COALESCE(SUM(s.total_amount), 0)::NUMERIC,
        COALESCE(SUM(si.unit_cost_snapshot * (si.quantity - si.quantity_returned)), 0)::NUMERIC,
        COALESCE(SUM((si.unit_price - si.unit_cost_snapshot) * (si.quantity - si.quantity_returned) - si.discount_amount), 0)::NUMERIC,
        COALESCE((
            SELECT SUM(sr.refund_amount) FROM sales_sale_return sr
            JOIN sales_sale s2 ON s2.id = sr.sale_id
            WHERE (p_branch_id IS NULL OR s2.branch_id = p_branch_id)
              AND sr.created_at::date BETWEEN p_date_from AND p_date_to
        ), 0)::NUMERIC
    FROM sales_sale s
    JOIN sales_sale_item si ON si.sale_id = s.id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_daily_sales_trend: day-by-day sales + profit, for line charts
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_daily_sales_trend(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    sale_date DATE,
    invoices BIGINT,
    net_sales NUMERIC,
    gross_profit NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.created_at::date AS sale_date,
        COUNT(DISTINCT s.id)::BIGINT,
        COALESCE(SUM(s.total_amount), 0)::NUMERIC,
        COALESCE(SUM((si.unit_price - si.unit_cost_snapshot) * (si.quantity - si.quantity_returned) - si.discount_amount), 0)::NUMERIC
    FROM sales_sale s
    JOIN sales_sale_item si ON si.sale_id = s.id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to
    GROUP BY s.created_at::date
    ORDER BY sale_date;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_top_selling_medicines: best sellers by quantity & revenue
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_top_selling_medicines(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    medicine_id INTEGER,
    medicine_name VARCHAR,
    units_sold BIGINT,
    revenue NUMERIC,
    profit NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        b.medicine_id,
        si.medicine_name_snapshot,
        SUM(si.quantity - si.quantity_returned)::BIGINT,
        SUM(si.line_total)::NUMERIC,
        SUM((si.unit_price - si.unit_cost_snapshot) * (si.quantity - si.quantity_returned) - si.discount_amount)::NUMERIC
    FROM sales_sale_item si
    JOIN sales_sale s ON s.id = si.sale_id
    JOIN inventory_batch b ON b.id = si.batch_id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to
    GROUP BY b.medicine_id, si.medicine_name_snapshot
    ORDER BY units_sold DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_cashier_performance: per-cashier sales totals (owner/manager oversight)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_cashier_performance(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    cashier_id INTEGER,
    cashier_name VARCHAR,
    invoices BIGINT,
    net_sales NUMERIC,
    avg_invoice_value NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id,
        COALESCE(NULLIF(TRIM(u.first_name || ' ' || u.last_name), ''), u.username)::VARCHAR,
        COUNT(s.id)::BIGINT,
        COALESCE(SUM(s.total_amount), 0)::NUMERIC,
        CASE WHEN COUNT(s.id) > 0 THEN (SUM(s.total_amount) / COUNT(s.id))::NUMERIC ELSE 0 END
    FROM sales_sale s
    JOIN accounts_user u ON u.id = s.cashier_id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to
    GROUP BY u.id, u.first_name, u.last_name, u.username
    ORDER BY net_sales DESC;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_payment_method_breakdown: how much came in via cash/card/bank/wallet/credit
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_payment_method_breakdown(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    method VARCHAR,
    total_amount NUMERIC,
    transaction_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sp.method::VARCHAR,
        SUM(sp.amount)::NUMERIC,
        COUNT(*)::BIGINT
    FROM sales_sale_payment sp
    JOIN sales_sale s ON s.id = sp.sale_id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to
    GROUP BY sp.method
    ORDER BY total_amount DESC;
END;
$$ LANGUAGE plpgsql STABLE;
