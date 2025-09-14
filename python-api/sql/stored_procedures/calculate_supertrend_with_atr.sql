-- =====================================================
-- SUPERTREND CALCULATION USING PRE-CALCULATED ATR
-- =====================================================
-- This version uses pre-calculated ATR values for efficiency
-- Falls back to calculating ATR if not available
-- =====================================================

-- Helper function for formatting multiplier values in keys
CREATE OR REPLACE FUNCTION format_decimal_param(value NUMERIC) 
RETURNS TEXT AS $$
BEGIN
    IF value = FLOOR(value) THEN
        RETURN FLOOR(value)::TEXT;
    ELSE
        RETURN REPLACE(value::TEXT, '.', 'dot');
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Main SuperTrend calculation using pre-calculated ATR
CREATE OR REPLACE FUNCTION calculate_supertrend_with_atr(
    p_symbol TEXT,
    p_period INTEGER,
    p_multiplier NUMERIC,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    direction_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_atr_key TEXT;
    rec RECORD;
    v_prev_final_upper NUMERIC;
    v_prev_final_lower NUMERIC;
    v_prev_trend INTEGER;
    v_supertrend NUMERIC;
    v_direction INTEGER;
    v_atr_calculated BOOLEAN := FALSE;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'atr_' || p_period;
    
    RAISE NOTICE 'Processing SuperTrend for symbol: % (will use ATR key: %)', p_symbol, v_atr_key;
    
    -- First, ensure ATR is calculated for this symbol
    PERFORM 1 FROM daily_candles 
    WHERE symbol = p_symbol 
    AND indicators ? v_atr_key 
    LIMIT 1;
    
    IF NOT FOUND THEN
        RAISE NOTICE 'ATR not found, calculating ATR(%) for symbol %', p_period, p_symbol;
        -- Calculate ATR first
        PERFORM * FROM calculate_atr(p_period, p_symbol, NULL);
        v_atr_calculated := TRUE;
    END IF;
    
    -- Create temp table with ATR values
    CREATE TEMP TABLE temp_supertrend_calc AS
    SELECT 
        candle_key_id,
        candle_sequence_number,
        high,
        low,
        close,
        -- Use pre-calculated ATR from indicators
        (indicators->v_atr_key)::numeric as atr,
        ROW_NUMBER() OVER (ORDER BY candle_sequence_number) as rn
    FROM daily_candles
    WHERE symbol = p_symbol
    ORDER BY candle_sequence_number;
    
    -- Initialize variables
    v_prev_final_upper := NULL;
    v_prev_final_lower := NULL;
    v_prev_trend := NULL;
    
    -- Process each candle sequentially for proper SuperTrend calculation
    FOR rec IN 
        SELECT * FROM temp_supertrend_calc 
        WHERE atr IS NOT NULL  -- Only process candles with ATR
        ORDER BY candle_sequence_number
    LOOP
        -- Calculate basic bands
        DECLARE
            v_hl_avg NUMERIC := (rec.high + rec.low) / 2;
            v_basic_upper NUMERIC := v_hl_avg + (p_multiplier * rec.atr);
            v_basic_lower NUMERIC := v_hl_avg - (p_multiplier * rec.atr);
            v_final_upper NUMERIC;
            v_final_lower NUMERIC;
        BEGIN
            -- Calculate final bands with SuperTrend rules
            -- Lower band should not decrease in uptrend
            IF v_prev_final_lower IS NULL OR v_basic_lower > v_prev_final_lower THEN
                v_final_lower := v_basic_lower;
            ELSE
                v_final_lower := v_prev_final_lower;
            END IF;
            
            -- Upper band should not increase in downtrend  
            IF v_prev_final_upper IS NULL OR v_basic_upper < v_prev_final_upper THEN
                v_final_upper := v_basic_upper;
            ELSE
                v_final_upper := v_prev_final_upper;
            END IF;
            
            -- Determine trend
            IF v_prev_trend IS NULL THEN
                -- Initial trend based on close position
                IF rec.close <= v_final_upper THEN
                    v_direction := 0; -- Downtrend
                ELSE
                    v_direction := 1; -- Uptrend
                END IF;
            ELSE
                -- Trend changes
                IF v_prev_trend = 1 THEN -- Was in uptrend
                    IF rec.close <= v_final_lower THEN
                        v_direction := 0; -- Switch to downtrend
                    ELSE
                        v_direction := 1; -- Stay in uptrend
                    END IF;
                ELSE -- Was in downtrend
                    IF rec.close >= v_final_upper THEN
                        v_direction := 1; -- Switch to uptrend
                    ELSE
                        v_direction := 0; -- Stay in downtrend
                    END IF;
                END IF;
            END IF;
            
            -- Set SuperTrend value based on trend
            IF v_direction = 1 THEN
                v_supertrend := ROUND(v_final_lower::numeric, 2);
            ELSE
                v_supertrend := ROUND(v_final_upper::numeric, 2);
            END IF;
            
            -- Update the candle
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, v_supertrend,
                    v_direction_key, v_direction
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = rec.candle_key_id
            AND (
                p_force_recalculate OR
                NOT (indicators ? v_indicator_key) OR 
                (indicators->v_indicator_key) IS NULL
            );
            
            GET DIAGNOSTICS v_updated_rows = v_updated_rows + ROW_COUNT;
            
            -- Update previous values for next iteration
            v_prev_final_upper := v_final_upper;
            v_prev_final_lower := v_final_lower;
            v_prev_trend := v_direction;
        END;
    END LOOP;
    
    -- Clean up
    DROP TABLE temp_supertrend_calc;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        CASE 
            WHEN v_atr_calculated THEN 'SUCCESS_WITH_ATR_CALC'
            ELSE 'SUCCESS'
        END::TEXT,
        v_indicator_key,
        v_direction_key;
        
EXCEPTION
    WHEN OTHERS THEN
        -- Clean up on error
        DROP TABLE IF EXISTS temp_supertrend_calc;
        
        RETURN QUERY SELECT 
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;

-- Wrapper function that ensures ATR is calculated first
CREATE OR REPLACE FUNCTION calculate_supertrend_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
    p_multiplier NUMERIC,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    direction_key TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Use the new function that leverages pre-calculated ATR
    RETURN QUERY 
    SELECT * FROM calculate_supertrend_with_atr(p_symbol, p_period, p_multiplier, p_force_recalculate);
END;
$$;

-- Batch calculation function
CREATE OR REPLACE FUNCTION calculate_supertrend_for_all_symbols(
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 3.0,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    total_symbols INTEGER,
    successful_symbols INTEGER,
    failed_symbols INTEGER,
    skipped_symbols INTEGER,
    total_execution_time_ms INTEGER,
    indicator_key TEXT,
    direction_key TEXT,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_symbol_record RECORD;
    v_result RECORD;
    v_success_count INTEGER := 0;
    v_fail_count INTEGER := 0;
    v_skip_count INTEGER := 0;
    v_total_count INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
BEGIN
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    
    RAISE NOTICE 'Starting batch SuperTrend calculation with ATR: % and %', v_indicator_key, v_direction_key;
    
    -- First calculate ATR for all symbols
    RAISE NOTICE 'Pre-calculating ATR(%) for all symbols...', p_period;
    PERFORM * FROM calculate_atr(p_period, NULL, NULL);
    
    FOR v_symbol_record IN 
        SELECT DISTINCT symbol 
        FROM daily_candles 
        ORDER BY symbol
    LOOP
        v_total_count := v_total_count + 1;
        
        SELECT * INTO v_result 
        FROM calculate_supertrend_with_atr(v_symbol_record.symbol, p_period, p_multiplier, p_force_recalculate);
        
        IF v_result.status LIKE 'SUCCESS%' AND v_result.updated_rows > 0 THEN
            v_success_count := v_success_count + 1;
        ELSIF v_result.status LIKE 'SUCCESS%' AND v_result.updated_rows = 0 THEN
            v_skip_count := v_skip_count + 1;
        ELSE
            v_fail_count := v_fail_count + 1;
            RAISE NOTICE 'Failed for symbol %: %', v_symbol_record.symbol, v_result.status;
        END IF;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_total_count,
        v_success_count,
        v_fail_count,
        v_skip_count,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        v_indicator_key,
        v_direction_key,
        CASE 
            WHEN v_fail_count = 0 THEN 'SUCCESS'::TEXT
            ELSE 'PARTIAL_SUCCESS'::TEXT
        END;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_supertrend_with_atr(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_supertrend_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_supertrend_for_all_symbols(INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;