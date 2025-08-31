# Query Flow Analysis - Complete Mapping

## 1. Query Flow Sequence
1. **API Endpoint** (`main.py`) → Receives query string
2. **Query Parser** (`query_service.py::parse_query`) → Parses query string into conditions
3. **Field Resolution** (`query_service.py::resolve_field_name`) → Normalizes field names 
4. **Query Validator** (`highspeed_query_validator.py`) → Validates fields exist
5. **Field Normalization** (`_normalize_field_name`) → Normalizes for database lookup
6. **Missing Field Detection** → Identifies missing indicators
7. **Indicator Parser** (`_parse_indicator_from_field`) → Parses indicator definition
8. **Dynamic Calculator** (`dynamic_indicator_manager.py`) → Auto-calculates missing
9. **Database Query** → Executes final query

## 2. Current Issues Identified

### Issue 1: Query Parser Field Resolution
**Location**: `query_service.py::resolve_field_name` (lines 89-166)
- When query is `weekly_supertrend_10_2 < 100`
- It strips "weekly_" prefix (line 128-130) 
- Returns `supertrend_10_2` instead of `weekly_supertrend_10_2`

### Issue 2: Validator Field Normalization  
**Location**: `highspeed_query_validator.py::_normalize_field_name` (lines 105-160)
- Line 130: `field_name = re.sub(r'^daily_', '', field_name)`
- This removes "daily_" prefix from ALL indicators
- Should only remove for backward compatibility, not new prefixed format

### Issue 3: Indicator Parser Timeframe Detection
**Location**: `highspeed_query_validator.py::_parse_indicator_from_field` (lines 249-350)
- Line 295-312: When field is `supertrend_10_2` (without prefix)
- Always defaults to "daily" timeframe
- Doesn't preserve original timeframe from query

### Issue 4: Missing Timeframe Context
- When validator strips prefixes, it loses timeframe information
- Auto-calculation then defaults to daily instead of intended timeframe

## 3. Required Fixes

### Fix A: Update resolve_field_name in query_service.py
- Keep timeframe prefixes for all indicators
- Only strip prefix for backward compatibility when needed

### Fix B: Update _normalize_field_name in validator
- Don't strip timeframe prefixes for new format
- Preserve weekly_ and monthly_ prefixes
- Only normalize for consistency (dot notation)

### Fix C: Update _parse_indicator_from_field
- Check for daily_ prefix explicitly
- If no prefix and it's supertrend, check context
- Preserve timeframe information throughout

### Fix D: Pass timeframe context through validation
- When missing field detected, preserve original field name
- Use original field name to determine correct timeframe

## 4. Indicator Naming Conventions

### Current Database Format (CORRECT):
- Daily: `daily_supertrend_10_3`, `daily_pctchg`
- Weekly: `weekly_supertrend_10_3`, `weekly_pctchg`
- Monthly: `monthly_supertrend_10_3`, `monthly_pctchg`

### Query Format (SHOULD MATCH):
- Daily: `daily_supertrend_10_3` or `daily supertrend (10,3)`
- Weekly: `weekly_supertrend_10_3` or `weekly supertrend (10,3)`
- Monthly: `monthly_supertrend_10_3` or `monthly supertrend (10,3)`

## 5. Test Cases Needed
1. `daily_supertrend_10_3 > 100` → Should query daily_supertrend_10_3
2. `weekly_supertrend_10_3 < 200` → Should query weekly_supertrend_10_3
3. `monthly_pctchg > 5` → Should query monthly_pctchg
4. `daily supertrend (10,3) > close` → Should query daily_supertrend_10_3
5. `weekly supertrend (10,2) < 100` → Should auto-calculate weekly_supertrend_10_2