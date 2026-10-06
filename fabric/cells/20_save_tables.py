## Save the report tables to NBA_Lakehouse (Delta) and keep a copy of the results in Files
import shutil

import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, FloatType


def save_table(path):
    pdf = pd.read_csv(path)
    for col in pdf.columns[pdf.dtypes == object]:
        pdf[col] = pdf[col].astype(object).where(pdf[col].notna(), None)
    sdf = spark.createDataFrame(pdf)
    for field in sdf.schema.fields:                         # NaN -> null, so Power BI sees blanks
        if isinstance(field.dataType, (DoubleType, FloatType)):
            sdf = sdf.withColumn(field.name, F.when(F.isnan(field.name), None).otherwise(F.col(field.name)))
    if "game_date" in pdf.columns:
        sdf = sdf.withColumn("game_date", F.to_date("game_date"))
    sdf.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(path.stem)
    print(f"{path.stem:24s} {len(pdf):>9,} rows")


for path in sorted((C.FABRIC / "tables").glob("*.csv")):
    save_table(path)

files = Path("/lakehouse/default/Files/nba")
for folder, name in ((C.TABLES, "results"), (C.FABRIC / "tables", "report_tables")):
    (files / name).mkdir(parents=True, exist_ok=True)
    for f in sorted(folder.glob("*.csv")):
        shutil.copyfile(f, files / name / f.name)       # file contents only: the OneLake mount keeps no Unix permissions
print("Copied result tables to Files/nba/")
