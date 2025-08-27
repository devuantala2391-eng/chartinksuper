-- =====================================================
-- PERCENTAGE CHANGE CALCULATION STORED PROCEDURE
-- =====================================================
-- This procedure calculates percentage change indicators
-- for all timeframes (daily, weekly, monthly) and stores
-- them in the indicators JSONB column
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_percentage_change(
    p_timeframe TEXT DEFAULT 'daily',
    p_symbol_filter TEXT DEFAULT NULL,  -- Optional symbol filter for single stock
    p_batch_size INTEGER DEFAULT 1000   -- Process in batches for performance
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
    v_table_name TEXT;
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_sql TEXT;
    v_batch_count INTEGER := 0;
    rec RECORD;
    symbol_cursor CURSOR FOR 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol;
BEGIN
    -- Validate timeframe parameter
    IF p_timeframe NOT IN ('daily', 'weekly', 'monthly') THEN
        RAISE EXCEPTION 'Invalid timeframe: %. Must be daily, weekly, or monthly', p_timeframe;
    END IF;
    
    -- Set table name and indicator key based on timeframe
    -- Monthly percentage is calculated from daily data, not monthly_candles
    IF p_timeframe = 'monthly' THEN
        v_table_name := 'daily_candles';
        v_indicator_key := 'monthly_pctchg';
    ELSE
        v_table_name := p_timeframe || '_candles';
        v_indicator_key := p_timeframe || '_pctchg';
    END IF;
    
    -- Log start of calculation
    RAISE NOTICE 'Starting % percentage change calculation for table % with batch size %', 
        p_timeframe, v_table_name, p_batch_size;
    
    -- Process each symbol separately for better performance and memory management
    FOR symbol_rec IN symbol_cursor LOOP
        -- Calculate percentage change for current symbol with timeframe-specific logic
        IF p_timeframe = 'monthly' THEN
            -- Monthly percentage change: compare with close price ~30 trading days ago
            EXECUTE format($sql$
                WITH ranked_candles AS (
                    SELECT 
                        candle_key_id,
                        symbol,
                        candle_sequence_number,
                        timestamp,
                        close,
                        indicators,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY candle_sequence_number) as rn,
                        LAG(close, 30) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) as prev_month_close
                    FROM %I
                    WHERE symbol = $1
                ),
                calculated AS (
                    SELECT 
                        candle_key_id,
                        symbol,
                        CASE 
                            WHEN prev_month_close IS NOT NULL AND prev_month_close != 0 THEN
                                ROUND(((close - prev_month_close) / prev_month_close * 100)::numeric, 4)
                            ELSE 
                                NULL
                        END as pct_change,
                        indicators
                    FROM ranked_candles
                )
                UPDATE %I AS target_table
                SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object($2, calculated.pct_change),
                    updated_at = CURRENT_TIMESTAMP
                FROM calculated
                WHERE target_table.candle_key_id = calculated.candle_key_id
                  AND (
                      -- Only update if indicator doesn't exist or is null
                      NOT (target_table.indicators ? $2) OR 
                      (target_table.indicators->$2) IS NULL OR
                      (target_table.indicators->$2) = 'null'::jsonb
                  )
            $sql$, v_table_name, v_table_name)
            USING symbol_rec.symbol, v_indicator_key;
        ELSE
            -- Daily/Weekly percentage change: compare with previous period
            EXECUTE format($sql$
                WITH ranked_candles AS (
                    SELECT 
                        candle_key_id,
                        symbol,
                        candle_sequence_number,
                        timestamp,
                        close,
                        indicators,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY candle_sequence_number) as rn,
                        LAG(close, 1) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) as prev_close
                    FROM %I
                    WHERE symbol = $1
                ),
                calculated AS (
                    SELECT 
                        candle_key_id,
                        symbol,
                        CASE 
                            WHEN prev_close IS NOT NULL AND prev_close != 0 THEN
                                ROUND(((close - prev_close) / prev_close * 100)::numeric, 4)
                            ELSE 
                                NULL
                        END as pct_change,
                        indicators
                    FROM ranked_candles
                )
                UPDATE %I AS target_table
                SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object($2, calculated.pct_change),
                    updated_at = CURRENT_TIMESTAMP
                FROM calculated
                WHERE target_table.candle_key_id = calculated.candle_key_id
                  AND (
                      -- Only update if indicator doesn't exist or is null
                      NOT (target_table.indicators ? $2) OR 
                      (target_table.indicators->$2) IS NULL OR
                      (target_table.indicators->$2) = 'null'::jsonb
                  )
            $sql$, v_table_name, v_table_name, v_table_name)
            USING symbol_rec.symbol, v_indicator_key;
        END IF;
        
        -- Get count of updated rows for this symbol
        GET DIAGNOSTICS v_batch_count = ROW_COUNT;
        v_updated_rows := v_updated_rows + v_batch_count;
        v_processed_symbols := v_processed_symbols + 1;
        
        -- Log progress every 100 symbols
        IF v_processed_symbols % 100 = 0 THEN
            RAISE NOTICE 'Processed % symbols, updated % rows total', 
                v_processed_symbols, v_updated_rows;
        END IF;
        
        -- Optional: Add small delay between batches to prevent resource exhaustion
        -- PERFORM pg_sleep(0.001); -- 1ms delay
    END LOOP;
    
    v_end_time := clock_timestamp();
    
    -- Log completion
    RAISE NOTICE 'Completed % percentage change calculation: % symbols processed, % rows updated in % ms',
        p_timeframe, v_processed_symbols, v_updated_rows, 
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
        RAISE NOTICE 'Error in calculate_percentage_change: %', SQLERRM;
        v_end_time := clock_timestamp();
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- HELPER FUNCTION: Calculate percentage change for single symbol
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_percentage_change_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily'
)
RETURNS TABLE(
    updated_rows INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    result RECORD;
BEGIN
    -- Call main function with symbol filter
    SELECT * INTO result FROM calculate_percentage_change(p_timeframe, p_symbol, 1000);
    
    RETURN QUERY SELECT result.updated_rows, result.status;
END;
$$;

-- =====================================================
-- UTILITY FUNCTION: Check percentage change coverage
-- =====================================================
CREATE OR REPLACE FUNCTION check_percentage_change_coverage(
    p_timeframe TEXT DEFAULT 'daily'
)
RETURNS TABLE(
    total_rows BIGINT,
    rows_with_indicator BIGINT,
    coverage_percentage NUMERIC,
    missing_rows BIGINT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_table_name TEXT;
    v_indicator_key TEXT;
BEGIN
    -- Monthly percentage is calculated from daily data, not monthly_candles
    IF p_timeframe = 'monthly' THEN
        v_table_name := 'daily_candles';
        v_indicator_key := 'monthly_pctchg';
    ELSE
        v_table_name := p_timeframe || '_candles';
        v_indicator_key := p_timeframe || '_pctchg';
    END IF;
    
    RETURN QUERY EXECUTE format($sql$
        WITH stats AS (
            SELECT 
                COUNT(*) as total_rows,
                COUNT(CASE WHEN indicators ? $1 AND (indicators->$1) IS NOT NULL THEN 1 END) as rows_with_indicator
            FROM %I
        )
        SELECT 
            total_rows,
            rows_with_indicator,
            CASE WHEN total_rows > 0 THEN 
                ROUND((rows_with_indicator::numeric / total_rows::numeric * 100), 2)
            ELSE 0 END as coverage_percentage,
            (total_rows - rows_with_indicator) as missing_rows
        FROM stats
    $sql$, v_table_name) USING v_indicator_key;
END;
$$;

-- =====================================================
-- COMMENTS AND USAGE EXAMPLES
-- =====================================================
/*
-- Calculate daily percentage change for all symbols
SELECT * FROM calculate_percentage_change('daily');

-- Calculate weekly percentage change for specific symbol
SELECT * FROM calculate_percentage_change_for_symbol('RELIANCE', 'weekly');

-- Check coverage of daily percentage change indicators
SELECT * FROM check_percentage_change_coverage('daily');

-- Calculate monthly percentage change with smaller batch size
SELECT * FROM calculate_percentage_change('monthly', NULL, 500);
*/