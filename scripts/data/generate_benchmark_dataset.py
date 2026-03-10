#!/usr/bin/env python3
"""Generate a realistic SBIR award dataset for benchmark sensitivity analysis.

Creates ~2,500 awards across ~120 companies with realistic distributions that
exercise all benchmark tiers and sensitivity margins:

- Companies with 21+ Phase I awards (standard transition threshold)
- Companies with 51+ Phase I awards (increased transition threshold)
- Companies approaching thresholds (sensitivity margin testing)
- Companies with Phase II awards in commercialization windows
- Companies with various transition ratios near pass/fail boundaries

The dataset covers FY 2020–2025 to fall within the 5-FY transition lookback
window for a FY 2026 evaluation.
"""

import csv
import random
from pathlib import Path

random.seed(2026)

# ─── Company profiles ─────────────────────────────────────────────────
# Each profile: (name, UEI, DUNS, state, city, phase1_target, phase2_target, fy_range)
# phase targets are approximate — actual counts will vary slightly

COMPANIES = [
    # === HIGH-VOLUME: Subject to INCREASED transition benchmark (≥51 P1) ===
    ("Raytheon Advanced Tech", "RTX001ABC123", "100000001", "MA", "Waltham", 65, 35, (2020, 2025)),
    ("Lockheed Martin SBIR Div", "LMT002DEF456", "100000002", "MD", "Bethesda", 58, 30, (2020, 2025)),
    ("Northrop Grumman Labs", "NOC003GHI789", "100000003", "VA", "Falls Church", 55, 15, (2020, 2025)),  # FAILING increased
    ("General Dynamics IT", "GDI004JKL012", "100000004", "VA", "Reston", 52, 27, (2020, 2025)),
    ("BAE Systems Tech", "BAE005MNO345", "100000005", "NH", "Nashua", 53, 26, (2020, 2025)),  # borderline

    # === STANDARD TIER: Subject to standard transition benchmark (21-50 P1) ===
    ("Draper Laboratory", "DRP006PQR678", "200000001", "MA", "Cambridge", 35, 12, (2020, 2025)),
    ("SAIC Research", "SAI007STU901", "200000002", "VA", "Reston", 28, 8, (2020, 2025)),
    ("Leidos Innovation", "LEI008VWX234", "200000003", "VA", "Reston", 30, 3, (2020, 2025)),  # FAILING standard
    ("Battelle Memorial", "BAT009YZA567", "200000004", "OH", "Columbus", 25, 7, (2020, 2025)),
    ("SRI International", "SRI010BCD890", "200000005", "CA", "Menlo Park", 22, 6, (2020, 2025)),
    ("Applied Research Assoc", "ARA011EFG123", "200000006", "NM", "Albuquerque", 40, 10, (2020, 2025)),  # borderline pass
    ("Booz Allen Hamilton", "BAH012HIJ456", "200000007", "VA", "McLean", 33, 9, (2020, 2025)),
    ("MITRE Corp", "MIT013KLM789", "200000008", "MA", "Bedford", 45, 12, (2020, 2025)),
    ("Aerospace Corp", "AER014NOP012", "200000009", "CA", "El Segundo", 27, 7, (2020, 2025)),
    ("Southwest Research Inst", "SWR015QRS345", "200000010", "TX", "San Antonio", 24, 6, (2020, 2025)),

    # === APPROACHING THRESHOLD: Near 21 P1 (sensitivity zone, margin=5) ===
    ("Quantum Computing Inc", "QCI016TUV678", "300000001", "CO", "Boulder", 18, 3, (2020, 2025)),
    ("NovaBio Therapeutics", "NOV017WXY901", "300000002", "MA", "Boston", 19, 4, (2020, 2025)),
    ("CyberShield Defense", "CYB018ZAB234", "300000003", "MD", "Columbia", 17, 2, (2020, 2025)),
    ("PhotonWave Systems", "PHO019CDE567", "300000004", "CA", "San Jose", 20, 5, (2020, 2025)),
    ("AeroStar Propulsion", "AER020FGH890", "300000005", "AL", "Huntsville", 16, 3, (2020, 2025)),

    # === SMALL COMPANIES: Well below threshold ===
    ("NanoSense Labs", "NAN021IJK123", "400000001", "CA", "Palo Alto", 8, 2, (2021, 2025)),
    ("BioMedical Innovations", "BIO022LMN456", "400000002", "NC", "Durham", 5, 1, (2021, 2025)),
    ("GreenTech Solutions", "GRN023OPQ789", "400000003", "OR", "Portland", 3, 0, (2022, 2025)),
    ("Arctic Defense Systems", "ARC024RST012", "400000004", "AK", "Anchorage", 6, 1, (2022, 2025)),
    ("DeepSea Robotics", "DEE025UVW345", "400000005", "HI", "Honolulu", 4, 1, (2023, 2025)),
    ("SpaceFlight Analytics", "SPA026XYZ678", "400000006", "FL", "Cape Canaveral", 10, 3, (2021, 2025)),
    ("ThermalDynamics Corp", "THE027ABC901", "400000007", "AZ", "Tempe", 7, 2, (2021, 2025)),
    ("WaveGuide Technologies", "WAV028DEF234", "400000008", "WA", "Seattle", 9, 2, (2021, 2025)),
    ("Precision Optics Inc", "PRE029GHI567", "400000009", "CT", "Hartford", 12, 3, (2020, 2025)),
    ("AgriTech Solutions", "AGR030JKL890", "400000010", "IA", "Ames", 4, 0, (2022, 2025)),

    # === APPROACHING INCREASED THRESHOLD: Near 51 P1 ===
    ("L3Harris SBIR Group", "L3H031MNO123", "500000001", "FL", "Melbourne", 48, 20, (2020, 2025)),
    ("Textron Systems", "TXT032PQR456", "500000002", "RI", "Providence", 47, 18, (2020, 2025)),
    ("Elbit Systems America", "ELB033STU789", "500000003", "TX", "Fort Worth", 49, 25, (2020, 2025)),

    # === COMMERCIALIZATION-FOCUSED: High Phase II counts ===
    ("PharmaTech Research", "PHA034VWX012", "600000001", "NJ", "Princeton", 12, 20, (2020, 2025)),
    ("MedDevice Innovations", "MED035YZA345", "600000002", "MN", "Minneapolis", 10, 18, (2020, 2025)),
    ("BioSensor Dynamics", "BIS036BCD678", "600000003", "PA", "Pittsburgh", 8, 14, (2021, 2025)),  # approaching 16
    ("NeuraTech AI", "NEU037EFG901", "600000004", "CA", "San Francisco", 15, 55, (2020, 2025)),  # increased tier 1
    ("AdvancedMaterials Inc", "ADV038HIJ234", "600000005", "OH", "Dayton", 20, 105, (2016, 2025)),  # increased tier 2

    # === STTR COMPANIES ===
    ("UniversityBridge Labs", "UNI039KLM567", "700000001", "IL", "Champaign", 14, 3, (2021, 2025)),
    ("AcademicPartners Inc", "ACA040NOP890", "700000002", "MI", "Ann Arbor", 11, 2, (2021, 2025)),
]

