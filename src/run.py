import logging

from src import setup_logging, create_app

setup_logging(default_level=logging.DEBUG, to_file=False)
app = create_app()

logger = logging.getLogger(__name__)


def main():
    logger.info("Launching Licksterr")
    app.run(debug=True)


if __name__ == '__main__':
    main()
