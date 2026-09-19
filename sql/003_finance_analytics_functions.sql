-- ============================================================================
-- FINANCE ANALYTICS — "kitne paise hain, bank ko kitne transfer kiye, kharcha"
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fn_bank_balance_summary: current balance per bank account + grand total
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_bank_balance_summary(
    p_branch_id INTEGER
)
RETURNS TABLE (
    bank_account_id BIGINT,
    bank_name VARCHAR,
    account_number VARCHAR,
    branch_name VARCHAR,
    current_balance NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ba.id,
        ba.bank_name::VARCHAR,
        ba.account_number::VARCHAR,
        COALESCE(br.name, 'Head Office')::VARCHAR,
        ba.current_balance
    FROM finance_bank_account ba
    LEFT JOIN branches_branch br ON br.id = ba.branch_id
    WHERE ba.is_active = TRUE
      AND (p_branch_id IS NULL OR ba.branch_id = p_branch_id OR ba.branch_id IS NULL)
    ORDER BY ba.bank_name;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_cash_position: cash currently sitting in each branch's open register(s)
-- + total cash deposited to bank in a date range (deposits reduce on-hand cash)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_cash_position(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    branch_id BIGINT,
    branch_name VARCHAR,
    cash_sales NUMERIC,
    cash_deposited_to_bank NUMERIC,
    estimated_cash_on_hand NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        br.id,
        br.name::VARCHAR,
        COALESCE((
            SELECT SUM(sp.amount) FROM sales_sale_payment sp
            JOIN sales_sale s ON s.id = sp.sale_id
            WHERE s.branch_id = br.id AND sp.method = 'CASH'
              AND s.status != 'VOIDED'
              AND s.created_at::date BETWEEN p_date_from AND p_date_to
        ), 0)::NUMERIC AS cash_sales,
        COALESCE((
            SELECT SUM(bt.amount) FROM finance_bank_transaction bt
            WHERE bt.branch_id = br.id AND bt.tx_type = 'DEPOSIT'
              AND bt.created_at::date BETWEEN p_date_from AND p_date_to
        ), 0)::NUMERIC AS cash_deposited_to_bank,
        (
            COALESCE((
                SELECT SUM(sp.amount) FROM sales_sale_payment sp
                JOIN sales_sale s ON s.id = sp.sale_id
                WHERE s.branch_id = br.id AND sp.method = 'CASH'
                  AND s.status != 'VOIDED'
                  AND s.created_at::date BETWEEN p_date_from AND p_date_to
            ), 0)
            -
            COALESCE((
                SELECT SUM(bt.amount) FROM finance_bank_transaction bt
                WHERE bt.branch_id = br.id AND bt.tx_type = 'DEPOSIT'
                  AND bt.created_at::date BETWEEN p_date_from AND p_date_to
            ), 0)
            -
            COALESCE((
                SELECT SUM(e.amount) FROM finance_expense e
                WHERE e.branch_id = br.id AND e.paid_from = 'CASH'
                  AND e.expense_date BETWEEN p_date_from AND p_date_to
            ), 0)
        )::NUMERIC AS estimated_cash_on_hand
    FROM branches_branch br
    WHERE (p_branch_id IS NULL OR br.id = p_branch_id)
    ORDER BY br.name;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_expense_breakdown: expenses grouped by category, for a date range
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_expense_breakdown(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    category_name VARCHAR,
    total_amount NUMERIC,
    transaction_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ec.name::VARCHAR,
        SUM(e.amount)::NUMERIC,
        COUNT(*)::BIGINT
    FROM finance_expense e
    JOIN finance_expense_category ec ON ec.id = e.category_id
    WHERE (p_branch_id IS NULL OR e.branch_id = p_branch_id)
      AND e.expense_date BETWEEN p_date_from AND p_date_to
    GROUP BY ec.name
    ORDER BY total_amount DESC;
END;
$$ LANGUAGE plpgsql STABLE;


-- ----------------------------------------------------------------------------
-- fn_profit_and_loss: simplified P&L for a date range (branch or chain-wide)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_profit_and_loss(
    p_branch_id INTEGER,
    p_date_from DATE,
    p_date_to DATE
)
RETURNS TABLE (
    net_sales NUMERIC,
    cost_of_goods_sold NUMERIC,
    gross_profit NUMERIC,
    total_expenses NUMERIC,
    net_profit NUMERIC
) AS $$
DECLARE
    v_net_sales NUMERIC;
    v_tax NUMERIC;
    v_cogs NUMERIC;
    v_expenses NUMERIC;
BEGIN
    SELECT COALESCE(SUM(s.total_amount), 0), COALESCE(SUM(s.tax_amount), 0)
    INTO v_net_sales, v_tax
    FROM sales_sale s
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to;

    SELECT COALESCE(SUM(si.unit_cost_snapshot * (si.quantity - si.quantity_returned)), 0) INTO v_cogs
    FROM sales_sale_item si
    JOIN sales_sale s ON s.id = si.sale_id
    WHERE (p_branch_id IS NULL OR s.branch_id = p_branch_id)
      AND s.status != 'VOIDED'
      AND s.created_at::date BETWEEN p_date_from AND p_date_to;

    SELECT COALESCE(SUM(e.amount), 0) INTO v_expenses
    FROM finance_expense e
    WHERE (p_branch_id IS NULL OR e.branch_id = p_branch_id)
      AND e.expense_date BETWEEN p_date_from AND p_date_to;

    -- Gross profit excludes tax_amount (it's collected on behalf of the
    -- government, not real profit) — same formula as fn_sales_summary and
    -- fn_owner_dashboard_summary, so all three dashboards always agree.
    RETURN QUERY SELECT
        v_net_sales::NUMERIC,
        v_cogs::NUMERIC,
        (v_net_sales - v_tax - v_cogs)::NUMERIC,
        v_expenses::NUMERIC,
        (v_net_sales - v_tax - v_cogs - v_expenses)::NUMERIC;
END;
$$ LANGUAGE plpgsql STABLE;