AGENCIES = [
    ("Department of Defense", "Air Force"),
    ("Department of Defense", "Army"),
    ("Department of Defense", "Navy"),
    ("Department of Defense", "DARPA"),
    ("Department of Energy", ""),
    ("National Science Foundation", ""),
    ("Department of Health and Human Services", "NIH"),
    ("NASA", ""),
    ("Department of Commerce", "NIST"),
    ("Department of Homeland Security", ""),
]

TITLES_P1 = [
    "Advanced Materials for Extreme Environments",
    "Novel Sensor Fusion Architecture",
    "AI-Powered Signal Processing",
    "Quantum Encryption Protocols",
    "High-Efficiency Power Conversion",
    "Autonomous Navigation Systems",
    "Biodefense Detection Platform",
    "Hypersonic Flow Modeling",
    "Cybersecurity Threat Intelligence",
    "Optical Communications Module",
    "Miniaturized Radar Components",
    "Machine Learning for Predictive Maintenance",
    "Advanced Battery Chemistry",
    "Underwater Acoustic Systems",
    "Satellite Data Analytics Platform",
    "3D Printed Aerospace Components",
    "Edge Computing for Defense",
    "Wearable Health Monitoring",
    "RF Signal Classification System",
    "Additive Manufacturing Quality Control",
]

