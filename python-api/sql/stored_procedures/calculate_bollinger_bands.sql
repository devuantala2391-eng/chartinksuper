-- =====================================================
-- BOLLINGER BANDS CALCULATION
-- =====================================================
-- Calculates Bollinger Bands for all timeframes (daily, weekly, monthly)
-- Upper Band = SMA + (multiplier × standard deviation)
-- Middle Band = SMA (Simple Moving Average)
-- Lower Band = SMA - (multiplier × standard deviation)
-- =====================================================

-- Helper function for formatting multiplier values in keys
CREATE OR REPLACE FUNCTION format_multiplier_param(value NUMERIC)
RETURNS TEXT AS $$
BEGIN
    IF value = FLOOR(value) THEN
        RETURN FLOOR(value)::TEXT;
    ELSE
        RETURN REPLACE(value::TEXT, '.', 'dot');
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- DAILY BOLLINGER BANDS CALCULATION FOR SINGLE SYMBOL
-- =====================================================
CREATE OR REPLACE FUNCTION calculate_daily_bollinger_bands_for_symbol(
    p_symbol TEXT,
    p_period INTEGER DEFAULT 20,
    p_multiplier NUMERIC DEFAULT 2.0,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
    updated_rows INTEGER,
    execution_time_ms INTEGER,
    status TEXT,
    indicator_key TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_rows INTEGER := 0;
    v_indicator_key TEXT;
    v_existing_count INTEGER;
    v_total_count INTEGER;
    rec RECORD;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'daily_bb_' || p_period || '_' || format_multiplier_param(p_multiplier);

    RAISE NOTICE 'Processing daily Bollinger Bands(%, %) for symbol: %', p_period, p_multiplier, p_symbol;

    -- Check if indicator already exists (unless force recalculate)
    IF NOT p_force_recalculate THEN
        SELECT COUNT(*) INTO v_total_count
        FROM daily_candles
        WHERE symbol = p_symbol;

        SELECT COUNT(*) INTO v_existing_count
        FROM daily_candles
        WHERE symbol = p_symbol
        AND indicators ? v_indicator_key
        AND (indicators->v_indicator_key) IS NOT NULL;

        -- If all rows already have the indicator, skip calculation
        IF v_existing_count = v_total_count AND v_total_count > 0 THEN
            RAISE NOTICE 'Indicator % already exists for all % rows of symbol %, skipping calculation',
                v_indicator_key, v_total_count, p_symbol;

            RETURN QUERY SELECT
                0,
                0,
                'ALREADY_EXISTS'::TEXT,
                v_indicator_key;
            RETURN;
        END IF;
    END IF;

    -- Process candles sequentially for Bollinger Bands calculation
    FOR rec IN
        SELECT
            candle_key_id,
            candle_sequence_number,
            close
        FROM daily_candles
        WHERE symbol = p_symbol
        ORDER BY candle_sequence_number
    LOOP
        DECLARE
            v_sma NUMERIC;
            v_stddev NUMERIC;
            v_upper_band NUMERIC;
            v_middle_band NUMERIC;
            v_lower_band NUMERIC;
            v_bb_data JSONB;
        BEGIN
            -- Calculate SMA and Standard Deviation for the period
            IF rec.candle_sequence_number >= p_period THEN
                -- Calculate SMA and STDDEV using window of p_period candles
                WITH period_data AS (
                    SELECT close
                    FROM daily_candles
                    WHERE symbol = p_symbol
                    AND candle_sequence_number <= rec.candle_sequence_number
                    AND candle_sequence_number > rec.candle_sequence_number - p_period
                    ORDER BY candle_sequence_number
                )
                SELECT
                    AVG(close),
                    STDDEV_POP(close)
                INTO v_sma, v_stddev
                FROM period_data;

                -- Calculate Bollinger Bands
                v_middle_band := v_sma;
                v_upper_band := v_sma + (p_multiplier * v_stddev);
                v_lower_band := v_sma - (p_multiplier * v_stddev);

                -- Create Bollinger Bands JSON object
                v_bb_data := jsonb_build_object(
                    'upper', ROUND(v_upper_band, 2),
                    'middle', ROUND(v_middle_band, 2),
                    'lower', ROUND(v_lower_band, 2)
                );
            ELSE
                -- Not enough data yet
                v_bb_data := NULL;
            END IF;

            -- Update the candle with Bollinger Bands values
            UPDATE daily_candles
            SET indicators = COALESCE(indicators, '{}'::jsonb) ||
                jsonb_build_object(v_indicator_key, v_bb_data),
                updated_at = CURRENT_TIMESTAMP
            WHERE candle_key_id = rec.candle_key_id
            AND (
                p_force_recalculate OR
                NOT (indicators ? v_indicator_key) OR
                (indicators->v_indicator_key) IS NULL
            );

            IF FOUND THEN
                v_updated_rows := v_updated_rows + 1;
            END IF;
        END;
    END LOOP;

    RAISE NOTICE 'Completed daily Bollinger Bands calculation for %: % rows updated in % ms',
        p_symbol, v_updated_rows, EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time);

    RETURN QUERY SELECT
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key;

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Error in calculate_daily_bollinger_bands_for_symbol: %', SQLERRM;
        RETURN QUERY SELECT
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key;
END;
$$;

