-- =====================================================
-- REMAINING CRON INDICATOR CALCULATIONS
-- =====================================================
-- SMA, Bollinger Bands, SuperTrend, Percentage Change
-- Optimized for incremental calculation efficiency
-- =====================================================

-- =====================================================
-- CRON SMA (SIMPLE MOVING AVERAGE) CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_sma_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 20
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    sma_value NUMERIC,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_indicator_key TEXT;
    v_sma NUMERIC;
    v_latest_indicators JSONB;
    v_count INTEGER;
BEGIN
    v_indicator_key := p_timeframe || '_sma_' || p_period;

    -- Get last 'period' candles and calculate SMA
    IF p_timeframe = 'daily' THEN
        SELECT AVG(close), COUNT(*) INTO v_sma, v_count
        FROM (SELECT close FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT p_period) sub;

        SELECT indicators INTO v_latest_indicators
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT AVG(weekly_close), COUNT(*) INTO v_sma, v_count
        FROM (SELECT weekly_close FROM daily_candles WHERE symbol = p_symbol AND weekly_close IS NOT NULL ORDER BY datetime DESC LIMIT p_period) sub;

        SELECT indicators INTO v_latest_indicators
        FROM weekly_candles wc JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'monthly' THEN
        SELECT AVG(monthly_close), COUNT(*) INTO v_sma, v_count
        FROM (SELECT monthly_close FROM daily_candles WHERE symbol = p_symbol AND monthly_close IS NOT NULL ORDER BY datetime DESC LIMIT p_period) sub;

        SELECT indicators INTO v_latest_indicators
        FROM monthly_candles mc JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    END IF;

    IF v_count < p_period THEN
        RETURN QUERY SELECT 0, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR', v_indicator_key, NULL::NUMERIC,
                           'Insufficient data for SMA(' || p_period || ') for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    IF v_latest_indicators IS NULL THEN v_latest_indicators := '{}'::JSONB; END IF;

    -- Update indicators
    v_latest_indicators := v_latest_indicators || jsonb_build_object(v_indicator_key, ROUND(v_sma, 2));

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

    RETURN QUERY SELECT 1,
                       EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                       'SUCCESS',
                       v_indicator_key,
                       ROUND(v_sma, 2),
                       NULL::TEXT;
END;
$$;

-- =====================================================
-- CRON BOLLINGER BANDS CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_bollinger_bands_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 20,
    p_multiplier NUMERIC DEFAULT 2.0
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    bb_value TEXT,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_indicator_key TEXT;
    v_sma NUMERIC;
    v_stddev NUMERIC;
    v_upper NUMERIC;
    v_lower NUMERIC;
    v_latest_indicators JSONB;
    v_count INTEGER;
    v_multiplier_str TEXT;
BEGIN
    v_multiplier_str := format_multiplier_param(p_multiplier);
    v_indicator_key := p_timeframe || '_bb_' || p_period || '_' || v_multiplier_str;

    -- Get last 'period' candles and calculate SMA and standard deviation
    IF p_timeframe = 'daily' THEN
        SELECT AVG(close), STDDEV_POP(close), COUNT(*) INTO v_sma, v_stddev, v_count
        FROM (SELECT close FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT p_period) sub;

        SELECT indicators INTO v_latest_indicators
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT AVG(weekly_close), STDDEV_POP(weekly_close), COUNT(*) INTO v_sma, v_stddev, v_count
        FROM (SELECT weekly_close FROM daily_candles WHERE symbol = p_symbol AND weekly_close IS NOT NULL ORDER BY datetime DESC LIMIT p_period) sub;

        SELECT indicators INTO v_latest_indicators
        FROM weekly_candles wc JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'monthly' THEN
        SELECT AVG(monthly_close), STDDEV_POP(monthly_close), COUNT(*) INTO v_sma, v_stddev, v_count
        FROM (SELECT monthly_close FROM daily_candles WHERE symbol = p_symbol AND monthly_close IS NOT NULL ORDER BY datetime DESC LIMIT p_period) sub;

        SELECT indicators INTO v_latest_indicators
        FROM monthly_candles mc JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    END IF;

    IF v_count < p_period THEN
        RETURN QUERY SELECT 0, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR', v_indicator_key, NULL::TEXT,
                           'Insufficient data for BB(' || p_period || ',' || p_multiplier || ') for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    -- Calculate bands
    v_upper := v_sma + (p_multiplier * v_stddev);
    v_lower := v_sma - (p_multiplier * v_stddev);

    IF v_latest_indicators IS NULL THEN v_latest_indicators := '{}'::JSONB; END IF;

    -- Update indicators
    v_latest_indicators := v_latest_indicators || jsonb_build_object(
        v_indicator_key, jsonb_build_object(
            'upper', ROUND(v_upper, 2),
            'middle', ROUND(v_sma, 2),
            'lower', ROUND(v_lower, 2)
        )
    );

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

    RETURN QUERY SELECT 1,
                       EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                       'SUCCESS',
                       v_indicator_key,
                       'U:' || ROUND(v_upper, 2)::TEXT || ' M:' || ROUND(v_sma, 2)::TEXT || ' L:' || ROUND(v_lower, 2)::TEXT,
                       NULL::TEXT;
