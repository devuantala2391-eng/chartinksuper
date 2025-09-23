-- =====================================================
-- CRON RSI (RELATIVE STRENGTH INDEX) CALCULATION
-- =====================================================
-- Optimized for incremental calculation using previous states
-- Designed for cron job efficiency - updates only latest candle
-- Uses Wilder's smoothing method with state persistence
-- =====================================================

-- =====================================================
-- CRON RSI CALCULATION FOR LATEST CANDLE
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_rsi_for_symbol(
    p_symbol TEXT,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 14
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT,
    rsi_value NUMERIC,
    warning_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_avg_gain_key TEXT;
    v_avg_loss_key TEXT;
    v_previous_avg_gain NUMERIC;
    v_previous_avg_loss NUMERIC;
    v_previous_close NUMERIC;
    v_current_close NUMERIC;
    v_change NUMERIC;
    v_current_gain NUMERIC;
    v_current_loss NUMERIC;
    v_new_avg_gain NUMERIC;
    v_new_avg_loss NUMERIC;
    v_rsi NUMERIC;
    v_alpha NUMERIC;
    v_latest_indicators JSONB;
    v_previous_indicators JSONB;
    v_warning TEXT := NULL;
    v_fallback_used BOOLEAN := FALSE;
BEGIN
    -- Generate indicator keys
    v_indicator_key := p_timeframe || '_rsi_' || p_period;
    v_avg_gain_key := '_' || p_timeframe || '_rsi_' || p_period || '_avg_gain';
    v_avg_loss_key := '_' || p_timeframe || '_rsi_' || p_period || '_avg_loss';

    -- Wilder's smoothing factor
    v_alpha := 1.0 / p_period;

    RAISE NOTICE 'Processing cron RSI(%) for symbol: % [%]', p_period, p_symbol, p_timeframe;

    -- Get latest candle with current indicators
    IF p_timeframe = 'daily' THEN
        SELECT indicators, close INTO v_latest_indicators, v_current_close
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY datetime DESC
        LIMIT 1;
    ELSIF p_timeframe = 'weekly' THEN
        SELECT weekly_close INTO v_current_close
        FROM daily_candles
        WHERE symbol = p_symbol AND weekly_close IS NOT NULL
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
        SELECT monthly_close INTO v_current_close
        FROM daily_candles
        WHERE symbol = p_symbol AND monthly_close IS NOT NULL
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

    -- Try to get previous states from current indicators
    v_previous_avg_gain := (v_latest_indicators ->> v_avg_gain_key)::NUMERIC;
    v_previous_avg_loss := (v_latest_indicators ->> v_avg_loss_key)::NUMERIC;

    -- If states not found, try to get from previous candle
    IF v_previous_avg_gain IS NULL OR v_previous_avg_loss IS NULL THEN
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
            v_previous_avg_gain := (v_previous_indicators ->> v_avg_gain_key)::NUMERIC;
            v_previous_avg_loss := (v_previous_indicators ->> v_avg_loss_key)::NUMERIC;
        END IF;
    ELSE
        -- Get previous close for change calculation
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

    -- If still no states found, calculate from history (fallback)
    IF v_previous_avg_gain IS NULL OR v_previous_avg_loss IS NULL OR v_previous_close IS NULL THEN
        v_warning := 'Missing RSI state, calculating from history for ' || p_symbol || ' [' || p_timeframe || ']';
        v_fallback_used := TRUE;

        -- Call original RSI calculation as fallback
        IF p_timeframe = 'daily' THEN
            PERFORM calculate_daily_rsi_for_symbol(p_symbol, p_period, TRUE);
        ELSIF p_timeframe = 'weekly' THEN
            PERFORM calculate_weekly_rsi_for_symbol(p_symbol, p_period, TRUE);
        ELSIF p_timeframe = 'monthly' THEN
            PERFORM calculate_monthly_rsi_for_symbol(p_symbol, p_period, TRUE);
        END IF;

        -- Get the calculated RSI value and calculate states for future incremental updates
        IF p_timeframe = 'daily' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC, indicators INTO v_rsi, v_latest_indicators
            FROM daily_candles
            WHERE symbol = p_symbol
            ORDER BY datetime DESC
            LIMIT 1;
        ELSIF p_timeframe = 'weekly' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC, indicators INTO v_rsi, v_latest_indicators
            FROM weekly_candles wc
            JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = p_symbol
            ORDER BY dc.datetime DESC
            LIMIT 1;
        ELSIF p_timeframe = 'monthly' THEN
            SELECT (indicators ->> v_indicator_key)::NUMERIC, indicators INTO v_rsi, v_latest_indicators
            FROM monthly_candles mc
            JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = p_symbol
            ORDER BY dc.datetime DESC
            LIMIT 1;
        END IF;

        -- Calculate and save current RSI states for future incremental calculations
        -- Calculate current avg_gain and avg_loss from recent price history
        IF p_timeframe = 'daily' THEN
            -- Calculate average gain/loss from last 14 daily candles
            WITH price_changes AS (
                SELECT
                    close - LAG(close) OVER (ORDER BY datetime) as change
                FROM (
                    SELECT close, datetime
                    FROM daily_candles
                    WHERE symbol = p_symbol
                    ORDER BY datetime DESC
                    LIMIT p_period + 1
                ) recent_prices
                ORDER BY datetime
            )
            SELECT
                AVG(GREATEST(0, change)) as avg_gain,
                AVG(GREATEST(0, -change)) as avg_loss
            INTO v_new_avg_gain, v_new_avg_loss
            FROM price_changes
            WHERE change IS NOT NULL;
        ELSIF p_timeframe = 'weekly' THEN
            -- Calculate from weekly closes
            WITH price_changes AS (
                SELECT
                    weekly_close - LAG(weekly_close) OVER (ORDER BY datetime) as change
                FROM (
                    SELECT weekly_close, datetime
                    FROM daily_candles
                    WHERE symbol = p_symbol AND weekly_close IS NOT NULL
                    ORDER BY datetime DESC
                    LIMIT p_period + 1
                ) recent_prices
                ORDER BY datetime
            )
            SELECT
                AVG(GREATEST(0, change)) as avg_gain,
                AVG(GREATEST(0, -change)) as avg_loss
            INTO v_new_avg_gain, v_new_avg_loss
            FROM price_changes
            WHERE change IS NOT NULL;
        ELSIF p_timeframe = 'monthly' THEN
            -- Calculate from monthly closes
            WITH price_changes AS (
                SELECT
                    monthly_close - LAG(monthly_close) OVER (ORDER BY datetime) as change
                FROM (
                    SELECT monthly_close, datetime
                    FROM daily_candles
                    WHERE symbol = p_symbol AND monthly_close IS NOT NULL
                    ORDER BY datetime DESC
                    LIMIT p_period + 1
                ) recent_prices
                ORDER BY datetime
            )
            SELECT
                AVG(GREATEST(0, change)) as avg_gain,
                AVG(GREATEST(0, -change)) as avg_loss
            INTO v_new_avg_gain, v_new_avg_loss
            FROM price_changes
            WHERE change IS NOT NULL;
        END IF;

        -- Handle null cases
        v_new_avg_gain := COALESCE(v_new_avg_gain, 0);
        v_new_avg_loss := COALESCE(v_new_avg_loss, 0);

        -- Add the state keys to the indicators
        v_latest_indicators := v_latest_indicators ||
                              jsonb_build_object(
                                  v_avg_gain_key, ROUND(v_new_avg_gain, 6),
                                  v_avg_loss_key, ROUND(v_new_avg_loss, 6)
                              );

        -- Update the database with the state keys
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

        v_updated_rows := 1;
    ELSE
        -- Incremental calculation using previous states
        v_change := v_current_close - v_previous_close;
        v_current_gain := GREATEST(0, v_change);
        v_current_loss := GREATEST(0, -v_change);

        -- Apply Wilder's smoothing
        v_new_avg_gain := v_previous_avg_gain + v_alpha * (v_current_gain - v_previous_avg_gain);
        v_new_avg_loss := v_previous_avg_loss + v_alpha * (v_current_loss - v_previous_avg_loss);

        -- Calculate RSI
        IF v_new_avg_loss = 0 THEN
            v_rsi := 100.0;
        ELSE
            v_rsi := 100 - (100 / (1 + (v_new_avg_gain / v_new_avg_loss)));
        END IF;

        -- Update indicators in database
        v_latest_indicators := v_latest_indicators ||
                              jsonb_build_object(
                                  v_indicator_key, ROUND(v_rsi, 2),
                                  v_avg_gain_key, ROUND(v_new_avg_gain, 6),
                                  v_avg_loss_key, ROUND(v_new_avg_loss, 6)
                              );

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
                       ROUND(v_rsi, 2),
                       v_warning;
END;
$$;

-- =====================================================
-- BATCH CRON RSI CALCULATION FOR MULTIPLE SYMBOLS
-- =====================================================
CREATE OR REPLACE FUNCTION cron_calculate_rsi_batch(
    p_symbols TEXT[] DEFAULT NULL,
    p_timeframe TEXT DEFAULT 'daily',
    p_period INTEGER DEFAULT 14
)
RETURNS TABLE(
    symbol TEXT,
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    rsi_value NUMERIC,
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
            SELECT * FROM cron_calculate_rsi_for_symbol(v_symbol, p_timeframe, p_period)
        LOOP
            RETURN QUERY SELECT v_symbol,
                               rec.updated_rows,
                               rec.execution_time_ms,
                               rec.status,
                               rec.rsi_value,
                               rec.warning_message;
        END LOOP;
    END LOOP;
END;
$$;