-- =====================================================
-- WEEKLY BOLLINGER BANDS CALCULATION (MAIN FUNCTION)
-- =====================================================
-- Calculates Bollinger Bands on actual weekly candles, then updates daily candles via sliding window
CREATE OR REPLACE FUNCTION calculate_weekly_bollinger_bands(
    p_period INTEGER DEFAULT 20,
    p_multiplier NUMERIC DEFAULT 2.0,
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_weekly_rows INTEGER,
    updated_daily_rows INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_weekly_rows INTEGER := 0;
    v_updated_daily_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'weekly_bb_' || p_period || '_' || format_multiplier_param(p_multiplier);

    RAISE NOTICE 'Calculating weekly Bollinger Bands(%, %) with daily updates', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM weekly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Calculate Bollinger Bands for weekly candles
        FOR candle_rec IN
            SELECT
                weekly_candle_key_id,
                week_sequence_number,
                close
            FROM weekly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY week_sequence_number
        LOOP
            DECLARE
                v_sma NUMERIC;
                v_stddev NUMERIC;
                v_upper_band NUMERIC;
                v_middle_band NUMERIC;
                v_lower_band NUMERIC;
                v_bb_data JSONB;
            BEGIN
                -- Calculate SMA and Standard Deviation for the period
                IF candle_rec.week_sequence_number >= p_period THEN
                    -- Calculate SMA and STDDEV using window of p_period weeks
                    WITH period_data AS (
                        SELECT close
                        FROM weekly_candles
                        WHERE symbol = symbol_rec.symbol
                        AND week_sequence_number <= candle_rec.week_sequence_number
                        AND week_sequence_number > candle_rec.week_sequence_number - p_period
                        ORDER BY week_sequence_number
                    )
                    SELECT
                        AVG(close),
                        STDDEV_POP(close)
                    INTO v_sma, v_stddev
                    FROM period_data;

                    -- Calculate Bollinger Bands
                    v_middle_band := v_sma;
                    v_upper_band := v_sma + (p_multiplier * v_stddev);
                    v_lower_band := v_sma - (p_multiplier * v_stddev);

                    -- Create Bollinger Bands JSON object
                    v_bb_data := jsonb_build_object(
                        'upper', ROUND(v_upper_band, 2),
                        'middle', ROUND(v_middle_band, 2),
                        'lower', ROUND(v_lower_band, 2)
                    );
                ELSE
                    -- Not enough data yet
                    v_bb_data := NULL;
                END IF;

                -- Store in weekly_candles
                UPDATE weekly_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, v_bb_data),
                    updated_at = CURRENT_TIMESTAMP
                WHERE weekly_candle_key_id = candle_rec.weekly_candle_key_id;

                v_updated_weekly_rows := v_updated_weekly_rows + 1;
            END;
        END LOOP;
    END LOOP;

    -- Update daily candles with sliding window Bollinger Bands
    PERFORM update_daily_weekly_bollinger_bands(p_period, p_multiplier, p_symbol_filter);
    GET DIAGNOSTICS v_updated_daily_rows = ROW_COUNT;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_weekly_rows,
        v_updated_daily_rows,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_weekly_rows,
            v_updated_daily_rows,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- MONTHLY BOLLINGER BANDS CALCULATION (MAIN FUNCTION)