END;
$$;

-- =====================================================
-- CRON PERCENTAGE CHANGE CALCULATION
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_percentage_change_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily'
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    percentage_value NUMERIC,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_indicator_key TEXT;
    v_current_close NUMERIC;
    v_previous_close NUMERIC;
    v_percentage_change NUMERIC;
    v_latest_indicators JSONB;
BEGIN
    v_indicator_key := p_timeframe || '_percentage_change';

    -- Get current and previous close
    IF p_timeframe = 'daily' THEN
        SELECT close INTO v_current_close
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;

        SELECT close INTO v_previous_close
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC OFFSET 1 LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT weekly_close INTO v_current_close
        FROM daily_candles WHERE symbol = p_symbol AND weekly_close IS NOT NULL ORDER BY datetime DESC LIMIT 1;

        SELECT weekly_close INTO v_previous_close
        FROM daily_candles WHERE symbol = p_symbol AND weekly_close IS NOT NULL ORDER BY datetime DESC OFFSET 1 LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM weekly_candles wc JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'monthly' THEN
        SELECT monthly_close INTO v_current_close
        FROM daily_candles WHERE symbol = p_symbol AND monthly_close IS NOT NULL ORDER BY datetime DESC LIMIT 1;

        SELECT monthly_close INTO v_previous_close
        FROM daily_candles WHERE symbol = p_symbol AND monthly_close IS NOT NULL ORDER BY datetime DESC OFFSET 1 LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM monthly_candles mc JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    END IF;

    IF v_current_close IS NULL OR v_previous_close IS NULL OR v_previous_close = 0 THEN
        RETURN QUERY SELECT 0, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR', v_indicator_key, NULL::NUMERIC,
                           'Insufficient data for percentage change for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    -- Calculate percentage change
    v_percentage_change := ((v_current_close - v_previous_close) / v_previous_close) * 100;

    IF v_latest_indicators IS NULL THEN v_latest_indicators := '{}'::JSONB; END IF;

    -- Update indicators
    v_latest_indicators := v_latest_indicators || jsonb_build_object(v_indicator_key, ROUND(v_percentage_change, 2));

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

    RETURN QUERY SELECT 1,
                       EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                       'SUCCESS',
                       v_indicator_key,
                       ROUND(v_percentage_change, 2),
                       NULL::TEXT;
END;
$$;

-- =====================================================
-- CRON SUPERTREND CALCULATION (depends on ATR)
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_supertrend_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 10,
    p_multiplier NUMERIC DEFAULT 2.0
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    supertrend_value TEXT,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_upper_band_key TEXT;
    v_lower_band_key TEXT;
    v_atr_key TEXT;
    v_current_atr NUMERIC;
    v_current_high NUMERIC;
    v_current_low NUMERIC;
    v_current_close NUMERIC;
    v_previous_close NUMERIC;
    v_previous_st NUMERIC;
    v_previous_direction INTEGER;
    v_previous_upper_band NUMERIC;
    v_previous_lower_band NUMERIC;
    v_hl2 NUMERIC;
    v_basic_upper_band NUMERIC;
    v_basic_lower_band NUMERIC;
    v_final_upper_band NUMERIC;
    v_final_lower_band NUMERIC;
    v_supertrend NUMERIC;
    v_direction INTEGER;
    v_latest_indicators JSONB;
    v_multiplier_str TEXT;
    v_warning TEXT := NULL;
    v_fallback_used BOOLEAN := FALSE;
