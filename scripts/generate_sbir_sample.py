#!/usr/bin/env python3
"""
Generate sample SBIR CSV data for testing.

Creates 100 representative records with edge cases and invalid data.
"""

import csv
import random

# CSV columns (42 total)
COLUMNS = [
    "Company",
    "Address1",
    "Address2",
    "City",
    "State",
    "Zip",
    "Company Website",
    "Number of Employees",
    "Award Title",
    "Abstract",
    "Agency",
    "Branch",
    "Phase",
    "Program",
    "Topic Code",
    "Award Amount",
    "Award Year",
    "Proposal Award Date",
    "Contract End Date",
    "Solicitation Close Date",
    "Proposal Receipt Date",
    "Date of Notification",
    "Agency Tracking Number",
    "Contract",
    "Solicitation Number",
    "Solicitation Year",
    "UEI",
    "Duns",
    "HUBZone Owned",
    "Socially and Economically Disadvantaged",
    "Woman Owned",
    "Contact Name",
    "Contact Title",
    "Contact Phone",
    "Contact Email",
    "PI Name",
    "PI Title",
    "PI Phone",
    "PI Email",
    "RI Name",
    "RI POC Name",
    "RI POC Phone",
]

# Sample data pools
COMPANY_NAMES = [
    "Acme Innovations",
    "BioTech Labs",
    "NanoWorks",
    "TechStart Inc",
    "GreenEnergy Corp",
    "StartupXYZ",
    "Quantum Computing LLC",
    "MedTech Solutions",
    "AeroSpace Dynamics",
    "CyberSec Systems",
    "DataViz Pro",
    "EcoMaterials Inc",
    "FinTech Innovations",
    "GeoSpatial Tech",
    "HealthAI Partners",
    "IoT Devices Co",
    "Jet Propulsion Labs",
    "Knowledge Base Inc",
    "Logistics Pro",
    "Mobile Apps LLC",
    "Neural Networks Corp",
    "Optics Research",
    "Photonics Ltd",
    "Quantum Sensors",
    "Robotics Inc",
    "SolarTech Systems",
    "ThermoDynamics",
    "UltraSound Tech",
    "Virtual Reality Co",
    "Wireless Networks",
    "Xenon Technologies",
    "Yield Optimization",
    "Zero Waste Inc",
]

CITIES = [
    "Anytown",
    "Bioville",
    "Cambridge",
    "Austin",
    "Seattle",
    "Boston",
    "Chicago",
    "Denver",
    "Atlanta",
    "Phoenix",
    "Portland",
    "Miami",
    "Dallas",
    "Salt Lake City",
]

STATES = ["CA", "MD", "MA", "TX", "WA", "NY", "IL", "CO", "GA", "AZ", "OR", "FL", "TX", "UT"]

AGENCIES = ["NASA", "NSF", "DOD", "DOE", "HHS", "USDA", "DOC", "DOT", "EPA", "NOAA"]

BRANCHES = ["Aerospace Research", "NIH", "Army", "Navy", "Air Force", "", "DARPA", "NIST"]

TOPICS = [
    "RX-101",
    "BT-22",
    "NW-001",
    "TS-45",
    "GE-10",
    "SX-01",
    "QC-01",
    "MT-02",
    "AD-03",
    "CS-04",
    "DV-05",
    "EM-06",
    "FT-07",
    "GS-08",
    "HA-09",
    "ID-10",
]

TITLES = [
    "Next-Gen Rocket Fuel",
    "Novel Antiviral Platform",
    "Nano-scale Sensors",
    "AI for Healthcare",
    "Sustainable Energy Solutions",
    "Innovative Widget",
    "Quantum Computing Algorithms",
    "Medical Device Innovation",
    "Advanced Propulsion",
    "Cybersecurity Framework",
    "Data Visualization Tools",
    "Eco-friendly Materials",
    "Financial Technology Platform",
    "Geospatial Analysis",
    "AI Healthcare Diagnostics",
    "IoT Sensor Networks",
    "Jet Engine Optimization",
    "Knowledge Graph Database",
    "Supply Chain Optimization",
    "Mobile Application Suite",
    "Neural Network Models",
    "Optical Systems",
    "Photonics Applications",
    "Quantum Sensing",
    "Robotics Automation",
    "Solar Energy Systems",
    "Thermal Management",
    "Ultrasound Technology",
    "Virtual Reality Training",
    "Wireless Communication",
    "Xenon-based Systems",
    "Yield Prediction Models",
    "Waste Reduction Technology",
]

ABSTRACTS = [
    "Research on high-efficiency rocket propellants, focusing on stability",
    "Develop platform to rapidly identify antiviral compounds, validate in vitro",
    "Development of nano-scale sensor technology",
    "Applying AI to medical diagnostics, evaluate on retrospective cohorts",
    "Developing renewable energy tech, prototypes and field trials",
    "Building the next big thing in widget technology",
    "Advanced algorithms for quantum computing applications",
    "Innovative medical devices for better patient outcomes",
    "Next-generation propulsion systems for aerospace",
    "Comprehensive cybersecurity framework for enterprise",
    "Advanced data visualization and analytics tools",
    "Sustainable materials for environmental applications",
    "Cutting-edge financial technology solutions",
    "Geospatial analysis and mapping technologies",
    "AI-powered healthcare diagnostic systems",
    "Internet of Things sensor network development",
    "Optimization of jet engine performance",
    "Knowledge graph databases for AI applications",
    "Advanced supply chain optimization algorithms",
    "Cross-platform mobile application development",
    "Deep learning neural network architectures",
    "Advanced optical systems and components",
    "Photonics applications in communications",
    "Quantum sensing technologies",
    "Robotics and automation solutions",
    "Solar energy system optimization",
    "Thermal management in electronics",
    "Advanced ultrasound imaging technology",
    "Virtual reality training simulations",
    "Wireless communication protocols",
    "Xenon-based technological applications",
    "Agricultural yield prediction models",
    "Zero-waste technology solutions",
]


