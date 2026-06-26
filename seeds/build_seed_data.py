"""1b.1 — Extraction script.

Embeds the reference build's 40-CAPA dataset (enterprise, sites, departments,
employees, taxonomy, capas, root causes, actions — transcribed verbatim from
`reference/backend/seeds/*.sql`) and applies the mapping/derivation rules
fixed during 1b planning to emit JSON under `seeds/data/` for the Postgres
mirror schema. Run once: `python seeds/build_seed_data.py`.

Excluded (no source data / no mirrored table): seed_assets.sql, action_taxonomy,
CAPA_ACTION_PLAN, CAPA_APPROVALS, CAPA_REVIEW_HISTORY, CAPA_REVIEW_TASKS,
CAPA_SUBCATEGORIES, CAPA_ESCALATION_LEVELS, CAPA_SLA_RULES, MSTR_HOLIDAY_CALENDAR.
"""

import json
from pathlib import Path

TENANT_ID = "TENANT_ACERTECH"
DATA_DIR = Path(__file__).parent / "data"

# =============================================================================
# Source data — transcribed verbatim from reference/backend/seeds/*.sql
# =============================================================================

ENTERPRISE = {
    "name": "AcerTech Industries",
    "industry": "Heavy Manufacturing & Chemical Processing",
    "contact_emp_id": 234,  # Anil Mehta, EHS Compliance Manager
}

# (site_id, name)
SITES_SRC = [
    (1, "Chennai Heavy Manufacturing Plant"),
    (2, "Mumbai Central Warehouse"),
    (3, "Hyderabad Chemical Processing Unit"),
    (4, "Pune Precision Manufacturing Plant"),
    (5, "Delhi Distribution Center"),
    (6, "Bengaluru Electronics Manufacturing Plant"),
    (7, "Ahmedabad Chemical Processing Unit"),
    (8, "Kolkata Heavy Manufacturing Plant"),
    (9, "Chennai North Construction Site"),
    (10, "Coimbatore Regional Distribution Center"),
    (11, "Mumbai Corporate Office"),
]

# (dept_id, site_id, name, description)
DEPARTMENTS_SRC = [
    (1, 1, "Production", "Manages fabrication and assembly operations; owns machine guarding, hot work, and production floor hazards."),
    (2, 1, "Maintenance", "Responsible for planned and corrective maintenance of all plant equipment; owns LOTO, working at heights, and electrical isolation hazards."),
    (3, 1, "EHS", "Oversees site-wide health, safety, and environmental compliance; leads incident investigation and CAPA management."),
    (4, 1, "Quality Control", "Manages product quality inspection and non-conformance reporting; owns NCR-triggered CAPA actions."),
    (5, 1, "Warehouse", "Handles inbound raw materials and outbound finished goods; owns forklift operations and racking inspection hazards."),
    (6, 1, "Engineering", "Responsible for process engineering, capital projects, and pressure system integrity; owns MOC and pressure vessel hazards."),
    (7, 1, "HR", "Manages workforce training, competency records, and HR compliance; supports EHS in training gap CAPAs."),
    (8, 2, "Operations", "Manages all inbound and outbound logistics, picking, packing, and dispatch; owns forklift-pedestrian conflict and manual handling hazards."),
    (9, 2, "Maintenance", "Responsible for forklift servicing, racking repairs, and facility maintenance; owns LOTO and working at heights hazards."),
    (10, 2, "EHS", "Leads site safety programme, fire safety, and emergency preparedness; manages CAPA actions for warehouse incidents."),
    (11, 2, "Dispatch", "Manages outbound shipment scheduling and loading dock operations; owns dock safety and vehicle interface hazards."),
    (12, 2, "Security", "Responsible for site access control and perimeter security; owns emergency evacuation and visitor management."),
    (13, 3, "Production", "Operates chemical blending, formulation, and packaging lines; owns vapour exposure, flammable liquid handling, and process safety hazards."),
    (14, 3, "Chemical Handling", "Responsible for receipt, storage, transfer, and disposal of raw chemicals and finished products; owns spill response and hazmat transport hazards."),
    (15, 3, "Maintenance", "Services process equipment, pipework, and instrumentation; owns hot work permits, confined space entry, and LOTO hazards."),
    (16, 3, "EHS", "Manages process safety management, COSHH assessments, and regulatory compliance for chemical operations."),
    (17, 3, "Quality", "Conducts batch quality testing and manages product specification compliance; raises NCRs for out-of-spec batches."),
    (18, 3, "Engineering", "Responsible for process design, instrumentation, and capital modifications; owns pressure relief and ventilation system design."),
    (19, 4, "Production", "Operates CNC machining, grinding, and finishing lines; owns machine guarding, cutting fluid exposure, and noise hazards."),
    (20, 4, "Maintenance", "Maintains all CNC and precision equipment; owns electrical isolation and mechanical failure prevention."),
    (21, 4, "EHS", "Leads health and safety compliance for precision manufacturing; manages hearing conservation and chemical hygiene programmes."),
    (22, 4, "Quality Control", "Manages dimensional and surface quality inspection; raises CAPAs for machining process deviations."),
    (23, 4, "Warehouse", "Handles parts receipt and finished goods dispatch; owns forklift and racking inspection hazards."),
    (24, 4, "Engineering", "Manages process engineering and tooling qualification; owns MOC and coolant system design hazards."),
    (25, 4, "HR", "Manages competency records and training compliance for precision manufacturing workforce."),
    (26, 5, "Operations", "Manages high-throughput inbound and outbound logistics; owns forklift-pedestrian hazards and shift fatigue risks."),
    (27, 5, "Maintenance", "Responsible for forklift fleet servicing and facility upkeep; owns LOTO and vehicle maintenance hazards."),
    (28, 5, "EHS", "Leads safety programme for logistics operations; manages fire safety and manual handling CAPA actions."),
    (29, 5, "Dispatch", "Manages outbound loading and carrier coordination; owns dock leveller and loading platform hazards."),
    (30, 5, "Security", "Controls site access and perimeter security; supports emergency evacuation planning."),
    (31, 6, "Production", "Operates PCB assembly, soldering, and electronics testing lines; owns solder fume, ESD, and ergonomic hazards."),
    (32, 6, "Maintenance", "Maintains production equipment and clean-room systems; owns electrical isolation and HVAC maintenance hazards."),
    (33, 6, "EHS", "Manages chemical hygiene, solder fume monitoring, and waste disposal compliance for electronics manufacturing."),
    (34, 6, "Quality Control", "Manages electronic component inspection and test failure analysis; raises CAPAs for systematic production defects."),
    (35, 6, "Warehouse", "Handles sensitive electronics components and ESD-controlled storage; owns packaging and handling hazards."),
    (36, 6, "Engineering", "Manages process engineering and equipment qualification for electronics assembly."),
    (37, 6, "HR", "Manages workforce ergonomics programme and occupational health monitoring for assembly workers."),
    (38, 7, "Production", "Operates bulk chemical transfer, blending, and storage operations; owns process safety, vapour cloud, and explosion hazards."),
    (39, 7, "Chemical Handling", "Manages receipt, storage, and transfer of acids, alkalis, and petrochemical intermediates; owns spill, fire, and HAZMAT hazards."),
    (40, 7, "Maintenance", "Services pressure vessels, pipework, and safety instrumentation; owns hot work, confined space, and pressure isolation hazards."),
    (41, 7, "EHS", "Manages PSM programme, HAZOP compliance, and regulatory reporting for bulk chemical operations."),
    (42, 7, "Quality", "Manages raw material and product batch quality testing; owns laboratory chemical exposure hazards."),
    (43, 7, "Engineering", "Responsible for pressure system design, PSV sizing, and process safety engineering; owns MOC and HAZOP hazards."),
    (44, 8, "Production", "Operates structural steel fabrication, welding, and heat treatment; owns hot work, heavy lifting, and weld fume hazards."),
    (45, 8, "Maintenance", "Maintains fabrication equipment, cranes, and pressure test rigs; owns LOTO, working at heights, and high-pressure system hazards."),
    (46, 8, "EHS", "Leads site safety programme for heavy fabrication; manages confined space entry, weld fume monitoring, and CAPA management."),
    (47, 8, "Quality Control", "Manages weld inspection, NDT, and pressure vessel code compliance; raises CAPAs for non-conforming welds."),
    (48, 8, "Warehouse", "Handles heavy steel stock, consumables, and finished vessel dispatch; owns crane and rigging hazards."),
    (49, 8, "Engineering", "Manages vessel design, pressure calculations, and code compliance; owns engineering change and pressure relief system hazards."),
    (50, 8, "HR", "Manages welding certifications, trade qualifications, and mandatory competency records for the heavy manufacturing workforce."),
    (51, 9, "Civil Works", "Manages foundation, structural, and civil construction activities; owns excavation, formwork collapse, and concrete hazards."),
    (52, 9, "Equipment Operations", "Operates cranes, excavators, and concrete equipment; owns mobile plant collision and overload hazards."),
    (53, 9, "EHS", "Manages construction site safety including working at heights, confined space, and subcontractor safety oversight."),
    (54, 9, "Subcontractor Management", "Manages all subcontractor approvals, inductions, and performance monitoring; owns subcontractor safety compliance hazards."),
    (55, 9, "Planning", "Manages project schedule, method statements, and engineering drawings; owns design change and temporary works hazards."),
    (56, 10, "Operations", "Manages receipt, put-away, picking, and dispatch for the southern regional warehouse; owns forklift and manual handling hazards."),
    (57, 10, "Maintenance", "Responsible for forklift servicing and racking integrity inspections; owns vehicle maintenance and fall-from-height hazards."),
    (58, 10, "EHS", "Leads safety programme and fire prevention for the Coimbatore facility; manages CAPA actions for minor incidents and near misses."),
    (59, 10, "Dispatch", "Manages outbound shipment documentation and loading dock operations; owns dock safety and driver interface hazards."),
    (60, 10, "Security", "Controls facility access and emergency response coordination for the Coimbatore site."),
    (61, 11, "EHS Compliance", "Corporate function managing group-wide EHS policy, audit programme, and regulatory compliance reporting."),
    (62, 11, "HR", "Group HR function managing workforce policies, training governance, and competency frameworks across all sites."),
    (63, 11, "Administration", "Manages office facilities, reception, and corporate building management; owns ergonomic, fire, and evacuation hazards."),
    (64, 11, "IT", "Manages IT infrastructure and systems including the EHS software platform; owns data security and business continuity risks."),
]

