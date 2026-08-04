# Massachusetts Physical Unmanned-Systems SBIR/STTR Readout

- **Data source:** SBIR.gov bulk `award_data.csv` local snapshot
- **Source timestamp:** 2026-04-01T00:00:06.904233+00:00
- **Source SHA-256:** `73d646fc6883ed93b36d19518b0d9442a9ebae94c5b49ad5a7fcd6d3c2b872dd`
- **Award years represented:** 1992–2026
- **Geography:** Award record lists Massachusetts as the awardee state

## Result

| Measure | Conservative reviewed result |
|---|---:|
| Massachusetts awardees | **76** |
| Relevant awards | **238** |
| Awarded dollars | **$109,526,154.89** |

This report includes both **SBIR and STTR** and physical unmanned systems in
the **aerial, ground, surface, and undersea** domains. It includes complete
platforms, components, payloads, power systems, materials, and manufacturing
processes.

The deterministic candidate pass returned 334 award-grain records totaling
$181,483,765.28 across 100 firm identities. Award-level review removed 96
records totaling $71,957,610.39 because the funded work was software-only,
service-led, merely used an unmanned platform, named an unmanned system as one
generic market, targeted counter-UAS detection/defeat, or had an evident
title/abstract or awardee/product attribution problem.

## Technology groups

### Platform, vehicle, and systems developers (26)

- AIRBEAMS LLC
- ARMADA MARINE ROBOTICS INC
- ATLAS DEVICES, LLC
- BENTHOS, INC.
- BLUEFIN ROBOTICS CORP.
- BOSTON ENGINEERING CORPORATION
- Crgo Inc
- CROSS DOMAIN SYSTEMS INC
- Cyphy Works, Inc.
- DIVERSIFIED TECHNOLOGIES, INC.
- EOM OFFSHORE, LLC
- FOSTER-MILLER, INC.
- GREENSIGHT INC.
- IROBOT CORP.
- KaZaK Composites Incorporated
- Ocean Acoustical Services and Instrumentation Systems, Inc.
- RESOLUTE MARINE ENERGY, INC.
- Riptide Autonomous Solutions, LLC
- Robotics 88, Inc.
- ROGUE WOLF ADVANCED RESEARCH LLC
- SCIENTIFIC SYSTEMS COMPANY, INC.
- SICDRONE CORPORATION
- SPECIAL PROJECTS TEAM, LLC
- TRITON SYSTEMS, INC.
- VECNA TECHNOLOGIES, INC
- VISHWA ROBOTICS AND AUTOMATION LLC

### Components, payloads, materials, power, and supporting hardware (50)

- Advanced Mechanical Technology, Inc.
- AERODYNE RESEARCH INC
- AGILTRON, INC.
- Anro Engineering, Inc.
- APPLIED NANOFEMTO TECHNOLOGIES LLC
- Atrex Energy, Inc.
- BODKIN DESIGN & ENGINEERING LLC
- BROOKE OCEAN TECHNOLOGY USA, INC.
- BUSEK CO., INC.
- D-2 Inc
- Datasonics, Inc.
- E-CIRCUIT MOTORS INC.
- FIBERSENSE TECHNOLOGY CORP.
- Flight Landata, Inc.
- FloDesign, Inc.
- GENCORES INC
- GINER INC
- GVD CORP
- Headwall Photonics, Inc.
- Hittite Microwave Corporation
- Infoscitex Corporation
- Intrinsix Corp.
- MAGIQ TECHNOLOGIES, INC.
- MASSA PRODUCTS CORPORATION
- Materials Systems Inc.
- MATRIXSPACE, INC
- MAYFLOWER COMMUNICATIONS COMPANY, INC.
- MC10 Inc.
- MESODYNE INC
- MIDE TECHNOLOGY CORP
- Nanolab, Inc
- NASCENT TECHNOLOGY CORP.
- NEXTDROID, INC
- NOTCH INC.
- NUCLEUS SCIENTIFIC INC
- Optra, Inc.
- PENDAR TECHNOLOGIES LLC
- PHOTRONIX
- PHYSICAL SCIENCES INC.
- PROSENSING INC.
- PROTONEX TECHNOLOGY CORP.
- RADIATION MONITORING DEVICES, INC.
- REMOTE SENSING SOLUTIONS, INC.
- Scientific Solutions, Inc.
- SI2 TECHNOLOGIES, INC
- SPECTRAL SCIENCES, INC
- SSG, Inc.
- VISIDYNE, INC.
- White River Technologies Inc
- ZULU PODS INC

