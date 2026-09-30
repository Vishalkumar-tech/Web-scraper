from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
import os
import re
from pathlib import Path


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

# Linux-safe project directory
BASE_DIR = Path(__file__).resolve().parent

# Master Excel file is in the same folder as app.py
MASTER_FILE = BASE_DIR / "Master_SKU.xlsx"


# ============================================================
# CONSTANTS
# ============================================================

ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

BUCKETS = [
    "<-5%",
    "-5%",
    "-4%",
    "-3%",
    "-2%",
    "-1%",
    "0%",
    "1%",
    "2%",
    "3%",
    "4%",
    "5%",
    ">5%"
]


# ============================================================
# FILE VALIDATION
# ============================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ============================================================
# COLUMN NORMALIZATION
# ============================================================

def normalize_column_name(value):
    """
    Normalize Excel headers while preserving percentage bucket signs.

    In particular:
        <-5%
        >5%

    must remain different headers.
    """

    value = str(value).strip().lower()

    value = value.replace("−", "-")
    value = value.replace("–", "-")
    value = value.replace("—", "-")

    value = value.replace("_", " ")

    # Normalize spaces
    value = re.sub(r"\s+", " ", value)

    # Normalize operators
    value = re.sub(r"\s*([<>+-])\s*", r"\1", value)

    # Normalize percentage sign
    value = re.sub(r"\s*%\s*", "%", value)

    # Keep meaningful characters
    value = re.sub(
        r"[^a-z0-9%<>+\- ]+",
        " ",
        value
    )

    return re.sub(r"\s+", " ", value).strip()


# ============================================================
# FIND COLUMN
# ============================================================

def find_column(df, candidates):

    normalized = {
        normalize_column_name(c): c
        for c in df.columns
    }

    # Exact match
    for candidate in candidates:

        key = normalize_column_name(candidate)

        if key in normalized:
            return normalized[key]

    # Partial match
    for candidate in candidates:

        key = normalize_column_name(candidate)

        for n, original in normalized.items():

            if key == n or key in n or n in key:
                return original

    return None


# ============================================================
# FIND BUCKET COLUMN
# ============================================================

def find_bucket_column(df, bucket):
    """
    Find a bucket column using whole-number percentage headers only.

    Expected Excel headers:

        <-5%
        -5%
        -4%
        ...
        5%
        >5%

    Also accepts headers without %.
    """

    target = str(bucket).strip().lower()

    # --------------------------------------------------------
    # Boundary buckets
    # --------------------------------------------------------

    if target in {"<-5%", ">5%"}:

        for col in df.columns:

            raw = str(col).strip().lower()

            raw = raw.replace("\xa0", " ")

            compact = re.sub(r"\s+", "", raw)

            compact = compact.replace("−", "-")
            compact = compact.replace("–", "-")
            compact = compact.replace("—", "-")

            # pandas may append .1, .2, etc.
            compact = re.sub(r"\.\d+$", "", compact)

            if compact == target or compact == target[:-1]:
                return col

        return None

    # --------------------------------------------------------
    # Normal buckets
    # --------------------------------------------------------

    try:

        target_number = int(
            target.replace("%", "").strip()
        )

    except (TypeError, ValueError):

        return None

    for col in df.columns:

        raw = str(col).strip().lower()

        raw = raw.replace("\xa0", " ")

        compact = re.sub(r"\s+", "", raw)

        compact = compact.replace("−", "-")
        compact = compact.replace("–", "-")
        compact = compact.replace("—", "-")

        compact = re.sub(r"\.\d+$", "", compact)

        # Header stored as -5%
        if compact.endswith("%"):

            try:

                if int(compact[:-1]) == target_number:
                    return col

            except ValueError:
                pass

            continue

        # Header stored as -5
        try:

            if int(compact) == target_number:
                return col

        except ValueError:
            pass

    return None


# ============================================================
# NUMBER CLEANING
# ============================================================

def clean_number(value):

    if pd.isna(value):
        return np.nan

    if isinstance(
        value,
        (int, float, np.integer, np.floating)
    ):
        return float(value)

    text = str(value).strip().replace(",", "")

    if not text:
        return np.nan

    text = re.sub(
        r"[^0-9.\-+eE]",
        "",
        text
    )

    try:
        return float(text)

    except Exception:
        return np.nan


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_sku_value(value):

    return normalize_text(value)


