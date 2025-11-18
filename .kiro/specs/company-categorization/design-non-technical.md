# Company Categorization System: Non-Technical Overview

## What This System Does

The Company Categorization System automatically classifies SBIR award recipients into three categories based on their complete federal contract portfolio:

- **Product-leaning companies**: Firms whose federal contracts are primarily for delivering physical products or hardware
- **Service-leaning companies**: Firms whose federal contracts are primarily for providing services or research and development work
- **Mixed companies**: Firms with a balanced portfolio of both product and service contracts

This classification helps understand the business model and capabilities of SBIR companies beyond just their SBIR awards.

## Why This Matters

When you look at SBIR awards alone, it's hard to tell whether a company is primarily a product manufacturer, a service provider, or both. By examining their entire federal contract portfolio—including non-SBIR contracts from USAspending—we get a clearer picture of what these companies actually do. This information is valuable for:

- **Program managers** evaluating company capabilities
- **Analysts** studying SBIR program outcomes
- **Researchers** understanding the SBIR ecosystem
- **Policy makers** assessing program effectiveness

## How It Works: The Two-Step Process

### Step 1: Classifying Individual Contracts

For each federal contract a company has received, the system determines whether it's a Product, Service, or R&D contract. It does this by looking at several pieces of information:

**Product Service Codes (PSC)**
- If the PSC starts with a number (like "1234"), it's typically a product contract
- If the PSC starts with a letter (like "R425"), it's typically a service contract
- If the PSC starts with "A" or "B", it's typically a research and development contract

**Contract Type and Pricing**
- Cost-plus contracts (CPFF) and time-and-materials (T&M) contracts are almost always services
- Fixed-price contracts (FFP) can be either products or services, so the system looks at other clues

**Contract Description**
- The system scans the contract description for keywords like "prototype," "hardware," or "device" to identify product contracts
- This helps catch cases where a fixed-price contract is actually for a product, even if the PSC suggests otherwise

**SBIR Phase Adjustments**
- For SBIR Phase I and Phase II awards, the system recognizes these are research and development work, regardless of other indicators
- However, if an SBIR award has a numeric PSC (indicating a product), it keeps the Product classification

### Step 2: Aggregating to Company Level

Once all of a company's contracts are classified, the system combines them to determine the company's overall category. Here's how:

**Dollar-Weighted Calculation**
- The system calculates what percentage of the company's total contract dollars come from product contracts versus service/R&D contracts
- This means a $10 million product contract counts more than a $100,000 service contract

**Classification Rules**
- If 60% or more of contract dollars are from products → **Product-leaning**
- If 60% or more of contract dollars are from services/R&D → **Service-leaning**
- If neither reaches 60% → **Mixed**

**Special Cases**
- Companies with fewer than 2 contracts are marked as **Uncertain** (not enough data)
- Companies with contracts spanning more than 6 different PSC families are automatically classified as **Mixed** (they're likely integrators or diversified firms)

**Confidence Levels**
- **High confidence**: Companies with 6+ contracts (enough data for reliable classification)
- **Medium confidence**: Companies with 3-5 contracts (reasonable data, but less certain)
- **Low confidence**: Companies with 2 or fewer contracts (very limited data)

## What Data Is Used

The system uses data from **USAspending.gov**, the official federal spending database. For each SBIR company, it retrieves:

- All federal contracts (not just SBIR awards)
- Contract amounts and dates
- Product Service Codes (PSC)
- Contract types and pricing mechanisms
- Contract descriptions
- Company identifiers (UEI, DUNS, CAGE codes)

The system matches companies using their Unique Entity Identifier (UEI), DUNS number, or CAGE code to ensure it captures all their federal contracts.

## What the Results Look Like

For each company, the system produces:

- **Classification**: Product-leaning, Service-leaning, Mixed, or Uncertain
- **Product percentage**: What share of their contract dollars come from product contracts
- **Service percentage**: What share of their contract dollars come from service/R&D contracts
- **Confidence level**: How reliable the classification is (High, Medium, or Low)
- **Supporting details**: Number of contracts analyzed, total contract dollars, etc.

## Example Scenarios

**Example 1: Product-Leaning Company**
- A company has 20 federal contracts totaling $50 million
- $35 million (70%) comes from contracts with numeric PSC codes for hardware and equipment
- $15 million (30%) comes from service contracts
- **Result**: Product-leaning (High confidence)

**Example 2: Service-Leaning Company**
- A company has 15 federal contracts totaling $30 million
- $25 million (83%) comes from research and development contracts (PSC codes starting with A or B)
- $5 million (17%) comes from product contracts
- **Result**: Service-leaning (High confidence)

**Example 3: Mixed Company**
- A company has 25 federal contracts totaling $40 million
- $18 million (45%) from product contracts
- $22 million (55%) from service contracts
- Neither category reaches 60%
- **Result**: Mixed (High confidence)

**Example 4: Uncertain Classification**
- A company has only 1 SBIR Phase II award
- No other federal contracts found in USAspending
- **Result**: Uncertain (Low confidence - insufficient data)

## Handling Edge Cases

The system is designed to handle real-world data challenges:

- **Missing data**: If a contract is missing key information, it's skipped rather than causing errors
- **No contracts found**: If a company has no USAspending records, they're marked as Uncertain
- **Data quality issues**: The system logs warnings but continues processing other companies
- **Large portfolios**: Companies with hundreds of contracts are processed efficiently

## Quality Assurance

The system includes built-in checks to ensure reliability:

- **Completeness check**: At least 80% of companies should receive a classification (not Uncertain)
- **Validation dataset**: The system is tested against a real dataset of 200+ high-volume SBIR companies with 100+ awards each
- **Audit trail**: Each classification includes details about which contracts contributed to the decision

## Limitations

It's important to understand what this system does and doesn't do:

**What it does:**
- Classifies companies based on their federal contract portfolio
- Uses official USAspending data
- Provides confidence levels to indicate reliability

**What it doesn't do:**
- Classify companies based on their commercial activities (only federal contracts)
- Guarantee 100% accuracy (some contracts are ambiguous)
- Replace human judgment for critical decisions

**Known limitations:**
- Companies with very few contracts may be classified as Uncertain
- Some contracts are genuinely ambiguous and may be misclassified
- The system only looks at federal contracts, not commercial sales or other revenue sources

## How This Fits Into the Bigger Picture

This categorization system is part of a larger SBIR analytics platform that:

1. Collects SBIR award data from SBIR.gov
2. Enriches it with additional federal contract data from USAspending
3. Links it with patent data from the USPTO
4. Stores everything in a graph database for analysis
5. Provides insights about SBIR companies, their capabilities, and program outcomes

The company categorization adds an important dimension to understanding SBIR companies beyond just their SBIR awards, helping stakeholders make more informed decisions about the program and its participants.

