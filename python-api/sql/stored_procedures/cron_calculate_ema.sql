-- =====================================================
-- CRON EMA (EXPONENTIAL MOVING AVERAGE) CALCULATION
-- =====================================================
-- Optimized for incremental calculation using previous EMA values
-- Uses exponential smoothing: EMA = (Price × α) + (Previous_EMA × (1-α))
-- Where α = 2/(period + 1)
-- =====================================================

CREATE OR REPLACE FUNCTION cron_calculate_ema_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 20
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    ema_value NUMERIC,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_previous_ema NUMERIC;
    v_current_close NUMERIC;
    v_new_ema NUMERIC;
    v_alpha NUMERIC;
    v_latest_indicators JSONB;
    v_previous_indicators JSONB;
    v_warning TEXT := NULL;
    v_fallback_used BOOLEAN := FALSE;
BEGIN
    -- Generate indicator key
    v_indicator_key := p_timeframe || '_ema_' || p_period;
    v_alpha := 2.0 / (p_period + 1);

    -- Get latest candle data
    IF p_timeframe = 'daily' THEN
        SELECT indicators, close INTO v_latest_indicators, v_current_close
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT weekly_close INTO v_current_close
        FROM daily_candles WHERE symbol = p_symbol AND weekly_close IS NOT NULL
        ORDER BY datetime DESC LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM weekly_candles wc JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'monthly' THEN
        SELECT monthly_close INTO v_current_close
        FROM daily_candles WHERE symbol = p_symbol AND monthly_close IS NOT NULL
        ORDER BY datetime DESC LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM monthly_candles mc JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    END IF;

    IF v_current_close IS NULL THEN
        RETURN QUERY SELECT 0, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR', v_indicator_key, NULL::NUMERIC,
                           'No current candle found for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    IF v_latest_indicators IS NULL THEN v_latest_indicators := '{}'::JSONB; END IF;

    -- Try to get previous EMA
    v_previous_ema := (v_latest_indicators ->> v_indicator_key)::NUMERIC;

    IF v_previous_ema IS NULL THEN
        -- Try from previous candle
        IF p_timeframe = 'daily' THEN
            SELECT indicators INTO v_previous_indicators
            FROM daily_candles WHERE symbol = p_symbol
            ORDER BY datetime DESC OFFSET 1 LIMIT 1;
        END IF;

        IF v_previous_indicators IS NOT NULL THEN
            v_previous_ema := (v_previous_indicators ->> v_indicator_key)::NUMERIC;
        END IF;
    END IF;

    -- If still no EMA found, calculate from history
    IF v_previous_ema IS NULL THEN
        v_warning := 'Missing EMA state, calculating from history for ' || p_symbol || ' [' || p_timeframe || ']';
        v_fallback_used := TRUE;

        -- Call original EMA calculation as fallback
        IF p_timeframe = 'daily' THEN
            PERFORM calculate_daily_ema_for_symbol(p_symbol, p_period, TRUE);
        END IF;

        -- Get the calculated EMA value
        IF p_timeframe = 'daily' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC INTO v_new_ema
            FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;
        END IF;

        v_updated_rows := 1;
    ELSE
        -- Incremental calculation: EMA = (Price × α) + (Previous_EMA × (1-α))
        v_new_ema := (v_current_close * v_alpha) + (v_previous_ema * (1 - v_alpha));

        -- Update indicators
        v_latest_indicators := v_latest_indicators ||
                              jsonb_build_object(v_indicator_key, ROUND(v_new_ema, 2));

        -- Update appropriate table
        IF p_timeframe = 'daily' THEN
            UPDATE daily_candles SET indicators = v_latest_indicators, updated_at = CURRENT_TIMESTAMP
            WHERE symbol = p_symbol AND datetime = (SELECT MAX(datetime) FROM daily_candles WHERE symbol = p_symbol);
        ELSIF p_timeframe = 'weekly' THEN
            UPDATE weekly_candles SET indicators = v_latest_indicators, updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = (SELECT weekly_candle_key_id FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1);
        ELSIF p_timeframe = 'monthly' THEN
            UPDATE monthly_candles SET indicators = v_latest_indicators, updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = (SELECT monthly_candle_key_id FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1);
        END IF;

        GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    END IF;

    RETURN QUERY SELECT v_updated_rows,
                       EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                       CASE WHEN v_fallback_used THEN 'FALLBACK' ELSE 'SUCCESS' END,
                       v_indicator_key,
                       ROUND(v_new_ema, 2),
                       v_warning;
END;
$$;