# ============================================================
# MONTH PARSING
# ============================================================

def parse_month_value(value, default_year=2026):
    """
    Convert Excel month/date values into:

        YYYY-MM

    Supports:

        1
        2
        3

        Jan
        Feb
        March

        January 2026
        2026-01
        2026-01-15

        Excel serial dates
        Pandas timestamps
    """

    if pd.isna(value):
        return None

    # --------------------------------------------------------
    # Pandas / Python datetime
    # --------------------------------------------------------

    if isinstance(value, pd.Timestamp):

        return value.strftime("%Y-%m")

    # --------------------------------------------------------
    # Numeric values
    # --------------------------------------------------------

    if isinstance(
        value,
        (int, float, np.integer, np.floating)
    ):

        number = float(value)

        # -----------------------------------------------
        # Month number 1-12
        # -----------------------------------------------

        if number.is_integer():

            month_number = int(number)

            if 1 <= month_number <= 12:

                return f"{default_year}-{month_number:02d}"

        # -----------------------------------------------
        # Excel serial date
        # -----------------------------------------------

        if number > 100:

            try:

                dt = pd.to_datetime(
                    number,
                    unit="D",
                    origin="1899-12-30",
                    errors="coerce"
                )

                if pd.notna(dt):

                    return dt.strftime("%Y-%m")

            except Exception:
                pass

    # --------------------------------------------------------
    # Convert text
    # --------------------------------------------------------

    text = str(value).strip()

    if not text:
        return None

    if text.lower() in {
        "nan",
        "none",
        "nat"
    }:
        return None

    # --------------------------------------------------------
    # Month names
    # --------------------------------------------------------

    month_names = {

        "jan": 1,
        "january": 1,

        "feb": 2,
        "february": 2,

        "mar": 3,
        "march": 3,

        "apr": 4,
        "april": 4,

        "may": 5,

        "jun": 6,
        "june": 6,

        "jul": 7,
        "july": 7,

        "aug": 8,
        "august": 8,

        "sep": 9,
        "sept": 9,
        "september": 9,

        "oct": 10,
        "october": 10,

        "nov": 11,
        "november": 11,

        "dec": 12,
        "december": 12,
    }

    text_lower = text.lower()

    if text_lower in month_names:

        month_number = month_names[text_lower]

        return f"{default_year}-{month_number:02d}"

    # --------------------------------------------------------
    # Text containing only month number
    # --------------------------------------------------------

    if re.fullmatch(r"\d{1,2}", text):

        month_number = int(text)

        if 1 <= month_number <= 12:

            return f"{default_year}-{month_number:02d}"

    # --------------------------------------------------------
    # Normal date parsing
    # --------------------------------------------------------

    dt = pd.to_datetime(
        text,
        errors="coerce"
    )

    if pd.notna(dt):

        return dt.strftime("%Y-%m")

    # Keep original if nothing can be parsed
    return text


# ============================================================
# CONTINUOUS MONTHS
# ============================================================

def continuous_months(month_values):

    cleaned = []

    for value in month_values:

        parsed = parse_month_value(value)

        if parsed and parsed not in cleaned:

            cleaned.append(parsed)

    iso = [
        x
        for x in cleaned
        if re.fullmatch(r"\d{4}-\d{2}", x)
    ]

    if len(iso) >= 2:

        start = pd.Period(
            min(iso),
            freq="M"
        )

        end = pd.Period(
            max(iso),
            freq="M"
        )

        return [
            str(x)
            for x in pd.period_range(
                start,
                end,
                freq="M"
            )
        ]

    return cleaned


# ============================================================
# MASTER FILE
# ============================================================

def load_master_count():

    try:

        if not MASTER_FILE.exists():
            return 0

        df = pd.read_excel(
            MASTER_FILE
        )

        return int(len(df))

    except Exception:

        return 0


# ============================================================
# PREPARE DATAFRAME
# ============================================================