-- =====================================================
-- Calculates Bollinger Bands on actual monthly candles, then updates daily candles via sliding window
CREATE OR REPLACE FUNCTION calculate_monthly_bollinger_bands(
    p_period INTEGER DEFAULT 20,
    p_multiplier NUMERIC DEFAULT 2.0,
    p_symbol_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    processed_symbols INTEGER,
    updated_monthly_rows INTEGER,
    updated_daily_rows INTEGER,
    status TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_start_time TIMESTAMP := clock_timestamp();
    v_updated_monthly_rows INTEGER := 0;
    v_updated_daily_rows INTEGER := 0;
    v_processed_symbols INTEGER := 0;
    v_indicator_key TEXT;
    symbol_rec RECORD;
    candle_rec RECORD;
BEGIN
    -- Generate indicator key
    v_indicator_key := 'monthly_bb_' || p_period || '_' || format_multiplier_param(p_multiplier);

    RAISE NOTICE 'Calculating monthly Bollinger Bands(%, %) with daily updates', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM monthly_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Calculate Bollinger Bands for monthly candles
        FOR candle_rec IN
            SELECT
                monthly_candle_key_id,
                month_sequence_number,
                close
            FROM monthly_candles
            WHERE symbol = symbol_rec.symbol
            ORDER BY month_sequence_number
        LOOP
            DECLARE
                v_sma NUMERIC;
                v_stddev NUMERIC;
                v_upper_band NUMERIC;
                v_middle_band NUMERIC;
                v_lower_band NUMERIC;
                v_bb_data JSONB;
            BEGIN
                -- Calculate SMA and Standard Deviation for the period
                IF candle_rec.month_sequence_number >= p_period THEN
                    -- Calculate SMA and STDDEV using window of p_period months
                    WITH period_data AS (
                        SELECT close
                        FROM monthly_candles
                        WHERE symbol = symbol_rec.symbol
                        AND month_sequence_number <= candle_rec.month_sequence_number
                        AND month_sequence_number > candle_rec.month_sequence_number - p_period
                        ORDER BY month_sequence_number
                    )
                    SELECT
                        AVG(close),
                        STDDEV_POP(close)
                    INTO v_sma, v_stddev
                    FROM period_data;

                    -- Calculate Bollinger Bands
                    v_middle_band := v_sma;
                    v_upper_band := v_sma + (p_multiplier * v_stddev);
                    v_lower_band := v_sma - (p_multiplier * v_stddev);

                    -- Create Bollinger Bands JSON object
                    v_bb_data := jsonb_build_object(
                        'upper', ROUND(v_upper_band, 2),
                        'middle', ROUND(v_middle_band, 2),
                        'lower', ROUND(v_lower_band, 2)
                    );
                ELSE
                    -- Not enough data yet
                    v_bb_data := NULL;
                END IF;

                -- Store in monthly_candles
                UPDATE monthly_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, v_bb_data),
                    updated_at = CURRENT_TIMESTAMP
                WHERE monthly_candle_key_id = candle_rec.monthly_candle_key_id;

                v_updated_monthly_rows := v_updated_monthly_rows + 1;
            END;
        END LOOP;
    END LOOP;

    -- Update daily candles with sliding window Bollinger Bands
    PERFORM update_daily_monthly_bollinger_bands(p_period, p_multiplier, p_symbol_filter);
    GET DIAGNOSTICS v_updated_daily_rows = ROW_COUNT;

    RETURN QUERY SELECT
        v_processed_symbols,
        v_updated_monthly_rows,
        v_updated_daily_rows,
        'SUCCESS'::TEXT;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            v_processed_symbols,
            v_updated_monthly_rows,
            v_updated_daily_rows,
            format('ERROR: %s', SQLERRM)::TEXT;
