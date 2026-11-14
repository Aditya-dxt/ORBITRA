# SatQuery

**Owner:** Computer Vision & Image Processing Lead

SatQuery is responsible for satellite/image-query and computer-vision work that turns supported image inputs into candidate change records for ARES.

## Planned responsibilities

- Audit the selected dataset, image pairs, labels, metadata, access, licence, and limitations.
- Build the image-pair loader, preprocessing, and alignment steps supported by the data.
- Implement a documented baseline change detector and generate candidate regions.
- Provide confidence and uncertainty values with documented meanings.
- Evaluate the vision pipeline using Precision, Recall, F1, and IoU, with visual examples and failure cases.
- Export documented, versioned candidate records for ARES.

## Integration dependency

Agree on a versioned candidate-record schema with the ARES owner before finalizing implementation. Document field names and types, image/pair identifiers, region geometry and coordinate reference, units where applicable, confidence, uncertainty, predicted change, schema version, missing-value behavior, and validation examples.

## Status

Scaffold only. Dataset selection, code, evaluation, and candidate records have not yet been completed. Update this README for meaningful SatQuery changes with the summary, run instructions, checks, limitations, and interface changes.