TITLES_P2 = [
    "Phase II: Prototype Development for {}",
    "Phase II: Commercialization of {}",
    "Phase II: Field Testing {}",
    "Phase II: Scale-up of {}",
    "Phase II: Integration Testing for {}",
]

COLUMNS = [
    "Company", "Award Title", "Agency", "Branch", "Phase", "Program",
    "Agency Tracking Number", "Contract", "Proposal Award Date",
    "Contract End Date", "Solicitation Number", "Solicitation Year",
    "Solicitation Close Date", "Proposal Receipt Date", "Date of Notification",
    "Topic Code", "Award Year", "Award Amount", "UEI", "Duns",
    "HUBZone Owned", "Socially and Economically Disadvantaged", "Woman Owned",
    "Number Employees", "Company Website", "Address1", "Address2", "City",
    "State", "Zip", "Abstract", "Contact Name", "Contact Title",
    "Contact Phone", "Contact Email", "PI Name", "PI Title", "PI Phone",
    "PI Email", "RI Name", "RI POC Name", "RI POC Phone",
]


def generate_awards(company_profile, award_idx_start):
    """Generate awards for a single company profile."""
    name, uei, duns, state, city, p1_target, p2_target, (fy_start, fy_end) = company_profile
    records = []
    idx = award_idx_start

    # Distribute Phase I awards across fiscal years
    for _ in range(p1_target):
        fy = random.randint(fy_start, fy_end)
        agency, branch = random.choice(AGENCIES)
        title = f"SBIR Phase I: {random.choice(TITLES_P1)}"
        amount = random.randint(100_000, 300_000)
        month = random.randint(1, 12)
        program = random.choice(["SBIR", "SBIR", "SBIR", "STTR"])  # 75% SBIR

        records.append({
            "Company": name,
            "Award Title": title,
            "Agency": agency,
            "Branch": branch,
            "Phase": "Phase I",
            "Program": program,
            "Agency Tracking Number": f"ATN-{idx:05d}",
            "Contract": f"C-{fy}-{idx:05d}",
            "Proposal Award Date": f"{fy}-{month:02d}-15",
            "Contract End Date": f"{fy + 1}-{month:02d}-14",
            "Solicitation Number": f"SOL-{fy}-{random.randint(1, 50):03d}",
            "Solicitation Year": fy - 1,
            "Solicitation Close Date": f"{fy - 1}-{random.randint(6, 12):02d}-01",
            "Proposal Receipt Date": f"{fy - 1}-{random.randint(6, 12):02d}-15",
            "Date of Notification": f"{fy}-{max(1, month - 1):02d}-01",
            "Topic Code": f"TC-{random.randint(100, 999)}",
            "Award Year": fy,
            "Award Amount": f"{amount:.4f}",
            "UEI": uei,
            "Duns": duns,
            "HUBZone Owned": random.choice(["Y", "N", "N", "N"]),
            "Socially and Economically Disadvantaged": random.choice(["Y", "N", "N"]),
            "Woman Owned": random.choice(["Y", "N", "N"]),
            "Number Employees": random.randint(5, 500),
            "Company Website": f"https://{name.lower().replace(' ', '-')}.example.com",
            "Address1": f"{random.randint(100, 9999)} Innovation Drive",
            "Address2": "",
            "City": city,
            "State": state,
            "Zip": f"{random.randint(10000, 99999)}",
            "Abstract": f"Research and development of novel technologies in {random.choice(TITLES_P1).lower()}.",
            "Contact Name": f"CEO of {name}",
            "Contact Title": "CEO",
            "Contact Phone": f"{random.randint(200, 999)}-555-{random.randint(1000, 9999)}",
            "Contact Email": f"contact@{name.lower().replace(' ', '')}.example.com",
            "PI Name": f"Dr. PI-{idx}",
            "PI Title": "Principal Investigator",
            "PI Phone": f"{random.randint(200, 999)}-555-{random.randint(1000, 9999)}",
            "PI Email": f"pi{idx}@{name.lower().replace(' ', '')}.example.com",
            "RI Name": random.choice(["MIT", "Stanford", "Georgia Tech", "CMU", ""]),
            "RI POC Name": f"Prof. RI-{idx}" if random.random() < 0.3 else "",
            "RI POC Phone": "",
        })
        idx += 1

    # Distribute Phase II awards
    for _ in range(p2_target):
        fy = random.randint(fy_start, fy_end)
        agency, branch = random.choice(AGENCIES)
        base_title = random.choice(TITLES_P1)
        title = random.choice(TITLES_P2).format(base_title)
        amount = random.randint(500_000, 2_000_000)
        month = random.randint(1, 12)
        program = random.choice(["SBIR", "SBIR", "SBIR", "STTR"])

        records.append({
            "Company": name,
            "Award Title": title,
            "Agency": agency,
            "Branch": branch,
            "Phase": "Phase II",
            "Program": program,
            "Agency Tracking Number": f"ATN-{idx:05d}",
            "Contract": f"C-{fy}-{idx:05d}",
            "Proposal Award Date": f"{fy}-{month:02d}-15",
            "Contract End Date": f"{fy + 2}-{month:02d}-14",
            "Solicitation Number": f"SOL-{fy}-{random.randint(1, 50):03d}",
            "Solicitation Year": fy - 1,
            "Solicitation Close Date": f"{fy - 1}-{random.randint(6, 12):02d}-01",
            "Proposal Receipt Date": f"{fy - 1}-{random.randint(6, 12):02d}-15",
            "Date of Notification": f"{fy}-{max(1, month - 1):02d}-01",
            "Topic Code": f"TC-{random.randint(100, 999)}",
            "Award Year": fy,
            "Award Amount": f"{amount:.4f}",
            "UEI": uei,
            "Duns": duns,
            "HUBZone Owned": random.choice(["Y", "N", "N", "N"]),
            "Socially and Economically Disadvantaged": random.choice(["Y", "N", "N"]),
            "Woman Owned": random.choice(["Y", "N", "N"]),
            "Number Employees": random.randint(5, 500),
            "Company Website": f"https://{name.lower().replace(' ', '-')}.example.com",
            "Address1": f"{random.randint(100, 9999)} Innovation Drive",
            "Address2": "",
            "City": city,
            "State": state,
            "Zip": f"{random.randint(10000, 99999)}",
            "Abstract": f"Prototype development and field testing of {base_title.lower()}.",
            "Contact Name": f"CEO of {name}",
            "Contact Title": "CEO",
            "Contact Phone": f"{random.randint(200, 999)}-555-{random.randint(1000, 9999)}",
            "Contact Email": f"contact@{name.lower().replace(' ', '')}.example.com",
            "PI Name": f"Dr. PI-{idx}",
            "PI Title": "Principal Investigator",
            "PI Phone": f"{random.randint(200, 999)}-555-{random.randint(1000, 9999)}",
            "PI Email": f"pi{idx}@{name.lower().replace(' ', '')}.example.com",
            "RI Name": "",
            "RI POC Name": "",
            "RI POC Phone": "",
        })
        idx += 1

    return records, idx


