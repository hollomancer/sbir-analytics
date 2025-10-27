# API Evaluation for M&A Enrichment

This document summarizes the evaluation of potential data sources for enriching Merger & Acquisition (M&A) data.

## SEC EDGAR API

- **M&A Data Availability:** A primary source for M&A data, but the data is unstructured and embedded within SEC filings (e.g., Form 8-K, 10-K, 10-Q).
- **Data Access:** Accessible via a free, public REST API at `data.sec.gov`. No API key is required.
- **Limitations:** The main challenge is the complexity of extracting structured data from the unstructured text of the filings, which would require significant NLP work.
- **Conclusion:** A rich and authoritative source, but the data extraction is a complex task.

## GDELT Project

- **M&A Data Availability:** Does not provide direct M&A data, but offers a massive, real-time database of global news and events that can be used to monitor news and sentiment related to companies.
- **Data Access:** Data is available as raw TSV files or through Google BigQuery.
- **Limitations:** The data is unstructured for M&A analysis, and extracting relevant insights would require a sophisticated NLP pipeline.
- **Conclusion:** More suitable for providing supporting evidence or context for M&A events rather than as a primary source for M&A detection.

## OpenCorporates API

- **M&A Data Availability:** Does not provide direct M&A data, but M&A activity could be inferred by analyzing changes in corporate structure over time.
- **Data Access:** Accessible via a REST API that requires an API key.
- **Limitations:** This is a commercial service with a limited free tier. Inferring M&A events from corporate structure changes would be a complex implementation.
- **Conclusion:** Due to the cost and the complexity of inferring M&A events, OpenCorporates has been removed from the scope of this project. It is better suited for targeted, in-depth analysis of specific companies.

## Wikidata

- **M&A Data Availability:** A free and open knowledge base that contains structured data about M&A deals, including acquiring and acquired companies, acquisition dates, and deal values.
- **Data Access:** Accessible via a SPARQL endpoint.
- **Limitations:** The main limitations are the potential for incomplete data and the learning curve associated with SPARQL.
- **Conclusion:** A promising source for M&A data due to its structured nature and free access. It would likely be easier to integrate into the pipeline than the unstructured sources.
