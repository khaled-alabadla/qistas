"""
Arabic locale formats for Qistas — Western digits everywhere (docs/adr/0016).

Django's bundled `ar` formats already use Western (ASCII) digits; this module
pins the choice explicitly so a future Django/locale change cannot switch the
UI to Arabic-Indic numerals for IDs, references, dates, or money.
"""

DATE_FORMAT = "Y-m-d"
DATETIME_FORMAT = "Y-m-d H:i"
TIME_FORMAT = "H:i"
YEAR_MONTH_FORMAT = "F Y"
MONTH_DAY_FORMAT = "j F"
SHORT_DATE_FORMAT = "Y-m-d"
SHORT_DATETIME_FORMAT = "Y-m-d H:i"
FIRST_DAY_OF_WEEK = 6  # Saturday

DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
DATETIME_INPUT_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"]
TIME_INPUT_FORMATS = ["%H:%M", "%H:%M:%S"]

DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3
USE_THOUSAND_SEPARATOR = True