def prepare_supplied_dataframe(df, month_label):

    """
    Read the supplied report exactly as provided by Excel.

    The workbook remains the source of truth.

    No bucket, adherence, total, spec, actual,
    difference or tolerance value is reconstructed.
    """

    # --------------------------------------------------------
    # Find columns
    # --------------------------------------------------------

    size_col = find_column(
        df,
        [
            "Size",
            "Tyre Size",
            "Tire Size"
        ]
    )

    spec_col = find_column(
        df,
        [
            "Spec (kg)",
            "Spec kg",
            "Spec"
        ]
    )

    actual_col = find_column(
        df,
        [
            "Actual (kg)",
            "Actual kg",
            "Actual"
        ]
    )

    total_col = find_column(
        df,
        [
            "Total tyres",
            "Total tyre",
            "Total tires",
            "Total tire"
        ]
    )

    adherence_col = find_column(
        df,
        [
            "% adher.",
            "% adherence",
            "Adherence %",
            "Adherence"
        ]
    )

    sku_col = find_column(
        df,
        [
            "SKU",
            "Tyre SKU",
            "Tire SKU",
            "Model",
            "Pattern"
        ]
    )

    month_col = find_column(
        df,
        [
            "Month",
            "Date",
            "Month Year",
            "Month-Year"
        ]
    )

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required = []

    if size_col is None:
        required.append("Size")

    if spec_col is None:
        required.append("Spec (kg)")

    if actual_col is None:
        required.append("Actual (kg)")

    if total_col is None:
        required.append("Total tyres")

    if adherence_col is None:
        required.append("% adher.")

    if required:

        raise ValueError(
            "Missing required supplied-data column(s): "
            + ", ".join(required)
        )

    # --------------------------------------------------------
    # Print input columns
    # --------------------------------------------------------

    print("\n========================================")
    print("INPUT COLUMNS")
    print("========================================")

    for i, col in enumerate(df.columns):

        print(
            i,
            repr(col),
            "TYPE:",
            type(col).__name__
        )

    print("========================================\n")

    # --------------------------------------------------------
    # Output dataframe
    # --------------------------------------------------------

    out = pd.DataFrame(
        index=df.index
    )

    out["size"] = df[
        size_col
    ].map(normalize_text)

    out["sku"] = (
        df[sku_col].map(normalize_sku_value)
        if sku_col is not None
        else out["size"]
    )

    out["spec"] = df[
        spec_col
    ].map(clean_number)

    out["actual"] = df[
        actual_col
    ].map(clean_number)

    out["total_tyres"] = df[
        total_col
    ].map(clean_number)

    out["adherence"] = df[
        adherence_col
    ].map(clean_number)

    # --------------------------------------------------------
    # MONTH FIX
    # --------------------------------------------------------

    if month_col is not None:

        out["month"] = df[
            month_col
        ].map(
            lambda x: parse_month_value(
                x,
                default_year=2026
            )
        )

    else:

        out["month"] = parse_month_value(
            month_label,
            default_year=2026
        )

    # --------------------------------------------------------
    # Bucket aliases
    # --------------------------------------------------------

    bucket_aliases = {

        "<-5%": [
            "<-5%",
            "< -5%",
            "< -5 %",
            "less than -5%",
            "less than -5"
        ],

        "-5%": [
            "-5%",
            "-5 %",
            "-5"
        ],

        "-4%": [
            "-4%",
            "-4 %",
            "-4"
        ],

        "-3%": [
            "-3%",
            "-3 %",
            "-3"
        ],

        "-2%": [
            "-2%",
            "-2 %",
            "-2"
        ],

        "-1%": [
            "-1%",
            "-1 %",
            "-1"
        ],

        "0%": [
            "0%",
            "0 %",
            "0"
        ],

        "1%": [
            "1%",
            "1 %",
            "1"
        ],

        "2%": [
            "2%",
            "2 %",
            "2"
        ],

        "3%": [
            "3%",
            "3 %",
            "3"
        ],

        "4%": [
            "4%",
            "4 %",
            "4"
        ],

        "5%": [
            "5%",
            "5 %",
            "5"
        ],

        ">5%": [
            ">5%",
            "> 5%",
            "> 5 %",
            "greater than 5%",
            "greater than 5"
        ],
    }

    # --------------------------------------------------------
    # Find bucket columns
    # --------------------------------------------------------

    bucket_columns = {}

    for bucket in BUCKETS:

        col = find_bucket_column(
            df,
            bucket
        )

        if col is None:

            col = find_column(
                df,
                bucket_aliases[bucket]
            )

        bucket_columns[bucket] = col

    # --------------------------------------------------------
    # Positional bucket fallback
    # --------------------------------------------------------

    try:

        actual_idx = list(
            df.columns
        ).index(actual_col)

        total_idx = list(
            df.columns
        ).index(total_col)

        between = list(
            df.columns
        )[
            actual_idx + 1:total_idx
        ]

        if len(between) == len(BUCKETS):

            print(
                "Using positional bucket mapping: "
                "13 columns between Actual and Total tyres."
            )

            for bucket, col in zip(
                BUCKETS,
                between
            ):

                if bucket_columns[bucket] is None:

                    bucket_columns[bucket] = col

    except Exception:

        pass

    # --------------------------------------------------------
    # Load bucket values
    # --------------------------------------------------------

    for bucket in BUCKETS:

        col = bucket_columns[bucket]

        print(
            f"Bucket {bucket:>5} "
            f"--> Excel column = {col!r}"
        )

        if col is not None:

            out[bucket] = df[
                col
            ].map(clean_number)

        else:

            out[bucket] = np.nan

    # --------------------------------------------------------
    # Optional tolerance columns
    # --------------------------------------------------------

    minus2_col = find_column(
        df,
        [
            "-2% Limit",
            "Minus 2% Limit",
            "-2% limit (kg)",
            "-2% (kg)"
        ]
    )

    plus2_col = find_column(
        df,
        [
            "+2% Limit",
            "Plus 2% Limit",
            "+2% limit (kg)",
            "+2% (kg)"
        ]
    )

    if minus2_col is not None:

        out["minus_2_limit"] = df[
            minus2_col
        ].map(clean_number)

    else:

        out["minus_2_limit"] = np.nan

    if plus2_col is not None:

        out["plus_2_limit"] = df[
            plus2_col
        ].map(clean_number)

    else:

        out["plus_2_limit"] = np.nan

    # --------------------------------------------------------
    # Remove empty sizes
    # --------------------------------------------------------

    out = out[
        out["size"].ne("")
    ].copy()

    out["source_row"] = np.arange(
        1,
        len(out) + 1
    )

    out["valid"] = (
        out["total_tyres"].notna()
        &
        out["adherence"].notna()
    )

    return out


