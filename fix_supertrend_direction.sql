-- Fix SuperTrend direction calculation
-- The issue is that the direction logic needs to be computed differently

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
        AND (indicators->v_direction_key) IS NOT NULL;
        
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
    
    -- Calculate SuperTrend with ATR and direction
    WITH atr_calc AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            timestamp,
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
        ORDER BY candle_sequence_number
    ),
    atr_values AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            timestamp,
            high,
            low,
            close,
            -- Calculate ATR using SMA of True Range
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
            timestamp,
            close,
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                ELSE ROUND(((high + low) / 2) + (p_multiplier * atr), 2)
            END as basic_upper_band,
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                ELSE ROUND(((high + low) / 2) - (p_multiplier * atr), 2)
            END as basic_lower_band
        FROM atr_values
    ),
    -- Calculate SuperTrend and Direction using window functions
    supertrend_calculation AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            basic_upper_band,
            basic_lower_band,
            -- Determine SuperTrend value and direction based on close vs bands
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                WHEN close <= basic_lower_band THEN basic_upper_band  -- Downtrend
                WHEN close >= basic_upper_band THEN basic_lower_band   -- Uptrend
                ELSE 
                    -- Continue previous trend
                    CASE 
                        WHEN LAG(close, 1) OVER (ORDER BY candle_sequence_number) <= 
                             LAG(basic_lower_band, 1) OVER (ORDER BY candle_sequence_number) 
                        THEN basic_upper_band  -- Was in downtrend, continue
                        ELSE basic_lower_band   -- Was in uptrend, continue
                    END
            END as supertrend,
            -- Direction: 1 for uptrend (price above ST), 0 for downtrend (price below ST)
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                WHEN close <= basic_lower_band THEN 0  -- Downtrend
                WHEN close >= basic_upper_band THEN 1  -- Uptrend
                ELSE 
                    -- Continue previous direction
                    LAG(
                        CASE 
                            WHEN close <= basic_lower_band THEN 0
                            WHEN close >= basic_upper_band THEN 1
                            ELSE NULL
                        END, 1
                    ) OVER (ORDER BY candle_sequence_number)
            END as direction
        FROM basic_bands
    ),
    -- Fill forward the direction values to handle NULLs
    filled_direction AS (
        SELECT 
            sc.candle_key_id,
            sc.candle_sequence_number,
            sc.close,
            sc.supertrend,
            -- Simple direction calculation based on price vs SuperTrend
            CASE 
                WHEN sc.supertrend IS NULL THEN NULL
                WHEN sc.close > sc.supertrend THEN 1  -- Uptrend
                ELSE 0  -- Downtrend
            END as final_direction
        FROM supertrend_calculation sc
    )
    -- Update the indicators JSONB column (only rows that don't have the indicator)
    UPDATE daily_candles dc
    SET indicators = 
        COALESCE(dc.indicators, '{}'::jsonb) || 
        jsonb_build_object(
            v_indicator_key, fd.supertrend,
            v_direction_key, fd.final_direction
        ),
        updated_at = CURRENT_TIMESTAMP
    FROM filled_direction fd
    WHERE dc.candle_key_id = fd.candle_key_id
    AND fd.supertrend IS NOT NULL
    AND (
        -- Only update if indicator doesn't exist or force recalculate
        p_force_recalculate OR
        NOT (dc.indicators ? v_indicator_key) OR 
        (dc.indicators->v_indicator_key) IS NULL OR
        NOT (dc.indicators ? v_direction_key) OR
        (dc.indicators->v_direction_key) IS NULL
    );
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
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