"""Rebuild curated practice content from the supplied materials, not web data.

Run from the repository root after unpacking materials.zip into research-sources/.
Reference answers are frozen at build time. Student submissions are never executed.
"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research-sources" / "materials"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
questions, datasets = [], {}


def locate(name):
    found = list(SOURCE.rglob(name))
    if len(found) != 1:
        raise ValueError(f"Expected one {name}, found {found}")
    return found[0]


def asset(key, filename, label, compressed=False):
    source = locate(filename)
    destination = DATA / (filename + ".gz" if compressed else filename)
    if compressed:
        with source.open("rb") as src, gzip.open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        shutil.copyfile(source, destination)
    datasets[key] = {
        "label": label, "file": destination.name, "download_name": filename,
        "source": source.relative_to(SOURCE).as_posix(),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "compressed": compressed,
    }
    return source


def add(id, title, prompt, subject, skill, files, source, kind, answer=None, **extra):
    questions.append(dict(
        id=id, title=title, prompt=prompt, subject=subject, skill=skill,
        datasets=files, source=source, kind=kind, answer=answer,
        hint=extra.pop("hint", "Check the requested population, grouping level and units."),
        solution=extra.pop("solution", ""),
        **extra,
    ))


film_path = asset("film", "NYC_Film_Permits.txt", "NYC film permits")
film = pd.read_csv(film_path)
fsource = "1. Excel Part 1/PWC Excel Assignment/Assignment_01_Excel-SQL.xlsx · Excel Questions"
shoot = film[film.EventType == "Shooting Permit"]
add("X01", "Know your dataset", "How many data records are in the NYC film-permits file? Exclude the header.", "Excel", "Data profiling", ["film"], fsource+" · Q1", "number", len(film), tolerance=0,
    hint="Exclude the header; count records rather than populated ZIP codes.",
    solution=f"There are {len(film):,} records. Count a fully populated identifier, or use the number of data rows.")
add("X02", "Missing ZIP codes", "How many records have a missing ZipCode? Use all event types.", "Excel", "Missing values", ["film"], fsource+" · Q3", "number", int(film.ZipCode.isna().sum()), tolerance=0,
    hint="Count empty ZipCode cells across all events, without discarding rows.",
    solution=f"Count blanks in ZipCode: {film.ZipCode.isna().sum()}. Missing and invalid values are different checks.")
add("X03", "Summarise event types", "Show the count of each EventType. Paste a two-column table headed EventType and Count; any row order is accepted.", "Excel", "Pivot tables", ["film"], fsource+" · Q8–9", "table",
    [[str(k), int(v)] for k,v in film.groupby("EventType").size().items()], columns=["EventType","Count"],
    solution="Create a pivot table with EventType in Rows and a count of EventID in Values. Include every event type.")
hours = (pd.to_datetime(shoot.EndDateTime) - pd.to_datetime(shoot.StartDateTime)).dt.total_seconds()/3600
rounded_hours = round(float(hours.mean()) * 2) / 2
add("X04", "Permit duration", "Find the average duration of a Shooting Permit, in hours. Round to the nearest half-hour and enter a number.", "Excel", "Date arithmetic", ["film"], fsource+" · Q16", "number", rounded_hours, tolerance=0.001,
    hint="Subtract start from end, multiply Excel date differences by 24, average shooting permits only, then round.",
    solution=f"Mean duration before rounding is {hours.mean():.6f} hours; the nearest half-hour is {rounded_hours}.",
    diagnostics=[{"value": round(float(hours.mean())/24,2), "message":"This resembles a duration in days. Excel date subtraction returns days; convert to hours before rounding."}])

plant_path = asset("plant", "Analytics_mindset_case_studies_ETL_Case3_Excel.xlsx", "Messy employee codes")
journal_path = asset("journal", "Analytics_mindset_case_studies_ETL_Case4_Excel.xlsx", "Journal entries and reference tables")
esource = "1. Excel part 2/ETL Assignment/Analytics_mindset_case_studies_ETL.docx"
plant = pd.read_excel(plant_path, sheet_name="Case 3 data")
import re
plant_answers = []
for value in plant.EmployeeCode.head(5):
    match = re.fullmatch(r"([^\d]+)(\d+)-(\d+)([A-Za-z]+)", value)
    country, employee, location, period = match.groups()
    plant_answers.append([value, country, int(employee), int(location), period, f"{country}-{location}"])
add("X05", "Decode variable-length identifiers", "For the first five employees on 'Case 3 data', extract the fields using formulas. Keep the country and pay-period text as written. Paste columns EmployeeCode, Location, EmpID, PlantID, PayPeriod, LocationPlantID in source order.", "Excel", "Text extraction", ["plant"], esource+" · Case 3", "table", plant_answers,
    columns=["EmployeeCode","Location","EmpID","PlantID","PayPeriod","LocationPlantID"], ordered=True,
    hint="Country names and pay-period suffixes vary in length. Locate the first digit and the hyphen rather than using fixed offsets.",
    solution="Use the first numeric position to end Location, the hyphen to end EmpID, and the first letter after the hyphen to end PlantID. Concatenate Location, '-', and PlantID.")
je = pd.read_excel(journal_path, sheet_name="JELineItems")
preparers = pd.read_excel(journal_path, sheet_name="PreparerInfo").dropna(subset=["PreparerID"])
def clean_name(value):
    return str(value).split("|")[0].strip()
people = preparers[preparers.PreparerID == 101].sort_values("BusinessUnitID")
add("X06", "The composite-key check", "Using PreparerInfo, list the preparer for PreparerID 101 in every business unit where that ID occurs. Return BusinessUnitID and PreparerName. Keep only the person's name before '|', without the job title. Sort by BusinessUnitID.", "Excel", "Composite-key lookups", ["journal"], esource+" · Case 4", "table",
    [[int(r.BusinessUnitID),clean_name(r.PreparerName)] for r in people.itertuples()], columns=["BusinessUnitID","PreparerName"], ordered=True,
    hint="PreparerID is reused. Match both PreparerID and BusinessUnitID; split the descriptive text at '|'.",
    solution="Match on the pair (PreparerID, BusinessUnitID), not PreparerID alone. In PreparerInfo, 101 maps to different people in different business units.")
add("X07", "Check the journal-line grain", "How many journal-entry line items are on JELineItems, excluding its header?", "Excel", "Data profiling", ["journal"], esource+" · Case 4", "number", len(je), tolerance=0,
    solution=f"There are {len(je)} line items. A JENumber can occur on multiple lines; distinct journal numbers do not count line items.")
add("X08", "Explain a repeatable lookup", "Explain why matching journal lines to preparers on PreparerID alone is unsafe, and how you would make the transformation repeatable.", "Excel", "Composite-key lookups", ["journal"], esource+" · Case 4", "explain",
    rubric=["PreparerID repeats across business units.", "Use PreparerID and BusinessUnitID together.", "Retain formulas and source data; check unmatched and duplicated results."],
    solution="Use a two-criteria INDEX/MATCH or another valid composite-key lookup. Keep formulas, preserve the original sheets, and reconcile the line count before and after enrichment.")

p15 = asset("pay15", "Analytics_mindset_case_studies_IntegrateCo_2015payroll.csv", "IntegrateCo 2015 payroll")
p16 = asset("pay16", "Analytics_mindset_case_studies_IntegrateCo_2016payroll.csv", "IntegrateCo 2016 payroll")
asset("jobs", "Analytics_mindset_case_studies_IntegrateCo_jobcodes.csv", "IntegrateCo job-code dictionary")
pay15, pay16 = pd.read_csv(p15, sep="|"), pd.read_csv(p16, sep="|")
psource = "1. Excel part 3/IntegrateCo Assignment/Analytics_mindset_case_studies_IntegrateCo_Excel.docx"
phantom = pay16[pay16.Employee_Number.isna()]
add("X09", "Find phantom payroll entries", "How many 2016 payroll rows have no Employee_Number?", "Excel", "Missing values", ["pay16"], psource+" · Part 4 Q3", "number", len(phantom), tolerance=0,
    solution=f"There are {len(phantom)} rows with no Employee_Number. Do not substitute Employee_ID, which is a different field.")
add("X10", "Quantify phantom wages", "Sum Gross_Wages for 2016 rows with no Employee_Number. Round to two decimals.", "Excel", "Conditional totals", ["pay16"], psource+" · Part 4 Q3", "number", round(float(phantom.Gross_Wages.sum()),2),
    solution=f"Filter missing Employee_Number and sum Gross_Wages: {phantom.Gross_Wages.sum():.2f}.")
total_cost = float(pay16[["Gross_Wages","SocSec_Medicare","FUTA","SUTA","Work_Comp"]].sum().sum())
add("X11", "Total employer cost", "Calculate total 2016 employee cost: Gross_Wages + SocSec_Medicare + FUTA + SUTA + Work_Comp across all rows, including phantom entries. Round to two decimals.", "Excel", "Calculated totals", ["pay16"], psource+" · Part 4 Q5", "number", round(total_cost,2),
    solution=f"Sum all five columns across the complete file: {total_cost:.2f}. Gross_Wages already includes regular and overtime wages.")
add("X12", "Make two payroll systems comparable", "Explain how to compare 2015 and 2016 gross wages by job code. Address field definitions, leading zeros, aggregation and the sign of the difference.", "Excel", "ETL and reconciliation", ["pay15","pay16","jobs"], psource+" · Parts 2–3", "explain",
    rubric=["2015 gross wages are Reg_Pay + OT_Pay; 2016 uses Gross_Wages.", "Extract the three-digit job code as text and reconcile to JobCodes.", "Aggregate both years to job code before comparing.", "Define change explicitly as 2016 minus 2015; positive means an increase."],
    solution="Align definitions first, extract and validate the job codes, then aggregate each year separately to a common grain. Use 2016 − 2015. This resolves contradictory subtraction wording in the source.")

songs = asset("songs", "songs.db", "Songs database")
chinook = asset("chinook", "Chinook_Sqlite.sqlite", "Chinook database")
movies = asset("movies", "movies.db", "Movies database", compressed=True)
def sqlq(id,title,prompt,db,key,source,query,skill,kind="table",hint=None):
    with sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True) as connection:
        cursor=connection.execute(query)
        rows=[list(row) for row in cursor.fetchall()]
        cols=[d[0] for d in cursor.description]
    add(id,title,prompt,"SQL",skill,[key],source,kind,rows[0][0] if kind=="number" else rows,
        **({"columns":cols,"ordered":True} if kind=="table" else {}),
        hint=hint or "Check filtering, joins, aggregation and the requested sort order.", solution=query)
ssource="2. SQL part 1/Assignments/cs50 assignment/songs/requierements.txt"
sqlq("S01","The three longest songs","Return the three longest songs, longest first. Use columns name and duration_ms.","" if False else songs,"songs",ssource+" · adapted from 3.sql","SELECT name, duration_ms FROM songs ORDER BY duration_ms DESC, name LIMIT 3","Sorting and limits")
sqlq("S02","Average tempo","Find the average tempo of all songs. Enter the result rounded to two decimals.",songs,"songs",ssource+" · 5.sql","SELECT ROUND(AVG(tempo),2) FROM songs","Aggregates","number")
sqlq("S03","Find an artist's songs","List the names of songs by Drake, alphabetically. Use the column name. Do not hard-code artist_id.",songs,"songs",ssource+" · 6.sql","SELECT s.name AS name FROM songs s JOIN artists a ON s.artist_id=a.id WHERE a.name='Drake' ORDER BY s.name","Joins")
sqlq("S04","Artist-level average","Find average energy for Post Malone's songs, rounded to three decimals.",songs,"songs",ssource+" · 7.sql","SELECT ROUND(AVG(s.energy),3) FROM songs s JOIN artists a ON s.artist_id=a.id WHERE a.name='Post Malone'","Joins and aggregates","number")
csource="2. SQL part 1/Assignments/pwc assignment/PWC SQL.docx"
sqlq("S05","High-value invoices","How many invoices have Total strictly greater than 20?",chinook,"chinook",csource+" · invoices above $20","SELECT COUNT(*) FROM Invoice WHERE Total>20","Filtering","number")
sqlq("S06","A bounded invoice range","How many invoices have Total strictly greater than 10 and strictly less than 20?",chinook,"chinook",csource+" · invoice range","SELECT COUNT(*) FROM Invoice WHERE Total>10 AND Total<20","Boundary conditions","number")
sqlq("S07","Sales by country","Return the five largest billing-country invoice totals. Use Country and Total, round totals to two decimals, and sort Total descending then Country ascending.",chinook,"chinook",csource+" · adapted country totals","SELECT BillingCountry AS Country, ROUND(SUM(Total),2) AS Total FROM Invoice GROUP BY BillingCountry ORDER BY Total DESC, Country LIMIT 5","Grouping and totals")
sqlq("S08","Missing company names","How many customers have a non-null Company?",chinook,"chinook",csource+" · customers listing company","SELECT COUNT(*) FROM Customer WHERE Company IS NOT NULL","Null handling","number")
msource="2. SQL part 1/Assignments/cs50 assignment/movies/requierements.txt"
sqlq("S09","Toy Story chronology","List titles and release years of movies whose title starts with 'Toy Story'. Use title and year, sorted by year then title.",movies,"movies",msource+" · 5.sql","SELECT title, year FROM movies WHERE title LIKE 'Toy Story%' ORDER BY year,title","Text matching")
sqlq("S10","Highly rated movies","How many movies have a rating strictly greater than 9.0?",movies,"movies",msource+" · 4.sql","SELECT COUNT(*) FROM ratings WHERE rating>9.0","Filtering","number")
sqlq("S11","An average across tables","Find the mean rating of movies released in 2013; round to two decimals.",movies,"movies",msource+" · 6.sql","SELECT ROUND(AVG(r.rating),2) FROM movies m JOIN ratings r ON m.id=r.movie_id WHERE m.year=2013","Joins and aggregates","number")
sqlq("S12","Two actors, one film","List titles of movies starring both Johnny Depp and Helena Bonham Carter, alphabetically. Use title.",movies,"movies",msource+" · 12.sql",
    "SELECT m.title FROM movies m WHERE m.id IN (SELECT s.movie_id FROM stars s JOIN people p ON p.id=s.person_id WHERE p.name='Johnny Depp') AND m.id IN (SELECT s.movie_id FROM stars s JOIN people p ON p.id=s.person_id WHERE p.name='Helena Bonham Carter') ORDER BY m.title","Relational intersections")

# Keep a clearly labelled, reproducible subset, not a silently altered full database.
pc_source=locate("pcards.db")
pc_dest=DATA/"pcards_osu_2014.db"
with sqlite3.connect(f"{pc_source.resolve().as_uri()}?mode=ro",uri=True) as conn:
    agencies=conn.execute("SELECT DISTINCT AgencyName FROM pcards WHERE AgencyName LIKE '%OKLAHOMA STATE UNIVERSITY%'").fetchall()
    exact=[a[0] for a in agencies if a[0].strip().upper()=="OKLAHOMA STATE UNIVERSITY"]
    if len(exact)!=1:
        raise ValueError(f"Confirm OSU agency before building: {agencies}")
    pc=pd.read_sql_query('SELECT * FROM pcards WHERE Year=2014 AND AgencyName=?',conn,params=exact)
with sqlite3.connect(pc_dest) as conn:
    pc.to_sql("pcards",conn,index=False,if_exists="replace")
    conn.execute("VACUUM")
datasets["pcards"]={"label":"P-cards · OSU 2014 subset","file":pc_dest.name,"download_name":pc_dest.name,
    "source":"2. SQL part 2/Pcards Assignment/pcards.db",
    "sha256":hashlib.sha256(pc_dest.read_bytes()).hexdigest(),"compressed":False,
    "note":f"Derived from the supplied pcards.db: Year = 2014 and AgencyName = {exact[0]!r}. {len(pc):,} rows; all source columns retained. Answers apply to this subset only."}
pcsource="2. SQL part 2/Pcards Assignment/Analytics_mindset_case_studies_PCard.docx"
sqlq("S13","P-card population","How many transactions are in the downloaded OSU 2014 subset? Count rows, including those with a missing Description.",pc_dest,"pcards",pcsource+" · Task 4 Q5, restricted to OSU 2014","SELECT COUNT(*) FROM pcards","Counting and nulls","number")
sqlq("S14","Single-transaction limit","How many transactions in the subset strictly exceed 5,000? Potential exceptions require follow-up; they do not prove misconduct.",pc_dest,"pcards",pcsource+" · Task 5 Q3, count adaptation","SELECT COUNT(*) FROM pcards WHERE Amount>5000","Control testing","number")
sqlq("S15","Large returns","How many returns are at least 1,000 in absolute value? Returns are negative amounts.",pc_dest,"pcards",pcsource+" · Task 4 Q17, count adaptation","SELECT COUNT(*) FROM pcards WHERE Amount<=-1000","Signed amounts","number",hint="A return of at least 1,000 is Amount <= -1000. Include the boundary.")
add("S16","Investigate split purchases","Describe how to flag same-person, same-vendor, same-day purchases whose combined amount exceeds 5,000. Explain why a flag is not proof of a violation.", "SQL","Control testing",["pcards"],pcsource+" · Task 5 Q4","explain",
    rubric=["Group by cardholder, vendor and transaction day.", "Require more than one transaction and a combined amount above 5,000.", "Join qualifying groups back to transaction details for investigation.", "Consider authorisations, legitimate purchases and other explanations before concluding."],
    solution="Aggregate by purchaser, vendor and date; apply COUNT(*) > 1 and SUM(Amount) > 5000; retrieve the underlying rows. Investigate context before concluding a control violation.")

restaurant=asset("restaurant","data.xlsm","Restaurant sales, weather and games")
rsource="1. Excel part 4/Regression Assignment/Restaurant/Instructions.docx"
sales=pd.read_excel(restaurant,sheet_name="salesData")
weather=pd.read_excel(restaurant,sheet_name="weatherData")
games=pd.read_excel(restaurant,sheet_name="gameData")
daily=sales.groupby("date",as_index=False)[["netTotal","netTotal_364"]].sum()
daily=daily.merge(weather[["date","tmax"]],on="date",how="left").merge(games[["date","gameDay"]],on="date",how="left")
daily["gameDay"]=daily.gameDay.fillna(0)
daily=daily.dropna()
X=np.column_stack([np.ones(len(daily)),daily.netTotal_364,daily.gameDay,daily.netTotal_364*daily.gameDay])
coef=np.linalg.lstsq(X,daily.netTotal,rcond=None)[0].round(6)
a,b,c,d=[float(x) for x in coef]
model=f"Fitted practice model from {len(daily)} observed days in the supplied workbook: Sales = {a} + ({b} × PriorYearSales) + ({c} × GameDay) + ({d} × PriorYearSales × GameDay). GameDay is 1 on listed game days and 0 otherwise. Sales and PriorYearSales use netTotal and netTotal_364 aggregated by date. Use these displayed coefficients."
add("R01","Predict on a game day",model+"\n\nPredict sales when PriorYearSales = 1000 and GameDay = 1. Round to two decimals. This is a supplied-input practice scenario, not an actual seven-day-ahead forecast.","Interpretation","Regression prediction",["restaurant"],rsource+" · prediction and interaction tasks","number",round(a+b*1000+c+d*1000,2),
    hint="Substitute into all four terms, including the interaction.",solution=f"{a} + {b}×1000 + {c} + {d}×1000 = {a+b*1000+c+d*1000:.2f}.")
add("R02","Interpret a conditional slope",model+"\n\nExplain what the coefficient of PriorYearSales means, and how its meaning changes on a game day.","Interpretation","Interaction interpretation",["restaurant"],rsource+" · final interaction task","explain",
    rubric=["The main slope applies when GameDay = 0.", "On a game day the slope is the main slope plus the interaction coefficient.", "Describe an association in sales units, not a proven causal effect."],
    solution=f"The non-game-day slope is {b}; the game-day slope is {b+d:.6f}. A one-unit increase in prior-year sales is associated with these changes in predicted current sales in the fitted model.")
add("R03","The game-day contrast",model+"\n\nAt PriorYearSales = 1000, calculate predicted game-day sales minus predicted non-game-day sales. Round to two decimals.","Interpretation","Interaction interpretation",["restaurant"],rsource+" · game-day and interaction tasks","number",round(c+d*1000,2),
    solution=f"The contrast is {c} + {d}×1000 = {c+d*1000:.2f}. The main GameDay coefficient alone applies only at PriorYearSales = 0.")
add("R04","Communicate confidence","Bob needs a sales forecast seven days beyond the last observed day. Explain what future inputs you would need and why a fitted regression does not guarantee accurate sales predictions.","Interpretation","Communicating uncertainty",["restaurant"],rsource+" · prediction and communication tasks","explain",
    rubric=["Specify the forecast date and aggregate sales target.", "Use inputs genuinely available at forecast time; do not use future realised sales or weather.", "Discuss model fit, forecast errors and unusual days.", "Separate association from causal claims and explain operational implications."],
    solution="Use known calendar/game information and historical sales; obtain or explicitly assume other future inputs. Evaluate forecast errors on held-out dates. Explain uncertainty and its implications for staffing and ingredients.")
temp_x=np.column_stack([np.ones(len(daily)),daily.tmax])
t0,t1=[float(x) for x in np.linalg.lstsq(temp_x,daily.netTotal,rcond=None)[0].round(6)]
temperature=f"Simple fitted practice model from {len(daily)} matched days: Sales = {t0} + ({t1} × tmax). tmax is maximum daily temperature in the source weather data (°F); Sales is daily aggregate netTotal. Use the displayed coefficients."
add("R05","Temperature prediction",temperature+"\n\nPredict sales for tmax = 60°F. Round to two decimals.","Interpretation","Regression prediction",["restaurant"],rsource+" · temperature task","number",round(t0+t1*60,2),solution=f"{t0} + {t1}×60 = {t0+t1*60:.2f}.")
add("R06","Temperature slope",temperature+"\n\nInterpret the slope in context. Can you conclude that changing temperature causes sales to change?","Interpretation","Coefficient interpretation",["restaurant"],rsource+" · temperature task","explain",
    rubric=["State the predicted sales change for one additional degree Fahrenheit.", "Describe association rather than causation.", "Acknowledge omitted factors and uncertainty; coefficients alone do not establish significance."],
    solution=f"One additional degree Fahrenheit is associated with {t1} units of daily sales in this fitted model. Observational association does not establish causation or statistical significance.")
add("R07","A ten-degree comparison",temperature+"\n\nWhat is the model's predicted change in sales when tmax rises from 50°F to 60°F? Round to two decimals.","Interpretation","Regression prediction",["restaurant"],rsource+" · temperature task","number",round(10*t1,2),solution=f"Subtract the two predictions. The intercept cancels: 10×{t1} = {10*t1:.2f}.")
add("R08","Prepare the restaurant data","Explain how you would combine salesData, weatherData and gameData for a daily-sales regression without multiplying records or losing non-game days.","Interpretation","Regression preparation",["restaurant"],rsource+" · ETL task","explain",
    rubric=["Aggregate product-level sales to date.", "Check one weather/game record per date before joining.", "Preserve sales dates and treat absent scheduled game dates as non-game days under an explicit assumption.", "Check missing weather and reconcile rows and total sales."],
    solution="Aggregate sales by date, check uniqueness of date in auxiliary tables, and left-join on date. Record the assumption that an absent game-date record means no game; inspect missing weather before fitting.")

# Additional tasks stay within the operations and populations in the source cases.
for i, borough in enumerate(["Brooklyn","Manhattan","Queens","Bronx","Staten Island"]):
    rows=shoot[shoot.Borough==borough]
    base=13+3*i
    add(f"X{base:02}","Shooting permits · "+borough,
        f"Count Shooting Permit records in {borough}. Use only that event type.",
        "Excel","Conditional counts",["film"],fsource+" · adaptations of Q9–13","number",len(rows),tolerance=0,
        solution=f"Filter EventType = Shooting Permit and Borough = {borough}; count EventID. Result: {len(rows)}.")
    start_dates=pd.to_datetime(rows.StartDateTime)
    end_dates=pd.to_datetime(rows.EndDateTime)
    duration=(end_dates-start_dates).dt.total_seconds()/3600
    value=round(float(duration.mean()),2)
    add(f"X{base+1:02}","Average duration · "+borough,
        f"Calculate the mean duration in hours of Shooting Permits in {borough}. Round to two decimals.",
        "Excel","Date arithmetic",["film"],fsource+" · adaptation of Q16","number",value,
        solution=f"Filter to {borough} shooting permits, subtract StartDateTime from EndDateTime, convert to hours, then average: {value}.")
    counts=rows.groupby("Category").size()
    add(f"X{base+2:02}","Categories · "+borough,
        f"Summarise Shooting Permits in {borough} by Category. Return Category and Count, sorted alphabetically by Category.",
        "Excel","Pivot tables",["film"],fsource+" · adaptation of Q10–11","table",
        [[str(k),int(v)] for k,v in counts.items()],columns=["Category","Count"],ordered=True,
        solution="Filter the source population, then pivot Category in Rows and count EventID in Values. Sort Category A–Z.")

for i,year in enumerate([2013,2014,2015]):
    count=int((pd.to_datetime(shoot.StartDateTime).dt.year==year).sum())
    add(f"X{28+i:02}",f"Shooting permits in {year}",
        f"Count Shooting Permits with StartDateTime in calendar year {year}. Include January 1 and exclude January 1 of the next year.",
        "Excel","Date filters",["film"],fsource+" · adaptations of Q13–15","number",count,tolerance=0,
        solution=f"Filter EventType and the specified start-date interval. The count is {count}.")
for i,unit in enumerate([1,2,3,4]):
    rows=je[je.BusinessUnitID==unit]
    add(f"X{31+i:02}",f"Journal lines · unit {unit}",
        f"On JELineItems, count line items for BusinessUnitID {unit}. Count lines, not distinct JENumber values.",
        "Excel","Conditional counts",["journal"],esource+" · Case 4, line-count adaptation","number",len(rows),tolerance=0,
        solution=f"Filter BusinessUnitID = {unit} and count data rows: {len(rows)}.")
for i,field in enumerate(["Gross_Wages","SocSec_Medicare","FUTA","SUTA","Work_Comp"]):
    value=round(float(pay16[field].sum()),2)
    add(f"X{35+i:02}","Payroll component · "+field,
        f"Sum {field} across every row in the 2016 payroll file, including rows without an Employee_Number. Round to two decimals.",
        "Excel","Calculated totals",["pay16"],psource+" · Part 4 Q5, component adaptation","number",value,
        solution=f"Sum the complete {field} column: {value:.2f}. Keep phantom entries in this population.")
for i,field in enumerate(["Reg_Pay","OT_Pay","Reg_Hrs","OT_Hrs"]):
    value=round(float(pay15[field].sum()),2)
    add(f"X{40+i:02}","2015 payroll · "+field,
        f"Find the total {field} across all 2015 payroll records. Round to two decimals.",
        "Excel","Calculated totals",["pay15"],psource+" · Parts 3–4, totals adaptation","number",value,
        solution=f"Sum all rows of {field}: {value:.2f}. Do not average employee-level averages.")

sqlq("S17","High-energy songs","List name and energy for songs with energy > 0.8, sorted by energy descending then name.",songs,"songs",ssource+" · adaptation of 4.sql",
     "SELECT name,energy FROM songs WHERE energy>0.8 ORDER BY energy DESC,name","Filtering")
sqlq("S18","A multi-condition playlist","List name for songs whose danceability, energy and valence are all > 0.6. Sort alphabetically.",songs,"songs",ssource+" · 4.sql",
     "SELECT name FROM songs WHERE danceability>0.6 AND energy>0.6 AND valence>0.6 ORDER BY name","Combined conditions")
sqlq("S19","Featured artists","List name for songs containing 'feat.' in the title, sorted alphabetically.",songs,"songs",ssource+" · 8.sql",
     "SELECT name FROM songs WHERE name LIKE '%feat.%' ORDER BY name","Text matching")
sqlq("S20","Fastest tempos","List name and tempo for the five fastest songs; sort tempo descending then name.",songs,"songs",ssource+" · adaptation of 2.sql",
     "SELECT name,tempo FROM songs ORDER BY tempo DESC,name LIMIT 5","Sorting and limits")
sqlq("S21","South American invoices","Count invoices with BillingCountry in Brazil, Argentina or Chile.",chinook,"chinook",csource+" · South American invoices",
     "SELECT COUNT(*) FROM Invoice WHERE BillingCountry IN ('Brazil','Argentina','Chile')","Set filters","number")
sqlq("S22","Country prefix","Count invoices whose BillingCountry starts with C.",chinook,"chinook",csource+" · country prefix",
     "SELECT COUNT(*) FROM Invoice WHERE BillingCountry LIKE 'C%'","Text matching","number")
sqlq("S23","Invoice-line count","How many InvoiceLine records are there?",chinook,"chinook",csource+" · invoice line items",
     "SELECT COUNT(*) FROM InvoiceLine","Counting","number")
sqlq("S24","Distinct unit prices","How many distinct UnitPrice values occur in InvoiceLine?",chinook,"chinook",csource+" · distinct prices",
     "SELECT COUNT(DISTINCT UnitPrice) FROM InvoiceLine","Distinct values","number")
sqlq("S25","Downloads at each price","Sum Quantity by UnitPrice in InvoiceLine. Return UnitPrice and Downloads in ascending price order.",chinook,"chinook",csource+" · downloads per price",
     "SELECT UnitPrice,SUM(Quantity) AS Downloads FROM InvoiceLine GROUP BY UnitPrice ORDER BY UnitPrice","Grouping and totals")
sqlq("S26","Longest surname","What is the maximum length of LastName in Employee?",chinook,"chinook",csource+" · longest last name",
     "SELECT MAX(LENGTH(LastName)) FROM Employee","Text functions","number")
sqlq("S27","Employee population","How many employees does Chinook have?",chinook,"chinook",csource+" · employee count",
     "SELECT COUNT(*) FROM Employee","Counting","number")
sqlq("S28","Movie release year","Count movies released in 2007.",movies,"movies",msource+" · count adaptation of 1.sql",
     "SELECT COUNT(*) FROM movies WHERE year=2007","Filtering","number")
sqlq("S29","Identify the person","Return Johnny Depp's birth year as a number. Assume the name is unique in this database.",movies,"movies",msource+" · 2.sql",
     "SELECT birth FROM people WHERE name='Johnny Depp'","Filtering","number")
sqlq("S30","Harry Potter cast","List name of all people starring in Harry Potter and the Sorcerer's Stone. Sort alphabetically.",movies,"movies",msource+" · 8.sql",
     "SELECT p.name FROM people p JOIN stars s ON s.person_id=p.id JOIN movies m ON m.id=s.movie_id WHERE m.title='Harry Potter and the Sorcerer''s Stone' ORDER BY p.name","Joins")
sqlq("S31","Top-rated performances","List title and rating for the five highest-rated movies starring Helena Bonham Carter. Sort rating descending, then title for ties.",movies,"movies",msource+" · adaptation of 11.sql",
     "SELECT m.title,r.rating FROM movies m JOIN ratings r ON r.movie_id=m.id JOIN stars s ON s.movie_id=m.id JOIN people p ON p.id=s.person_id WHERE p.name='Helena Bonham Carter' ORDER BY r.rating DESC,m.title LIMIT 5","Joins and ranking")
sqlq("S32","Returns population","Count all negative-Amount transactions in the OSU 2014 subset.",pc_dest,"pcards",pcsource+" · Task 4 Q10, count adaptation",
     "SELECT COUNT(*) FROM pcards WHERE Amount<0","Signed amounts","number")
sqlq("S33","Returned value","Calculate the signed total Amount of returns in the OSU 2014 subset. Enter a negative number rounded to two decimals.",pc_dest,"pcards",pcsource+" · Task 4 Q10, total adaptation",
     "SELECT ROUND(SUM(Amount),2) FROM pcards WHERE Amount<0","Conditional totals","number")
sqlq("S34","Monthly transaction counts","Return Month and Transactions for all months in the OSU 2014 subset, sorted by Month ascending.",pc_dest,"pcards",pcsource+" · Task 4 Q8, month adaptation",
     "SELECT Month,COUNT(*) AS Transactions FROM pcards GROUP BY Month ORDER BY Month","Grouping")
sqlq("S35","At the threshold","Count transactions with Amount >= 5000 in the OSU 2014 subset. Include exactly 5000.",pc_dest,"pcards",pcsource+" · Task 4 Q6",
     "SELECT COUNT(*) FROM pcards WHERE Amount>=5000","Boundary conditions","number")
sqlq("S36","Q1 returns","Find the signed total of returns during January through March in the OSU 2014 subset, using Month. Round to two decimals.",pc_dest,"pcards",pcsource+" · Task 4 Q7",
     "SELECT ROUND(SUM(Amount),2) FROM pcards WHERE Month BETWEEN 1 AND 3 AND Amount<0","Date filters","number")
sqlq("S37","Highest spending vendors","Return Vendor and Total for the five vendors with highest net spend in the OSU 2014 subset. Round Total to two decimals; sort descending Total then Vendor.",pc_dest,"pcards",pcsource+" · Task 4 vendor aggregation adaptation",
     "SELECT Vendor,ROUND(SUM(Amount),2) AS Total FROM pcards GROUP BY Vendor ORDER BY Total DESC,Vendor LIMIT 5","Grouping and totals")
sqlq("S38","Medium-risk returns","Count returns with absolute value at least 500 and strictly below 1000 in the OSU 2014 subset.",pc_dest,"pcards",pcsource+" · Task 4 Q17",
     "SELECT COUNT(*) FROM pcards WHERE Amount<=-500 AND Amount>-1000","Boundary conditions","number")
sqlq("S39","Low-risk returns","Count negative returns with absolute value strictly below 500 in the OSU 2014 subset.",pc_dest,"pcards",pcsource+" · Task 4 Q17",
     "SELECT COUNT(*) FROM pcards WHERE Amount<0 AND Amount>-500","Boundary conditions","number")
sqlq("S40","December tax scenario","Assume all December transactions in the OSU 2014 subset are net of state sales tax. Calculate 4.5% of their net Amount sum, rounded to two decimals.",pc_dest,"pcards",pcsource+" · Task 4 Q13–14",
     "SELECT ROUND(SUM(Amount)*0.045,2) FROM pcards WHERE Month=12","Calculated totals","number")
for i,prior in enumerate([500,750,1250,1500]):
    for j,game in enumerate([0,1]):
        rid=f"R{9+i*2+j:02}"
        value=round(a+b*prior+c*game+d*prior*game,2)
        add(rid,f"Sales scenario · {prior}, {'game' if game else 'no game'}",
            model+f"\n\nPredict sales when PriorYearSales = {prior} and GameDay = {game}. Round to two decimals. These are supplied hypothetical inputs.",
            "Interpretation","Regression prediction",["restaurant"],rsource+" · prediction and interaction tasks","number",value,
            solution=f"Substitute {prior} and {game} into the displayed model: {value:.2f}.")
for i,temp in enumerate([40,50,70,80]):
    value=round(t0+t1*temp,2)
    add(f"R{17+i:02}",f"Temperature scenario · {temp}°F",
        temperature+f"\n\nPredict sales when tmax = {temp}°F. Round to two decimals. This is a supplied-input practice scenario.",
        "Interpretation","Regression prediction",["restaurant"],rsource+" · temperature task","number",value,
        solution=f"Substitute tmax = {temp}: {t0} + {t1}×{temp} = {value:.2f}.")

exams=[
    {"id":"M01","title":"First principles","description":"Film permits, then your first SQL summaries.","minutes":8,"subject":"Manipulation","questions":["X01","X03","X04","S01","S02","S03"]},
    {"id":"M02","title":"Follow the right key","description":"Text extraction, journal lookups and Chinook.","minutes":12,"subject":"Manipulation","questions":["X05","X06","X08","S05","S07","S08"]},
    {"id":"M03","title":"The payroll review","description":"Find incomplete records and quantify their impact.","minutes":10,"subject":"Manipulation","questions":["X09","X10","X11","S13","S14","S15"]},
    {"id":"M04","title":"Connect the evidence","description":"Reconcile data and query movie relationships.","minutes":12,"subject":"Manipulation","questions":["X07","X12","X02","S09","S11","S12"]},
    {"id":"R01","title":"Game day at the restaurant","description":"Predictions, interactions and forecast confidence.","minutes":5,"subject":"Interpretation","questions":["R01","R02","R03","R04"]},
    {"id":"R02","title":"Weather and sales","description":"Temperature predictions and responsible interpretation.","minutes":5,"subject":"Interpretation","questions":["R05","R06","R07","R08"]},
]
for exam in exams:
    exam["minutes"]=5 if exam["subject"]=="Interpretation" else 8
# Stable compositions are built once, not reshuffled on every Streamlit rerun.
# Each added manipulation exam combines three Excel and three SQL questions,
# from exactly one workbook/file and one database.
import random
rng=random.Random(20261020)
excel_groups=[
    ("Film permits",["X01","X02","X03","X04"]+[f"X{i:02}" for i in range(13,31)]),
    ("Journal entries",["X06","X07","X08"]+[f"X{i:02}" for i in range(31,35)]),
    ("2016 payroll",["X09","X10","X11"]+[f"X{i:02}" for i in range(35,40)]),
    ("2015 payroll",[f"X{i:02}" for i in range(40,44)]),
]
sql_groups=[
    ("Songs",["S01","S02","S03","S04","S17","S18","S19","S20"]),
    ("Chinook",["S05","S06","S07","S08"]+[f"S{i:02}" for i in range(21,28)]),
    ("Movies",["S09","S10","S11","S12"]+[f"S{i:02}" for i in range(28,32)]),
    ("P-cards",["S13","S14","S15","S16"]+[f"S{i:02}" for i in range(32,41)]),
]
seen={tuple(sorted(e["questions"])) for e in exams}
for exlabel,exids in excel_groups:
    for sqllabel,sqlids in sql_groups:
        for variant in range(3):
            while True:
                ids=rng.sample(exids,3)+rng.sample(sqlids,3)
                signature=tuple(sorted(ids))
                if signature not in seen:break
            seen.add(signature)
            exams.append({"id":f"M{sum(e['subject']=='Manipulation' for e in exams)+1:02}",
                "title":f"{exlabel} + {sqllabel} · {variant+1}",
                "description":"Three Excel tasks and three SQL tasks. Download both files before starting.",
                "minutes":8,"subject":"Manipulation","questions":ids})
for i,rid in enumerate([f"R{n:02}" for n in range(9,17)]):
    exams.append({"id":f"R{i+3:02}","title":f"Restaurant interactions · {i+1}",
        "description":"A new prediction scenario, conditional effects and forecast reasoning.",
        "minutes":5,"subject":"Interpretation","questions":[rid,"R02","R03","R04"]})
for i,rid in enumerate([f"R{n:02}" for n in range(17,21)]):
    exams.append({"id":f"R{i+11:02}","title":f"Temperature interpretation · {i+1}",
        "description":"A new temperature scenario, slope interpretation and data preparation.",
        "minutes":5,"subject":"Interpretation","questions":[rid,"R06","R07","R08"]})
# Compact schema-only context lets the tutor use real names without uploading files.
for key,meta in datasets.items():
    path=locate(meta["download_name"]) if key!="pcards" else pc_dest
    if path.suffix in (".db",".sqlite"):
        with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro",uri=True) as conn:
            tables=conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            meta["structure"]={name:[{"column":r[1],"type":r[2]} for r in conn.execute('PRAGMA table_info("'+name.replace('"','""')+'")')] for (name,) in tables}
    elif path.suffix in (".xlsx",".xlsm"):
        book=pd.ExcelFile(path)
        meta["structure"]={sheet:list(pd.read_excel(book,sheet_name=sheet,nrows=0).columns.astype(str)) for sheet in book.sheet_names}
    else:
        meta["structure"]={"delimiter":"|" if key in ("pay15","pay16","jobs") else ",",
                           "columns":list(pd.read_csv(path,sep="|" if key in ("pay15","pay16","jobs") else ",",nrows=0).columns)}
content={"version":"2026.10.20.2","datasets":datasets,"questions":questions,"exams":exams}
(DATA/"catalog.json").write_text(json.dumps(content,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
print(f"Built {len(questions)} questions, {len(exams)} exams and {len(datasets)} datasets.")