END;
$$;

-- =====================================================
-- SLIDING WINDOW BOLLINGER BANDS UPDATE FUNCTIONS
-- =====================================================

-- Update daily candles with weekly Bollinger Bands sliding window
CREATE OR REPLACE FUNCTION update_daily_weekly_bollinger_bands(
    p_period INTEGER DEFAULT 20,
    p_multiplier NUMERIC DEFAULT 2.0,
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
    symbol_rec RECORD;
    candle_rec RECORD;
BEGIN
    -- Generate indicator key for daily storage
    v_indicator_key := 'weekly_bb_' || p_period || '_' || format_multiplier_param(p_multiplier);

    RAISE NOTICE 'Updating daily candles with weekly Bollinger Bands(%, %) sliding window using partial week data', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with sliding window weekly Bollinger Bands
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.weekly_candle_key_id,
                dc.weekly_close,
                wc.week_sequence_number
            FROM daily_candles dc
            LEFT JOIN weekly_candles wc ON wc.weekly_candle_key_id = dc.weekly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND wc.week_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        LOOP
            -- Skip candles from first p_period weeks
            IF candle_rec.week_sequence_number < p_period THEN
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, NULL),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Calculate sliding window weekly Bollinger Bands using current week's partial data
            DECLARE
                v_sma NUMERIC;
                v_stddev NUMERIC;
                v_upper_band NUMERIC;
                v_middle_band NUMERIC;
                v_lower_band NUMERIC;
                v_bb_data JSONB;
            BEGIN
                -- Get weekly close prices for the sliding window calculation
                -- This includes the current partial week's close
                WITH period_data AS (
                    SELECT
                        CASE
                            WHEN wc_period.week_sequence_number = candle_rec.week_sequence_number
                            THEN candle_rec.weekly_close  -- Use current partial week close
                            ELSE wc_period.close  -- Use completed week close
                        END as close_price
                    FROM weekly_candles wc_period
                    WHERE wc_period.symbol = symbol_rec.symbol
                    AND wc_period.week_sequence_number <= candle_rec.week_sequence_number
                    AND wc_period.week_sequence_number > candle_rec.week_sequence_number - p_period
                    ORDER BY wc_period.week_sequence_number
                )
                SELECT
                    AVG(close_price),
                    STDDEV_POP(close_price)
                INTO v_sma, v_stddev
                FROM period_data;

                -- Calculate Bollinger Bands
                v_middle_band := v_sma;
                v_upper_band := v_sma + (p_multiplier * v_stddev);
                v_lower_band := v_sma - (p_multiplier * v_stddev);

                -- Create Bollinger Bands JSON object
                v_bb_data := jsonb_build_object(
                    'upper', ROUND(v_upper_band, 2),
                    'middle', ROUND(v_middle_band, 2),
                    'lower', ROUND(v_lower_band, 2)
                );

                -- Store in daily candles
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, v_bb_data),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;

                v_updated_rows := v_updated_rows + 1;
            END;
        END LOOP;
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

