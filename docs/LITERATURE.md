# Literature synthesis — defect prevalence in Indonesian BPJS inpatient claims

Every injection rate in `config/defects.yaml` traces to a row in this file.
Rows are graded, because not all of these are equally good evidence and the
paper should say so.

**Evidence grades**

| Grade | Meaning |
|---|---|
| **A** | Peer-reviewed, primary data, defect-level measurement, inpatient, Indonesia |
| **B** | Peer-reviewed, primary data, but single-site, outpatient, or share-of-pending rather than prevalence |
| **C** | Peer-reviewed secondary/review, or primary data from a related system (Malaysia MY-DRG) |
| **D** | Grey literature, vendor content, news. **Never cited in the paper as evidence** — listed only to show where a widely-repeated figure actually comes from |

---

## The anchor study

**Opitasari C, Nurwahyuni A. (2018).** *The completeness and accuracy of clinical
coding for diagnosis and medical procedure on the INA-CBGs claim amounts at a
hospital in South Jakarta.* Health Science Journal of Indonesia 9(1):14–18.
DOI [10.22435/hsji.v9i1.464](https://doi.org/10.22435/hsji.v9i1.464). **Grade A.**

Design matters here: 105 BPJS **inpatient** medical records, November 2017,
government hospital in South Jakarta. Hospital coders' output was **re-coded by
a standard coder** from the Ministry of Health national casemix centre (PORMIKI
member, certified, senior), and both were re-grouped through the same INA-CBG
software. The difference between the two is the measurement.

That design is very close to what Vitera claims to automate, which is why this
study carries most of the generator.

| Measure | Value | Table |
|---|---|---|
| Discharge summary incomplete — lab / supporting examination | **12.2%** (13/105) | T1 |
| Discharge summary incomplete — all other components | 0–0.9% | T1 |
| Secondary diagnosis: record ↔ discharge summary **non-conformity** | **68.6%** (72/105) | T2 |
| Primary diagnosis non-conformity | 8.6% (9/105) | T2 |
| Procedure non-conformity | 5.6% (4/105) | T2 |
| Primary diagnosis **coded inaccurately** vs. standard coder | **21.9%** (23/105) | T3 |
| Secondary diagnosis coded inaccurately | 10.5% (11/105) | T3 |
| Procedure coded inaccurately | 3.9% (3/105) | T3 |
| Cases where hospital **undercoded** (standard coder's claim higher) | **13.3%** (14/105) | T4 |
| Cases where hospital **overcoded** (standard coder's claim lower) | **6.7%** (7/105) | T4 |
| Cases identical | 80.0% (84/105) | T4 |
| Net revenue difference | Rp 65,005,500 on Rp 1,584,607,500 ≈ **4%** | T4 |

Also reported in that paper's preliminary section: BPJS returned **24.5%** of the
hospital's inpatient claim documents (Jan–Mar 2017) against an internal target
of under 20%, and the most common return reason was confirmation of diagnosis
and procedure coding (**43.4%**).

### Three things this study settles for us

1. **The undercoding-to-overcoding ratio is roughly 2:1** (13.3% vs. 6.7%).
   Undercoding is the larger phenomenon, which is the paper's "undercoding as
   the reveal" narrative — now with a primary source instead of an assertion.

2. **Secondary-diagnosis documentation is the dominant failure**, at 68.6%
   non-conformity — an order of magnitude worse than primary diagnosis (8.6%)
   or procedures (5.6%). The authors attribute it directly to underreporting in
   the discharge summary: *"many secondary diagnoses in medical records were
   underreporting in the discharge summary… Missing documentation of secondary
   diagnosis or comorbidity can lead to miscoding or undercoding."*

   This is precisely the `documented_day = null` case in our generator, and it
   is the single most important number in this document.

3. **Defect prevalence far exceeds the pend rate.** Pend rates run 12–17%
   (below), but observed defect prevalence runs 12–69% depending on class.
   Most defects therefore never pend — they are silently absorbed as
   underpayment. **That gap is the product's reason to exist**, and it is
   measured, not assumed.

---

## Pend rates — inpatient

| Site / study | Period | n | Pend rate | Grade |
|---|---|---|---|---|
| RS Universitas Airlangga — Maulida & Djunawan (2022), *MKMI* 21(6):374–379, DOI [10.14710/mkmi.21.6.374-379](https://doi.org/10.14710/mkmi.21.6.374-379) | Dec 2021 | 720 | **12.2%** (88/720) | A |
| RS Dharma Kerti Tabanan — Dewi & Wirajaya, *Jurnal Ekonomi Kesehatan Indonesia* 11(1) | Aug–Oct 2024 | 779 | **16.7%** (130/779) | B |
| Government hospital, South Jakarta — Opitasari & Nurwahyuni (2018), preliminary | Jan–Mar 2017 | — | **24.5%** returned | A |

**Working range: 12–17%**, with one site at 24.5%. The design brief's "~15%" sits
inside this range and is defensible as *reported at 12–17% across single-site
Indonesian inpatient studies* — not as a national figure, which nobody has
published.

## Pend causes — inpatient, share of pended claims

| Study | Berkas / admin | Coding | Supporting exam | Clinical / therapy evidence | Grade |
|---|---|---|---|---|---|
| Maulida & Djunawan (2022), n=88 | 34% | 33% | 23% | 10% | A |
| RS UNS 2023, n=617 | 32% (admin) | 12% | — | 56% (clinical) | B |
| Multi-site, n≈4,879 | 61.4% | 9.4% | 21.1% | — | B |
| Outpatient comparator | 35.3% | 18.1% | — | 46.6% (indikasi medis) | B |

These disagree substantially, which is expected: "berkas tidak lengkap" and
"pending klinis" are defined differently at each site. **We use the
Maulida distribution** because it is inpatient, single-period, and its four
categories map cleanly onto D1 / D2–D3 / D5 / D3.

## Coding accuracy — background

| Study | Finding | Grade |
|---|---|---|
| Systematic review, 45 of 458 articles, 2009–2019, *Jurnal Rekam Medis dan Informasi Kesehatan* [7688](https://ejournal.poltekkes-smg.ac.id/ojs/index.php/RMIK/article/view/7688) | ICD-10 coding accuracy **21–81% in hospitals**, 26–45% in puskesmas | C |
| Zafirah et al. (2018), *BMC Health Serv Res* 18(38) — Malaysia MY-DRG | Coding errors in **89.4%** of records; secondary diagnoses the highest | C |
| Kresnowati & Ernawati (2014), RSUD Semarang | Procedure coding errors 50%, principal diagnosis 20.6% | C |

The 21–81% range is too wide to set a rate from. It is useful only as evidence
that accuracy varies enormously by site — which is why `config/sites.yaml`
models documentation quality per hospital and why holdout is by hospital.

---

## Claims we currently CANNOT support

This section exists so nobody puts these on a slide.

| Claim in our materials | What we actually found | Action |
|---|---|---|
| "Only 5–15% of claims receive pre-submission review at hospitals above 1,000 claims/month" | Traces to **medminutes.io**, a vendor blog (grade D). No peer-reviewed source located. | **Do not state as a finding.** Reframe as: casemix units of 2–5 staff cannot review 30–50 claims/day at volume — an arithmetic argument from staffing, presented as our estimate. |
| "Casemix unit of 2–5 people" | Same vendor source, grade D | Same treatment — present as typical, not as measured |
| ">60–70% of claims sit at severity level I, indicating systematic under-documentation" | Same vendor source, grade D | **Drop**, or replace with Opitasari's 68.6% secondary-diagnosis non-conformity, which is grade A and makes the same point better |
| "Undercoding costs ~4.2% of claim revenue" | Opitasari measures **4%**, single site, n=105 | Restate as **"~4% at one hospital (Opitasari & Nurwahyuni 2018)"**. Where 4.2% came from is unknown — if there is another source, add it here; otherwise correct the number in the design brief |
| "8–12% bad debt from pended claims" | Not located | Unsupported. Flagged in `CRITERIA_PROGRESS.md` as needing verification; still unverified |

---

## Gaps that no literature closes

1. **No published Indonesian data on the time gap between clinical signal and
   documentation.** Opitasari establishes *that* secondary diagnoses go
   undocumented (68.6%); nothing establishes *when* they would have been
   documentable. `temporal.signal_to_doc_gap_days` is therefore an **explicit
   modelling assumption, not a cited rate**, and every report of
   `detection_lead_time` must say so. This is honesty note 1 in
   `intent-anchor.md`, and it is the attack we are most exposed to.

2. **No national pend-rate statistic.** All figures are single-site.

3. **No public BPJS pend-reason taxonomy**, so our eight defect classes are
   constructed from study categories rather than from the payer's own codes.

---

*Compiled bucket 3. Add a row before adding a rate.*
