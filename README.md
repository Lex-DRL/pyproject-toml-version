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

# And to use dynamic versions with not-yet-supported backends
version: str = pyproject_version('pyproject.toml', dynamic_field='tool.unknown.version.file-path')
```

> [!NOTE]
> ## 🚧🏗️ Dynamic versions supported only partially
> Better support for dynamic versions is planned, but at the moment - only the following detected:
> - static versions - nothing to mishandle here, they just work ✅
> - Hatchling backend:
>   - [regex](https://hatch.pypa.io/latest/version/)-based detection (default or custom pattern) ✅
>   - [code](https://hatch.pypa.io/latest/plugins/version-source/code/), [env](https://hatch.pypa.io/latest/plugins/version-source/env/) or [custom plugins](https://hatch.pypa.io/latest/plugins/version-source/reference/) ❌
>   - Only the main `pyproject.toml` is read, not external `hatch.toml` ⚠️
> - Any other backends are treated in "fallback" mode - with a universal dynamic-version-detector, which tries to extract the dynamic version by **guessing** from the most common formats, and it also requires you to explicitly specify the field in `pyproject.toml` to read for the dynamic-version source (the python file keeping the version).
>   - Catches `__version__` or `VERSION` as variable names in the file; case ignored.
>   - Very likely, it would "just work" for you, but not guaranteed. Test before relying on the package.