# ============================================================
# ROW JSON
# ============================================================

def row_json(row):

    def num(v, digits=None):

        if pd.isna(v):
            return None

        x = float(v)

        return (
            round(x, digits)
            if digits is not None
            else x
        )

    result = {

        "size": row.get(
            "size",
            ""
        ),

        "sku": row.get(
            "sku",
            ""
        ),

        "month": row.get(
            "month",
            ""
        ),

        "spec": num(
            row.get("spec"),
            3
        ),

        "actual": num(
            row.get("actual"),
            3
        ),

        "total_tyres": num(
            row.get("total_tyres")
        ),

        "adherence": num(
            row.get("adherence"),
            2
        ),

        "minus_2_limit": num(
            row.get("minus_2_limit"),
            3
        ),

        "plus_2_limit": num(
            row.get("plus_2_limit"),
            3
        ),
    }

    for bucket in BUCKETS:

        result[bucket] = num(
            row.get(bucket)
        )

    return result


# ============================================================
# SIZE SUMMARY
# ============================================================

def build_size_summary(df):

    work = df.copy()

    work["sku_sort"] = (
        work["sku"]
        .fillna("")
        .astype(str)
        .str.casefold()
    )

    work["month_sort"] = (
        work["month"]
        .fillna("")
        .astype(str)
    )

    work["month_period"] = pd.to_datetime(
        work["month_sort"] + "-01",
        errors="coerce"
    )

    work = work.sort_values(
        [
            "sku_sort",
            "month_period",
            "month_sort",
            "source_row"
        ],
        kind="stable",
        na_position="last"
    )

    rows = []

    for i, (_, row) in enumerate(
        work.iterrows(),
        1
    ):

        result = row_json(row)

        result["s_no"] = i

        rows.append(result)

    return rows