## Representative non-aerial and STTR evidence

| Awardee | Massachusetts location | Funded physical work |
|---|---|---|
| ARMADA Marine Robotics | Falmouth | External payload deployment hardware for cylindrical UUVs |
| Bluefin Robotics | Cambridge | UUV/USV launch-and-recovery prototypes and pressure-tolerant UUV batteries |
| NextDroid | Boston | Propulsion units for mine-countermeasures UUVs |
| MC10 | Cambridge | STTR-funded conformal photovoltaic modules for UAVs |
| White River Technologies | Newton | UAV electric-field sensor payload and UUV magnetic-sensor module |
| Resolute Marine Energy | Boston | Wave-powered AUV docking and recharge station |
| Vecna Technologies | Burlington | ChemBioBEAR UGV and integrated sensing package |
| Advanced Mechanical Technology | Watertown | STTR-funded wave-energy hardware for USVs |
| Rogue Wolf Advanced Research | Cohasset | Mechanical adapters, payloads, and components for assembling sUAS |
| E-Circuit Motors | Newton | PCB-stator axial-flux propulsion motor for deep-operating UUVs |

## Method

1. Load all SBIR.gov award rows and preserve source-row provenance, address,
   UEI, DUNS, contract, and tracking identifiers.
2. Collapse revised editions using the repository's `sbir-source-v2` compound
   award key. Mutable title, abstract, amount, and end date are not identity
   fields. This reduced 219,500 source rows to 219,445 award-grain records.
3. Assign conservative firm keys over the full source before applying the
   Massachusetts filter: UEI first; unambiguous DUNS-to-UEI bridge second;
   exact normalized company plus state only when no identifier resolves.
4. Filter the selected award edition to state code `MA`, leaving 27,164
   Massachusetts award-grain records for classification.
5. Apply the versioned `unmanned_systems_manufacturing` physical-development
   profile. Non-aerial acronyms require nearby platform context so, for
   example, `USV` does not match “ultrasonic vocalizations.”
6. Review candidate titles and abstracts at award grain. Retain only work that
   designs, fabricates, prototypes, integrates, or tests a physical platform
   or platform-specific component.

The deterministic candidate stage can be rerun with:

```bash
python scripts/data/build_tech_census.py \
  --area unmanned_systems_manufacturing \
  --state MA \
  --awards /absolute/path/to/award_data.csv \
  --data-vintage 2026-04-01
```

The 238-award published figure is the conservative reviewed result, not the
unreviewed classifier total. The source snapshot contains known historical
title/abstract mismatches, so that distinction is material.

The original award-level review decisions were not retained as a
machine-readable ledger. This branch preserves the verified aggregate and
firm readout plus the reproducible 334-award candidate stage; a future audit
ledger is required to regenerate the 238-award reviewed figure from the raw
snapshot alone.

## Interpretation limits

- “Massachusetts” means the selected public award record carried a
  Massachusetts awardee address. It does not establish current headquarters,
  incorporation, or manufacturing-site location.
- The award text establishes funded physical development. It does not by
  itself prove present-day production capacity or continuing commercial
  operation.
- Materials Systems' two AUV acoustic-imaging awards have title evidence but
  `N/A` abstracts and should be treated as provisional.
- The local file timestamp is provenance, not proof of the SBIR.gov release
  date. Awards added or revised after this snapshot are absent.
