# SBIR Data Dictionary & CSV Analysis

Generated: 2025-10-26T10:09:00.382182 UTC

## Summary

- CSV rows: **6**
- CSV columns: **42**
- Dictionary columns: **47**

## Comparison

### Missing in CSV (present in data dictionary)

- Company Name
- Title
- Contract/Grant #
- DUNS
- HubZone Owned
- Women-Owned
- Company Url
- Address 1
- Address 2
- Research Area Keywords
- Award Link
- POINT OF CONTACT
- PRINCIPAL INVESTIGATOR
- RESEARCH INSTITUTION (STTR ONLY)

### Extra columns in CSV (not in data dictionary)

- Company
- Address1
- Address2
- Company Website
- Award Title
- Contract
- Duns
- HUBZone Owned
- Woman Owned

## Column Summaries (CSV)

### `Company`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"Acme Innovations": 1, "BioTech Labs": 1, "NanoWorks": 1, "TechStart Inc": 1, "GreenEnergy Corp": 1}
- Examples: 'Acme Innovations', 'BioTech Labs', 'NanoWorks', 'TechStart Inc', 'GreenEnergy Corp'

### `Address1`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: string
- Top values: {"123 Main St": 1, "456 Bio Rd": 1, "456 Nano Way": 1, "789 Tech Blvd": 1, "101 Green St": 1}
- Examples: '123 Main St', '456 Bio Rd', '456 Nano Way', '789 Tech Blvd', '101 Green St'

### `Address2`

- Missing: 83.33%
- Unique values: 1
- Type suggestion: string
- Top values: {"Suite 200": 1}
- Examples: 'Suite 200'

### `City`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: string
- Top values: {"Anytown": 1, "Bioville": 1, "Cambridge": 1, "Austin": 1, "Seattle": 1}
- Examples: 'Anytown', 'Bioville', 'Cambridge', 'Austin', 'Seattle'

### `State`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: string
- Top values: {"CA": 1, "MD": 1, "MA": 1, "TX": 1, "WA": 1}
- Examples: 'CA', 'MD', 'MA', 'TX', 'WA'

### `Zip`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: numeric
- Top values: {"94105": 1, "21201-1234": 1, "02139": 1, "78701": 1, "98101": 1}
- Examples: '94105', '21201-1234', '02139', '78701', '98101'

### `Company Website`

- Missing: 50.0%
- Unique values: 3
- Type suggestion: string
- Top values: {"https://acme.example.com": 1, "http://biotech.example.org": 1, "https://techstart.com": 1}
- Examples: 'https://acme.example.com', 'http://biotech.example.org', 'https://techstart.com'

### `Number of Employees`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: date
- Top values: {"50": 1, "120": 1, "25": 1, "1,000": 1, "500": 1}
- Examples: '50', '120', '25', '1,000', '500'

### `Award Title`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"Next-Gen Rocket Fuel": 1, "Novel Antiviral Platform": 1, "Nano-scale Sensors": 1, "AI for Healthcare": 1, "Sustainable Energy Solutions": 1}
- Examples: 'Next-Gen Rocket Fuel', 'Novel Antiviral Platform', 'Nano-scale Sensors', 'AI for Healthcare', 'Sustainable Energy Solutions'

### `Abstract`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"Research on high-efficiency rocket propellants, focusing on stability": 1, "Develop platform to rapidly identify antiviral compounds, validate in vitro": 1, "Development of nano-scale sensor technology": 1, "Applying AI to medical diagnostics, evaluate on retrospective cohorts": 1, "Developing renewable energy tech, prototypes and field trials": 1}
- Examples: 'Research on high-efficiency rocket propellants, focusing on stability', 'Develop platform to rapidly identify antiviral compounds, validate in vitro', 'Development of nano-scale sensor technology', 'Applying AI to medical diagnostics, evaluate on retrospective cohorts', 'Developing renewable energy tech, prototypes and field trials'

### `Agency`

- Missing: 0.0%
- Unique values: 5
- Type suggestion: string
- Top values: {"DOD": 2, "NASA": 1, "HHS": 1, "NSF": 1, "DOE": 1}
- Examples: 'NASA', 'HHS', 'DOD', 'NSF', 'DOE'

