import csv
import io

def parse_csv(file_bytes, encoding="utf-8"):
    """
    Read a CSV file from bytes and return a list of dict rows and header fields.

    :param file_bytes: bytes object from file.read()
    :param encoding: encoding used for CSV files (default utf-8)
    :return: (rows: list of dict, fieldnames: list of str)
    """
    try:
        text = file_bytes.decode(encoding)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        return rows, reader.fieldnames
    except Exception as e:
        print(f"CSV parse error: {e}")
        return [], []

def dicts_to_csv_string(dict_rows, fieldnames=None):
    """
    Convert a list of dicts to a CSV string, using given fieldnames (header order).

    :param dict_rows: list[dict]
    :param fieldnames: columns (if None, autodetect from first row)
    :return: CSV contents as string
    """
    if not dict_rows:
        return ""
    if fieldnames is None:
        fieldnames = list(dict_rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in dict_rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return output.getvalue()
