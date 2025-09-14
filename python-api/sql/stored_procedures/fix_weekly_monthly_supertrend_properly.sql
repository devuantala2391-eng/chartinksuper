-- =====================================================
-- PROPERLY FIXED WEEKLY SUPERTREND CALCULATION
-- =====================================================
-- This version only calculates once per week change, not every daily candle
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_weekly_supertrend_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
    p_multiplier NUMERIC,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
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
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_atr_key TEXT;
    rec RECORD;
    v_final_upper NUMERIC := NULL;
    v_final_lower NUMERIC := NULL;
    v_trend INTEGER := NULL;
    v_prev_week_key TEXT := NULL;
    v_current_supertrend NUMERIC;
    v_current_direction INTEGER;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'weekly_supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'weekly_atr_' || p_period;

    RAISE NOTICE 'Processing weekly SuperTrend(%, %) for symbol: %', p_period, p_multiplier, p_symbol;

    -- Process candles, but only calculate SuperTrend when week changes
    FOR rec IN
        SELECT
            candle_key_id,
            candle_sequence_number,
            weekly_candle_key_id,
            weekly_high as high,
            weekly_low as low,
            weekly_close as close,
            (indicators->v_atr_key)::numeric as atr
        FROM daily_candles
        WHERE symbol = p_symbol
        AND weekly_high IS NOT NULL
        AND weekly_low IS NOT NULL
        AND weekly_close IS NOT NULL
        AND indicators ? v_atr_key
        AND (indicators->v_atr_key) IS NOT NULL
        ORDER BY candle_sequence_number
    LOOP
        -- Only recalculate when we enter a new week
        IF v_prev_week_key IS NULL OR v_prev_week_key != rec.weekly_candle_key_id THEN
            DECLARE
                v_hl2 NUMERIC := (rec.high + rec.low) / 2.0;
                v_basic_upper NUMERIC := v_hl2 + (p_multiplier * rec.atr);
                v_basic_lower NUMERIC := v_hl2 - (p_multiplier * rec.atr);
            BEGIN
                -- Apply band persistence logic
                IF v_final_upper IS NULL THEN
                    -- First week
                    v_final_upper := v_basic_upper;
                    v_final_lower := v_basic_lower;
                ELSE
                    -- Band persistence based on current trend
                    IF v_trend IS NULL OR v_trend = 0 THEN
                        -- Downtrend: Upper band can only decrease or stay same
                        IF v_basic_upper < v_final_upper THEN
                            v_final_upper := v_basic_upper;
                        END IF;
                        -- Lower band resets
                        v_final_lower := v_basic_lower;
                    ELSE
                        -- Uptrend: Lower band can only increase or stay same
                        IF v_basic_lower > v_final_lower THEN
                            v_final_lower := v_basic_lower;
                        END IF;
                        -- Upper band resets
                        v_final_upper := v_basic_upper;
                    END IF;
                END IF;

                -- Determine trend
                IF v_trend IS NULL THEN
                    -- Initial trend: Use HL2 to determine if we're in uptrend or downtrend
                    v_current_direction := CASE WHEN rec.close > v_hl2 THEN 1 ELSE 0 END;
                ELSE
                    IF v_trend = 1 THEN
                        IF rec.close <= v_final_lower THEN
                            v_current_direction := 0;
                        ELSE
                            v_current_direction := 1;
                        END IF;
                    ELSE
                        IF rec.close >= v_final_upper THEN
                            v_current_direction := 1;
                        ELSE
                            v_current_direction := 0;
                        END IF;
                    END IF;
                END IF;

                -- SuperTrend value
                IF v_current_direction = 1 THEN
                    v_current_supertrend := ROUND(v_final_lower, 2);
                ELSE
                    v_current_supertrend := ROUND(v_final_upper, 2);
                END IF;

                -- Update trend for next iteration
                v_trend := v_current_direction;
                v_prev_week_key := rec.weekly_candle_key_id;
            END;
        END IF;

        -- Update every daily candle with the current week's SuperTrend
        UPDATE daily_candles
        SET indicators = COALESCE(indicators, '{}'::jsonb) ||
            jsonb_build_object(
                v_indicator_key, v_current_supertrend,
                v_direction_key, v_current_direction
            ),
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
    END LOOP;

    RETURN QUERY SELECT
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key,
        v_direction_key;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;

-- =====================================================
-- PROPERLY FIXED MONTHLY SUPERTREND CALCULATION
-- =====================================================
-- This version only calculates once per month change, not every daily candle
-- =====================================================

