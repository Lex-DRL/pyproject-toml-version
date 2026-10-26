<div align="center">

# `pyproject.toml` → version

[![PyPI][pypi-shield]][pypi-url]
[![GitHub Release][github-release-shield]][github-release-url]

[pypi-shield]: https://img.shields.io/pypi/v/pyproject-toml-version?logo=pypi
[pypi-url]: https://pypi.org/p/pyproject-toml-version
[github-release-shield]: https://img.shields.io/github/v/release/Lex-DRL/pyproject-toml-version?logo=github
[github-release-url]: https://github.com/Lex-DRL/pyproject-toml-version/releases/latest

*Get version from `pyproject.toml` - static or dynamic, regardless of backend.*
</div>

## Usage

```python
from pyproject_toml_version import pyproject_version
# or, since the module exports only this ^ function:
from pyproject_toml_version import *

version: str = pyproject_version('pyproject.toml')
```

> [!WARNING]
> ## 🚧🏗️ `TODO:` Dynamic versions
> Dynamic versions support is planned, but - in this first minimal release - only static version is detected.
