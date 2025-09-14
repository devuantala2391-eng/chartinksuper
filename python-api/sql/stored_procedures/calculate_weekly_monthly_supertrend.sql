-- =====================================================
-- SLIDING WINDOW WEEKLY AND MONTHLY SUPERTREND CALCULATION
-- =====================================================
-- Uses sliding window approach like SMA/EMA where each daily candle
-- gets its own SuperTrend value based on the window at that point
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_weekly_monthly_supertrend(
    p_timeframe TEXT DEFAULT 'weekly',  -- weekly or monthly
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
    
    RAISE NOTICE 'Calculating % SuperTrend(%,%) with sliding window, storing as % and %', 
        p_timeframe, p_period, p_multiplier, v_indicator_key, v_direction_key;
    
    -- Process each symbol
    FOR symbol_rec IN 
        SELECT DISTINCT symbol FROM daily_candles 
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;
        
        IF p_timeframe = 'weekly' THEN
            -- Weekly SuperTrend with sliding window approach (like SMA/EMA)
            WITH daily_candles_with_week AS (
                SELECT 
                    dc.candle_key_id,
                    dc.symbol,
                    dc.candle_sequence_number,
                    dc.weekly_high as current_high,
                    dc.weekly_low as current_low,
                    dc.weekly_close as current_close,
                    wc.week_sequence_number
                FROM daily_candles dc
                JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.weekly_high IS NOT NULL
                AND dc.weekly_low IS NOT NULL
                AND dc.weekly_close IS NOT NULL
                AND wc.week_sequence_number IS NOT NULL
                ORDER BY dc.candle_sequence_number
            ),
            -- Get historical weekly true ranges for ATR calculation
            historical_weekly_tr AS (
                SELECT 
                    week_sequence_number,
                    GREATEST(
                        high - low,
                        ABS(high - LAG(close, 1) OVER (ORDER BY week_sequence_number)),
                        ABS(low - LAG(close, 1) OVER (ORDER BY week_sequence_number))
                    ) as true_range
                FROM weekly_candles
                WHERE symbol = symbol_rec.symbol
                AND high IS NOT NULL
                AND low IS NOT NULL
                AND close IS NOT NULL
                ORDER BY week_sequence_number
            ),
            -- For each daily candle, calculate its own ATR using sliding window
            daily_with_atr AS (
                SELECT 
                    dcw.candle_key_id,
                    dcw.current_high,
                    dcw.current_low,
                    dcw.current_close,
                    dcw.week_sequence_number,
                    -- Calculate current day's true range
                    GREATEST(
                        dcw.current_high - dcw.current_low,
                        ABS(dcw.current_high - LAG(dcw.current_close, 1) OVER (PARTITION BY dcw.symbol ORDER BY dcw.candle_sequence_number)),
                        ABS(dcw.current_low - LAG(dcw.current_close, 1) OVER (PARTITION BY dcw.symbol ORDER BY dcw.candle_sequence_number))
                    ) as current_tr,
                    -- Get average of previous (p_period - 1) weeks' true ranges
                    (
                        SELECT AVG(true_range)
                        FROM (
                            SELECT true_range
                            FROM historical_weekly_tr hwt
                            WHERE hwt.week_sequence_number < dcw.week_sequence_number
                            AND hwt.week_sequence_number >= dcw.week_sequence_number - (p_period - 1)
                            ORDER BY hwt.week_sequence_number DESC
                            LIMIT (p_period - 1)
                        ) prev_trs
                    ) as prev_weeks_avg_tr
                FROM daily_candles_with_week dcw
            ),
            -- Calculate ATR and SuperTrend for each daily candle
            daily_supertrend AS (
                SELECT 
                    candle_key_id,
                    current_high,
                    current_low,
                    current_close,
                    week_sequence_number,
                    -- Sliding window ATR: combine previous weeks with current day's TR
                    CASE 
                        WHEN prev_weeks_avg_tr IS NOT NULL AND current_tr IS NOT NULL THEN
                            ((prev_weeks_avg_tr * (p_period - 1)) + current_tr) / p_period
                        WHEN prev_weeks_avg_tr IS NULL AND p_period = 1 THEN
                            current_tr
                        ELSE NULL
                    END as atr
                FROM daily_with_atr
            ),
            -- Calculate final SuperTrend values
            supertrend_final AS (
                SELECT 
                    ds.candle_key_id,
                    CASE 
                        WHEN ds.atr IS NOT NULL THEN
                            CASE 
                                -- If close is nearer to lower band, use lower band
                                WHEN ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) - (p_multiplier * ds.atr))) 
                                     <= ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) + (p_multiplier * ds.atr))) THEN 
                                    ROUND((((ds.current_high + ds.current_low) / 2) - (p_multiplier * ds.atr))::numeric, 2)
                                -- Otherwise use upper band
                                ELSE 
                                    ROUND((((ds.current_high + ds.current_low) / 2) + (p_multiplier * ds.atr))::numeric, 2)
                            END
                        ELSE NULL
                    END as supertrend_value,
                    CASE 
                        WHEN ds.atr IS NOT NULL THEN
                            CASE 
                                -- Direction: 1 = bullish (using lower band), 0 = bearish (using upper band)
                                WHEN ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) - (p_multiplier * ds.atr))) 
                                     <= ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) + (p_multiplier * ds.atr))) THEN 1
                                ELSE 0
                            END
                        ELSE NULL
                    END as direction
                FROM daily_supertrend ds
                WHERE ds.week_sequence_number >= (p_period - 1)  -- Need enough history
            )
            -- Update each daily candle with its own SuperTrend value
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, sf.supertrend_value,
                    v_direction_key, sf.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM supertrend_final sf
            WHERE target.candle_key_id = sf.candle_key_id
            AND sf.supertrend_value IS NOT NULL
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
        ELSIF p_timeframe = 'monthly' THEN
            -- Monthly SuperTrend with sliding window approach (like SMA/EMA)
            WITH daily_candles_with_month AS (
                SELECT 
                    dc.candle_key_id,
                    dc.symbol,
                    dc.candle_sequence_number,
                    dc.monthly_high as current_high,
                    dc.monthly_low as current_low,
                    dc.monthly_close as current_close,
                    mc.month_sequence_number
                FROM daily_candles dc
                JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.monthly_high IS NOT NULL
                AND dc.monthly_low IS NOT NULL
                AND dc.monthly_close IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.candle_sequence_number
            ),
            -- Get historical monthly true ranges for ATR calculation
            historical_monthly_tr AS (
                SELECT 
                    month_sequence_number,
                    GREATEST(
                        high - low,
                        ABS(high - LAG(close, 1) OVER (ORDER BY month_sequence_number)),
                        ABS(low - LAG(close, 1) OVER (ORDER BY month_sequence_number))
                    ) as true_range
                FROM monthly_candles
                WHERE symbol = symbol_rec.symbol
                AND high IS NOT NULL
                AND low IS NOT NULL
                AND close IS NOT NULL
                ORDER BY month_sequence_number
            ),
            -- For each daily candle, calculate its own ATR using sliding window
            daily_with_atr AS (
                SELECT 
                    dcm.candle_key_id,
                    dcm.current_high,
                    dcm.current_low,
                    dcm.current_close,
                    dcm.month_sequence_number,
                    -- Calculate current day's true range
                    GREATEST(
                        dcm.current_high - dcm.current_low,
                        ABS(dcm.current_high - LAG(dcm.current_close, 1) OVER (PARTITION BY dcm.symbol ORDER BY dcm.candle_sequence_number)),
                        ABS(dcm.current_low - LAG(dcm.current_close, 1) OVER (PARTITION BY dcm.symbol ORDER BY dcm.candle_sequence_number))
                    ) as current_tr,
                    -- Get average of previous (p_period - 1) months' true ranges
                    (
                        SELECT AVG(true_range)
                        FROM (
                            SELECT true_range
                            FROM historical_monthly_tr hmt
                            WHERE hmt.month_sequence_number < dcm.month_sequence_number
                            AND hmt.month_sequence_number >= dcm.month_sequence_number - (p_period - 1)
                            ORDER BY hmt.month_sequence_number DESC
                            LIMIT (p_period - 1)
                        ) prev_trs
                    ) as prev_months_avg_tr
                FROM daily_candles_with_month dcm
            ),
            -- Calculate ATR and SuperTrend for each daily candle
            daily_supertrend AS (
                SELECT 
                    candle_key_id,
                    current_high,
                    current_low,
                    current_close,
                    month_sequence_number,
                    -- Sliding window ATR: combine previous months with current day's TR
                    CASE 
                        WHEN prev_months_avg_tr IS NOT NULL AND current_tr IS NOT NULL THEN
                            ((prev_months_avg_tr * (p_period - 1)) + current_tr) / p_period
                        WHEN prev_months_avg_tr IS NULL AND p_period = 1 THEN
                            current_tr
                        ELSE NULL
                    END as atr
                FROM daily_with_atr
            ),
            -- Calculate final SuperTrend values
            supertrend_final AS (
                SELECT 
                    ds.candle_key_id,
                    CASE 
                        WHEN ds.atr IS NOT NULL THEN
                            CASE 
                                -- If close is nearer to lower band, use lower band
                                WHEN ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) - (p_multiplier * ds.atr))) 
                                     <= ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) + (p_multiplier * ds.atr))) THEN 
                                    ROUND((((ds.current_high + ds.current_low) / 2) - (p_multiplier * ds.atr))::numeric, 2)
                                -- Otherwise use upper band
                                ELSE 
                                    ROUND((((ds.current_high + ds.current_low) / 2) + (p_multiplier * ds.atr))::numeric, 2)
                            END
                        ELSE NULL
                    END as supertrend_value,
                    CASE 
                        WHEN ds.atr IS NOT NULL THEN
                            CASE 
                                -- Direction: 1 = bullish (using lower band), 0 = bearish (using upper band)
                                WHEN ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) - (p_multiplier * ds.atr))) 
                                     <= ABS(ds.current_close - (((ds.current_high + ds.current_low) / 2) + (p_multiplier * ds.atr))) THEN 1
                                ELSE 0
                            END
                        ELSE NULL
                    END as direction
                FROM daily_supertrend ds
                WHERE ds.month_sequence_number >= (p_period - 1)  -- Need enough history
            )
            -- Update each daily candle with its own SuperTrend value
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, sf.supertrend_value,
                    v_direction_key, sf.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM supertrend_final sf
            WHERE target.candle_key_id = sf.candle_key_id
            AND sf.supertrend_value IS NOT NULL
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
        END IF;
        
        GET DIAGNOSTICS v_batch_count = ROW_COUNT;
        v_updated_rows := v_updated_rows + v_batch_count;
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

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_weekly_monthly_supertrend(TEXT, INTEGER, NUMERIC, TEXT) TO PUBLIC;