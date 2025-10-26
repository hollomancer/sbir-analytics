## File: annual.dta

- Sample rows analyzed: 100
- Candidate key columns: ['year', 'total_app', 'nber19_inforce', 'nber51_inforce', 'nber52_inforce', 'nber53_inforce', 'nber55_inforce', 'nber59_inforce', 'nber61_inforce', 'nber63_inforce', 'nber65_inforce', 'nber66_inforce', 'nber69_inforce', 'nber1_inforce', 'nber5_inforce', 'nber6_inforce', 'total_inforce', 'nber19_inforce_max', 'nber51_inforce_max', 'nber52_inforce_max', 'nber53_inforce_max', 'nber55_inforce_max', 'nber59_inforce_max', 'nber61_inforce_max', 'nber63_inforce_max', 'nber65_inforce_max', 'nber66_inforce_max', 'nber69_inforce_max', 'nber1_inforce_max', 'nber5_inforce_max', 'nber6_inforce_max', 'total_inforce_max', 'nber5_iss', 'total_iss', 'nber64_inforce', 'nber3_inforce', 'nber64_inforce_max', 'nber3_inforce_max', 'nber19_iss', 'nber65_iss', 'nber6_iss', 'nber11_inforce', 'nber32_inforce', 'nber43_inforce', 'nber67_inforce', 'nber4_inforce', 'nber11_inforce_max', 'nber32_inforce_max', 'nber43_inforce_max', 'nber67_inforce_max', 'nber4_inforce_max', 'nber51_iss', 'nber55_iss']
- Top columns (summary):

  - **year** (int16): nonnull_fraction=1.0 unique=100
  - **total_app** (float32): nonnull_fraction=1.0 unique=100
  - **nber11_inforce** (int16): nonnull_fraction=1.0 unique=98
  - **nber12_inforce** (int16): nonnull_fraction=1.0 unique=97
  - **nber13_inforce** (int16): nonnull_fraction=1.0 unique=94
  - **nber14_inforce** (float32): nonnull_fraction=1.0 unique=93
  - **nber15_inforce** (float32): nonnull_fraction=1.0 unique=89
  - **nber19_inforce** (float32): nonnull_fraction=1.0 unique=100
  - **nber21_inforce** (float32): nonnull_fraction=1.0 unique=93
  - **nber22_inforce** (float32): nonnull_fraction=1.0 unique=92


## File: assignee.dta

- Sample rows analyzed: 100
- Candidate key columns: ['rf_id']
- Common USPTO-like fields present: ['rf_id']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=100
  - **ee_name** (object): nonnull_fraction=1.0 unique=93
  - **ee_address_1** (object): nonnull_fraction=1.0 unique=54
  - **ee_address_2** (object): nonnull_fraction=1.0 unique=17
  - **ee_city** (object): nonnull_fraction=1.0 unique=60
  - **ee_state** (object): nonnull_fraction=1.0 unique=14
  - **ee_postcode** (object): nonnull_fraction=1.0 unique=25
  - **ee_country** (object): nonnull_fraction=1.0 unique=15


## File: assignment_conveyance.dta

- Sample rows analyzed: 100
- Candidate key columns: ['rf_id']
- Common USPTO-like fields present: ['rf_id']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=100
  - **convey_ty** (object): nonnull_fraction=1.0 unique=3
  - **employer_assign** (int8): nonnull_fraction=1.0 unique=2


## File: documentid_admin.dta

- Sample rows analyzed: 100
- Candidate key columns: ['grant_doc_num']
- Common USPTO-like fields present: ['rf_id', 'grant_doc_num']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=96
  - **appno_doc_num** (object): nonnull_fraction=1.0 unique=1
  - **grant_doc_num** (object): nonnull_fraction=1.0 unique=100
  - **admin_appl_id_for_grant** (object): nonnull_fraction=1.0 unique=4
  - **admin_pat_no_for_appno** (object): nonnull_fraction=1.0 unique=1
  - **error** (object): nonnull_fraction=1.0 unique=1


## File: annual.dta

