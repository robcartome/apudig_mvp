"""Read-only comparison of Website migration history with its physical schema."""

from django.db.migrations.loader import MigrationLoader


def audit_website_schema(connection):
    loader = MigrationLoader(connection)
    loader.graph.validate_consistency()
    loader.check_consistent_history(connection)
    applied = set(loader.applied_migrations)
    replaced_nodes = {
        node for migration in loader.replacements.values() for node in migration.replaces
    }
    known_nodes = set(loader.graph.nodes) | replaced_nodes
    unknown = sorted(
        name for app, name in applied
        if app == "websites" and (app, name) not in known_nodes
    )
    nodes = sorted(applied.intersection(loader.graph.nodes))
    state = loader.project_state(nodes=nodes)
    expected = {
        model._meta.db_table: model
        for model in state.apps.get_models(include_auto_created=True)
        if model._meta.app_label == "websites"
    }
    tables = set(connection.introspection.table_names())
    actual = {name for name in tables if name == "websites" or name.startswith(("website_", "websites_"))}
    issues = []
    if unknown:
        issues.append("Hay migraciones websites aplicadas sin fuente local: " + ", ".join(unknown))
    if actual != set(expected):
        issues.append(f"Tablas divergentes: faltantes={sorted(set(expected) - actual)}, no registradas={sorted(actual - set(expected))}")
    details = {}
    with connection.cursor() as cursor:
        for table, model in sorted(expected.items()):
            if table not in actual:
                continue
            columns = {col.name: col for col in connection.introspection.get_table_description(cursor, table)}
            fields = {field.column: field for field in model._meta.local_fields}
            if set(columns) != set(fields):
                issues.append(f"Columnas divergentes en {table}.")
            for column in set(columns).intersection(fields):
                if columns[column].null_ok != fields[column].null:
                    issues.append(f"Nulabilidad divergente en {table}.{column}.")
            constraints = connection.introspection.get_constraints(cursor, table)
            for constraint in (*model._meta.constraints, *model._meta.indexes):
                if constraint.name not in constraints:
                    issues.append(f"Falta restricción/índice {table}.{constraint.name}.")
            for field in fields.values():
                if field.primary_key or field.unique:
                    kind = "primary_key" if field.primary_key else "unique"
                    if not any(item.get(kind) and item["columns"] == [field.column] for item in constraints.values()):
                        issues.append(f"Falta unicidad en {table}.{field.column}.")
                if field.is_relation and field.db_constraint:
                    target = (field.remote_field.model._meta.db_table, field.target_field.column)
                    if not any(item.get("foreign_key") == target and item["columns"] == [field.column] for item in constraints.values()):
                        issues.append(f"Falta FK en {table}.{field.column}.")
            details[table] = {
                "columns": sorted(columns),
                "indexes": sorted(name for name, item in constraints.items() if item.get("index")),
                "constraints": sorted(name for name, item in constraints.items() if not item.get("index")),
            }
    return {
        "engine": connection.vendor,
        "website_migrations": sorted(name for app, name in applied if app == "websites"),
        "schema": details,
        "issues": issues,
        "compatible": not issues,
    }