# (emp_id, dept_id, name, role, role_description, email)
EMPLOYEES_SRC = [
    (1, 1, "Arun Sharma", "Production Supervisor", "Supervises daily fabrication and assembly operations; ensures machine guarding compliance and hot work permit adherence.", "arun.sharma@acertech.in"),
    (2, 1, "Venkat Subramanian", "Production Lead", "Leads shift production team and conducts pre-shift toolbox talks on floor safety.", "venkat.subramanian@acertech.in"),
    (3, 1, "Mani Sundaram", "Machine Operator", "Operates CNC and fabrication machinery; responsible for pre-use equipment checks.", "mani.sundaram@acertech.in"),
    (4, 1, "Karthik Rajan", "Machine Operator", "Operates overhead crane and rigging equipment under Maintenance Supervisor oversight.", "karthik.rajan@acertech.in"),
    (5, 1, "Deepa Murugesan", "Quality Technician", "Performs inline quality checks during production; escalates non-conformances to Quality Control.", "deepa.murugesan@acertech.in"),
    (6, 2, "Rajesh Kumar", "Maintenance Supervisor", "Plans and oversees all planned and corrective maintenance; controls LOTO programme and permit-to-work system.", "rajesh.kumar@acertech.in"),
    (7, 2, "Suresh Babu", "Maintenance Technician", "Performs mechanical repairs and preventive maintenance tasks under Rajesh Kumar supervision.", "suresh.babu@acertech.in"),
    (8, 2, "Balaji Natarajan", "Maintenance Technician", "Specialises in hydraulic and pneumatic system maintenance; certified for high-pressure isolation.", "balaji.natarajan@acertech.in"),
    (9, 2, "Prakash Sundaresan", "Electrician", "Maintains electrical panels and motor control centres; authorised for electrical isolation under LOTO.", "prakash.sundaresan@acertech.in"),
    (10, 2, "Murali Krishnan", "Maintenance Technician", "Performs crane inspections, rigging checks, and overhead lifting equipment servicing.", "murali.krishnan@acertech.in"),
    (11, 3, "Priya Nair", "EHS Officer", "Manages day-to-day safety compliance, incident investigation, and CAPA tracking for the Chennai plant.", "priya.nair@acertech.in"),
    (12, 3, "Suresh Krishnan", "EHS Manager", "Leads the site EHS programme, regulatory liaison, and ISO 45001 management review.", "suresh.krishnan@acertech.in"),
    (13, 3, "Meena Rajendran", "Safety Inspector", "Conducts daily safety inspections, audits PPE compliance, and maintains inspection records.", "meena.rajendran@acertech.in"),
    (14, 3, "Ganesan Pillai", "EHS Coordinator", "Maintains EHS documentation, training records, and chemical inventory registers.", "ganesan.pillai@acertech.in"),
    (15, 4, "Lakshmi Iyer", "Quality Control Manager", "Manages product quality inspection programme and leads NCR investigation and CAPA generation.", "lakshmi.iyer@acertech.in"),
    (16, 4, "Srinivas Rao", "Quality Inspector", "Performs dimensional and visual inspection of fabricated components; raises non-conformance reports.", "srinivas.rao@acertech.in"),
    (17, 4, "Anand Seshadri", "Quality Inspector", "Specialises in weld inspection and NDT; CSWIP certified.", "anand.seshadri@acertech.in"),
    (18, 4, "Kavitha Venkat", "Quality Technician", "Maintains calibration records for inspection equipment and manages the measurement system.", "kavitha.venkat@acertech.in"),
    (19, 5, "Murugan Selvam", "Warehouse Manager", "Manages material receipt, storage, and dispatch; oversees forklift operations and racking safety.", "murugan.selvam@acertech.in"),
    (20, 5, "Ravi Chandran", "Forklift Operator", "Operates forklifts for internal material movements; conducts daily pre-use forklift inspections.", "ravi.chandran@acertech.in"),
    (21, 5, "Kumar Arumugam", "Forklift Operator", "Operates forklifts and assists with crane-assisted heavy lifts in the warehouse bay.", "kumar.arumugam@acertech.in"),
    (22, 5, "Selvi Durai", "Stores Assistant", "Manages parts receipt, issue documentation, and inventory accuracy in the materials store.", "selvi.durai@acertech.in"),
    (23, 6, "Venkat Menon", "Plant Engineer", "Responsible for pressure vessel integrity, MOC approvals, and capital project engineering at Chennai.", "venkat.menon@acertech.in"),
    (24, 6, "Harish Nambiar", "Process Engineer", "Manages process parameters, equipment performance, and engineering change control.", "harish.nambiar@acertech.in"),
    (25, 6, "Deepak Varma", "Instrumentation Engineer", "Maintains process instrumentation, safety interlocks, and control systems.", "deepak.varma@acertech.in"),
    (26, 6, "Sudha Krishnamurthy", "Design Engineer", "Produces engineering drawings and specifications for plant modifications.", "sudha.krishnamurthy@acertech.in"),
    (27, 7, "Rama Subramanian", "HR Manager", "Manages workforce training compliance and competency records for Chennai manufacturing staff.", "rama.subramanian@acertech.in"),
    (28, 7, "Parvathi Srinivasan", "HR Officer", "Maintains training matrices, induction records, and manages the LMS for site-based staff.", "parvathi.srinivasan@acertech.in"),
    (29, 7, "Dinesh Natesan", "Training Coordinator", "Coordinates external training bookings and manages trade certification renewals.", "dinesh.natesan@acertech.in"),
    (30, 8, "Sanjay Patel", "Operations Manager", "Manages all warehouse operations, forklift fleet, and logistics throughput at the Mumbai hub.", "sanjay.patel@acertech.in"),
    (31, 8, "Nitin Joshi", "Shift Supervisor", "Supervises picking, packing, and dispatch operations during assigned shifts; enforces safety rules.", "nitin.joshi@acertech.in"),
    (32, 8, "Ramesh Desai", "Forklift Operator", "Operates reach trucks and counterbalance forklifts for high-bay racking operations.", "ramesh.desai@acertech.in"),
    (33, 8, "Priti Shah", "Warehouse Associate", "Performs picking, packing, and inventory count tasks; trained in manual handling best practice.", "priti.shah@acertech.in"),
    (34, 9, "Mohan Singh", "Maintenance Supervisor", "Oversees forklift servicing schedule, racking inspection programme, and building maintenance at the Mumbai warehouse.", "mohan.singh@acertech.in"),
    (35, 9, "Sunil Yadav", "Maintenance Technician", "Services and repairs the forklift fleet; maintains service logs and defect records.", "sunil.yadav@acertech.in"),
    (36, 9, "Arun Mishra", "Electrician", "Maintains lighting, power distribution, and battery-charging infrastructure in the warehouse.", "arun.mishra@acertech.in"),
    (37, 9, "Geeta Tiwari", "Maintenance Technician", "Performs racking inspection, load sign replacement, and building fabric maintenance.", "geeta.tiwari@acertech.in"),
    (38, 10, "Kavya Reddy", "EHS Officer", "Manages safety compliance, incident reporting, and CAPA actions for the Mumbai warehouse.", "kavya.reddy@acertech.in"),
    (39, 10, "Ajay Verma", "Safety Inspector", "Conducts daily walkthrough inspections of racking, forklifts, and fire safety equipment.", "ajay.verma@acertech.in"),
    (40, 10, "Suma Kulkarni", "EHS Coordinator", "Maintains chemical register, fire drill records, and CAPA tracking for Mumbai warehouse.", "suma.kulkarni@acertech.in"),
    (41, 11, "Farhan Sheikh", "Dispatch Supervisor", "Manages outbound shipment scheduling and dock allocation; owns dock safety procedures.", "farhan.sheikh@acertech.in"),
    (42, 11, "Aisha Khan", "Dispatch Coordinator", "Coordinates carrier bookings and manages driver induction and dock rules briefings.", "aisha.khan@acertech.in"),
    (43, 11, "Vikram Deshpande", "Dock Operative", "Operates dock levellers and manages vehicle reversing safety at the loading bays.", "vikram.deshpande@acertech.in"),
    (44, 11, "Rima Mehta", "Dispatch Clerk", "Manages shipping documentation and maintains outbound delivery accuracy records.", "rima.mehta@acertech.in"),
    (45, 12, "Prakash Gupta", "Security Supervisor", "Manages access control, perimeter security, and emergency evacuation coordination at Mumbai warehouse.", "prakash.gupta@acertech.in"),
    (46, 12, "Rakesh Pandey", "Security Guard", "Controls visitor access, monitors CCTV, and enforces site safety rules at entry points.", "rakesh.pandey@acertech.in"),
    (47, 12, "Sunita Chauhan", "Security Guard", "Patrols the facility and assists with emergency muster point management during evacuations.", "sunita.chauhan@acertech.in"),
    (48, 13, "Vikram Rao", "Production Supervisor", "Oversees chemical blending, formulation, and packaging operations; enforces permit-to-work and PPE standards.", "vikram.rao@acertech.in"),
    (49, 13, "Satish Reddy", "Process Operator", "Operates blending reactors and packaging lines under close supervision; trained in spill response.", "satish.reddy@acertech.in"),
    (50, 13, "Lalitha Naidu", "Process Operator", "Manages chemical transfer and batching operations; trained in confined space rescue.", "lalitha.naidu@acertech.in"),
    (51, 13, "Ravi Prasad", "Production Lead", "Leads the night shift production team and conducts pre-shift chemical hazard briefings.", "ravi.prasad@acertech.in"),
    (52, 14, "Dinesh Verma", "Chemical Handling Supervisor", "Manages receipt, storage, and internal transfer of all hazardous chemicals; owns HAZMAT emergency response procedures.", "dinesh.verma@acertech.in"),
    (53, 14, "Pooja Agarwal", "Chemical Handler", "Operates chemical transfer pumps, drum decanting, and pipework connections; trained in Level B PPE.", "pooja.agarwal@acertech.in"),
    (54, 14, "Tarun Bhatia", "Chemical Handler", "Manages chemical storage area compliance and SDS register for all site chemicals.", "tarun.bhatia@acertech.in"),
    (55, 14, "Jyoti Kapoor", "Chemical Handler", "Responsible for hazardous waste segregation and disposal coordination with licensed contractors.", "jyoti.kapoor@acertech.in"),
    (56, 14, "Suresh Malhotra", "Chemical Handler", "Performs daily inspection of chemical storage areas and emergency shower/eyewash stations.", "suresh.malhotra@acertech.in"),
    (57, 15, "Ashok Iyer", "Maintenance Supervisor", "Manages all maintenance activities at the chemical processing site; owns hot work, confined space entry, and LOTO controls.", "ashok.iyer@acertech.in"),
    (58, 15, "Naveen Pillai", "Maintenance Technician", "Services chemical process pumps, valves, and pipework; certified for confined space entry.", "naveen.pillai@acertech.in"),
    (59, 15, "Vimal Sharma", "Instrument Technician", "Maintains safety instrumented systems, PSVs, and process alarms; calibrates gas detectors.", "vimal.sharma@acertech.in"),
    (60, 15, "Radha Krishnan", "Electrician", "Maintains electrical installations in hazardous areas (Zone 1/2); ATEX-certified.", "radha.krishnan@acertech.in"),
    (61, 16, "Anita Pillai", "EHS Officer", "Manages process safety programme, COSHH assessments, and CAPA actions for the Hyderabad chemical plant.", "anita.pillai@acertech.in"),
    (62, 16, "Ramesh Nair", "EHS Manager", "Leads ISO 14001 and ISO 45001 compliance and manages regulatory inspections for the chemical processing site.", "ramesh.nair@acertech.in"),
    (63, 16, "Sunitha Babu", "Safety Inspector", "Conducts process safety inspections, chemical storage audits, and fire safety compliance checks.", "sunitha.babu@acertech.in"),
    (64, 17, "Pradeep Kumar", "Quality Manager", "Manages batch quality testing, product specification compliance, and NCR investigation at the Hyderabad unit.", "pradeep.kumar@acertech.in"),
    (65, 17, "Leela Devi", "Quality Analyst", "Performs analytical testing of chemical batches; maintains laboratory safety and reagent controls.", "leela.devi@acertech.in"),
    (66, 17, "Mohan Rao", "Quality Analyst", "Manages raw material incoming inspection and supplier quality data.", "mohan.rao@acertech.in"),
    (67, 17, "Usha Reddy", "Quality Technician", "Maintains calibration records for laboratory instruments and manages sample archive.", "usha.reddy@acertech.in"),
    (68, 18, "Chandra Sekhar", "Process Engineer", "Responsible for process design, HAZOP review, and engineering change control at the Hyderabad plant.", "chandra.sekhar@acertech.in"),
    (69, 18, "Nagesh Rao", "Mechanical Engineer", "Manages pressure system integrity, PSV testing, and vessel inspection programme.", "nagesh.rao@acertech.in"),
    (70, 18, "Savitha Murthy", "Instrumentation Engineer", "Maintains safety instrumented system documentation and validates SIS performance.", "savitha.murthy@acertech.in"),
    (71, 18, "Kiran Babu", "Design Engineer", "Produces P&IDs and engineering drawings for plant modification projects.", "kiran.babu@acertech.in"),
    (72, 19, "Ravi Joshi", "Production Supervisor", "Supervises CNC machining and finishing operations; enforces machine guarding and cutting fluid hygiene standards.", "ravi.joshi@acertech.in"),
    (73, 19, "Anil Kulkarni", "Production Lead", "Leads CNC machining shift team and conducts pre-shift safety briefings.", "anil.kulkarni@acertech.in"),
    (74, 19, "Shweta Pawar", "CNC Operator", "Operates multi-axis CNC machining centres; responsible for machine guarding and coolant management.", "shweta.pawar@acertech.in"),
    (75, 19, "Nikhil Chavan", "CNC Operator", "Operates grinding machines and performs surface finishing operations with appropriate PPE.", "nikhil.chavan@acertech.in"),
    (76, 19, "Priya Bhosale", "Production Technician", "Manages tooling changeovers and assists with first-off inspection processes.", "priya.bhosale@acertech.in"),
    (77, 20, "Naresh Gupta", "Maintenance Supervisor", "Manages preventive maintenance of CNC and precision equipment; controls the LOTO programme at Pune.", "naresh.gupta@acertech.in"),
    (78, 20, "Sudhir Wagh", "Maintenance Technician", "Performs CNC machine servicing, lubrication, and ball-screw calibration.", "sudhir.wagh@acertech.in"),
    (79, 20, "Vijay Deshpande", "Electrician", "Maintains servo drives, control panels, and electrical isolation points for CNC machines.", "vijay.deshpande@acertech.in"),
    (80, 20, "Rekha Patil", "Maintenance Technician", "Services coolant filtration systems, chip conveyors, and coolant management plant.", "rekha.patil@acertech.in"),
    (81, 20, "Ganesh More", "Maintenance Technician", "Responsible for overhead crane inspections and lifting gear certification at the Pune facility.", "ganesh.more@acertech.in"),
    (82, 21, "Sunita Mehta", "EHS Officer", "Manages health and safety compliance for precision manufacturing; leads hearing conservation and chemical hygiene programmes.", "sunita.mehta@acertech.in"),
    (83, 21, "Sagar Jadhav", "Safety Inspector", "Conducts daily machine guarding inspections, noise monitoring surveys, and fire safety checks.", "sagar.jadhav@acertech.in"),
    (84, 21, "Neha Phadke", "EHS Coordinator", "Maintains CAPA tracking, training records, and ISO 45001 documentation for the Pune plant.", "neha.phadke@acertech.in"),
    (85, 22, "Deepak Marathe", "Quality Control Manager", "Manages dimensional inspection programme and NCR management for Pune precision components.", "deepak.marathe@acertech.in"),
    (86, 22, "Sneha Thakur", "Quality Inspector", "Performs CMM-based dimensional inspection and surface roughness measurement.", "sneha.thakur@acertech.in"),
    (87, 22, "Ajit Kamble", "Quality Inspector", "Manages first article inspection (FAI) and customer-specific quality plans.", "ajit.kamble@acertech.in"),
    (88, 22, "Rashmi Sawant", "Quality Technician", "Maintains calibration records and manages gauge inventory for the Pune quality lab.", "rashmi.sawant@acertech.in"),
    (89, 23, "Yogesh Gaikwad", "Warehouse Supervisor", "Manages parts receipt and finished goods dispatch for the Pune plant; oversees forklift safety.", "yogesh.gaikwad@acertech.in"),
    (90, 23, "Amit Shinde", "Forklift Operator", "Operates counterbalance forklift for material movements; conducts daily pre-use checks.", "amit.shinde@acertech.in"),
    (91, 23, "Vaishali Naik", "Stores Assistant", "Manages raw material kitting and works-in-progress storage for the production floor.", "vaishali.naik@acertech.in"),
    (92, 23, "Rahul Thombare", "Stores Assistant", "Handles finished goods packing and preparation for outbound dispatch.", "rahul.thombare@acertech.in"),
    (93, 24, "Manoj Khatri", "Process Engineer", "Manages CNC process parameters, toolpath optimisation, and engineering change control at Pune.", "manoj.khatri@acertech.in"),
    (94, 24, "Priti Ghosalkar", "Design Engineer", "Produces manufacturing drawings and tooling specifications for precision components.", "priti.ghosalkar@acertech.in"),
    (95, 24, "Santosh Kale", "Tooling Engineer", "Manages cutting tool selection, tool life monitoring, and supplier qualification.", "santosh.kale@acertech.in"),
    (96, 24, "Pallavi Datar", "CAD/CAM Engineer", "Programs CNC machines and manages CAM simulation for new production programmes.", "pallavi.datar@acertech.in"),
    (97, 25, "Hemant Gokhale", "HR Manager", "Manages workforce training compliance and competency tracking for Pune manufacturing staff.", "hemant.gokhale@acertech.in"),
    (98, 25, "Swati Karnik", "HR Officer", "Coordinates operator certification renewals and induction training for new joiners at Pune.", "swati.karnik@acertech.in"),
    (99, 25, "Rushikesh Bhide", "Training Coordinator", "Manages machine-specific training records and external certification bookings.", "rushikesh.bhide@acertech.in"),
    (100, 26, "Deepak Chauhan", "Operations Manager", "Manages all logistics operations at the Delhi distribution centre; leads forklift safety and manual handling improvement programmes.", "deepak.chauhan@acertech.in"),
    (101, 26, "Rajiv Sood", "Shift Supervisor", "Supervises picking and dispatch operations; enforces pedestrian segregation rules on the warehouse floor.", "rajiv.sood@acertech.in"),
    (102, 26, "Harpreet Kaur", "Forklift Operator", "Operates reach trucks in narrow aisle racking; trained in pedestrian awareness and blind spot management.", "harpreet.kaur@acertech.in"),
    (103, 26, "Manish Saxena", "Warehouse Associate", "Performs order picking and packing; trained in manual handling and ergonomic lifting techniques.", "manish.saxena@acertech.in"),
    (104, 27, "Kiran Yadav", "Maintenance Supervisor", "Manages forklift servicing and racking inspection programme for the Delhi distribution centre.", "kiran.yadav@acertech.in"),
    (105, 27, "Suresh Arora", "Maintenance Technician", "Services counterbalance and reach truck forklifts; maintains pre-use inspection records.", "suresh.arora@acertech.in"),
    (106, 27, "Pankaj Sharma", "Electrician", "Maintains warehouse lighting, power distribution, and battery charging stations for electric forklifts.", "pankaj.sharma@acertech.in"),
    (107, 27, "Neetu Bhatia", "Maintenance Technician", "Responsible for racking inspections, load rating signs, and minor structural repairs.", "neetu.bhatia@acertech.in"),
    (108, 28, "Pooja Sharma", "EHS Officer", "Manages health and safety programme for the Delhi distribution centre; leads fire safety and forklift safety campaigns.", "pooja.sharma@acertech.in"),
    (109, 28, "Amit Rawat", "Safety Inspector", "Conducts racking, forklift, and fire safety inspections; investigates near misses and minor incidents.", "amit.rawat@acertech.in"),
    (110, 28, "Reema Singh", "EHS Coordinator", "Maintains CAPA tracking, training records, and fire drill documentation for the Delhi site.", "reema.singh@acertech.in"),
    (111, 29, "Vikas Kapoor", "Dispatch Supervisor", "Manages outbound loading dock operations and driver safety inductions at Delhi DC.", "vikas.kapoor@acertech.in"),
    (112, 29, "Seema Ahluwalia", "Dispatch Coordinator", "Coordinates carrier schedules and manages dock allocation for efficient outbound flow.", "seema.ahluwalia@acertech.in"),
    (113, 29, "Rohit Bansode", "Dock Operative", "Operates dock levellers and manages lorry reversing safety under Dispatch Supervisor oversight.", "rohit.bansode@acertech.in"),
    (114, 29, "Nidhi Jain", "Dispatch Clerk", "Manages dispatch documentation, delivery notes, and carrier compliance records.", "nidhi.jain@acertech.in"),
    (115, 30, "Gurpreet Singh", "Security Supervisor", "Manages access control and emergency response coordination at the Delhi distribution centre.", "gurpreet.singh@acertech.in"),
    (116, 30, "Ajay Tandon", "Security Guard", "Controls visitor access and monitors CCTV systems at Delhi DC entry points.", "ajay.tandon@acertech.in"),
    (117, 30, "Priya Malhotra", "Security Guard", "Patrols the facility perimeter and assists with emergency evacuations.", "priya.malhotra@acertech.in"),
    (118, 31, "Mahesh Nair", "Production Supervisor", "Supervises PCB assembly, soldering, and electronics test lines; enforces ESD and solder fume controls.", "mahesh.nair@acertech.in"),
    (119, 31, "Anitha Rao", "Production Lead", "Leads SMT line operations and conducts pre-shift briefings on soldering fume and ergonomic hazards.", "anitha.rao@acertech.in"),
    (120, 31, "Chetan Hegde", "SMT Operator", "Operates surface mount technology placement and reflow soldering machines; trained in fume extraction maintenance.", "chetan.hegde@acertech.in"),
    (121, 31, "Geetha Narayan", "Assembly Technician", "Performs manual PCB assembly and through-hole soldering; uses ESD wrist strap and anti-static mat.", "geetha.narayan@acertech.in"),
    (122, 31, "Vinod Shetty", "Test Technician", "Operates automated test equipment for electronics functional testing; manages test fixture safety.", "vinod.shetty@acertech.in"),
    (123, 32, "Arjun Reddy", "Maintenance Supervisor", "Manages all maintenance activities at the Bengaluru electronics plant including clean-room HVAC systems.", "arjun.reddy@acertech.in"),
    (124, 32, "Ramana Gowda", "Maintenance Technician", "Services SMT placement machines, reflow ovens, and automated test equipment.", "ramana.gowda@acertech.in"),
    (125, 32, "Indira Prasad", "Electrician", "Maintains electrical installations, UPS systems, and ESD protection infrastructure.", "indira.prasad@acertech.in"),
    (126, 32, "Suresh Bhat", "HVAC Technician", "Services clean-room HVAC, fume extraction systems, and environmental monitoring equipment.", "suresh.bhat@acertech.in"),
    (127, 32, "Padmavathi Rao", "Maintenance Technician", "Maintains solder paste printing machines and dispensing equipment.", "padmavathi.rao@acertech.in"),
    (128, 33, "Divya Krishnamurthy", "EHS Officer", "Manages chemical hygiene, solder fume monitoring, waste disposal compliance, and CAPA actions for the Bengaluru plant.", "divya.krishnamurthy@acertech.in"),
    (129, 33, "Sridhar Narayana", "Safety Inspector", "Conducts daily fume extraction, ESD, and fire safety inspections; maintains inspection logs.", "sridhar.narayana@acertech.in"),
    (130, 33, "Bharathi Sundaram", "EHS Coordinator", "Maintains CAPA tracking, chemical register, and occupational health records for Bengaluru.", "bharathi.sundaram@acertech.in"),
    (131, 34, "Krishnamurthy Iyengar", "Quality Control Manager", "Manages electronics inspection programme including AOI, X-ray, and functional test at Bengaluru.", "krishnamurthy.iyengar@acertech.in"),
    (132, 34, "Sowmya Reddy", "Quality Inspector", "Operates automated optical inspection and visual inspection for solder defects.", "sowmya.reddy@acertech.in"),
    (133, 34, "Rajan Pillai", "Quality Inspector", "Manages IPC-A-610 workmanship standards compliance and operator training.", "rajan.pillai@acertech.in"),
    (134, 34, "Thenmozhi Kumar", "Quality Technician", "Maintains calibration records for test equipment and manages measurement uncertainty analysis.", "thenmozhi.kumar@acertech.in"),
    (135, 35, "Suresh Gopalan", "Warehouse Supervisor", "Manages ESD-controlled component storage and finished electronics goods dispatch at Bengaluru.", "suresh.gopalan@acertech.in"),
    (136, 35, "Madhuri Srinivasan", "Stores Associate", "Manages ESD packaging, component kitting, and humidity-sensitive component storage.", "madhuri.srinivasan@acertech.in"),
    (137, 35, "Balu Krishnan", "Forklift Operator", "Operates pallet truck and pedestrian-operated forklifts for internal material movements.", "balu.krishnan@acertech.in"),
    (138, 35, "Hema Sekar", "Stores Associate", "Manages goods receipt inspection and component traceability documentation.", "hema.sekar@acertech.in"),
    (139, 36, "Prashanth Murthy", "Process Engineer", "Manages SMT process parameters, solder paste qualification, and engineering change control.", "prashanth.murthy@acertech.in"),
    (140, 36, "Roopa Venkatesh", "Design Engineer", "Designs PCB layouts and manages design-for-manufacture (DFM) guidelines.", "roopa.venkatesh@acertech.in"),
    (141, 36, "Aditya Prabhu", "Test Engineer", "Develops automated test fixtures and maintains test coverage documentation.", "aditya.prabhu@acertech.in"),
    (142, 36, "Sindhu Ramesh", "NPI Engineer", "Manages new product introduction activities and pilot production readiness reviews.", "sindhu.ramesh@acertech.in"),
    (143, 37, "Nirmala Naidu", "HR Manager", "Manages workforce ergonomics programme and occupational health monitoring for Bengaluru assembly staff.", "nirmala.naidu@acertech.in"),
    (144, 37, "Santosh Kulkarni", "HR Officer", "Coordinates workstation ergonomic assessments and manages DSE health surveillance.", "santosh.kulkarni@acertech.in"),
    (145, 37, "Archana Pai", "Training Coordinator", "Manages IPC-A-610 certification renewals and ESD awareness training records.", "archana.pai@acertech.in"),
    (146, 38, "Ganesh Shah", "Production Supervisor", "Oversees bulk chemical transfer and blending operations; enforces process safety and permit-to-work standards.", "ganesh.shah@acertech.in"),
    (147, 38, "Bharat Patel", "Process Operator", "Operates acid transfer systems and bulk storage transfers; trained in HAZMAT emergency response.", "bharat.patel@acertech.in"),
    (148, 38, "Hinal Desai", "Process Operator", "Manages alkali blending operations and chemical transfer pipework connections.", "hinal.desai@acertech.in"),
    (149, 38, "Jignesh Modi", "Production Lead", "Leads shift operations and conducts pre-shift chemical hazard and emergency response briefings.", "jignesh.modi@acertech.in"),
    (150, 39, "Rahul Tiwari", "Chemical Handling Supervisor", "Manages receipt, storage, and transfer of all bulk chemicals at the Ahmedabad site; owns HAZMAT and spill response procedures.", "rahul.tiwari@acertech.in"),
    (151, 39, "Kalpesh Joshi", "Chemical Handler", "Operates road tanker connections and bulk acid/alkali transfer systems.", "kalpesh.joshi@acertech.in"),
    (152, 39, "Mira Trivedi", "Chemical Handler", "Manages chemical storage area compliance, SDS files, and incompatibility segregation.", "mira.trivedi@acertech.in"),
    (153, 39, "Nirav Bhatt", "Chemical Handler", "Responsible for hazardous waste packaging, labelling, and licensed disposal contractor coordination.", "nirav.bhatt@acertech.in"),
    (154, 39, "Puja Mehta", "Chemical Handler", "Performs daily inspection of chemical bunds, drain covers, and spill kit inventory.", "puja.mehta@acertech.in"),
    (155, 40, "Sunil Dubey", "Maintenance Supervisor", "Manages all maintenance work at the chemical processing site; controls hot work, confined space, and pressure isolation permits.", "sunil.dubey@acertech.in"),
    (156, 40, "Mahesh Patel", "Maintenance Technician", "Services chemical process pumps, valves, and pipework; confined space entry rescue trained.", "mahesh.patel@acertech.in"),
    (157, 40, "Sanjay Vaghela", "Instrument Technician", "Maintains pressure transmitters, PSVs, and safety interlock systems at the Ahmedabad plant.", "sanjay.vaghela@acertech.in"),
    (158, 40, "Rekha Solanki", "Electrician", "Maintains ATEX-rated electrical equipment and conducts periodic zone inspection in classified areas.", "rekha.solanki@acertech.in"),
    (159, 41, "Meena Agarwal", "EHS Officer", "Manages PSM programme, HAZOP compliance, and CAPA actions for the Ahmedabad chemical processing unit.", "meena.agarwal@acertech.in"),
    (160, 41, "Yogesh Dave", "EHS Manager", "Leads ISO 14001 compliance, regulatory liaison, and emergency response planning for Ahmedabad.", "yogesh.dave@acertech.in"),
    (161, 41, "Devyani Parikh", "Safety Inspector", "Conducts process safety, HAZMAT storage, and emergency equipment inspections daily.", "devyani.parikh@acertech.in"),
    (162, 42, "Alpesh Bhavsar", "Quality Manager", "Manages raw material and finished batch quality testing; handles supplier non-conformance reports.", "alpesh.bhavsar@acertech.in"),
    (163, 42, "Pragna Rao", "Quality Analyst", "Performs analytical chemistry testing of chemical batches; manages GC and titration equipment.", "pragna.rao@acertech.in"),
    (164, 42, "Sailesh Kapadia", "Quality Analyst", "Manages raw material incoming quality inspection and COA verification.", "sailesh.kapadia@acertech.in"),
    (165, 42, "Heena Mirza", "Quality Technician", "Maintains laboratory safety, reagent controls, and sample chain-of-custody documentation.", "heena.mirza@acertech.in"),
    (166, 43, "Dhruv Sharma", "Process Engineer", "Manages process design, HAZOP reviews, and MOC approvals for the Ahmedabad chemical plant.", "dhruv.sharma@acertech.in"),
    (167, 43, "Bela Contractor", "Mechanical Engineer", "Manages pressure vessel inspection, PSV testing, and storage tank integrity programme.", "bela.contractor@acertech.in"),
    (168, 43, "Rajan Suri", "Instrumentation Engineer", "Maintains SIS documentation and validates functional safety performance for critical loops.", "rajan.suri@acertech.in"),
    (169, 43, "Foram Desai", "Design Engineer", "Produces P&IDs, engineering drawings, and technical specifications for plant modifications.", "foram.desai@acertech.in"),
    (170, 44, "Bimal Bose", "Production Supervisor", "Supervises structural steel fabrication, welding, and heat treatment operations at Kolkata.", "bimal.bose@acertech.in"),
    (171, 44, "Subhasis Das", "Production Lead", "Leads fabrication shift team and ensures hot work permit compliance and weld fume extraction use.", "subhasis.das@acertech.in"),
    (172, 44, "Tapas Ghosh", "Welder", "Performs structural steel welding; certified to BS EN ISO 9606-1; uses weld fume extraction LEV.", "tapas.ghosh@acertech.in"),
    (173, 44, "Suparna Sen", "Welder", "Performs TIG and MIG welding on pressure vessel components; uses appropriate respiratory protection.", "suparna.sen@acertech.in"),
    (174, 44, "Ratan Pal", "Fabricator", "Performs plate marking, cutting, and fit-up for pressure vessel fabrication.", "ratan.pal@acertech.in"),
    (175, 45, "Santosh Das", "Maintenance Supervisor", "Manages all planned and corrective maintenance at Kolkata; controls LOTO programme and overhead crane certification.", "santosh.das@acertech.in"),
    (176, 45, "Amit Chatterjee", "Maintenance Technician", "Services overhead cranes, lifting gear, and welding machines; crane inspection trained.", "amit.chatterjee@acertech.in"),
    (177, 45, "Debashis Mondal", "Electrician", "Maintains welding power sources, electrical panels, and HV isolation systems at Kolkata.", "debashis.mondal@acertech.in"),
    (178, 45, "Sharmistha Roy", "Maintenance Technician", "Services hydraulic press brakes, plate rollers, and forming equipment.", "sharmistha.roy@acertech.in"),
    (179, 45, "Pinaki Sarkar", "Crane Operator", "Operates bridge cranes and jib cranes for heavy plate and vessel movement; licensed overhead crane operator.", "pinaki.sarkar@acertech.in"),
    (180, 46, "Rekha Ghosh", "EHS Officer", "Manages site safety programme for heavy fabrication including confined space, hot work, and weld fume monitoring at Kolkata.", "rekha.ghosh@acertech.in"),
    (181, 46, "Arup Banerjee", "EHS Manager", "Leads ISO 45001 compliance and manages regulatory inspections for the Kolkata heavy manufacturing site.", "arup.banerjee@acertech.in"),
    (182, 46, "Mousumi Paul", "Safety Inspector", "Conducts daily hot work, confined space, and crane safety inspections at Kolkata.", "mousumi.paul@acertech.in"),
    (183, 47, "Prasenjit Mukherjee", "Quality Control Manager", "Manages weld inspection, NDT, and pressure vessel code compliance at the Kolkata plant.", "prasenjit.mukherjee@acertech.in"),
    (184, 47, "Sukla Biswas", "NDT Inspector", "Performs UT, MT, PT, and radiographic inspection of weld joints; PCN Level 2 certified.", "sukla.biswas@acertech.in"),
    (185, 47, "Tanmay Datta", "Quality Inspector", "Conducts dimensional inspection of pressure vessels against customer drawings and code requirements.", "tanmay.datta@acertech.in"),
    (186, 47, "Indrani Chakraborty", "Quality Technician", "Maintains weld map records, NDE reports, and pressure test certificates.", "indrani.chakraborty@acertech.in"),
    (187, 48, "Sourav Nandi", "Warehouse Supervisor", "Manages heavy steel plate receipt, storage, and finished vessel dispatch at Kolkata; oversees crane-assisted loading.", "sourav.nandi@acertech.in"),
    (188, 48, "Dipak Halder", "Crane Operator", "Operates overhead cranes for heavy plate and vessel movement in the Kolkata warehouse bay.", "dipak.halder@acertech.in"),
    (189, 48, "Madhu Banerjee", "Stores Associate", "Manages consumable stores, welding wire, gas cylinder inventory, and documentation.", "madhu.banerjee@acertech.in"),
    (190, 48, "Arnab Dey", "Rigging Technician", "Responsible for slinging, rigging, and banksman duties for all heavy lifts at Kolkata.", "arnab.dey@acertech.in"),
    (191, 49, "Sujoy Chakraborty", "Structural Engineer", "Manages pressure vessel design, code calculations, and MOC approvals for Kolkata fabrication projects.", "sujoy.chakraborty@acertech.in"),
    (192, 49, "Paramita Ghosh", "Process Engineer", "Manages heat treatment specifications, weld procedure qualification, and material traceability.", "paramita.ghosh@acertech.in"),
    (193, 49, "Ayan Roy", "Design Engineer", "Produces vessel fabrication drawings and weld maps for customer and code submission.", "ayan.roy@acertech.in"),
    (194, 49, "Nilima Basu", "NDT Coordinator", "Manages the NDT programme, inspection scope, and PCN-certified contractor interface.", "nilima.basu@acertech.in"),
    (195, 50, "Rupa Mitra", "HR Manager", "Manages welding certifications, trade qualifications, and mandatory competency records at Kolkata.", "rupa.mitra@acertech.in"),
    (196, 50, "Sohini Das", "HR Officer", "Coordinates welder certification renewals, code qualification records, and external training.", "sohini.das@acertech.in"),
    (197, 50, "Uttam Paul", "Training Coordinator", "Manages mandatory safety training records, confined space rescue training, and first aid certifications.", "uttam.paul@acertech.in"),
    (198, 51, "Tarun Singh", "Civil Engineer", "Manages foundation and structural construction activities; prepares method statements for excavation and formwork.", "tarun.singh@acertech.in"),
    (199, 51, "Senthil Raj", "Site Foreman", "Supervises day-to-day construction activities; enforces excavation shoring and working at heights safety rules.", "senthil.raj@acertech.in"),
    (200, 51, "Murugesan Pillai", "Construction Worker", "Performs formwork, concrete placing, and rebar fixing tasks; trained in working at heights and evacuation procedures.", "murugesan.pillai@acertech.in"),
    (201, 51, "Arumugam Durai", "Construction Worker", "Performs excavation support, backfill, and civil finishing tasks under Site Foreman supervision.", "arumugam.durai@acertech.in"),
    (202, 52, "Vijay Kumar", "Equipment Operator", "Operates excavators and concrete mixers for construction activities; conducts daily plant pre-use checks.", "vijay.kumar@acertech.in"),
    (203, 52, "Selvam Krishnan", "Equipment Operator", "Operates tower crane and concrete pump for structural construction activities; licensed crane operator.", "selvam.krishnan@acertech.in"),
    (204, 52, "Ravi Muthusamy", "Equipment Operator", "Operates mobile plant and generator sets; manages fuel storage and equipment maintenance logs.", "ravi.muthusamy@acertech.in"),
    (205, 52, "Balakumar Sekar", "Banksman", "Provides banksman duties for crane lifts and plant movements; controls exclusion zones during lifting operations.", "balakumar.sekar@acertech.in"),
    (206, 53, "Lakshmi Murugan", "EHS Officer", "Manages construction site safety including working at heights, confined space, and subcontractor safety oversight.", "lakshmi.murugan@acertech.in"),
    (207, 53, "Dinesh Babu", "Safety Inspector", "Conducts daily safety inspections of scaffolding, lifting equipment, and excavation edge protection.", "dinesh.babu@acertech.in"),
    (208, 53, "Geetha Rajan", "EHS Coordinator", "Maintains induction records, permit-to-work logs, and incident investigation documentation for the construction site.", "geetha.rajan@acertech.in"),
    (209, 54, "Ramachandran Venkat", "Subcontractor Manager", "Manages subcontractor approval, pre-qualification, and ongoing safety performance monitoring on the construction site.", "ramachandran.venkat@acertech.in"),
    (210, 54, "Bharani Murugan", "Subcontractor Coordinator", "Coordinates subcontractor inductions, permit submissions, and safety compliance documentation.", "bharani.murugan@acertech.in"),
    (211, 54, "Saravanan Pillai", "Site Administrator", "Manages site visitor logs, subcontractor register, and RAMS documentation filing.", "saravanan.pillai@acertech.in"),
    (212, 54, "Preethi Pandian", "Procurement Coordinator", "Manages subcontractor procurement, POs, and contract compliance documentation.", "preethi.pandian@acertech.in"),
    (213, 55, "Prakash Pillai", "Site Engineer", "Manages project schedule, method statements, and temporary works coordination for the construction site.", "prakash.pillai@acertech.in"),
    (214, 55, "Chandru Sivakumar", "Planning Engineer", "Produces construction programme, look-ahead schedules, and resource allocation plans.", "chandru.sivakumar@acertech.in"),
    (215, 55, "Revathi Anand", "Document Controller", "Manages drawing revisions, method statement approvals, and engineering correspondence files.", "revathi.anand@acertech.in"),
    (216, 56, "Uday Pandey", "Operations Manager", "Manages all logistics operations at Coimbatore DC; leads forklift safety and racking inspection programmes.", "uday.pandey@acertech.in"),
    (217, 56, "Bhaskar Sundaram", "Shift Supervisor", "Supervises picking and dispatch shifts; enforces pedestrian segregation and manual handling standards.", "bhaskar.sundaram@acertech.in"),
    (218, 56, "Muthukumar Selvan", "Forklift Operator", "Operates counterbalance forklift for receipt and put-away operations; conducts daily pre-use checks.", "muthukumar.selvan@acertech.in"),
    (219, 56, "Kavitha Gopal", "Warehouse Associate", "Performs order picking, packing, and stock count duties; trained in ergonomic lifting techniques.", "kavitha.gopal@acertech.in"),
    (220, 57, "Harish Verma", "Maintenance Supervisor", "Manages forklift servicing schedule and racking inspection programme for the Coimbatore facility.", "harish.verma@acertech.in"),
    (221, 57, "Suresh Raj", "Maintenance Technician", "Services forklift fleet and maintains pre-use inspection records for Coimbatore DC.", "suresh.raj@acertech.in"),
    (222, 57, "Bhanu Prakash", "Electrician", "Maintains warehouse electrical systems, emergency lighting, and battery charging infrastructure.", "bhanu.prakash@acertech.in"),
    (223, 57, "Malathi Rajan", "Maintenance Technician", "Responsible for racking inspection, load rating signs, and minor facility repairs.", "malathi.rajan@acertech.in"),
    (224, 58, "Nisha Iyer", "EHS Officer", "Leads safety programme and fire prevention for the Coimbatore DC; manages CAPA actions for near misses and incidents.", "nisha.iyer@acertech.in"),
    (225, 58, "Tamilarasan Ganesan", "Safety Inspector", "Conducts racking, forklift, and fire safety inspections; investigates near miss events.", "tamilarasan.ganesan@acertech.in"),
    (226, 58, "Janani Murugesan", "EHS Coordinator", "Maintains CAPA tracking, training records, and emergency drill documentation for Coimbatore.", "janani.murugesan@acertech.in"),
    (227, 59, "Rajan Kumar", "Dispatch Supervisor", "Manages outbound loading dock operations and driver safety inductions at Coimbatore DC.", "rajan.kumar@acertech.in"),
    (228, 59, "Saranya Murugan", "Dispatch Coordinator", "Coordinates carrier schedules and manages dock allocation for the southern region shipments.", "saranya.murugan@acertech.in"),
    (229, 59, "Ganesh Babu", "Dock Operative", "Operates dock levellers and manages vehicle reversing safety under Dispatch Supervisor supervision.", "ganesh.babu@acertech.in"),
    (230, 59, "Priya Selvam", "Dispatch Clerk", "Manages dispatch documentation, delivery notes, and carrier performance records.", "priya.selvam@acertech.in"),
    (231, 60, "Balan Krishnan", "Security Supervisor", "Manages access control and emergency response coordination for the Coimbatore distribution centre.", "balan.krishnan@acertech.in"),
    (232, 60, "Palaniappan Murugan", "Security Guard", "Controls visitor access and monitors CCTV at the Coimbatore DC entrance.", "palaniappan.murugan@acertech.in"),
    (233, 60, "Sumathi Raj", "Security Guard", "Patrols the facility perimeter and assists with emergency muster management.", "sumathi.raj@acertech.in"),
    (234, 61, "Anil Mehta", "EHS Compliance Manager", "Leads group-wide EHS policy, audit programme, and regulatory compliance reporting for AcerTech Industries.", "anil.mehta@acertech.in"),
    (235, 61, "Kavita Sharma", "EHS Auditor", "Conducts internal EHS audits across all AcerTech sites and manages audit finding closure.", "kavita.sharma@acertech.in"),
    (236, 61, "Prashant Rane", "Regulatory Affairs Officer", "Manages regulatory submissions, government inspections, and compliance reporting for the group.", "prashant.rane@acertech.in"),
    (237, 61, "Sonali Patil", "EHS Data Analyst", "Manages group EHS performance metrics, incident statistics, and management reporting dashboards.", "sonali.patil@acertech.in"),
    (238, 62, "Suma Patel", "Group HR Manager", "Manages group HR policy, workforce planning, and training governance across all AcerTech sites.", "suma.patel@acertech.in"),
    (239, 62, "Rohan Kapoor", "HR Business Partner", "Partners with site leadership teams to drive workforce compliance and competency development.", "rohan.kapoor@acertech.in"),
    (240, 62, "Anjali Bose", "Learning & Development Manager", "Manages the group LMS, mandatory training frameworks, and leadership development programmes.", "anjali.bose@acertech.in"),
    (241, 62, "Vivek Nair", "HR Analyst", "Maintains group workforce data, absence statistics, and regulatory training compliance reports.", "vivek.nair@acertech.in"),
    (242, 63, "Shalini Gupta", "Office Manager", "Manages corporate office facilities, reception, and building services at the Mumbai headquarters.", "shalini.gupta@acertech.in"),
    (243, 63, "Rakesh Tiwari", "Facilities Coordinator", "Manages building maintenance, contractor access, and office infrastructure at corporate HQ.", "rakesh.tiwari@acertech.in"),
    (244, 63, "Pooja Chatterjee", "Receptionist", "Manages visitor management, meeting room bookings, and front-of-house operations at HQ.", "pooja.chatterjee@acertech.in"),
    (245, 63, "Manish Kumar", "Building Services Engineer", "Manages HVAC, lifts, and building services maintenance for the corporate office.", "manish.kumar@acertech.in"),
    (246, 64, "Rajesh Sinha", "IT Manager", "Manages IT infrastructure, cyber security, and the EHS software platform for AcerTech Industries.", "rajesh.sinha@acertech.in"),
    (247, 64, "Anand Trivedi", "Systems Administrator", "Manages server infrastructure, network security, and backup systems for the corporate office and site links.", "anand.trivedi@acertech.in"),
    (248, 64, "Priya Rajan", "IT Support Engineer", "Provides first and second line IT support for all AcerTech sites; manages end-user devices.", "priya.rajan@acertech.in"),
    (249, 64, "Sanjay Menon", "Data Engineer", "Manages the EHS data platform, database administration, and business intelligence reporting.", "sanjay.menon@acertech.in"),
]