def random_date(start_year: int = 1983, end_year: int = 2026) -> str:
    """Generate random date string."""
    year = random.randint(start_year, end_year)
    month = random.randint(1, 12)
    day = random.randint(1, 28)  # Avoid month/day issues
    return f"{year:04d}-{month:02d}-{day:02d}"


def random_phone() -> str:
    """Generate random phone number."""
    area = random.randint(200, 999)
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)
    return f"{area}-{exchange}-{number}"


def random_email(name: str, company: str) -> str:
    """Generate random email."""
    domain = company.lower().replace(" ", "").replace(",", "") + ".example.com"
    return f"{name.lower().replace(' ', '.')}@{domain}"


def random_uei() -> str:
    """Generate random UEI (12 alphanumeric)."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(12))


def random_duns() -> str:
    """Generate random DUNS (9 digits)."""
    return "".join(str(random.randint(0, 9)) for _ in range(9))


def generate_record(idx: int) -> dict:
    """Generate a single SBIR record."""
    company = random.choice(COMPANY_NAMES)
    contact_name = f"Contact {idx}"
    pi_name = f"Dr. PI {idx}"
    ri_name = f"Research Inst {idx}" if random.random() < 0.3 else ""

    # Award year
    award_year = random.randint(1983, 2025)

    # Dates
    award_date = random_date(award_year, award_year)
    end_year = award_year + random.randint(1, 3)
    end_date = random_date(end_year, end_year)

    # Amount
    base_amount = random.randint(50000, 2000000)
    if random.random() < 0.1:  # Edge case: high amount
        base_amount = random.randint(8000000, 10000000)

    # Phase duration
    if random.choice(["Phase I", "Phase II", "Phase III"]) == "Phase I":
        pass
    elif random.choice(["Phase I", "Phase II", "Phase III"]) == "Phase II":
        pass
    else:
        pass

    # Edge cases
    has_missing_uei = random.random() < 0.2
    has_invalid_phone = random.random() < 0.1

    return {
        "Company": company,
        "Address1": f"{random.randint(100, 999)} {random.choice(['Main St', 'Oak Ave', 'Pine Rd', 'Elm St'])}",
        "Address2": f"Suite {random.randint(100, 500)}" if random.random() < 0.5 else "",
        "City": random.choice(CITIES),
        "State": random.choice(STATES),
        "Zip": f"{random.randint(10000, 99999)}",
        "Company Website": f"https://{company.lower().replace(' ', '').replace(',', '')}.example.com",
        "Number of Employees": random.randint(1, 1000) if random.random() < 0.8 else "",
        "Award Title": random.choice(TITLES),
        "Abstract": random.choice(ABSTRACTS),
        "Agency": random.choice(AGENCIES),
        "Branch": random.choice(BRANCHES),
        "Phase": random.choice(["Phase I", "Phase II", "Phase III"]),
        "Program": random.choice(["SBIR", "STTR"]),
        "Topic Code": random.choice(TOPICS),
        "Award Amount": f"{base_amount:.2f}",
        "Award Year": award_year,
        "Proposal Award Date": award_date,
        "Contract End Date": end_date,
        "Solicitation Close Date": random_date(award_year - 1, award_year - 1)
        if award_year > 1983
        else "",
        "Proposal Receipt Date": random_date(award_year - 1, award_year - 1)
        if award_year > 1983
        else "",
        "Date of Notification": award_date,
        "Agency Tracking Number": f"ATN-{idx:04d}",
        "Contract": f"C-{award_year}-{idx:04d}",
        "Solicitation Number": f"SOL-{award_year}-{random.randint(1, 20):02d}",
        "Solicitation Year": award_year - 1 if award_year > 1983 else "",
        "UEI": "" if has_missing_uei else random_uei(),
        "Duns": random_duns(),
        "HUBZone Owned": random.choice(["Y", "N", ""]),
        "Socially and Economically Disadvantaged": random.choice(["Y", "N", ""]),
        "Woman Owned": random.choice(["Y", "N", ""]),
        "Contact Name": contact_name,
        "Contact Title": random.choice(["CEO", "CTO", "Founder", "President", "VP Engineering"]),
        "Contact Phone": "invalid-phone" if has_invalid_phone else random_phone(),
        "Contact Email": random_email(contact_name, company),
        "PI Name": pi_name,
        "PI Title": "Principal Investigator",
        "PI Phone": random_phone(),
        "PI Email": random_email(pi_name, company),
        "RI Name": ri_name,
        "RI POC Name": f"POC {idx}" if ri_name else "",
        "RI POC Phone": random_phone() if ri_name else "",
    }


def main():
    """Generate sample CSV."""
    random.seed(42)  # For reproducible results

    with open("tests/fixtures/sbir_sample.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()

        for i in range(100):
            record = generate_record(i + 1)
            writer.writerow(record)

    print("Generated 100 sample SBIR records in tests/fixtures/sbir_sample.csv")


if __name__ == "__main__":
    main()
