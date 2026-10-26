import contextlib
from sqlalchemy import create_engine, event, select, inspect
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Personnel, InventoryItem, ShelfSlot


class Store:
    def __init__(self, config):
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            config.db_url, connect_args={"check_same_thread": False, "timeout": 10}
        )

        @event.listens_for(self.engine, "connect")
        def pragmas(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")

        Base.metadata.create_all(self.engine)
        # Additive M2 -> operational schema upgrade. Existing history is retained.
        additions = {
            "personnel": {"level": "INTEGER NOT NULL DEFAULT 1"},
            "sessions": {"expires_ts": "FLOAT", "end_reason": "VARCHAR(20)"},
            "reconciliations": {"token": "VARCHAR(40)"},
            "inventory_items": {
                "tag_uid": "VARCHAR(20)",
                "min_level": "INTEGER NOT NULL DEFAULT 1",
                "loan_minutes": "INTEGER NOT NULL DEFAULT 60",
                "status": "VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'",
                "holder_id": "INTEGER REFERENCES personnel(id)",
                "due_ts": "FLOAT",
            },
        }
        with self.engine.begin() as conn:
            for table, columns in additions.items():
                present = {v["name"] for v in inspect(conn).get_columns(table)}
                for name, definition in columns.items():
                    if name not in present:
                        conn.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                        )
            conn.exec_driver_sql("DROP INDEX IF EXISTS one_open_session")
            # Cross-table UID identity must also hold during concurrent API writes.
            for table, column, other, other_column in [
                ("personnel", "uid", "inventory_items", "tag_uid"),
                ("inventory_items", "tag_uid", "personnel", "uid"),
            ]:
                for operation in ["INSERT", "UPDATE"]:
                    conn.exec_driver_sql(
                        f"CREATE TRIGGER IF NOT EXISTS registry_{table}_{operation} BEFORE {operation} ON {table} WHEN NEW.{column} IS NOT NULL AND EXISTS(SELECT 1 FROM {other} WHERE {other_column}=NEW.{column}) BEGIN SELECT RAISE(ABORT,'Tag is already registered in the other registry'); END"
                    )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS item_tag_unique ON inventory_items(tag_uid) WHERE tag_uid IS NOT NULL"
            )
            conn.exec_driver_sql("PRAGMA user_version=3")
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextlib.contextmanager
    def session(self):
        with self.factory() as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    def seed(self):
        with self.session() as s:
            if not s.scalar(select(Personnel.id).limit(1)):
                s.add_all(
                    [
                        Personnel(uid="A1B2C3D4", name="Aarav Shah", level=2),
                        Personnel(uid="11223344", name="Meera Patel"),
                    ]
                )
            if not s.scalar(select(InventoryItem.id).limit(1)):
                for i, name in enumerate(
                    ["Resistor Kit", "Multimeter", "Raspberry Pi"]
                ):
                    item = InventoryItem(
                        name=name,
                        marker_id=i,
                        notes="Simulation demo item",
                        tag_uid=["01020304", "05060708", "090A0B0C"][i],
                        min_level=i + 1,
                        loan_minutes=2 if i == 2 else 60,
                    )
                    s.add(item)
                    s.flush()
                    s.add(
                        ShelfSlot(
                            name=f"Bay {i + 1}",
                            roi_x=0.06 + i * 0.31,
                            roi_y=0.25,
                            roi_w=0.26,
                            roi_h=0.55,
                            marker_id=i,
                            item_id=item.id,
                        )
                    )


def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
