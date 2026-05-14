"""
Robust file format handling for various data file types.
Handles edge cases in CSV, Excel, and JSON loading.
"""

from __future__ import annotations

import io
import json
import chardet
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path

import numpy as np
import pandas as pd


class FileFormatError(Exception):
    """Custom exception for file format errors."""

    pass


class RobustFileReader:
    """
    Handles various file formats with automatic detection and robust parsing.
    """

    SUPPORTED_FORMATS = {
        ".csv": "csv",
        ".tsv": "tsv",
        ".txt": "text",
        ".xlsx": "excel",
        ".xls": "excel",
        ".json": "json",
        ".jsonl": "jsonl",
    }

    CSV_DELIMITERS = [",", ";", "\t", "|"]

    ENCODINGS_TO_TRY = [
        "utf-8",
        "utf-8-sig",
        "latin-1",
        "iso-8859-1",
        "cp1252",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
    ]

    def detect_format(self, file_path: str) -> str:
        """Detect file format from extension."""
        ext = Path(file_path).suffix.lower()
        return self.SUPPORTED_FORMATS.get(ext, "unknown")

    def detect_encoding(self, content: bytes) -> str:
        """Detect file encoding."""
        result = chardet.detect(content[:10000])
        return result.get("encoding", "utf-8") or "utf-8"

    def detect_delimiter(self, content: str) -> str:
        """Detect CSV delimiter by analyzing the content."""
        first_lines = content.split("\n")[:5]

        delimiter_counts = {}
        for line in first_lines:
            for delimiter in self.CSV_DELIMITERS:
                count = line.count(delimiter)
                if count > 0:
                    key = (delimiter, count)
                    delimiter_counts[key] = delimiter_counts.get(key, 0) + 1

        if delimiter_counts:
            best = max(delimiter_counts, key=lambda x: delimiter_counts[x])
            return best[0]

        return ","

    def read_file(
        self, file_path: str, content: Optional[bytes] = None, **kwargs
    ) -> pd.DataFrame:
        """
        Read a file and return a DataFrame.
        Automatically detects format, encoding, and delimiter.
        """
        fmt = self.detect_format(file_path)

        if fmt == "unknown":
            raise FileFormatError(f"Unsupported file format: {file_path}")

        if content is None:
            with open(file_path, "rb") as f:
                content = f.read()

        if fmt in ("csv", "tsv", "text"):
            return self._read_csv(content, **kwargs)
        elif fmt == "excel":
            return self._read_excel(file_path, content, **kwargs)
        elif fmt == "json":
            return self._read_json(content, **kwargs)
        elif fmt == "jsonl":
            return self._read_jsonl(content, **kwargs)

        raise FileFormatError(f"Cannot read format: {fmt}")

    def _read_csv(self, content: bytes, **kwargs) -> pd.DataFrame:
        """Read CSV with automatic encoding and delimiter detection."""
        encoding = self.detect_encoding(content)
        text = content.decode(encoding, errors="replace")

        delimiter = self.detect_delimiter(text)

        if delimiter == "\t":
            kwargs.setdefault("sep", "\t")
        elif delimiter != ",":
            kwargs.setdefault("sep", delimiter)

        kwargs.setdefault("encoding", encoding)
        kwargs.setdefault("engine", "python")

        try:
            df = pd.read_csv(io.BytesIO(content), **kwargs)
            return self._clean_dataframe(df)
        except Exception as e:
            for enc in self.ENCODINGS_TO_TRY:
                if enc == encoding:
                    continue
                try:
                    kwargs["encoding"] = enc
                    df = pd.read_csv(io.BytesIO(content), **kwargs)
                    return self._clean_dataframe(df)
                except:
                    continue

            raise FileFormatError(f"Failed to read CSV: {str(e)}")

    def _read_excel(
        self, file_path: str, content: Optional[bytes] = None, **kwargs
    ) -> pd.DataFrame:
        """Read Excel file with robust handling."""
        kwargs.setdefault("engine", "openpyxl")

        try:
            if content:
                df = pd.read_excel(io.BytesIO(content), **kwargs)
            else:
                df = pd.read_excel(file_path, **kwargs)

            return self._clean_dataframe(df)
        except Exception as e:
            if "openpyxl" in str(e).lower():
                kwargs["engine"] = "xlrd"
                try:
                    df = pd.read_excel(file_path, **kwargs)
                    return self._clean_dataframe(df)
                except:
                    pass

            raise FileFormatError(f"Failed to read Excel: {str(e)}")

    def _read_json(self, content: bytes, **kwargs) -> pd.DataFrame:
        """Read JSON file with support for various structures."""
        text = content.decode("utf-8", errors="replace")

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            text = self._fix_json(text)
            data = json.loads(text)

        if isinstance(data, list):
            if all(isinstance(item, dict) for item in data):
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame({"value": data})
        elif isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                df = pd.DataFrame(data["data"])
            elif "records" in data and isinstance(data["records"], list):
                df = pd.DataFrame(data["records"])
            elif "results" in data and isinstance(data["results"], list):
                df = pd.DataFrame(data["results"])
            else:
                records = self._flatten_dict(data)
                df = pd.DataFrame([records])
        else:
            raise FileFormatError("JSON does not contain tabular data")

        return self._clean_dataframe(df)

    def _read_jsonl(self, content: bytes, **kwargs) -> pd.DataFrame:
        """Read JSON Lines format."""
        text = content.decode("utf-8", errors="replace")
        lines = [
            json.loads(line)
            for line in text.strip().split("\n")
            if line.strip() and not line.startswith("#")
        ]

        if not lines:
            raise FileFormatError("JSONL file is empty or contains no valid records")

        return self._clean_dataframe(pd.DataFrame(lines))

    def _fix_json(self, text: str) -> str:
        """Attempt to fix malformed JSON."""
        text = text.strip()

        if text.startswith("'") and text.endswith("'"):
            text = '"' + text[1:-1].replace("'", '"') + '"'

        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*\]", "]", text)

        try:
            json.loads(text)
            return text
        except:
            pass

        if text.startswith("{") and not text.endswith("}"):
            text = text + "}"
        elif text.startswith("[") and not text.endswith("]"):
            text = text + "]"

        return text

    def _flatten_dict(self, d: Dict, parent_key: str = "", sep: str = "_") -> Dict:
        """Flatten nested dictionary."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                for i, item in enumerate(v):
                    items.extend(
                        self._flatten_dict(item, f"{new_key}_{i}", sep=sep).items()
                    )
            else:
                items.append((new_key, v))
        return dict(items)

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean the loaded DataFrame."""
        df = df.copy()

        df.columns = df.columns.str.strip()

        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]

        empty_cols = df.columns[df.isna().all()]
        if len(empty_cols) > 0:
            df = df.drop(columns=empty_cols)

        df = df.replace({np.nan: None, "nan": None, "NaN": None, "null": None})

        return df

    def get_file_info(
        self, file_path: str, content: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """Get information about a file without fully loading it."""
        fmt = self.detect_format(file_path)
        info = {
            "format": fmt,
            "size_bytes": len(content) if content else Path(file_path).stat().st_size,
            "estimated_rows": None,
            "estimated_columns": None,
            "detected_encoding": None,
            "detected_delimiter": None,
        }

        if content is None:
            with open(file_path, "rb") as f:
                content = f.read()

        if fmt in ("csv", "tsv", "text"):
            info["detected_encoding"] = self.detect_encoding(content)
            text = content.decode(info["detected_encoding"], errors="replace")
            info["detected_delimiter"] = self.detect_delimiter(text)

            first_line = text.split("\n")[0]
            info["estimated_columns"] = first_line.count(info["detected_delimiter"]) + 1

            lines = text.split("\n")
            info["estimated_rows"] = len([l for l in lines if l.strip()])

        elif fmt == "excel":
            try:
                xl_file = pd.ExcelFile(io.BytesIO(content))
                info["sheet_names"] = xl_file.sheet_names
                df = pd.read_excel(xl_file, nrows=0)
                info["estimated_columns"] = len(df.columns)
            except:
                pass

        return info


class SmartDataLoader:
    """
    Smart data loading with automatic format detection and initial cleaning.
    """

    def __init__(self):
        self.reader = RobustFileReader()

    def load(
        self,
        file_path: str,
        content: Optional[bytes] = None,
        clean_headers: bool = True,
        infer_types: bool = True,
        **kwargs,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Load data file with smart handling.

        Returns:
            Tuple of (DataFrame, metadata dict)
        """
        info = self.reader.get_file_info(file_path, content)

        df = self.reader.read_file(file_path, content, **kwargs)

        if clean_headers:
            df = self._clean_headers(df)

        if infer_types:
            df = self._infer_and_convert_types(df)

        metadata = {
            "format": info["format"],
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "null_counts": df.isnull().sum().to_dict(),
        }

        return df, metadata

    def _clean_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean column headers."""
        df = df.copy()

        df.columns = df.columns.str.strip()
        df.columns = df.columns.str.replace(r"\s+", "_", regex=True)
        df.columns = df.columns.str.replace(r"[^a-zA-Z0-9_]", "", regex=True)
        df.columns = df.columns.str.lower()

        return df

    def _infer_and_convert_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """Infer and convert column types."""
        from services.schema_inferrer import SchemaInferrer

        inferrer = SchemaInferrer()
        suggestions = inferrer.get_conversion_suggestions(df)

        for suggestion in suggestions:
            if suggestion["confidence"] > 70:
                col = suggestion["column"]
                dtype = suggestion["suggested_type"]

                try:
                    if dtype == "int":
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype(
                            "Int64"
                        )
                    elif dtype == "float":
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    elif dtype == "date":
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    elif dtype == "bool":
                        df[col] = (
                            df[col]
                            .astype(str)
                            .str.lower()
                            .isin(["true", "yes", "1", "y", "t"])
                        )
                except:
                    pass

        return df


def load_data(
    file_path: str, content: Optional[bytes] = None, **kwargs
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Convenience function for smart data loading.

    Args:
        file_path: Path to the file
        content: Optional file content as bytes
        **kwargs: Additional arguments passed to pandas read functions

    Returns:
        Tuple of (DataFrame, metadata dict)
    """
    loader = SmartDataLoader()
    return loader.load(file_path, content, **kwargs)
