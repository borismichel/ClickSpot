# Data Spaces

A Data Space is a scoped, configured view over the warehouse. Each one has its own chat,
its own dashboards, and its own filters, so a team can work inside a focused slice of the
CRM without the rest getting in the way.

## Why they exist

The full warehouse covers every object, pipeline, and team. Most people only care about a
subset: a region, a product line, a single sales pipeline. A Data Space pins that scope
once, and everything inside it (the chat answers, the dashboards, the linked selections)
respects it.

## What a Data Space contains

- **Its own chat.** Questions are answered within the space's scope.
- **Its own dashboards.** Pinned results that belong to the space.
- **Its own filters.** The date ranges, owners, and pipelines that define the slice.

## How to work with one

The [Working with Data Spaces](../guides/data-spaces.md) guide covers creating a space,
configuring its scope in the designer, and using its chat and dashboards.

!!! note "Implementation"
    Data Spaces are backed by the `app/spaces/` module and persisted alongside objects,
    dashboards, and conversations. The [Backend](../backend.md) doc has the detail.