# ============================================================
# MONTHLY SUMMARY
# ============================================================

def build_monthly_summary(df):

    work = df.copy()

    work["month_sort"] = (
        work["month"]
        .fillna("")
        .astype(str)
    )

    work["sku_sort"] = (
        work["sku"]
        .fillna("")
        .astype(str)
        .str.casefold()
    )

    work["month_period"] = pd.to_datetime(
        work["month_sort"] + "-01",
        errors="coerce"
    )

    work = work.sort_values(
        [
            "month_period",
            "month_sort",
            "sku_sort",
            "source_row"
        ],
        kind="stable",
        na_position="last"
    )

    return [

        {
            "month": (
                str(row["month"])
                if pd.notna(row["month"])
                else ""
            ),

            "sku": str(row["sku"]),

            "total_tyres": (
                float(row["total_tyres"])
                if pd.notna(row["total_tyres"])
                else None
            ),

            "adherence": (
                float(row["adherence"])
                if pd.notna(row["adherence"])
                else None
            ),
        }

        for _, row in work.iterrows()

        if (
            pd.notna(row["month"])
            and str(row["month"]).strip()
        )
    ]


# ============================================================
# SKU MONTH SUMMARY
# ============================================================

def build_sku_month_summary(df):

    if df.empty:
        return [], []

    work = df.copy()

    work["sku_sort"] = (
        work["sku"]
        .fillna("")
        .astype(str)
        .str.casefold()
    )

    work["month_sort"] = (
        work["month"]
        .fillna("")
        .astype(str)
    )

    work["month_period"] = pd.to_datetime(
        work["month_sort"] + "-01",
        errors="coerce"
    )

    work = work.sort_values(
        [
            "sku_sort",
            "month_period",
            "month_sort",
            "source_row"
        ],
        kind="stable",
        na_position="last"
    )

    rows = []
    duplicates = []

    for (
        sku,
        month
    ), group in work.groupby(
        ["sku", "month"],
        sort=False,
        dropna=False
    ):

        if not sku or not month:
            continue

        first = group.iloc[0]

        row = {

            "sku": str(sku),

            "month": str(month),

            "spec": (
                float(first["spec"])
                if pd.notna(first["spec"])
                else None
            ),

            "average_running_weight": (
                float(first["actual"])
                if pd.notna(first["actual"])
                else None
            ),

            "actual": (
                float(first["actual"])
                if pd.notna(first["actual"])
                else None
            ),

            "minus_2_percent": (
                float(first["spec"]) * 0.98
                if pd.notna(first["spec"])
                else None
            ),

            "plus_2_percent": (
                float(first["spec"]) * 1.02
                if pd.notna(first["spec"])
                else None
            ),

            "total_tyres": (
                float(first["total_tyres"])
                if pd.notna(first["total_tyres"])
                else None
            ),

            "adherence": (
                float(first["adherence"])
                if pd.notna(first["adherence"])
                else None
            ),

            "source_row": int(
                first["source_row"]
            ),
        }

        for bucket in BUCKETS:

            row[bucket] = (
                float(first[bucket])
                if pd.notna(first[bucket])
                else None
            )

        rows.append(row)

        if len(group) > 1:

            duplicates.append({

                "sku": str(sku),

                "month": str(month),

                "rows": int(len(group)),

                "source_rows": [
                    int(x)
                    for x in group[
                        "source_row"
                    ].tolist()
                ],
            })

    return rows, duplicates


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():

    return render_template(
        "dashboard.html"
    )


# ============================================================
# UPLOAD / ANALYZE
# ============================================================