BEGIN
    v_multiplier_str := replace(p_multiplier::TEXT, '.', '_');
    v_indicator_key := p_timeframe || '_supertrend_' || p_period || '_' || v_multiplier_str;
    v_direction_key := v_indicator_key || '_direction';
    v_upper_band_key := '_' || v_indicator_key || '_upper_band';
    v_lower_band_key := '_' || v_indicator_key || '_lower_band';
    v_atr_key := p_timeframe || '_atr_' || p_period;

    -- Get current candle data and indicators
    IF p_timeframe = 'daily' THEN
        SELECT indicators, high, low, close
        INTO v_latest_indicators, v_current_high, v_current_low, v_current_close
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC LIMIT 1;

        SELECT close INTO v_previous_close
        FROM daily_candles WHERE symbol = p_symbol ORDER BY datetime DESC OFFSET 1 LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT weekly_high, weekly_low, weekly_close
        INTO v_current_high, v_current_low, v_current_close
        FROM daily_candles WHERE symbol = p_symbol AND weekly_high IS NOT NULL ORDER BY datetime DESC LIMIT 1;

        SELECT weekly_close INTO v_previous_close
        FROM daily_candles WHERE symbol = p_symbol AND weekly_close IS NOT NULL ORDER BY datetime DESC OFFSET 1 LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM weekly_candles wc JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    ELSIF p_timeframe = 'monthly' THEN
        SELECT monthly_high, monthly_low, monthly_close
        INTO v_current_high, v_current_low, v_current_close
        FROM daily_candles WHERE symbol = p_symbol AND monthly_high IS NOT NULL ORDER BY datetime DESC LIMIT 1;

        SELECT monthly_close INTO v_previous_close
        FROM daily_candles WHERE symbol = p_symbol AND monthly_close IS NOT NULL ORDER BY datetime DESC OFFSET 1 LIMIT 1;

        SELECT indicators INTO v_latest_indicators
        FROM monthly_candles mc JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
        WHERE dc.symbol = p_symbol ORDER BY dc.datetime DESC LIMIT 1;
    END IF;

    IF v_current_close IS NULL OR v_previous_close IS NULL THEN
        RETURN QUERY SELECT 0, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR', v_indicator_key, NULL::TEXT,
                           'Insufficient data for SuperTrend for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    IF v_latest_indicators IS NULL THEN v_latest_indicators := '{}'::JSONB; END IF;

    -- Get current ATR (should be calculated first due to dependency)
    v_current_atr := (v_latest_indicators ->> v_atr_key)::NUMERIC;

    IF v_current_atr IS NULL THEN
        RETURN QUERY SELECT 0, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                           'ERROR', v_indicator_key, NULL::TEXT,
                           'ATR not available for SuperTrend for ' || p_symbol || ' [' || p_timeframe || ']';
        RETURN;
    END IF;

    -- Get previous SuperTrend states
    v_previous_st := (v_latest_indicators ->> v_indicator_key)::NUMERIC;
    v_previous_direction := (v_latest_indicators ->> v_direction_key)::INTEGER;
    v_previous_upper_band := (v_latest_indicators ->> v_upper_band_key)::NUMERIC;
    v_previous_lower_band := (v_latest_indicators ->> v_lower_band_key)::NUMERIC;

    -- If missing states, use fallback or initialize
    IF v_previous_st IS NULL OR v_previous_direction IS NULL OR
       v_previous_upper_band IS NULL OR v_previous_lower_band IS NULL THEN
        v_warning := 'Missing SuperTrend state, using simplified calculation for ' || p_symbol || ' [' || p_timeframe || ']';

        -- Calculate basic SuperTrend (simplified initialization)
        v_hl2 := (v_current_high + v_current_low) / 2.0;
        v_final_upper_band := v_hl2 + (p_multiplier * v_current_atr);
        v_final_lower_band := v_hl2 - (p_multiplier * v_current_atr);

        -- Simple initialization: assume uptrend
        v_supertrend := v_final_lower_band;
        v_direction := 1;
    ELSE
        -- Full SuperTrend calculation with band persistence
        v_hl2 := (v_current_high + v_current_low) / 2.0;
        v_basic_upper_band := v_hl2 + (p_multiplier * v_current_atr);
        v_basic_lower_band := v_hl2 - (p_multiplier * v_current_atr);

        -- Band persistence logic
        -- Upper band can only move down or stay same
        IF v_basic_upper_band < v_previous_upper_band OR v_previous_close <= v_previous_upper_band THEN
            v_final_upper_band := v_basic_upper_band;
        ELSE
            v_final_upper_band := v_previous_upper_band;
        END IF;

        -- Lower band can only move up or stay same
        IF v_basic_lower_band > v_previous_lower_band OR v_previous_close >= v_previous_lower_band THEN
            v_final_lower_band := v_basic_lower_band;
        ELSE
            v_final_lower_band := v_previous_lower_band;
        END IF;

        -- Determine SuperTrend value and direction
        IF v_previous_st = v_previous_upper_band THEN
            -- Was in downtrend
            IF v_current_close <= v_final_lower_band THEN
                v_supertrend := v_final_upper_band;
                v_direction := -1;
            ELSE
                v_supertrend := v_final_lower_band;
                v_direction := 1;
            END IF;
        ELSE
            -- Was in uptrend
            IF v_current_close >= v_final_upper_band THEN
                v_supertrend := v_final_lower_band;
                v_direction := 1;
            ELSE
                v_supertrend := v_final_upper_band;
                v_direction := -1;
            END IF;
        END IF;
    END IF;

    -- Update indicators
    v_latest_indicators := v_latest_indicators || jsonb_build_object(
        v_indicator_key, ROUND(v_supertrend, 2),
        v_direction_key, v_direction,
        v_upper_band_key, ROUND(v_final_upper_band, 2),
        v_lower_band_key, ROUND(v_final_lower_band, 2)
    );

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

    RETURN QUERY SELECT 1,
                       EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
                       'SUCCESS',
                       v_indicator_key,
                       ROUND(v_supertrend, 2)::TEXT || ' (' || (CASE WHEN v_direction = 1 THEN 'UP' ELSE 'DOWN' END) || ')',
                       v_warning;
END;
$$;