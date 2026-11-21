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
The whole point of this package - in one example:
```python
from pyproject_toml_version import pyproject_version
# Or just wildcard import, since this ^ is the only public member of the package:
from pyproject_toml_version import *

version: str = pyproject_version('pyproject.toml')

# Or the first argument could be omitted,
# if the path is literally just 'pyproject.toml':
version = pyproject_version()

# And to use dynamic versions with not-yet-supported backends (see below):
version = pyproject_version(dynamic_field='tool.unknown.version.file-path')
```

> [!NOTE]
> ## 🚧🏗️ Dynamic versions supported only partially (but good enough)
> Better support is planned, but at the moment - the status is as follows:
> 
> | Feature | Status | Notes |
> |---|---|---|
> | Static versions<br />(any backend) | ✅ Just work: nothing to mishandle here | `project.version` field in your `pyproject.toml` |
> | Dynamic version:<br />**Hatchling** backend | ✅ Supported for most common cases<br />⚠️ Limitations on edge cases | ✅ [regex](https://hatch.pypa.io/latest/version/)-based detection that the official docs suggest (default or custom pattern)<br />❌ [code](https://hatch.pypa.io/latest/plugins/version-source/code/), [env](https://hatch.pypa.io/latest/plugins/version-source/env/) or [custom plugins](https://hatch.pypa.io/latest/plugins/version-source/reference/) as dynamic-version sources<br />⚠️ Only the main `pyproject.toml` is read, not external `hatch.toml` |
> | Dynamic version:<br />other backends | ❔ Likely yes - fallback mode<br />(see below) | `pyproject-toml-version` tries to extract the dynamic version by **guessing** from the most common formats, and it also requires you to explicitly specify the field to read from `pyproject.toml` for the dynamic-version source (the python file keeping the version) |
> | Dynamic version:<br />version-var names | ✅ The standard ones | ✅ Catches `__version__` / `VERSION`, any case (even mixed)<br />✅ For **Hatchling**, other names are caught with the native approach for custom regex-pattern |

## Fallback mode
Assume you have the following file structure:
```
Your project root
 ├─ pyproject.toml
 └─📂src
    └─📂my_module
       ├─ __init__.py
       ├─ ...
       └─ __version_meta.py
```

And you use a dynamic version, *AND* your build-backend is **anything but** Hatchling - so you have `pyproject.toml` like this:
```toml
[build-system]
build-backend = "not-yet-explicitly-supported-backend.build"

[project]
dynamic = ["version"]

[tool.some-unknown-build.version]
dyn_ver_path = "src/my_module/__version_meta.py"
```

**Very** likely (almost guaranteed), that `pyproject-toml-version` would still work for you just fine - try it:
```python
version = pyproject_version(dynamic_field='tool.some-unknown-build.version.dyn_ver_path')
```

`pyproject-toml-version` does some heuristics to attempt extracting the version regardless of the specific backend:

## Fallback mode in detail
- You **do** need to explicitly pass the `dynamic_field` arg to `pyproject_version()`: it tells what **field** in the `pyproject.toml` contains the path to a dynamic-version file.
  - For this example, it would be `tool.some-unknown-build.version.dyn_ver_path`
  - For Hatchling, there's no harm in passing it, but its value would simply be ignored.
- Then, `pyproject_version()` reads the field from `pyproject.toml` and tries to determine the actual path to this dyn-ver-file:
  - The file must exist, must be a file (not a dir), and be a `*.py` type.
  - The path is treated as relative to the dir where `pyproject.toml` itself lives.
  - First, the path from this field is attempted to be interpreted literally - expecting slashes there (and a lack of them meaning the file is in the same dir).
  - On fail, the same field is interpreted as a pythonic **module** path - i.e., `src.my_module.__version_meta` for this example.
  - Early-error if a proper python file can't be found.
- The version is attempted to be extracted - by trying to actually **import** the file as an isolated module (unaware of the rest of your project) and look for a matching variable:
  - The variable name must be `__version__` or `VERSION` *(case is ignored, so `__VERSION__`, `version`, `VERsion` etc. all match)*.
  - The variable must hold a string value.
  - `__version__` takes precedence over `VERSION`.
- If import fails (e.g., the module itself does some relative imports), a more "standard" regex-based search for the same variable names is performed, line by line.
  - The first match wins.
  - Like with real backends, `pyproject-toml-version` doesn't exclude the lines inside triple-quote multiline strings. So avoid having "version examples" in the module-level docstring.
- `v` prefix is **preserved** (it's not for Hatchling, unless you specify a custom regex pattern).