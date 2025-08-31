-- =====================================================
-- UTILITY FUNCTION FOR FORMATTING INDICATOR KEYS
-- =====================================================
-- Properly formats multipliers and periods for indicator keys
-- Avoids floating point precision issues
-- =====================================================

-- Function to format multiplier for indicator keys
CREATE OR REPLACE FUNCTION format_multiplier_for_key(p_multiplier NUMERIC)
RETURNS TEXT 
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_rounded NUMERIC;
BEGIN
    -- Handle NULL
    IF p_multiplier IS NULL THEN
        RETURN '2';  -- Default multiplier
    END IF;
    
    -- Check if it's effectively an integer
    IF p_multiplier = FLOOR(p_multiplier) THEN
        RETURN FLOOR(p_multiplier)::TEXT;
    END IF;
    
    -- Round to 2 decimal places to avoid floating point precision issues
    v_rounded := ROUND(p_multiplier, 2);
    
    -- Check again if rounded value is an integer
    IF v_rounded = FLOOR(v_rounded) THEN
        RETURN FLOOR(v_rounded)::TEXT;
    ELSE
        -- Format with minimal decimal places and convert to dot notation
        -- Use trim to remove trailing zeros
        RETURN REPLACE(TRIM(TRAILING '0' FROM TRIM(TRAILING '.' FROM v_rounded::TEXT)), '.', 'dot');
    END IF;
END;
$$;

-- Function to format period for indicator keys
CREATE OR REPLACE FUNCTION format_period_for_key(p_period NUMERIC)
RETURNS TEXT 
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    -- Handle NULL
    IF p_period IS NULL THEN
        RETURN '10';  -- Default period
    END IF;
    
    -- Always return as integer
    RETURN FLOOR(p_period)::TEXT;
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION format_multiplier_for_key(NUMERIC) TO PUBLIC;
GRANT EXECUTE ON FUNCTION format_period_for_key(NUMERIC) TO PUBLIC;

-- Test the functions
SELECT 
    format_multiplier_for_key(3.0) as test1,  -- Should return '3'
    format_multiplier_for_key(3.5) as test2,  -- Should return '3dot5'
    format_multiplier_for_key(1.6) as test3,  -- Should return '1dot6'
    format_multiplier_for_key(1.600000000000000088817841970012523233890533447265625) as test4,  -- Should return '1dot6'
    format_multiplier_for_key(2.25) as test5,  -- Should return '2dot25'
    format_period_for_key(10.0) as test6,  -- Should return '10'
    format_period_for_key(14) as test7;  -- Should return '14'