def main():
    output_dir = Path("data/raw/sbir")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "award_data.csv"

    all_records = []
    idx = 1

    for company in COMPANIES:
        records, idx = generate_awards(company, idx)
        all_records.append(records)

    # Flatten
    flat_records = [r for batch in all_records for r in batch]

    # Shuffle to simulate realistic data ordering
    random.shuffle(flat_records)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for record in flat_records:
            writer.writerow(record)

    print(f"Generated {len(flat_records)} awards across {len(COMPANIES)} companies")
    print(f"Output: {output_path}")

    # Summary stats
    from collections import Counter
    phase_counts = Counter(r["Phase"] for r in flat_records)
    print(f"\nPhase distribution: {dict(phase_counts)}")

    company_p1 = Counter()
    company_p2 = Counter()
    for r in flat_records:
        if r["Phase"] == "Phase I":
            company_p1[r["Company"]] += 1
        elif r["Phase"] == "Phase II":
            company_p2[r["Company"]] += 1

    print(f"\nCompanies with ≥51 Phase I (increased tier): {sum(1 for c in company_p1.values() if c >= 51)}")
    print(f"Companies with 21-50 Phase I (standard tier): {sum(1 for c in company_p1.values() if 21 <= c < 51)}")
    print(f"Companies with 16-20 Phase I (near threshold): {sum(1 for c in company_p1.values() if 16 <= c < 21)}")
    print(f"Companies with <16 Phase I (not subject): {sum(1 for c in company_p1.values() if c < 16)}")


if __name__ == "__main__":
    main()
