# Sample CSV Files

Sample data from Globant challenge specification.

## Files

- **hired_employees.csv**: 50 employee records with hire dates
- **departments.csv**: 12 departments
- **jobs.csv**: 43 job titles

## Format

All files are comma-separated with headers.

## Usage

```bash
./infra/update_pipeline.sh
```

This loads the sample CSV files to BigQuery through the complete pipeline.