@app.route(
    "/upload",
    methods=["POST"]
)
@app.route(
    "/analyze",
    methods=["POST"]
)
def analyze():

    if "file" not in request.files:

        return jsonify({
            "success": False,
            "error": "No file uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:

        return jsonify({
            "success": False,
            "error": "Please select a file."
        }), 400

    if not allowed_file(
        file.filename
    ):

        return jsonify({
            "success": False,
            "error": (
                "Only XLSX, XLS or CSV files "
                "are supported."
            )
        }), 400

    try:

        # ----------------------------------------------------
        # Read workbook
        # ----------------------------------------------------

        if file.filename.lower().endswith(
            ".csv"
        ):

            sheets = {
                "Data": pd.read_csv(file)
            }

        else:

            sheets = pd.read_excel(
                file,
                sheet_name=None
            )

        parts = []
        invalid = []
        sheet_stats = []

        # ----------------------------------------------------
        # Process sheets
        # ----------------------------------------------------

        for (
            sheet_name,
            raw
        ) in sheets.items():

            try:

                prepared = prepare_supplied_dataframe(
                    raw,
                    sheet_name
                )

                parts.append(
                    prepared
                )

                sheet_stats.append({

                    "month": str(
                        sheet_name
                    ),

                    "rows": int(
                        len(raw)
                    ),

                    "valid": int(
                        prepared["valid"].sum()
                    ),

                    "invalid": int(
                        len(prepared)
                        -
                        prepared["valid"].sum()
                    )
                })

            except Exception as exc:

                invalid.append({

                    "month": str(
                        sheet_name
                    ),

                    "row": "all",

                    "size": "",

                    "reason": str(exc)
                })

        # ----------------------------------------------------
        # No readable sheets
        # ----------------------------------------------------

        if not parts:

            return jsonify({
                "success": False,
                "error": (
                    "No readable report sheets "
                    "were found."
                )
            }), 400

        # ----------------------------------------------------
        # Combine
        # ----------------------------------------------------

        data = pd.concat(
            parts,
            ignore_index=True
        )

        valid = data[
            data["valid"]
        ].copy()

        if valid.empty:

            return jsonify({
                "success": False,
                "error": (
                    "No rows with supplied Total "
                    "tyres and % adher. were found."
                )
            }), 400

        # ----------------------------------------------------
        # Summaries
        # ----------------------------------------------------

        size_summary = build_size_summary(
            valid
        )

        monthly_summary = build_monthly_summary(
            valid
        )

        (
            sku_month_summary,
            duplicate_sku_month_rows
        ) = build_sku_month_summary(
            valid
        )

        # ----------------------------------------------------
        # SKU running weight chart
        # ----------------------------------------------------

        sku_running_weight_chart = []

        for r in sku_month_summary:

            sku_running_weight_chart.append({

                "sku": r["sku"],

                "month": r["month"],

                "spec": r["spec"],

                "average_running_weight":
                    r["average_running_weight"],

                "minus_2_percent":
                    r["minus_2_percent"],

                "plus_2_percent":
                    r["plus_2_percent"],

                "total_tyres":
                    r["total_tyres"],
            })

        # ----------------------------------------------------
        # Total tyres
        # ----------------------------------------------------

        total_series = pd.to_numeric(
            valid["total_tyres"],
            errors="coerce"
        ).dropna()

        total_tyres = (
            float(total_series.sum())
            if not total_series.empty
            else None
        )

        # ----------------------------------------------------
        # Bucket totals
        # ----------------------------------------------------

        bucket_totals = {}

        for bucket in BUCKETS:

            vals = pd.to_numeric(
                valid[bucket],
                errors="coerce"
            ).dropna()

            bucket_totals[bucket] = (
                float(vals.sum())
                if not vals.empty
                else None
            )

        # ----------------------------------------------------
        # Adherence
        # ----------------------------------------------------

        adherence_values = pd.to_numeric(
            valid["adherence"],
            errors="coerce"
        ).dropna().tolist()

        unique_adherence = []

        for value in adherence_values:

            if not any(
                abs(
                    float(value) - x
                ) < 1e-12
                for x in unique_adherence
            ):

                unique_adherence.append(
                    float(value)
                )

        overall_adherence = (
            unique_adherence[0]
            if len(unique_adherence) == 1
            else None
        )

        # ----------------------------------------------------
        # Adherent tyres
        # ----------------------------------------------------

        adherence_bucket_values = [

            bucket_totals[b]

            for b in BUCKETS[1:-1]

            if bucket_totals[b] is not None
        ]

        adherent_tyres = (
            float(
                sum(adherence_bucket_values)
            )
            if adherence_bucket_values
            else None
        )

        # ----------------------------------------------------
        # Monthly chart
        # ----------------------------------------------------

        monthly_chart = []

        chart_work = valid.copy()

        chart_work["month_period"] = pd.to_datetime(
            chart_work["month"].astype(str) + "-01",
            errors="coerce"
        )

        chart_work = chart_work.sort_values(
            [
                "month_period",
                "month",
                "sku",
                "source_row"
            ],
            kind="stable",
            na_position="last"
        )

        for _, r in chart_work.iterrows():

            if pd.notna(
                r["adherence"]
            ):

                monthly_chart.append({

                    "month": str(
                        r["month"]
                    ),

                    "sku": str(
                        r["sku"]
                    ),

                    "adherence": float(
                        r["adherence"]
                    ),

                    "source_row": int(
                        r["source_row"]
                    ),
                })

        # ----------------------------------------------------
        # Graph
        # ----------------------------------------------------

        graph = []

        for _, r in valid.iterrows():

            graph.append({

                "label": r["size"],

                "size": r["size"],

                "spec": (
                    float(r["spec"])
                    if pd.notna(r["spec"])
                    else None
                ),

                "actual": (
                    float(r["actual"])
                    if pd.notna(r["actual"])
                    else None
                ),

                "adherence": (
                    float(r["adherence"])
                    if pd.notna(r["adherence"])
                    else None
                ),
            })

        # ----------------------------------------------------
        # Details
        # ----------------------------------------------------

        details = [
            row_json(r)
            for _, r in valid.iterrows()
        ]

        # ----------------------------------------------------
        # Months
        # ----------------------------------------------------

        months = [
            str(x)
            for x in valid[
                "month"
            ].dropna().tolist()
        ]

        # ----------------------------------------------------
        # SKUs
        # ----------------------------------------------------

        skus = sorted(
            {
                str(x)
                for x in valid[
                    "sku"
                ].dropna().tolist()
                if str(x).strip()
            },
            key=str.casefold
        )

        # ----------------------------------------------------
        # Sort details
        # ----------------------------------------------------

        details = sorted(
            details,
            key=lambda r: (
                str(
                    r.get(
                        "sku",
                        ""
                    )
                ).casefold(),

                str(
                    r.get(
                        "month",
                        ""
                    )
                ),

                str(
                    r.get(
                        "size",
                        ""
                    )
                ).casefold()
            )
        )

        # ----------------------------------------------------
        # Return JSON
        # ----------------------------------------------------

        return jsonify({

            "success": True,

            "message": (
                "Excel processed. Supplied report "
                "values were used without recalculating "
                "the bucket/adherence fields."
            ),

            "filename": file.filename,

            "kpis": {

                "total_tyres":
                    total_tyres,

                "adherent_tyres":
                    adherent_tyres,

                "non_adherent_tyres": (
                    total_tyres - adherent_tyres
                    if (
                        total_tyres is not None
                        and
                        adherent_tyres is not None
                    )
                    else None
                ),

                "adherence":
                    overall_adherence,
            },

            "summary":
                size_summary,

            "size_summary":
                size_summary,

            "monthly":
                monthly_summary,

            "monthly_summary":
                monthly_summary,

            "sku_month_summary":
                sku_month_summary,

            "sku_running_weight_chart":
                sku_running_weight_chart,

            "sku_values":
                skus,

            "month_values":
                list(
                    dict.fromkeys(months)
                ),

            "continuous_months":
                continuous_months(months),

            "graph":
                graph,

            "bucket_totals":
                bucket_totals,

            "monthly_chart":
                monthly_chart,

            "details":
                details,

            "invalid":
                invalid,

            "meta": {

                "master_count":
                    load_master_count(),

                "sheet_count":
                    len(sheets),

                "sheets":
                    [
                        str(x)
                        for x in sheets.keys()
                    ],

                "bucket_order":
                    BUCKETS,

                "source_of_truth":
                    "uploaded Excel supplied values",

                "calculation_mode":
                    "no reconstruction of supplied report metrics",

                "sheet_statistics":
                    sheet_stats,

                "duplicate_sku_month_rows":
                    duplicate_sku_month_rows,

                "pagination": {

                    "default_page_size":
                        20,

                    "page_size_options":
                        [10, 20, 50, 100],

                    "mode":
                        "client-side table pagination",
                },
            }
        })

    except Exception as exc:

        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
