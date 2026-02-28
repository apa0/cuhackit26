# RootWatch

An early-warning intelligence platform for South Carolina agriculture planners to detect and respond to data center threats before farms are lost

---

## The Problem

South Carolina is losing farmland fast — 281,000 acres converted between 2001–2016, and billions of dollars in data center projects are accelerating that trend. These projects are often approved quietly, with little transparency on water or electricity impact. A $2.4B data center was approved in Marion County during a January 2026 winter storm; most residents didn't know it was on the agenda.

The data to fight this exists. It's scattered across USGS water databases, USDA crop surveys, 46 county zoning boards, and state legislative filings. RootWatch connects them.

---

## What We're Building

RootWatch is a dashboard for SC agriculture planners with three core features:

**Threat Map** — An interactive map overlaying data center locations, USGS groundwater wells, USDA farmland data, and watershed boundaries. Click a data center to see its specs and which farms share its aquifer.

**Impact Analysis** — For any proposed data center, model projected groundwater risk, electricity rate increases, and the number of farms within a 5/10/25-mile radius.

**Alerts (planned)** — Notify planners when new zoning filings or public hearings are scheduled in counties they're watching.

---

## Architecture (planned)

- Flask backend with REST API
- Leaflet.js interactive map
- AWS Textract for OCR on zoning documents
- AWS Comprehend for sentiment analysis on public hearing transcripts
- S3 for document storage
- JSON files for hackathon; DynamoDB for production

---

## Data Sources

All public and free:

- Data center locations: Baxtel, DataCenterMap, news articles
- Groundwater: USGS Water Services API
- Farmland: USDA CropScape
- County boundaries: US Census TIGER/Line
- Electricity rates: EIA Open Data API
- SC legislation: SC Legislature Online

---

## Context

Two bills are moving through the SC legislature now:

- **Bill 867** — "Data Center Development Act": tiered permitting, water assessments, infrastructure reviews
- **Bill 4583** — "Data Center Responsibility Act": energy independence requirements, groundwater extraction ban, environmental liability

RootWatch provides the evidence layer these policies need — and the early-warning system SC's 25,000 farmers need to protect their land and water.

---

Built at CUhackit 2026 — Clemson University's annual hackathon.
