# Verified Data Dictionary

## Dataset and validation status

This dictionary records the observed schema of `data/raw/ev_charging_dataset.csv`, verified during Phase 2. The CSV contains 1,317,750 rows and 33 columns, with 150 station identifiers and no missing cells in the full validation pass.

Raw dtypes below are the pandas dtypes observed from a 1,000-row schema sample. Full-file validation confirmed the listed columns were readable for all 1,317,750 rows. A field's name and observed values do not by themselves establish a complete real-world measurement definition; meanings marked as unverified require source or domain confirmation.

## Verified source fields

| Field | Observed dtype | Preliminary/verified description | Validation finding |
|---|---|---|---|
| `timestamp` | `object` | Observation timestamp; parsed to UTC for processing. | 0 invalid; range `2025-07-01T00:00:00Z` to `2025-12-31T00:00:00Z`; 8,785 unique timestamps; 30-minute station intervals. |
| `station_id` | `object` | Charging-station identifier. | 150 unique stations; 8,785 records per station. |
| `station_name` | `object` | Station name or label; exact source semantics unverified. | 0 missing. |
| `network` | `object` | Network/provider label; exact source semantics unverified. | 0 missing. |
| `city` | `object` | City label associated with a station; exact source semantics unverified. | 0 missing. |
| `state` | `object` | State or regional label; exact source semantics unverified. | 0 missing. |
| `latitude` | `float64` | Geographic latitude; coordinate convention and precision require source confirmation. | 0 missing. |
| `longitude` | `float64` | Geographic longitude; coordinate convention and precision require source confirmation. | 0 missing. |
| `location_type` | `object` | Location category label; exact category definitions unverified. | 0 missing. |
| `charger_type` | `object` | Charger-type label; exact category definitions unverified. | 0 missing. |
| `power_output_kw` | `float64` | Power-output value in kW as named by the column; measurement convention unverified. | 0 missing. |
| `amenities_nearby` | `object` | Nearby-amenities label or value; encoding and completeness unverified. | 0 missing. |
| `ports_total` | `int64` | Reported total number of charging ports. | 0 missing; no negative values; no port-balance violations. |
| `ports_available` | `int64` | Reported number of available ports. | 0 missing; no negative or greater-than-total values. |
| `ports_occupied` | `int64` | Reported number of occupied ports and the Phase 2 primary forecasting target. | 0 missing; no negative or greater-than-total values. |
| `ports_out_of_service` | `int64` | Reported number of out-of-service ports. | 0 missing; no negative or greater-than-total values. |
| `utilization_rate` | `float64` | Supplied utilization-related value; exact source formula is unverified. | Preserved unchanged. It differs from the required operational formula on 1,228,757 of 1,233,368 comparable rows (99.6261%). |
| `station_status` | `object` | Station status label; allowed values and operational semantics unverified. | 0 missing. |
| `estimated_wait_time_mins` | `int64` | Estimated wait-time field in minutes as named by the column; methodology is unverified. | 1,233,368 zero values and 84,382 positive values; not used as the primary target. |
| `avg_session_duration_mins` | `int64` | Average-session-duration value in minutes as named by the column; calculation window and methodology unverified. | 0 missing. |
| `current_price` | `float64` | Current-price value; currency, unit, and pricing context unverified. | 0 missing. |
| `pricing_type` | `object` | Pricing-category label; exact category definitions unverified. | 0 missing. |
| `temperature_f` | `float64` | Temperature value in Fahrenheit as named by the column; source and measurement context unverified. | 0 missing. |
| `precipitation_mm` | `float64` | Precipitation value in millimetres as named by the column; source and accumulation interval unverified. | 0 missing. |
| `weather_condition` | `object` | Weather-condition label; source and category definitions unverified. | 0 missing. |
| `gas_price_per_gallon` | `float64` | Gas-price value per gallon as named by the column; currency, location, and time basis unverified. | 0 missing. |
| `traffic_congestion_index` | `int64` | Traffic-congestion index; scale and methodology unverified. | 0 missing. |
| `local_event` | `object` | Local-event label or indicator; source and coding rules unverified. | 0 missing. |
| `is_weekend` | `bool` | Source weekend indicator. | 0 missing; matched UTC timestamp-derived weekend status for all rows. |
| `is_peak_hour` | `bool` | Source peak-hour indicator; threshold definition unverified. | 0 missing. |
| `hour_of_day` | `int64` | Source hour-of-day calendar field. | 0 missing; matched UTC timestamp-derived hour for all rows. |
| `day_of_week` | `int64` | Source day-of-week calendar field. | 0 missing; matched UTC timestamp-derived weekday numbering for all rows. |
| `month` | `int64` | Source calendar month field. | 0 missing; matched UTC timestamp-derived month for all rows. |

## Processed fields added in Phase 2

| Field | Type/representation | Description |
|---|---|---|
| `operational_utilization` | `float64` | Calculated as `ports_occupied / (ports_available + ports_occupied)`. Zero denominators produce null rather than an artificial value; 84,382 rows had zero denominators. |
| `hour` | nullable integer | UTC timestamp hour derived from the parsed timestamp. |
| `day` | nullable integer | UTC calendar day of month derived from the parsed timestamp. |
| `calendar_timezone` | text | Constant `UTC`, documenting the representation used for parsed timestamps and derived calendar features. |

The original `utilization_rate`, `hour_of_day`, `day_of_week`, `month`, and `is_weekend` columns were retained. The processed dataset is station- and timestamp-sorted and contains no artificial observations or interpolated charging-port values.

## Validation summary

- Fully duplicated rows: 0 extra occurrences.
- Duplicated `station_id`/`timestamp` pairs: 0 extra occurrences.
- Missing cells: 0.
- Port balance violations: 0 for `ports_available + ports_occupied + ports_out_of_service = ports_total`.
- Negative port counts: 0.
- Port counts greater than total: 0.
- Irregular or missing 30-minute intervals: 0 across all 150 stations.

The supplied utilization field and estimated wait-time field remain limited by their unverified source methodologies. Future forecasting must use `ports_occupied` as the primary target and must not claim that `estimated_wait_time_mins` is reliable real-world queue waiting time.
