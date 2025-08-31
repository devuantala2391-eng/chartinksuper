-- =====================================================
-- SUPERTREND INDICATOR CALCULATION STORED PROCEDURE
-- =====================================================
-- Calculates SuperTrend with direction for all symbols
-- Stores values with 2 decimal precision
-- Direction: 1 = uptrend (green/buy), 0 = downtrend (red/sell)
-- =====================================================

-- Function to format decimal parameters for indicator keys
CREATE OR REPLACE FUNCTION format_decimal_param(value NUMERIC) 
RETURNS TEXT AS $$
BEGIN
    IF value = FLOOR(value) THEN
        -- Whole number
        RETURN FLOOR(value)::TEXT;
    ELSE
        -- Decimal - replace . with 'dot'
        RETURN REPLACE(value::TEXT, '.', 'dot');
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- SUPERTREND CALCULATION FOR SINGLE SYMBOL
-- =====================================================
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
    supertrend_bands AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            timestamp,
            close,
            atr,
            -- Calculate basic bands
            ((high + low) / 2) + (p_multiplier * atr) as upper_band,
            ((high + low) / 2) - (p_multiplier * atr) as lower_band
        FROM atr_values
    ),
    supertrend_calc AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            timestamp,
            close,
            upper_band,
            lower_band,
            -- Determine trend direction using recursive logic
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                WHEN close > upper_band THEN lower_band
                WHEN close < lower_band THEN upper_band
                ELSE 
                    -- Continue previous trend
                    LAG(
                        CASE 
                            WHEN close > upper_band THEN lower_band
                            WHEN close < lower_band THEN upper_band
                            ELSE NULL
                        END, 1
                    ) OVER (ORDER BY candle_sequence_number)
            END as supertrend_value,
            -- Direction: 1 for uptrend, 0 for downtrend
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                WHEN close > upper_band THEN 1
                WHEN close < lower_band THEN 0
                ELSE 
                    -- Continue previous direction
                    LAG(
                        CASE 
                            WHEN close > upper_band THEN 1
                            WHEN close < lower_band THEN 0
                            ELSE NULL
                        END, 1
                    ) OVER (ORDER BY candle_sequence_number)
            END as direction
        FROM supertrend_bands
    ),
    -- Refine SuperTrend with proper trend continuation
    refined_supertrend AS (
        SELECT 
            s1.candle_key_id,
            s1.candle_sequence_number,
            -- Round SuperTrend value to 2 decimal places
            CASE 
                WHEN s1.candle_sequence_number < p_period THEN NULL
                ELSE ROUND(
                    COALESCE(
                        s1.supertrend_value,
                        -- If no value, use the appropriate band based on last known direction
                        CASE 
                            WHEN COALESCE(
                                (SELECT direction FROM supertrend_calc s2 
                                 WHERE s2.candle_sequence_number < s1.candle_sequence_number 
                                 AND s2.direction IS NOT NULL 
                                 ORDER BY s2.candle_sequence_number DESC LIMIT 1), 
                                1
                            ) = 1 THEN s1.lower_band
                            ELSE s1.upper_band
                        END
                    ), 2
                )
            END as supertrend_final,
            -- Direction with proper continuation
            CASE 
                WHEN s1.candle_sequence_number < p_period THEN NULL
                ELSE COALESCE(
                    s1.direction,
                    -- If no direction, use the last known direction
                    (SELECT direction FROM supertrend_calc s2 
                     WHERE s2.candle_sequence_number < s1.candle_sequence_number 
                     AND s2.direction IS NOT NULL 
                     ORDER BY s2.candle_sequence_number DESC LIMIT 1)
                )
            END as direction_final
        FROM supertrend_calc s1
    )
    -- Update the indicators JSONB column (only rows that don't have the indicator)
    UPDATE daily_candles dc
    SET indicators = 
        CASE 
            WHEN rs.supertrend_final IS NULL AND rs.direction_final IS NULL THEN
                COALESCE(dc.indicators, '{}'::jsonb)
            ELSE
                COALESCE(dc.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, rs.supertrend_final,
                    v_direction_key, rs.direction_final
                )
        END,
        updated_at = CURRENT_TIMESTAMP
    FROM refined_supertrend rs
    WHERE dc.candle_key_id = rs.candle_key_id
    AND (rs.supertrend_final IS NOT NULL OR rs.direction_final IS NOT NULL)
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

-- =====================================================
-- BATCH SUPERTREND CALCULATION FOR ALL SYMBOLS
-- =====================================================
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
    v_end_time TIMESTAMP;
    v_symbol_record RECORD;
    v_result RECORD;
    v_success_count INTEGER := 0;
    v_fail_count INTEGER := 0;
    v_skip_count INTEGER := 0;
    v_total_count INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
BEGIN
    -- Generate indicator keys with decimal support
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    
    RAISE NOTICE 'Starting batch SuperTrend calculation: % and %', v_indicator_key, v_direction_key;
    RAISE NOTICE 'Parameters: period=%, multiplier=%, force_recalculate=%', p_period, p_multiplier, p_force_recalculate;
    
    -- Process each symbol
    FOR v_symbol_record IN 
        SELECT DISTINCT symbol 
        FROM daily_candles 
        ORDER BY symbol
    LOOP
        v_total_count := v_total_count + 1;
        
        -- Calculate SuperTrend for this symbol
        SELECT * INTO v_result 
        FROM calculate_supertrend_for_symbol(v_symbol_record.symbol, p_period, p_multiplier, p_force_recalculate);
        
        IF v_result.status = 'ALREADY_EXISTS' THEN
            v_skip_count := v_skip_count + 1;
        ELSIF v_result.status = 'SUCCESS' AND v_result.updated_rows > 0 THEN
            v_success_count := v_success_count + 1;
        ELSIF v_result.status = 'SUCCESS' AND v_result.updated_rows = 0 THEN
            -- No rows to update (might be empty symbol)
            v_skip_count := v_skip_count + 1;
        ELSE
            v_fail_count := v_fail_count + 1;
            RAISE NOTICE 'Failed for symbol %: %', v_symbol_record.symbol, v_result.status;
        END IF;
        
        -- Log progress every 100 symbols
        IF v_total_count % 100 = 0 THEN
            RAISE NOTICE 'Progress: % symbols processed (% success, % skipped, % failed)', 
                v_total_count, v_success_count, v_skip_count, v_fail_count;
        END IF;
    END LOOP;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Batch SuperTrend calculation complete:';
    RAISE NOTICE '  Total symbols: %', v_total_count;
    RAISE NOTICE '  Successful: % (new calculations)', v_success_count;
    RAISE NOTICE '  Skipped: % (already exists)', v_skip_count;
    RAISE NOTICE '  Failed: %', v_fail_count;
    RAISE NOTICE '  Execution time: % ms', EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    RAISE NOTICE '  Indicators: % (values with 2 decimal precision), % (direction: 1=up, 0=down)', 
        v_indicator_key, v_direction_key;
    
    RETURN QUERY SELECT 
        v_total_count,
        v_success_count,
        v_fail_count,
        v_skip_count,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        v_indicator_key,
        v_direction_key,
        CASE 
            WHEN v_fail_count = 0 AND v_success_count > 0 THEN 'SUCCESS'::TEXT
            WHEN v_fail_count = 0 AND v_skip_count = v_total_count THEN 'ALL_ALREADY_EXISTS'::TEXT
            WHEN v_success_count > 0 THEN 'PARTIAL_SUCCESS'::TEXT
            ELSE 'FAILED'::TEXT
        END;
END;
$$;

-- =====================================================
-- CONVENIENCE FUNCTION TO CHECK SUPERTREND STATUS
-- =====================================================
CREATE OR REPLACE FUNCTION check_supertrend_coverage(
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 3.0
)
RETURNS TABLE(
    total_rows BIGINT,
    rows_with_supertrend BIGINT,
    rows_with_direction BIGINT,
    coverage_percentage NUMERIC,
    missing_rows BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_indicator_key TEXT;
    v_direction_key TEXT;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    
    RETURN QUERY
    SELECT 
        COUNT(*) as total_rows,
        COUNT(CASE WHEN indicators ? v_indicator_key AND (indicators->v_indicator_key) IS NOT NULL THEN 1 END) as rows_with_supertrend,
        COUNT(CASE WHEN indicators ? v_direction_key AND (indicators->v_direction_key) IS NOT NULL THEN 1 END) as rows_with_direction,
        CASE 
            WHEN COUNT(*) > 0 THEN 
                ROUND((COUNT(CASE WHEN indicators ? v_indicator_key THEN 1 END)::numeric / COUNT(*)::numeric * 100), 2)
            ELSE 0
        END as coverage_percentage,
        COUNT(*) - COUNT(CASE WHEN indicators ? v_indicator_key THEN 1 END) as missing_rows
    FROM daily_candles;
END;
$$;

-- =====================================================
-- DYNAMIC INDICATOR HANDLER (Called from Python)
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_dynamic_supertrend(
    p_indicator_name TEXT  -- e.g., 'supertrend with various parameters'
)
RETURNS TABLE(
    success BOOLEAN,
    message TEXT,
    indicator_key TEXT,
    direction_key TEXT,
    symbols_processed INTEGER,
    symbols_updated INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_period INTEGER;
    v_multiplier NUMERIC;
    v_multiplier_str TEXT;
    v_parts TEXT[];
    v_result RECORD;
BEGIN
    -- Parse the indicator name to extract parameters
    -- Format: supertrend_<period>_<multiplier>
    v_parts := string_to_array(p_indicator_name, '_');
    
    IF array_length(v_parts, 1) != 3 OR v_parts[1] != 'supertrend' THEN
        RETURN QUERY SELECT 
            FALSE,
            'Invalid indicator name format. Expected: supertrend_<period>_<multiplier>',
            NULL::TEXT,
            NULL::TEXT,
            0,
            0;
        RETURN;
    END IF;
    
    -- Extract period (handle both integer and float strings)
    BEGIN
        -- Convert to numeric first, then to integer to handle "10.0" format
        v_period := ROUND(v_parts[2]::NUMERIC)::INTEGER;
    EXCEPTION
        WHEN OTHERS THEN
            RETURN QUERY SELECT 
                FALSE,
                'Invalid period parameter: ' || v_parts[2],
                NULL::TEXT,
                NULL::TEXT,
                0,
                0;
            RETURN;
    END;
    
    -- Extract multiplier (handle 'dot' notation for decimals)
    v_multiplier_str := v_parts[3];
    BEGIN
        IF position('dot' in v_multiplier_str) > 0 THEN
            -- Convert 'dot' back to decimal point
            v_multiplier := REPLACE(v_multiplier_str, 'dot', '.')::NUMERIC;
        ELSE
            v_multiplier := v_multiplier_str::NUMERIC;
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            RETURN QUERY SELECT 
                FALSE,
                'Invalid multiplier parameter: ' || v_multiplier_str,
                NULL::TEXT,
                NULL::TEXT,
                0,
                0;
            RETURN;
    END;
    
    RAISE NOTICE 'Parsed SuperTrend request: period=%, multiplier=%', v_period, v_multiplier;
    
    -- Calculate SuperTrend for all symbols
    SELECT * INTO v_result 
    FROM calculate_supertrend_for_all_symbols(v_period, v_multiplier, FALSE);
    
    -- Return results
    RETURN QUERY SELECT 
        (v_result.status IN ('SUCCESS', 'ALL_ALREADY_EXISTS', 'PARTIAL_SUCCESS'))::BOOLEAN as success,
        format('Processed %s symbols: %s new, %s skipped, %s failed', 
            v_result.total_symbols, 
            v_result.successful_symbols,
            v_result.skipped_symbols,
            v_result.failed_symbols) as message,
        v_result.indicator_key,
        v_result.direction_key,
        v_result.total_symbols as symbols_processed,
        v_result.successful_symbols as symbols_updated;
END;
$$;

-- =====================================================
-- GRANT PERMISSIONS
-- =====================================================
GRANT EXECUTE ON FUNCTION format_decimal_param(NUMERIC) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_supertrend_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_supertrend_for_all_symbols(INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION check_supertrend_coverage(INTEGER, NUMERIC) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_dynamic_supertrend(TEXT) TO PUBLIC;