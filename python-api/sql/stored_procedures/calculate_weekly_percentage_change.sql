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
            wc.week_start_timestamp as timestamp_ms,
            wc.close,
            LAG(wc.close, p_lookback) OVER (PARTITION BY wc.symbol ORDER BY wc.week_start_timestamp) as prev_close
        FROM weekly_candles wc
        WHERE wc.symbol = p_symbol
        ORDER BY wc.week_start_timestamp
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

-- Drop existing function to avoid signature conflicts
DROP FUNCTION IF EXISTS calculate_weekly_percentage_change_for_symbol(TEXT);

-- Function to calculate weekly percentage change for a single symbol
-- Returns status information to match the service expected signature
CREATE OR REPLACE FUNCTION calculate_weekly_percentage_change_for_symbol(
    p_symbol TEXT
) RETURNS TABLE (
    updated_rows INTEGER,
    status TEXT
) AS $$
DECLARE
    v_updated_rows INTEGER := 0;
BEGIN
    -- Calculate weekly percentage change using dynamic sliding window approach
    -- Each day compares its OWN close to the previous week's final close
    WITH weekly_pct_data AS (
        SELECT 
            dc.candle_key_id,
            dc.close as current_day_close,
            wc_prev.close as prev_week_final_close,
            CASE 
                WHEN wc_prev.close IS NOT NULL AND wc_prev.close > 0 THEN
                    ROUND(((dc.close - wc_prev.close) / wc_prev.close * 100)::numeric, 4)
                ELSE 
                    NULL
            END as weekly_pct_change
        FROM daily_candles dc
        -- Join with current week's weekly candle to get week info
        LEFT JOIN weekly_candles wc_current 
            ON dc.weekly_candle_key_id = wc_current.weekly_candle_key_id
        -- Join with previous week's weekly candle to get previous week's final close
        LEFT JOIN weekly_candles wc_prev 
            ON wc_prev.weekly_candle_key_id = (dc.symbol || '_W' || (wc_current.week_sequence_number - 1)::TEXT)
        WHERE dc.symbol = p_symbol
          AND wc_current.week_sequence_number > 1  -- Skip first week since no previous week
    )
    UPDATE daily_candles AS target_table
    SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object('weekly_pctchg', wpd.weekly_pct_change),
        updated_at = CURRENT_TIMESTAMP
    FROM weekly_pct_data wpd
    WHERE target_table.candle_key_id = wpd.candle_key_id
      AND wpd.weekly_pct_change IS NOT NULL
      AND (
          -- Only update if indicator doesn't exist or is null
          NOT (target_table.indicators ? 'weekly_pctchg') OR 
          (target_table.indicators->'weekly_pctchg') IS NULL OR
          (target_table.indicators->'weekly_pctchg') = 'null'::jsonb
      );
    
    -- Get count of updated rows
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    -- Return results
    RETURN QUERY SELECT 
        v_updated_rows,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        -- Return failure status
        RETURN QUERY SELECT 
            0,
            format('ERROR: %s', SQLERRM)::TEXT;
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

-- Drop the function first to avoid signature conflicts
DROP FUNCTION IF EXISTS calculate_weekly_percentage_change(TEXT, INTEGER);

-- Main interface function to match the service expected signature
-- This function updates the indicators column in daily_candles with weekly percentage change
CREATE OR REPLACE FUNCTION calculate_weekly_percentage_change(
    p_symbol_filter TEXT DEFAULT NULL,  -- Optional symbol filter for single stock
    p_batch_size INTEGER DEFAULT 1000   -- Not used for weekly, kept for compatibility
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_end_time TIMESTAMP;
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_batch_count INTEGER := 0;
    symbol_cursor CURSOR FOR 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol;
    symbol_rec RECORD;
BEGIN
    
    RAISE NOTICE 'Starting weekly percentage change calculation';
    
    -- Process each symbol separately for better performance and memory management
    FOR symbol_rec IN symbol_cursor LOOP
        -- Calculate weekly percentage change using dynamic sliding window approach
        -- Each day compares its close to the previous week's final close
        WITH weekly_pct_data AS (
            SELECT 
                dc.candle_key_id,
                dc.close as current_day_close,
                wc_prev.close as prev_week_final_close,
                CASE 
                    WHEN wc_prev.close IS NOT NULL AND wc_prev.close > 0 THEN
                        ROUND(((dc.close - wc_prev.close) / wc_prev.close * 100)::numeric, 4)
                    ELSE 
                        NULL
                END as weekly_pct_change
            FROM daily_candles dc
            -- Join with current week's weekly candle to get week info
            LEFT JOIN weekly_candles wc_current 
                ON dc.weekly_candle_key_id = wc_current.weekly_candle_key_id
            -- Join with previous week's weekly candle to get previous week's final close
            LEFT JOIN weekly_candles wc_prev 
                ON wc_prev.weekly_candle_key_id = (dc.symbol || '_W' || (wc_current.week_sequence_number - 1)::TEXT)
            WHERE dc.symbol = symbol_rec.symbol
              AND wc_current.week_sequence_number > 1  -- Skip first week since no previous week
        )
        UPDATE daily_candles AS target_table
        SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object('weekly_pctchg', wpd.weekly_pct_change),
            updated_at = CURRENT_TIMESTAMP
        FROM weekly_pct_data wpd
        WHERE target_table.candle_key_id = wpd.candle_key_id
          AND wpd.weekly_pct_change IS NOT NULL
          AND (
              -- Only update if indicator doesn't exist or is null
              NOT (target_table.indicators ? 'weekly_pctchg') OR 
              (target_table.indicators->'weekly_pctchg') IS NULL OR
              (target_table.indicators->'weekly_pctchg') = 'null'::jsonb
          );
        
        -- Get count of updated rows for this symbol
        GET DIAGNOSTICS v_batch_count = ROW_COUNT;
        v_updated_rows := v_updated_rows + v_batch_count;
        v_processed_symbols := v_processed_symbols + 1;
        
        -- Log progress every 10 symbols
        IF v_processed_symbols % 10 = 0 THEN
            RAISE NOTICE 'Processed % symbols, updated % rows total', 
                v_processed_symbols, v_updated_rows;
        END IF;
        
    END LOOP;
    
    v_end_time := clock_timestamp();
    
    -- Log completion
    RAISE NOTICE 'Completed weekly percentage change calculation: % symbols processed, % rows updated in % ms',
        v_processed_symbols, v_updated_rows, 
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    -- Return results
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        -- Log error and return failure status
        RAISE NOTICE 'Error in calculate_weekly_percentage_change: %', SQLERRM;
        v_end_time := clock_timestamp();
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;