# (category_id, name) — root_cause_taxonomy, descriptions dropped (not in mirror schema)
ROOT_CAUSE_TAXONOMY_SRC = [
    (1, "Equipment Fault"),
    (2, "Training Gap"),
    (3, "Process Failure"),
    (4, "Missing Inspection"),
    (5, "Engineering Control Gap"),
    (6, "Management System Weakness"),
    (7, "Human Error"),
    (8, "Environmental Factor"),
]

# (capa_id, title, description, source_type, source_id, site_id, dept_id,
#  severity, priority, status, due_date, capa_type, closed_at, created_by, assigned_to)
CAPAS_SRC = [
    (1, 'Overhead Crane Wire Rope Failure During Production Lift',
     'Wire rope on OC-001 failed mid-lift dropping a 400 kg component 2.1 m. No injury. Fatigue strands were not detected at previous monthly inspection.',
     'Incident', 'INC-2024-0312', 1, 2, 'High', 'High', 'Closed', '2024-06-15', 'Corrective and Preventive', '2024-06-10', 11, 6),
    (2, 'CNC Spindle Brake Failure — Uncontrolled Rotation After Tool Change',
     'Spindle brake failed to engage on CNC-04 following tool change. Machine rotated for 12 seconds after stop command. Operator withdrew hand in time.',
     'Incident', 'INC-2024-0718', 4, 20, 'High', 'High', 'Closed', '2024-10-31', 'Corrective', '2024-10-15', 82, 77),
    (3, 'HVAC Chiller Failure Causes Clean Room Temperature Exceedance',
     'Chiller CH-2 failed, allowing SMT clean room temperature to exceed 35 C for 4 hours. Products quarantined. No personal injury reported.',
     'Near Miss', 'NM-2024-1105', 6, 32, 'Medium', 'High', 'Open', '2025-07-15', 'Corrective and Preventive', None, 128, 123),
    (4, 'Pressure Vessel Wall Thinning Found at Statutory Inspection',
     'Five-year statutory inspection of PV-012 revealed wall thinning to 67 percent of nominal in a corrosion zone. Vessel taken out of service immediately.',
     'Inspection', 'INS-2024-0330', 8, 45, 'High', 'High', 'Closed', '2024-06-30', 'Corrective and Preventive', '2024-06-25', 180, 175),
    (5, 'Forklift Hydraulic Hose Burst During Warehouse Stacking Operation',
     'Hydraulic hose on FL-07 burst during stacking. Fluid released onto floor creating slip hazard. Hose was 18 months beyond its scheduled replacement date.',
     'Inspection', 'INS-2024-1110', 10, 57, 'Low', 'Low', 'Closed', '2025-02-28', 'Corrective', '2025-02-15', 224, 216),
    (6, 'Forklift Operator Near Miss — No Training on Pedestrian Zone Controls',
     'FL-03 driver entered designated pedestrian crossing without slowing. Investigation found operator had received no site-specific pedestrian-vehicle segregation training.',
     'Near Miss', 'NM-2024-0502', 2, 8, 'Medium', 'High', 'Closed', '2024-08-15', 'Corrective and Preventive', '2024-08-10', 38, 34),
    (7, 'Manual Handler Placed Hands Under Pallet During Unstacking',
     'Picker placed hands between pallet base and floor during unstable load. Near miss injury avoided. No manual handling training record found in personnel file.',
     'Safety Observation', 'SO-2025-0107', 5, 26, 'Low', 'Low', 'Closed', '2025-04-30', 'Corrective', '2025-04-15', 108, 100),
    (8, 'Hot Work Permit Issued by Supervisor Without PTW Authoriser Training',
     'Shift supervisor issued hot work permit without completing the required checklist items. Supervisor had never been trained for the PTW authoriser role.',
     'Incident', 'INC-2025-0215', 1, 7, 'Medium', 'High', 'Open', '2025-09-15', 'Corrective and Preventive', None, 11, 12),
    (9, 'Construction Scaffolder Erected System Type Without Required Certification',
     'Scaffold inspector found system scaffold erected by operative lacking the required CISRS card for that system type. Structure was assessed as unsafe for use.',
     'Near Miss', 'NM-2025-0120', 9, 53, 'High', 'High', 'In Progress', '2025-09-01', 'Corrective and Preventive', None, 206, 213),
    (10, 'Chemical Operator Added Wrong Reagent Due to Inadequate Label Training',
     'Operator misread drum label and added incorrect reagent to a batch. Batch scrapped. No documented training on label differentiation or reagent identification found.',
     'Incident', 'INC-2024-0905', 3, 13, 'High', 'High', 'Closed', '2024-12-15', 'Corrective and Preventive', '2024-12-10', 61, 52),
    (11, 'COSHH Assessment Not Updated After Chemical Substitution',
     'A replacement solvent was introduced into the degreasing process without updating the COSHH risk assessment or informing operators of the changed hazard profile.',
     'Audit', 'AUD-2024-0318', 3, 16, 'High', 'High', 'Closed', '2024-06-30', 'Corrective and Preventive', '2024-06-25', 61, 52),
    (12, 'Non-Conforming Components Released Without Deviation Approval',
     '240 precision-machined components were dispatched without completing the required deviation approval process. Traceability gap across two production orders.',
     'NCR', 'NCR-2024-0712', 4, 22, 'Medium', 'Medium', 'Closed', '2024-10-31', 'Corrective', '2024-10-15', 82, 72),
    (13, 'Quality Hold Bypassed — Non-Conforming Units Dispatched to Customer',
     '180 units under quality hold were dispatched following an undocumented supervisor override. Customer complaint received. Hold process controls were not enforced.',
     'NCR', 'NCR-2024-1103', 6, 34, 'High', 'High', 'Closed', '2025-01-31', 'Corrective', '2025-01-20', 128, 118),
    (14, 'Management of Change Not Initiated for Temporary Safety System Bypass',
     'An instrumented safety bypass was installed to maintain production during a maintenance outage with no MOC process initiated and no risk assessment completed.',
     'Audit', 'AUD-2024-0620', 8, 46, 'High', 'High', 'Closed', '2024-09-30', 'Corrective and Preventive', '2024-09-25', 180, 181),
    (15, 'Group EHS Policy Not Distributed to Four Recently Appointed Site Managers',
     'Corporate audit found four site managers appointed in the past 12 months had not received the current Group EHS Policy. No distribution or acknowledgement record exists.',
     'Audit', 'AUD-2025-0401', 11, 61, 'High', 'High', 'Open', '2025-12-31', 'Corrective and Preventive', None, 234, 234),
    (16, 'Solvent Vapour Overexposure Due to Failed LEV System',
     'LEV ductwork detached at a joint in the degreasing booth. Solvent vapour STEL exceeded 3.4 times the limit. Three operators exposed. System not re-tested after prior duct repair.',
     'Incident', 'INC-2024-0407', 3, 14, 'High', 'High', 'Closed', '2024-07-15', 'Corrective and Preventive', '2024-07-10', 61, 57),
    (17, 'Acid Transfer Line Leak at Corroded Flange — Operator Skin Burn',
     'HCl process line PL-007 developed a pinhole leak at a corroded gasket. Operator sustained first-degree acid burns to forearm. Line had exceeded its inspection interval.',
     'Incident', 'INC-2024-0519', 7, 39, 'High', 'High', 'Closed', '2024-08-31', 'Corrective and Preventive', '2024-08-25', 159, 155),
    (18, 'Flammable Liquid Decanting Without Earth Bonding — Near Miss',
     'Operator observed decanting methanol without attaching earth bonding clip. Ignition source present within 3 m. Drum decanting procedure does not specify the bonding requirement.',
     'Near Miss', 'NM-2024-0908', 7, 40, 'Medium', 'Medium', 'Closed', '2024-12-31', 'Corrective', '2024-12-20', 159, 150),
    (19, 'Nitrogen Purge Failure Creates Oxygen-Deficient Atmosphere in Vessel',
     'Nitrogen purge system for Reactor R-006 failed mid-purge. Operator entered vessel before atmosphere testing. O2 reading on entry measured 16.8 percent.',
     'Incident', 'INC-2025-0325', 7, 40, 'High', 'High', 'Open', '2025-09-30', 'Corrective and Preventive', None, 159, 155),
    (20, 'Chemical Storage Bund Capacity Below 110 Percent Regulatory Minimum',
     'Engineering review confirmed secondary containment for Tank Farm A has net capacity of 82 percent of the largest vessel, below the regulatory 110 percent minimum.',
     'Risk', 'RISK-2024-1120', 7, 43, 'High', 'High', 'In Progress', '2025-09-30', 'Corrective and Preventive', None, 159, 155),
    (21, 'Fire Extinguisher Annual Service Overdue — Six Units Out of Date',
     'Monthly inspection found 6 of 24 portable fire extinguishers on the production floor with service dates exceeding 12 months. Annual contractor service had not been completed.',
     'Inspection', 'INS-2024-0605', 1, 3, 'Medium', 'Medium', 'Closed', '2024-09-30', 'Corrective', '2024-09-15', 11, 11),
    (22, 'Emergency Exit Partially Obstructed by Stored Pallet Stacks',
     'Safety walkthrough found two emergency exit doors partially blocked. Clearance reduced to 0.6 m against a required 1.2 m minimum. Obstruction had been in place for at least two weeks.',
     'Inspection', 'INS-2024-0720', 2, 10, 'Low', 'Low', 'Closed', '2024-10-31', 'Corrective', '2024-10-20', 38, 30),
    (23, 'Emergency Lighting Battery Failures Found on Annual Duration Test',
     'Annual 3-hour duration test found 14 of 76 emergency lighting fittings failing to maintain illumination. Batteries had not been individually tested as required between annual tests.',
     'Audit', 'AUD-2024-1202', 6, 33, 'High', 'High', 'In Progress', '2025-08-31', 'Corrective and Preventive', None, 128, 128),
    (24, 'Sprinkler Quarterly Flow Test Overdue — No Deferral Approval Recorded',
     'Q3 sprinkler system quarterly flow test was not completed. Maintenance schedule shows test overdue by 45 days. No deferred inspection approval had been recorded.',
     'Inspection', 'INS-2024-1108', 8, 46, 'Low', 'Low', 'Open', '2025-08-01', 'Corrective', None, 180, 175),
    (25, 'Emergency Assembly Point Signs Removed During Construction — No Replacement',
     'Active construction in Zone 6 resulted in removal of three emergency assembly point signs. No temporary replacement signage was installed as required by the site hot works permit.',
     'Near Miss', 'NM-2025-0319', 9, 53, 'High', 'High', 'Closed', '2025-08-15', 'Corrective', '2025-08-01', 206, 213),
    (26, 'OC-001 Wire Rope Broken Strands Found — First Documented Recurrence',
     'Maintenance inspection found broken strands on OC-001 wire rope for the second time in 12 months. Prior corrective action was verbal instruction to operators only.',
     'Inspection', 'INS-2023-0310', 1, 2, 'High', 'High', 'Closed', '2023-06-10', 'Corrective', '2023-06-15', 11, 6),
    (27, 'OC-001 Wire Rope Below Discard Criteria — Second Recurrence',
     'Wire rope on OC-001 found below discard criteria at routine inspection. Training-only corrective action from prior CAPA demonstrably failed to address root cause.',
     'Inspection', 'INS-2023-1105', 1, 2, 'High', 'High', 'Closed', '2024-02-05', 'Corrective', '2024-02-20', 11, 6),
    (28, 'OC-001 Wire Rope Degraded to Failure Before Scheduled Replacement — Third',
     'Wire rope degraded to failure before replacement. PM schedule was extended after prior CAPA but no inspection technique improvement was implemented.',
     'Incident', 'INC-2024-0601', 1, 2, 'High', 'High', 'Closed', '2024-09-01', 'Corrective', '2024-09-15', 11, 6),
    (29, 'OC-001 Wire Rope Management Failure — Fourth Documented Occurrence',
     'Fourth recorded wire rope failure on OC-001. PM schedule revision from prior CAPA not enforced. Actions from two prior CAPAs confirmed failed at effectiveness check.',
     'Incident', 'INC-2025-0110', 1, 2, 'High', 'High', 'Closed', '2025-04-10', 'Corrective', '2025-04-20', 11, 6),
    (30, 'OC-001 Crane Wire Rope Management System Overhaul — Active CAPA',
     'Comprehensive overhaul of OC-001 wire rope inspection and replacement programme following four recurrence events. Condition-based monitoring programme being implemented.',
     'Incident', 'INC-2025-0915', 1, 2, 'High', 'High', 'Open', '2026-01-15', 'Corrective and Preventive', None, 11, 6),
    (31, 'Forklift-Pedestrian Near Miss at Dispatch Bay B — First Occurrence',
     'Forklift drove through pedestrian crossing at Dispatch Bay B without stopping. Operator received verbal warning. No structured training programme for bay-specific controls.',
     'Near Miss', 'NM-2023-0520', 5, 26, 'Medium', 'High', 'Closed', '2023-08-20', 'Corrective', '2023-09-01', 108, 100),
    (32, 'Forklift Near Miss at Pedestrian Zone — Second Occurrence Same Location',
     'Second near miss at same pedestrian crossing within eight months. Classroom training provided after first CAPA included no practical assessment. Behaviour change not verified.',
     'Near Miss', 'NM-2024-0115', 5, 26, 'Medium', 'High', 'Closed', '2024-04-15', 'Corrective', '2024-05-01', 108, 100),
    (33, 'Forklift Reversed Into Pedestrian Walkway — Third Occurrence',
     'Third forklift-pedestrian conflict at the same location in 18 months. Refresher training from second CAPA focused on knowledge recall with no behavioural verification.',
     'Near Miss', 'NM-2024-0810', 5, 26, 'Medium', 'High', 'Closed', '2024-11-10', 'Corrective', '2024-11-20', 108, 100),
    (34, 'Forklift Pedestrian Conflict — Fourth Occurrence Despite Three Prior CAPAs',
     'Fourth near miss at Dispatch Bay B. All prior CAPAs used training as the sole corrective action. Engineering and physical segregation controls were never implemented.',
     'Near Miss', 'NM-2025-0301', 5, 26, 'High', 'High', 'Closed', '2025-06-01', 'Corrective', '2025-06-10', 108, 100),
    (35, 'Forklift Pedestrian Segregation Programme Overhaul — Active CAPA',
     'Physical pedestrian segregation programme replacing training-only approach after four recurrence events. Barrier installation, bay re-zoning, and revised permit system in progress.',
     'Incident', 'INC-2025-1001', 5, 26, 'High', 'High', 'In Progress', '2026-02-01', 'Corrective and Preventive', None, 108, 100),
    (36, 'LTI: Welder Sustains Arc Flash Burns — No Arc Flash Risk Assessment',
     'Welder sustained second-degree burns to face and arms during live panel work. No arc flash barrier erected. Risk assessment did not classify the task as an arc flash hazard.',
     'Incident', 'INC-2024-0814', 8, 44, 'High', 'High', 'Closed', '2024-11-30', 'Corrective and Preventive', '2024-11-25', 180, 181),
    (37, 'LTI: Worker Arm Fracture — Crane Load Swing Without Lift Plan',
     'Worker sustained fractured forearm when suspended load swung unexpectedly. Lift plan was absent. Exclusion zone was not established before the lift began.',
     'Incident', 'INC-2025-0211', 1, 2, 'High', 'High', 'Closed', '2025-05-31', 'Corrective and Preventive', '2025-05-20', 11, 12),
    (38, 'LTI: Worker Struck by Reversing Excavator on Construction Site',
     'Worker struck by reversing excavator in an uncontrolled exclusion zone. Banksman was not in position during the reverse manoeuvre. Outcome: fractured leg, 14 lost-time days.',
     'Incident', 'INC-2025-0406', 9, 51, 'High', 'High', 'Open', '2025-10-31', 'Corrective and Preventive', None, 206, 213),
    (39, 'ISO 45001 Internal Audit Finds Management Review Not Documented',
     'Corporate ISO 45001 audit found that the annual management review had been conducted informally with no agenda, attendance record, output actions, or signed minutes retained.',
     'Audit', 'AUD-2025-0210', 11, 61, 'Medium', 'Medium', 'Closed', '2025-07-31', 'Corrective and Preventive', '2025-07-20', 234, 234),
    (40, 'NCR: CAPA Closure Rate Below 80 Percent — Customer Audit Finding',
     'Customer audit found only 67 percent of open CAPAs closed within target dates over the past 12 months. No escalation process was in operation for overdue items.',
     'NCR', 'NCR-2025-0115', 4, 22, 'Medium', 'Medium', 'Closed', '2025-05-31', 'Corrective', '2025-05-15', 82, 72),
]

