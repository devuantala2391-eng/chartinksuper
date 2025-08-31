-- =====================================================
-- COMPREHENSIVE TIMEFRAME INDICATORS CALCULATION
-- =====================================================
-- This procedure calculates all indicators (percentage change, SuperTrend, etc.)
-- for all timeframes (daily, weekly, monthly) with proper prefixes
-- ALL indicators are stored in daily_candles.indicators JSONB column
-- =====================================================

-- Drop existing functions first for clean recreation
DROP FUNCTION IF EXISTS calculate_all_timeframe_indicators(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS calculate_timeframe_percentage_change(TEXT, TEXT);
DROP FUNCTION IF EXISTS calculate_timeframe_supertrend(TEXT, INTEGER, NUMERIC, TEXT);

-- =====================================================
-- PERCENTAGE CHANGE CALCULATION FOR ALL TIMEFRAMES
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_timeframe_percentage_change(
    p_timeframe TEXT DEFAULT 'daily',  -- daily, weekly, monthly
    p_symbol_filter TEXT DEFAULT NULL
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
    v_updated_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_batch_count INTEGER;
    symbol_rec RECORD;
BEGIN
    -- Set indicator key with timeframe prefix
    v_indicator_key := p_timeframe || '_pctchg';
    
    RAISE NOTICE 'Calculating % percentage change, storing as % in daily_candles', p_timeframe, v_indicator_key;
    
    -- Process each symbol
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        IF p_timeframe = 'daily' THEN
            -- Daily percentage change: compare with previous day
            WITH daily_changes AS (
                SELECT 
                    candle_key_id,
                    symbol,
                    close,
                    LAG(close, 1) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) as prev_close,
                    CASE 
                        WHEN LAG(close, 1) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) IS NOT NULL 
                        AND LAG(close, 1) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) != 0 THEN
                            ROUND(((close - LAG(close, 1) OVER (PARTITION BY symbol ORDER BY candle_sequence_number)) / 
                                   LAG(close, 1) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) * 100)::numeric, 4)
                        ELSE NULL
                    END as pct_change
                FROM daily_candles
                WHERE symbol = symbol_rec.symbol
            )
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, dc.pct_change),
                updated_at = CURRENT_TIMESTAMP
            FROM daily_changes dc
            WHERE target.candle_key_id = dc.candle_key_id
            AND dc.pct_change IS NOT NULL
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
        ELSIF p_timeframe = 'weekly' THEN
            -- Weekly percentage change: use weekly_close from daily_candles
            -- Compare current week's close with previous week's close from weekly_candles
            WITH weekly_changes AS (
                SELECT 
                    dc.candle_key_id,
                    dc.symbol,
                    dc.weekly_close as current_close,
                    wc_prev.close as prev_week_close,
                    CASE 
                        WHEN wc_prev.close IS NOT NULL AND wc_prev.close != 0 THEN
                            ROUND(((dc.weekly_close - wc_prev.close) / wc_prev.close * 100)::numeric, 4)
                        ELSE NULL
                    END as pct_change
                FROM daily_candles dc
                LEFT JOIN weekly_candles wc_current 
                    ON wc_current.weekly_candle_key_id = dc.weekly_candle_key_id
                LEFT JOIN weekly_candles wc_prev 
                    ON wc_prev.symbol = dc.symbol 
                    AND wc_prev.week_sequence_number = (wc_current.week_sequence_number - 1)
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.weekly_close IS NOT NULL
            )
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, wc.pct_change),
                updated_at = CURRENT_TIMESTAMP
            FROM weekly_changes wc
            WHERE target.candle_key_id = wc.candle_key_id
            AND wc.pct_change IS NOT NULL
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
        ELSIF p_timeframe = 'monthly' THEN
            -- Monthly percentage change: use monthly_close from daily_candles
            -- Compare with ~30 trading days ago
            WITH monthly_changes AS (
                SELECT 
                    candle_key_id,
                    symbol,
                    monthly_close as current_close,
                    LAG(close, 30) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) as prev_month_close,
                    CASE 
                        WHEN LAG(close, 30) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) IS NOT NULL 
                        AND LAG(close, 30) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) != 0 THEN
                            ROUND(((monthly_close - LAG(close, 30) OVER (PARTITION BY symbol ORDER BY candle_sequence_number)) / 
                                   LAG(close, 30) OVER (PARTITION BY symbol ORDER BY candle_sequence_number) * 100)::numeric, 4)
                        ELSE NULL
                    END as pct_change
                FROM daily_candles
                WHERE symbol = symbol_rec.symbol
                AND monthly_close IS NOT NULL
            )
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(v_indicator_key, mc.pct_change),
                updated_at = CURRENT_TIMESTAMP
            FROM monthly_changes mc
            WHERE target.candle_key_id = mc.candle_key_id
            AND mc.pct_change IS NOT NULL
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
        END IF;
        
        GET DIAGNOSTICS v_batch_count = ROW_COUNT;
        v_updated_rows := v_updated_rows + v_batch_count;
        v_processed_symbols := v_processed_symbols + 1;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT;
        
EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- SUPERTREND CALCULATION FOR ALL TIMEFRAMES
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_timeframe_supertrend(
    p_timeframe TEXT DEFAULT 'daily',  -- daily, weekly, monthly
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 3.0,
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
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
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_multiplier_str TEXT;
    v_batch_count INTEGER;
    symbol_rec RECORD;
BEGIN
    -- Format multiplier for key generation using utility function
    v_multiplier_str := format_multiplier_for_key(p_multiplier);
    
    -- Set indicator keys with timeframe prefix
    v_indicator_key := p_timeframe || '_supertrend_' || p_period || '_' || v_multiplier_str;
    v_direction_key := v_indicator_key || '_direction';
    
    RAISE NOTICE 'Calculating % SuperTrend(%,%), storing as % and % in daily_candles', 
        p_timeframe, p_period, p_multiplier, v_indicator_key, v_direction_key;
    
    -- Process each symbol
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        IF p_timeframe = 'daily' THEN
            -- Daily SuperTrend: calculate from daily OHLC
            WITH daily_atr AS (
                SELECT 
                    candle_key_id,
                    candle_sequence_number,
                    high,
                    low,
                    close,
                    GREATEST(
                        high - low,
                        ABS(high - LAG(close, 1) OVER (ORDER BY candle_sequence_number)),
                        ABS(low - LAG(close, 1) OVER (ORDER BY candle_sequence_number))
                    ) as true_range
                FROM daily_candles
                WHERE symbol = symbol_rec.symbol
                ORDER BY candle_sequence_number
            ),
            atr_values AS (
                SELECT 
                    candle_key_id,
                    candle_sequence_number,
                    high,
                    low,
                    close,
                    AVG(true_range) OVER (
                        ORDER BY candle_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    ) as atr
                FROM daily_atr
            ),
            supertrend_calc AS (
                SELECT 
                    candle_key_id,
                    candle_sequence_number,
                    close,
                    ((high + low) / 2) + (p_multiplier * atr) as upper_band,
                    ((high + low) / 2) - (p_multiplier * atr) as lower_band,
                    atr
                FROM atr_values
                WHERE candle_sequence_number >= p_period
            ),
            final_values AS (
                SELECT 
                    candle_key_id,
                    CASE 
                        WHEN ABS(close - lower_band) <= ABS(close - upper_band) THEN 
                            ROUND(lower_band::numeric, 2)
                        ELSE 
                            ROUND(upper_band::numeric, 2)
                    END as supertrend_value,
                    CASE 
                        WHEN ABS(close - lower_band) <= ABS(close - upper_band) THEN 1
                        ELSE 0
                    END as direction
                FROM supertrend_calc
            )
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, fv.supertrend_value,
                    v_direction_key, fv.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM final_values fv
            WHERE target.candle_key_id = fv.candle_key_id
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
        ELSIF p_timeframe = 'weekly' THEN
            -- Weekly SuperTrend: use partial week approach
            -- Current week OHLC from daily_candles + previous weeks from weekly_candles
            WITH weekly_data AS (
                SELECT 
                    dc.candle_key_id,
                    dc.candle_sequence_number,
                    dc.symbol,
                    dc.weekly_candle_key_id,
                    wc.week_sequence_number,
                    dc.weekly_high as high,
                    dc.weekly_low as low,
                    dc.weekly_close as close,
                    dc.datetime
                FROM daily_candles dc
                LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.weekly_high IS NOT NULL
                AND wc.week_sequence_number IS NOT NULL
            ),
            weekly_with_history AS (
                SELECT 
                    wd.candle_key_id,
                    wd.candle_sequence_number,
                    wd.week_sequence_number,
                    wd.high,
                    wd.low,
                    wd.close,
                    wd.datetime,
                    -- Get previous week's close for ATR calculation
                    LAG(wc_prev.close, 1) OVER (ORDER BY wd.candle_sequence_number) as prev_close
                FROM weekly_data wd
                LEFT JOIN weekly_candles wc_prev 
                    ON wc_prev.symbol = symbol_rec.symbol 
                    AND wc_prev.week_sequence_number = (wd.week_sequence_number - 1)
            ),
            weekly_atr AS (
                SELECT 
                    candle_key_id,
                    candle_sequence_number,
                    week_sequence_number,
                    high,
                    low,
                    close,
                    datetime,
                    GREATEST(
                        high - low,
                        CASE WHEN prev_close IS NOT NULL THEN ABS(high - prev_close) ELSE high - low END,
                        CASE WHEN prev_close IS NOT NULL THEN ABS(low - prev_close) ELSE high - low END
                    ) as true_range
                FROM weekly_with_history
            ),
            atr_calculated AS (
                SELECT 
                    wa.candle_key_id,
                    wa.candle_sequence_number,
                    wa.high,
                    wa.low,
                    wa.close,
                    -- Calculate ATR over previous p_period weeks
                    (
                        SELECT AVG(
                            GREATEST(
                                wc.high - wc.low,
                                ABS(wc.high - LAG(wc.close, 1) OVER (ORDER BY wc.week_sequence_number)),
                                ABS(wc.low - LAG(wc.close, 1) OVER (ORDER BY wc.week_sequence_number))
                            )
                        )
                        FROM weekly_candles wc
                        WHERE wc.symbol = symbol_rec.symbol
                        AND wc.week_sequence_number <= wa.week_sequence_number
                        AND wc.week_sequence_number > (wa.week_sequence_number - p_period)
                    ) as atr
                FROM weekly_atr wa
                WHERE wa.week_sequence_number >= p_period
            ),
            weekly_supertrend AS (
                SELECT 
                    candle_key_id,
                    close,
                    ((high + low) / 2) + (p_multiplier * atr) as upper_band,
                    ((high + low) / 2) - (p_multiplier * atr) as lower_band
                FROM atr_calculated
                WHERE atr IS NOT NULL
            ),
            final_weekly AS (
                SELECT 
                    candle_key_id,
                    CASE 
                        WHEN ABS(close - lower_band) <= ABS(close - upper_band) THEN 
                            ROUND(lower_band::numeric, 2)
                        ELSE 
                            ROUND(upper_band::numeric, 2)
                    END as supertrend_value,
                    CASE 
                        WHEN ABS(close - lower_band) <= ABS(close - upper_band) THEN 1
                        ELSE 0
                    END as direction
                FROM weekly_supertrend
            )
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, fw.supertrend_value,
                    v_direction_key, fw.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM final_weekly fw
            WHERE target.candle_key_id = fw.candle_key_id
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
        ELSIF p_timeframe = 'monthly' THEN
            -- Monthly SuperTrend: similar to weekly but using monthly data
            WITH monthly_data AS (
                SELECT 
                    dc.candle_key_id,
                    dc.candle_sequence_number,
                    dc.symbol,
                    dc.monthly_candle_key_id,
                    mc.month_sequence_number,
                    dc.monthly_high as high,
                    dc.monthly_low as low,
                    dc.monthly_close as close,
                    dc.datetime
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.monthly_high IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
            ),
            monthly_with_history AS (
                SELECT 
                    md.candle_key_id,
                    md.candle_sequence_number,
                    md.month_sequence_number,
                    md.high,
                    md.low,
                    md.close,
                    md.datetime,
                    LAG(mc_prev.close, 1) OVER (ORDER BY md.candle_sequence_number) as prev_close
                FROM monthly_data md
                LEFT JOIN monthly_candles mc_prev 
                    ON mc_prev.symbol = symbol_rec.symbol 
                    AND mc_prev.month_sequence_number = (md.month_sequence_number - 1)
            ),
            monthly_atr AS (
                SELECT 
                    candle_key_id,
                    candle_sequence_number,
                    month_sequence_number,
                    high,
                    low,
                    close,
                    datetime,
                    GREATEST(
                        high - low,
                        CASE WHEN prev_close IS NOT NULL THEN ABS(high - prev_close) ELSE high - low END,
                        CASE WHEN prev_close IS NOT NULL THEN ABS(low - prev_close) ELSE high - low END
                    ) as true_range
                FROM monthly_with_history
            ),
            atr_calculated AS (
                SELECT 
                    ma.candle_key_id,
                    ma.candle_sequence_number,
                    ma.high,
                    ma.low,
                    ma.close,
                    (
                        SELECT AVG(
                            GREATEST(
                                mc.high - mc.low,
                                ABS(mc.high - LAG(mc.close, 1) OVER (ORDER BY mc.month_sequence_number)),
                                ABS(mc.low - LAG(mc.close, 1) OVER (ORDER BY mc.month_sequence_number))
                            )
                        )
                        FROM monthly_candles mc
                        WHERE mc.symbol = symbol_rec.symbol
                        AND mc.month_sequence_number <= ma.month_sequence_number
                        AND mc.month_sequence_number > (ma.month_sequence_number - p_period)
                    ) as atr
                FROM monthly_atr ma
                WHERE ma.month_sequence_number >= p_period
            ),
            monthly_supertrend AS (
                SELECT 
                    candle_key_id,
                    close,
                    ((high + low) / 2) + (p_multiplier * atr) as upper_band,
                    ((high + low) / 2) - (p_multiplier * atr) as lower_band
                FROM atr_calculated
                WHERE atr IS NOT NULL
            ),
            final_monthly AS (
                SELECT 
                    candle_key_id,
                    CASE 
                        WHEN ABS(close - lower_band) <= ABS(close - upper_band) THEN 
                            ROUND(lower_band::numeric, 2)
                        ELSE 
                            ROUND(upper_band::numeric, 2)
                    END as supertrend_value,
                    CASE 
                        WHEN ABS(close - lower_band) <= ABS(close - upper_band) THEN 1
                        ELSE 0
                    END as direction
                FROM monthly_supertrend
            )
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, fm.supertrend_value,
                    v_direction_key, fm.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM final_monthly fm
            WHERE target.candle_key_id = fm.candle_key_id
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
        END IF;
        
        GET DIAGNOSTICS v_batch_count = ROW_COUNT;
        v_updated_rows := v_updated_rows + v_batch_count;
        v_processed_symbols := v_processed_symbols + 1;
    END LOOP;
    
    RETURN QUERY SELECT 
        v_processed_symbols,
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key,
        v_direction_key;
        
EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT 
            v_processed_symbols,
            v_updated_rows,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            format('ERROR: %s', SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;

-- =====================================================
-- MASTER FUNCTION TO CALCULATE ALL INDICATORS
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_all_timeframe_indicators(
    p_indicator_type TEXT DEFAULT 'all',  -- all, percentage, supertrend
    p_timeframe TEXT DEFAULT 'all',       -- all, daily, weekly, monthly
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    indicator_type TEXT,
    timeframe TEXT,
    processed_symbols INTEGER,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_result RECORD;
    v_timeframes TEXT[];
    v_tf TEXT;
BEGIN
    -- Determine timeframes to process
    IF p_timeframe = 'all' THEN
        v_timeframes := ARRAY['daily', 'weekly', 'monthly'];
    ELSE
        v_timeframes := ARRAY[p_timeframe];
    END IF;
    
    -- Process each timeframe
    FOREACH v_tf IN ARRAY v_timeframes
    LOOP
        -- Calculate percentage change if requested
        IF p_indicator_type IN ('all', 'percentage') THEN
            SELECT * INTO v_result 
            FROM calculate_timeframe_percentage_change(v_tf, p_symbol_filter);
            
            RETURN QUERY SELECT 
                'percentage'::TEXT,
                v_tf,
                v_result.processed_symbols,
                v_result.updated_rows,
                v_result.execution_time_ms,
                v_result.status;
        END IF;
        
        -- Calculate SuperTrend if requested
        IF p_indicator_type IN ('all', 'supertrend') THEN
            -- Calculate default SuperTrend(10, 3)
            SELECT * INTO v_result 
            FROM calculate_timeframe_supertrend(v_tf, 10, 3.0, p_symbol_filter);
            
            RETURN QUERY SELECT 
                'supertrend'::TEXT,
                v_tf,
                v_result.processed_symbols,
                v_result.updated_rows,
                v_result.execution_time_ms,
                v_result.status;
        END IF;
    END LOOP;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_timeframe_percentage_change(TEXT, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_timeframe_supertrend(TEXT, INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_all_timeframe_indicators(TEXT, TEXT, TEXT) TO PUBLIC;

-- =====================================================
-- USAGE EXAMPLES
-- =====================================================
/*
-- Calculate all indicators for all timeframes
SELECT * FROM calculate_all_timeframe_indicators('all', 'all');

-- Calculate only percentage change for daily timeframe
SELECT * FROM calculate_timeframe_percentage_change('daily');

-- Calculate weekly SuperTrend(10, 3) for specific symbol
SELECT * FROM calculate_timeframe_supertrend('weekly', 10, 3.0, '20MICRONS');

-- Calculate all indicators for weekly timeframe
SELECT * FROM calculate_all_timeframe_indicators('all', 'weekly');
*/