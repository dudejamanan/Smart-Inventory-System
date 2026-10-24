import contextlib
from sqlalchemy import create_engine, event, select
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
                        Personnel(uid="A1B2C3D4", name="Aarav Shah"),
                        Personnel(uid="11223344", name="Meera Patel"),
                    ]
                )
            if not s.scalar(select(InventoryItem.id).limit(1)):
                for i, name in enumerate(
                    ["Sensor kits", "Controller boards", "Spare components"]
                ):
                    item = InventoryItem(
                        name=name, marker_id=i, notes="Simulation demo item"
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