# (root_cause_id, capa_id, root_cause_statement, rca_method, root_cause_category,
#  contributing_factors, failed_controls, missing_controls)
ROOT_CAUSES_SRC = [
    (1, 1, 'The PM programme for OC-001 specified visual inspection only. No bore gauge method or ISO 4309 discard criteria were defined, allowing internal fatigue strand failure to go undetected.', '5 Why Analysis', 'Equipment Fault',
     ['Wire rope inspection limited to visual check only', 'No internal core inspection in PM schedule', '30-day interval too long for load cycle frequency'],
     ['Monthly visual inspection', 'Pre-use operator check'],
     ['ISO 4309 discard criteria in PM card', 'Bore gauge inspection requirement']),
    (2, 2, 'The CNC spindle brake clearance check was absent from the PM procedure. Brake pad wear exceeded manufacturer tolerance undetected across multiple PM cycles.', '5 Why Analysis', 'Equipment Fault',
     ['PM procedure omitted brake clearance check', 'No post-tool-change brake functional test', 'Technician not trained on spindle brake adjustment'],
     ['Pre-use machine check', 'PM brake inspection'],
     ['Brake clearance specification in PM', 'Post-maintenance functional test requirement']),
    (3, 3, 'The HVAC planned maintenance schedule did not include a refrigerant charge inspection for chiller units. No redundant cooling capacity was available for the critical clean room.', 'Incident Report Review', 'Equipment Fault', None, None, None),
    (4, 4, 'The pressure vessel inspection programme did not account for accelerated corrosion following a process change 18 months prior. Inspection scope was not updated after the change.', 'Fault Tree Analysis', 'Equipment Fault',
     ['Process change not linked to updated inspection scope', 'Ultrasonic thickness gauging not specified for affected zone', 'Inspection interval unchanged after process change'],
     ['Five-year statutory inspection', 'Corrosion inhibitor programme'],
     ['Post-process-change inspection scope review', 'Localised ultrasonic scan requirement']),
    (5, 5, 'The forklift hydraulic hose replacement schedule used a fixed calendar interval that did not account for elevated wear rates caused by high ambient temperatures at Coimbatore.', 'Incident Report Review', 'Equipment Fault', None, None, None),
    (6, 6, 'The site pedestrian-vehicle segregation training programme used generic content not specific to the dispatch bay layout. No post-training practical competency assessment was conducted.', '5 Why Analysis', 'Training Gap',
     ['Generic training not site-specific', 'No practical competency assessment', 'New operator inducted during peak season under reduced supervision'],
     ['Operator induction training', 'Pedestrian crossing signage'],
     ['Site-specific segregation training module', 'Practical assessment for forklift operators']),
    (7, 7, 'No task-specific manual handling training was in place for warehouse pickers. Induction covered generic theory only with no pallet stacking task instruction.', 'Incident Report Review', 'Training Gap', None, None, None),
    (8, 8, 'The PTW authoriser role was assigned to all shift supervisors without verifying that each supervisor held the required hot work authoriser training and competency.', 'Direct Cause Identification', 'Training Gap', None, None, None),
    (9, 9, 'The subcontractor induction checklist did not require verification of CISRS card type before allowing operatives to erect scaffolding. Card type was assumed from job title rather than verified.', '5 Why Analysis', 'Training Gap',
     ['Induction checklist omitted scaffold card type verification', 'No copy of CISRS card retained on site', 'Subcontractor sent uncertified operative without disclosure'],
     ['Contractor induction checklist', 'Scaffold inspection sign-off'],
     ['CISRS card type verification at induction', 'Scaffolding competency matrix']),
    (10, 10, 'Chemical reagent drums used visually similar labels with no colour-coding differentiation. Operator training addressed generic hazard communication but not label disambiguation for this chemical group.', '5 Why Analysis', 'Human Error',
     ['Labels visually similar in colour and font', 'Training did not cover label differentiation', 'Similar drums stored adjacent to each other'],
     ['Goods receipt label check', 'Pre-use visual inspection'],
     ['Label differentiation procedure for similar chemicals', 'Drum layout segregation standard']),
    (11, 11, 'The chemical substitution approval process had no mandatory COSHH reassessment gate. The EHS team was not included in the substitution approval workflow.', '5 Why Analysis', 'Process Failure',
     ['Substitution approval form had no COSHH update gate', 'EHS excluded from substitution workflow', 'No chemical change management process'],
     ['Chemical substitution approval form', 'EHS review gate'],
     ['COSHH update requirement in substitution process', 'EHS sign-off for chemical changes']),
    (12, 12, 'The non-conformance procedure did not specify that a formal deviation approval was required before release of components with dimensional deviations. Supervisors were releasing on personal authority.', 'Incident Report Review', 'Management System Weakness', None, None, None),
    (13, 13, 'The quality hold process allowed supervisor override at dispatch without requiring second-level authorisation or recording the override rationale. The control had a single point of failure.', 'Direct Cause Identification', 'Process Failure', None, None, None),
    (14, 14, 'The MOC procedure was not communicated to operations supervisors as a mandatory requirement for temporary modifications. The boundary between a temporary measure and a formal change was undefined.', 'Fault Tree Analysis', 'Management System Weakness',
     ['MOC classified as engineering-only responsibility', 'Operations supervisors unaware of their MOC obligation', 'No temporary modification register visible to non-engineering staff'],
     ['Pre-work safety review', 'Engineering approval for modifications'],
     ['MOC applicability guidance for operations staff', 'Temporary modification register']),
    (15, 15, 'The Group EHS Policy distribution process relied on site managers self-registering receipt. No push-distribution mechanism or acknowledgement tracking was in place for new manager onboarding.', 'Direct Cause Identification', 'Management System Weakness', None, None, None),
    (16, 16, 'LEV ductwork joints in the degreasing booth used push-fit connections subject to vibration-induced separation. Post-maintenance re-test was limited to flow measurement with no duct integrity check.', '5 Why Analysis', 'Engineering Control Gap',
     ['Push-fit duct connections susceptible to vibration', 'Post-maintenance re-test limited to flow measurement', 'No duct integrity check in maintenance sign-off'],
     ['Post-maintenance LEV performance test', 'Periodic LEV thorough examination'],
     ['Duct joint integrity check in post-maintenance protocol', 'Secure ductwork joint specification']),
    (17, 17, 'The flange inspection programme for acid-service pipework used a uniform calendar interval. No corrosion rate calculation was performed to assign differentiated intervals based on service severity.', 'Fault Tree Analysis', 'Engineering Control Gap',
     ['Uniform inspection interval not adjusted for corrosion severity', 'CUI not assessed for this line', 'Prior inspection recorded marginal acceptance without scheduling early re-inspection'],
     ['Annual flange visual inspection', 'Process line pressure test'],
     ['Corrosion rate-based inspection interval calculation', 'CUI assessment for acid service piping']),
    (18, 18, 'The drum decanting SOP did not specify the requirement to earth bond the drum and receiving vessel before opening the drum valve. This step was treated as optional by operators.', 'Incident Report Review', 'Process Failure', None, None, None),
    (19, 19, 'The nitrogen purge sequence for Reactor R-006 did not require a continuous oxygen monitoring interlock to prevent vessel entry until the atmosphere was confirmed safe. Entry was controlled by procedure only.', 'Direct Cause Identification', 'Engineering Control Gap', None, None, None),
    (20, 20, 'Secondary containment for Tank Farm A predated the largest vessel installation and was never recalculated after the capacity upgrade. No periodic bund capacity verification was in the maintenance programme.', 'Bow-Tie Analysis', 'Engineering Control Gap',
     ['Bund designed to pre-upgrade vessel inventory', 'MOC process did not require bund capacity recalculation', 'No periodic bund capacity audit'],
     ['Secondary containment bund', 'Annual insurance inspection'],
     ['Post-MOC bund capacity calculation requirement', 'Periodic bund capacity audit procedure']),
    (21, 21, 'The annual fire extinguisher service was managed by a single contractor whose appointment lapsed without a renewal alert. No internal due-date tracking existed for legally-required contractor services.', '5 Why Analysis', 'Missing Inspection',
     ['Contractor appointment renewal not calendar-tracked', 'No internal due-date reminder for contractor services', 'Responsible person changed roles without formal handover'],
     ['Annual contractor service', 'Monthly extinguisher inspection'],
     ['Contractor service due-date tracking system', 'Inspection calendar with automated alerts']),
    (22, 22, 'The daily fire escape route inspection checklist did not include a check for clear floor path to emergency exits. Pallet placement by operations staff was not classified as an obstruction risk.', 'Incident Report Review', 'Missing Inspection', None, None, None),
    (23, 23, 'The emergency lighting battery replacement programme used a fixed 5-year cycle that did not account for shorter battery service life in high-ambient-temperature areas of the electronics plant.', '5 Why Analysis', 'Engineering Control Gap',
     ['Uniform battery replacement cycle not adjusted for ambient temperature', 'Annual duration test only — monthly 30-second tests not performed', 'Maintenance contractor not informed of high-temperature zones'],
     ['Annual duration test', '5-year battery replacement programme'],
     ['Temperature-adjusted battery replacement interval', 'Monthly 30-second battery function test']),
    (24, 24, 'The sprinkler maintenance schedule was in a paper logbook not reviewed during a responsible-person handover. The quarterly test fell due during a period when no named responsible person was in post.', 'Direct Cause Identification', 'Missing Inspection', None, None, None),
    (25, 25, 'The hot works permit did not require re-erection of emergency assembly point signage before permit closure. The construction method statement did not identify assembly point visibility as a works requirement.', 'Incident Report Review', 'Missing Inspection', None, None, None),
    (26, 26, 'Wire rope inspection was performed visually only. Training-only corrective action provided as sole remedy did not address the absence of a technical inspection standard for internal rope condition.', 'Direct Cause Identification', 'Equipment Fault', None, None, None),
    (27, 27, 'Training-only corrective action from prior CAPA did not change inspection method or interval. No reduction in degradation rate was achieved. Absence of discard criteria remained unaddressed.', 'Direct Cause Identification', 'Equipment Fault', None, None, None),
    (28, 28, 'PM interval shortened from 30 to 21 days but no inspection technique improvement was made. Discard criteria still absent. Prior CAPA actions recorded as ineffective at effectiveness check.', 'Incident Report Review', 'Equipment Fault',
     ['PM interval shortened but inspection method unchanged', 'No discard criteria defined', 'Effectiveness check confirmed no improvement in inspection quality'],
     None, None),
    (29, 29, 'Fourth occurrence confirms systemic failure of corrective programme. Inspection technique, discard criteria, and PM frequency each addressed in isolation across prior CAPAs but never as an integrated system.', 'Incident Report Review', 'Equipment Fault',
     ['Three prior CAPAs all used single-point actions', 'No systemic root cause analysis conducted', 'Effectiveness checks not passed for any prior CAPA action'],
     None, None),
    (30, 30, 'Fault tree analysis identified absence of condition-based wire rope management as the systemic root cause. Prior CAPAs addressed symptoms without rebuilding the programme to ISO 4309 standard.', 'Fault Tree Analysis', 'Equipment Fault',
     ['No condition-based monitoring system', 'Inspection standard not aligned with ISO 4309', 'Maintenance planner not trained in wire rope inspection criteria'],
     ['Monthly visual inspection', 'Pre-use operator check', 'PM scheduling system'],
     ['ISO 4309-compliant discard criteria', 'Magnetic rope testing protocol', 'Condition-based replacement trigger system']),
    (31, 31, 'Forklift operators received no training specific to the dispatch bay layout. Classroom induction covered generic pedestrian awareness only. No competency test was conducted.', 'Direct Cause Identification', 'Training Gap', None, None, None),
    (32, 32, 'Classroom training delivered after first CAPA but no behavioural competency assessment was conducted. Training records were signed but practical driving behaviour was not observed or verified.', 'Direct Cause Identification', 'Training Gap', None, None, None),
    (33, 33, 'Refresher training from second CAPA focused on knowledge recall rather than behaviour change. No physical controls introduced. Training-only approach proven ineffective across two prior CAPAs.', 'Incident Report Review', 'Training Gap',
     ['Training approach unchanged from prior CAPA', 'No engineering control introduced', 'Effectiveness check relied on training records not observed behaviour'],
     None, None),
    (34, 34, 'Four near misses at the same location confirm training-only actions cannot control this hazard. Root cause is absence of physical pedestrian segregation, not an operator knowledge deficit.', 'Incident Report Review', 'Training Gap',
     ['Physical segregation never implemented despite four incidents', 'Root cause misclassified as training gap in CAPAs 31-33', 'Hierarchy of controls assessment never applied'],
     None, None),
    (35, 35, 'Bow-tie analysis confirmed absence of physical pedestrian segregation as the primary control gap. Training and signage are inadequate as sole controls for a forklift-pedestrian conflict in an active dispatch area.', 'Bow-Tie Analysis', 'Training Gap',
     ['No physical barrier between forklift route and pedestrian walkway', 'Dispatch bay layout never assessed under pedestrian-vehicle segregation standard', 'Four prior CAPAs all used training as sole control'],
     ['Forklift speed limit signage', 'Operator training programme', 'Pedestrian crossing markings'],
     ['Physical pedestrian segregation barriers', 'Forklift-activated warning system at crossing', 'Bay layout redesign to eliminate conflict point']),
    (36, 36, 'The live panel works procedure did not specify arc flash boundary distance or require arc flash PPE. The risk assessment classified the task as low voltage with no arc flash assessment conducted.', 'Fault Tree Analysis', 'Engineering Control Gap',
     ['No arc flash risk assessment for live panel tasks', 'PPE specification limited to insulated gloves only', 'Electrician not trained on NFPA 70E arc flash boundary requirements'],
     ['Live working permit', 'Pre-work PPE check'],
     ['Arc flash risk assessment for all live panel tasks', 'Arc flash boundary specification in live working procedure']),
    (37, 37, 'The crane and lifting procedure did not require a written lift plan for lifts below 500 kg. No exclusion zone establishment requirement existed. Workers approached the load path without restriction.', '5 Why Analysis', 'Engineering Control Gap',
     ['Lift plan threshold set too high', 'No exclusion zone requirement in lift procedure', 'Slinger not trained on exclusion zone responsibilities'],
     ['Crane pre-use check', 'Slinger and banksman qualification'],
     ['Written lift plan requirement for all suspended loads', 'Exclusion zone as mandatory pre-lift step']),
    (38, 38, 'The site traffic management plan did not designate the excavation zone as a plant-exclusion area for pedestrians. Banksman duties were unassigned during the reverse manoeuvre phase of the operation.', 'Direct Cause Identification', 'Management System Weakness', None, None, None),
    (39, 39, 'The ISO 45001 management review procedure specified a review must be conducted annually but did not define minimum outputs, required agenda items, or record format. Reviews were conducted informally.', '5 Why Analysis', 'Management System Weakness',
     ['Procedure specified review requirement but not output format', 'No template or checklist for management review outputs', 'EHS Manager unaware that retained documented information was a certification requirement'],
     ['Annual management review requirement', 'ISO 45001 audit programme'],
     ['Management review output template', 'Documented information retention requirement in procedure']),
    (40, 40, 'No escalation process existed for CAPAs approaching or exceeding their target closure dates. CAPA owners were not prompted when due dates were missed and overdue items had no management visibility.', 'Incident Report Review', 'Management System Weakness', None, None, None),
]

