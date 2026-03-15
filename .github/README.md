# GitHub Actions Setup

## TestPyPI Deployment

The workflow `publish-testpypi.yml` automatically builds and publishes to TestPyPI.

### Setup Steps

1. **Generate TestPyPI token:**
   - Go to https://test.pypi.org/manage/account/token/
   - Create a new API token
   - Copy the token (starts with `pypi-...`)

2. **Add token to GitHub:**
   - Go to repository Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `TESTPYPI_TOKEN`
   - Value: paste your TestPyPI token
   - Click "Add secret"

3. **Trigger deployment:**
   - **Automatic:** Push to `main` branch
   - **Manual:** Go to Actions tab → "Publish to TestPyPI" → Run workflow

### Testing the installation

After successful deployment:
```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ docs-mcp
```

### Production PyPI

When ready for production, create `publish-pypi.yml` workflow:
- Remove `repository-url` parameter
- Use `PYPI_TOKEN` secret instead
- Trigger on git tags (e.g., `v0.1.0`)