### `Branch`

- Missing: 33.33%
- Unique values: 3
- Type suggestion: string
- Top values: {"Army": 2, "Aerospace Research": 1, "NIH": 1}
- Examples: 'Aerospace Research', 'NIH', 'Army', 'Army'

### `Phase`

- Missing: 0.0%
- Unique values: 2
- Type suggestion: string
- Top values: {"Phase I": 4, "Phase II": 2}
- Examples: 'Phase I', 'Phase II', 'Phase I', 'Phase I', 'Phase II'

### `Program`

- Missing: 0.0%
- Unique values: 2
- Type suggestion: string
- Top values: {"SBIR": 5, "STTR": 1}
- Examples: 'SBIR', 'STTR', 'SBIR', 'SBIR', 'SBIR'

### `Topic Code`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"RX-101": 1, "BT-22": 1, "NW-001": 1, "TS-45": 1, "GE-10": 1}
- Examples: 'RX-101', 'BT-22', 'NW-001', 'TS-45', 'GE-10'

### `Award Amount`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: numeric
- Top values: {"500000.00": 1, "1,500,000.50": 1, "75,000": 1, "1,000,000.00": 1, "2500000": 1}
- Examples: '500000.00', '1,500,000.50', '75,000', '1,000,000.00', '2500000'

### `Award Year`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: date
- Top values: {"2023": 1, "2021": 1, "2019": 1, "2022": 1, "2020": 1}
- Examples: '2023', '2021', '2019', '2022', '2020'

### `Proposal Award Date`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: date
- Top values: {"2023-06-15": 1, "2021-08-01": 1, "2019-01-10": 1, "05/15/2022": 1, "10-01-2020": 1}
- Examples: '2023-06-15', '2021-08-01', '2019-01-10', '05/15/2022', '10-01-2020'

### `Contract End Date`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: date
- Top values: {"2024-06-14": 1, "2023-08-01": 1, "2019-12-31": 1, "05/14/2024": 1, "10-01-2022": 1}
- Examples: '2024-06-14', '2023-08-01', '2019-12-31', '05/14/2024', '10-01-2022'

### `Solicitation Close Date`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: date
- Top values: {"2023-03-01": 1, "2021-05-01": 1, "2019-01-05": 1, "02/01/2022": 1, "07-01-2020": 1}
- Examples: '2023-03-01', '2021-05-01', '2019-01-05', '02/01/2022', '07-01-2020'

### `Proposal Receipt Date`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: date
- Top values: {"2023-02-15": 1, "2021-04-15": 1, "2019-01-05": 1, "01/15/2022": 1, "06-15-2020": 1}
- Examples: '2023-02-15', '2021-04-15', '2019-01-05', '01/15/2022', '06-15-2020'

### `Date of Notification`

- Missing: 16.67%
- Unique values: 5
- Type suggestion: date
- Top values: {"2023-06-01": 1, "2021-07-20": 1, "2019-01-05": 1, "05/01/2022": 1, "09-20-2020": 1}
- Examples: '2023-06-01', '2021-07-20', '2019-01-05', '05/01/2022', '09-20-2020'

### `Agency Tracking Number`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"ATN-0001": 1, "ATN-0002": 1, "ATN-0100": 1, "ATN-0003": 1, "ATN-0004": 1}
- Examples: 'ATN-0001', 'ATN-0002', 'ATN-0100', 'ATN-0003', 'ATN-0004'

### `Contract`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"C-2023-0001": 1, "C-2021-0420": 1, "C-2019-0001": 1, "C-2022-0003": 1, "C-2020-0004": 1}
- Examples: 'C-2023-0001', 'C-2021-0420', 'C-2019-0001', 'C-2022-0003', 'C-2020-0004'

### `Solicitation Number`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: string
- Top values: {"SOL-2023-01": 1, "SOL-2021-03": 1, "SOL-2019-01": 1, "SOL-2022-05": 1, "SOL-2020-07": 1}
- Examples: 'SOL-2023-01', 'SOL-2021-03', 'SOL-2019-01', 'SOL-2022-05', 'SOL-2020-07'