# (action_id, capa_id, action_type, title, description, owner_id, due_date,
#  evidence_required, effectiveness_check, effectiveness_result,
#  effectiveness_verified_at, strength_label, ai_generated)
ACTIONS_SRC = [
    (1, 1, 'Corrective', 'Replace OC-001 Wire Rope and Implement ISO 4309 Inspection Standard',
     'Replace wire rope on OC-001 with manufacturer-specified grade. Update PM card to specify strand count using bore gauge per ISO 4309 Table 6 and define discard criteria before next inspection.',
     6, '2024-05-15', ['Replacement work order signed off', 'Updated PM card with ISO 4309 discard criteria', 'Inspector competency record'],
     'Re-inspect at 30 and 90 days; verify zero broken strands detected before threshold; confirm PM card in use by maintenance team.',
     'Pass', '2024-08-10', 'Strong', False),
    (2, 1, 'Preventive', 'Extend ISO 4309 Discard Criteria to All Site Overhead Cranes',
     'Audit all 4 overhead cranes on the Chennai site against ISO 4309 discard criteria. Update PM cards for all units. Train maintenance technicians on rope bore inspection technique.',
     6, '2024-06-15', ['All crane PM cards updated', 'Maintenance technician training records', 'Crane inspection register updated'],
     'Verify all cranes inspected per new standard at next scheduled PM. Confirm no further wire rope failure events over 6-month period.',
     'Pass', '2024-09-10', 'Strong', False),
    (3, 2, 'Corrective', 'Retrain Machine Operators on Guarding and Equipment Inspection Requirements',
     'Retrain all CNC operators on machine guarding and pre-use inspection requirements.',
     77, '2024-09-30', ['Training attendance record'],
     'Confirm training completed.',
     'Fail', '2024-11-01', 'Weak', False),
    (4, 3, 'Corrective', 'Fix the Chiller Issue',
     'Fix the issue.',
     123, '2025-06-01', [],
     None,
     'Pending', None, 'Critical', False),
    (5, 4, 'Corrective', 'Replace PV-012 Shell Course and Implement Post-Process-Change Inspection Scope Review',
     'Replace corroded shell course section on PV-012. Commission updated inspection scope assessment for all pressure vessels where a process change has occurred in the prior 24 months, assigning localised ultrasonic scan requirements.',
     175, '2024-05-30', ['Shell replacement work order', 'Updated inspection scope assessment report for all affected PVs', 'Next statutory inspection completed and record on file'],
     'Verify PV-012 returned to service with no defects at first follow-up inspection. Confirm updated scope applied to all affected vessels at 60-day review.',
     'Pass', '2024-08-01', 'Strong', False),
    (6, 4, 'Preventive', 'Embed Process-Change to Inspection-Scope Link in MOC Procedure',
     'Update the MOC procedure to require an inspection scope review for any process change that alters fluid chemistry, temperature, or pressure on a pressure system. Brief engineering and EHS teams on the requirement.',
     180, '2024-06-20', ['Revised MOC procedure with inspection scope review gate', 'Engineering team briefing record', 'EHS sign-off on procedure update'],
     'Audit next three MOC closures involving process changes to confirm inspection scope review was triggered and completed.',
     'Pass', '2024-09-20', 'Strong', False),
    (7, 5, 'Corrective', 'Ensure All Operators Inspect Equipment Before Use',
     'Ensure all operators inspect equipment before use.',
     216, '2025-01-31', ['Completion sign-off'],
     'Monitor situation.',
     'Fail', '2025-03-01', 'Weak', False),
    (8, 6, 'Corrective', 'Develop Site-Specific Dispatch Bay Segregation Training with Practical Assessment',
     'Develop a site-specific training module covering the Mumbai Warehouse pedestrian-vehicle segregation layout including the dispatch bay crossing. Include a practical competency assessment. Re-train all forklift operators and record pass/fail.',
     34, '2024-07-15', ['Revised training content covering dispatch bay layout', 'All operator training records with practical assessment sign-off', 'Assessment pass records'],
     'Observe all operators at the dispatch crossing within 14 days of training completion. Re-test any operator with unsafe behaviour observed.',
     'Pass', '2024-09-15', 'Strong', False),
    (9, 6, 'Preventive', 'Install Proximity Warning Alarms on All Forklifts for Pedestrian Zone Entry',
     'Install proximity alarm systems on all 8 forklifts at Mumbai Warehouse to activate an audible alert when approaching designated pedestrian crossings. Test all units before returning to service.',
     34, '2024-08-01', ['Installation certificates for all 8 forklifts', 'Test records confirming alarm activation at pedestrian zone', 'Updated pre-use check form referencing alarm test'],
     'Confirm alarm systems functioning at next three consecutive monthly inspections. Zero bypass incidents over 90-day monitoring period.',
     'Pass', '2024-10-20', 'Strong', False),
    (10, 7, 'Corrective', 'Conduct Refresher Manual Handling Training for All Warehouse Staff',
     'Conduct refresher training on manual handling for all warehouse staff.',
     100, '2025-03-31', ['Training attendance record'],
     'Confirm training completed.',
     'Fail', '2025-04-30', 'Weak', False),
    (11, 8, 'Corrective', 'Ensure Compliance with PTW Authoriser Requirements',
     'Ensure compliance.',
     12, '2025-07-01', [],
     None,
     'Pending', None, 'Critical', False),
    (12, 9, 'Corrective', 'Update Subcontractor Induction to Verify CISRS Card Type Before Work Commences',
     'Update the subcontractor induction checklist to require sighting and recording of CISRS card type before any operative is permitted to erect scaffolding. Retain a copy of the card in the contractor file.',
     213, '2025-06-01', ['Updated induction checklist', 'Completed checklist for current operatives', 'CISRS card copies on file'],
     'Verify updated induction applied to next three new subcontractor operatives. Audit checklist completion records at 60 days.',
     'Pending', None, 'Strong', False),
    (13, 9, 'Preventive', 'Develop Scaffolding Competency Matrix for All AcerTech Construction Sites',
     'Develop a competency matrix listing all scaffold system types used on AcerTech construction sites and the corresponding CISRS card requirements. Include in subcontractor pre-qualification documentation.',
     213, '2025-07-01', ['Competency matrix signed off by Site Manager', 'Matrix distributed to all site managers', 'Pre-qualification questionnaire updated to reference matrix'],
     'Confirm matrix referenced at next two new subcontractor inductions. Zero non-compliant scaffold erection events in the following 6 months.',
     'Pending', None, 'Strong', False),
    (14, 10, 'Corrective', 'Retrain Chemical Production Operators on Reagent Label Reading',
     'Retrain all chemical production operators on reagent label reading.',
     52, '2024-11-01', ['Training attendance record'],
     'Confirm training attended.',
     'Fail', '2024-12-15', 'Weak', False),
    (15, 11, 'Corrective', 'Update COSHH Assessment for Substitute Solvent and Brief Operators Before Return to Work',
     'Commission updated COSHH assessment for the substitute solvent. Update the COSHH register, risk assessment, and operator information sheet. Brief all degreasing area operators before next shift return.',
     52, '2024-05-30', ['Updated COSHH assessment signed by EHS Manager', 'Revised operator information sheet distributed', 'Briefing attendance record'],
     'Verify updated COSHH assessment in use at post-change inspection. Air monitoring results for first 4 weeks to confirm exposure below STEL.',
     'Pass', '2024-07-01', 'Strong', False),
    (16, 11, 'Preventive', 'Embed EHS COSHH Review as Mandatory Gate in Chemical Substitution Approval Process',
     'Revise the chemical substitution approval form to include a mandatory EHS sign-off gate before procurement. Train procurement team on the requirement. Update the chemical management procedure.',
     61, '2024-06-15', ['Revised approval form with EHS gate', 'Procurement team briefing record', 'Updated chemical management procedure'],
     'Audit next three chemical substitution requests to confirm EHS gate triggered and completed before purchase order raised.',
     'Pass', '2024-09-15', 'Strong', False),
    (17, 12, 'Corrective', 'Brief Supervisors on Deviation Approval Process',
     'Brief supervisors on deviation approval process.',
     72, '2024-09-30', ['Briefing attendance record'],
     'Confirm briefing completed.',
     'Fail', '2024-11-01', 'Weak', False),
    (18, 13, 'Corrective', 'Ensure the Quality Hold Process Is Followed',
     'Ensure compliance with quality hold process.',
     118, '2024-12-31', [],
     None,
     'Fail', '2025-01-30', 'Critical', False),
    (19, 14, 'Corrective', 'Re-Issue MOC Procedure to Operations Supervisors with Practical Workshop',
     'Re-issue the MOC procedure to all operations supervisors with a covering memo defining the boundary between routine maintenance and formal change. Conduct a 1-hour workshop with case examples.',
     181, '2024-08-15', ['Distribution record for MOC procedure re-issue', 'Workshop attendance register', 'Completed case study exercise sheets'],
     'Conduct unannounced audit of active temporary modifications within 60 days. Zero unapproved bypasses identified.',
     'Pass', '2024-10-01', 'Strong', False),
    (20, 14, 'Preventive', 'Implement Shared Temporary Modification Register Visible to Engineering and Operations',
     'Implement a shared temporary modification register requiring supervisor sign-off for any temporary bypass. Include in monthly safety review agenda. Archive completed entries for 12 months.',
     181, '2024-09-15', ['Temporary modification register live in system', 'Access demonstrated by operations supervisor', 'Monthly safety review agenda updated'],
     'Verify register in use at 30 and 90 days. Audit that all active modifications appear in register at next site inspection.',
     'Pass', '2024-11-20', 'Strong', False),
    (21, 15, 'Corrective', 'Distribute Group EHS Policy to All Site Managers Without Confirmed Receipt',
     'Distribute Group EHS Policy to all relevant site managers and obtain signed acknowledgement.',
     234, '2025-09-30', ['Distribution record with signed acknowledgements'],
     'Confirm receipt from all four managers.',
     'Pending', None, 'Weak', False),
    (22, 16, 'Corrective', 'Replace LEV Ductwork Joints with Mechanically-Secured Clamps and Re-Test',
     'Replace all push-fit duct connections in the degreasing booth with mechanically-secured clamp connections. Conduct LEV re-test to COSHH Regulations Schedule 4 standard within 5 days of repair.',
     57, '2024-06-15', ['Contractor work order for joint replacement', 'COSHH Reg Schedule 4 LEV re-test report signed by competent person', 'Photo evidence of secured joints'],
     'LEV re-test report to confirm capture velocity meets standard. Air monitoring in booth at 30 days post-repair to confirm vapour below STEL.',
     'Pass', '2024-07-20', 'Strong', False),
    (23, 16, 'Preventive', 'Revise LEV Maintenance Sign-Off to Include Mandatory Duct Integrity Check',
     'Update the LEV maintenance sign-off form to require a visual duct integrity check of joints, seals, and duct runs as a mandatory item. Brief maintenance technicians on the revised requirement before next scheduled service.',
     61, '2024-07-01', ['Revised LEV maintenance sign-off form', 'Technician briefing record', 'Completed sign-off form from next scheduled service'],
     'Audit next two LEV maintenance events to confirm duct integrity check completed and recorded on sign-off form.',
     'Pass', '2024-09-15', 'Strong', False),
    (24, 17, 'Corrective', 'Replace Corroded Flange and Implement Corrosion Rate-Based Inspection Intervals',
     'Replace gasket and flange on PL-007. Commission a corrosion rate calculation for all acid-service flanges on site. Assign differentiated inspection intervals based on corrosion severity class. Schedule highest-severity flanges at 6-monthly intervals.',
     155, '2024-07-15', ['Flange replacement work order', 'Corrosion rate calculation report signed by process engineer', 'Updated inspection schedule for all acid-service flanges'],
     'Confirm all acid-service flanges re-inspected per new interval within 3 months. Zero further flange leaks within 12-month monitoring period.',
     'Pass', '2024-10-01', 'Strong', False),
    (25, 17, 'Preventive', 'Extend CUI Assessment to All Insulated Process Lines at Ahmedabad',
     'Scope all insulated process lines at the Ahmedabad site for CUI risk. Assign inspection intervals based on service environment and insulation type. Document in the process plant inspection register.',
     155, '2024-08-15', ['CUI risk assessment for all insulated lines', 'Updated process plant inspection register', 'Risk-based inspection intervals approved by Site Engineer'],
     'Verify CUI assessments completed for all lines. Confirm highest-risk lines scheduled for first inspection within 6 months.',
     'Pass', '2024-11-01', 'Strong', False),
    (26, 18, 'Corrective', 'Remind Operators About Importance of Earth Bonding During Decanting',
     'Discuss earth bonding requirements with operators.',
     150, '2024-11-01', ['Toolbox talk record'],
     'Confirm discussion held.',
     'Fail', '2024-12-31', 'Weak', False),
    (27, 19, 'Corrective', 'Address the Nitrogen Purge System Fault on R-006',
     'Fix the issue.',
     155, '2025-07-01', [],
     None,
     'Pending', None, 'Critical', False),
    (28, 20, 'Corrective', 'Redesign Tank Farm A Secondary Containment to Achieve 110 Percent Capacity',
     'Engage structural engineer to redesign bund for Tank Farm A to achieve net capacity of not less than 110 percent of the largest vessel plus 10 percent freeboard. Obtain permitting approval before construction begins.',
     155, '2025-07-15', ['Structural engineer design report', 'Building permit or permitting authority approval', 'As-built drawing with capacity calculation'],
     'Engineer to certify completed bund meets 110 percent minimum. Insurance inspection to re-assess bund rating after construction.',
     'Pending', None, 'Strong', False),
    (29, 20, 'Preventive', 'Include Bund Capacity Verification in MOC Closure Checklist for All Future Vessel Installations',
     'Update the MOC closure checklist to require a bund capacity recalculation as a mandatory sign-off item for any new or modified vessel in secondary containment areas. Communicate change to engineering and EHS teams.',
     159, '2025-06-01', ['Updated MOC closure checklist', 'Engineering team briefing record', 'EHS procedure updated to reference bund capacity check'],
     'Audit next two MOC closures involving vessel changes to confirm bund capacity calculation was completed and signed off.',
     'Pending', None, 'Strong', False),
    (30, 21, 'Corrective', 'Complete Overdue Service and Implement Automated Due-Date Tracking for Contractor Services',
     'Arrange emergency service of all 6 overdue extinguishers within 5 working days. Implement a calendar-based contractor service due-date tracker with automated email alert 30 days before expiry. Assign a named deputy responsible person as backup.',
     11, '2024-08-01', ['Contractor service certificates for all units', 'Screenshot of due-date tracker with automated alert configured', 'Named backup responsible person recorded in tracker'],
     'Confirm all extinguishers serviced and tracker active within 30 days. Verify no further overdue extinguishers at next monthly inspection.',
     'Pass', '2024-09-20', 'Strong', False),
    (31, 21, 'Preventive', 'Extend Due-Date Tracking to All Legally-Required Inspection Activities on Site',
     'Audit all legally-required inspection activities — fire extinguishers, LEV, electrical, lifting equipment, PRVs — and add each to the due-date tracking system. Review completeness of tracker at next monthly EHS review.',
     11, '2024-09-01', ['Complete inspection due-date register', 'Monthly EHS review minutes confirming tracker reviewed', 'No overdue items at first tracker review'],
     'Zero overdue statutory inspections at 30 and 90-day review. Tracker to be audited at next ISO 45001 internal audit.',
     'Pass', '2024-11-01', 'Strong', False),
    (32, 22, 'Corrective', 'Remove Pallets from Emergency Exits and Remind Staff',
     'Remove pallets from emergency exits and remind staff not to block exits.',
     30, '2024-09-30', ['Completion sign-off'],
     'Confirm exits clear.',
     'Fail', '2024-11-01', 'Weak', False),
    (33, 23, 'Corrective', 'Replace Failed Batteries and Implement Monthly 30-Second Function Tests',
     'Replace batteries in all 14 failed emergency lighting fittings within 10 working days. Implement monthly 30-second function tests for all fittings as required by BS 5266 Part 1. Assign a named responsible person for each floor zone.',
     128, '2025-05-31', ['Battery replacement records for all 14 fittings', 'Monthly test logbook in use', 'Named zone responsible persons recorded'],
     'Annual duration test at 12 months to confirm 100 percent pass rate. Monthly test records to show zero missed tests.',
     'Pending', None, 'Strong', False),
    (34, 23, 'Preventive', 'Revise Battery Replacement Programme to Use Temperature-Adjusted Intervals',
     'Identify all emergency lighting zones with ambient temperature above 25 C. Reduce battery replacement interval to 3 years for these zones. Update the maintenance schedule and instruct the contractor.',
     128, '2025-07-01', ['Temperature survey for all emergency lighting zones', 'Updated maintenance schedule with temperature-adjusted intervals', 'Contractor briefed and schedule accepted'],
     'Confirm temperature-adjusted replacements completed for affected zones within programme timeline. No battery failures at next annual duration test.',
     'Pending', None, 'Strong', False),
    (35, 24, 'Corrective', 'Update Records and Complete Overdue Test',
     'Update records.',
     175, '2025-07-01', [],
     None,
     'Pending', None, 'Critical', False),
    (36, 25, 'Corrective', 'Reinstall Assembly Point Signs and Monitor Site',
     'Monitor the situation.',
     213, '2025-06-01', ['Completion sign-off'],
     'Confirm signs in place.',
     'Fail', '2025-08-05', 'Weak', False),
    (37, 26, 'Corrective', 'Train the Team on Wire Rope Inspection',
     'Train the team.',
     6, '2023-06-10', [],
     None,
     'Fail', '2023-07-15', 'Critical', False),
    (38, 27, 'Corrective', 'Discuss Wire Rope Issue with Maintenance Supervisor',
     'Discuss with supervisor.',
     6, '2024-02-05', [],
     None,
     'Fail', '2024-03-10', 'Critical', False),
    (39, 28, 'Corrective', 'Shorten PM Interval and Remind Inspectors to Be More Thorough',
     'Shorten PM interval and remind inspection team to be more thorough.',
     6, '2024-09-01', ['Updated PM schedule'],
     'Confirm schedule updated.',
     'Fail', '2024-10-15', 'Weak', False),
    (40, 29, 'Corrective', 'Conduct Refresher Training on Wire Rope Inspection',
     'Conduct refresher training for maintenance technicians on wire rope inspection.',
     6, '2025-04-10', ['Training attendance record'],
     'Confirm training completed.',
     'Fail', '2025-05-20', 'Weak', False),
    (41, 30, 'Containment', 'Remove OC-001 from Service Pending Full ISO 4309 Inspection',
     'Remove OC-001 from service immediately. Conduct full wire rope inspection per ISO 4309 using bore inspection gauge. Confirm safe condition in writing before returning to service. Arrange hire crane as interim replacement.',
     6, '2025-10-01', ['Out-of-service tag applied and photographed', 'ISO 4309 bore inspection report signed by competent person', 'Hire crane booking confirmation'],
     'Wire rope bore inspection completed and signed off before crane returns to service.',
     'Pending', None, 'Strong', False),
    (42, 30, 'Corrective', 'Implement ISO 4309-Compliant Condition-Based Wire Rope Management Programme',
     'Develop and implement a wire rope management programme for all site overhead cranes aligned to ISO 4309. Define discard criteria, inspection method including bore gauge, and frequency. Train maintenance technicians. Link PM cards to programme.',
     6, '2026-01-01', ['Wire rope management procedure signed off', 'All crane PM cards updated to ISO 4309 standard', 'Technician training records for bore inspection', 'Updated PM schedule in CMMS'],
     'Audit PM records at 90 days to confirm bore inspections completed at correct frequency. Zero wire rope failures on site in 12-month monitoring period.',
     'Pending', None, 'Strong', False),
    (43, 30, 'Preventive', 'Install Magnetic Rope Testing Sensor on Two Highest-Utilisation Cranes',
     'Install a permanent magnetic rope testing sensor on the two highest-utilisation overhead cranes including OC-001. Configure sensor to trigger maintenance alert at 10 percent cross-section loss threshold.',
     23, '2026-01-15', ['MRT sensor installation certificate for each crane', 'Sensor alert threshold configuration report', 'Maintenance team trained on alert response procedure'],
     'Confirm MRT sensors generating data at 30 days. Review alert history at 3 and 6 months to confirm early detection capability.',
     'Pending', None, 'Strong', False),
    (44, 31, 'Corrective', 'Train Forklift Operators on Pedestrian Awareness',
     'Train the team.',
     100, '2023-08-20', [],
     None,
     'Fail', '2023-10-01', 'Critical', False),
    (45, 32, 'Corrective', 'Ensure Compliance with Pedestrian Segregation Rules',
     'Ensure compliance with pedestrian segregation rules.',
     100, '2024-04-15', [],
     None,
     'Fail', '2024-06-01', 'Critical', False),
    (46, 33, 'Corrective', 'Retrain Operators and Issue Formal Warning Notices',
     'Retrain all forklift operators on pedestrian awareness and issue formal warning notices to operators involved in incidents.',
     100, '2024-11-10', ['Training attendance record', 'Warning notice records'],
     'Confirm training completed and warnings issued.',
     'Fail', '2024-12-15', 'Weak', False),
    (47, 34, 'Corrective', 'Conduct Refresher Training and Update Crossing Signage',
     'Conduct refresher training on pedestrian safety and update crossing signage at dispatch bay.',
     100, '2025-06-01', ['Training record', 'Photo of updated signage'],
     'Confirm training and signage completed.',
     'Fail', '2025-07-01', 'Weak', False),
    (48, 35, 'Corrective', 'Install Physical Pedestrian Segregation Barriers at Dispatch Bay B',
     'Install Armco-type physical pedestrian segregation barriers along the full forklift route through Dispatch Bay B. Create a single designated pedestrian crossing with drop kerb and tactile paving. Conduct risk assessment for revised layout before reopening.',
     100, '2025-12-01', ['Barrier installation completion sign-off', 'Post-installation risk assessment', 'Photo evidence of completed barriers and crossing'],
     'Observe pedestrian and forklift behaviour at new crossing for 4 consecutive weeks. Zero crossings outside designated point. Re-assess risk at 3 months.',
     'Pending', None, 'Strong', False),
    (49, 35, 'Preventive', 'Audit All AcerTech Warehouse Sites for Pedestrian-Vehicle Conflict Points',
     'Conduct a pedestrian-vehicle conflict point audit at all 3 AcerTech warehouse sites. Apply the hierarchy of controls assessment to each identified conflict point. Submit findings to Group EHS Manager within 60 days.',
     108, '2026-01-15', ['Completed audit report for all 3 warehouse sites', 'Hierarchy of controls assessment for each conflict point', 'Findings submitted to Group EHS Manager'],
     'Confirm engineering controls proposed for all high-risk conflict points. Verify implementation timelines included in site CAPAs.',
     'Pending', None, 'Strong', False),
    (50, 35, 'Risk Mitigation', 'Install Forklift-Activated Warning Lights at All Pedestrian Crossings in Delhi DC',
     'Install a forklift-proximity warning light system at all four pedestrian crossings in the Delhi Distribution Center. System to activate a flashing amber beacon visible from 20 m when a forklift approaches within 5 m of the crossing.',
     104, '2026-02-01', ['Installation certificates for all 4 crossings', 'Activation test records', 'Pre-use check updated to include light function test'],
     'Confirm lights functioning at all crossings at monthly inspection for 6 consecutive months. Review near miss register for any pedestrian crossing events.',
     'Pending', None, 'Strong', False),
    (51, 36, 'Corrective', 'Commission Arc Flash Risk Assessment for All Live Panel Work Locations',
     'Commission arc flash risk assessment for all identified live panel work locations at Kolkata plant. Specify NFPA 70E-compliant PPE requirements for each task and boundary distances. Brief all electricians before live work resumes.',
     181, '2024-10-15', ['Arc flash risk assessment signed by electrical engineer', 'PPE specification for all live panel tasks', 'Electrician briefing attendance record'],
     'Audit next 3 live panel work events to confirm arc flash assessment referenced and correct PPE worn. Zero arc flash incidents in 12-month monitoring period.',
     'Pass', '2024-12-01', 'Strong', False),
    (52, 36, 'Preventive', 'Update Live Working Procedure to Mandate Arc Flash Boundary Establishment',
     'Revise the site live working procedure to require arc flash boundary establishment as a mandatory pre-work step for any live panel task. Include in the live working permit checklist. Train all permit issuers and performers.',
     181, '2024-11-01', ['Revised live working procedure', 'Updated permit checklist', 'Permit issuer training records'],
     'Verify arc flash boundary referenced on next 5 live working permits issued. Confirm procedure in use at next ISO 45001 internal audit.',
     'Pass', '2024-12-20', 'Strong', False),
    (53, 37, 'Corrective', 'Implement Written Lift Plan Requirement for All Lifts Above 250 kg',
     'Revise the crane and lifting procedure to require a written lift plan including load path, exclusion zone, appointed person sign-off, and emergency plan for all lifts above 250 kg. Train appointed persons and crane operators on the revised requirement.',
     12, '2025-03-15', ['Revised lifting procedure signed off', 'Lift plan template distributed to all appointed persons', 'Appointed person training records'],
     'Audit next 5 lifts above 250 kg to confirm written lift plan completed and exclusion zone established. Zero near misses from load swing in 6-month monitoring period.',
     'Pass', '2025-06-01', 'Strong', False),
    (54, 37, 'Preventive', 'Standardise Lift Plan Template and Distribute to All AcerTech Manufacturing Sites',
     'Develop a standardised lift plan template covering load weight confirmation, lift path assessment, exclusion zone method, equipment rating check, and emergency de-rigging plan. Distribute to all manufacturing site EHS managers.',
     11, '2025-04-01', ['Lift plan template finalised and approved by Group EHS', 'Template distributed to all manufacturing site EHS managers', 'Group lifting procedure updated to reference template'],
     'Confirm template adopted at minimum 3 manufacturing sites at 90-day review. Template to be referenced in next group EHS audit checklist.',
     'Pass', '2025-06-15', 'Strong', False),
    (55, 38, 'Corrective', 'Address the Traffic Management Issue on Site',
     'Fix the issue.',
     213, '2025-08-01', [],
     None,
     'Pending', None, 'Critical', False),
    (56, 39, 'Corrective', 'Revise Management Review Procedure to Define Minimum Outputs and Record Format',
     'Update the ISO 45001 management review procedure to define minimum agenda items, required documented outputs, and record retention period. Conduct a retrospective structured management review to produce a compliant record for the current year.',
     234, '2025-05-31', ['Revised management review procedure signed off', 'Completed management review record for current year', 'Agenda template and output checklist in use'],
     'Next management review to be conducted using new template. External certification auditor to confirm compliance at next surveillance audit.',
     'Pass', '2025-07-25', 'Strong', False),
    (57, 39, 'Preventive', 'Add Management Review Checklist to Annual ISO 45001 Internal Audit Programme',
     'Add a checklist item to the ISO 45001 internal audit programme to verify management review outputs against the minimum requirement defined in the revised procedure. Audit to be conducted annually in Q1 before the external surveillance audit.',
     234, '2025-06-30', ['Updated internal audit programme with management review checklist item', 'Audit schedule confirmed for next cycle'],
     'Confirm management review checklist item appears in next internal audit report. External audit result to confirm no non-conformity against Clause 9.3.',
     'Pass', '2025-07-25', 'Strong', False),
    (58, 40, 'Corrective', 'Review All Overdue CAPAs and Update Records',
     'Review all overdue CAPAs and update records.',
     72, '2025-04-30', ['Updated CAPA log'],
     'Confirm records updated.',
     'Fail', '2025-05-20', 'Weak', False),
]

