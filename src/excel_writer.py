from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

REQUIRED_COLS = [
    "Job title available",
    "employer",
    "job post url link",
    "job post from what source",
    "date job post was posted",
    "application closing date",
    "key job requirement",
    "estimated salary",
    "job full-time or part-time",
    "Relevance score",
    "Closing date passed? (Y/N)",
]

def build_excel_bytes(df_jobs, notes_dict):
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"

    # Header
    ws.append(REQUIRED_COLS)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)

    for c in ws[1]:
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(vertical="center", wrap_text=True)

    ws.freeze_panes = "A2"

    # Rows
    for _, row in df_jobs.iterrows():
        ws.append([row.get(col, "") for col in REQUIRED_COLS])

    # Hyperlinks in URL col (C)
    for r in range(2, ws.max_row + 1):
        cell = ws.cell(row=r, column=3)
        url = cell.value
        if isinstance(url, str) and url.startswith("http"):
            cell.hyperlink = url
            cell.style = "Hyperlink"

    # Column widths
    widths = {1:42,2:28,3:58,4:18,5:18,6:20,7:48,8:18,9:18,10:14,11:18}
    for col_idx, w in widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # Wrap text on selected cols
    wrap_cols = {1,2,7,8,9}
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=(cell.column in wrap_cols))

    # Add Excel table
    table_ref = f"A1:{get_column_letter(len(REQUIRED_COLS))}{ws.max_row}"
    tab = Table(displayName="JobsTable", ref=table_ref)
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showRowStripes=True,
        showColumnStripes=False
    )
    ws.add_table(tab)

    # Notes sheet
    ws2 = wb.create_sheet("Notes")
    ws2.append(["Item", "Value"])
    ws2["A1"].font = Font(bold=True)
    ws2["B1"].font = Font(bold=True)
    ws2.freeze_panes = "A2"
    ws2.column_dimensions["A"].width = 40
    ws2.column_dimensions["B"].width = 120

    for k, v in notes_dict.items():
        ws2.append([k, v])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.read()