### `Solicitation Year`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: date
- Top values: {"2023": 1, "2021": 1, "2019": 1, "2022": 1, "2020": 1}
- Examples: '2023', '2021', '2019', '2022', '2020'

### `UEI`

- Missing: 0.0%
- Unique values: 6
- Type suggestion: uei
- Top values: {"A1B2C3D4E5F6": 1, "Z9Y8X7W6V5U4": 1, "NWUEI0000000": 1, "TSUEI1234567": 1, "GREENUEI0000": 1}
- Examples: 'A1B2C3D4E5F6', 'Z9Y8X7W6V5U4', 'NWUEI0000000', 'TSUEI1234567', 'GREENUEI0000'

### `Duns`

- Missing: 0.0%
- Unique values: 5
- Type suggestion: numeric
- Top values: {"987654321": 2, "123456789": 1, "000000001": 1, "123-456-789": 1, "000000002": 1}
- Examples: '123456789', '987654321', '000000001', '123-456-789', '987654321'

### `HUBZone Owned`

- Missing: 0.0%
- Unique values: 2
- Type suggestion: string
- Top values: {"N": 3, "Y": 3}
- Examples: 'N', 'Y', 'N', 'Y', 'N'

### `Socially and Economically Disadvantaged`

- Missing: 0.0%
- Unique values: 2
- Type suggestion: string
- Top values: {"N": 4, "Y": 2}
- Examples: 'Y', 'N', 'N', 'Y', 'N'

### `Woman Owned`

- Missing: 0.0%
- Unique values: 2
- Type suggestion: string
- Top values: {"N": 4, "Y": 2}
- Examples: 'N', 'Y', 'N', 'Y', 'N'

### `Contact Name`

- Missing: 33.33%
- Unique values: 4
- Type suggestion: string
- Top values: {"Jane Doe": 1, "Sam Biotech": 1, "Tom Inventor": 1, "John Tech": 1}
- Examples: 'Jane Doe', 'Sam Biotech', 'Tom Inventor', 'John Tech'

### `Contact Title`

- Missing: 33.33%
- Unique values: 3
- Type suggestion: string
- Top values: {"Founder": 2, "CEO": 1, "CTO": 1}
- Examples: 'CEO', 'CTO', 'Founder', 'Founder'

### `Contact Phone`

- Missing: 33.33%
- Unique values: 4
- Type suggestion: string
- Top values: {"555-123-4567": 1, "410-555-0199": 1, "555-000-0000": 1, "512-555-0123": 1}
- Examples: '555-123-4567', '410-555-0199', '555-000-0000', '512-555-0123'

### `Contact Email`

- Missing: 33.33%
- Unique values: 4
- Type suggestion: string
- Top values: {"jane.doe@acme.example.com": 1, "contact@biotech.example.org": 1, "tom@nanoworks.example.com": 1, "john@techstart.com": 1}
- Examples: 'jane.doe@acme.example.com', 'contact@biotech.example.org', 'tom@nanoworks.example.com', 'john@techstart.com'

### `PI Name`

- Missing: 50.0%
- Unique values: 3
- Type suggestion: string
- Top values: {"Dr. Alan Smith": 1, "Dr. Susan Lee": 1, "Dr. Jane AI": 1}
- Examples: 'Dr. Alan Smith', 'Dr. Susan Lee', 'Dr. Jane AI'

### `PI Title`

- Missing: 50.0%
- Unique values: 3
- Type suggestion: uei
- Top values: {"Lead Scientist": 1, "Principal Investigator": 1, "AI Researcher": 1}
- Examples: 'Lead Scientist', 'Principal Investigator', 'AI Researcher'

### `PI Phone`

- Missing: 50.0%
- Unique values: 3
- Type suggestion: string
- Top values: {"555-987-6543": 1, "410-555-0200": 1, "512-555-0124": 1}
- Examples: '555-987-6543', '410-555-0200', '512-555-0124'

### `PI Email`