# =============================================================================
# Mapping dicts — minted master IDs (we mint our own; not reading real Oracle
# masters yet, see phase1.md "Master values" decision).
# =============================================================================

# capas.severity / capas.priority values -> (mirror ID, numeric level for severity)
SEVERITY_MAP = {
    "Informational": ("SEV_INFORMATIONAL", 1),
    "Low": ("SEV_LOW", 2),
    "Medium": ("SEV_MEDIUM", 3),
    "High": ("SEV_HIGH", 4),
    "Critical": ("SEV_CRITICAL", 5),
}

PRIORITY_MAP = {
    "Informational": "PRI_INFORMATIONAL",
    "Low": "PRI_LOW",
    "Medium": "PRI_MEDIUM",
    "High": "PRI_HIGH",
    "Critical": "PRI_CRITICAL",
}

# CAPA.STATUS_ID (CAPA_STATUS_MASTER, SOURCE_TABLE='CAPA')
STATUS_MAP = {
    "Open": "STATUS_OPEN",
    "In Progress": "STATUS_IN_PROGRESS",
    "Closed": "STATUS_CLOSED",
    "Cancelled": "STATUS_CANCELLED",
}

# CAPA_ACTIONS.STATUS_ID (CAPA_STATUS_MASTER, SOURCE_TABLE='CAPA_ACTIONS') — the
# source schema has no per-action status column, so action status is derived
# from the parent CAPA's status (see phase1.md derivation rules).
ACTION_STATUS_MAP = {
    "Open": "ACTION_STATUS_OPEN",
    "In Progress": "ACTION_STATUS_IN_PROGRESS",
    "Closed": "ACTION_STATUS_CLOSED",
    "Cancelled": "ACTION_STATUS_CANCELLED",
}

