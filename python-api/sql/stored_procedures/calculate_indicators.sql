-- =====================================================
-- INDICATOR CALCULATION STORED PROCEDURES
-- =====================================================
-- Clean, properly named functions for all SMA/EMA calculations
-- Supports daily, weekly, and monthly timeframes
-- =====================================================

-- =====================================================
-- DAILY SMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_sma(
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    symbol_result RECORD;
BEGIN
    v_indicator_key := 'sma_' || p_period;
    
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        SELECT * INTO symbol_result FROM calculate_daily_sma_for_symbol(
            symbol_rec.symbol, 
            p_period, 
            p_force_recalculate
        );
        
        IF symbol_result.status = 'SUCCESS' THEN
            v_total_updated_rows := v_total_updated_rows + symbol_result.updated_rows;
        END IF;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
END;
$$;

-- =====================================================
-- DAILY EMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_ema(
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    symbol_result RECORD;
BEGIN
    v_indicator_key := 'ema_' || p_period;
    
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        SELECT * INTO symbol_result FROM calculate_daily_ema_for_symbol(
            symbol_rec.symbol, 
            p_period, 
            p_force_recalculate
        );
        
        IF symbol_result.status = 'SUCCESS' THEN
            v_total_updated_rows := v_total_updated_rows + symbol_result.updated_rows;
        END IF;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
END;
$$;

-- =====================================================
-- WEEKLY SMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_weekly_sma(
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_symbol_updated_rows INTEGER;
    symbol_rec RECORD;
BEGIN
    v_indicator_key := 'weekly_sma_' || p_period;
    
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        -- Calculate individual SMA for each daily candle within weekly periods
        WITH daily_candles_with_week AS (
            SELECT 
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_close,
                wc.week_sequence_number
            FROM daily_candles dc
            JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND dc.weekly_close IS NOT NULL
            AND wc.week_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        ),
        daily_with_previous_weeks AS (
            SELECT 
                dcw.candle_key_id,
                dcw.weekly_close as current_week_close,
                dcw.week_sequence_number,
                ARRAY(
                    SELECT wc.close 
                    FROM weekly_candles wc 
                    WHERE wc.symbol = symbol_rec.symbol
                    AND wc.week_sequence_number < dcw.week_sequence_number
                    AND wc.week_sequence_number >= dcw.week_sequence_number - (p_period - 1)
                    ORDER BY wc.week_sequence_number
                ) as previous_weeks_closes
            FROM daily_candles_with_week dcw
        ),
        daily_sma AS (
            SELECT 
                dwpw.candle_key_id,
                CASE 
                    WHEN array_length(dwpw.previous_weeks_closes, 1) IS NULL THEN
                        CASE WHEN p_period = 1 THEN 
                            ROUND(dwpw.current_week_close::numeric, 2)
                        ELSE NULL 
                        END
                    WHEN array_length(dwpw.previous_weeks_closes, 1) + 1 >= p_period THEN
                        ROUND((
                            (SELECT SUM(unnest) FROM unnest(
                                dwpw.previous_weeks_closes[
                                    GREATEST(1, array_length(dwpw.previous_weeks_closes, 1) - (p_period - 2)):
                                    array_length(dwpw.previous_weeks_closes, 1)
                                ]
                            )) 
                            + dwpw.current_week_close
                        ) / p_period::numeric, 2)
                    ELSE NULL
                END as sma_value
            FROM daily_with_previous_weeks dwpw
        )
        UPDATE daily_candles AS target
        SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
            jsonb_build_object(v_indicator_key, ds.sma_value),
            updated_at = CURRENT_TIMESTAMP
        FROM daily_sma ds
        WHERE target.candle_key_id = ds.candle_key_id
        AND ds.sma_value IS NOT NULL
        AND (
            p_force_recalculate OR
            NOT (target.indicators ? v_indicator_key) OR 
            (target.indicators->v_indicator_key) IS NULL
        );
        
        GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
        v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
END;
$$;

-- =====================================================
-- WEEKLY EMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_weekly_ema(
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_alpha NUMERIC;
    v_symbol_updated_rows INTEGER;
    symbol_rec RECORD;
BEGIN
    v_indicator_key := 'weekly_ema_' || p_period;
    v_alpha := 2.0 / (p_period + 1);
    
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        -- Calculate individual EMA for each daily candle within weekly periods
        WITH RECURSIVE daily_candles_ordered AS (
            SELECT 
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_close,
                wc.week_sequence_number,
                ROW_NUMBER() OVER (ORDER BY dc.candle_sequence_number) as row_num
            FROM daily_candles dc
            JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND dc.weekly_close IS NOT NULL
            AND wc.week_sequence_number IS NOT NULL
        ),
        initial_sma AS (
            SELECT 
                AVG(dco.weekly_close) as initial_value,
                MIN(dco.candle_key_id) as first_candle_id,
                MIN(dco.row_num) + p_period - 1 as sma_end_row
            FROM daily_candles_ordered dco
            WHERE dco.row_num <= p_period
        ),
        daily_ema AS (
            SELECT 
                dco.candle_key_id,
                dco.row_num,
                dco.weekly_close,
                CASE 
                    WHEN dco.row_num <= isma.sma_end_row THEN ROUND(isma.initial_value::numeric, 2)
                    ELSE NULL
                END as ema_value
            FROM daily_candles_ordered dco
            CROSS JOIN initial_sma isma
            WHERE dco.row_num = isma.sma_end_row
            
            UNION ALL
            
            SELECT 
                dco.candle_key_id,
                dco.row_num,
                dco.weekly_close,
                ROUND((dco.weekly_close * v_alpha + de.ema_value * (1 - v_alpha))::numeric, 2) as ema_value
            FROM daily_candles_ordered dco
            INNER JOIN daily_ema de ON dco.row_num = de.row_num + 1
        )
        UPDATE daily_candles AS target
        SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
            jsonb_build_object(v_indicator_key, de.ema_value),
            updated_at = CURRENT_TIMESTAMP
        FROM daily_ema de
        WHERE target.candle_key_id = de.candle_key_id
        AND de.ema_value IS NOT NULL
        AND (
            p_force_recalculate OR
            NOT (target.indicators ? v_indicator_key) OR 
            (target.indicators->v_indicator_key) IS NULL
        );
        
        GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
        v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
END;
$$;

-- =====================================================
-- MONTHLY SMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_monthly_sma(
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_symbol_updated_rows INTEGER;
    symbol_rec RECORD;
BEGIN
    v_indicator_key := 'monthly_sma_' || p_period;
    
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        -- Calculate individual SMA for each daily candle within monthly periods
        WITH daily_candles_with_month AS (
            SELECT 
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.monthly_close,
                mc.month_sequence_number
            FROM daily_candles dc
            JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND dc.monthly_close IS NOT NULL
            AND mc.month_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        ),
        daily_with_previous_months AS (
            SELECT 
                dcm.candle_key_id,
                dcm.monthly_close as current_month_close,
                dcm.month_sequence_number,
                ARRAY(
                    SELECT mc.close 
                    FROM monthly_candles mc 
                    WHERE mc.symbol = symbol_rec.symbol
                    AND mc.month_sequence_number < dcm.month_sequence_number
                    AND mc.month_sequence_number >= dcm.month_sequence_number - (p_period - 1)
                    ORDER BY mc.month_sequence_number
                ) as previous_months_closes
            FROM daily_candles_with_month dcm
        ),
        daily_sma AS (
            SELECT 
                dwpm.candle_key_id,
                CASE 
                    WHEN array_length(dwpm.previous_months_closes, 1) IS NULL THEN
                        CASE WHEN p_period = 1 THEN 
                            ROUND(dwpm.current_month_close::numeric, 2)
                        ELSE NULL 
                        END
                    WHEN array_length(dwpm.previous_months_closes, 1) + 1 >= p_period THEN
                        ROUND((
                            (SELECT SUM(unnest) FROM unnest(
                                dwpm.previous_months_closes[
                                    GREATEST(1, array_length(dwpm.previous_months_closes, 1) - (p_period - 2)):
                                    array_length(dwpm.previous_months_closes, 1)
                                ]
                            )) 
                            + dwpm.current_month_close
                        ) / p_period::numeric, 2)
                    ELSE NULL
                END as sma_value
            FROM daily_with_previous_months dwpm
        )
        UPDATE daily_candles AS target
        SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
            jsonb_build_object(v_indicator_key, ds.sma_value),
            updated_at = CURRENT_TIMESTAMP
        FROM daily_sma ds
        WHERE target.candle_key_id = ds.candle_key_id
        AND ds.sma_value IS NOT NULL
        AND (
            p_force_recalculate OR
            NOT (target.indicators ? v_indicator_key) OR 
            (target.indicators->v_indicator_key) IS NULL
        );
        
        GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
        v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
END;
$$;

-- =====================================================
-- MONTHLY EMA CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_monthly_ema(
    p_period INTEGER,
    p_symbol_filter TEXT DEFAULT NULL,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_total_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_alpha NUMERIC;
    v_symbol_updated_rows INTEGER;
    symbol_rec RECORD;
BEGIN
    v_indicator_key := 'monthly_ema_' || p_period;
    v_alpha := 2.0 / (p_period + 1);
    
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        -- Calculate individual EMA for each daily candle within monthly periods
        WITH RECURSIVE daily_candles_ordered AS (
            SELECT 
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.monthly_close,
                mc.month_sequence_number,
                ROW_NUMBER() OVER (ORDER BY dc.candle_sequence_number) as row_num
            FROM daily_candles dc
            JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND dc.monthly_close IS NOT NULL
            AND mc.month_sequence_number IS NOT NULL
        ),
        initial_sma AS (
            SELECT 
                AVG(dco.monthly_close) as initial_value,
                MIN(dco.candle_key_id) as first_candle_id,
                MIN(dco.row_num) + p_period - 1 as sma_end_row
            FROM daily_candles_ordered dco
            WHERE dco.row_num <= p_period
        ),
        daily_ema AS (
            SELECT 
                dco.candle_key_id,
                dco.row_num,
                dco.monthly_close,
                CASE 
                    WHEN dco.row_num <= isma.sma_end_row THEN ROUND(isma.initial_value::numeric, 2)
                    ELSE NULL
                END as ema_value
            FROM daily_candles_ordered dco
            CROSS JOIN initial_sma isma
            WHERE dco.row_num = isma.sma_end_row
            
            UNION ALL
            
            SELECT 
                dco.candle_key_id,
                dco.row_num,
                dco.monthly_close,
                ROUND((dco.monthly_close * v_alpha + de.ema_value * (1 - v_alpha))::numeric, 2) as ema_value
            FROM daily_candles_ordered dco
            INNER JOIN daily_ema de ON dco.row_num = de.row_num + 1
        )
        UPDATE daily_candles AS target
        SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
            jsonb_build_object(v_indicator_key, de.ema_value),
            updated_at = CURRENT_TIMESTAMP
        FROM daily_ema de
        WHERE target.candle_key_id = de.candle_key_id
        AND de.ema_value IS NOT NULL
        AND (
            p_force_recalculate OR
            NOT (target.indicators ? v_indicator_key) OR 
            (target.indicators->v_indicator_key) IS NULL
        );
        
        GET DIAGNOSTICS v_symbol_updated_rows = ROW_COUNT;
        v_total_updated_rows := v_total_updated_rows + v_symbol_updated_rows;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_total_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;
END;
$$;

-- =====================================================
-- DYNAMIC INDICATOR HANDLER
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_dynamic_sma_ema(
    p_indicator_name TEXT
)
RETURNS TABLE(
    success BOOLEAN,
    message TEXT,
    indicator_key TEXT,
    updated_rows INTEGER,
    execution_time_ms INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_parts TEXT[];
    v_indicator_type TEXT;
    v_period INTEGER;
    v_timeframe TEXT := 'daily';
    v_result RECORD;
    v_start_time TIMESTAMP := clock_timestamp();
BEGIN
    -- Parse indicator name: timeframe_type_period or type_period
    v_parts := string_to_array(p_indicator_name, '_');
    
    IF array_length(v_parts, 1) = 3 THEN
        v_timeframe := v_parts[1];
        v_indicator_type := v_parts[2];
        v_period := v_parts[3]::INTEGER;
    ELSIF array_length(v_parts, 1) = 2 THEN
        v_timeframe := 'daily';
        v_indicator_type := v_parts[1];
        v_period := v_parts[2]::INTEGER;
    ELSE
        RETURN QUERY SELECT 
            FALSE,
            'Invalid indicator name format. Expected: [timeframe_]type_period',
            p_indicator_name,
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER;
        RETURN;
    END IF;
    
    IF v_indicator_type NOT IN ('sma', 'ema') THEN
        RETURN QUERY SELECT 
            FALSE,
            'Unsupported indicator type: ' || v_indicator_type || '. Supported: sma, ema',
            p_indicator_name,
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER;
        RETURN;
    END IF;
    
    -- Call appropriate calculation function
    IF v_timeframe = 'daily' THEN
        IF v_indicator_type = 'sma' THEN
            SELECT * INTO v_result FROM calculate_daily_sma(v_period);
        ELSIF v_indicator_type = 'ema' THEN
            SELECT * INTO v_result FROM calculate_daily_ema(v_period);
        END IF;
    ELSIF v_timeframe = 'weekly' THEN
        IF v_indicator_type = 'sma' THEN
            SELECT * INTO v_result FROM calculate_weekly_sma(v_period);
        ELSIF v_indicator_type = 'ema' THEN
            SELECT * INTO v_result FROM calculate_weekly_ema(v_period);
        END IF;
    ELSIF v_timeframe = 'monthly' THEN
        IF v_indicator_type = 'sma' THEN
            SELECT * INTO v_result FROM calculate_monthly_sma(v_period);
        ELSIF v_indicator_type = 'ema' THEN
            SELECT * INTO v_result FROM calculate_monthly_ema(v_period);
        END IF;
    ELSE
        RETURN QUERY SELECT 
            FALSE,
            'Unsupported timeframe: ' || v_timeframe || '. Supported: daily, weekly, monthly',
            p_indicator_name,
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER;
        RETURN;
    END IF;
    
    IF v_result.status = 'SUCCESS' THEN
        RETURN QUERY SELECT 
            TRUE,
            'Successfully calculated ' || v_timeframe || ' ' || upper(v_indicator_type) || '(' || v_period || ')',
            v_result.indicator_key,
            v_result.updated_rows,
            v_result.execution_time_ms;
    ELSE
        RETURN QUERY SELECT 
            FALSE,
            'Failed to calculate ' || v_timeframe || ' ' || upper(v_indicator_type) || '(' || v_period || '): ' || v_result.status,
            p_indicator_name,
            COALESCE(v_result.updated_rows, 0),
            COALESCE(v_result.execution_time_ms, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER);
    END IF;
    
EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT 
            FALSE,
            'Error in calculate_dynamic_sma_ema: ' || SQLERRM,
            p_indicator_name,
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_daily_sma(INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_daily_ema(INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_sma(INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_ema(INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_sma(INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_ema(INTEGER, TEXT, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_dynamic_sma_ema(TEXT) TO PUBLIC;