-- Update daily candles with monthly Bollinger Bands sliding window
CREATE OR REPLACE FUNCTION update_daily_monthly_bollinger_bands(
    p_period INTEGER DEFAULT 20,
    p_multiplier NUMERIC DEFAULT 2.0,
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
    symbol_rec RECORD;
    candle_rec RECORD;
BEGIN
    -- Generate indicator key for daily storage
    v_indicator_key := 'monthly_bb_' || p_period || '_' || format_multiplier_param(p_multiplier);

    RAISE NOTICE 'Updating daily candles with monthly Bollinger Bands(%, %) sliding window using partial month data', p_period, p_multiplier;

    -- Process each symbol
    FOR symbol_rec IN
        SELECT DISTINCT symbol FROM daily_candles
        WHERE (p_symbol_filter IS NULL OR symbol = p_symbol_filter)
        ORDER BY symbol
    LOOP
        v_processed_symbols := v_processed_symbols + 1;

        -- Update each daily candle with sliding window monthly Bollinger Bands
        FOR candle_rec IN
            SELECT
                dc.candle_key_id,
                dc.candle_sequence_number,
                dc.monthly_candle_key_id,
                dc.monthly_close,
                mc.month_sequence_number
            FROM daily_candles dc
            LEFT JOIN monthly_candles mc ON mc.monthly_candle_key_id = dc.monthly_candle_key_id
            WHERE dc.symbol = symbol_rec.symbol
            AND mc.month_sequence_number IS NOT NULL
            ORDER BY dc.candle_sequence_number
        LOOP
            -- Skip candles from first p_period months
            IF candle_rec.month_sequence_number < p_period THEN
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, NULL),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;
                v_updated_rows := v_updated_rows + 1;
                CONTINUE;
            END IF;

            -- Calculate sliding window monthly Bollinger Bands using current month's partial data
            DECLARE
                v_sma NUMERIC;
                v_stddev NUMERIC;
                v_upper_band NUMERIC;
                v_middle_band NUMERIC;
                v_lower_band NUMERIC;
                v_bb_data JSONB;
            BEGIN
                -- Get monthly close prices for the sliding window calculation
                -- This includes the current partial month's close
                WITH period_data AS (
                    SELECT
                        CASE
                            WHEN mc_period.month_sequence_number = candle_rec.month_sequence_number
                            THEN candle_rec.monthly_close  -- Use current partial month close
                            ELSE mc_period.close  -- Use completed month close
                        END as close_price
                    FROM monthly_candles mc_period
                    WHERE mc_period.symbol = symbol_rec.symbol
                    AND mc_period.month_sequence_number <= candle_rec.month_sequence_number
                    AND mc_period.month_sequence_number > candle_rec.month_sequence_number - p_period
                    ORDER BY mc_period.month_sequence_number
                )
                SELECT
                    AVG(close_price),
                    STDDEV_POP(close_price)
                INTO v_sma, v_stddev
                FROM period_data;

                -- Calculate Bollinger Bands
                v_middle_band := v_sma;
                v_upper_band := v_sma + (p_multiplier * v_stddev);
                v_lower_band := v_sma - (p_multiplier * v_stddev);

                -- Create Bollinger Bands JSON object
                v_bb_data := jsonb_build_object(
                    'upper', ROUND(v_upper_band, 2),
                    'middle', ROUND(v_middle_band, 2),
                    'lower', ROUND(v_lower_band, 2)
                );

                -- Store in daily candles
                UPDATE daily_candles
                SET indicators = COALESCE(indicators, '{}')::jsonb ||
                    jsonb_build_object(v_indicator_key, v_bb_data),
                    updated_at = CURRENT_TIMESTAMP
                WHERE candle_key_id = candle_rec.candle_key_id;

                v_updated_rows := v_updated_rows + 1;
            END;
        END LOOP;
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

-- Grant permissions
GRANT EXECUTE ON FUNCTION calculate_daily_bollinger_bands_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_weekly_bollinger_bands(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_bollinger_bands(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_weekly_bollinger_bands(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_daily_monthly_bollinger_bands(INTEGER, NUMERIC, TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION format_multiplier_param(NUMERIC) TO PUBLIC;