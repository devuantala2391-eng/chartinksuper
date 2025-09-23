-- =====================================================
-- CRON ATR (AVERAGE TRUE RANGE) CALCULATION
-- =====================================================
-- Optimized for incremental calculation using previous ATR values
-- Designed for cron job efficiency - updates only latest candle
-- Uses Wilder's smoothing method: ATR = ((n-1) × Previous_ATR + TR) / n
-- =====================================================

-- =====================================================
-- CRON ATR CALCULATION FOR LATEST CANDLE
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_atr_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 14
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    atr_value NUMERIC,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_previous_atr NUMERIC;
    v_previous_close NUMERIC;
    v_current_high NUMERIC;
    v_current_low NUMERIC;
    v_current_close NUMERIC;
    v_tr1 NUMERIC;
    v_tr2 NUMERIC;
    v_tr3 NUMERIC;
    v_true_range NUMERIC;
    v_new_atr NUMERIC;
    v_latest_indicators JSONB;
    v_previous_indicators JSONB;
    v_warning TEXT := NULL;
    v_fallback_used BOOLEAN := FALSE;
BEGIN
    -- Generate indicator key
    v_indicator_key := p_timeframe || '_atr_' || p_period;

    RAISE NOTICE 'Processing cron ATR(%) for symbol: % [%]', p_period, p_symbol, p_timeframe;

    -- Get latest candle OHLC data
    IF p_timeframe = 'daily' THEN
        SELECT indicators, high, low, close
        INTO v_latest_indicators, v_current_high, v_current_low, v_current_close
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY datetime DESC
        LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT weekly_high, weekly_low, weekly_close
        INTO v_current_high, v_current_low, v_current_close
        FROM daily_candles
        WHERE symbol = p_symbol AND weekly_high IS NOT NULL
        ORDER BY datetime DESC
        LIMIT 1;

        -- Get weekly indicators from weekly_candles table
        SELECT indicators INTO v_latest_indicators
        FROM weekly_candles wc
        JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
        WHERE dc.symbol = p_symbol
        ORDER BY dc.datetime DESC
        LIMIT 1;
    ELSIF p_timeframe = 'monthly' THEN
        SELECT monthly_high, monthly_low, monthly_close
        INTO v_current_high, v_current_low, v_current_close
        FROM daily_candles
        WHERE symbol = p_symbol AND monthly_high IS NOT NULL
        ORDER BY datetime DESC
        LIMIT 1;

        -- Get monthly indicators from monthly_candles table
        SELECT indicators INTO v_latest_indicators
        FROM monthly_candles mc
        JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
        WHERE dc.symbol = p_symbol
        ORDER BY dc.datetime DESC
        LIMIT 1;
    END IF;

    IF v_current_close IS NULL THEN
        RETURN QUERY SELECT 0,
                           EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR',
                           v_indicator_key,
                           NULL::NUMERIC,
                           'No current candle found for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    -- Initialize indicators JSONB if NULL
    IF v_latest_indicators IS NULL THEN
        v_latest_indicators := '{}'::JSONB;
    END IF;

    -- Try to get previous ATR from current indicators
    v_previous_atr := (v_latest_indicators ->> v_indicator_key)::NUMERIC;

    -- If ATR not found, try to get from previous candle
    IF v_previous_atr IS NULL THEN
        IF p_timeframe = 'daily' THEN
            SELECT indicators, close INTO v_previous_indicators, v_previous_close
            FROM daily_candles
            WHERE symbol = p_symbol
            ORDER BY datetime DESC
            OFFSET 1 LIMIT 1;
        ELSIF p_timeframe = 'weekly' THEN
            SELECT weekly_close INTO v_previous_close
            FROM daily_candles
            WHERE symbol = p_symbol AND weekly_close IS NOT NULL
            ORDER BY datetime DESC
            OFFSET 1 LIMIT 1;
        ELSIF p_timeframe = 'monthly' THEN
            SELECT monthly_close INTO v_previous_close
            FROM daily_candles
            WHERE symbol = p_symbol AND monthly_close IS NOT NULL
            ORDER BY datetime DESC
            OFFSET 1 LIMIT 1;
        END IF;

        IF v_previous_indicators IS NOT NULL THEN
            v_previous_atr := (v_previous_indicators ->> v_indicator_key)::NUMERIC;
        END IF;
    ELSE
        -- Get previous close for True Range calculation
        IF p_timeframe = 'daily' THEN
            SELECT close INTO v_previous_close
            FROM daily_candles
            WHERE symbol = p_symbol
            ORDER BY datetime DESC
            OFFSET 1 LIMIT 1;
        ELSIF p_timeframe = 'weekly' THEN
            SELECT weekly_close INTO v_previous_close
            FROM daily_candles
            WHERE symbol = p_symbol AND weekly_close IS NOT NULL
            ORDER BY datetime DESC
            OFFSET 1 LIMIT 1;
        ELSIF p_timeframe = 'monthly' THEN
            SELECT monthly_close INTO v_previous_close
            FROM daily_candles
            WHERE symbol = p_symbol AND monthly_close IS NOT NULL
            ORDER BY datetime DESC
            OFFSET 1 LIMIT 1;
        END IF;
    END IF;

    -- If still no ATR found, calculate from history (fallback)
    IF v_previous_atr IS NULL OR v_previous_close IS NULL THEN
        v_warning := 'Missing ATR state, calculating from history for ' || p_symbol || ' [' || p_timeframe || ']';
        v_fallback_used := TRUE;

        -- Call original ATR calculation as fallback (these functions expect symbol_filter as 2nd param)
        IF p_timeframe = 'daily' THEN
            PERFORM calculate_atr(p_period, p_symbol);
        ELSIF p_timeframe = 'weekly' THEN
            PERFORM calculate_weekly_atr(p_period, p_symbol);
        ELSIF p_timeframe = 'monthly' THEN
            PERFORM calculate_monthly_atr(p_period, p_symbol);
        END IF;

        -- Get the calculated ATR value
        IF p_timeframe = 'daily' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC INTO v_new_atr
            FROM daily_candles
            WHERE symbol = p_symbol
            ORDER BY datetime DESC
            LIMIT 1;
        ELSIF p_timeframe = 'weekly' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC INTO v_new_atr
            FROM weekly_candles wc
            JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = p_symbol
            ORDER BY dc.datetime DESC
            LIMIT 1;
        ELSIF p_timeframe = 'monthly' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC INTO v_new_atr
            FROM monthly_candles mc
            JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = p_symbol
            ORDER BY dc.datetime DESC
            LIMIT 1;
        END IF;

        v_updated_rows := 1;
    ELSE
        -- Incremental calculation using previous ATR
        -- Calculate True Range: MAX(H-L, |H-Prev_C|, |L-Prev_C|)
        v_tr1 := v_current_high - v_current_low;
        v_tr2 := ABS(v_current_high - v_previous_close);
        v_tr3 := ABS(v_current_low - v_previous_close);
        v_true_range := GREATEST(v_tr1, v_tr2, v_tr3);

        -- Apply Wilder's smoothing: ATR = ((n-1) × Previous_ATR + TR) / n
        v_new_atr := ((p_period - 1) * v_previous_atr + v_true_range) / p_period;

        -- Update indicators in database
        v_latest_indicators := v_latest_indicators ||
                              jsonb_build_object(v_indicator_key, ROUND(v_new_atr, 2));

        -- Update appropriate table
        IF p_timeframe = 'daily' THEN
            UPDATE daily_candles
            SET indicators = v_latest_indicators,
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = p_symbol
            AND datetime = (SELECT MAX(datetime) FROM daily_candles WHERE symbol = p_symbol);
        ELSIF p_timeframe = 'weekly' THEN
            UPDATE weekly_candles
            SET indicators = v_latest_indicators,
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = (
                SELECT weekly_candle_key_id FROM daily_candles
                WHERE symbol = p_symbol
                ORDER BY datetime DESC LIMIT 1
            );
        ELSIF p_timeframe = 'monthly' THEN
            UPDATE monthly_candles
            SET indicators = v_latest_indicators,
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = (
                SELECT monthly_candle_key_id FROM daily_candles
                WHERE symbol = p_symbol
                ORDER BY datetime DESC LIMIT 1
            );
        END IF;

        GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    END IF;

    RETURN QUERY SELECT v_updated_rows,
                       EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                       CASE WHEN v_fallback_used THEN 'FALLBACK' ELSE 'SUCCESS' END,
                       v_indicator_key,
                       ROUND(v_new_atr, 2),
                       v_warning;
END;
$$;

-- =====================================================
-- BATCH CRON ATR CALCULATION FOR MULTIPLE SYMBOLS
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_atr_batch(
    p_symbols TEXT[] DEFAULT NULL,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 14
)
RETURNS TABLE(
    symbol TEXT,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    atr_value NUMERIC,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_symbol TEXT;
    v_symbols TEXT[];
    rec RECORD;
BEGIN
    -- Get symbols to process
    IF p_symbols IS NULL THEN
        SELECT array_agg(DISTINCT daily_candles.symbol ORDER BY daily_candles.symbol)
        INTO v_symbols
        FROM daily_candles;
    ELSE
        v_symbols := p_symbols;
    END IF;

    -- Process each symbol
    FOREACH v_symbol IN ARRAY v_symbols
    LOOP
        FOR rec IN
            SELECT * FROM cron_calculate_atr_for_symbol(v_symbol, p_timeframe, p_period)
        LOOP
            RETURN QUERY SELECT v_symbol,
                               rec.updated_rows,
                               rec.execution_time_ms,
                               rec.status,
                               rec.atr_value,
                               rec.warning_message;
        END LOOP;
    END LOOP;
END;
$$;