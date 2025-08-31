-- =====================================================
-- FIXED PERCENTAGE CHANGE CALCULATION STORED PROCEDURE
-- =====================================================
-- This procedure calculates percentage change indicators
-- for all timeframes (daily, weekly, monthly) with proper
-- column name handling for each timeframe
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_percentage_change_fixed(
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
    v_key_column TEXT;
    v_sequence_column TEXT;
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
    
    -- Set table name, key column, and indicator key based on timeframe
    IF p_timeframe = 'daily' THEN
        v_table_name := 'daily_candles';
        v_key_column := 'candle_key_id';
        v_sequence_column := 'candle_sequence_number';
        v_indicator_key := 'daily_pctchg';
    ELSIF p_timeframe = 'weekly' THEN
        v_table_name := 'weekly_candles';
        v_key_column := 'weekly_candle_key_id';
        v_sequence_column := 'week_sequence_number';
        v_indicator_key := 'weekly_pctchg';
    ELSIF p_timeframe = 'monthly' THEN
        -- Monthly percentage is calculated from daily data, not monthly_candles
        v_table_name := 'daily_candles';
        v_key_column := 'candle_key_id';
        v_sequence_column := 'candle_sequence_number';
        v_indicator_key := 'monthly_pctchg';
    END IF;
    
    -- Log start of calculation
    RAISE NOTICE 'Starting % percentage change calculation for table % with key column %', 
        p_timeframe, v_table_name, v_key_column;
    
    -- Get list of symbols based on the target table
    IF p_timeframe = 'weekly' THEN
        -- For weekly, get symbols from weekly_candles table
        FOR rec IN 
            SELECT DISTINCT symbol FROM weekly_candles 
            WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
            ORDER BY symbol
        LOOP
            -- Calculate weekly percentage change: compare with previous week
            EXECUTE format($sql$
                WITH ranked_candles AS (
                    SELECT 
                        %I,
                        symbol,
                        %I,
                        close,
                        indicators,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY %I) as rn,
                        LAG(close, 1) OVER (PARTITION BY symbol ORDER BY %I) as prev_close
                    FROM %I
                    WHERE symbol = $1
                ),
                calculated AS (
                    SELECT 
                        %I,
                        symbol,
                        %I,
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
                WHERE target_table.%I = calculated.%I
                  AND calculated.%I > 0  -- Skip first candle for percentage calculation
                  AND (
                      -- Only update if indicator doesn't exist or is null
                      NOT (target_table.indicators ? $2) OR 
                      (target_table.indicators->$2) IS NULL OR
                      (target_table.indicators->$2) = 'null'::jsonb
                  )
            $sql$, 
                v_key_column, v_sequence_column, v_sequence_column, v_sequence_column, v_table_name,
                v_key_column, v_sequence_column, v_table_name, v_key_column, v_key_column, v_sequence_column)
            USING rec.symbol, v_indicator_key;
            
            -- Get count of updated rows for this symbol
            GET DIAGNOSTICS v_batch_count = ROW_COUNT;
            v_updated_rows := v_updated_rows + v_batch_count;
            v_processed_symbols := v_processed_symbols + 1;
        END LOOP;
        
    ELSIF p_timeframe = 'monthly' THEN
        -- Monthly percentage change: compare with close price ~30 trading days ago (using daily data)
        FOR rec IN symbol_cursor LOOP
            EXECUTE format($sql$
                WITH ranked_candles AS (
                    SELECT 
                        %I,
                        symbol,
                        %I,
                        timestamp,
                        close,
                        indicators,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY %I) as rn,
                        LAG(close, 30) OVER (PARTITION BY symbol ORDER BY %I) as prev_month_close
                    FROM %I
                    WHERE symbol = $1
                ),
                calculated AS (
                    SELECT 
                        %I,
                        symbol,
                        CASE 
                            WHEN prev_month_close IS NOT NULL AND prev_month_close != 0 THEN
                                ROUND(((close - prev_month_close) / prev_month_close * 100)::numeric, 4)
                            ELSE 
                                NULL
                        END as pct_change,
                        indicators
                    FROM ranked_candles
                    WHERE rn > 30  -- Only calculate for rows with valid comparison data
                )
                UPDATE %I AS target_table
                SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object($2, calculated.pct_change),
                    updated_at = CURRENT_TIMESTAMP
                FROM calculated
                WHERE target_table.%I = calculated.%I
                  AND calculated.pct_change IS NOT NULL
                  AND (
                      -- Only update if indicator doesn't exist or is null
                      NOT (target_table.indicators ? $2) OR 
                      (target_table.indicators->$2) IS NULL OR
                      (target_table.indicators->$2) = 'null'::jsonb
                  )
            $sql$, 
                v_key_column, v_sequence_column, v_sequence_column, v_sequence_column, v_table_name,
                v_key_column, v_table_name, v_key_column, v_key_column)
            USING rec.symbol, v_indicator_key;
            
            -- Get count of updated rows for this symbol
            GET DIAGNOSTICS v_batch_count = ROW_COUNT;
            v_updated_rows := v_updated_rows + v_batch_count;
            v_processed_symbols := v_processed_symbols + 1;
        END LOOP;
        
    ELSE
        -- Daily percentage change: compare with previous day
        FOR rec IN symbol_cursor LOOP
            EXECUTE format($sql$
                WITH ranked_candles AS (
                    SELECT 
                        %I,
                        symbol,
                        %I,
                        timestamp,
                        close,
                        indicators,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY %I) as rn,
                        LAG(close, 1) OVER (PARTITION BY symbol ORDER BY %I) as prev_close
                    FROM %I
                    WHERE symbol = $1
                ),
                calculated AS (
                    SELECT 
                        %I,
                        symbol,
                        %I,
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
                WHERE target_table.%I = calculated.%I
                  AND calculated.%I > 0  -- Skip first candle (sequence 0) since it will always be null
                  AND (
                      -- Only update if indicator doesn't exist or is null
                      NOT (target_table.indicators ? $2) OR 
                      (target_table.indicators->$2) IS NULL OR
                      (target_table.indicators->$2) = 'null'::jsonb
                  )
            $sql$, 
                v_key_column, v_sequence_column, v_sequence_column, v_sequence_column, v_table_name,
                v_key_column, v_sequence_column, v_table_name, v_key_column, v_key_column, v_sequence_column)
            USING rec.symbol, v_indicator_key;
            
            -- Get count of updated rows for this symbol
            GET DIAGNOSTICS v_batch_count = ROW_COUNT;
            v_updated_rows := v_updated_rows + v_batch_count;
            v_processed_symbols := v_processed_symbols + 1;
        END LOOP;
    END IF;
    
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
        RAISE NOTICE 'Error in calculate_percentage_change_fixed: %', SQLERRM;
        v_end_time := clock_timestamp();
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- Helper function for single symbol
CREATE OR REPLACE FUNCTION calculate_percentage_change_fixed_for_symbol(
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
    SELECT * INTO result FROM calculate_percentage_change_fixed(p_timeframe, p_symbol, 1000);
    
    RETURN QUERY SELECT result.updated_rows, result.status;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_percentage_change_fixed(TEXT, TEXT, INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_percentage_change_fixed_for_symbol(TEXT, TEXT) TO PUBLIC;