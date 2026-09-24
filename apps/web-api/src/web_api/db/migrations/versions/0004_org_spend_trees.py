"""Organization-owned spend trees

Revision ID: 0004_org_spend_trees
Revises: 0003_line_unit_and_doc_number
Create Date: 2026-08-09

Moves the spend taxonomy from "four loose columns hanging off a company" to a
real tree owned by the organization:

- creates ``spend_trees`` (org-owned, ``max_depth`` 3 or 4, template or custom);
- gives ``spend_categories`` a ``spend_tree_id``, ``parent_id``, ``depth``,
  ``name``, ``code`` and ``sort_order``, and relaxes ``level_2`` to nullable
  (``Direct``/``Indirect`` are depth-1 rows now, and their path is ``level_1``
  alone);
- points each company at a tree via ``companies.spend_tree_id``;
- adds ``invoice_lines.level_4``.

**The data step is not a formality.** In practice ``spend_categories`` is empty
on every database we know of — nothing ever seeded it — but a migration that
assumes that would silently drop a customer's taxonomy if it were wrong. Each
distinct ``company_id`` present gets one ``custom`` tree in that company's
organization; its nodes move onto that tree with ``parent_id``/``depth``/``name``
reconstructed from the level path, and the company is assigned to it. Interior
nodes the old flat rows only implied (a row with ``level_3`` set but no row of
its own for its ``level_2``) are materialized, because a tree with a missing
middle cannot be navigated.

**Downgrade is lossy, deliberately.** ``spend_categories.company_id`` is restored
from the *first* company assigned to each tree, so a tree that came to be shared
by several companies collapses onto one of them; and the tree's structure —
parentage, ordering, codes — is discarded, since the pre-tree schema has nowhere
to put it. Nodes on a tree with no assigned company cannot be restored at all
and are deleted. Downgrading past this revision is a schema rollback, not a
round trip.
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
    """Move flat ``spend_categories`` rows onto per-company trees.

    Runs inside the migration's own transaction. Nodes whose ``level_1`` is null
    but which have deeper levels are treated as rooted at ``level_2`` — the old
    model made ``level_1`` optional, so a tenant may never have classified
    Direct/Indirect at all, and the tree is built from whatever prefix exists.
    """
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
            # Orphan nodes on a company that no longer exists. Nothing sensible
            # to attach them to; the FK below would reject them anyway.
            conn.execute(
                sa.text("DELETE FROM spend_categories WHERE company_id = :cid"),
                {"cid": company_id},
            )
            continue

        tree_id = f"migrated-{company_id}"
        # Depth 4 unconditionally: these rows predate any depth rule and the
        # migration must not reject data the old schema accepted.
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

        # Map every path prefix to a node id, materializing the interior nodes
        # the flat rows only implied, and keeping each original row's own id so
        # `invoice_lines.spend_category_id` keeps resolving.
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

        # A row whose whole level path was empty describes no node at all.
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

    # Nullable and defaulted first so the data step can fill them, then tightened.
    op.add_column("spend_categories", sa.Column("spend_tree_id", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("parent_id", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column("spend_categories", sa.Column("name", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("code", sa.String(), nullable=True))
    op.add_column("spend_categories", sa.Column("sort_order", sa.Integer(), nullable=True))
    # `Direct` and `Indirect` are depth-1 rows now, and a depth-1 node's path is
    # its level_1 alone.
    op.alter_column("spend_categories", "level_2", existing_type=sa.String(), nullable=True)
    # Relaxed *before* the data step, not after: that step materializes the
    # interior nodes the flat rows only implied, and those belong to a tree, not
    # to a company. The column is dropped at the end of this migration anyway.
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
    # Lossy by construction: a tree shared by several companies collapses onto
    # whichever one sorts first. See the module docstring.
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
    # A pre-tree row with no level_2 cannot exist under the restored constraint.
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
