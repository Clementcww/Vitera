"""Reference tables. Data, no logic.

Everything here is a lookup a coder could verify by hand — that is the point of
the trust boundary: if a defect class is decidable by table join, it never
reaches the model.

ponytail: hardcoded slices of the real masters, enough to run the sample
episode. Swap for CSV loads over data/masters/ once the real ICD-10, ICD-9-CM
and Permenkes INA-CBG tables are in the repo — the call sites below are all
dict lookups, so only this module changes.
"""

# --- ICD-10 diagnoses: code -> description. Descriptions are the model input. ---
ICD10 = {
    "A41.9": "Sepsis, unspecified organism",
    "N18.3": "Chronic kidney disease, stage 3",
    "N18.4": "Chronic kidney disease, stage 4",
    "N18.5": "Chronic kidney disease, stage 5",
    "D64.9": "Anaemia, unspecified",
    "E11.9": "Type 2 diabetes mellitus without complications",
    "O80": "Single spontaneous delivery",
}

# --- ICD-9-CM procedures ---
ICD9 = {
    "99.04": "Transfusion of packed cells",
    "88.91": "Magnetic resonance imaging of brain and brain stem",
}

DESCRIPTIONS = {**ICD10, **ICD9}

# --- R2: codes valid only for one sex, and only within an age band. ---
SEX_ONLY = {"O80": "F"}
AGE_BAND = {"O80": (12, 60)}

# --- R3: pairs that cannot both appear on one episode. ---
EXCLUSIVE_PAIRS = [("N18.3", "N18.4"), ("N18.4", "N18.5")]

# --- M1: a coded stage and the more specific stages that could replace it. ---
MORE_SPECIFIC = {
    "N18.3": ["N18.4", "N18.5"],
    "N18.4": ["N18.5"],
}

# --- Grouper: sorted code set -> (INA-CBG group, tariff IDR). ---
TARIFF = {
    ("A41.9", "N18.3"): ("A-4-13-II", 18_400_000),
    ("A41.9", "N18.4"): ("A-4-13-II", 20_550_000),
    ("99.04", "A41.9", "N18.4"): ("A-4-13-III", 21_950_000),
    ("99.04", "A41.9", "N18.3"): ("A-4-13-III", 19_800_000),
}

# --- C1: documents each stage must carry before the berkas is submittable. ---
REQUIRED_DOCS = {
    "checkin": ["sep", "spri"],
    "instay": [],
    "checkout": ["resume_medis", "tagihan", "grouping"],
}

# --- C2: documents that are worthless without a DPJP signature. ---
MUST_BE_SIGNED = ["resume_medis", "laporan_operasi"]

# --- C3: coded procedure -> the doc type that must evidence it. ---
PROC_EVIDENCE = {"99.04": "cppt", "88.91": "radiologi"}

# --- C1: an order written in the notes -> (doc type that must follow, IDR at
# risk if it never arrives). Caught on hospital day 2, someone walks to
# radiologi. Caught after submission, it is a pend.
ORDER_EVIDENCE = [
    (r"mri\s+\w+\s+diusulkan", "radiologi", 4_800_000),
    (r"kultur\s+darah\s+diusulkan", "lab", 1_200_000),
]


def describe(code: str) -> str:
    return DESCRIPTIONS.get(code, code)


def tariff(codes) -> tuple[str | None, int]:
    return TARIFF.get(tuple(sorted(codes)), (None, 0))
