from smartnews_api.wsgi import build_app

DEV_SERVER_PORT = 8000


def main() -> None:
    # Flask's development server, for local use only; Docker runs gunicorn.
    build_app().run(host="127.0.0.1", port=DEV_SERVER_PORT)


if __name__ == "__main__":
    main()
