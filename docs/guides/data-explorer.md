# Data Explorer

The Data Explorer is the direct view of the warehouse — browse the tables, see their typed
columns, and follow the relationships between objects. It's where linked selections live:
pick a value in one table and every connected table filters to match.

## Browse the schema

See the bronze and silver tables with their typed columns — the modeled shape of your CRM,
without writing any SQL.

<figure markdown>
  ![Schema browser showing bronze and silver tables with typed columns](../assets/screenshots/explorer-schema.png){ .shot }
  <figcaption>The schema browser — bronze and silver tables with typed columns.</figcaption>
</figure>

## Linked selections

Select a value in any table and all connected tables filter automatically. This works by
traversing the relationship graph through the silver bridge tables — pick a company, and
its deals, contacts, owners, and pipeline stages narrow to match.

<figure markdown>
  ![Data explorer showing deals linked to contacts, companies, owners, and pipeline stages](../assets/screenshots/explorer-associative.png){ .shot }
  <figcaption>Linked selections — deals connected to contacts, companies, owners, and stages.</figcaption>
</figure>

The graph has 13 bridge edges across the silver layer, so most CRM objects are a hop or two
apart. See [The medallion warehouse](../concepts/warehouse.md) for the underlying tables and
[Architecture](../architecture.md) for the relationship graph itself.

<!-- UXDesigner (CLI-118 follow-up): expand into a walkthrough — opening a table, reading
columns, making a selection and watching connected tables filter, clearing selections, and
how it relates to the Analytics API. Add a short screen capture of a live selection. Run
the humanify skill. -->
