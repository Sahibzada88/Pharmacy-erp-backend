-- ============================================================================
-- INVENTORY ANALYTICS — stock value, expiry, low-stock alerts
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fn_stock_valuation: "kitna stock hai, kitne paise ka hai" — chain or branch level
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_stock_valuation(
    p_branch_id INTEGER
)
RETURNS TABLE (
    total_batches BIGINT,
    total_units BIGINT,
    total_cost_value NUMERIC,
    total_retail_value NUMERIC,
    potential_profit NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT,
        COALESCE(SUM(b.quantity_remaining), 0)::BIGINT,
        COALESCE(SUM(b.quantity_remaining * b.cost_price), 0)::NUMERIC,
        COALESCE(SUM(b.quantity_remaining * b.sale_price), 0)::NUMERIC,
        COALESCE(SUM(b.quantity_remaining * (b.sale_price - b.cost_price)), 0)::NUMERIC
    FROM inventory_batch b
    WHERE (p_branch_id IS NULL OR b.branch_id = p_branch_id)
      AND b.is_active = TRUE
      AND b.quantity_remaining > 0;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_stock_valuation_by_branch: same as above but broken out per branch,
-- used for the owner's chain-wide comparison dashboard.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_stock_valuation_by_branch()
RETURNS TABLE (
    branch_id BIGINT,
    branch_name VARCHAR,
    total_units BIGINT,
    total_cost_value NUMERIC,
    total_retail_value NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        br.id,
        br.name::VARCHAR,
        COALESCE(SUM(b.quantity_remaining), 0)::BIGINT,
        COALESCE(SUM(b.quantity_remaining * b.cost_price), 0)::NUMERIC,
        COALESCE(SUM(b.quantity_remaining * b.sale_price), 0)::NUMERIC
    FROM branches_branch br
    LEFT JOIN inventory_batch b ON b.branch_id = br.id AND b.is_active = TRUE AND b.quantity_remaining > 0
    GROUP BY br.id, br.name
    ORDER BY br.name;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_expiry_report: batches expiring within N days, ordered soonest-first
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_expiry_report(
    p_branch_id INTEGER,
    p_days INTEGER DEFAULT 60
)
RETURNS TABLE (
    batch_id BIGINT,
    medicine_name VARCHAR,
    branch_name VARCHAR,
    batch_number VARCHAR,
    quantity_remaining INTEGER,
    expiry_date DATE,
    days_to_expiry INTEGER,
    stock_value NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        b.id,
        m.name::VARCHAR,
        br.name::VARCHAR,
        b.batch_number::VARCHAR,
        b.quantity_remaining,
        b.expiry_date,
        (b.expiry_date - CURRENT_DATE)::INTEGER,
        (b.quantity_remaining * b.cost_price)::NUMERIC
    FROM inventory_batch b
    JOIN inventory_medicine m ON m.id = b.medicine_id
    JOIN branches_branch br ON br.id = b.branch_id
    WHERE (p_branch_id IS NULL OR b.branch_id = p_branch_id)
      AND b.is_active = TRUE
      AND b.quantity_remaining > 0
      AND b.expiry_date <= CURRENT_DATE + p_days
    ORDER BY b.expiry_date ASC;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_low_stock_report: medicines at/below reorder level (chain or branch scope)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_low_stock_report(
    p_branch_id INTEGER
)
RETURNS TABLE (
    medicine_id BIGINT,
    medicine_name VARCHAR,
    sku VARCHAR,
    total_remaining BIGINT,
    reorder_level INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.name::VARCHAR,
        m.sku::VARCHAR,
        COALESCE(SUM(b.quantity_remaining), 0)::BIGINT AS total_remaining,
        m.reorder_level
    FROM inventory_medicine m
    LEFT JOIN inventory_batch b
        ON b.medicine_id = m.id AND b.is_active = TRUE
        AND (p_branch_id IS NULL OR b.branch_id = p_branch_id)
    WHERE m.is_active = TRUE
    GROUP BY m.id, m.name, m.sku, m.reorder_level
    HAVING COALESCE(SUM(b.quantity_remaining), 0) <= m.reorder_level
    ORDER BY total_remaining ASC;
END;
$$ LANGUAGE plpgsql STABLE;
