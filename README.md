# pipelines
All GitHub Action Workflows


```yaml
name: Build|Upload|Release Python Package

on:
  push:
    branches:
      - 'main'

jobs:
  publish:
    uses: Knuckles-Team/pipelines/.github/workflows/python_pipeline.yml@latest
    secrets:
      PYPI_API_TOKEN: ${{ secrets.PYPI_API_TOKEN }}
```