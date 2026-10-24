import argparse
import logging
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from app.config import Config

    c = Config()
    if args.seed:
        from app.db.store import Store

        Store(c).seed()
        print("Demo personnel and inventory seeded")
        return
    from app.main import create_app

    uvicorn.run(create_app(c, args.simulate), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
