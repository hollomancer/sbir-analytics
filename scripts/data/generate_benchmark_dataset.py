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

# FY 2026 statutory windows:
#   Transition Phase I:    FY 2020–2024  (5yr lookback, excl 1 recent)
#   Transition Phase II:   FY 2021–2025  (5yr lookback, incl recent)
#   Commercialization:     FY 2014–2023  (10yr lookback, excl 2 recent)
#
# Column format:
#   (name, UEI, DUNS, state, city,
#    p1_target, p2_transition_target,  # Phase I & II in transition window (2020-2025)
#    p2_comm_target,                   # Phase II in commercialization window (2014-2023)
#    transition_fy_range,              # FY range for transition awards
#    comm_fy_range)                    # FY range for commercialization Phase II awards

COMPANIES = [
    # === HIGH-VOLUME: Subject to INCREASED transition benchmark (≥51 P1) ===
    # name, UEI, DUNS, state, city, p1, p2_trans, p2_comm, trans_fy, comm_fy
    ("Raytheon Advanced Tech", "RTX001ABC123", "100000001", "MA", "Waltham",
     65, 35, 30, (2020, 2025), (2014, 2023)),
    ("Lockheed Martin SBIR Div", "LMT002DEF456", "100000002", "MD", "Bethesda",
     58, 30, 25, (2020, 2025), (2014, 2023)),
    ("Northrop Grumman Labs", "NOC003GHI789", "100000003", "VA", "Falls Church",
     55, 15, 18, (2020, 2025), (2014, 2023)),  # FAILING increased
    ("General Dynamics IT", "GDI004JKL012", "100000004", "VA", "Reston",
     52, 27, 22, (2020, 2025), (2014, 2023)),
    ("BAE Systems Tech", "BAE005MNO345", "100000005", "NH", "Nashua",
     53, 26, 20, (2020, 2025), (2014, 2023)),  # borderline

    # === STANDARD TIER: Subject to standard transition benchmark (21-50 P1) ===
    ("Draper Laboratory", "DRP006PQR678", "200000001", "MA", "Cambridge",
     35, 12, 18, (2020, 2025), (2014, 2023)),
    ("SAIC Research", "SAI007STU901", "200000002", "VA", "Reston",
     28, 8, 14, (2020, 2025), (2014, 2023)),
    ("Leidos Innovation", "LEI008VWX234", "200000003", "VA", "Reston",
     30, 3, 10, (2020, 2025), (2016, 2023)),  # FAILING standard
    ("Battelle Memorial", "BAT009YZA567", "200000004", "OH", "Columbus",
     25, 7, 12, (2020, 2025), (2014, 2023)),
    ("SRI International", "SRI010BCD890", "200000005", "CA", "Menlo Park",
     22, 6, 10, (2020, 2025), (2015, 2023)),
    ("Applied Research Assoc", "ARA011EFG123", "200000006", "NM", "Albuquerque",
     40, 10, 16, (2020, 2025), (2014, 2023)),  # borderline pass
    ("Booz Allen Hamilton", "BAH012HIJ456", "200000007", "VA", "McLean",
     33, 9, 15, (2020, 2025), (2014, 2023)),
    ("MITRE Corp", "MIT013KLM789", "200000008", "MA", "Bedford",
     45, 12, 20, (2020, 2025), (2014, 2023)),
    ("Aerospace Corp", "AER014NOP012", "200000009", "CA", "El Segundo",
     27, 7, 12, (2020, 2025), (2014, 2023)),
    ("Southwest Research Inst", "SWR015QRS345", "200000010", "TX", "San Antonio",
     24, 6, 10, (2020, 2025), (2015, 2023)),

    # === APPROACHING THRESHOLD: Near 21 P1 (sensitivity zone, margin=5) ===
    ("Quantum Computing Inc", "QCI016TUV678", "300000001", "CO", "Boulder",
     18, 3, 5, (2020, 2025), (2018, 2023)),
    ("NovaBio Therapeutics", "NOV017WXY901", "300000002", "MA", "Boston",
     19, 4, 6, (2020, 2025), (2017, 2023)),
    ("CyberShield Defense", "CYB018ZAB234", "300000003", "MD", "Columbia",
     17, 2, 4, (2020, 2025), (2018, 2023)),
    ("PhotonWave Systems", "PHO019CDE567", "300000004", "CA", "San Jose",
     20, 5, 7, (2020, 2025), (2017, 2023)),
    ("AeroStar Propulsion", "AER020FGH890", "300000005", "AL", "Huntsville",
     16, 3, 5, (2020, 2025), (2018, 2023)),

    # === SMALL COMPANIES: Well below threshold ===
    ("NanoSense Labs", "NAN021IJK123", "400000001", "CA", "Palo Alto",
     8, 2, 3, (2021, 2025), (2019, 2023)),
    ("BioMedical Innovations", "BIO022LMN456", "400000002", "NC", "Durham",
     5, 1, 2, (2021, 2025), (2020, 2023)),
    ("GreenTech Solutions", "GRN023OPQ789", "400000003", "OR", "Portland",
     3, 0, 0, (2022, 2025), None),
    ("Arctic Defense Systems", "ARC024RST012", "400000004", "AK", "Anchorage",
     6, 1, 2, (2022, 2025), (2020, 2023)),
    ("DeepSea Robotics", "DEE025UVW345", "400000005", "HI", "Honolulu",
     4, 1, 1, (2023, 2025), (2022, 2023)),
    ("SpaceFlight Analytics", "SPA026XYZ678", "400000006", "FL", "Cape Canaveral",
     10, 3, 5, (2021, 2025), (2018, 2023)),
    ("ThermalDynamics Corp", "THE027ABC901", "400000007", "AZ", "Tempe",
     7, 2, 3, (2021, 2025), (2019, 2023)),
    ("WaveGuide Technologies", "WAV028DEF234", "400000008", "WA", "Seattle",
     9, 2, 4, (2021, 2025), (2018, 2023)),
    ("Precision Optics Inc", "PRE029GHI567", "400000009", "CT", "Hartford",
     12, 3, 6, (2020, 2025), (2017, 2023)),
    ("AgriTech Solutions", "AGR030JKL890", "400000010", "IA", "Ames",
     4, 0, 0, (2022, 2025), None),

    # === APPROACHING INCREASED THRESHOLD: Near 51 P1 ===
    ("L3Harris SBIR Group", "L3H031MNO123", "500000001", "FL", "Melbourne",
     48, 20, 22, (2020, 2025), (2014, 2023)),
    ("Textron Systems", "TXT032PQR456", "500000002", "RI", "Providence",
     47, 18, 20, (2020, 2025), (2014, 2023)),
    ("Elbit Systems America", "ELB033STU789", "500000003", "TX", "Fort Worth",
     49, 25, 15, (2020, 2025), (2015, 2023)),

    # === COMMERCIALIZATION-FOCUSED: High Phase II in comm window (FY 2014-2023) ===
    ("PharmaTech Research", "PHA034VWX012", "600000001", "NJ", "Princeton",
     12, 8, 20, (2020, 2025), (2014, 2023)),     # standard comm tier
    ("MedDevice Innovations", "MED035YZA345", "600000002", "MN", "Minneapolis",
     10, 6, 18, (2020, 2025), (2014, 2023)),      # standard comm tier
    ("BioSensor Dynamics", "BIS036BCD678", "600000003", "PA", "Pittsburgh",
     8, 4, 14, (2018, 2025), (2016, 2023)),        # approaching 16
    ("NeuraTech AI", "NEU037EFG901", "600000004", "CA", "San Francisco",
     15, 10, 55, (2020, 2025), (2014, 2023)),      # increased tier 1
    ("AdvancedMaterials Inc", "ADV038HIJ234", "600000005", "OH", "Dayton",
     20, 15, 105, (2020, 2025), (2014, 2023)),     # increased tier 2

    # === STTR COMPANIES ===
    ("UniversityBridge Labs", "UNI039KLM567", "700000001", "IL", "Champaign",
     14, 3, 5, (2021, 2025), (2018, 2023)),
    ("AcademicPartners Inc", "ACA040NOP890", "700000002", "MI", "Ann Arbor",
     11, 2, 3, (2021, 2025), (2019, 2023)),
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


def _make_record(name, uei, duns, state, city, phase, fy, idx):
    """Generate a single award record."""
    agency, branch = random.choice(AGENCIES)
    month = random.randint(1, 12)
    program = random.choice(["SBIR", "SBIR", "SBIR", "STTR"])

    if phase == "Phase I":
        title = f"SBIR Phase I: {random.choice(TITLES_P1)}"
        amount = random.randint(100_000, 300_000)
        end_offset = 1
    else:
        base_title = random.choice(TITLES_P1)
        title = random.choice(TITLES_P2).format(base_title)
        amount = random.randint(500_000, 2_000_000)
        end_offset = 2

    return {
        "Company": name,
        "Award Title": title,
        "Agency": agency,
        "Branch": branch,
        "Phase": phase,
        "Program": program,
        "Agency Tracking Number": f"ATN-{idx:05d}",
        "Contract": f"C-{fy}-{idx:05d}",
        "Proposal Award Date": f"{fy}-{month:02d}-15",
        "Contract End Date": f"{fy + end_offset}-{month:02d}-14",
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
        "Abstract": f"{'Research into' if phase == 'Phase I' else 'Development of'} {random.choice(TITLES_P1).lower()}.",
        "Contact Name": f"CEO of {name}",
        "Contact Title": "CEO",
        "Contact Phone": f"{random.randint(200, 999)}-555-{random.randint(1000, 9999)}",
        "Contact Email": f"contact@{name.lower().replace(' ', '')}.example.com",
        "PI Name": f"Dr. PI-{idx}",
        "PI Title": "Principal Investigator",
        "PI Phone": f"{random.randint(200, 999)}-555-{random.randint(1000, 9999)}",
        "PI Email": f"pi{idx}@{name.lower().replace(' ', '')}.example.com",
        "RI Name": random.choice(["MIT", "Stanford", "Georgia Tech", "CMU", ""]) if phase == "Phase I" else "",
        "RI POC Name": f"Prof. RI-{idx}" if random.random() < 0.3 and phase == "Phase I" else "",
        "RI POC Phone": "",
    }


def generate_awards(company_profile, award_idx_start):
    """Generate awards for a single company profile.

    Produces three sets of awards to properly populate statutory windows:
    1. Phase I awards in the transition window (FY range from profile)
    2. Phase II awards in the transition window (same FY range)
    3. Phase II awards in the commercialization window (separate FY range,
       may reach back to FY 2014)
    """
    (name, uei, duns, state, city,
     p1_target, p2_trans_target, p2_comm_target,
     trans_fy_range, comm_fy_range) = company_profile

    records = []
    idx = award_idx_start
    trans_start, trans_end = trans_fy_range

    # 1. Phase I awards in transition window
    for _ in range(p1_target):
        fy = random.randint(trans_start, trans_end)
        records.append(_make_record(name, uei, duns, state, city, "Phase I", fy, idx))
        idx += 1

    # 2. Phase II awards in transition window (recent years)
    for _ in range(p2_trans_target):
        fy = random.randint(trans_start, trans_end)
        records.append(_make_record(name, uei, duns, state, city, "Phase II", fy, idx))
        idx += 1

    # 3. Phase II awards in commercialization window (may go back to FY 2014)
    #    Only add awards that are NOT already in the transition window range
    #    to avoid double-counting. Awards in the overlap are already covered above.
    if comm_fy_range is not None:
        comm_start, comm_end = comm_fy_range
        # How many of the p2_comm_target fall in years before the transition window?
        # Distribute proportionally, with remaining in the overlap years
        pre_transition_years = list(range(comm_start, min(comm_end + 1, trans_start)))
        overlap_years = list(range(max(comm_start, trans_start), min(comm_end, trans_end) + 1))

        if pre_transition_years:
            # Most commercialization Phase II awards should be in earlier years
            # (they've had time to commercialize)
            pre_count = max(1, p2_comm_target - p2_trans_target) if p2_comm_target > p2_trans_target else 0
            for _ in range(pre_count):
                fy = random.choice(pre_transition_years)
                records.append(_make_record(name, uei, duns, state, city, "Phase II", fy, idx))
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