# capas.capa_type / capa_actions.action_type values -> CAPA_TYPE_MASTER ID.
# "Corrective and Preventive" is a composite CAPA-level label with no single
# FK target in the real schema (CAPA.CAPA_TYPE_ID is singular) — collapsed to
# its primary/first-listed type, Corrective.
CAPA_TYPE_MAP = {
    "Containment": "TYPE_CONTAINMENT",
    "Corrective": "TYPE_CORRECTIVE",
    "Preventive": "TYPE_PREVENTIVE",
    "Risk Mitigation": "TYPE_RISK_MITIGATION",
    "Corrective and Preventive": "TYPE_CORRECTIVE",
}

# root_cause_taxonomy.category_name -> CAPA_CATEGORIES.CATEGORY_ID
CATEGORY_MAP = {
    "Equipment Fault": "CAT_EQUIPMENT_FAULT",
    "Training Gap": "CAT_TRAINING_GAP",
    "Process Failure": "CAT_PROCESS_FAILURE",
    "Missing Inspection": "CAT_MISSING_INSPECTION",
    "Engineering Control Gap": "CAT_ENGINEERING_CONTROL_GAP",
    "Management System Weakness": "CAT_MANAGEMENT_SYSTEM_WEAKNESS",
    "Human Error": "CAT_HUMAN_ERROR",
    "Environmental Factor": "CAT_ENVIRONMENTAL_FACTOR",
}

# --- Generic descriptions for master/lookup rows ---
# These columns exist in schema.sql but were left NULL in the first seed pass.
# Filled now so the Context Retrieval Agent has human-readable semantics to
# inject per master value (severity/priority/type/category meaning), not bare
# IDs. Severity/priority text is deliberately generic (tenant-agnostic); the
# category/type text describes the controlled-vocab term itself.
SEVERITY_DESC = {
    "Informational": "No safety, compliance, or operational impact; logged for awareness and trend analysis only.",
    "Low": "Minor, localized impact that is easily controlled with no regulatory exposure; routine handling.",
    "Medium": "Moderate impact — potential for injury, limited downtime, or a minor compliance gap; prompt action required.",
    "High": "Major impact — serious injury potential, significant downtime, or a regulatory breach; expedited action and management oversight.",
    "Critical": "Severe/catastrophic impact — fatality potential, major loss, or statutory violation; immediate containment and executive escalation.",
}

PRIORITY_DESC = {
    "Informational": "No action deadline; tracked for visibility only.",
    "Low": "Address within normal work scheduling; no expedited handling.",
    "Medium": "Schedule within the standard SLA; routine priority queue.",
    "High": "Expedite ahead of routine work; tighter SLA and active follow-up.",
    "Critical": "Drop-everything priority; immediate assignment and continuous tracking.",
}

# Keyed by minted CAPA_TYPE_MASTER ID (multiple source names collapse to one id).
CAPA_TYPE_DESC = {
    "TYPE_CONTAINMENT": "Immediate interim action to limit or stop the impact of a problem before the root cause is addressed.",
    "TYPE_CORRECTIVE": "Action that eliminates the root cause of a detected nonconformity to prevent its recurrence.",
    "TYPE_PREVENTIVE": "Action that eliminates the cause of a potential nonconformity to prevent its occurrence.",
    "TYPE_RISK_MITIGATION": "Action that reduces the likelihood or consequence of an identified risk that has not yet materialized.",
}

# Keyed by root_cause_taxonomy category name (the CAPA_CATEGORIES controlled vocab).
CATEGORY_DESC = {
    "Equipment Fault": "Failure or malfunction of plant, machinery, or equipment due to wear, defect, or inadequate maintenance.",
    "Training Gap": "Incident or nonconformity arising from missing, incomplete, or unverified competency/training.",
    "Process Failure": "Breakdown in a defined procedure or workflow — steps skipped, controls bypassed, or the process not followed.",
    "Missing Inspection": "A required inspection, test, or verification was overdue, skipped, or not recorded.",
    "Engineering Control Gap": "Absent or inadequate engineered safeguard (guarding, ventilation, containment, interlock).",
    "Management System Weakness": "Deficiency in the governing system — policy, MOC, document control, oversight, or accountability.",
    "Human Error": "Action slip, lapse, or mistake by an individual despite adequate systems and training.",
    "Environmental Factor": "Contributing conditions from the working environment (weather, lighting, temperature, housekeeping).",
}

# Per-site description, keyed by source site number. Stored in MSTR_TENANT_SITES.META
# (no dedicated SITE_DESCRIPTION column in the real Oracle schema — META is the
# faithful home for free-text site context the Context Agent can inject).
SITE_DESC = {
    1: "Heavy fabrication and assembly plant; overhead cranes, hot work, and machine-guarding hazards dominate.",
    2: "Central distribution warehouse; forklift-pedestrian conflict and racking/manual-handling hazards.",
    3: "Chemical blending and packaging unit; vapour exposure, flammable liquids, and process-safety hazards.",
    4: "CNC machining and finishing plant; machine guarding, coolant exposure, and noise hazards.",
    5: "High-throughput logistics hub; forklift-pedestrian hazards and shift-fatigue risk.",
    6: "PCB assembly and electronics test; solder fume, ESD, and clean-room environmental controls.",
    7: "Bulk chemical transfer and storage; PSM, vapour-cloud, pressure-system, and HAZMAT hazards.",
    8: "Structural steel fabrication and pressure-vessel work; hot work, heavy lifting, and confined-space hazards.",
    9: "Active civil construction site; working at heights, excavation, mobile plant, and subcontractor oversight.",
    10: "Regional warehouse; forklift, racking-integrity, and manual-handling hazards.",
    11: "Group corporate office; EHS governance, training oversight, and office/evacuation hazards.",
}

