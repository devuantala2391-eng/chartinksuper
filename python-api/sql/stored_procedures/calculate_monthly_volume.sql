-- =====================================================
-- Monthly Volume Calculation Procedures (Dynamic Sliding Window - Cumulative Type)
-- =====================================================
-- This implements dynamic sliding window approach for monthly volume
-- Each day shows cumulative volume from start of current month up to that day

-- Drop existing function to avoid signature conflicts
DROP FUNCTION IF EXISTS calculate_monthly_volume(TEXT, INTEGER);
DROP FUNCTION IF EXISTS calculate_monthly_volume_for_symbol(TEXT);

-- Function to calculate monthly volume for a single symbol
-- Returns status information to match the service expected signature  
CREATE OR REPLACE FUNCTION calculate_monthly_volume_for_symbol(
    p_symbol TEXT
) RETURNS TABLE (
    updated_rows INTEGER,
    status TEXT
) AS $$
DECLARE
    v_updated_rows INTEGER := 0;
BEGIN
    -- Calculate monthly volume using dynamic sliding window approach (cumulative)
    -- Each day shows cumulative volume from start of current month up to that day
    WITH monthly_volume_data AS (
        SELECT 
            dc.candle_key_id,
            SUM(dc_month.volume) as monthly_volume_cumulative
        FROM daily_candles dc
        -- Join with current month's monthly candle to get month info
        LEFT JOIN monthly_candles mc_current 
            ON dc.monthly_candle_key_id = mc_current.monthly_candle_key_id
        -- Join with all daily candles in the same month that are <= current day
        LEFT JOIN daily_candles dc_month 
            ON dc_month.monthly_candle_key_id = mc_current.monthly_candle_key_id
            AND dc_month.datetime <= dc.datetime  -- Only sum up to current day
            AND dc_month.symbol = dc.symbol
        WHERE dc.symbol = p_symbol
          AND mc_current.month_sequence_number >= 1  -- Include all months (no previous month reference needed)
        GROUP BY dc.candle_key_id
    )
    UPDATE daily_candles AS target_table
    SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object('monthly_volume', mvd.monthly_volume_cumulative),
        updated_at = CURRENT_TIMESTAMP
    FROM monthly_volume_data mvd
    WHERE target_table.candle_key_id = mvd.candle_key_id
      AND mvd.monthly_volume_cumulative IS NOT NULL
      AND (
          -- Only update if indicator doesn't exist or is null
          NOT (target_table.indicators ? 'monthly_volume') OR 
          (target_table.indicators->'monthly_volume') IS NULL OR
          (target_table.indicators->'monthly_volume') = 'null'::jsonb
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
-- This function updates the indicators column in daily_candles with monthly volume
CREATE OR REPLACE FUNCTION calculate_monthly_volume(
    p_symbol_filter TEXT DEFAULT NULL,  -- Optional symbol filter for single stock
    p_batch_size INTEGER DEFAULT 1000   -- Not used for monthly volume, kept for compatibility
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
    
    RAISE NOTICE 'Starting monthly volume calculation';
    
    -- Process each symbol separately for better performance and memory management
    FOR symbol_rec IN symbol_cursor LOOP
        -- Calculate monthly volume using dynamic sliding window approach (cumulative)
        -- Each day shows cumulative volume from start of current month up to that day
        WITH monthly_volume_data AS (
            SELECT 
                dc.candle_key_id,
                SUM(dc_month.volume) as monthly_volume_cumulative
            FROM daily_candles dc
            -- Join with current month's monthly candle to get month info
            LEFT JOIN monthly_candles mc_current 
                ON dc.monthly_candle_key_id = mc_current.monthly_candle_key_id
            -- Join with all daily candles in the same month that are <= current day
            LEFT JOIN daily_candles dc_month 
                ON dc_month.monthly_candle_key_id = mc_current.monthly_candle_key_id
                AND dc_month.datetime <= dc.datetime  -- Only sum up to current day
                AND dc_month.symbol = dc.symbol
            WHERE dc.symbol = symbol_rec.symbol
              AND mc_current.month_sequence_number >= 1  -- Include all months
            GROUP BY dc.candle_key_id
        )
        UPDATE daily_candles AS target_table
        SET indicators = COALESCE(target_table.indicators, '{}'::jsonb) || jsonb_build_object('monthly_volume', mvd.monthly_volume_cumulative),
            updated_at = CURRENT_TIMESTAMP
        FROM monthly_volume_data mvd
        WHERE target_table.candle_key_id = mvd.candle_key_id
          AND mvd.monthly_volume_cumulative IS NOT NULL
          AND (
              -- Only update if indicator doesn't exist or is null
              NOT (target_table.indicators ? 'monthly_volume') OR 
              (target_table.indicators->'monthly_volume') IS NULL OR
              (target_table.indicators->'monthly_volume') = 'null'::jsonb
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
    RAISE NOTICE 'Completed monthly volume calculation: % symbols processed, % rows updated in % ms',
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
        RAISE NOTICE 'Error in calculate_monthly_volume: %', SQLERRM;
        v_end_time := clock_timestamp();
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;