- Missing: 50.0%
- Unique values: 3
- Type suggestion: string
- Top values: {"alan.smith@acme.example.com": 1, "susan.lee@biotech.example.org": 1, "jane@techstart.com": 1}
- Examples: 'alan.smith@acme.example.com', 'susan.lee@biotech.example.org', 'jane@techstart.com'

### `RI Name`

- Missing: 83.33%
- Unique values: 1
- Type suggestion: string
- Top values: {"Bio Research Institute": 1}
- Examples: 'Bio Research Institute'

### `RI POC Name`

- Missing: 83.33%
- Unique values: 1
- Type suggestion: string
- Top values: {"Alice Researcher": 1}
- Examples: 'Alice Researcher'

### `RI POC Phone`

- Missing: 83.33%
- Unique values: 1
- Type suggestion: string
- Top values: {"410-555-0210": 1}
- Examples: '410-555-0210'

## Data Dictionary Extract (first 50 entries)

- **UEI** — _Text_ — **REQUIRED**
- **Company Name** — _Text_ — **REQUIRED**
- **Title** — _Text_ — **REQUIRED**
- **Agency** — _Dropdown_ — **REQUIRED**
- **Branch** — _Dropdown_
- **Phase** — _Radio_ — **REQUIRED**
- **Program** — _Radio_ — **REQUIRED**
- **Agency Tracking Number** — _Text_ — **REQUIRED**
- **Contract/Grant #** — _Text_ — **REQUIRED**
- **Proposal Award Date** — _Date_
- **Contract End Date** — _Date_
- **Solicitation Number** — _Text_
- **Solicitation Year** — _Text_ — **REQUIRED**
- **Solicitation Close Date** — _Date_
- **Proposal Receipt Date** — _Date_ — **REQUIRED**
- **Date of Notification** — _Date_
- **Topic Code** — _Text_ — **REQUIRED**
- **Award Year** — _Dropdown_ — **REQUIRED**
- **Award Amount** — _Text_ — **REQUIRED**
- **DUNS** — _Text_
- **HubZone Owned** — _Radio_ — **REQUIRED**
- **Socially and Economically Disadvantaged** — _Radio_ — **REQUIRED**
- **Women-Owned** — _Radio_ — **REQUIRED**
- **Number of Employees** — _Text_
- **Company Url** — _Text_
- **Address 1** — _Text_ — **REQUIRED**
- **Address 2** — _Text_
- **City** — _Text_ — **REQUIRED**
- **State** — _Dropdown_ — **REQUIRED**
- **Zip** — _Text_ — **REQUIRED**
- **Research Area Keywords** — _Text_
- **Abstract** — _Text Area_ — **REQUIRED**
- **Award Link** — _Text_
- **POINT OF CONTACT**
- **Contact Name** — _Text_
- **Contact Title** — _Text_
- **Contact Phone** — _Text_ — **REQUIRED**
- **Contact Email** — _Text_ — **REQUIRED**
- **PRINCIPAL INVESTIGATOR**
- **PI Name** — _Text_
- **PI Title** — _Text_
- **PI Phone** — _Text_ — **REQUIRED**
- **PI Email** — _Text_ — **REQUIRED**
- **RESEARCH INSTITUTION (STTR ONLY)**
- **RI Name** — _Text_ — **REQUIRED**
- **RI POC Name** — _Text_
- **RI POC Phone** — _Text_
## Suggested Validators / Coercions

### `UEI`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: uei
- **coerce**: strip non-alnum, uppercase; expect 12 chars
- **validator**: warn if not 12 chars

### `Company Name`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `Title`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `Agency`

- **dtype_hint**: Dropdown
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Branch`

- **dtype_hint**: Dropdown
- **pct_missing**: 33.33
- **dtype_suggestion**: string

### `Phase`

- **dtype_hint**: Radio
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Program`

- **dtype_hint**: Radio
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Agency Tracking Number`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Contract/Grant #`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `Proposal Award Date`

- **dtype_hint**: Date
- **pct_missing**: 0.0
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Contract End Date`

- **dtype_hint**: Date
- **pct_missing**: 16.67
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Solicitation Number`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Solicitation Year`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Solicitation Close Date`

