"""Organization-owned spend trees

Revision ID: 0004_org_spend_trees
Revises: 0003_line_unit_and_doc_number
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "0004_org_spend_trees"
down_revision = "0003_line_unit_and_doc_number"
branch_labels = None
depends_on = None


_LEVELS = ("level_1", "level_2", "level_3", "level_4")


def _path(row) -> tuple:
    """The non-null prefix of a flat row's level path."""
    values = [getattr(row, level) for level in _LEVELS]
    path: list[str] = []
    for value in values:
        if value is None or value == "":
            break
        path.append(value)
    return tuple(path)


def _migrate_existing_nodes() -> None:
    """Move flat ``spend_categories`` rows onto per-company trees."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, company_id, level_1, level_2, level_3, level_4, description "
            "FROM spend_categories ORDER BY id"
        )
    ).fetchall()
    if not rows:
        return

    by_company: dict[str, list] = {}
    for row in rows:
        by_company.setdefault(row.company_id, []).append(row)

    for company_id, company_rows in by_company.items():
        org_id = conn.execute(
            sa.text("SELECT organization_id, name FROM companies WHERE id = :cid"),
            {"cid": company_id},
        ).fetchone()
        if org_id is None:
            conn.execute(
                sa.text("DELETE FROM spend_categories WHERE company_id = :cid"),
                {"cid": company_id},
            )
            continue

        tree_id = f"migrated-{company_id}"
        conn.execute(
            sa.text(
                "INSERT INTO spend_trees "
                "(id, organization_id, name, max_depth, source, template_version, archived_at) "
                "VALUES (:id, :org, :name, 4, 'custom', NULL, NULL)"
            ),
            {"id": tree_id, "org": org_id.organization_id, "name": f"{org_id.name} spend tree"},
        )
        conn.execute(
            sa.text("UPDATE companies SET spend_tree_id = :tid WHERE id = :cid"),
            {"tid": tree_id, "cid": company_id},
        )

        node_ids: dict[tuple, str] = {}
        paths = {_path(row): row for row in company_rows}
        for path, row in sorted(paths.items(), key=lambda item: len(item[0])):
            if not path:
                continue
            node_ids[path] = row.id

        interior: dict[tuple, str] = {}
        for path in list(node_ids):
            for length in range(1, len(path)):
                prefix = path[:length]
                if prefix not in node_ids and prefix not in interior:
                    interior[prefix] = f"migrated-node-{company_id}-{'-'.join(prefix)}"

        for prefix, node_id in sorted(interior.items(), key=lambda item: len(item[0])):
            levels = list(prefix) + [None] * (4 - len(prefix))
            conn.execute(
                sa.text(
                    "INSERT INTO spend_categories "
                    "(id, spend_tree_id, parent_id, depth, name, code, sort_order, "
                    " level_1, level_2, level_3, level_4, description) "
                    "VALUES (:id, :tid, NULL, :depth, :name, NULL, 0, "
                    " :l1, :l2, :l3, :l4, NULL)"
                ),
                {
                    "id": node_id, "tid": tree_id, "depth": len(prefix), "name": prefix[-1],
                    "l1": levels[0], "l2": levels[1], "l3": levels[2], "l4": levels[3],
                },
            )
        node_ids.update(interior)

        for path, node_id in node_ids.items():
            parent_id = node_ids.get(path[:-1]) if len(path) > 1 else None
            conn.execute(
                sa.text(
                    "UPDATE spend_categories SET spend_tree_id = :tid, parent_id = :pid, "
                    "depth = :depth, name = :name WHERE id = :id"
                ),
                {
                    "tid": tree_id, "pid": parent_id, "depth": len(path),
                    "name": path[-1], "id": node_id,
                },
            )

        conn.execute(
            sa.text(
                "DELETE FROM spend_categories "
                "WHERE company_id = :cid AND spend_tree_id IS NULL"
            ),
            {"cid": company_id},
        )


def upgrade() -> None:
    op.create_table(
        "spend_trees",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("template_version", sa.String(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_spend_trees_organization_id"), "spend_trees", ["organization_id"], unique=False
    )

    op.add_column("companies", sa.Column("spend_tree_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_companies_spend_tree_id", "companies", "spend_trees", ["spend_tree_id"], ["id"]
    )

    op.add_column("spend_categories", sa.Column("spend_tree_id", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("parent_id", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column("spend_categories", sa.Column("name", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("code", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("sort_order", sa.Integer(), nullable=True))
    op.alter_column("spend_categories", "level_2", existing_type=sa.String(), nullable=True)
    op.alter_column("spend_categories", "company_id", existing_type=sa.String(), nullable=True)

    _migrate_existing_nodes()

    op.execute("UPDATE spend_categories SET sort_order = 0 WHERE sort_order IS NULL")
    op.alter_column("spend_categories", "spend_tree_id", existing_type=sa.String(), nullable=False)
    op.alter_column("spend_categories", "depth", existing_type=sa.Integer(), nullable=False)
    op.alter_column("spend_categories", "name", existing_type=sa.String(), nullable=False)
    op.alter_column("spend_categories", "sort_order", existing_type=sa.Integer(), nullable=False)

    op.create_foreign_key(
        "fk_spend_categories_spend_tree_id",
        "spend_categories", "spend_trees", ["spend_tree_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_spend_categories_parent_id",
        "spend_categories", "spend_categories", ["parent_id"], ["id"],
    )
    op.create_unique_constraint(
        "uq_spend_category_sibling", "spend_categories", ["spend_tree_id", "parent_id", "name"]
    )
    op.create_unique_constraint(
        "uq_spend_category_code", "spend_categories", ["spend_tree_id", "code"]
    )
    op.create_index(
        op.f("ix_spend_categories_spend_tree_id"),
        "spend_categories", ["spend_tree_id"], unique=False,
    )

    op.drop_constraint("spend_categories_company_id_fkey", "spend_categories", type_="foreignkey")
    op.drop_column("spend_categories", "company_id")

    op.add_column("invoice_lines", sa.Column("level_4", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_lines", "level_4")

    op.add_column("spend_categories", sa.Column("company_id", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE spend_categories AS sc
           SET company_id = (
               SELECT c.id FROM companies AS c
                WHERE c.spend_tree_id = sc.spend_tree_id
                ORDER BY c.id
                LIMIT 1
           )
        """
    )
    op.execute("DELETE FROM spend_categories WHERE company_id IS NULL")
    op.alter_column("spend_categories", "company_id", existing_type=sa.String(), nullable=False)
    op.create_foreign_key(
        "spend_categories_company_id_fkey",
        "spend_categories", "companies", ["company_id"], ["id"],
    )

    op.drop_index(op.f("ix_spend_categories_spend_tree_id"), table_name="spend_categories")
    op.drop_constraint("uq_spend_category_code", "spend_categories", type_="unique")
    op.drop_constraint("uq_spend_category_sibling", "spend_categories", type_="unique")
    op.drop_constraint("fk_spend_categories_parent_id", "spend_categories", type_="foreignkey")
    op.drop_constraint("fk_spend_categories_spend_tree_id", "spend_categories", type_="foreignkey")
    op.execute("DELETE FROM spend_categories WHERE level_2 IS NULL")
    op.alter_column("spend_categories", "level_2", existing_type=sa.String(), nullable=False)
    op.drop_column("spend_categories", "sort_order")
    op.drop_column("spend_categories", "code")
    op.drop_column("spend_categories", "name")
    op.drop_column("spend_categories", "depth")
    op.drop_column("spend_categories", "parent_id")
    op.drop_column("spend_categories", "spend_tree_id")

    op.drop_constraint("fk_companies_spend_tree_id", "companies", type_="foreignkey")
    op.drop_column("companies", "spend_tree_id")

    op.drop_index(op.f("ix_spend_trees_organization_id"), table_name="spend_trees")
    op.drop_table("spend_trees")
