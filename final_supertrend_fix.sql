-- Final fix for SuperTrend with proper direction calculation
DROP FUNCTION IF EXISTS calculate_supertrend_for_symbol CASCADE;

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
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_end_time TIMESTAMP;
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_existing_count INTEGER;
    v_total_count INTEGER;
BEGIN
    -- Generate indicator keys with decimal support
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    
    RAISE NOTICE 'Processing % and % for symbol: %', v_indicator_key, v_direction_key, p_symbol;
    
    -- Check if indicator already exists (unless force recalculate)
    IF NOT p_force_recalculate THEN
        SELECT COUNT(*) INTO v_total_count
        FROM daily_candles
        WHERE symbol = p_symbol;
        
        SELECT COUNT(*) INTO v_existing_count
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_indicator_key
        AND (indicators->v_indicator_key) IS NOT NULL
        AND indicators ? v_direction_key
        AND (indicators->v_direction_key) IS NOT NULL
        AND (indicators->v_direction_key)::text != 'null';
        
        -- If all rows already have the indicator, skip calculation
        IF v_existing_count = v_total_count AND v_total_count > 0 THEN
            RAISE NOTICE 'Indicator % already exists for all % rows of symbol %, skipping calculation', 
                v_indicator_key, v_total_count, p_symbol;
            
            RETURN QUERY SELECT 
                0,
                0,
                'ALREADY_EXISTS'::TEXT,
                v_indicator_key,
                v_direction_key;
            RETURN;
        ELSIF v_existing_count > 0 THEN
            RAISE NOTICE 'Indicator % exists for % out of % rows, will calculate missing rows only', 
                v_indicator_key, v_existing_count, v_total_count;
        END IF;
    END IF;
    
    -- Create temporary table with SuperTrend calculations
    CREATE TEMP TABLE temp_supertrend AS
    WITH atr_calc AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            high,
            low,
            close,
            -- Calculate True Range
            GREATEST(
                high - low,
                ABS(high - LAG(close, 1) OVER (ORDER BY candle_sequence_number)),
                ABS(low - LAG(close, 1) OVER (ORDER BY candle_sequence_number))
            ) as true_range
        FROM daily_candles
        WHERE symbol = p_symbol
    ),
    atr_values AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            high,
            low,
            close,
            -- Calculate ATR
            AVG(true_range) OVER (
                ORDER BY candle_sequence_number 
                ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
            ) as atr
        FROM atr_calc
    ),
    basic_bands AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                ELSE ROUND(((high + low) / 2) - (p_multiplier * atr), 2)
            END as lower_band,
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                ELSE ROUND(((high + low) / 2) + (p_multiplier * atr), 2)
            END as upper_band
        FROM atr_values
    )
    SELECT 
        candle_key_id,
        close,
        lower_band,
        upper_band,
        -- Simple SuperTrend: use lower band in uptrend, upper band in downtrend
        -- For initial determination, check if price is above or below middle
        CASE 
            WHEN candle_sequence_number < p_period THEN NULL
            WHEN close > ((upper_band + lower_band) / 2) THEN lower_band
            ELSE upper_band
        END as supertrend_value
    FROM basic_bands
    ORDER BY candle_sequence_number;
    
    -- Update daily_candles with SuperTrend and direction
    UPDATE daily_candles dc
    SET indicators = 
        COALESCE(dc.indicators, '{}'::jsonb) || 
        jsonb_build_object(
            v_indicator_key, ts.supertrend_value,
            v_direction_key, 
            CASE 
                WHEN ts.supertrend_value IS NULL THEN NULL
                WHEN dc.close > ts.supertrend_value THEN 1  -- Uptrend
                ELSE 0  -- Downtrend
            END
        ),
        updated_at = CURRENT_TIMESTAMP
    FROM temp_supertrend ts
    WHERE dc.candle_key_id = ts.candle_key_id
    AND ts.supertrend_value IS NOT NULL
    AND (
        p_force_recalculate OR
        NOT (dc.indicators ? v_indicator_key) OR 
        (dc.indicators->v_indicator_key) IS NULL OR
        NOT (dc.indicators ? v_direction_key) OR
        (dc.indicators->v_direction_key) IS NULL OR
        (dc.indicators->v_direction_key)::text = 'null'
    );
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    -- Clean up temp table
    DROP TABLE IF EXISTS temp_supertrend;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed SuperTrend calculation for %: % rows updated in % ms',
        p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key,
        v_direction_key;
        
EXCEPTION
    WHEN OTHERS THEN
        -- Clean up temp table on error
        DROP TABLE IF EXISTS temp_supertrend;
        
        RAISE NOTICE 'Error in calculate_supertrend_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT 
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;

GRANT EXECUTE ON FUNCTION calculate_supertrend_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;