- **dtype_hint**: Date
- **pct_missing**: 16.67
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Proposal Receipt Date`

- **dtype_hint**: Date
- **pct_missing**: 16.67
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Date of Notification`

- **dtype_hint**: Date
- **pct_missing**: 16.67
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Topic Code`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Award Year`

- **dtype_hint**: Dropdown
- **pct_missing**: 0.0
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Award Amount`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: numeric
- **coerce**: strip commas, cast to float
- **validator**: positive and reasonable range (domain specific)

### `DUNS`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `HubZone Owned`

- **dtype_hint**: Radio
- **note**: column not present in CSV or no data summary available

### `Socially and Economically Disadvantaged`

- **dtype_hint**: Radio
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Women-Owned`

- **dtype_hint**: Radio
- **note**: column not present in CSV or no data summary available

### `Number of Employees`

- **dtype_hint**: Text
- **pct_missing**: 0.0
- **dtype_suggestion**: date
- **coerce**: parse ISO, YYYY-MM-DD, MM/DD/YYYY, MM-DD-YYYY, etc.

### `Company Url`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `Address 1`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `Address 2`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `City`

- **dtype_hint**: Text
- **pct_missing**: 16.67
- **dtype_suggestion**: string

### `State`

- **dtype_hint**: Dropdown
- **pct_missing**: 16.67
- **dtype_suggestion**: string

### `Zip`

- **dtype_hint**: Text
- **pct_missing**: 16.67
- **dtype_suggestion**: numeric
- **coerce**: strip commas, cast to float
- **validator**: positive and reasonable range (domain specific)

### `Research Area Keywords`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `Abstract`

- **dtype_hint**: Text Area
- **pct_missing**: 0.0
- **dtype_suggestion**: string

### `Award Link`

- **dtype_hint**: Text
- **note**: column not present in CSV or no data summary available

### `POINT OF CONTACT`

- **note**: column not present in CSV or no data summary available

### `Contact Name`

- **dtype_hint**: Text
- **pct_missing**: 33.33
- **dtype_suggestion**: string

### `Contact Title`

- **dtype_hint**: Text
- **pct_missing**: 33.33
- **dtype_suggestion**: string

### `Contact Phone`

- **dtype_hint**: Text
- **pct_missing**: 33.33
- **dtype_suggestion**: string

### `Contact Email`

- **dtype_hint**: Text
- **pct_missing**: 33.33
- **dtype_suggestion**: string

### `PRINCIPAL INVESTIGATOR`

- **note**: column not present in CSV or no data summary available

### `PI Name`

- **dtype_hint**: Text
- **pct_missing**: 50.0
- **dtype_suggestion**: string

### `PI Title`

- **dtype_hint**: Text
- **pct_missing**: 50.0
- **dtype_suggestion**: uei
- **coerce**: strip non-alnum, uppercase; expect 12 chars
- **validator**: warn if not 12 chars

### `PI Phone`

- **dtype_hint**: Text
- **pct_missing**: 50.0
- **dtype_suggestion**: string

### `PI Email`

- **dtype_hint**: Text
- **pct_missing**: 50.0
- **dtype_suggestion**: string

### `RESEARCH INSTITUTION (STTR ONLY)`

- **note**: column not present in CSV or no data summary available

### `RI Name`

- **dtype_hint**: Text
- **pct_missing**: 83.33
- **dtype_suggestion**: string

### `RI POC Name`

- **dtype_hint**: Text
- **pct_missing**: 83.33
- **dtype_suggestion**: string

### `RI POC Phone`

- **dtype_hint**: Text
- **pct_missing**: 83.33
- **dtype_suggestion**: string

## Notes & Next Steps

- Review columns marked 'missing in CSV' to determine whether they are optional or upstream is missing data.
- Implement coercion helpers for numeric/date fields, and add explicit validators for UEI/DUNS/ZIP based on suggestions above.
- Expand CSV fixtures with edge cases (missing UEI, varied date formats, amount strings with commas) for robust unit tests.

---
Report generated by sbir-etl/scripts/analyze_data_dictionary_and_csv.py
