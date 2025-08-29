-- =====================================================
-- Monthly Percentage Change Calculation Procedures
-- =====================================================
-- This implements dynamic sliding window approach for monthly percentage
-- Each day compares its close to the previous month's final close

-- Drop existing function to avoid signature conflicts
DROP FUNCTION IF EXISTS calculate_monthly_percentage_change(TEXT, INTEGER);
DROP FUNCTION IF EXISTS calculate_monthly_percentage_change_for_symbol(TEXT);

-- Function to calculate monthly percentage change for a single symbol
-- Returns status information to match the service expected signature  
CREATE OR REPLACE FUNCTION calculate_monthly_percentage_change_for_symbol(
    p_symbol TEXT
) RETURNS TABLE (
    updated_rows INTEGER,
    status TEXT
) AS $$
DECLARE
    v_updated_rows INTEGER := 0;
BEGIN
    -- Calculate monthly percentage change using dynamic sliding window approach
    -- Each day compares its OWN close to the previous month's final close
    WITH monthly_pct_data AS (
        SELECT 
            dc.candle_key_id,
            dc.close as current_day_close,
            mc_prev.close as prev_month_final_close,
            CASE 
                WHEN mc_prev.close IS NOT NULL AND mc_prev.close > 0 THEN
                    ROUND(((dc.close - mc_prev.close) / mc_prev.close * 100)::numeric, 4)
                ELSE 
                    NULL
            END as monthly_pct_change
        FROM daily_candles dc
        -- Join with current month's monthly candle to get month info
        LEFT JOIN monthly_candles mc_current 
            ON dc.monthly_candle_key_id = mc_current.monthly_candle_key_id
        -- Join with previous month's monthly candle to get previous month's final close
        -- We need to find the previous month based on the sequence number, not key format
        LEFT JOIN monthly_candles mc_prev 
            ON mc_prev.symbol = dc.symbol 
            AND mc_prev.month_sequence_number = (mc_current.month_sequence_number - 1)
        WHERE dc.symbol = p_symbol
          AND mc_current.month_sequence_number > 1  -- Skip first month since no previous month
    )
    UPDATE daily_candles AS target_table
    SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object('monthly_pctchg', mpd.monthly_pct_change),
        updated_at = CURRENT_TIMESTAMP
    FROM monthly_pct_data mpd
    WHERE target_table.candle_key_id = mpd.candle_key_id
      AND mpd.monthly_pct_change IS NOT NULL
      AND (
          -- Only update if indicator doesn't exist or is null
          NOT (target_table.indicators ? 'monthly_pctchg') OR 
          (target_table.indicators->'monthly_pctchg') IS NULL OR
          (target_table.indicators->'monthly_pctchg') = 'null'::jsonb
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

-- Main interface function to match the service expected signature
-- This function updates the indicators column in daily_candles with monthly percentage change
CREATE OR REPLACE FUNCTION calculate_monthly_percentage_change(
    p_symbol_filter TEXT DEFAULT NULL,  -- Optional symbol filter for single stock
    p_batch_size INTEGER DEFAULT 1000   -- Not used for monthly, kept for compatibility
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
    
    RAISE NOTICE 'Starting monthly percentage change calculation';
    
    -- Process each symbol separately for better performance and memory management
    FOR symbol_rec IN symbol_cursor LOOP
        -- Calculate monthly percentage change using dynamic sliding window approach
        -- Each day compares its close to the previous month's final close
        WITH monthly_pct_data AS (
            SELECT 
                dc.candle_key_id,
                dc.close as current_day_close,
                mc_prev.close as prev_month_final_close,
                CASE 
                    WHEN mc_prev.close IS NOT NULL AND mc_prev.close > 0 THEN
                        ROUND(((dc.close - mc_prev.close) / mc_prev.close * 100)::numeric, 4)
                    ELSE 
                        NULL
                END as monthly_pct_change
            FROM daily_candles dc
            -- Join with current month's monthly candle to get month info
            LEFT JOIN monthly_candles mc_current 
                ON dc.monthly_candle_key_id = mc_current.monthly_candle_key_id
            -- Join with previous month's monthly candle to get previous month's final close
            -- We need to find the previous month based on the sequence number, not key format
            LEFT JOIN monthly_candles mc_prev 
                ON mc_prev.symbol = dc.symbol 
                AND mc_prev.month_sequence_number = (mc_current.month_sequence_number - 1)
            WHERE dc.symbol = symbol_rec.symbol
              AND mc_current.month_sequence_number > 1  -- Skip first month since no previous month
        )
        UPDATE daily_candles AS target_table
        SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object('monthly_pctchg', mpd.monthly_pct_change),
            updated_at = CURRENT_TIMESTAMP
        FROM monthly_pct_data mpd
        WHERE target_table.candle_key_id = mpd.candle_key_id
          AND mpd.monthly_pct_change IS NOT NULL
          AND (
              -- Only update if indicator doesn't exist or is null
              NOT (target_table.indicators ? 'monthly_pctchg') OR 
              (target_table.indicators->'monthly_pctchg') IS NULL OR
              (target_table.indicators->'monthly_pctchg') = 'null'::jsonb
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
    RAISE NOTICE 'Completed monthly percentage change calculation: % symbols processed, % rows updated in % ms',
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
        RAISE NOTICE 'Error in calculate_monthly_percentage_change: %', SQLERRM;
        v_end_time := clock_timestamp();
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;