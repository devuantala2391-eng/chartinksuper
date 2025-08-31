-- =====================================================
-- IMPROVED INDICATOR CALCULATIONS
-- =====================================================
-- Fixes EMA and RSI calculations with proper formulas
-- =====================================================

-- =====================================================
-- PROPER EMA CALCULATION FUNCTION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_ema_for_symbol(
    p_symbol TEXT,
    p_period INTEGER
)
RETURNS TABLE(
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
    v_alpha NUMERIC;
    v_indicator_key TEXT;
BEGIN
    -- EMA formula: alpha = 2 / (period + 1)
    v_alpha := 2.0 / (p_period + 1);
    v_indicator_key := 'ema_' || p_period;
    
    RAISE NOTICE 'Calculating EMA(%) for symbol: %, alpha: %', p_period, p_symbol, v_alpha;
    
    -- Create temporary table for EMA calculation
    CREATE TEMP TABLE temp_ema AS
    WITH ema_calc AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            -- For first period values, use SMA
            CASE 
                WHEN candle_sequence_number < p_period THEN NULL
                WHEN candle_sequence_number = p_period THEN 
                    AVG(close) OVER (
                        ORDER BY candle_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    )
                ELSE NULL -- Will be calculated recursively
            END as ema_value
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY candle_sequence_number
    )
    SELECT * FROM ema_calc;
    
    -- Recursive calculation of EMA
    DECLARE
        v_prev_ema NUMERIC;
        v_current_row RECORD;
    BEGIN
        -- Get initial EMA (SMA of first period)
        SELECT ema_value INTO v_prev_ema
        FROM temp_ema
        WHERE candle_sequence_number = p_period;
        
        -- Calculate EMA for remaining rows
        FOR v_current_row IN 
            SELECT * FROM temp_ema 
            WHERE candle_sequence_number > p_period
            ORDER BY candle_sequence_number
        LOOP
            -- EMA = alpha * current_price + (1 - alpha) * previous_EMA
            v_prev_ema := v_alpha * v_current_row.close + (1 - v_alpha) * v_prev_ema;
            
            -- Update the temp table
            UPDATE temp_ema 
            SET ema_value = ROUND(v_prev_ema, 2)
            WHERE candle_key_id = v_current_row.candle_key_id;
        END LOOP;
    END;
    
    -- Update the main table with calculated EMA values
    UPDATE daily_candles dc
    SET indicators = 
        CASE 
            WHEN te.ema_value IS NULL THEN dc.indicators
            ELSE COALESCE(dc.indicators, '{}'::jsonb) || 
                 jsonb_build_object(v_indicator_key, te.ema_value)
        END,
        updated_at = CURRENT_TIMESTAMP
    FROM temp_ema te
    WHERE dc.candle_key_id = te.candle_key_id
    AND te.ema_value IS NOT NULL;
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    -- Clean up
    DROP TABLE IF EXISTS temp_ema;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed EMA(%) calculation for %: % rows updated in % ms',
        p_period, p_symbol, v_updated_rows, 
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        DROP TABLE IF EXISTS temp_ema;
        RAISE NOTICE 'Error in calculate_ema_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT 
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- PROPER RSI CALCULATION FUNCTION (Wilder's Method)
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_rsi_for_symbol(
    p_symbol TEXT,
    p_period INTEGER DEFAULT 14
)
RETURNS TABLE(
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
    v_indicator_key TEXT;
BEGIN
    v_indicator_key := 'rsi_' || p_period;
    
    RAISE NOTICE 'Calculating RSI(%) for symbol: % using Wilder method', p_period, p_symbol;
    
    -- Create temporary table for RSI calculation
    CREATE TEMP TABLE temp_rsi AS
    WITH price_changes AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            close - LAG(close, 1) OVER (ORDER BY candle_sequence_number) as price_change
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY candle_sequence_number
    ),
    gains_losses AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            price_change,
            CASE WHEN price_change > 0 THEN price_change ELSE 0 END as gain,
            CASE WHEN price_change < 0 THEN ABS(price_change) ELSE 0 END as loss
        FROM price_changes
    ),
    initial_averages AS (
        SELECT 
            candle_key_id,
            candle_sequence_number,
            close,
            gain,
            loss,
            -- Calculate initial average gain and loss using SMA for first period
            CASE 
                WHEN candle_sequence_number = p_period THEN
                    AVG(gain) OVER (
                        ORDER BY candle_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    )
                ELSE NULL
            END as avg_gain,
            CASE 
                WHEN candle_sequence_number = p_period THEN
                    AVG(loss) OVER (
                        ORDER BY candle_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    )
                ELSE NULL
            END as avg_loss
        FROM gains_losses
    )
    SELECT * FROM initial_averages;
    
    -- Apply Wilder's smoothing for average gain and loss
    DECLARE
        v_prev_avg_gain NUMERIC;
        v_prev_avg_loss NUMERIC;
        v_current_row RECORD;
        v_rs NUMERIC;
        v_rsi NUMERIC;
    BEGIN
        -- Get initial averages
        SELECT avg_gain, avg_loss 
        INTO v_prev_avg_gain, v_prev_avg_loss
        FROM temp_rsi
        WHERE candle_sequence_number = p_period;
        
        -- Update RSI for the initial period
        IF v_prev_avg_loss > 0 THEN
            v_rs := v_prev_avg_gain / v_prev_avg_loss;
            v_rsi := 100 - (100 / (1 + v_rs));
        ELSE
            v_rsi := 100; -- If no losses, RSI is 100
        END IF;
        
        UPDATE temp_rsi 
        SET avg_gain = v_prev_avg_gain,
            avg_loss = v_prev_avg_loss
        WHERE candle_sequence_number = p_period;
        
        -- Calculate RSI for remaining rows using Wilder's smoothing
        FOR v_current_row IN 
            SELECT * FROM temp_rsi 
            WHERE candle_sequence_number > p_period
            ORDER BY candle_sequence_number
        LOOP
            -- Wilder's smoothing: 
            -- avg_gain = ((prev_avg_gain * (period - 1)) + current_gain) / period
            -- avg_loss = ((prev_avg_loss * (period - 1)) + current_loss) / period
            v_prev_avg_gain := ((v_prev_avg_gain * (p_period - 1)) + v_current_row.gain) / p_period;
            v_prev_avg_loss := ((v_prev_avg_loss * (p_period - 1)) + v_current_row.loss) / p_period;
            
            -- Update the temp table
            UPDATE temp_rsi 
            SET avg_gain = v_prev_avg_gain,
                avg_loss = v_prev_avg_loss
            WHERE candle_key_id = v_current_row.candle_key_id;
        END LOOP;
    END;
    
    -- Calculate final RSI values and update main table
    UPDATE daily_candles dc
    SET indicators = 
        CASE 
            WHEN tr.candle_sequence_number < p_period THEN dc.indicators
            ELSE COALESCE(dc.indicators, '{}'::jsonb) || 
                 jsonb_build_object(
                     v_indicator_key, 
                     ROUND(
                         CASE 
                             WHEN tr.avg_loss = 0 THEN 100
                             ELSE 100 - (100 / (1 + (tr.avg_gain / tr.avg_loss)))
                         END, 2
                     )
                 )
        END,
        updated_at = CURRENT_TIMESTAMP
    FROM temp_rsi tr
    WHERE dc.candle_key_id = tr.candle_key_id
    AND tr.candle_sequence_number >= p_period;
    
    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    
    -- Clean up
    DROP TABLE IF EXISTS temp_rsi;
    
    v_end_time := clock_timestamp();
    
    RAISE NOTICE 'Completed RSI(%) calculation for %: % rows updated in % ms',
        p_period, p_symbol, v_updated_rows, 
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER;
    
    RETURN QUERY SELECT 
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM v_end_time - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        DROP TABLE IF EXISTS temp_rsi;
        RAISE NOTICE 'Error in calculate_rsi_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT 
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- BATCH CALCULATION FUNCTIONS
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_ema_for_all_symbols(
    p_period INTEGER
)
RETURNS TABLE(
    total_symbols INTEGER,
    successful_symbols INTEGER,
    failed_symbols INTEGER,
    total_execution_time_ms INTEGER,
    indicator_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_symbol_record RECORD;
    v_result RECORD;
    v_success_count INTEGER := 0;
    v_fail_count INTEGER := 0;
    v_total_count INTEGER := 0;
BEGIN
    RAISE NOTICE 'Starting batch EMA(%) calculation for all symbols', p_period;
    
    FOR v_symbol_record IN 
        SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol
    LOOP
        v_total_count := v_total_count + 1;
        
        SELECT * INTO v_result 
        FROM calculate_ema_for_symbol(v_symbol_record.symbol, p_period);
        
        IF v_result.status = 'SUCCESS' AND v_result.updated_rows > 0 THEN
            v_success_count := v_success_count + 1;
        ELSE
            v_fail_count := v_fail_count + 1;
        END IF;
        
        IF v_total_count % 10 = 0 THEN
            RAISE NOTICE 'Progress: % symbols processed', v_total_count;
        END IF;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_total_count,
        v_success_count,
        v_fail_count,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'ema_' || p_period;
END;
$$;

CREATE OR REPLACE FUNCTION calculate_rsi_for_all_symbols(
    p_period INTEGER DEFAULT 14
)
RETURNS TABLE(
    total_symbols INTEGER,
    successful_symbols INTEGER,
    failed_symbols INTEGER,
    total_execution_time_ms INTEGER,
    indicator_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_symbol_record RECORD;
    v_result RECORD;
    v_success_count INTEGER := 0;
    v_fail_count INTEGER := 0;
    v_total_count INTEGER := 0;
BEGIN
    RAISE NOTICE 'Starting batch RSI(%) calculation for all symbols', p_period;
    
    FOR v_symbol_record IN 
        SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol
    LOOP
        v_total_count := v_total_count + 1;
        
        SELECT * INTO v_result 
        FROM calculate_rsi_for_symbol(v_symbol_record.symbol, p_period);
        
        IF v_result.status = 'SUCCESS' AND v_result.updated_rows > 0 THEN
            v_success_count := v_success_count + 1;
        ELSE
            v_fail_count := v_fail_count + 1;
        END IF;
        
        IF v_total_count % 10 = 0 THEN
            RAISE NOTICE 'Progress: % symbols processed', v_total_count;
        END IF;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_total_count,
        v_success_count,
        v_fail_count,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'rsi_' || p_period;
END;
$$;

-- =====================================================
-- IMPROVED COMPREHENSIVE CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_all_improved_indicators_for_symbol(
    p_symbol TEXT
)
RETURNS TABLE(
    indicator_name TEXT,
    updated_rows INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_result RECORD;
BEGIN
    -- Calculate proper EMA values
    SELECT * INTO v_result FROM calculate_ema_for_symbol(p_symbol, 5);
    RETURN QUERY SELECT 'ema_5'::TEXT, v_result.updated_rows, v_result.status;
    
    SELECT * INTO v_result FROM calculate_ema_for_symbol(p_symbol, 10);
    RETURN QUERY SELECT 'ema_10'::TEXT, v_result.updated_rows, v_result.status;
    
    SELECT * INTO v_result FROM calculate_ema_for_symbol(p_symbol, 20);
    RETURN QUERY SELECT 'ema_20'::TEXT, v_result.updated_rows, v_result.status;
    
    -- Calculate proper RSI
    SELECT * INTO v_result FROM calculate_rsi_for_symbol(p_symbol, 14);
    RETURN QUERY SELECT 'rsi_period_14'::TEXT, v_result.updated_rows, v_result.status;
END;
$$;

-- =====================================================
-- GRANT PERMISSIONS
-- =====================================================
GRANT EXECUTE ON FUNCTION calculate_ema_for_symbol(TEXT, INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_rsi_for_symbol(TEXT, INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_ema_for_all_symbols(INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_rsi_for_all_symbols(INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_all_improved_indicators_for_symbol(TEXT) TO PUBLIC;