CREATE OR REPLACE FUNCTION calculate_monthly_supertrend_for_symbol(
    p_symbol TEXT,
    p_period INTEGER,
    p_multiplier NUMERIC,
    p_force_recalculate BOOLEAN DEFAULT FALSE
)
RETURNS TABLE(
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
    v_indicator_key TEXT;
    v_direction_key TEXT;
    v_atr_key TEXT;
    rec RECORD;
    v_final_upper NUMERIC := NULL;
    v_final_lower NUMERIC := NULL;
    v_trend INTEGER := NULL;
    v_prev_month_key TEXT := NULL;
    v_current_supertrend NUMERIC;
    v_current_direction INTEGER;
BEGIN
    -- Generate indicator keys
    v_indicator_key := 'monthly_supertrend_' || p_period || '_' || format_decimal_param(p_multiplier);
    v_direction_key := v_indicator_key || '_direction';
    v_atr_key := 'monthly_atr_' || p_period;

    RAISE NOTICE 'Processing monthly SuperTrend(%, %) for symbol: %', p_period, p_multiplier, p_symbol;

    -- Process candles, but only calculate SuperTrend when month changes
    FOR rec IN
        SELECT
            candle_key_id,
            candle_sequence_number,
            monthly_candle_key_id,
            monthly_high as high,
            monthly_low as low,
            monthly_close as close,
            (indicators->v_atr_key)::numeric as atr
        FROM daily_candles
        WHERE symbol = p_symbol
        AND monthly_high IS NOT NULL
        AND monthly_low IS NOT NULL
        AND monthly_close IS NOT NULL
        AND indicators ? v_atr_key
        AND (indicators->v_atr_key) IS NOT NULL
        ORDER BY candle_sequence_number
    LOOP
        -- Only recalculate when we enter a new month
        IF v_prev_month_key IS NULL OR v_prev_month_key != rec.monthly_candle_key_id THEN
            DECLARE
                v_hl2 NUMERIC := (rec.high + rec.low) / 2.0;
                v_basic_upper NUMERIC := v_hl2 + (p_multiplier * rec.atr);
                v_basic_lower NUMERIC := v_hl2 - (p_multiplier * rec.atr);
            BEGIN
                -- Apply band persistence logic
                IF v_final_upper IS NULL THEN
                    -- First month
                    v_final_upper := v_basic_upper;
                    v_final_lower := v_basic_lower;
                ELSE
                    -- Band persistence based on current trend
                    IF v_trend IS NULL OR v_trend = 0 THEN
                        -- Downtrend: Upper band can only decrease or stay same
                        IF v_basic_upper < v_final_upper THEN
                            v_final_upper := v_basic_upper;
                        END IF;
                        -- Lower band resets
                        v_final_lower := v_basic_lower;
                    ELSE
                        -- Uptrend: Lower band can only increase or stay same
                        IF v_basic_lower > v_final_lower THEN
                            v_final_lower := v_basic_lower;
                        END IF;
                        -- Upper band resets
                        v_final_upper := v_basic_upper;
                    END IF;
                END IF;

                -- Determine trend
                IF v_trend IS NULL THEN
                    -- Initial trend: Use HL2 to determine if we're in uptrend or downtrend
                    v_current_direction := CASE WHEN rec.close > v_hl2 THEN 1 ELSE 0 END;
                ELSE
                    IF v_trend = 1 THEN
                        IF rec.close <= v_final_lower THEN
                            v_current_direction := 0;
                        ELSE
                            v_current_direction := 1;
                        END IF;
                    ELSE
                        IF rec.close >= v_final_upper THEN
                            v_current_direction := 1;
                        ELSE
                            v_current_direction := 0;
                        END IF;
                    END IF;
                END IF;

                -- SuperTrend value
                IF v_current_direction = 1 THEN
                    v_current_supertrend := ROUND(v_final_lower, 2);
                ELSE
                    v_current_supertrend := ROUND(v_final_upper, 2);
                END IF;

                -- Update trend for next iteration
                v_trend := v_current_direction;
                v_prev_month_key := rec.monthly_candle_key_id;
            END;
        END IF;

        -- Update every daily candle with the current month's SuperTrend
        UPDATE daily_candles
        SET indicators = COALESCE(indicators, '{}'::jsonb) ||
            jsonb_build_object(
                v_indicator_key, v_current_supertrend,
                v_direction_key, v_current_direction
            ),
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
    END LOOP;

    RETURN QUERY SELECT
        v_updated_rows,
        EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
        'SUCCESS'::TEXT,
        v_indicator_key,
        v_direction_key;

EXCEPTION
    WHEN OTHERS THEN
        RETURN QUERY SELECT
            0,
            EXTRACT(MILLISECONDS FROM clock_timestamp() - v_start_time)::INTEGER,
            ('ERROR: ' || SQLERRM)::TEXT,
            v_indicator_key,
            v_direction_key;
END;
$$;

GRANT EXECUTE ON FUNCTION calculate_weekly_supertrend_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;
GRANT EXECUTE ON FUNCTION calculate_monthly_supertrend_for_symbol(TEXT, INTEGER, NUMERIC, BOOLEAN) TO PUBLIC;