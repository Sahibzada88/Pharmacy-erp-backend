-- ============================================================================
-- SUPPLIER ANALYTICS — "kitne supplier ko dene hain" (accounts payable)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fn_supplier_dues: total owed per supplier (purchase orders cost - payments made)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_supplier_dues(
    p_branch_id INTEGER
)
RETURNS TABLE (
    supplier_id BIGINT,
    supplier_name VARCHAR,
    total_purchased NUMERIC,
    total_paid NUMERIC,
    balance_due NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sup.id,
        sup.name::VARCHAR,
        COALESCE(po_totals.total_purchased, 0)::NUMERIC,
        COALESCE(pay_totals.total_paid, 0)::NUMERIC,
        (COALESCE(po_totals.total_purchased, 0) - COALESCE(pay_totals.total_paid, 0))::NUMERIC
    FROM suppliers_supplier sup
    LEFT JOIN (
        SELECT po.supplier_id, SUM(poi.quantity_ordered * poi.unit_cost) AS total_purchased
        FROM suppliers_purchase_order po
        JOIN suppliers_purchase_order_item poi ON poi.purchase_order_id = po.id
        WHERE po.status != 'CANCELLED'
          AND (p_branch_id IS NULL OR po.branch_id = p_branch_id)
        GROUP BY po.supplier_id
    ) po_totals ON po_totals.supplier_id = sup.id
    LEFT JOIN (
        SELECT sp.supplier_id, SUM(sp.amount) AS total_paid
        FROM suppliers_payment sp
        WHERE (p_branch_id IS NULL OR sp.branch_id = p_branch_id)
        GROUP BY sp.supplier_id
    ) pay_totals ON pay_totals.supplier_id = sup.id
    WHERE sup.is_active = TRUE
    ORDER BY balance_due DESC;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_supplier_payment_history: payments made to suppliers within a date range
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_supplier_payment_trend(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    payment_date DATE,
    total_paid NUMERIC,
    payment_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sp.paid_on,
        SUM(sp.amount)::NUMERIC,
        COUNT(*)::BIGINT
    FROM suppliers_payment sp
    WHERE (p_branch_id IS NULL OR sp.branch_id = p_branch_id)
      AND sp.paid_on BETWEEN p_date_from AND p_date_to
    GROUP BY sp.paid_on
    ORDER BY sp.paid_on;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_owner_dashboard_summary: one-shot combined KPI card for the OWNER's home
-- screen — sales, profit, stock value, payables, receivables-like cash, all
-- chain-wide (p_branch_id NULL) or filtered to one branch.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_owner_dashboard_summary(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    net_sales NUMERIC,
    gross_profit NUMERIC,
    total_invoices BIGINT,
    total_stock_value NUMERIC,
    total_bank_balance NUMERIC,
    total_supplier_dues NUMERIC,
    low_stock_items BIGINT,
    expiring_soon_items BIGINT
) AS $$
DECLARE
    v_net_sales NUMERIC := 0;
    v_tax NUMERIC := 0;
    v_gross_profit NUMERIC := 0;
    v_invoices BIGINT := 0;
    v_stock_value NUMERIC := 0;
    v_bank_balance NUMERIC := 0;
    v_supplier_dues NUMERIC := 0;
    v_low_stock BIGINT := 0;
    v_expiring BIGINT := 0;
    v_cogs NUMERIC := 0;
BEGIN
    SELECT COALESCE(SUM(s.total_amount), 0), COALESCE(SUM(s.tax_amount), 0), COUNT(DISTINCT s.id)
    INTO v_net_sales, v_tax, v_invoices
    FROM sales_sale s
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to;

    SELECT COALESCE(SUM(si.unit_cost_snapshot * (si.quantity - si.quantity_returned)), 0)
    INTO v_cogs
    FROM sales_sale_item si
    JOIN sales_sale s ON s.id = si.sale_id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to;

    -- Same formula as fn_sales_summary / fn_profit_and_loss: gross profit
    -- excludes tax (it's collected, not earned) and is net of COGS.
    v_gross_profit := v_net_sales - v_tax - v_cogs;

    SELECT COALESCE(SUM(b.quantity_remaining * b.cost_price), 0)
    INTO v_stock_value
    FROM inventory_batch b
    WHERE (p_branch_id IS NULL OR b.branch_id = p_branch_id)
      AND b.is_active = TRUE AND b.quantity_remaining > 0;

    SELECT COALESCE(SUM(ba.current_balance), 0)
    INTO v_bank_balance
    FROM finance_bank_account ba
    WHERE ba.is_active = TRUE
      AND (p_branch_id IS NULL OR ba.branch_id = p_branch_id OR ba.branch_id IS NULL);

    SELECT COALESCE(SUM(due.balance_due), 0) INTO v_supplier_dues
    FROM fn_supplier_dues(p_branch_id) due;

    SELECT COUNT(*) INTO v_low_stock FROM fn_low_stock_report(p_branch_id);

    SELECT COUNT(*) INTO v_expiring FROM fn_expiry_report(p_branch_id, 60);

    RETURN QUERY SELECT
        v_net_sales, v_gross_profit, v_invoices, v_stock_value,
        v_bank_balance, v_supplier_dues, v_low_stock, v_expiring;
END;
$$ LANGUAGE plpgsql STABLE;
