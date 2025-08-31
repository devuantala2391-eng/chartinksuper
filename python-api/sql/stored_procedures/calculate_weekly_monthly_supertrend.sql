-- =====================================================
-- SIMPLIFIED WEEKLY AND MONTHLY SUPERTREND CALCULATION
-- =====================================================
-- Uses partial week/month approach with simplified ATR calculation
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
    v_sql TEXT;
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
        IF p_timeframe = 'weekly' THEN
            -- Weekly SuperTrend using weekly OHLC columns in daily_candles
            -- Combined with historical weekly data
            WITH weekly_enriched AS (
                SELECT DISTINCT ON (dc.weekly_candle_key_id)
                    dc.candle_key_id,
                    dc.symbol,
                    dc.weekly_candle_key_id,
                    wc.week_sequence_number,
                    dc.weekly_high as high,
                    dc.weekly_low as low,
                    dc.weekly_close as close,
                    dc.candle_sequence_number
                FROM daily_candles dc
                LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.weekly_high IS NOT NULL
                AND wc.week_sequence_number IS NOT NULL
                ORDER BY dc.weekly_candle_key_id, dc.candle_sequence_number DESC
            ),
            weekly_with_tr AS (
                SELECT 
                    we.*,
                    -- Simple TR calculation
                    GREATEST(
                        we.high - we.low,
                        ABS(we.high - LAG(we.close, 1) OVER (ORDER BY we.week_sequence_number)),
                        ABS(we.low - LAG(we.close, 1) OVER (ORDER BY we.week_sequence_number))
                    ) as true_range
                FROM weekly_enriched we
            ),
            weekly_with_atr AS (
                SELECT 
                    *,
                    AVG(true_range) OVER (
                        ORDER BY week_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    ) as atr
                FROM weekly_with_tr
                WHERE week_sequence_number >= (p_period - 1)
            ),
            weekly_supertrend_calc AS (
                SELECT 
                    candle_key_id,
                    symbol,
                    close,
                    ((high + low) / 2) + (p_multiplier * atr) as upper_band,
                    ((high + low) / 2) - (p_multiplier * atr) as lower_band
                FROM weekly_with_atr
                WHERE atr IS NOT NULL
            ),
            weekly_final AS (
                SELECT 
                    wsc.candle_key_id,
                    CASE 
                        WHEN ABS(wsc.close - wsc.lower_band) <= ABS(wsc.close - wsc.upper_band) THEN 
                            ROUND(wsc.lower_band::numeric, 2)
                        ELSE 
                            ROUND(wsc.upper_band::numeric, 2)
                    END as supertrend_value,
                    CASE 
                        WHEN ABS(wsc.close - wsc.lower_band) <= ABS(wsc.close - wsc.upper_band) THEN 1
                        ELSE 0
                    END as direction
                FROM weekly_supertrend_calc wsc
            )
            -- Update all daily candles in the same week with the weekly SuperTrend value
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, wf.supertrend_value,
                    v_direction_key, wf.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM weekly_final wf
            INNER JOIN daily_candles dc2 ON dc2.candle_key_id = wf.candle_key_id
            WHERE target.symbol = symbol_rec.symbol
            AND target.weekly_candle_key_id = dc2.weekly_candle_key_id
            AND (
                NOT (target.indicators ? v_indicator_key) OR 
                (target.indicators->v_indicator_key) IS NULL
            );
            
        ELSIF p_timeframe = 'monthly' THEN
            -- Monthly SuperTrend using monthly OHLC columns in daily_candles
            WITH monthly_enriched AS (
                SELECT DISTINCT ON (dc.monthly_candle_key_id)
                    dc.candle_key_id,
                    dc.symbol,
                    dc.monthly_candle_key_id,
                    mc.month_sequence_number,
                    dc.monthly_high as high,
                    dc.monthly_low as low,
                    dc.monthly_close as close,
                    dc.candle_sequence_number
                FROM daily_candles dc
                LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = symbol_rec.symbol
                AND dc.monthly_high IS NOT NULL
                AND mc.month_sequence_number IS NOT NULL
                ORDER BY dc.monthly_candle_key_id, dc.candle_sequence_number DESC
            ),
            monthly_with_tr AS (
                SELECT 
                    me.*,
                    -- Simple TR calculation
                    GREATEST(
                        me.high - me.low,
                        ABS(me.high - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number)),
                        ABS(me.low - LAG(me.close, 1) OVER (ORDER BY me.month_sequence_number))
                    ) as true_range
                FROM monthly_enriched me
            ),
            monthly_with_atr AS (
                SELECT 
                    *,
                    AVG(true_range) OVER (
                        ORDER BY month_sequence_number 
                        ROWS BETWEEN (p_period - 1) PRECEDING AND CURRENT ROW
                    ) as atr
                FROM monthly_with_tr
                WHERE month_sequence_number >= (p_period - 1)
            ),
            monthly_supertrend_calc AS (
                SELECT 
                    candle_key_id,
                    symbol,
                    close,
                    ((high + low) / 2) + (p_multiplier * atr) as upper_band,
                    ((high + low) / 2) - (p_multiplier * atr) as lower_band
                FROM monthly_with_atr
                WHERE atr IS NOT NULL
            ),
            monthly_final AS (
                SELECT 
                    msc.candle_key_id,
                    CASE 
                        WHEN ABS(msc.close - msc.lower_band) <= ABS(msc.close - msc.upper_band) THEN 
                            ROUND(msc.lower_band::numeric, 2)
                        ELSE 
                            ROUND(msc.upper_band::numeric, 2)
                    END as supertrend_value,
                    CASE 
                        WHEN ABS(msc.close - msc.lower_band) <= ABS(msc.close - msc.upper_band) THEN 1
                        ELSE 0
                    END as direction
                FROM monthly_supertrend_calc msc
            )
            -- Update all daily candles in the same month with the monthly SuperTrend value
            UPDATE daily_candles AS target
            SET indicators = COALESCE(target.indicators, '{}'::jsonb) || 
                jsonb_build_object(
                    v_indicator_key, mf.supertrend_value,
                    v_direction_key, mf.direction
                ),
                updated_at = CURRENT_TIMESTAMP
            FROM monthly_final mf
            INNER JOIN daily_candles dc2 ON dc2.candle_key_id = mf.candle_key_id
            WHERE target.symbol = symbol_rec.symbol
            AND target.monthly_candle_key_id = dc2.monthly_candle_key_id
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

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_weekly_monthly_supertrend(TEXT, INTEGER, NUMERIC, TEXT) TO PUBLIC;