# MSTR_STATUS_MASTER is generic/tenant-agnostic; tenant/site/group/user rows
# all just need *a* STATUS_ID value (no FK constraint ties them to this table)
# — mint one shared "active" row so the table isn't empty and the value is
# self-documenting rather than a bare string.
GENERIC_ACTIVE_STATUS_ID = "STATUS_ACTIVE"

# effectiveness_result -> CAPA_REVIEWS.REVIEW_OUTCOME
REVIEW_OUTCOME_MAP = {
    "Pass": "Effective",
    "Fail": "Ineffective",
    "Pending": "Pending Review",
}

# --- Recurrence clusters (CAPA.IS_RECURRING / RECURRENCE_COUNT / LINKED_CAPA_IDS) ---
# Cluster A: Equipment Fault, site=1, dept=2 (Maintenance), OC-001 wire rope.
# Cluster B: Training Gap, site=5, dept=26 (Operations), forklift-pedestrian.
# RECURRENCE_COUNT = number of prior occurrences linked at the time of this
# CAPA; LINKED_CAPA_IDS = those prior occurrences, in order.
RECURRENCE_CLUSTERS = {
    1: (0, []),
    26: (1, [1]),
    27: (2, [1, 26]),
    28: (3, [1, 26, 27]),
    29: (4, [1, 26, 27, 28]),
    30: (5, [1, 26, 27, 28, 29]),
    31: (0, []),
    32: (1, [31]),
    33: (2, [31, 32]),
    34: (3, [31, 32, 33]),
    35: (4, [31, 32, 33, 34]),
}

# RCA method free-text -> mirror ID. Not a real master table (RCA_METHOD_ID has
# no FK constraint in schema.sql) — minted purely for consistency/readability.
RCA_METHOD_MAP = {
    "5 Why Analysis": "RCA_METHOD_5WHY",
    "Fault Tree Analysis": "RCA_METHOD_FTA",
    "Bow-Tie Analysis": "RCA_METHOD_BOWTIE",
    "Direct Cause Identification": "RCA_METHOD_DIRECT",
    "Incident Report Review": "RCA_METHOD_INCIDENT_REVIEW",
}

ENTERPRISE_CONTACT_EMAIL = "anil.mehta@acertech.in"  # ENTERPRISE.contact_emp_id (234)

# =============================================================================
# ID helpers + lookups
# =============================================================================

def _site_id(n: int) -> str:
    return f"SITE_{n:02d}"


def _group_id(n: int) -> str:
    return f"GROUP_{n:02d}"


def _capa_id(n: int) -> str:
    return f"CAPA_{n:04d}"


def _action_id(n: int) -> str:
    return f"ACTION_{n:04d}"


def _rca_id(n: int) -> str:
    return f"RCA_{n:04d}"


def _investigation_id(n: int) -> str:
    return f"INV_{n:04d}"


def _review_id(n: int) -> str:
    return f"REVIEW_{n:04d}"


def _closure_id(n: int) -> str:
    return f"CLOSURE_{n:04d}"


EMP_EMAIL = {emp_id: email for emp_id, _dept_id, _name, _role, _desc, email in EMPLOYEES_SRC}
DEPT_SITE = {dept_id: site_id for dept_id, site_id, _name, _desc in DEPARTMENTS_SRC}
DEPT_FIRST_EMP = {}
for _emp_id, _dept_id, _name, _role, _desc, _email in EMPLOYEES_SRC:
    DEPT_FIRST_EMP.setdefault(_dept_id, _email)

# capa_id -> parsed CAPAS_SRC row, for cross-entity lookups while building
# actions/RCA/investigations/reviews/closure.
CAPA_BY_ID = {row[0]: row for row in CAPAS_SRC}


# =============================================================================
# Transform functions
# =============================================================================

def build_tenant() -> dict:
    return {
        "tenant_id": TENANT_ID,
        "tenant_name": ENTERPRISE["name"],
        "domain": "acertech.in",
        "status_id": GENERIC_ACTIVE_STATUS_ID,
        "contact_name": "Anil Mehta",
        "contact_email": ENTERPRISE_CONTACT_EMAIL,
    }


def build_sites() -> list[dict]:
    return [
        {
            "site_id": _site_id(sid),
            "tenant_id": TENANT_ID,
            "site_name": name,
            "status_id": GENERIC_ACTIVE_STATUS_ID,
            "meta": SITE_DESC.get(sid),
        }
        for sid, name in SITES_SRC
    ]


def build_groups() -> list[dict]:
    return [
        {
            "group_id": _group_id(did),
            "tenant_id": TENANT_ID,
            "group_name": name,
            "group_description": desc,
            "group_manager_email": DEPT_FIRST_EMP.get(did),
            "status_id": GENERIC_ACTIVE_STATUS_ID,
        }
        for did, _site_id_, name, desc in DEPARTMENTS_SRC
    ]


def build_site_groups() -> list[dict]:
    seen = set()
    rows = []
    for did, sid, _name, _desc in DEPARTMENTS_SRC:
        key = (sid, did)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "tenant_id": TENANT_ID,
            "site_id": _site_id(sid),
            "group_id": _group_id(did),
        })
    return rows


def build_users() -> list[dict]:
    return [
        {
            "user_email": email,
            "tenant_id": TENANT_ID,
            "full_name": name,
            "status_id": GENERIC_ACTIVE_STATUS_ID,
            "group_id": _group_id(did),
        }
        for _emp_id, did, name, _role, _desc, email in EMPLOYEES_SRC
    ]


def build_employees() -> list[dict]:
    """MSTR_TENANT_EMP — employee/org-directory record (role + role_description),
    distinct from MSTR_USERS_METADATA's login-identity fields. See phase2.md
    decision 1. Linked back to the MSTR_USERS_METADATA row via USER_EMAIL
    since every employee here also has a build_users() row."""
    return [
        {
            "emp_id": f"EMP_{emp_id:04d}",
            "tenant_id": TENANT_ID,
            "site_id": _site_id(DEPT_SITE[did]),
            "group_id": _group_id(did),
            "user_email": email,
            "full_name": name,
            "role_title": role,
            "role_description": desc,
            "status_id": GENERIC_ACTIVE_STATUS_ID,
        }
        for emp_id, did, name, role, desc, email in EMPLOYEES_SRC
    ]


def build_masters() -> dict:
    severities = [
        {"severity_id": sid, "severity_name": name, "severity_level": level,
         "display_order": level, "description": SEVERITY_DESC.get(name)}
        for name, (sid, level) in SEVERITY_MAP.items()
    ]
    priorities = [
        {"priority_id": pid, "priority_level": name, "display_order": i + 1,
         "description": PRIORITY_DESC.get(name)}
        for i, (name, pid) in enumerate(PRIORITY_MAP.items())
    ]
    capa_statuses = [
        {"status_id": sid, "tenant_id": TENANT_ID, "status": name, "status_description": f"{name} (CAPA)", "source_table": "CAPA"}
        for name, sid in STATUS_MAP.items()
    ] + [
        {"status_id": sid, "tenant_id": TENANT_ID, "status": name, "status_description": f"{name} (CAPA Action)", "source_table": "CAPA_ACTIONS"}
        for name, sid in ACTION_STATUS_MAP.items()
    ]
    # de-dupe capa_types by id (multiple source names collapse onto the same id,
    # e.g. "Corrective and Preventive" -> TYPE_CORRECTIVE)
    capa_types_by_id = {}
    for name, tid in CAPA_TYPE_MAP.items():
        capa_types_by_id.setdefault(tid, name.split(" and ")[0])
    capa_types = [
        {"capa_type_id": tid, "tenant_id": TENANT_ID, "capa_type_name": name,
         "capa_type_description": CAPA_TYPE_DESC.get(tid)}
        for tid, name in capa_types_by_id.items()
    ]
    categories = [
        {
            "category_id": cid,
            "tenant_id": TENANT_ID,
            "category_name": name,
            "category_description": CATEGORY_DESC.get(name),
            "created_by": ENTERPRISE_CONTACT_EMAIL,
        }
        for name, cid in CATEGORY_MAP.items()
    ]
    mstr_status = [
        {
            "status_id": GENERIC_ACTIVE_STATUS_ID,
            "status": "Active",
            "status_description": "Generic active status shared by tenant/site/group/user master rows",
            "source_table": "GENERIC",
        }
    ]
    return {
        "severities": severities,
        "priorities": priorities,
        "capa_statuses": capa_statuses,
        "capa_types": capa_types,
        "categories": categories,
        "mstr_status": mstr_status,
    }


def build_capas() -> list[dict]:
    rows = []
    for (cid, title, description, source_type, source_id, site_id, dept_id,
         severity, priority, status, due_date, capa_type, closed_at,
         created_by, assigned_to) in CAPAS_SRC:
        severity_id, _level = SEVERITY_MAP[severity]
        recurrence_count, linked = RECURRENCE_CLUSTERS.get(cid, (0, []))
        rows.append({
            "capa_id": _capa_id(cid),
            "tenant_id": TENANT_ID,
            "site_id": _site_id(site_id),
            "source_module": source_type,
            "source_record_id": source_id,
            "owner_group_id": _group_id(dept_id),
            "capa_title": title,
            "capa_description": description,
            "rca_method_id": None,  # set below from CAPA_RCA's rca_method once known
            "root_cause": None,     # set below from root_cause_statement
            "priority_id": PRIORITY_MAP[priority],
            "severity_id": severity_id,
            "capa_type_id": CAPA_TYPE_MAP[capa_type],
            "status_id": STATUS_MAP[status],
            "created_by": EMP_EMAIL[created_by],
            "assigned_to": EMP_EMAIL[assigned_to],
            "due_date": due_date,
            "completed_date": closed_at,
            "capa_closure_date": closed_at,
            "recurrence_count": recurrence_count,
            "linked_capa_ids": ",".join(_capa_id(x) for x in linked) or None,
            "is_recurring": 1 if recurrence_count > 0 else 0,
        })
    # second pass: thread RCA method + root cause statement onto CAPA.ROOT_CAUSE
    # / RCA_METHOD_ID (these live on capa_root_causes in the source, which maps
    # to CAPA.ROOT_CAUSE + CAPA.RCA_METHOD_ID per phase1.md Source -> Mirror Mapping)
    rc_by_capa = {rc[1]: rc for rc in ROOT_CAUSES_SRC}
    for cid, row in zip([r[0] for r in CAPAS_SRC], rows):
        rc = rc_by_capa[cid]
        statement, rca_method = rc[2], rc[3]
        row["root_cause"] = statement
        row["rca_method_id"] = RCA_METHOD_MAP[rca_method]
    return rows


def build_actions() -> list[dict]:
    rows = []
    for (aid, capa_ref, action_type, title, description, owner_id, due_date,
         evidence_required, effectiveness_check, effectiveness_result,
         effectiveness_verified_at, _strength_label, _ai_generated) in ACTIONS_SRC:
        parent = CAPA_BY_ID[capa_ref]
        (_pid, _ptitle, _pdesc, _psrc_type, _psrc_id, p_site_id, _pdept_id,
         p_severity, p_priority, p_status, _pdue, _ptype, _pclosed, p_created_by,
         _passigned_to) = parent
        verified = effectiveness_result in ("Pass", "Fail")
        rows.append({
            "action_id": _action_id(aid),
            "capa_id": _capa_id(capa_ref),
            "tenant_id": TENANT_ID,
            "site_id": _site_id(p_site_id),
            "action_title": title,
            "action_description": description,
            "priority_id": PRIORITY_MAP[p_priority],
            "capa_type_id": CAPA_TYPE_MAP[action_type],
            "severity_id": SEVERITY_MAP[p_severity][0],
            "created_by": EMP_EMAIL[p_created_by],
            "assigned_to": EMP_EMAIL[owner_id],
            "status_id": ACTION_STATUS_MAP[p_status],
            "due_date": due_date,
            "completion_date": effectiveness_verified_at if verified else None,
            "verification_required": 1 if effectiveness_check else 0,
            "verified_by": EMP_EMAIL[owner_id] if verified else None,
            "verified_date": effectiveness_verified_at if verified else None,
            "evidence_required": evidence_required or [],
        })
    return rows


def build_rca() -> list[dict]:
    rows = []
    for n, (rc_id, capa_ref, statement, rca_method, category,
            contributing_factors, failed_controls, missing_controls) in enumerate(ROOT_CAUSES_SRC, start=1):
        rows.append({
            "rca_id": _rca_id(n),
            "capa_id": _capa_id(capa_ref),
            "tenant_id": TENANT_ID,
            "contributing_factors": contributing_factors or [],
            "failed_controls": failed_controls or [],
            "missing_controls": missing_controls or [],
            "root_cause_category": CATEGORY_MAP[category],
        })
    return rows


def build_investigations() -> list[dict]:
    rows = []
    for n, (rc_id, capa_ref, statement, rca_method, _category,
            _cf, _fc, _mc) in enumerate(ROOT_CAUSES_SRC, start=1):
        parent = CAPA_BY_ID[capa_ref]
        (_pid, title, _pdesc, _psrc_type, _psrc_id, p_site_id, _pdept_id,
         _psev, _ppri, _pstatus, _pdue, _ptype, _pclosed, p_created_by,
         _passigned_to) = parent
        outcome = "Direct Cause Identified" if rca_method == "Incident Report Review" else "Root Cause Confirmed"
        rows.append({
            "investigation_id": _investigation_id(n),
            "capa_id": _capa_id(capa_ref),
            "tenant_id": TENANT_ID,
            "site_id": _site_id(p_site_id),
            "investigation_title": f"Root Cause Investigation — {title}"[:255],
            "investigation_description": statement,
            "investigator_email": EMP_EMAIL[p_created_by],
            "investigation_outcome": outcome,
        })
    return rows


def build_reviews() -> list[dict]:
    rows = []
    for n, (aid, capa_ref, _atype, _atitle, _adesc, _owner, _adue,
            _evid, effectiveness_check, effectiveness_result,
            effectiveness_verified_at, _strength, _ai) in enumerate(ACTIONS_SRC, start=1):
        parent = CAPA_BY_ID[capa_ref]
        (_pid, _ptitle, _pdesc, _psrc_type, _psrc_id, p_site_id, _pdept_id,
         _psev, _ppri, _pstatus, _pdue, _ptype, _pclosed, _pcreated_by,
         p_assigned_to) = parent
        rows.append({
            "review_id": _review_id(n),
            "capa_id": _capa_id(capa_ref),
            "tenant_id": TENANT_ID,
            "site_id": _site_id(p_site_id),
            "reviewed_by": EMP_EMAIL[p_assigned_to],
            "review_outcome": REVIEW_OUTCOME_MAP[effectiveness_result],
            "review_iteration": 1,
            "reviewer_comments": effectiveness_check or "Effectiveness check pending.",
            "review_date": effectiveness_verified_at,
            "review_type": "Effectiveness Check",
            "recurring_review": 0,
        })
    return rows


def build_closures() -> list[dict]:
    rows = []
    n = 0
    actions_by_capa: dict[int, list[tuple]] = {}
    for action in ACTIONS_SRC:
        actions_by_capa.setdefault(action[1], []).append(action)
    for (cid, _title, _desc, _src_type, _src_id, site_id, _dept_id,
         _sev, _pri, status, _due, _type, closed_at, created_by,
         assigned_to) in CAPAS_SRC:
        if status != "Closed":
            continue
        n += 1
        results = [a[9] for a in actions_by_capa.get(cid, [])]  # effectiveness_result
        if results and all(r == "Pass" for r in results):
            closure_status = "Verified Effective"
        elif any(r == "Fail" for r in results):
            closure_status = "Closed - Ineffective"
        else:
            closure_status = "Closed"
        approved_by = EMP_EMAIL[created_by]
        rows.append({
            "closure_id": _closure_id(n),
            "capa_id": _capa_id(cid),
            "tenant_id": TENANT_ID,
            "site_id": _site_id(site_id),
            "closed_by": EMP_EMAIL[assigned_to],
            "closure_date": closed_at,
            "closure_status": closure_status,
            "approval_status": "Approved",
            "approved_by": approved_by,
            "closure_comments": f"CAPA closed; final action effectiveness: {closure_status}.",
            # Extra keys not on the CapaClosure Pydantic model — CAPA_CLOSURE.
            # COMMENTED_BY/COMMENTED_DATE are NOT NULL in schema.sql but were
            # never added to models/schemas.py; the loader inserts them via
            # raw SQL directly from these JSON keys.
            "commented_by": approved_by,
            "commented_date": closed_at,
        })
    return rows


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    masters = build_masters()
    payload = {
        "tenant.json": build_tenant(),
        "sites.json": build_sites(),
        "groups.json": build_groups(),
        "site_groups.json": build_site_groups(),
        "users.json": build_users(),
        "employees.json": build_employees(),
        "severities.json": masters["severities"],
        "priorities.json": masters["priorities"],
        "capa_statuses.json": masters["capa_statuses"],
        "capa_types.json": masters["capa_types"],
        "categories.json": masters["categories"],
        "mstr_status.json": masters["mstr_status"],
        "capas.json": build_capas(),
        "actions.json": build_actions(),
        "rca.json": build_rca(),
        "investigations.json": build_investigations(),
        "reviews.json": build_reviews(),
        "closures.json": build_closures(),
    }
    for filename, data in payload.items():
        path = DATA_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        count = len(data) if isinstance(data, list) else 1
        print(f"wrote {filename}: {count} row(s)")


if __name__ == "__main__":
    main()
