# SBIR Sample Data

This directory contains sample SBIR (Small Business Innovation Research) award data for testing purposes.

## Files

- `sbir_sample.csv`: Sample dataset with 100 SBIR/STTR award records

## Data Structure

The CSV file contains 42 columns matching the structure of the actual SBIR.gov awards database:

### Company Information (7 columns)

- `Company`: Company name (string)
- `Address1`: Primary street address (string)
- `Address2`: Secondary address (string, optional)
- `City`: City name (string)
- `State`: 2-letter state code (string)
- `Zip`: ZIP code (5 or 9 digits, string)
- `Company Website`: Website URL (string, optional)
- `Number of Employees`: Employee count (integer, optional)

### Award Details (7 columns)

- `Award Title`: Project title (string)
- `Abstract`: Project description (string, optional)
- `Agency`: Federal agency (e.g., NASA, NSF, DOD, DOE, HHS)
- `Branch`: Agency branch/division (string, optional)
- `Phase`: Phase I, Phase II, or Phase III
- `Program`: SBIR or STTR
- `Topic Code`: Solicitation topic code (string, optional)

### Financial & Timeline (5 columns)

- `Award Amount`: Award amount in USD (float)
- `Award Year`: Year of award (integer, 1983-2026)
- `Proposal Award Date`: Award date (YYYY-MM-DD format)
- `Contract End Date`: Contract end date (YYYY-MM-DD format)
- `Solicitation Close Date`: Solicitation deadline (YYYY-MM-DD, optional)

### Additional Dates (3 columns)

- `Proposal Receipt Date`: Date proposal received (YYYY-MM-DD, optional)
- `Date of Notification`: Notification date (YYYY-MM-DD, optional)

### Tracking (4 columns)

- `Agency Tracking Number`: Agency's internal tracking ID
- `Contract`: Contract/grant number
- `Solicitation Number`: Solicitation number
- `Solicitation Year`: Year of solicitation (integer, optional)

### Identifiers (2 columns)

- `UEI`: Unique Entity Identifier (12 alphanumeric characters)
- `Duns`: DUNS number (9 digits)

### Business Classifications (3 columns)

- `HUBZone Owned`: HUBZone business (Y/N, optional)
- `Socially and Economically Disadvantaged`: Disadvantaged business (Y/N, optional)
- `Woman Owned`: Woman-owned business (Y/N, optional)

### Contact Information (4 columns)

- `Contact Name`: Primary contact name
- `Contact Title`: Contact job title
- `Contact Phone`: Contact phone number
- `Contact Email`: Contact email address

### Principal Investigator (4 columns)

- `PI Name`: Principal Investigator name
- `PI Title`: PI job title
- `PI Phone`: PI phone number
- `PI Email`: PI email address

### Research Institution (3 columns)

- `RI Name`: Research Institution name (optional)
- `RI POC Name`: RI Point of Contact name (optional)
- `RI POC Phone`: RI POC phone number (optional)

## Data Characteristics

### Representative Records

- 100 total records
- Mix of SBIR and STTR programs
- All major federal agencies represented
- Various company sizes (1-1000 employees)
- Award amounts from $50K to $10M

### Edge Cases Included

- **Missing UEI**: ~20% of records have empty UEI field
- **Old awards**: Records from 1983-1990
- **High amounts**: Awards exceeding $9M (near maximum)
- **Invalid data**: Some records with invalid phone formats for validation testing
- **Incomplete records**: Various optional fields left blank

### Data Quality

- Most records are valid and representative
- Includes realistic company names, addresses, and project titles
- Dates are consistent (award date ≤ end date)
- Phone numbers and emails follow standard formats (with some intentional invalid examples)

## Usage

This sample data is used for:

- Unit testing of SBIR validators
- Integration testing of ETL pipelines
- Performance testing with known dataset size
- Validation rule testing with edge cases

The data is generated programmatically with random.seed(42) for reproducible results.
