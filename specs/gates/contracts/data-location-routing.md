# Contract — data-location-routing

Provider: pipelines PIPE-GATES-R014.7
Consumer: medulla MEDULLA-SRC-AUTH-R001

## Wire shape

Each connector declares `DataLocation` entries with the held classes, the instance or store, the read tool, a route parameter and a federation key. The SDK renders them as `sc:DataLocation` individuals. The engine imports them with the connector pack and resolves source routing through them.

## Refusal codes

The gate reports `locations:` gaps for a missing location, held class, instance or read tool.

## Authoritative types

The gate check is `location_gaps` in `pipelines_hooks/hygiene/connector_surface_contracts.py`. The engine projection is owned by `MEDULLA-SRC-AUTH-R001`.

## Test vectors

`tests/hooks/test_connector_surface.py::test_incomplete_data_location_is_a_gap`.