- Sample rows analyzed: 100
- Candidate key columns: ['year', 'total_app', 'nber19_inforce', 'nber51_inforce', 'nber52_inforce', 'nber53_inforce', 'nber55_inforce', 'nber59_inforce', 'nber61_inforce', 'nber63_inforce', 'nber65_inforce', 'nber66_inforce', 'nber69_inforce', 'nber1_inforce', 'nber5_inforce', 'nber6_inforce', 'total_inforce', 'nber19_inforce_max', 'nber51_inforce_max', 'nber52_inforce_max', 'nber53_inforce_max', 'nber55_inforce_max', 'nber59_inforce_max', 'nber61_inforce_max', 'nber63_inforce_max', 'nber65_inforce_max', 'nber66_inforce_max', 'nber69_inforce_max', 'nber1_inforce_max', 'nber5_inforce_max', 'nber6_inforce_max', 'total_inforce_max', 'nber5_iss', 'total_iss', 'nber64_inforce', 'nber3_inforce', 'nber64_inforce_max', 'nber3_inforce_max', 'nber19_iss', 'nber65_iss', 'nber6_iss', 'nber11_inforce', 'nber32_inforce', 'nber43_inforce', 'nber67_inforce', 'nber4_inforce', 'nber11_inforce_max', 'nber32_inforce_max', 'nber43_inforce_max', 'nber67_inforce_max', 'nber4_inforce_max', 'nber51_iss', 'nber55_iss']
- Top columns (summary):

  - **year** (int16): nonnull_fraction=1.0 unique=100
  - **total_app** (float32): nonnull_fraction=1.0 unique=100
  - **nber11_inforce** (int16): nonnull_fraction=1.0 unique=98
  - **nber12_inforce** (int16): nonnull_fraction=1.0 unique=97
  - **nber13_inforce** (int16): nonnull_fraction=1.0 unique=94
  - **nber14_inforce** (float32): nonnull_fraction=1.0 unique=93
  - **nber15_inforce** (float32): nonnull_fraction=1.0 unique=89
  - **nber19_inforce** (float32): nonnull_fraction=1.0 unique=100
  - **nber21_inforce** (float32): nonnull_fraction=1.0 unique=93
  - **nber22_inforce** (float32): nonnull_fraction=1.0 unique=92


## File: assignee.dta

- Sample rows analyzed: 100
- Candidate key columns: ['rf_id']
- Common USPTO-like fields present: ['rf_id']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=100
  - **ee_name** (object): nonnull_fraction=1.0 unique=93
  - **ee_address_1** (object): nonnull_fraction=1.0 unique=54
  - **ee_address_2** (object): nonnull_fraction=1.0 unique=17
  - **ee_city** (object): nonnull_fraction=1.0 unique=60
  - **ee_state** (object): nonnull_fraction=1.0 unique=14
  - **ee_postcode** (object): nonnull_fraction=1.0 unique=25
  - **ee_country** (object): nonnull_fraction=1.0 unique=15


## File: assignment.dta

- Sample rows analyzed: 100
- Candidate key columns: ['rf_id', 'frame_no']
- Common USPTO-like fields present: ['rf_id', 'file_id']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=100
  - **file_id** (int8): nonnull_fraction=1.0 unique=1
  - **cname** (object): nonnull_fraction=1.0 unique=83
  - **caddress_1** (object): nonnull_fraction=1.0 unique=86
  - **caddress_2** (object): nonnull_fraction=1.0 unique=78
  - **caddress_3** (object): nonnull_fraction=1.0 unique=33
  - **caddress_4** (object): nonnull_fraction=1.0 unique=5
  - **reel_no** (int32): nonnull_fraction=1.0 unique=10
  - **frame_no** (int16): nonnull_fraction=1.0 unique=99
  - **convey_text** (object): nonnull_fraction=1.0 unique=5


## File: assignment_conveyance.dta

- Sample rows analyzed: 100
- Candidate key columns: ['rf_id']
- Common USPTO-like fields present: ['rf_id']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=100
  - **convey_ty** (object): nonnull_fraction=1.0 unique=3
  - **employer_assign** (int8): nonnull_fraction=1.0 unique=2


## File: assignor.dta

- Sample rows analyzed: 100
- Candidate key columns: ['or_name', 'rf_id', 'exec_dt']
- Common USPTO-like fields present: ['rf_id']
- Top columns (summary):

  - **rf_id** (int32): nonnull_fraction=1.0 unique=57
  - **or_name** (object): nonnull_fraction=1.0 unique=97
  - **exec_dt** (datetime64[ns]): nonnull_fraction=0.96 unique=55
  - **ack_dt** (datetime64[ns]): nonnull_fraction=0.0 unique=0


