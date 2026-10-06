## Create (or update) the Power BI report
from sempy_labs.report import create_report_from_reportjson, update_report_from_reportjson

report_json = build()
existing = fabric.list_items(item_type="Report")
if REPORT in set(existing["Display Name"]):
    update_report_from_reportjson(report=REPORT, report_json=report_json)
    print(f"Updated report '{REPORT}'")
else:
    create_report_from_reportjson(report=REPORT, dataset=MODEL, report_json=report_json)
    print(f"Created report '{REPORT}'")
