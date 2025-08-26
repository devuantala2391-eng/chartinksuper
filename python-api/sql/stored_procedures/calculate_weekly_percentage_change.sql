-- =====================================================
-- Weekly Percentage Change Calculation Procedures
-- =====================================================

-- Function to calculate percentage change for a single stock symbol
CREATE OR REPLACE FUNCTION calculate_weekly_percentage_change(
    p_symbol TEXT,
    p_lookback INTEGER DEFAULT 1
) RETURNS TABLE (
    symbol TEXT,
    timestamp_ms BIGINT,
    percentage_change DECIMAL(10,4)
) AS $$
BEGIN
    RETURN QUERY
    WITH ordered_candles AS (
        SELECT 
            wc.symbol,
            wc.start_timestamp as timestamp_ms,
            wc.close,
            LAG(wc.close, p_lookback) OVER (PARTITION BY wc.symbol ORDER BY wc.start_timestamp) as prev_close
        FROM weekly_candles wc
        WHERE wc.symbol = p_symbol
        ORDER BY wc.start_timestamp
    )
    SELECT 
        oc.symbol::TEXT,
        oc.timestamp_ms,
        CASE 
            WHEN oc.prev_close IS NOT NULL AND oc.prev_close > 0 
            THEN ROUND(((oc.close - oc.prev_close) / oc.prev_close * 100)::DECIMAL, 4)
            ELSE NULL
        END as percentage_change
    FROM ordered_candles oc
    WHERE oc.prev_close IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate percentage change for all symbols
CREATE OR REPLACE FUNCTION calculate_weekly_percentage_change_for_symbol(
    p_symbol TEXT
) RETURNS TABLE (
    symbol TEXT,
    timestamp_ms BIGINT,
    weekly_pctchg DECIMAL(10,4)
) AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM calculate_weekly_percentage_change(p_symbol, 1);
END;
$$ LANGUAGE plpgsql;

-- Function to batch process multiple symbols
CREATE OR REPLACE FUNCTION calculate_weekly_percentage_change_batch(
    p_symbols TEXT[]
) RETURNS TABLE (
    symbol TEXT,
    timestamp_ms BIGINT,
    weekly_pctchg DECIMAL(10,4)
) AS $$
DECLARE
    symbol_name TEXT;
BEGIN
    FOREACH symbol_name IN ARRAY p_symbols
    LOOP
        RETURN QUERY
        SELECT * FROM calculate_weekly_percentage_change_for_symbol(symbol_name);
    END LOOP;
END;
$$ LANGUAGE plpgsql;