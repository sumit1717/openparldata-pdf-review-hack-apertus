# Dependencies and source attribution

Existing source copied from private `sumit1717/doru-formrehearsal` at `7c41afde120ccbd3671684ed620ba529c30e309f` is identified per file in root `SOURCE_PINS.json`. The generic pipeline and schemas remain byte-identical. New layout/CLI/container/docs are isolated candidate additions; no earlier execution credit transfers to them.

Layout reference: HackApertus/project-template at `09f8e9e2b588db3325869b23c6d5132f5c3756f7`. The candidate follows its required paths but does not adopt the template report's placeholder CC-BY-4.0 paragraph as an effective license grant for the project.

Runtime pins preserved from the existing reviewed packaging:

- Python `3.12.14-slim-bookworm` image digest `sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`
- pypdf 6.10.0, converter hash lock
- jsonschema 4.26.0, attrs 26.1.0, jsonschema-specifications 2025.9.1, referencing 0.37.0, rpds-py 2026.6.3, typing-extensions 4.16.0, base hash lock

The rpds lock is for a CPython 3.12 Linux x86_64 wheel. Other architectures/platforms are unverified. The Dockerfile permits only binary hash-locked installs and checks dependency consistency. The base image and packages have not been pulled or installed in this work. Availability and image-build compatibility remain fresh-runtime tests.

The original license files for all seven exact hash-locked wheels are retained under [licenses](licenses/); [DEPENDENCY_LICENSES.json](../../DEPENDENCY_LICENSES.json) records their wheel and extracted-file hashes. Inspection was ZIP-data-only, without installation, dependency import or application execution. No wheel, installed package or base image is included. A later built-image distribution must preserve all package/base-image and transitive notices from that exact image.

The report embeds DejaVu Sans subsets; the original companion [font notice](licenses/DejaVu-Sans-Notice.txt) is included. The project grants are approved and scoped in [LICENSE_POLICY.md](../../LICENSE_POLICY.md), with Apache-2.0 [LICENSE](../../LICENSE), CC-BY-4.0 documentation and CDLA-Permissive-2.0 authored-data texts. These grants do not replace third-party terms.

AI assistance was used in implementation, report preparation and synthetic engineering review. It is not manual-human semantic gold. The public template-derived starter is 58272f3575871c894a9dbe381319c86fded26223; this local source upload remains pending.
